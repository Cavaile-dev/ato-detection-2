"""
Reconstruction-Based Anomaly Model
Keeps the historical LSTMAutoencoderModel interface for compatibility,
but uses tabular reconstruction because the training data is session-level
aggregates rather than true within-session sequences.
"""

import shutil
from pathlib import Path
from typing import Dict, Any, Optional

import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler

from server.config import (
    FEATURE_COLUMNS,
    LSTM_MODEL,
    LSTM_SEQUENCE_LENGTH,
    LSTM_ENCODING_DIM,
)


class LSTMAutoencoderModel:
    """Reconstruction model for anomaly detection on tabular session features."""

    def __init__(self):
        self.model = None
        self.scaler = RobustScaler()
        self.is_trained = False
        self.feature_names = FEATURE_COLUMNS
        self.sequence_length = LSTM_SEQUENCE_LENGTH
        self.encoding_dim = LSTM_ENCODING_DIM
        self.n_components = None
        self.model_kind = 'pca_reconstruction'

    def _determine_n_components(self, X: np.ndarray) -> int:
        """Choose a compressed latent width without destroying small datasets."""
        n_samples, n_features = X.shape

        if n_samples < 3:
            raise ValueError("Need at least 3 samples to train reconstruction model")

        if n_features < 2:
            raise ValueError("Need at least 2 active features to train reconstruction model")

        max_components = min(n_samples - 1, n_features)
        compressed_width = max(1, int(np.ceil(n_features / 2.0)))
        target_components = min(max_components, self.encoding_dim, compressed_width)

        if n_features > 1:
            target_components = min(target_components, n_features - 1)

        return max(1, int(target_components))

    def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Train the reconstruction model.

        Returns negative reconstruction error at inference so it aligns with
        the rest of the anomaly stack: lower score means more anomalous.
        """
        X = np.asarray(X, dtype=float)

        if X.ndim != 2:
            raise ValueError("Expected a 2D feature matrix")

        self.n_components = self._determine_n_components(X)
        X_scaled = self.scaler.fit_transform(X)

        self.model = PCA(n_components=self.n_components, svd_solver='auto')
        latent = self.model.fit_transform(X_scaled)
        reconstructed = self.model.inverse_transform(latent)
        mse = np.mean(np.square(X_scaled - reconstructed), axis=1)

        self.is_trained = True

        explained_variance = float(np.sum(self.model.explained_variance_ratio_))

        return {
            'mean_mse': float(np.mean(mse)),
            'std_mse': float(np.std(mse)),
            'min_mse': float(np.min(mse)),
            'max_mse': float(np.max(mse)),
            'explained_variance_ratio': explained_variance,
            'n_samples': int(X.shape[0]),
            'n_features': int(X.shape[1]),
            'n_components': int(self.n_components),
            'model_kind': self.model_kind
        }

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict anomaly scores based on negative reconstruction error."""
        if not self.is_trained or self.model is None:
            raise ValueError("Model must be trained before prediction")

        X = np.asarray(X, dtype=float)
        if X.ndim != 2:
            raise ValueError("Expected a 2D feature matrix")

        X_scaled = self.scaler.transform(X)
        latent = self.model.transform(X_scaled)
        reconstructed = self.model.inverse_transform(latent)
        mse = np.mean(np.square(X_scaled - reconstructed), axis=1)

        return -mse

    def predict_single(self, features: Dict[str, float]) -> float:
        """Predict anomaly score for a single feature vector."""
        X = np.array([[features.get(col, 0.0) for col in self.feature_names]], dtype=float)
        scores = self.predict(X)
        return float(scores[0])

    def save(self, path: Optional[Path] = None) -> None:
        """Save model and metadata to disk."""
        save_path = path or LSTM_MODEL
        save_path.parent.mkdir(parents=True, exist_ok=True)

        if save_path.exists() and save_path.is_dir():
            shutil.rmtree(save_path, ignore_errors=True)

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'is_trained': self.is_trained,
            'feature_names': self.feature_names,
            'sequence_length': self.sequence_length,
            'encoding_dim': self.encoding_dim,
            'n_components': self.n_components,
            'model_kind': self.model_kind
        }

        joblib.dump(model_data, save_path)

    def load(self, path: Optional[Path] = None) -> None:
        """Load model and metadata from disk."""
        load_path = path or LSTM_MODEL

        if not load_path.exists():
            raise FileNotFoundError(f"Model file not found: {load_path}")

        if load_path.is_dir():
            raise RuntimeError("Legacy directory-based LSTM model format is not supported")

        model_data = joblib.load(load_path)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.is_trained = model_data['is_trained']
        self.feature_names = model_data.get('feature_names', FEATURE_COLUMNS)
        self.sequence_length = model_data.get('sequence_length', LSTM_SEQUENCE_LENGTH)
        self.encoding_dim = model_data.get('encoding_dim', LSTM_ENCODING_DIM)
        self.n_components = model_data.get('n_components')
        self.model_kind = model_data.get('model_kind', 'pca_reconstruction')

    def is_model_trained(self) -> bool:
        """Check if model is trained."""
        return self.is_trained
