"""
Configuration module for Real-Time Login Anomaly Detection System
Contains all constants, paths, and configuration parameters
"""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
SERVER_DIR = BASE_DIR / "server"
MODEL_DIR = BASE_DIR / "model"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
WEB_DIR = BASE_DIR / "web"

# Database configuration
DB_NAME = "behavior_detection.db"
DB_PATH = DATA_DIR / DB_NAME

# Data files
REAL_FEATURES_PATH = DATA_DIR / "real_features.csv"
SESSION_DATA_PATH = DATA_DIR / "session_data.json"

# Model files
ISOLATION_FOREST_MODEL = MODEL_DIR / "isolation_forest.joblib"
SVM_MODEL = MODEL_DIR / "one_class_svm.joblib"
LSTM_MODEL = MODEL_DIR / "lstm_autoencoder"
ENSEMBLE_MODEL = MODEL_DIR / "ensemble_model.joblib"
SCALER_MODEL = MODEL_DIR / "scaler.joblib"

# Feature columns (30+ features)
FEATURE_COLUMNS = [
    # Mouse features (12)
    'mouse_velocity_mean',
    'mouse_velocity_std',
    'mouse_velocity_max',
    'mouse_acceleration_mean',
    'mouse_acceleration_std',
    'mouse_acceleration_max',
    'mouse_jerk_mean',
    'mouse_jerk_std',
    'mouse_curvature_mean',
    'mouse_direction_changes',
    'mouse_pause_count',
    'mouse_click_interval_mean',

    # Keystroke features (10)
    'keystroke_dwell_time_mean',
    'keystroke_dwell_time_std',
    'keystroke_flight_time_mean',
    'keystroke_flight_time_std',
    'keystroke_typing_consistency',
    'keystroke_error_rate',
    'keystroke_transition_entropy',
    'keystroke_backspace_rate',
    'keystroke_correction_rate',
    'keystroke_typing_speed',

    # Temporal features (4)
    'temporal_time_of_day_score',
    'temporal_session_duration',
    'temporal_activity_bursts',
    'temporal_idle_time_ratio',

    # Navigation features (4)
    'nav_page_transition_pattern',
    'nav_time_per_page_mean',
    'nav_scroll_depth_mean',
    'nav_scroll_velocity_mean',

    # Cross-modal features (2)
    'cross_mouse_keyboard_coordination',
    'cross_copy_paste_frequency'
]

# Feature categories for easier access
MOUSE_FEATURES = [col for col in FEATURE_COLUMNS if col.startswith('mouse_')]
KEYSTROKE_FEATURES = [col for col in FEATURE_COLUMNS if col.startswith('keystroke_')]
TEMPORAL_FEATURES = [col for col in FEATURE_COLUMNS if col.startswith('temporal_')]
NAVIGATION_FEATURES = [col for col in FEATURE_COLUMNS if col.startswith('nav_')]
CROSS_MODAL_FEATURES = [col for col in FEATURE_COLUMNS if col.startswith('cross_')]

# Model configuration
ISOLATION_FOREST_CONTAMINATION = 0.1
ISOLATION_FOREST_N_ESTIMATORS = 100
ISOLATION_FOREST_MAX_SAMPLES = 256

SVM_NU = 0.1
SVM_KERNEL = 'rbf'
SVM_GAMMA = 'scale'

LSTM_SEQUENCE_LENGTH = 50
LSTM_ENCODING_DIM = 32
LSTM_EPOCHS = 50
LSTM_BATCH_SIZE = 32

ENSEMBLE_WEIGHTS = {
    'isolation_forest': 0.4,
    'svm': 0.3,
    'lstm': 0.3
}

# Pipeline configuration
ROLLING_WINDOW_SIZE = 90  # Number of events to keep in rolling window
MIN_EVENTS_FOR_ASSESSMENT = 30  # Minimum events before making assessment
ASSESSMENT_INTERVAL = 10  # Assess every N events

# Session configuration
MIN_TRAINING_SAMPLES = 3
SESSION_TIMEOUT_MINUTES = 30

# Timezone configuration
APP_TIMEZONE = "Asia/Jakarta"
APP_TIMEZONE_LABEL = "WIB"

# Training data quality configuration
TRAINING_MIN_SESSION_DURATION_SECONDS = 1.0
TRAINING_MIN_NONZERO_FEATURES = 4
TRAINING_MIN_NONZERO_FEATURE_RATIO = 0.15
TRAINING_MAX_EVENT_RATE = 200.0
TRAINING_OUTLIER_PRUNING_MIN_SAMPLES = 12
TRAINING_OUTLIER_MAD_MULTIPLIER = 4.0

# Feature preprocessing configuration
FEATURE_VARIANCE_EPSILON = 1e-6
FEATURE_MIN_NONZERO_OCCURRENCES = 2
FEATURE_CLIP_QUANTILE_SMALL_SAMPLE = 5.0
FEATURE_CLIP_QUANTILE_LARGE_SAMPLE = 2.5

# Hybrid inference configuration
HYBRID_PERSONAL_MIN_WEIGHT = 0.25
HYBRID_PERSONAL_MAX_WEIGHT = 0.75
HYBRID_PERSONAL_FULL_WEIGHT_SAMPLES = 12

# Risk scoring thresholds
RISK_THRESHOLD_LOW = 0.0
RISK_THRESHOLD_MEDIUM = 0.5

# Risk levels
RISK_LEVEL_LOW = "LOW"
RISK_LEVEL_MEDIUM = "MEDIUM"
RISK_LEVEL_HIGH = "HIGH"

# Risk actions
RISK_ACTION_ALLOW = "ALLOW_SESSION"
RISK_ACTION_REQUIRE_MFA = "REQUIRE_MFA"
RISK_ACTION_BLOCK = "BLOCK_SESSION"

# Event types
EVENT_TYPE_MOUSE_MOVE = "MOUSE_MOVE"
EVENT_TYPE_MOUSE_CLICK = "MOUSE_CLICK"
EVENT_TYPE_MOUSE_SCROLL = "MOUSE_SCROLL"
EVENT_TYPE_KEYSTROKE = "KEYSTROKE"
EVENT_TYPE_NAVIGATION = "NAVIGATION"
EVENT_TYPE_COPY = "COPY"
EVENT_TYPE_PASTE = "PASTE"

# Flask configuration
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = True
SESSION_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "lato-lato-dev-secret-change-me")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("FLASK_SESSION_COOKIE_SECURE", "0") == "1"

# CORS configuration
CORS_ORIGINS = ["http://127.0.0.1:5000", "http://localhost:5000"]

# Logging configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = LOGS_DIR / "app.log"

# Security configuration
PASSWORD_HASH_METHOD = "pbkdf2:sha256"
PASSWORD_HASH_SALT_LENGTH = 16

# Device fingerprinting
DEVICE_FINGERPRINT_ENABLED = True

# Create necessary directories
def ensure_directories():
    """Create all necessary directories if they don't exist"""
    directories = [MODEL_DIR, DATA_DIR, LOGS_DIR]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

# Initialize directories
ensure_directories()
