"""
Database operations module
Handles all SQLite database operations including schema creation and CRUD operations
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from contextlib import contextmanager

from server.config import DB_PATH, FEATURE_COLUMNS
from server.time_utils import now_in_app_tz, now_in_app_tz_iso, to_app_tz_datetime, to_app_tz_iso


class Database:
    """Database handler for SQLite operations"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.init_database()
        self.migrate_timestamps_to_app_timezone()

    @staticmethod
    def _normalize_timestamp(value: Any) -> Any:
        if value is None:
            return None
        normalized = to_app_tz_iso(value)
        return normalized if normalized else value

    def _normalize_record_timestamps(
        self,
        record: Dict[str, Any],
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        if not record:
            return record

        normalized = dict(record)
        timestamp_fields = fields or ['created_at', 'start_time', 'end_time', 'trained_at']
        for field_name in timestamp_fields:
            if field_name in normalized and normalized[field_name]:
                normalized[field_name] = self._normalize_timestamp(normalized[field_name])
        return normalized

    def _normalize_records_timestamps(
        self,
        records: List[Dict[str, Any]],
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        return [self._normalize_record_timestamps(record, fields=fields) for record in records]

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    baseline_count INTEGER DEFAULT 0,
                    baseline_completed BOOLEAN DEFAULT 0
                )
            """)

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    ip_address TEXT,
                    device_fingerprint TEXT,
                    user_agent TEXT,
                    is_baseline BOOLEAN DEFAULT 0,
                    event_count INTEGER DEFAULT 0,
                    anomaly_score REAL,
                    risk_level TEXT,
                    action TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # Raw events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    x REAL,
                    y REAL,
                    velocity REAL,
                    acceleration REAL,
                    key TEXT,
                    key_code INTEGER,
                    key_interval REAL,
                    hold_time REAL,
                    scroll_delta REAL,
                    scroll_velocity REAL,
                    button TEXT,
                    page_url TEXT,
                    page_title TEXT,
                    referrer TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # Features table
            feature_columns_sql = ",\n                    ".join([
                        f"{col} REAL DEFAULT 0.0" for col in FEATURE_COLUMNS
                    ])

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    {feature_columns_sql},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # Models table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    model_type TEXT NOT NULL,
                    version TEXT NOT NULL,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    samples_used INTEGER,
                    accuracy_metrics TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Create indexes for better query performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id
                ON sessions(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_start_time
                ON sessions(start_time)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_raw_events_session_id
                ON raw_events(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_raw_events_timestamp
                ON raw_events(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_session_id
                ON features(session_id)
            """)

    def migrate_timestamps_to_app_timezone(self) -> None:
        """
        Normalize legacy naive UTC timestamps to ISO-8601 in configured timezone.
        This migration is idempotent because timezone-aware values convert to
        the same wall-clock representation on subsequent runs.
        """
        migration_key = 'timestamps_migrated_to_app_timezone_v1'
        targets = [
            ('users', 'id', 'created_at'),
            ('sessions', 'session_id', 'start_time'),
            ('sessions', 'session_id', 'end_time'),
            ('raw_events', 'id', 'created_at'),
            ('features', 'id', 'created_at'),
            ('models', 'id', 'trained_at'),
        ]

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                (migration_key,)
            )
            row = cursor.fetchone()
            if row and row['value'] == '1':
                return

            for table_name, pk_name, col_name in targets:
                cursor.execute(
                    f"SELECT {pk_name}, {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL"
                )
                rows = cursor.fetchall()
                updates = []
                for row in rows:
                    raw_value = row[col_name]
                    converted = to_app_tz_iso(raw_value)
                    if converted and converted != raw_value:
                        updates.append((converted, row[pk_name]))

                if updates:
                    cursor.executemany(
                        f"UPDATE {table_name} SET {col_name} = ? WHERE {pk_name} = ?",
                        updates
                    )

            cursor.execute(
                """
                INSERT INTO app_metadata(key, value)
                VALUES (?, '1')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (migration_key,)
            )

    # User operations
    def create_user(self, username: str, password_hash: str) -> int:
        """Create a new user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, created_at)
                VALUES (?, ?, ?)
                """,
                (username, password_hash, now_in_app_tz_iso())
            )
            return cursor.lastrowid

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM users WHERE username = ?
                """,
                (username,)
            )
            row = cursor.fetchone()
            return self._normalize_record_timestamps(dict(row)) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM users WHERE id = ?
                """,
                (user_id,)
            )
            row = cursor.fetchone()
            return self._normalize_record_timestamps(dict(row)) if row else None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users with count of sessions valid for training."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.created_at,
                    COUNT(s.session_id) AS total_sessions,
                    COALESCE(SUM(
                        CASE
                            WHEN s.is_baseline = 1 AND s.end_time IS NOT NULL THEN 1
                            ELSE 0
                        END
                    ), 0) AS train_valid_sessions
                FROM users u
                LEFT JOIN sessions s ON s.user_id = u.id
                GROUP BY u.id, u.username, u.created_at
                ORDER BY username ASC
                """
            )
            rows = cursor.fetchall()
            return self._normalize_records_timestamps([dict(row) for row in rows])

    def get_user_training_valid_session_count(self, user_id: int) -> int:
        """Get count of ended sessions that are marked valid for training."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM sessions
                WHERE user_id = ? AND is_baseline = 1 AND end_time IS NOT NULL
                """,
                (user_id,)
            )
            row = cursor.fetchone()
            return int(row['count']) if row else 0

    # Session operations
    def create_session(
        self,
        session_id: str,
        user_id: int,
        ip_address: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        user_agent: Optional[str] = None,
        is_baseline: bool = False
    ) -> None:
        """Create a new session.

        `is_baseline` is kept for backward compatibility and now means
        "valid for training dataset".
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (
                    session_id, user_id, start_time, ip_address, device_fingerprint,
                    user_agent, is_baseline
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    now_in_app_tz_iso(),
                    ip_address,
                    device_fingerprint,
                    user_agent,
                    is_baseline
                )
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sessions WHERE session_id = ?
                """,
                (session_id,)
            )
            row = cursor.fetchone()
            return self._normalize_record_timestamps(dict(row)) if row else None

    def update_session_event_count(self, session_id: str, count: int):
        """Update session event count"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET event_count = ?
                WHERE session_id = ?
                """,
                (count, session_id)
            )

    def update_session_training_validity(self, session_id: str, is_valid: bool):
        """Mark whether this session is valid to be used for model training."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET is_baseline = ?
                WHERE session_id = ?
                """,
                (1 if is_valid else 0, session_id)
            )

    def update_session_risk_assessment(
        self,
        session_id: str,
        anomaly_score: float,
        risk_level: str,
        action: str
    ):
        """Update session with risk assessment results"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET anomaly_score = ?, risk_level = ?, action = ?
                WHERE session_id = ?
                """,
                (anomaly_score, risk_level, action, session_id)
            )

    def end_session(self, session_id: str):
        """Mark session as ended"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET end_time = ?
                WHERE session_id = ?
                """,
                (now_in_app_tz_iso(), session_id)
            )

    def get_all_sessions_detailed(self) -> List[Dict[str, Any]]:
        """Get all sessions with user info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, u.username 
                FROM sessions s 
                JOIN users u ON s.user_id = u.id 
                ORDER BY s.start_time DESC
            """)
            rows = cursor.fetchall()
            return self._normalize_records_timestamps([dict(row) for row in rows])

    def get_active_session_count(self) -> int:
        """Get count of sessions that are still active in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM sessions
                WHERE end_time IS NULL
                """
            )
            row = cursor.fetchone()
            return int(row['count']) if row else 0

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions for runtime restoration."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM sessions
                WHERE end_time IS NULL
                ORDER BY start_time ASC
                """
            )
            rows = cursor.fetchall()
            return self._normalize_records_timestamps([dict(row) for row in rows])

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its associated data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete features
            cursor.execute("DELETE FROM features WHERE session_id = ?", (session_id,))
            
            # Delete raw events
            cursor.execute("DELETE FROM raw_events WHERE session_id = ?", (session_id,))
            
            # Delete session
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            
            return cursor.rowcount > 0

    def delete_user_and_related(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Delete a user and all related sessions/events/features/models.
        Returns deletion summary, or None when user does not exist.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, username FROM users WHERE id = ?",
                (user_id,)
            )
            user_row = cursor.fetchone()
            if not user_row:
                return None

            cursor.execute(
                "SELECT COUNT(*) AS count FROM sessions WHERE user_id = ?",
                (user_id,)
            )
            sessions_deleted = int(cursor.fetchone()['count'])

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM raw_events
                WHERE session_id IN (
                    SELECT session_id FROM sessions WHERE user_id = ?
                )
                """,
                (user_id,)
            )
            events_deleted = int(cursor.fetchone()['count'])

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM features
                WHERE session_id IN (
                    SELECT session_id FROM sessions WHERE user_id = ?
                )
                """,
                (user_id,)
            )
            features_deleted = int(cursor.fetchone()['count'])

            cursor.execute(
                "SELECT COUNT(*) AS count FROM models WHERE user_id = ?",
                (user_id,)
            )
            models_deleted = int(cursor.fetchone()['count'])

            cursor.execute(
                """
                DELETE FROM raw_events
                WHERE session_id IN (
                    SELECT session_id FROM sessions WHERE user_id = ?
                )
                """,
                (user_id,)
            )
            cursor.execute(
                """
                DELETE FROM features
                WHERE session_id IN (
                    SELECT session_id FROM sessions WHERE user_id = ?
                )
                """,
                (user_id,)
            )
            cursor.execute(
                "DELETE FROM sessions WHERE user_id = ?",
                (user_id,)
            )
            cursor.execute(
                "DELETE FROM models WHERE user_id = ?",
                (user_id,)
            )
            cursor.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,)
            )

            return {
                'user_id': int(user_row['id']),
                'username': user_row['username'],
                'sessions_deleted': sessions_deleted,
                'events_deleted': events_deleted,
                'features_deleted': features_deleted,
                'models_deleted': models_deleted
            }

    def reset_database(self) -> None:
        """
        Delete all application data while keeping schema intact.
        This clears users, sessions, events, features, and models.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Child tables first, then parent tables.
            cursor.execute("DELETE FROM raw_events")
            cursor.execute("DELETE FROM features")
            cursor.execute("DELETE FROM sessions")
            cursor.execute("DELETE FROM models")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM app_metadata")

            # Optional table for some branches/versions.
            try:
                cursor.execute("DELETE FROM user_profiles")
            except sqlite3.OperationalError:
                pass

    def get_user_sessions(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get sessions for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ?
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (user_id, limit)
            )
            rows = cursor.fetchall()
            return self._normalize_records_timestamps([dict(row) for row in rows])

    def get_training_valid_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get sessions marked valid for training for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND is_baseline = 1 AND end_time IS NOT NULL
                ORDER BY start_time DESC
                """,
                (user_id,)
            )
            rows = cursor.fetchall()
            return self._normalize_records_timestamps([dict(row) for row in rows])

    def get_baseline_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Backward-compatible alias for get_training_valid_sessions."""
        return self.get_training_valid_sessions(user_id)

    # Event operations
    def insert_event(self, session_id: str, event: Dict[str, Any]) -> int:
        """Insert a raw event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO raw_events (
                    session_id, event_type, timestamp, x, y, velocity,
                    acceleration, key, key_code, key_interval, hold_time,
                    scroll_delta, scroll_velocity, button, page_url,
                    page_title, referrer
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event.get('event_type'),
                    event.get('timestamp'),
                    event.get('x'),
                    event.get('y'),
                    event.get('velocity'),
                    event.get('acceleration'),
                    event.get('key'),
                    event.get('key_code'),
                    event.get('key_interval'),
                    event.get('hold_time'),
                    event.get('scroll_delta'),
                    event.get('scroll_velocity'),
                    event.get('button'),
                    event.get('page_url'),
                    event.get('page_title'),
                    event.get('referrer')
                )
            )
            return cursor.lastrowid

    def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all events for a session"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM raw_events
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,)
            )
            rows = cursor.fetchall()
            return self._normalize_records_timestamps(
                [dict(row) for row in rows],
                fields=['created_at']
            )

    def get_recent_events(self, session_id: str, limit: int = 90) -> List[Dict[str, Any]]:
        """Get recent events for a session (for rolling window)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM raw_events
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit)
            )
            rows = cursor.fetchall()
            return self._normalize_records_timestamps(
                [dict(row) for row in rows],
                fields=['created_at']
            )

    # Feature operations
    def save_features(self, session_id: str, features: Dict[str, float]) -> None:
        """Save extracted features for a session"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Build the SQL dynamically based on FEATURE_COLUMNS
            columns = ["session_id"] + FEATURE_COLUMNS
            placeholders = ", ".join(["?"] * len(columns))
            columns_sql = ", ".join(columns)

            values = [session_id] + [features.get(col, 0.0) for col in FEATURE_COLUMNS]

            cursor.execute(
                f"""
                INSERT OR REPLACE INTO features ({columns_sql})
                VALUES ({placeholders})
                """,
                values
            )

    def get_session_features(self, session_id: str) -> Optional[Dict[str, float]]:
        """Get features for a session"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM features WHERE session_id = ?
                """,
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                return {col: row[col] for col in FEATURE_COLUMNS}
            return None

    def get_all_features_for_training(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all features for model training"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute(
                    f"""
                    SELECT
                        f.*,
                        s.user_id,
                        s.is_baseline,
                        s.start_time,
                        s.end_time,
                        s.event_count
                    FROM features f
                    JOIN sessions s ON f.session_id = s.session_id
                    WHERE s.user_id = ? AND s.is_baseline = 1 AND s.end_time IS NOT NULL
                    ORDER BY f.created_at DESC
                    """,
                    (user_id,)
                )
            else:
                cursor.execute(
                    f"""
                    SELECT
                        f.*,
                        s.user_id,
                        s.is_baseline,
                        s.start_time,
                        s.end_time,
                        s.event_count
                    FROM features f
                    JOIN sessions s ON f.session_id = s.session_id
                    WHERE s.is_baseline = 1 AND s.end_time IS NOT NULL
                    ORDER BY f.created_at DESC
                    """
                )

            rows = cursor.fetchall()
            return self._normalize_records_timestamps(
                [dict(row) for row in rows],
                fields=['start_time', 'end_time', 'created_at']
            )

    # Model operations
    def save_model_metadata(
        self,
        user_id: Optional[int],
        model_type: str,
        version: str,
        samples_used: int,
        accuracy_metrics: Optional[Dict[str, float]] = None
    ) -> int:
        """Save model metadata"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO models (
                    user_id, model_type, version, trained_at, samples_used, accuracy_metrics
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    model_type,
                    version,
                    now_in_app_tz_iso(),
                    samples_used,
                    json.dumps(accuracy_metrics) if accuracy_metrics else None
                )
            )
            return cursor.lastrowid

    def get_latest_model(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get latest model metadata"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute(
                    """
                    SELECT * FROM models
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY trained_at DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM models
                    WHERE is_active = 1
                    ORDER BY trained_at DESC
                    LIMIT 1
                    """
                )

            row = cursor.fetchone()
            return self._normalize_record_timestamps(dict(row)) if row else None

    # Dashboard statistics
    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get dashboard statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total counts
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM sessions")
            total_sessions = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM raw_events")
            total_events = cursor.fetchone()['count']

            # Active sessions (no end_time)
            cursor.execute("SELECT COUNT(*) as count FROM sessions WHERE end_time IS NULL")
            active_sessions = cursor.fetchone()['count']

            # Risk distribution for current Jakarta day.
            cursor.execute(
                """
                SELECT start_time, risk_level
                FROM sessions
                WHERE risk_level IS NOT NULL
                """
            )
            today_local = now_in_app_tz().date()
            high_risk_today = 0
            medium_risk_today = 0
            low_risk_today = 0

            for row in cursor.fetchall():
                local_dt = to_app_tz_datetime(row['start_time'])
                if not local_dt or local_dt.date() != today_local:
                    continue

                risk_level = row['risk_level']
                if risk_level == 'HIGH':
                    high_risk_today += 1
                elif risk_level == 'MEDIUM':
                    medium_risk_today += 1
                elif risk_level == 'LOW':
                    low_risk_today += 1

            # Average risk score
            cursor.execute("""
                SELECT AVG(anomaly_score) as avg_score
                FROM sessions
                WHERE anomaly_score IS NOT NULL
            """)
            avg_score = cursor.fetchone()['avg_score'] or 0.0

            # Model trained status
            cursor.execute("SELECT COUNT(*) as count FROM models WHERE is_active = 1")
            model_trained = cursor.fetchone()['count'] > 0

            # Top users by session count
            cursor.execute("""
                SELECT u.username, COUNT(s.session_id) as session_count
                FROM users u
                LEFT JOIN sessions s ON u.id = s.user_id
                GROUP BY u.id
                ORDER BY session_count DESC
                LIMIT 5
            """)
            top_users = [dict(row) for row in cursor.fetchall()]

            # Recent sessions
            cursor.execute("""
                SELECT s.session_id, u.username, s.start_time, s.risk_level, s.anomaly_score, s.event_count
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                ORDER BY s.start_time DESC
                LIMIT 10
            """)
            recent_sessions = self._normalize_records_timestamps(
                [dict(row) for row in cursor.fetchall()],
                fields=['start_time']
            )

            return {
                'total_users': total_users,
                'total_sessions': total_sessions,
                'total_events': total_events,
                'active_sessions': active_sessions,
                'high_risk_sessions_today': high_risk_today,
                'medium_risk_sessions_today': medium_risk_today,
                'low_risk_sessions_today': low_risk_today,
                'average_risk_score': avg_score,
                'model_trained': model_trained,
                'top_users': top_users,
                'recent_sessions': recent_sessions
            }


# Global database instance
db = Database()
