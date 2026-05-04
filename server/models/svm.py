"""
One-Class SVM Model
Unsupervised anomaly detection using Support Vector Machine
"""

import numpy as np
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import RobustScaler
import joblib
from pathlib import Path
from typing import Dict, Any, Optional

from server.config import (
    FEATURE_COLUMNS,
    SVM_MODEL,
    SVM_NU,
    SVM_KERNEL,
    SVM_GAMMA
)


class SVMModel:
    """One-Class SVM model for anomaly detection"""

    def __init__(self):
        self.model = None
        self.scaler = RobustScaler()
        self.is_trained = False
        self.feature_names = FEATURE_COLUMNS

    def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Train the One-Class SVM model

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Labels (optional, for information only - OneClassSVM is unsupervised)

        Returns:
            Training metrics
        """
        if len(X) < 2:
            raise ValueError("Need at least 2 samples to train OneClassSVM")

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train model
        self.model = OneClassSVM(
            nu=SVM_NU,
            kernel=SVM_KERNEL,
            gamma=SVM_GAMMA,
            verbose=False
        )

        self.model.fit(X_scaled)
        self.is_trained = True

        # Calculate metrics
        scores = self.model.score_samples(X_scaled)
        metrics = {
            'mean_score': float(np.mean(scores)),
            'std_score': float(np.std(scores)),
            'min_score': float(np.min(scores)),
            'max_score': float(np.max(scores)),
            'n_samples': len(X),
            'n_features': X.shape[1]
        }

        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict anomaly scores

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Anomaly scores (negative values indicate anomalies)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        X_scaled = self.scaler.transform(X)
        scores = self.model.score_samples(X_scaled)
        return scores

    def predict_single(self, features: Dict[str, float]) -> float:
        """
        Predict anomaly score for a single feature vector

        Args:
            features: Dictionary of feature names to values

        Returns:
            Anomaly score
        """
        # Convert dict to array
        X = np.array([[features.get(col, 0.0) for col in self.feature_names]])
        scores = self.predict(X)
        return float(scores[0])

    def save(self, path: Optional[Path] = None) -> None:
        """Save model and scaler to disk"""
        save_path = path or SVM_MODEL
        save_path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'is_trained': self.is_trained,
            'feature_names': self.feature_names
        }

        joblib.dump(model_data, save_path)

    def load(self, path: Optional[Path] = None) -> None:
        """Load model and scaler from disk"""
        load_path = path or SVM_MODEL

        if not load_path.exists():
            raise FileNotFoundError(f"Model file not found: {load_path}")

        model_data = joblib.load(load_path)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.is_trained = model_data['is_trained']
        self.feature_names = model_data.get('feature_names', FEATURE_COLUMNS)

    def is_model_trained(self) -> bool:
        """Check if model is trained"""
        return self.is_trained
