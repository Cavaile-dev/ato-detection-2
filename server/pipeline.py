"""
Real-Time Processing Pipeline
Handles real-time event processing and risk assessment
"""

import threading
import time
import uuid
import shutil
from collections import Counter, deque
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging
from pathlib import Path

import numpy as np

from server.config import (
    ROLLING_WINDOW_SIZE,
    MIN_EVENTS_FOR_ASSESSMENT,
    ASSESSMENT_INTERVAL,
    FEATURE_COLUMNS,
    ENSEMBLE_MODEL,
    MODEL_DIR,
    TRAINING_MIN_SESSION_DURATION_SECONDS,
    TRAINING_MIN_NONZERO_FEATURES,
    TRAINING_MIN_NONZERO_FEATURE_RATIO,
    TRAINING_MAX_EVENT_RATE,
    TRAINING_OUTLIER_PRUNING_MIN_SAMPLES,
    TRAINING_OUTLIER_MAD_MULTIPLIER,
    HYBRID_PERSONAL_MIN_WEIGHT,
    HYBRID_PERSONAL_MAX_WEIGHT,
    HYBRID_PERSONAL_FULL_WEIGHT_SAMPLES
)
from server.database import db
from server.feature_extraction import FeatureExtractor
from server.models.ensemble import EnsembleModel
from server.risk_engine import RiskEngine, RiskAssessment
from server.time_utils import now_in_app_tz

logger = logging.getLogger(__name__)


class SessionState:
    """Manages state for an active session"""

    def __init__(
        self,
        session_id: str,
        user_id: int,
        is_training_valid: bool = False,
        start_time: Optional[datetime] = None
    ):
        self.session_id = session_id
        self.user_id = user_id
        # Backward-compatible field name; now means "valid for training dataset".
        self.is_baseline = is_training_valid
        self.start_time = start_time or now_in_app_tz()
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
        self.personal_models: Dict[int, Dict[str, Any]] = {}
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
        is_training_valid = False

        # Create session state
        session_state = SessionState(session_id, user_id, is_training_valid)
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
            is_baseline=is_training_valid
        )

        logger.info(f"Started session {session_id} for user {user_id}")

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
            'is_baseline': session_state.is_baseline,
            'is_training_valid': session_state.is_baseline
        }

        # Perform assessment if needed
        if session_state.should_assess() and self._has_model_for_user(session_state.user_id):
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

    def _assess_events(
        self,
        events: List[Dict[str, Any]],
        user_id: int,
        session_id: str,
        is_training_valid: bool
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, float]]]:
        """Perform risk assessment for a given event set."""
        if len(events) < MIN_EVENTS_FOR_ASSESSMENT:
            return None, None

        # Extract features
        features = self.feature_extractor.extract_features(events)

        try:
            prediction = self._predict_for_user(
                features=features,
                session_user_id=user_id,
                model_scope='auto'
            )
        except ValueError:
            return None, features

        # Assess risk
        assessment = self.risk_engine.assess_risk(
            anomaly_score=prediction['ensemble_score'],
            individual_scores=prediction['individual_scores'],
            features=features,
            session_context={
                'user_id': user_id,
                'session_id': session_id,
                'is_baseline': is_training_valid,
                'is_training_valid': is_training_valid
            }
        )

        assessment['model_scope'] = prediction.get('model_scope', 'auto')
        assessment['model_user_id'] = prediction.get('model_user_id')
        assessment['model_weights'] = prediction.get('model_weights')
        if prediction.get('raw_individual_scores') is not None:
            assessment['raw_individual_scores'] = prediction.get('raw_individual_scores')
        if prediction.get('model_details') is not None:
            assessment['model_details'] = prediction.get('model_details')

        return assessment, features

    def _assess_session(self, session_state: SessionState) -> Dict[str, Any]:
        """Perform risk assessment on a session"""
        assessment, features = self._assess_events(
            events=session_state.get_events(),
            user_id=session_state.user_id,
            session_id=session_state.session_id,
            is_training_valid=session_state.is_baseline
        )

        session_state.features = features
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

        if not self._has_model_for_user(session_state.user_id):
            return None

        return self._assess_session(session_state)

    def reassess_session(
        self,
        session_id: str,
        model_scope: str = 'global',
        model_user_id: Optional[int] = None,
        persist: bool = True
    ) -> Dict[str, Any]:
        """
        Re-predict risk for an existing session with selected model and optionally persist.
        """
        session = db.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        previous_risk_level = session.get('risk_level')
        previous_anomaly_score = session.get('anomaly_score')

        events = db.get_session_events(session_id)
        if len(events) < MIN_EVENTS_FOR_ASSESSMENT:
            raise ValueError(
                f"Insufficient events for assessment ({len(events)} < {MIN_EVENTS_FOR_ASSESSMENT})"
            )

        features = self.feature_extractor.extract_features(events)
        session_user_id = int(session.get('user_id'))

        prediction = self._predict_for_user(
            features=features,
            session_user_id=session_user_id,
            model_scope=model_scope,
            model_user_id=model_user_id
        )
        assessment = self.risk_engine.assess_risk(
            anomaly_score=prediction['ensemble_score'],
            individual_scores=prediction['individual_scores'],
            features=features,
            session_context={
                'user_id': session_user_id,
                'session_id': session_id,
                'is_baseline': bool(session.get('is_baseline', False))
            }
        )
        assessment['model_scope'] = prediction.get('model_scope', model_scope)
        assessment['model_user_id'] = prediction.get('model_user_id')
        assessment['model_weights'] = prediction.get('model_weights')
        if prediction.get('raw_individual_scores') is not None:
            assessment['raw_individual_scores'] = prediction.get('raw_individual_scores')
        if prediction.get('model_details') is not None:
            assessment['model_details'] = prediction.get('model_details')

        if persist:
            db.update_session_risk_assessment(
                session_id=session_id,
                anomaly_score=assessment['anomaly_score'],
                risk_level=assessment['risk_level'],
                action=assessment['action']
            )
            db.save_features(session_id, features)

        # Keep in-memory active state in sync if session is still active.
        active_state = self.get_session(session_id)
        if active_state:
            active_state.features = features
            active_state.latest_assessment = assessment

        new_risk_level = assessment.get('risk_level')
        new_anomaly_score = assessment.get('anomaly_score')
        score_changed = False
        if previous_anomaly_score is not None and new_anomaly_score is not None:
            try:
                score_changed = float(previous_anomaly_score) != float(new_anomaly_score)
            except (TypeError, ValueError):
                score_changed = str(previous_anomaly_score) != str(new_anomaly_score)

        return {
            'session_id': session_id,
            'persisted': persist,
            'assessment': assessment,
            'previous_risk_level': previous_risk_level,
            'new_risk_level': new_risk_level,
            'risk_changed': (
                previous_risk_level is not None and
                new_risk_level is not None and
                previous_risk_level != new_risk_level
            ),
            'previous_anomaly_score': previous_anomaly_score,
            'new_anomaly_score': new_anomaly_score,
            'score_changed': score_changed,
            'updated_fields': ['anomaly_score', 'risk_level', 'action']
        }

    def end_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """End a session and perform final assessment"""
        session_state = self.get_session(session_id)
        db_session = db.get_session(session_id)
        if not db_session:
            return None

        user_id = int(db_session.get('user_id'))

        # Perform final assessment
        assessment = None
        all_events = db.get_session_events(session_id)
        features = None

        if all_events and self._has_model_for_user(user_id):
            assessment, features = self._assess_events(
                events=all_events,
                user_id=user_id,
                session_id=session_id,
                is_training_valid=bool(db_session.get('is_baseline', False))
            )
        elif all_events:
            features = self.feature_extractor.extract_features(all_events)

        if assessment:
            db.update_session_risk_assessment(
                session_id=session_id,
                anomaly_score=assessment['anomaly_score'],
                risk_level=assessment['risk_level'],
                action=assessment['action']
            )

        if features:
            db.save_features(session_id, features)

        # Mark whether this session is valid for training dataset.
        is_training_valid = len(all_events) >= MIN_EVENTS_FOR_ASSESSMENT
        db.update_session_training_validity(session_id, is_training_valid)
        if session_state:
            session_state.is_baseline = is_training_valid
            session_state.features = features
            session_state.latest_assessment = assessment

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
            session_state = self.active_sessions.get(session_id)

        if session_state:
            return session_state

        return self._restore_session_from_db(session_id)

    def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs"""
        with self.lock:
            return list(self.active_sessions.keys())

    def clear_active_sessions(self) -> None:
        """Clear in-memory active sessions (used after full database reset)."""
        with self.lock:
            self.active_sessions.clear()
            self.personal_models.clear()

    def remove_user_runtime_state(
        self,
        user_id: int,
        remove_model_artifacts: bool = True
    ) -> Dict[str, Any]:
        """
        Remove in-memory runtime references for a deleted user and optionally
        delete saved personal model artifacts on disk.
        """
        removed_session_ids: List[str] = []
        with self.lock:
            for session_id, state in list(self.active_sessions.items()):
                if int(state.user_id) == int(user_id):
                    removed_session_ids.append(session_id)
                    self.active_sessions.pop(session_id, None)

            self.personal_models.pop(int(user_id), None)

        model_path = self._personal_model_path(int(user_id))
        model_dir = model_path.parent
        model_artifacts_deleted = False
        if remove_model_artifacts and model_dir.exists():
            shutil.rmtree(model_dir, ignore_errors=True)
            model_artifacts_deleted = True

        return {
            'removed_active_sessions': len(removed_session_ids),
            'removed_session_ids': removed_session_ids,
            'model_artifacts_deleted': model_artifacts_deleted
        }

    def restore_active_sessions(self) -> int:
        """Restore open sessions from the database into memory."""
        restored = 0
        for session in db.get_active_sessions():
            if self._restore_session_from_db(session['session_id'], session_record=session):
                restored += 1
        return restored

    def _restore_session_from_db(
        self,
        session_id: str,
        session_record: Optional[Dict[str, Any]] = None
    ) -> Optional[SessionState]:
        """Restore an active session from persisted database state."""
        session = session_record or db.get_session(session_id)
        if not session or session.get('end_time') is not None:
            return None

        start_time = None
        start_time_raw = session.get('start_time')
        if isinstance(start_time_raw, str):
            try:
                start_time = datetime.fromisoformat(start_time_raw)
            except ValueError:
                start_time = None

        restored_state = SessionState(
            session_id=session_id,
            user_id=int(session['user_id']),
            is_training_valid=bool(session.get('is_baseline', False)),
            start_time=start_time
        )
        restored_state.ip_address = session.get('ip_address')
        restored_state.device_fingerprint = session.get('device_fingerprint')
        restored_state.user_agent = session.get('user_agent')

        recent_events = list(reversed(db.get_recent_events(session_id, limit=ROLLING_WINDOW_SIZE)))
        for event in recent_events:
            restored_state.event_buffer.append(event)

        restored_state.event_count = int(session.get('event_count') or len(recent_events))

        with self.lock:
            existing_state = self.active_sessions.get(session_id)
            if existing_state:
                return existing_state
            self.active_sessions[session_id] = restored_state

        logger.info(f"Restored active session {session_id} for user {restored_state.user_id}")
        return restored_state

    def _personal_model_path(self, user_id: int) -> Path:
        from server.config import MODEL_DIR
        return MODEL_DIR / "personal" / f"user_{user_id}" / "ensemble_model.joblib"

    def _load_personal_model(self, user_id: int) -> Optional[EnsembleModel]:
        """Load personal model from disk/cache; returns None if unavailable."""
        personal_model_path = self._personal_model_path(user_id)
        if not personal_model_path.exists():
            return None

        try:
            current_mtime = personal_model_path.stat().st_mtime
            cached = self.personal_models.get(user_id)

            if cached and cached.get('mtime') == current_mtime:
                model = cached.get('model')
                if model and model.is_model_trained():
                    return model

            personal_model = EnsembleModel()
            personal_model.load(path=personal_model_path)

            if personal_model.is_model_trained():
                self.personal_models[user_id] = {
                    'model': personal_model,
                    'mtime': current_mtime
                }
                return personal_model
        except Exception as e:
            logger.warning(f"Could not load personal model for user {user_id}: {e}")

        return None

    def has_personal_model(self, user_id: int) -> bool:
        """Public helper for API/UI layer to know if personal model is available."""
        return self._load_personal_model(user_id) is not None

    def _get_model_training_samples(
        self,
        model: EnsembleModel,
        fallback_user_id: Optional[int] = None
    ) -> int:
        """Resolve the best available training-sample count for a model."""
        metadata = getattr(model, 'training_metadata', {}) or {}
        sample_count = metadata.get('n_samples')

        try:
            resolved = int(sample_count)
        except (TypeError, ValueError):
            resolved = 0

        if resolved <= 0 and fallback_user_id:
            resolved = db.get_user_training_valid_session_count(fallback_user_id)

        return max(0, resolved)

    def _calculate_personal_model_weight(
        self,
        user_id: int,
        personal_model: EnsembleModel
    ) -> float:
        """Increase personal-model influence as user-specific data becomes mature."""
        sample_count = self._get_model_training_samples(
            personal_model,
            fallback_user_id=user_id
        )
        maturity = min(
            1.0,
            sample_count / max(1, HYBRID_PERSONAL_FULL_WEIGHT_SAMPLES)
        )
        return (
            HYBRID_PERSONAL_MIN_WEIGHT +
            maturity * (HYBRID_PERSONAL_MAX_WEIGHT - HYBRID_PERSONAL_MIN_WEIGHT)
        )

    def _predict_with_model(
        self,
        model: EnsembleModel,
        features: Dict[str, float],
        scope: str,
        model_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run prediction for one concrete model and attach provenance metadata."""
        if not model.is_model_trained():
            raise ValueError("Selected model is not trained")

        prediction = model.predict_with_details(features)
        prediction['model_scope'] = scope
        prediction['model_user_id'] = model_user_id
        prediction['model_weights'] = {
            scope: 1.0
        }
        prediction['model_details'] = {
            scope: {
                'samples': self._get_model_training_samples(
                    model,
                    fallback_user_id=model_user_id
                ),
                'active_features': list(
                    getattr(model, 'active_feature_names', getattr(model, 'feature_names', []))
                ),
                'dropped_features': list(
                    getattr(model, 'preprocessing', {}).get('dropped_features', [])
                ),
            }
        }
        return prediction

    def _blend_predictions(
        self,
        global_prediction: Dict[str, Any],
        personal_prediction: Dict[str, Any],
        personal_weight: float
    ) -> Dict[str, Any]:
        """Blend global and personal predictions into one calibrated hybrid score."""
        personal_weight = min(1.0, max(0.0, personal_weight))
        global_weight = 1.0 - personal_weight

        individual_scores: Dict[str, Optional[float]] = {
            'global_ensemble': global_prediction.get('ensemble_score'),
            'personal_ensemble': personal_prediction.get('ensemble_score'),
        }
        raw_individual_scores: Dict[str, Optional[float]] = {}

        for prefix, prediction in (('global', global_prediction), ('personal', personal_prediction)):
            for model_name, score in (prediction.get('individual_scores') or {}).items():
                individual_scores[f'{prefix}_{model_name}'] = score
            for model_name, score in (prediction.get('raw_individual_scores') or {}).items():
                raw_individual_scores[f'{prefix}_{model_name}'] = score

        return {
            'ensemble_score': (
                float(global_prediction['ensemble_score']) * global_weight +
                float(personal_prediction['ensemble_score']) * personal_weight
            ),
            'individual_scores': individual_scores,
            'raw_individual_scores': raw_individual_scores,
            'model_scope': 'hybrid',
            'model_user_id': personal_prediction.get('model_user_id'),
            'model_weights': {
                'global': global_weight,
                'personal': personal_weight
            },
            'model_details': {
                'global': {
                    'samples': global_prediction.get('model_details', {}).get('global', {}).get('samples'),
                    'active_features': global_prediction.get('active_features'),
                    'dropped_features': global_prediction.get('dropped_features'),
                },
                'personal': {
                    'samples': personal_prediction.get('model_details', {}).get('personal', {}).get('samples'),
                    'active_features': personal_prediction.get('active_features'),
                    'dropped_features': personal_prediction.get('dropped_features'),
                }
            }
        }

    def _predict_for_user(
        self,
        features: Dict[str, float],
        session_user_id: int,
        model_scope: str = 'auto',
        model_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Resolve and execute the best prediction path for global/personal/auto modes."""
        global_model = self.ensemble_model if self.ensemble_model.is_model_trained() else None

        if model_scope == 'global':
            if not global_model:
                raise ValueError("Global model is not trained")
            return self._predict_with_model(global_model, features, 'global')

        if model_scope == 'personal':
            target_user_id = model_user_id or session_user_id
            personal_model = self._load_personal_model(target_user_id)
            if not personal_model:
                raise ValueError(f"Personal model for user_id={target_user_id} not found")
            return self._predict_with_model(
                personal_model,
                features,
                'personal',
                model_user_id=target_user_id
            )

        if model_scope != 'auto':
            raise ValueError("Invalid model_scope. Use 'auto', 'global', or 'personal'.")

        personal_model = self._load_personal_model(session_user_id)
        if personal_model and global_model:
            global_prediction = self._predict_with_model(global_model, features, 'global')
            personal_prediction = self._predict_with_model(
                personal_model,
                features,
                'personal',
                model_user_id=session_user_id
            )
            personal_weight = self._calculate_personal_model_weight(
                session_user_id,
                personal_model
            )
            return self._blend_predictions(
                global_prediction=global_prediction,
                personal_prediction=personal_prediction,
                personal_weight=personal_weight
            )

        if personal_model:
            return self._predict_with_model(
                personal_model,
                features,
                'personal',
                model_user_id=session_user_id
            )

        if global_model:
            return self._predict_with_model(global_model, features, 'global')

        raise ValueError("No trained model available")

    def _has_model_for_user(self, user_id: Optional[int]) -> bool:
        """Check whether there is a usable model for this user."""
        return bool(
            self.ensemble_model.is_model_trained() or
            (user_id and self._load_personal_model(user_id) is not None)
        )

    def has_any_trained_model(self) -> bool:
        """Check whether any global or personal model is available."""
        if self.ensemble_model.is_model_trained():
            return True

        from server.config import MODEL_DIR
        personal_root = MODEL_DIR / "personal"
        return personal_root.exists() and any(
            personal_root.glob("user_*/ensemble_model.joblib")
        )

    def load_model(self) -> bool:
        """Load trained model"""
        try:
            self.ensemble_model.load()
            logger.info("Ensemble model loaded successfully")
            return True
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
            return False

    def reset_runtime(self, remove_model_artifacts: bool = False) -> None:
        """Clear in-memory runtime state and optionally delete saved model artifacts."""
        self.clear_active_sessions()
        self.ensemble_model = EnsembleModel()

        if not remove_model_artifacts:
            return

        from server.config import (
            ENSEMBLE_MODEL,
            ISOLATION_FOREST_MODEL,
            SVM_MODEL,
            LSTM_MODEL,
            SCALER_MODEL,
            MODEL_DIR
        )

        file_targets = [
            ENSEMBLE_MODEL,
            ISOLATION_FOREST_MODEL,
            SVM_MODEL,
            SCALER_MODEL
        ]

        for target in file_targets:
            if target.exists():
                target.unlink()

        if LSTM_MODEL.exists():
            if LSTM_MODEL.is_dir():
                shutil.rmtree(LSTM_MODEL, ignore_errors=True)
            else:
                LSTM_MODEL.unlink()

        personal_root = MODEL_DIR / "personal"
        if personal_root.exists():
            shutil.rmtree(personal_root, ignore_errors=True)

    def _required_nonzero_feature_count(self, feature_count: int) -> int:
        return min(
            feature_count,
            max(
                TRAINING_MIN_NONZERO_FEATURES,
                int(np.ceil(feature_count * TRAINING_MIN_NONZERO_FEATURE_RATIO))
            )
        )

    def _prepare_training_data(
        self,
        training_data: List[Dict[str, Any]],
        feature_columns: List[str],
        min_samples: int
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Apply data-quality filtering before model fitting."""
        min_nonzero_features = self._required_nonzero_feature_count(len(feature_columns))
        drop_reasons: Counter = Counter()
        accepted_rows: List[Dict[str, Any]] = []
        rejected_preview: List[Dict[str, Any]] = []
        candidate_distribution: Counter = Counter()

        for row in training_data:
            session_id = row.get('session_id')
            row_user_id = row.get('user_id')
            if row_user_id is not None:
                candidate_distribution[str(row_user_id)] += 1

            values = []
            for column in feature_columns:
                value = row.get(column, 0.0)
                try:
                    numeric_value = float(value or 0.0)
                except (TypeError, ValueError):
                    numeric_value = 0.0
                if not np.isfinite(numeric_value):
                    numeric_value = 0.0
                values.append(numeric_value)

            feature_vector = np.asarray(values, dtype=float)
            duration = float(row.get('temporal_session_duration') or 0.0)
            event_count = int(row.get('event_count') or 0)
            nonzero_features = int(
                np.count_nonzero(np.abs(feature_vector) > 1e-9)
            )
            feature_abs_sum = float(np.sum(np.abs(feature_vector)))
            event_rate = (
                event_count / max(duration, 1e-6)
                if event_count > 0
                else 0.0
            )

            reasons = []
            if not row.get('end_time'):
                reasons.append('open_session')
            if event_count < MIN_EVENTS_FOR_ASSESSMENT:
                reasons.append('low_event_count')
            if duration < TRAINING_MIN_SESSION_DURATION_SECONDS:
                reasons.append('short_duration')
            if nonzero_features < min_nonzero_features:
                reasons.append('low_feature_coverage')
            if feature_abs_sum <= 0.0:
                reasons.append('empty_feature_vector')
            if event_rate > TRAINING_MAX_EVENT_RATE:
                reasons.append('excessive_event_rate')

            if reasons:
                drop_reasons.update(reasons)
                if len(rejected_preview) < 10:
                    rejected_preview.append({
                        'session_id': session_id,
                        'user_id': row_user_id,
                        'reasons': reasons,
                        'event_count': event_count,
                        'duration': duration,
                        'event_rate': event_rate,
                        'nonzero_features': nonzero_features
                    })
                continue

            accepted_rows.append({
                'session_id': session_id,
                'user_id': row_user_id,
                'values': feature_vector,
                'event_count': event_count,
                'duration': duration,
                'event_rate': event_rate,
                'nonzero_features': nonzero_features,
                'feature_abs_sum': feature_abs_sum
            })

        accepted_before_outlier = len(accepted_rows)

        if len(accepted_rows) >= TRAINING_OUTLIER_PRUNING_MIN_SAMPLES:
            matrix = np.vstack([row['values'] for row in accepted_rows])
            medians = np.median(matrix, axis=0)
            mad = np.median(np.abs(matrix - medians), axis=0)
            scale = np.where(mad > 1e-6, mad * 1.4826, 1.0)
            row_scores = np.mean(np.abs((matrix - medians) / scale), axis=1)

            score_median = float(np.median(row_scores))
            score_mad = float(np.median(np.abs(row_scores - score_median)))
            score_scale = max(score_mad * 1.4826, 1e-6)
            threshold = max(
                6.0,
                score_median + TRAINING_OUTLIER_MAD_MULTIPLIER * score_scale
            )
            keep_mask = row_scores <= threshold

            if int(np.sum(keep_mask)) >= max(min_samples, 6):
                retained_rows = []
                for row, keep, score in zip(accepted_rows, keep_mask, row_scores):
                    if keep:
                        retained_rows.append(row)
                        continue

                    drop_reasons.update(['feature_outlier'])
                    if len(rejected_preview) < 10:
                        rejected_preview.append({
                            'session_id': row['session_id'],
                            'user_id': row['user_id'],
                            'reasons': ['feature_outlier'],
                            'event_count': row['event_count'],
                            'duration': row['duration'],
                            'event_rate': row['event_rate'],
                            'nonzero_features': row['nonzero_features'],
                            'outlier_score': float(score)
                        })

                accepted_rows = retained_rows

        used_distribution: Counter = Counter()
        for row in accepted_rows:
            if row.get('user_id') is not None:
                used_distribution[str(row['user_id'])] += 1

        X = (
            np.vstack([row['values'] for row in accepted_rows]).astype(float)
            if accepted_rows
            else np.empty((0, len(feature_columns)), dtype=float)
        )

        report = {
            'candidate_samples': len(training_data),
            'samples_after_quality_filter': accepted_before_outlier,
            'samples_used': int(len(accepted_rows)),
            'filtered_samples': int(len(training_data) - len(accepted_rows)),
            'drop_reasons': dict(sorted(drop_reasons.items())),
            'quality_thresholds': {
                'min_events': MIN_EVENTS_FOR_ASSESSMENT,
                'min_duration_seconds': TRAINING_MIN_SESSION_DURATION_SECONDS,
                'min_nonzero_features': min_nonzero_features,
                'max_event_rate': TRAINING_MAX_EVENT_RATE
            },
            'candidate_user_distribution': dict(sorted(candidate_distribution.items())),
            'used_user_distribution': dict(sorted(used_distribution.items())),
            'rejected_sessions_preview': rejected_preview
        }

        return X, report

    def train_model(
        self,
        scope: str = 'global',
        user_id: Optional[int] = None,
        selected_features: Optional[List[str]] = None,
        min_samples: int = 10
    ) -> Dict[str, Any]:
        """Train global/personal model with selected feature subset."""
        import os

        if selected_features is not None and len(selected_features) == 0:
            return {
                'success': False,
                'message': 'At least one feature must be selected',
                'samples_used': 0
            }

        feature_columns = selected_features or FEATURE_COLUMNS
        invalid_features = [f for f in feature_columns if f not in FEATURE_COLUMNS]
        if invalid_features:
            return {
                'success': False,
                'message': f"Invalid features requested: {', '.join(invalid_features)}",
                'samples_used': 0
            }

        if scope not in ('global', 'personal'):
            return {
                'success': False,
                'message': "Invalid scope. Use 'global' or 'personal'.",
                'samples_used': 0
            }

        if scope == 'personal' and not user_id:
            return {
                'success': False,
                'message': 'user_id is required for personal model training',
                'samples_used': 0
            }

        # Get training data by scope.
        training_data = db.get_all_features_for_training(user_id if scope == 'personal' else None)

        if not training_data:
            return {
                'success': False,
                'message': 'No training data available',
                'samples_used': 0,
                'training_report': {
                    'candidate_samples': 0,
                    'samples_used': 0,
                    'filtered_samples': 0,
                    'drop_reasons': {}
                }
            }

        X, training_report = self._prepare_training_data(
            training_data=training_data,
            feature_columns=feature_columns,
            min_samples=min_samples
        )

        if len(X) < min_samples:
            return {
                'success': False,
                'message': (
                    "Insufficient usable samples after quality filtering: "
                    f"{len(X)} available, minimum {min_samples} required"
                ),
                'samples_used': int(len(X)),
                'candidate_samples': training_report['candidate_samples'],
                'filtered_samples': training_report['filtered_samples'],
                'training_report': training_report
            }

        try:
            if scope == 'global':
                target_model = self.ensemble_model
                save_path = ENSEMBLE_MODEL
                model_type = 'ensemble_global'
            else:
                target_model = EnsembleModel()
                personal_dir = MODEL_DIR / "personal" / f"user_{user_id}"
                save_path = personal_dir / "ensemble_model.joblib"
                model_type = 'ensemble_personal'

            # Keep feature mapping aligned for both training and prediction.
            target_model.feature_names = list(feature_columns)
            target_model.isolation_forest.feature_names = list(feature_columns)
            target_model.svm.feature_names = list(feature_columns)
            target_model.lstm.feature_names = list(feature_columns)

            metrics = target_model.train(X)
            warnings = []
            if training_report['samples_used'] <= min_samples:
                warnings.append(
                    'Training completed at the minimum usable sample threshold; more clean sessions will improve stability.'
                )
            if scope == 'global' and len(training_report['used_user_distribution']) < 2:
                warnings.append(
                    'Global model currently relies on one user only after quality filtering.'
                )
            if training_report['filtered_samples'] > training_report['samples_used']:
                warnings.append(
                    'More sessions were filtered out than retained; collect additional clean training data.'
                )
            dropped_feature_count = len(target_model.preprocessing.get('dropped_features', []))
            if dropped_feature_count > 0:
                warnings.append(
                    f'{dropped_feature_count} low-signal features were pruned automatically during training.'
                )

            training_report['warnings'] = warnings
            target_model.training_metadata.update({
                'scope': scope,
                'user_id': user_id if scope == 'personal' else None,
                'candidate_samples': training_report['candidate_samples'],
                'filtered_samples': training_report['filtered_samples'],
                'quality_report': training_report,
                'warnings': warnings
            })
            target_model.save(path=save_path if scope == 'personal' else None)

            version = os.path.getmtime(save_path) if save_path.exists() else 0
            db.save_model_metadata(
                user_id=user_id if scope == 'personal' else None,
                model_type=model_type,
                version=str(version),
                samples_used=len(X),
                accuracy_metrics={
                    'ensemble': metrics.get('ensemble', {}),
                    'training_report': training_report
                }
            )

            if scope == 'personal' and user_id:
                self.personal_models[user_id] = {
                    'model': target_model,
                    'mtime': version
                }

            return {
                'success': True,
                'message': f"{scope.capitalize()} model trained successfully",
                'scope': scope,
                'target_user_id': user_id if scope == 'personal' else None,
                'candidate_samples': training_report['candidate_samples'],
                'samples_used': int(len(X)),
                'filtered_samples': training_report['filtered_samples'],
                'feature_count': len(feature_columns),
                'active_feature_count': len(target_model.active_feature_names),
                'selected_features': list(feature_columns),
                'active_features': list(target_model.active_feature_names),
                'dropped_features': list(target_model.preprocessing.get('dropped_features', [])),
                'metrics': metrics,
                'training_report': training_report,
                'trained_models': list(target_model.training_metadata.get('trained_models', [])),
                'warnings': warnings,
                'model_version': str(version),
                'model_path': str(save_path) if scope == 'personal' else str(ENSEMBLE_MODEL)
            }

        except Exception as e:
            logger.error(f"Error training model: {e}")
            return {
                'success': False,
                'message': f'Error training model: {str(e)}',
                'samples_used': 0,
                'training_report': training_report
            }


# Global pipeline instance
pipeline = ProcessingPipeline()
