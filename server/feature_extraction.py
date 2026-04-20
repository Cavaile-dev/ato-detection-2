"""
Feature Extraction Module
Extracts 30+ behavioral features from raw events for anomaly detection
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from collections import defaultdict
import math

from server.config import (
    FEATURE_COLUMNS,
    MOUSE_FEATURES,
    KEYSTROKE_FEATURES,
    TEMPORAL_FEATURES,
    NAVIGATION_FEATURES,
    CROSS_MODAL_FEATURES,
    EVENT_TYPE_MOUSE_MOVE,
    EVENT_TYPE_MOUSE_CLICK,
    EVENT_TYPE_MOUSE_SCROLL,
    EVENT_TYPE_KEYSTROKE,
    EVENT_TYPE_NAVIGATION,
    EVENT_TYPE_COPY,
    EVENT_TYPE_PASTE
)


class FeatureExtractor:
    """Extract behavioral features from raw events"""

    def __init__(self):
        self.event_buffer = []
        self.last_keystroke_time = None
        self.last_mouse_position = None
        self.last_mouse_time = None
        self.session_start_time = None

    def extract_features(self, events: List[Dict[str, Any]], session_start_time: Optional[float] = None) -> Dict[str, float]:
        """
        Extract all features from a list of events
        Returns a dictionary with all 30+ features
        """
        if not events:
            return {col: 0.0 for col in FEATURE_COLUMNS}

        if session_start_time:
            self.session_start_time = session_start_time

        # Clear buffer
        self.event_buffer = events
        self.last_keystroke_time = None
        self.last_mouse_position = None
        self.last_mouse_time = None

        # Extract features by category
        features = {}
        features.update(self._extract_mouse_features())
        features.update(self._extract_keystroke_features())
        features.update(self._extract_temporal_features())
        features.update(self._extract_navigation_features())
        features.update(self._extract_cross_modal_features())

        # Ensure all features are present
        for col in FEATURE_COLUMNS:
            if col not in features:
                features[col] = 0.0

        return features

    def _extract_mouse_features(self) -> Dict[str, float]:
        """Extract 12 mouse-related features"""
        mouse_events = [
            e for e in self.event_buffer
            if e.get('event_type') in [EVENT_TYPE_MOUSE_MOVE, EVENT_TYPE_MOUSE_CLICK, EVENT_TYPE_MOUSE_SCROLL]
        ]

        if len(mouse_events) < 2:
            return {feat: 0.0 for feat in MOUSE_FEATURES}

        # Calculate velocities
        velocities = []
        accelerations = []
        jerks = []
        curvatures = []
        direction_changes = 0
        last_direction = None

        for i in range(1, len(mouse_events)):
            prev = mouse_events[i-1]
            curr = mouse_events[i]

            dt = curr.get('timestamp', 0) - prev.get('timestamp', 0)
            if dt == 0:
                continue

            # Position
            x1, y1 = prev.get('x', 0), prev.get('y', 0)
            x2, y2 = curr.get('x', 0), curr.get('y', 0)

            # Velocity
            dx = x2 - x1
            dy = y2 - y1
            distance = math.sqrt(dx**2 + dy**2)
            velocity = distance / dt if dt > 0 else 0
            velocities.append(velocity)

            # Direction
            if distance > 0:
                direction = math.atan2(dy, dx)
                if last_direction is not None:
                    angle_diff = abs(direction - last_direction)
                    if angle_diff > math.pi / 4:  # 45 degree threshold
                        direction_changes += 1
                last_direction = direction

            # Acceleration (if we have previous velocity)
            if len(velocities) > 1:
                prev_velocity = velocities[-2]
                dv = velocity - prev_velocity
                acceleration = dv / dt if dt > 0 else 0
                accelerations.append(acceleration)

                # Jerk (rate of change of acceleration)
                if len(accelerations) > 1:
                    prev_accel = accelerations[-2]
                    da = acceleration - prev_accel
                    jerk = da / dt if dt > 0 else 0
                    jerks.append(jerk)

            # Curvature (for 3+ points)
            if i >= 2:
                prev2 = mouse_events[i-2]
                x0, y0 = prev2.get('x', 0), prev2.get('y', 0)

                # Calculate curvature using three points
                area = x0*(y1 - y2) + x1*(y2 - y0) + x2*(y0 - y1)
                side_a = math.sqrt((x1-x0)**2 + (y1-y0)**2)
                side_b = math.sqrt((x2-x1)**2 + (y2-y1)**2)
                side_c = math.sqrt((x2-x0)**2 + (y2-y0)**2)

                if side_a * side_b * side_c > 0:
                    curvature = 4 * area / (side_a * side_b * side_c)
                    curvatures.append(abs(curvature))

        # Calculate click intervals
        click_events = [
            e for e in mouse_events
            if e.get('event_type') == EVENT_TYPE_MOUSE_CLICK
        ]
        click_intervals = []
        for i in range(1, len(click_events)):
            interval = click_events[i].get('timestamp', 0) - click_events[i-1].get('timestamp', 0)
            click_intervals.append(interval)

        # Calculate pauses (periods of inactivity)
        pauses = []
        for i in range(1, len(mouse_events)):
            dt = mouse_events[i].get('timestamp', 0) - mouse_events[i-1].get('timestamp', 0)
            if dt > 100:  # 100ms threshold for pause
                pauses.append(dt)

        # Aggregate features
        features = {
            'mouse_velocity_mean': float(np.mean(velocities)) if velocities else 0.0,
            'mouse_velocity_std': float(np.std(velocities)) if velocities else 0.0,
            'mouse_velocity_max': float(np.max(velocities)) if velocities else 0.0,
            'mouse_acceleration_mean': float(np.mean(accelerations)) if accelerations else 0.0,
            'mouse_acceleration_std': float(np.std(accelerations)) if accelerations else 0.0,
            'mouse_acceleration_max': float(np.max(accelerations)) if accelerations else 0.0,
            'mouse_jerk_mean': float(np.mean(jerks)) if jerks else 0.0,
            'mouse_jerk_std': float(np.std(jerks)) if jerks else 0.0,
            'mouse_curvature_mean': float(np.mean(curvatures)) if curvatures else 0.0,
            'mouse_direction_changes': float(direction_changes),
            'mouse_pause_count': float(len(pauses)),
            'mouse_click_interval_mean': float(np.mean(click_intervals)) if click_intervals else 0.0
        }

        return features

    def _extract_keystroke_features(self) -> Dict[str, float]:
        """Extract 10 keystroke-related features"""
        keystroke_events = [
            e for e in self.event_buffer
            if e.get('event_type') == EVENT_TYPE_KEYSTROKE
        ]

        if len(keystroke_events) < 2:
            return {feat: 0.0 for feat in KEYSTROKE_FEATURES}

        # Dwell times (how long key is held)
        dwell_times = [
            e.get('hold_time', 0) for e in keystroke_events
            if e.get('hold_time') is not None
        ]

        # Flight times (time between keystrokes)
        flight_times = []
        for i in range(1, len(keystroke_events)):
            dt = keystroke_events[i].get('timestamp', 0) - keystroke_events[i-1].get('timestamp', 0)
            flight_times.append(dt)

        # Calculate typing consistency (coefficient of variation)
        if len(flight_times) > 0:
            mean_flight = np.mean(flight_times)
            std_flight = np.std(flight_times)
            typing_consistency = 1.0 - (std_flight / (mean_flight + 1e-6))
            typing_consistency = max(0.0, min(1.0, typing_consistency))
        else:
            typing_consistency = 0.0

        # Error rate (backspace, delete keys)
        error_keys = ['Backspace', 'Delete']
        error_count = sum(
            1 for e in keystroke_events
            if e.get('key') in error_keys
        )
        error_rate = error_count / len(keystroke_events) if keystroke_events else 0.0

        # Key transition entropy (measure of randomness in key sequences)
        key_transitions = []
        for i in range(1, len(keystroke_events)):
            transition = (
                keystroke_events[i-1].get('key', ''),
                keystroke_events[i].get('key', '')
            )
            key_transitions.append(transition)

        # Calculate entropy
        if key_transitions:
            transition_counts = defaultdict(int)
            for transition in key_transitions:
                transition_counts[transition] += 1

            total = len(key_transitions)
            entropy = 0.0
            for count in transition_counts.values():
                p = count / total
                entropy -= p * math.log(p + 1e-6)
            key_entropy = entropy
        else:
            key_entropy = 0.0

        # Backspace rate
        backspace_count = sum(
            1 for e in keystroke_events
            if e.get('key') == 'Backspace'
        )
        backspace_rate = backspace_count / len(keystroke_events) if keystroke_events else 0.0

        # Correction rate (backspace followed by typing)
        correction_count = 0
        for i in range(1, len(keystroke_events)):
            if keystroke_events[i].get('key') == 'Backspace':
                # Check if next key is a regular character
                if i + 1 < len(keystroke_events):
                    next_key = keystroke_events[i + 1].get('key', '')
                    if next_key not in error_keys and len(next_key) == 1:
                        correction_count += 1
        correction_rate = correction_count / len(keystroke_events) if keystroke_events else 0.0

        # Typing speed (characters per second)
        if keystroke_events and flight_times:
            total_time = sum(flight_times)
            typing_speed = (len(keystroke_events) / (total_time / 1000.0)) if total_time > 0 else 0.0
        else:
            typing_speed = 0.0

        features = {
            'keystroke_dwell_time_mean': float(np.mean(dwell_times)) if dwell_times else 0.0,
            'keystroke_dwell_time_std': float(np.std(dwell_times)) if dwell_times else 0.0,
            'keystroke_flight_time_mean': float(np.mean(flight_times)) if flight_times else 0.0,
            'keystroke_flight_time_std': float(np.std(flight_times)) if flight_times else 0.0,
            'keystroke_typing_consistency': float(typing_consistency),
            'keystroke_error_rate': float(error_rate),
            'keystroke_transition_entropy': float(key_entropy),
            'keystroke_backspace_rate': float(backspace_rate),
            'keystroke_correction_rate': float(correction_rate),
            'keystroke_typing_speed': float(typing_speed)
        }

        return features

    def _extract_temporal_features(self) -> Dict[str, float]:
        """Extract 4 temporal features"""
        if not self.event_buffer:
            return {feat: 0.0 for feat in TEMPORAL_FEATURES}

        # Session duration
        first_event = self.event_buffer[0]
        last_event = self.event_buffer[-1]
        session_duration = (last_event.get('timestamp', 0) - first_event.get('timestamp', 0)) / 1000.0  # seconds

        # Time of day score (normalized 0-1)
        import datetime
        first_time = datetime.datetime.fromtimestamp(first_event.get('timestamp', 0) / 1000.0)
        hour_of_day = first_time.hour + first_time.minute / 60.0
        time_of_day_score = hour_of_day / 24.0  # Normalize to 0-1

        # Activity bursts (periods of high activity)
        # Group events by time windows (1 second)
        time_windows = defaultdict(int)
        for event in self.event_buffer:
            window = int(event.get('timestamp', 0) / 1000)
            time_windows[window] += 1

        activity_counts = list(time_windows.values())
        if activity_counts:
            mean_activity = np.mean(activity_counts)
            std_activity = np.std(activity_counts)
            activity_bursts = sum(1 for count in activity_counts if count > mean_activity + 2 * std_activity)
        else:
            activity_bursts = 0

        # Idle time ratio (periods with no activity)
        if len(self.event_buffer) > 1:
            gaps = []
            for i in range(1, len(self.event_buffer)):
                gap = self.event_buffer[i].get('timestamp', 0) - self.event_buffer[i-1].get('timestamp', 0)
                gaps.append(gap)

            idle_threshold = 2000  # 2 seconds
            idle_time = sum(g for g in gaps if g > idle_threshold)
            idle_time_ratio = idle_time / (session_duration * 1000) if session_duration > 0 else 0.0
        else:
            idle_time_ratio = 0.0

        features = {
            'temporal_time_of_day_score': float(time_of_day_score),
            'temporal_session_duration': float(session_duration),
            'temporal_activity_bursts': float(activity_bursts),
            'temporal_idle_time_ratio': float(idle_time_ratio)
        }

        return features

    def _extract_navigation_features(self) -> Dict[str, float]:
        """Extract 4 navigation-related features"""
        nav_events = [
            e for e in self.event_buffer
            if e.get('event_type') == EVENT_TYPE_NAVIGATION or e.get('event_type') == EVENT_TYPE_MOUSE_SCROLL
        ]

        if not nav_events:
            return {feat: 0.0 for feat in NAVIGATION_FEATURES}

        # Page transition pattern (measure of predictability)
        page_urls = [
            e.get('page_url', '')
            for e in nav_events
            if e.get('page_url')
        ]
        unique_pages = len(set(page_urls))
        page_transition_pattern = unique_pages / len(page_urls) if page_urls else 0.0

        # Time per page
        page_times = []
        page_map = {}
        for event in nav_events:
            url = event.get('page_url', '')
            if url:
                if url not in page_map:
                    page_map[url] = {'first': event.get('timestamp', 0), 'last': event.get('timestamp', 0)}
                else:
                    page_map[url]['last'] = event.get('timestamp', 0)

        for page_data in page_map.values():
            duration = (page_data['last'] - page_data['first']) / 1000.0
            if duration > 0:
                page_times.append(duration)

        time_per_page_mean = float(np.mean(page_times)) if page_times else 0.0

        # Scroll depth (how much user scrolls)
        scroll_events = [
            e for e in self.event_buffer
            if e.get('event_type') == EVENT_TYPE_MOUSE_SCROLL
        ]

        scroll_deltas = [
            abs(e.get('scroll_delta', 0))
            for e in scroll_events
        ]
        scroll_depth_mean = float(np.mean(scroll_deltas)) if scroll_deltas else 0.0

        # Scroll velocity
        scroll_velocities = [
            e.get('scroll_velocity', 0)
            for e in scroll_events
            if e.get('scroll_velocity') is not None
        ]
        scroll_velocity_mean = float(np.mean(scroll_velocities)) if scroll_velocities else 0.0

        features = {
            'nav_page_transition_pattern': float(page_transition_pattern),
            'nav_time_per_page_mean': float(time_per_page_mean),
            'nav_scroll_depth_mean': float(scroll_depth_mean),
            'nav_scroll_velocity_mean': float(scroll_velocity_mean)
        }

        return features

    def _extract_cross_modal_features(self) -> Dict[str, float]:
        """Extract 2 cross-modal features"""
        if not self.event_buffer:
            return {feat: 0.0 for feat in CROSS_MODAL_FEATURES}

        # Mouse-keyboard coordination
        # Measure how often mouse and keyboard events alternate
        mouse_events = [
            e for e in self.event_buffer
            if e.get('event_type') in [EVENT_TYPE_MOUSE_MOVE, EVENT_TYPE_MOUSE_CLICK]
        ]

        keyboard_events = [
            e for e in self.event_buffer
            if e.get('event_type') == EVENT_TYPE_KEYSTROKE
        ]

        # Count alternations
        alternations = 0
        last_type = None

        # Merge and sort by timestamp
        all_events = sorted(
            mouse_events + keyboard_events,
            key=lambda x: x.get('timestamp', 0)
        )

        for event in all_events:
            event_type = event.get('event_type', '')
            current_type = 'mouse' if 'MOUSE' in event_type else 'keyboard'

            if last_type and last_type != current_type:
                alternations += 1

            last_type = current_type

        mouse_keyboard_coordination = alternations / len(all_events) if all_events else 0.0

        # Copy-paste frequency
        copy_events = [
            e for e in self.event_buffer
            if e.get('event_type') == EVENT_TYPE_COPY
        ]

        paste_events = [
            e for e in self.event_buffer
            if e.get('event_type') == EVENT_TYPE_PASTE
        ]

        total_copy_paste = len(copy_events) + len(paste_events)
        copy_paste_frequency = total_copy_paste / len(self.event_buffer) if self.event_buffer else 0.0

        features = {
            'cross_mouse_keyboard_coordination': float(mouse_keyboard_coordination),
            'cross_copy_paste_frequency': float(copy_paste_frequency)
        }

        return features


def extract_features_from_events(events: List[Dict[str, Any]], session_start_time: Optional[float] = None) -> Dict[str, float]:
    """
    Convenience function to extract features from events
    """
    extractor = FeatureExtractor()
    return extractor.extract_features(events, session_start_time)


def extract_features_from_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract features from a DataFrame of events
    Useful for batch processing
    """
    features_list = []

    for session_id in df['session_id'].unique():
        session_events = df[df['session_id'] == session_id].to_dict('records')
        features = extract_features_from_events(session_events)
        features['session_id'] = session_id
        features_list.append(features)

    return pd.DataFrame(features_list)
