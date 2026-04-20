"""
LSTM Autoencoder Model
Deep learning model for temporal anomaly detection
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import json
from pathlib import Path

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False

from server.config import (
    FEATURE_COLUMNS,
    LSTM_MODEL,
    LSTM_SEQUENCE_LENGTH,
    LSTM_ENCODING_DIM,
    LSTM_EPOCHS,
    LSTM_BATCH_SIZE
)


class LSTMAutoencoderModel:
    """LSTM Autoencoder model for anomaly detection"""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.is_trained = False
        self.feature_names = FEATURE_COLUMNS
        self.sequence_length = LSTM_SEQUENCE_LENGTH
        self.encoding_dim = LSTM_ENCODING_DIM

        if not TENSORFLOW_AVAILABLE:
            print("Warning: TensorFlow not available. LSTM model will not work.")

    def _build_model(self, n_features: int) -> keras.Model:
        """Build LSTM Autoencoder architecture"""
        # Input layer
        input_layer = layers.Input(shape=(self.sequence_length, n_features))

        # Encoder
        encoded = layers.LSTM(64, return_sequences=True)(input_layer)
        encoded = layers.LSTM(32, return_sequences=False)(encoded)
        encoded = layers.RepeatVector(self.sequence_length)(encoded)

        # Decoder
        decoded = layers.LSTM(32, return_sequences=True)(encoded)
        decoded = layers.LSTM(64, return_sequences=True)(decoded)
        decoded = layers.TimeDistributed(layers.Dense(n_features))(decoded)

        # Create model
        model = keras.Model(inputs=input_layer, outputs=decoded)
        model.compile(optimizer='adam', loss='mse')

        return model

    def _create_sequences(self, X: np.ndarray) -> np.ndarray:
        """
        Create sequences for LSTM training
        Converts (n_samples, n_features) to (n_sequences, sequence_length, n_features)
        """
        sequences = []

        for i in range(len(X) - self.sequence_length + 1):
            sequences.append(X[i:i + self.sequence_length])

        return np.array(sequences)

    def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Train the LSTM Autoencoder model

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Labels (optional, not used for unsupervised training)

        Returns:
            Training metrics
        """
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required for LSTM model")

        if len(X) < self.sequence_length:
            raise ValueError(f"Need at least {self.sequence_length} samples to train LSTM")

        # Import StandardScaler here
        from sklearn.preprocessing import StandardScaler

        if self.scaler is None:
            self.scaler = StandardScaler()

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Create sequences
        X_sequences = self._create_sequences(X_scaled)

        # Build model
        n_features = X.shape[1]
        self.model = self._build_model(n_features)

        # Train model
        history = self.model.fit(
            X_sequences,
            X_sequences,
            epochs=LSTM_EPOCHS,
            batch_size=LSTM_BATCH_SIZE,
            verbose=0,
            validation_split=0.1
        )

        self.is_trained = True

        # Calculate reconstruction error as metric
        reconstructions = self.model.predict(X_sequences, verbose=0)
        mse = np.mean(np.power(X_sequences - reconstructions, 2), axis=(1, 2))

        metrics = {
            'mean_mse': float(np.mean(mse)),
            'std_mse': float(np.std(mse)),
            'min_mse': float(np.min(mse)),
            'max_mse': float(np.max(mse)),
            'final_loss': float(history.history['loss'][-1]),
            'n_samples': len(X),
            'n_features': X.shape[1],
            'n_sequences': len(X_sequences)
        }

        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict anomaly scores based on reconstruction error

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Anomaly scores (higher values indicate more anomalous)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required for LSTM model")

        X_scaled = self.scaler.transform(X)

        # Create sequences
        X_sequences = self._create_sequences(X_scaled)

        # Predict reconstructions
        reconstructions = self.model.predict(X_sequences, verbose=0)

        # Calculate reconstruction error
        mse = np.mean(np.power(X_sequences - reconstructions, 2), axis=(1, 2))

        # Pad scores to match original length
        scores = np.zeros(len(X))
        scores[self.sequence_length - 1:] = mse

        # Fill first values with mean
        scores[:self.sequence_length - 1] = np.mean(mse)

        # Negate to match other models (negative = anomalous)
        scores = -scores

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
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required for LSTM model")

        save_path = path or LSTM_MODEL
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Save model
        self.model.save(str(save_path))

        # Save scaler separately
        import joblib
        scaler_path = save_path.parent / f"{save_path.name}_scaler.joblib"
        joblib.dump(self.scaler, scaler_path)

        # Save metadata
        metadata = {
            'is_trained': self.is_trained,
            'feature_names': self.feature_names,
            'sequence_length': self.sequence_length,
            'encoding_dim': self.encoding_dim
        }

        metadata_path = save_path.parent / f"{save_path.name}_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)

    def load(self, path: Optional[Path] = None) -> None:
        """Load model and scaler from disk"""
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow is required for LSTM model")

        load_path = path or LSTM_MODEL

        if not load_path.exists():
            raise FileNotFoundError(f"Model file not found: {load_path}")

        # Load model
        self.model = keras.models.load_model(str(load_path))

        # Load scaler
        import joblib
        scaler_path = load_path.parent / f"{load_path.name}_scaler.joblib"
        if scaler_path.exists():
            self.scaler = joblib.load(scaler_path)

        # Load metadata
        metadata_path = load_path.parent / f"{load_path.name}_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            self.is_trained = metadata.get('is_trained', False)
            self.feature_names = metadata.get('feature_names', FEATURE_COLUMNS)
            self.sequence_length = metadata.get('sequence_length', LSTM_SEQUENCE_LENGTH)
            self.encoding_dim = metadata.get('encoding_dim', LSTM_ENCODING_DIM)

    def is_model_trained(self) -> bool:
        """Check if model is trained"""
        return self.is_trained
