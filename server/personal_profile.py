"""
Personal profile scoring for progressive risk assessment.
"""

from typing import Dict, Optional
import numpy as np

from server.config import MIN_PERSONAL_PROFILE_SAMPLES


class PersonalProfileScorer:
    """Score behavior against a user's own historical profile."""

    def __init__(self, min_samples: int = MIN_PERSONAL_PROFILE_SAMPLES):
        self.min_samples = min_samples

    def score(
        self,
        features: Dict[str, float],
        profile: Optional[Dict[str, object]]
    ) -> Optional[float]:
        """
        Return score in range [-1, 1], where lower means more anomalous.
        """
        if not profile:
            return None

        sample_count = int(profile.get('sample_count', 0) or 0)
        if sample_count < self.min_samples:
            return None

        mean_map = profile.get('feature_mean') or {}
        std_map = profile.get('feature_std') or {}

        if not mean_map:
            return None

        z_scores = []
        for key, mean_value in mean_map.items():
            if key not in features:
                continue
            std_value = float(std_map.get(key, 0.0) or 0.0)
            # Guard against zero variance and tiny denominators
            safe_std = max(std_value, 1e-6)
            z = abs((float(features[key]) - float(mean_value)) / safe_std)
            z_scores.append(z)

        if not z_scores:
            return None

        # Typical benign sessions cluster around low average z.
        avg_z = float(np.mean(z_scores))
        score = 1.0 - (avg_z / 3.0)
        return float(np.clip(score, -1.0, 1.0))

