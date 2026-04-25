"""
Real-Time Processing Pipeline
Handles real-time event processing and risk assessment
"""

import threading
import uuid
from collections import deque
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging
import numpy as np

from server.config import (
    ROLLING_WINDOW_SIZE,
    MIN_EVENTS_FOR_ASSESSMENT,
    ASSESSMENT_INTERVAL,
    MIN_BASELINE_SESSIONS,
    ENABLE_PROGRESSIVE_BLEND,
    MIN_PERSONAL_PROFILE_SAMPLES,
    PERSONAL_BLEND_START_SAMPLES,
    PERSONAL_BLEND_FULL_SAMPLES
)
from server.database import db
from server.feature_extraction import FeatureExtractor
from server.models.ensemble import EnsembleModel
from server.personal_profile import PersonalProfileScorer
from server.risk_engine import RiskEngine

logger = logging.getLogger(__name__)


class SessionState:
    """Manages state for an active session"""

    def __init__(self, session_id: str, user_id: int, is_baseline: bool = True):
        self.session_id = session_id
        self.user_id = user_id
        self.is_baseline = is_baseline
        self.start_time = datetime.utcnow()
        self.event_buffer = deque(maxlen=ROLLING_WINDOW_SIZE)
        self.event_count = 0
        self.latest_assessment = None
        self.features = None
        self.lock = threading.Lock()

    def add_events(self, events: List[Dict[str, Any]]) -> int:
        """Add events to the session buffer"""
        with self.lock:
            for event in events:
                self.event_buffer.append(event)
                self.event_count += 1
            return len(events)

    def get_events(self) -> List[Dict[str, Any]]:
        """Get all events in the buffer"""
        with self.lock:
            return list(self.event_buffer)

    def should_assess(self) -> bool:
        """Check if we should perform a risk assessment"""
        with self.lock:
            return (
                self.event_count >= MIN_EVENTS_FOR_ASSESSMENT and
                self.event_count % ASSESSMENT_INTERVAL == 0
            )

    def get_event_count(self) -> int:
        """Get total event count"""
        with self.lock:
            return self.event_count


class ProcessingPipeline:
    """Real-time processing pipeline for behavioral events"""

    def __init__(self):
        self.active_sessions: Dict[str, SessionState] = {}
        self.feature_extractor = FeatureExtractor()
        self.ensemble_model = EnsembleModel()
        self.personal_scorer = PersonalProfileScorer()
        self.risk_engine = RiskEngine()
        self.lock = threading.Lock()
        self.is_running = False
        self.worker_thread = None

    def start_session(
        self,
        user_id: int,
        ip_address: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        Start a new session

        Returns:
            session_id
        """
        session_id = str(uuid.uuid4())

        # Check if user has completed baseline
        user = db.get_user_by_id(user_id)
        is_baseline = not (user and user.get('baseline_completed', False))

        # Create session state
        session_state = SessionState(session_id, user_id, is_baseline)
        session_state.ip_address = ip_address
        session_state.device_fingerprint = device_fingerprint
        session_state.user_agent = user_agent

        with self.lock:
            self.active_sessions[session_id] = session_state

        # Create session in database
        db.create_session(
            session_id=session_id,
            user_id=user_id,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            user_agent=user_agent,
            is_baseline=is_baseline
        )

        logger.info(f"Started session {session_id} for user {user_id} (baseline: {is_baseline})")

        return session_id

    def process_events(self, session_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process events for a session

        Returns:
            Processing result with assessment if available
        """
        session_state = self.get_session(session_id)
        if not session_state:
            raise ValueError(f"Session {session_id} not found")

        # Add events to buffer
        added_count = session_state.add_events(events)

        # Store events in database
        for event in events:
            db.insert_event(session_id, event)

        # Update session event count
        db.update_session_event_count(session_id, session_state.get_event_count())

        result = {
            'session_id': session_id,
            'events_processed': added_count,
            'total_events': session_state.get_event_count(),
            'is_baseline': session_state.is_baseline
        }

        # Perform assessment if needed
        if session_state.should_assess() and self._has_any_scoring_model(session_state.user_id):
            assessment = self._assess_session(session_state)
            if assessment:
                result['assessment'] = assessment

                # Update session in database
                db.update_session_risk_assessment(
                    session_id=session_id,
                    anomaly_score=assessment['anomaly_score'],
                    risk_level=assessment['risk_level'],
                    action=assessment['action']
                )

        return result

    def _assess_session(self, session_state: SessionState) -> Dict[str, Any]:
        """Perform risk assessment on a session"""
        events = session_state.get_events()

        if len(events) < MIN_EVENTS_FOR_ASSESSMENT:
            return None

        # Extract features
        features = self.feature_extractor.extract_features(events)
        session_state.features = features

        user_profile = db.get_user_profile(session_state.user_id)
        profile_samples = int((user_profile or {}).get('sample_count', 0) or 0)

        global_score = None
        global_details = {}
        if self.ensemble_model.is_model_trained():
            prediction = self.ensemble_model.predict_with_details(features)
            global_score = prediction['ensemble_score']
            global_details = prediction['individual_scores']

        personal_score = self.personal_scorer.score(features, user_profile)

        global_weight, personal_weight = self._get_blend_weights(profile_samples)

        # Fall back to available score source
        if global_score is None and personal_score is None:
            return None
        if global_score is None:
            blended_score = personal_score
            global_weight, personal_weight = 0.0, 1.0
        elif personal_score is None:
            blended_score = global_score
            global_weight, personal_weight = 1.0, 0.0
        else:
            blended_score = (global_score * global_weight) + (personal_score * personal_weight)

        # Assess risk
        assessment = self.risk_engine.assess_risk(
            anomaly_score=blended_score,
            individual_scores={
                **global_details,
                'global_ensemble': global_score,
                'personal_profile': personal_score
            },
            features=features,
            session_context={
                'user_id': session_state.user_id,
                'session_id': session_state.session_id,
                'is_baseline': session_state.is_baseline
            }
        )

        assessment['scoring'] = {
            'strategy': 'progressive_blend' if ENABLE_PROGRESSIVE_BLEND else 'global_only',
            'global_score': global_score,
            'personal_score': personal_score,
            'global_weight': float(global_weight),
            'personal_weight': float(personal_weight),
            'profile_samples': profile_samples,
            'min_personal_samples': MIN_PERSONAL_PROFILE_SAMPLES
        }
        if personal_weight == 0.0:
            assessment['reasons'].append("Cold start mode: decision relies on global behavior model")
        elif global_weight == 0.0:
            assessment['reasons'].append("Personalized mode: decision relies on personal behavior profile")
        else:
            assessment['reasons'].append(
                f"Progressive blend active: global {global_weight:.2f}, personal {personal_weight:.2f}"
            )

        session_state.latest_assessment = assessment

        return assessment

    def get_assessment(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get latest assessment for a session"""
        session_state = self.get_session(session_id)
        if not session_state:
            return None

        return session_state.latest_assessment

    def force_assessment(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Force an assessment regardless of event count"""
        session_state = self.get_session(session_id)
        if not session_state:
            return None

        if not self._has_any_scoring_model(session_state.user_id):
            return None

        return self._assess_session(session_state)

    def end_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """End a session and perform final assessment"""
        session_state = self.get_session(session_id)
        
        # Get baseline status and user_id from session_state or db
        is_baseline = False
        user_id = None
        
        if session_state:
            is_baseline = session_state.is_baseline
            user_id = session_state.user_id
        else:
            db_session = db.get_session(session_id)
            if db_session:
                is_baseline = bool(db_session.get('is_baseline', False))
                user_id = db_session.get('user_id')
            else:
                return None

        # Perform final assessment
        assessment = None
        if session_state and self._has_any_scoring_model(user_id):
            assessment = self._assess_session(session_state)

            # Update session in database
            if assessment:
                db.update_session_risk_assessment(
                    session_id=session_id,
                    anomaly_score=assessment['anomaly_score'],
                    risk_level=assessment['risk_level'],
                    action=assessment['action']
                )

        # Extract and save features for training using ALL session events
        all_events = db.get_session_events(session_id)
        if all_events:
            features = self.feature_extractor.extract_features(all_events)
            db.save_features(session_id, features)
            if user_id:
                self._refresh_user_profile(user_id)

        # If baseline session, update user baseline count
        if is_baseline and user_id:
            db.increment_baseline_count(user_id)

            # Check if baseline is complete
            user = db.get_user_by_id(user_id)
            if user and user.get('baseline_count', 0) >= MIN_BASELINE_SESSIONS:
                db.set_baseline_completed(user_id)

        # Mark session as ended in database
        db.end_session(session_id)

        # Remove from active sessions
        with self.lock:
            self.active_sessions.pop(session_id, None)

        logger.info(f"Ended session {session_id}")

        return assessment

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get session state"""
        with self.lock:
            return self.active_sessions.get(session_id)

    def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs"""
        with self.lock:
            return list(self.active_sessions.keys())

    def load_model(self) -> bool:
        """Load trained model"""
        try:
            self.ensemble_model.load()
            logger.info("Ensemble model loaded successfully")
            return True
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
            return False

    def _refresh_user_profile(self, user_id: int) -> Optional[int]:
        """Recompute and persist profile stats from benign user sessions."""
        rows = db.get_profile_features(user_id)
        if not rows:
            return None

        X = []
        from server.config import FEATURE_COLUMNS
        for row in rows:
            X.append([float(row.get(col, 0.0) or 0.0) for col in FEATURE_COLUMNS])

        X = np.array(X)
        mean_map = {}
        std_map = {}
        for i, col in enumerate(FEATURE_COLUMNS):
            mean_map[col] = float(np.mean(X[:, i]))
            std_map[col] = float(np.std(X[:, i]))

        sample_count = int(X.shape[0])
        db.upsert_user_profile(
            user_id=user_id,
            sample_count=sample_count,
            feature_mean=mean_map,
            feature_std=std_map
        )
        return sample_count

    def _get_blend_weights(self, profile_samples: int) -> Tuple[float, float]:
        """Return (global_weight, personal_weight)."""
        if not ENABLE_PROGRESSIVE_BLEND:
            return 1.0, 0.0

        if profile_samples < PERSONAL_BLEND_START_SAMPLES:
            return 1.0, 0.0

        if PERSONAL_BLEND_FULL_SAMPLES <= PERSONAL_BLEND_START_SAMPLES:
            return 0.0, 1.0

        ratio = (profile_samples - PERSONAL_BLEND_START_SAMPLES) / (
            PERSONAL_BLEND_FULL_SAMPLES - PERSONAL_BLEND_START_SAMPLES
        )
        personal_weight = float(np.clip(ratio, 0.0, 1.0))
        global_weight = 1.0 - personal_weight
        return global_weight, personal_weight

    def _has_any_scoring_model(self, user_id: Optional[int]) -> bool:
        """Check whether global model or a valid personal profile is available."""
        if self.ensemble_model.is_model_trained():
            return True

        if not user_id:
            return False

        profile = db.get_user_profile(user_id)
        if not profile:
            return False

        return int(profile.get('sample_count', 0) or 0) >= MIN_PERSONAL_PROFILE_SAMPLES

    def train_model(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Train model with collected data"""
        # Train global model using all baseline sessions
        training_data = db.get_all_features_for_training(user_id=None)

        if not training_data:
            return {
                'success': False,
                'message': 'No training data available',
                'samples_used': 0
            }

        # Prepare feature matrix
        from server.config import FEATURE_COLUMNS
        X = []
        for row in training_data:
            features = [row.get(col, 0.0) for col in FEATURE_COLUMNS]
            X.append(features)

        X = np.array(X, dtype=float)

        # Train model
        try:
            metrics = self.ensemble_model.train(X)

            # Save model
            self.ensemble_model.save()

            # Save metadata to database
            from server.config import ENSEMBLE_MODEL
            import os
            version = os.path.getmtime(ENSEMBLE_MODEL) if ENSEMBLE_MODEL.exists() else 0

            db.save_model_metadata(
                user_id=None,
                model_type='ensemble',
                version=str(version),
                samples_used=len(X),
                accuracy_metrics=metrics.get('ensemble', {})
            )

            profile_samples = None
            if user_id:
                profile_samples = self._refresh_user_profile(user_id)

            return {
                'success': True,
                'message': 'Global model trained successfully',
                'samples_used': len(X),
                'metrics': metrics,
                'model_version': str(version),
                'global_model': True,
                'personal_profile_samples': profile_samples
            }

        except Exception as e:
            logger.error(f"Error training model: {e}")
            return {
                'success': False,
                'message': f'Error training model: {str(e)}',
                'samples_used': 0
            }


# Global pipeline instance
pipeline = ProcessingPipeline()
