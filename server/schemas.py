"""
Pydantic schemas for data validation and serialization
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# Enums
class EventType(str, Enum):
    MOUSE_MOVE = "MOUSE_MOVE"
    MOUSE_CLICK = "MOUSE_CLICK"
    MOUSE_SCROLL = "MOUSE_SCROLL"
    KEYSTROKE = "KEYSTROKE"
    NAVIGATION = "NAVIGATION"
    COPY = "COPY"
    PASTE = "PASTE"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class RiskAction(str, Enum):
    ALLOW_SESSION = "ALLOW_SESSION"
    REQUIRE_MFA = "REQUIRE_MFA"
    BLOCK_SESSION = "BLOCK_SESSION"

# Request Schemas
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class SessionStartRequest(BaseModel):
    user_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_fingerprint: Optional[str] = None

class BehaviorEvent(BaseModel):
    event_type: EventType
    timestamp: float = Field(..., description="Unix timestamp in milliseconds")
    x: Optional[float] = Field(None, description="X coordinate for mouse events")
    y: Optional[float] = Field(None, description="Y coordinate for mouse events")
    velocity: Optional[float] = Field(None, description="Velocity for mouse events")
    acceleration: Optional[float] = Field(None, description="Acceleration for mouse events")
    key: Optional[str] = Field(None, description="Key pressed for keystroke events")
    key_code: Optional[int] = Field(None, description="Key code for keystroke events")
    key_interval: Optional[float] = Field(None, description="Time since last keypress (ms)")
    hold_time: Optional[float] = Field(None, description="Key hold duration (ms)")
    scroll_delta: Optional[float] = Field(None, description="Scroll delta for scroll events")
    scroll_velocity: Optional[float] = Field(None, description="Scroll velocity")
    button: Optional[int] = Field(None, description="Mouse button for click events")
    page_url: Optional[str] = Field(None, description="Current page URL")
    page_title: Optional[str] = Field(None, description="Current page title")
    referrer: Optional[str] = Field(None, description="Referrer URL")

    @validator('timestamp')
    def validate_timestamp(cls, v):
        if v <= 0:
            raise ValueError('Timestamp must be positive')
        return v

class EventsSubmitRequest(BaseModel):
    session_id: str
    events: List[BehaviorEvent]

class TrainModelRequest(BaseModel):
    user_id: Optional[int] = Field(None, description="Train for specific user, or all if None")
    min_samples: int = Field(10, ge=1, description="Minimum samples required for training")

# Response Schemas
class UserResponse(BaseModel):
    id: int
    username: str
    baseline_count: int
    baseline_completed: bool
    created_at: datetime

    class Config:
        from_attributes = True

class SessionResponse(BaseModel):
    session_id: str
    user_id: int
    start_time: datetime
    ip_address: Optional[str]
    device_fingerprint: Optional[str]
    is_baseline: bool
    event_count: int

    class Config:
        from_attributes = True

class RiskAssessmentResponse(BaseModel):
    session_id: str
    anomaly_score: float
    risk_level: RiskLevel
    action: RiskAction
    reasons: List[str]
    individual_scores: Optional[Dict[str, float]] = Field(None, description="Scores from individual models")
    feature_contributions: Optional[Dict[str, float]] = Field(None, description="Feature contribution to anomaly score")
    timestamp: datetime

class FeatureVector(BaseModel):
    """Feature vector with all 30+ features"""
    # Mouse features (12)
    mouse_velocity_mean: float = 0.0
    mouse_velocity_std: float = 0.0
    mouse_velocity_max: float = 0.0
    mouse_acceleration_mean: float = 0.0
    mouse_acceleration_std: float = 0.0
    mouse_acceleration_max: float = 0.0
    mouse_jerk_mean: float = 0.0
    mouse_jerk_std: float = 0.0
    mouse_curvature_mean: float = 0.0
    mouse_direction_changes: float = 0.0
    mouse_pause_count: float = 0.0
    mouse_click_interval_mean: float = 0.0

    # Keystroke features (10)
    keystroke_dwell_time_mean: float = 0.0
    keystroke_dwell_time_std: float = 0.0
    keystroke_flight_time_mean: float = 0.0
    keystroke_flight_time_std: float = 0.0
    keystroke_typing_consistency: float = 0.0
    keystroke_error_rate: float = 0.0
    keystroke_transition_entropy: float = 0.0
    keystroke_backspace_rate: float = 0.0
    keystroke_correction_rate: float = 0.0
    keystroke_typing_speed: float = 0.0

    # Temporal features (4)
    temporal_time_of_day_score: float = 0.0
    temporal_session_duration: float = 0.0
    temporal_activity_bursts: float = 0.0
    temporal_idle_time_ratio: float = 0.0

    # Navigation features (4)
    nav_page_transition_pattern: float = 0.0
    nav_time_per_page_mean: float = 0.0
    nav_scroll_depth_mean: float = 0.0
    nav_scroll_velocity_mean: float = 0.0

    # Cross-modal features (2)
    cross_mouse_keyboard_coordination: float = 0.0
    cross_copy_paste_frequency: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return self.model_dump()

    def to_list(self) -> List[float]:
        """Convert to list in FEATURE_COLUMNS order"""
        from server.config import FEATURE_COLUMNS
        return [self.model_dump()[col] for col in FEATURE_COLUMNS]

class DashboardStatsResponse(BaseModel):
    total_users: int
    total_sessions: int
    total_events: int
    active_sessions: int
    high_risk_sessions_today: int
    medium_risk_sessions_today: int
    low_risk_sessions_today: int
    average_risk_score: float
    model_trained: bool
    top_users: List[Dict[str, Any]]

class SessionReplayResponse(BaseModel):
    session_id: str
    user_id: int
    start_time: datetime
    end_time: Optional[datetime]
    events: List[BehaviorEvent]
    anomaly_score: float
    risk_level: RiskLevel
    features: FeatureVector

class ModelTrainingResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[int]
    samples_used: int
    model_version: str
    individual_models: Dict[str, bool]

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
