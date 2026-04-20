"""
Ensemble Model
Combines multiple models for robust anomaly detection
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import joblib
from pathlib import Path

from server.config import (
    FEATURE_COLUMNS,
    ENSEMBLE_MODEL,
    ENSEMBLE_WEIGHTS
)

try:
    from .isolation_forest import IsolationForestModel
    from .svm import SVMModel
    from .lstm_autoencoder import LSTMAutoencoderModel
except ImportError:
    # Handle when running as script
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from server.models.isolation_forest import IsolationForestModel
    from server.models.svm import SVMModel
    from server.models.lstm_autoencoder import LSTMAutoencoderModel


class EnsembleModel:
    """Ensemble model combining multiple anomaly detection models"""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize ensemble model

        Args:
            weights: Dictionary mapping model names to weights
                    Default: {'isolation_forest': 0.4, 'svm': 0.3, 'lstm': 0.3}
        """
        self.weights = weights or ENSEMBLE_WEIGHTS.copy()

        # Initialize individual models
        self.isolation_forest = IsolationForestModel()
        self.svm = SVMModel()
        self.lstm = LSTMAutoencoderModel()

        self.is_trained = False
        self.feature_names = FEATURE_COLUMNS

    def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Train all models in the ensemble

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Labels (optional)

        Returns:
            Training metrics for all models
        """
        metrics = {}

        # Train Isolation Forest
        try:
            if_metrics = self.isolation_forest.train(X, y)
            metrics['isolation_forest'] = if_metrics
            metrics['isolation_forest']['trained'] = True
        except Exception as e:
            metrics['isolation_forest'] = {'trained': False, 'error': str(e)}

        # Train SVM
        try:
            svm_metrics = self.svm.train(X, y)
            metrics['svm'] = svm_metrics
            metrics['svm']['trained'] = True
        except Exception as e:
            metrics['svm'] = {'trained': False, 'error': str(e)}

        # Train LSTM (may fail if not enough data or TensorFlow not available)
        try:
            lstm_metrics = self.lstm.train(X, y)
            metrics['lstm'] = lstm_metrics
            metrics['lstm']['trained'] = True
        except Exception as e:
            metrics['lstm'] = {'trained': False, 'error': str(e)}

        # Check if at least one model is trained
        any_trained = any(
            metrics.get(model, {}).get('trained', False)
            for model in ['isolation_forest', 'svm', 'lstm']
        )

        self.is_trained = any_trained

        # Add ensemble info
        metrics['ensemble'] = {
            'models_trained': sum(
                1 for model in ['isolation_forest', 'svm', 'lstm']
                if metrics.get(model, {}).get('trained', False)
            ),
            'weights': self.weights
        }

        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict ensemble anomaly scores

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Ensemble anomaly scores
        """
        if not self.is_trained:
            raise ValueError("At least one model must be trained before prediction")

        scores = np.zeros(len(X))
        total_weight = 0.0

        # Get predictions from each trained model
        if self.isolation_forest.is_model_trained():
            if_scores = self.isolation_forest.predict(X)
            weight = self.weights.get('isolation_forest', 0.0)
            scores += if_scores * weight
            total_weight += weight

        if self.svm.is_model_trained():
            svm_scores = self.svm.predict(X)
            weight = self.weights.get('svm', 0.0)
            scores += svm_scores * weight
            total_weight += weight

        if self.lstm.is_model_trained():
            lstm_scores = self.lstm.predict(X)
            weight = self.weights.get('lstm', 0.0)
            scores += lstm_scores * weight
            total_weight += weight

        # Normalize by total weight
        if total_weight > 0:
            scores /= total_weight

        return scores

    def predict_single(self, features: Dict[str, float]) -> float:
        """
        Predict ensemble anomaly score for a single feature vector

        Args:
            features: Dictionary of feature names to values

        Returns:
            Ensemble anomaly score
        """
        # Convert dict to array
        X = np.array([[features.get(col, 0.0) for col in self.feature_names]])
        scores = self.predict(X)
        return float(scores[0])

    def predict_with_details(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Predict with individual model scores

        Args:
            features: Dictionary of feature names to values

        Returns:
            Dictionary with ensemble score and individual model scores
        """
        # Convert dict to array
        X = np.array([[features.get(col, 0.0) for col in self.feature_names]])

        result = {
            'ensemble_score': 0.0,
            'individual_scores': {}
        }

        total_weight = 0.0

        # Get predictions from each trained model
        if self.isolation_forest.is_model_trained():
            if_scores = self.isolation_forest.predict(X)
            weight = self.weights.get('isolation_forest', 0.0)
            result['individual_scores']['isolation_forest'] = float(if_scores[0])
            result['ensemble_score'] += if_scores[0] * weight
            total_weight += weight
        else:
            result['individual_scores']['isolation_forest'] = None

        if self.svm.is_model_trained():
            svm_scores = self.svm.predict(X)
            weight = self.weights.get('svm', 0.0)
            result['individual_scores']['svm'] = float(svm_scores[0])
            result['ensemble_score'] += svm_scores[0] * weight
            total_weight += weight
        else:
            result['individual_scores']['svm'] = None

        if self.lstm.is_model_trained():
            lstm_scores = self.lstm.predict(X)
            weight = self.weights.get('lstm', 0.0)
            result['individual_scores']['lstm'] = float(lstm_scores[0])
            result['ensemble_score'] += lstm_scores[0] * weight
            total_weight += weight
        else:
            result['individual_scores']['lstm'] = None

        # Normalize by total weight
        if total_weight > 0:
            result['ensemble_score'] /= total_weight

        return result

    def save(self, path: Optional[Path] = None) -> None:
        """Save ensemble model to disk"""
        save_path = path or ENSEMBLE_MODEL
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Save individual models
        self.isolation_forest.save()
        self.svm.save()

        try:
            self.lstm.save()
        except:
            pass  # LSTM may not be trained

        # Save ensemble metadata
        ensemble_data = {
            'weights': self.weights,
            'is_trained': self.is_trained,
            'feature_names': self.feature_names
        }

        joblib.dump(ensemble_data, save_path)

    def load(self, path: Optional[Path] = None) -> None:
        """Load ensemble model from disk"""
        load_path = path or ENSEMBLE_MODEL

        if not load_path.exists():
            raise FileNotFoundError(f"Model file not found: {load_path}")

        # Load individual models
        try:
            self.isolation_forest.load()
        except FileNotFoundError:
            pass  # Model may not exist

        try:
            self.svm.load()
        except FileNotFoundError:
            pass  # Model may not exist

        try:
            self.lstm.load()
        except:
            pass  # LSTM may not be available or trained

        # Load ensemble metadata
        ensemble_data = joblib.load(load_path)
        self.weights = ensemble_data.get('weights', ENSEMBLE_WEIGHTS)
        self.is_trained = ensemble_data.get('is_trained', False)
        self.feature_names = ensemble_data.get('feature_names', FEATURE_COLUMNS)

    def is_model_trained(self) -> bool:
        """Check if ensemble is trained (at least one model)"""
        return (
            self.isolation_forest.is_model_trained() or
            self.svm.is_model_trained() or
            self.lstm.is_model_trained()
        )
