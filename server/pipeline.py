"""
Real-Time Processing Pipeline
Handles real-time event processing and risk assessment
"""

import threading
import time
import uuid
from collections import deque
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from server.config import (
    ROLLING_WINDOW_SIZE,
    MIN_EVENTS_FOR_ASSESSMENT,
    ASSESSMENT_INTERVAL,
    MIN_BASELINE_SESSIONS
)
from server.database import db
from server.feature_extraction import FeatureExtractor
from server.models.ensemble import EnsembleModel
from server.risk_engine import RiskEngine, RiskAssessment

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
            if self.is_baseline:
                return False  # Don't assess baseline sessions
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
        if session_state.should_assess() and self.ensemble_model.is_model_trained():
            assessment = self._assess_session(session_state)
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

        # Get prediction with details
        prediction = self.ensemble_model.predict_with_details(features)

        # Assess risk
        assessment = self.risk_engine.assess_risk(
            anomaly_score=prediction['ensemble_score'],
            individual_scores=prediction['individual_scores'],
            features=features,
            session_context={
                'user_id': session_state.user_id,
                'session_id': session_state.session_id,
                'is_baseline': session_state.is_baseline
            }
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

        if not self.ensemble_model.is_model_trained():
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
        if session_state and not is_baseline and self.ensemble_model.is_model_trained():
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

    def train_model(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Train model with collected data"""
        # Get training data
        training_data = db.get_all_features_for_training(user_id)

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

        X = np.array(X)

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
                user_id=user_id,
                model_type='ensemble',
                version=str(version),
                samples_used=len(X),
                accuracy_metrics=metrics.get('ensemble', {})
            )

            return {
                'success': True,
                'message': 'Model trained successfully',
                'samples_used': len(X),
                'metrics': metrics,
                'model_version': str(version)
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

# Import numpy at module level for train_model
import numpy as np
