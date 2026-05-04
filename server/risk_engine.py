"""
Risk Engine Module
Handles risk scoring and decision making based on anomaly scores
"""

from typing import Dict, List, Any, Optional
import numpy as np

from server.time_utils import now_in_app_tz, now_in_app_tz_iso
from server.config import (
    RISK_THRESHOLD_LOW,
    RISK_THRESHOLD_MEDIUM,
    RISK_LEVEL_LOW,
    RISK_LEVEL_MEDIUM,
    RISK_LEVEL_HIGH,
    RISK_ACTION_ALLOW,
    RISK_ACTION_REQUIRE_MFA,
    RISK_ACTION_BLOCK,
    FEATURE_COLUMNS
)


class RiskEngine:
    """Engine for calculating risk scores and making decisions"""

    def __init__(self):
        self.threshold_low = RISK_THRESHOLD_LOW
        self.threshold_medium = RISK_THRESHOLD_MEDIUM

    def assess_risk(
        self,
        anomaly_score: float,
        individual_scores: Optional[Dict[str, float]] = None,
        features: Optional[Dict[str, float]] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Assess risk based on anomaly score and other factors

        Args:
            anomaly_score: Ensemble anomaly score (negative = anomalous)
            individual_scores: Scores from individual models
            features: Feature vector for contribution analysis
            session_context: Additional session context

        Returns:
            Risk assessment with level, action, and reasons
        """
        # Determine risk level
        if anomaly_score < self.threshold_low:
            risk_level = RISK_LEVEL_HIGH
            action = RISK_ACTION_BLOCK
        elif anomaly_score <= self.threshold_medium:
            risk_level = RISK_LEVEL_MEDIUM
            action = RISK_ACTION_REQUIRE_MFA
        else:
            risk_level = RISK_LEVEL_LOW
            action = RISK_ACTION_ALLOW

        # Generate reasons
        reasons = self._generate_reasons(
            anomaly_score,
            individual_scores,
            features,
            risk_level
        )

        # Calculate feature contributions
        feature_contributions = None
        if features:
            feature_contributions = self._calculate_feature_contributions(features)

        return {
            'anomaly_score': float(anomaly_score),
            'risk_level': risk_level,
            'action': action,
            'reasons': reasons,
            'individual_scores': individual_scores,
            'feature_contributions': feature_contributions,
            'timestamp': now_in_app_tz_iso()
        }

    def _generate_reasons(
        self,
        anomaly_score: float,
        individual_scores: Optional[Dict[str, float]],
        features: Optional[Dict[str, float]],
        risk_level: str
    ) -> List[str]:
        """Generate human-readable reasons for the risk assessment"""
        reasons = []

        # Base reason from risk level
        if risk_level == RISK_LEVEL_HIGH:
            reasons.append("Anomaly score exceeds high-risk threshold")
        elif risk_level == RISK_LEVEL_MEDIUM:
            reasons.append("Anomaly score indicates moderate risk")
        else:
            reasons.append("Behavior appears normal")

        # Individual model analysis
        if individual_scores:
            high_risk_models = [
                model for model, score in individual_scores.items()
                if score is not None and score < self.threshold_low
            ]

            if high_risk_models:
                reasons.append(f"High risk detected by: {', '.join(high_risk_models)}")

        # Feature-based reasons
        if features:
            feature_reasons = self._analyze_features(features)
            reasons.extend(feature_reasons)

        return reasons

    def _analyze_features(self, features: Dict[str, float]) -> List[str]:
        """Analyze features and generate specific reasons"""
        reasons = []

        # Mouse features
        if features.get('mouse_velocity_mean', 0) > 2000:
            reasons.append("Unusually high mouse velocity detected")

        if features.get('mouse_direction_changes', 0) > 100:
            reasons.append("Erratic mouse movement pattern detected")

        if features.get('mouse_pause_count', 0) > 50:
            reasons.append("Excessive mouse pauses detected")

        # Keystroke features
        if features.get('keystroke_typing_speed', 0) > 15:  # chars per second
            reasons.append("Unusually fast typing speed detected")

        if features.get('keystroke_error_rate', 0) > 0.2:
            reasons.append("High keystroke error rate detected")

        if features.get('keystroke_dwell_time_std', 0) > 100:
            reasons.append("Inconsistent keystroke timing detected")

        # Temporal features
        if features.get('temporal_session_duration', 0) < 10:
            reasons.append("Extremely short session duration")

        if features.get('temporal_idle_time_ratio', 0) > 0.8:
            reasons.append("High idle time ratio detected")

        # Cross-modal features
        if features.get('cross_copy_paste_frequency', 0) > 0.1:
            reasons.append("High copy-paste activity detected")

        return reasons

    def _calculate_feature_contributions(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate contribution of each feature to the anomaly score
        This is a simplified version - actual implementation would use model-specific methods
        """
        contributions = {}

        # Normalize features to 0-1 range for comparison
        for feature_name, value in features.items():
            if value != 0:
                # Use absolute value and normalize
                contributions[feature_name] = min(1.0, abs(value) / 100.0)
            else:
                contributions[feature_name] = 0.0

        return contributions

    def calculate_confidence(
        self,
        individual_scores: Dict[str, float],
        anomaly_score: float
    ) -> float:
        """
        Calculate confidence in the risk assessment
        Higher confidence when models agree
        """
        if not individual_scores:
            return 0.5

        # Get valid scores
        valid_scores = [s for s in individual_scores.values() if s is not None]

        if len(valid_scores) < 2:
            return 0.5

        # Calculate standard deviation (lower = higher confidence)
        std_dev = np.std(valid_scores)

        # Convert to confidence (0-1)
        confidence = 1.0 - min(1.0, std_dev / 2.0)

        return float(confidence)

    def get_risk_distribution(
        self,
        sessions: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Get distribution of risk levels across sessions

        Args:
            sessions: List of session dictionaries

        Returns:
            Dictionary with counts for each risk level
        """
        distribution = {
            RISK_LEVEL_LOW: 0,
            RISK_LEVEL_MEDIUM: 0,
            RISK_LEVEL_HIGH: 0
        }

        for session in sessions:
            risk_level = session.get('risk_level')
            if risk_level in distribution:
                distribution[risk_level] += 1

        return distribution


class RiskAssessment:
    """Container for risk assessment results"""

    def __init__(
        self,
        anomaly_score: float,
        risk_level: str,
        action: str,
        reasons: List[str],
        individual_scores: Optional[Dict[str, float]] = None,
        feature_contributions: Optional[Dict[str, float]] = None
    ):
        self.anomaly_score = anomaly_score
        self.risk_level = risk_level
        self.action = action
        self.reasons = reasons
        self.individual_scores = individual_scores
        self.feature_contributions = feature_contributions
        self.timestamp = now_in_app_tz()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'anomaly_score': self.anomaly_score,
            'risk_level': self.risk_level,
            'action': self.action,
            'reasons': self.reasons,
            'individual_scores': self.individual_scores,
            'feature_contributions': self.feature_contributions,
            'timestamp': self.timestamp.isoformat()
        }

    def is_high_risk(self) -> bool:
        """Check if this is a high-risk assessment"""
        return self.risk_level == RISK_LEVEL_HIGH

    def is_low_risk(self) -> bool:
        """Check if this is a low-risk assessment"""
        return self.risk_level == RISK_LEVEL_LOW

    def should_block(self) -> bool:
        """Check if session should be blocked"""
        return self.action == RISK_ACTION_BLOCK

    def requires_mfa(self) -> bool:
        """Check if session requires MFA"""
        return self.action == RISK_ACTION_REQUIRE_MFA
