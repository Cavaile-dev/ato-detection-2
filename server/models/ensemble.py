"""
Ensemble Model
Combines multiple anomaly detection models with shared preprocessing and
calibrated score fusion so the final score is stable across model types.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import joblib
import numpy as np

from server.config import (
    FEATURE_COLUMNS,
    ENSEMBLE_MODEL,
    ENSEMBLE_WEIGHTS,
    FEATURE_VARIANCE_EPSILON,
    FEATURE_MIN_NONZERO_OCCURRENCES,
    FEATURE_CLIP_QUANTILE_SMALL_SAMPLE,
    FEATURE_CLIP_QUANTILE_LARGE_SAMPLE,
)

try:
    from .isolation_forest import IsolationForestModel
    from .svm import SVMModel
    from .lstm_autoencoder import LSTMAutoencoderModel
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from server.models.isolation_forest import IsolationForestModel
    from server.models.svm import SVMModel
    from server.models.lstm_autoencoder import LSTMAutoencoderModel


class EnsembleModel:
    """Ensemble model combining multiple anomaly detection models."""

    MODEL_NAMES = ('isolation_forest', 'svm', 'lstm')

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or ENSEMBLE_WEIGHTS.copy()
        self.isolation_forest = IsolationForestModel()
        self.svm = SVMModel()
        self.lstm = LSTMAutoencoderModel()
        self.is_trained = False
        self.feature_names = list(FEATURE_COLUMNS)
        self.active_feature_names = list(FEATURE_COLUMNS)
        self.preprocessing: Dict[str, Any] = {}
        self.score_calibration: Dict[str, Dict[str, Any]] = {}
        self.training_metadata: Dict[str, Any] = {}

    def _iter_models(self) -> List[Tuple[str, Any]]:
        return [
            ('isolation_forest', self.isolation_forest),
            ('svm', self.svm),
            ('lstm', self.lstm),
        ]

    def _resolve_feature_names(self, n_features: int) -> List[str]:
        if self.feature_names and len(self.feature_names) == n_features:
            return list(self.feature_names)
        return [f'feature_{index}' for index in range(n_features)]

    def _fit_preprocessing(self, X: np.ndarray) -> np.ndarray:
        """Fit feature preprocessing metadata and return the filtered matrix."""
        X = np.asarray(X, dtype=float)
        if X.ndim != 2:
            raise ValueError("Expected a 2D feature matrix")

        n_samples, n_features = X.shape
        feature_names = self._resolve_feature_names(n_features)
        self.feature_names = feature_names

        finite_mask = np.isfinite(X)
        X_nan = np.where(finite_mask, X, np.nan)
        medians = np.nanmedian(X_nan, axis=0)
        medians = np.where(np.isfinite(medians), medians, 0.0)
        X_imputed = np.where(np.isfinite(X), X, medians)

        stds = np.std(X_imputed, axis=0)
        q25 = np.percentile(X_imputed, 25, axis=0)
        q75 = np.percentile(X_imputed, 75, axis=0)
        iqr = q75 - q25
        nonzero_counts = np.count_nonzero(np.abs(X_imputed) > FEATURE_VARIANCE_EPSILON, axis=0)

        min_nonzero_occurrences = min(
            n_samples,
            max(FEATURE_MIN_NONZERO_OCCURRENCES, int(np.ceil(n_samples * 0.1)))
        )

        active_mask = (
            stds > FEATURE_VARIANCE_EPSILON
        ) & (
            (iqr > FEATURE_VARIANCE_EPSILON) |
            (nonzero_counts >= min_nonzero_occurrences)
        )

        if not np.any(active_mask):
            if np.any(stds > 0):
                active_mask[int(np.argmax(stds))] = True
            else:
                active_mask[0] = True

        active_indices = np.flatnonzero(active_mask)
        active_feature_names = [feature_names[index] for index in active_indices]
        dropped_features = [
            feature_names[index]
            for index in range(n_features)
            if index not in set(active_indices.tolist())
        ]

        X_active = X_imputed[:, active_indices]
        clip_quantile = (
            FEATURE_CLIP_QUANTILE_SMALL_SAMPLE
            if n_samples < 20
            else FEATURE_CLIP_QUANTILE_LARGE_SAMPLE
        )
        clip_lower = np.percentile(X_active, clip_quantile, axis=0)
        clip_upper = np.percentile(X_active, 100.0 - clip_quantile, axis=0)
        X_clipped = np.clip(X_active, clip_lower, clip_upper)

        self.active_feature_names = active_feature_names
        self.preprocessing = {
            'feature_names': feature_names,
            'active_indices': active_indices.tolist(),
            'active_feature_names': active_feature_names,
            'dropped_features': dropped_features,
            'medians': medians.tolist(),
            'clip_lower': clip_lower.tolist(),
            'clip_upper': clip_upper.tolist(),
            'stds': stds.tolist(),
            'iqr': iqr.tolist(),
            'nonzero_counts': nonzero_counts.tolist(),
            'min_nonzero_occurrences': min_nonzero_occurrences,
            'clip_quantile': clip_quantile,
        }

        return X_clipped

    def _prepare_for_inference(self, X: np.ndarray) -> np.ndarray:
        """Apply stored preprocessing to inference-time features."""
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if X.ndim != 2:
            raise ValueError("Expected a 2D feature matrix")

        preprocessing = self.preprocessing or {}
        medians = np.asarray(preprocessing.get('medians', []), dtype=float)
        if medians.size == 0:
            return X

        if X.shape[1] != medians.size:
            raise ValueError(
                f"Feature width mismatch: expected {medians.size}, received {X.shape[1]}"
            )

        X_imputed = np.where(np.isfinite(X), X, medians)
        active_indices = np.asarray(
            preprocessing.get('active_indices', list(range(X.shape[1]))),
            dtype=int
        )
        if active_indices.size == 0:
            active_indices = np.arange(X.shape[1], dtype=int)

        X_active = X_imputed[:, active_indices]
        clip_lower = np.asarray(preprocessing.get('clip_lower', []), dtype=float)
        clip_upper = np.asarray(preprocessing.get('clip_upper', []), dtype=float)

        if clip_lower.size == X_active.shape[1] and clip_upper.size == X_active.shape[1]:
            X_active = np.clip(X_active, clip_lower, clip_upper)

        return X_active

    def _normalize_scores(self, model_name: str, raw_scores: np.ndarray) -> np.ndarray:
        """Map raw model scores onto a shared [-1, 1] scale using the empirical CDF."""
        raw_scores = np.asarray(raw_scores, dtype=float)
        calibration = self.score_calibration.get(model_name)
        if not calibration:
            return raw_scores

        sorted_scores = np.asarray(calibration.get('sorted_scores', []), dtype=float)
        if sorted_scores.size == 0:
            return raw_scores

        positions = np.searchsorted(sorted_scores, raw_scores, side='right')
        percentiles = (positions + 0.5) / (sorted_scores.size + 1.0)
        percentiles = np.clip(percentiles, 0.01, 0.99)
        return (2.0 * percentiles) - 1.0

    def _fit_score_calibration(self, model_name: str, raw_scores: np.ndarray) -> Dict[str, Any]:
        raw_scores = np.asarray(raw_scores, dtype=float)
        sorted_scores = np.sort(raw_scores)
        self.score_calibration[model_name] = {
            'method': 'empirical_cdf',
            'sorted_scores': sorted_scores.tolist(),
            'n_samples': int(sorted_scores.size)
        }

        normalized_scores = self._normalize_scores(model_name, raw_scores)
        return {
            'method': 'empirical_cdf',
            'n_scores': int(sorted_scores.size),
            'raw_min': float(np.min(raw_scores)),
            'raw_max': float(np.max(raw_scores)),
            'normalized_mean': float(np.mean(normalized_scores)),
            'normalized_std': float(np.std(normalized_scores)),
            'normalized_min': float(np.min(normalized_scores)),
            'normalized_max': float(np.max(normalized_scores))
        }

    def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """Train all models in the ensemble."""
        X_prepared = self._fit_preprocessing(X)
        metrics: Dict[str, Any] = {}
        self.score_calibration = {}

        for model_name, model in self._iter_models():
            try:
                model.feature_names = list(self.active_feature_names)
                model_metrics = model.train(X_prepared, y)
                raw_scores = model.predict(X_prepared)
                calibration = self._fit_score_calibration(model_name, raw_scores)
                model_metrics['calibration'] = calibration
                model_metrics['trained'] = True
                metrics[model_name] = model_metrics
            except Exception as exc:
                metrics[model_name] = {'trained': False, 'error': str(exc)}

        self.is_trained = any(
            metrics.get(model_name, {}).get('trained', False)
            for model_name in self.MODEL_NAMES
        )

        self.training_metadata = {
            'n_samples': int(X_prepared.shape[0]),
            'requested_feature_count': int(len(self.feature_names)),
            'active_feature_count': int(len(self.active_feature_names)),
            'requested_features': list(self.feature_names),
            'active_features': list(self.active_feature_names),
            'dropped_features': list(self.preprocessing.get('dropped_features', [])),
            'trained_models': [
                model_name
                for model_name in self.MODEL_NAMES
                if metrics.get(model_name, {}).get('trained', False)
            ]
        }

        metrics['ensemble'] = {
            'models_trained': len(self.training_metadata['trained_models']),
            'weights': self.weights,
            'requested_feature_count': self.training_metadata['requested_feature_count'],
            'active_feature_count': self.training_metadata['active_feature_count'],
            'active_features': self.training_metadata['active_features'],
            'dropped_features': self.training_metadata['dropped_features'],
            'preprocessing': self.preprocessing
        }

        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict calibrated ensemble anomaly scores."""
        if not self.is_model_trained():
            raise ValueError("At least one model must be trained before prediction")

        X_prepared = self._prepare_for_inference(X)
        scores = np.zeros(X_prepared.shape[0], dtype=float)
        total_weight = 0.0

        for model_name, model in self._iter_models():
            if not model.is_model_trained():
                continue
            raw_scores = model.predict(X_prepared)
            normalized_scores = self._normalize_scores(model_name, raw_scores)
            weight = float(self.weights.get(model_name, 0.0))
            scores += normalized_scores * weight
            total_weight += weight

        if total_weight <= 0:
            raise ValueError("No trained ensemble components available for prediction")

        return scores / total_weight

    def predict_single(self, features: Dict[str, float]) -> float:
        """Predict ensemble anomaly score for a single feature vector."""
        X = np.array([[features.get(col, 0.0) for col in self.feature_names]], dtype=float)
        scores = self.predict(X)
        return float(scores[0])

    def predict_with_details(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Predict with calibrated and raw per-model details."""
        if not self.is_model_trained():
            raise ValueError("At least one model must be trained before prediction")

        X = np.array([[features.get(col, 0.0) for col in self.feature_names]], dtype=float)
        X_prepared = self._prepare_for_inference(X)

        result = {
            'ensemble_score': 0.0,
            'individual_scores': {},
            'raw_individual_scores': {},
            'model_weights': {},
            'active_features': list(self.active_feature_names),
            'dropped_features': list(self.preprocessing.get('dropped_features', [])),
        }

        total_weight = 0.0

        for model_name, model in self._iter_models():
            if model.is_model_trained():
                raw_scores = model.predict(X_prepared)
                normalized_scores = self._normalize_scores(model_name, raw_scores)
                weight = float(self.weights.get(model_name, 0.0))
                result['raw_individual_scores'][model_name] = float(raw_scores[0])
                result['individual_scores'][model_name] = float(normalized_scores[0])
                result['model_weights'][model_name] = weight
                result['ensemble_score'] += float(normalized_scores[0]) * weight
                total_weight += weight
            else:
                result['raw_individual_scores'][model_name] = None
                result['individual_scores'][model_name] = None
                result['model_weights'][model_name] = 0.0

        if total_weight <= 0:
            raise ValueError("No trained ensemble components available for prediction")

        result['ensemble_score'] /= total_weight
        return result

    def save(self, path: Optional[Path] = None) -> None:
        """Save ensemble model to disk."""
        save_path = path or ENSEMBLE_MODEL
        save_path.parent.mkdir(parents=True, exist_ok=True)

        if path:
            if_path = save_path.parent / "isolation_forest.joblib"
            svm_path = save_path.parent / "one_class_svm.joblib"
            lstm_path = save_path.parent / "lstm_autoencoder"
        else:
            if_path = None
            svm_path = None
            lstm_path = None

        self.isolation_forest.save(path=if_path)
        self.svm.save(path=svm_path)

        try:
            self.lstm.save(path=lstm_path)
        except Exception:
            pass

        ensemble_data = {
            'weights': self.weights,
            'is_trained': self.is_trained,
            'feature_names': self.feature_names,
            'active_feature_names': self.active_feature_names,
            'preprocessing': self.preprocessing,
            'score_calibration': self.score_calibration,
            'training_metadata': self.training_metadata,
        }

        joblib.dump(ensemble_data, save_path)

    def load(self, path: Optional[Path] = None) -> None:
        """Load ensemble model from disk."""
        load_path = path or ENSEMBLE_MODEL

        if not load_path.exists():
            raise FileNotFoundError(f"Model file not found: {load_path}")

        if path:
            if_path = load_path.parent / "isolation_forest.joblib"
            svm_path = load_path.parent / "one_class_svm.joblib"
            lstm_path = load_path.parent / "lstm_autoencoder"
        else:
            if_path = None
            svm_path = None
            lstm_path = None

        try:
            self.isolation_forest.load(path=if_path)
        except FileNotFoundError:
            pass

        try:
            self.svm.load(path=svm_path)
        except FileNotFoundError:
            pass

        try:
            self.lstm.load(path=lstm_path)
        except Exception:
            pass

        ensemble_data = joblib.load(load_path)
        self.weights = ensemble_data.get('weights', ENSEMBLE_WEIGHTS.copy())
        self.is_trained = ensemble_data.get('is_trained', False)
        self.feature_names = ensemble_data.get('feature_names', list(FEATURE_COLUMNS))
        self.active_feature_names = ensemble_data.get(
            'active_feature_names',
            list(self.feature_names)
        )
        self.preprocessing = ensemble_data.get('preprocessing', {})
        self.score_calibration = ensemble_data.get('score_calibration', {})
        self.training_metadata = ensemble_data.get('training_metadata', {})

        if not self.preprocessing:
            active_indices = list(range(len(self.feature_names)))
            self.preprocessing = {
                'feature_names': list(self.feature_names),
                'active_indices': active_indices,
                'active_feature_names': list(self.active_feature_names),
                'dropped_features': [],
                'medians': [0.0] * len(self.feature_names),
                'clip_lower': [],
                'clip_upper': [],
            }

    def is_model_trained(self) -> bool:
        """Check if ensemble is trained (at least one model)."""
        return (
            self.isolation_forest.is_model_trained() or
            self.svm.is_model_trained() or
            self.lstm.is_model_trained()
        )
