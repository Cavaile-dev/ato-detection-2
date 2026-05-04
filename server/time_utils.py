"""
Timezone helpers for consistent app-wide timestamp handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from server.config import APP_TIMEZONE


TimestampInput = Union[str, datetime]


def get_app_timezone() -> ZoneInfo:
    """Return configured timezone object."""
    return ZoneInfo(APP_TIMEZONE)


def now_in_app_tz() -> datetime:
    """Current datetime in configured timezone."""
    return datetime.now(get_app_timezone())


def now_in_app_tz_iso() -> str:
    """Current datetime in configured timezone as ISO-8601 string."""
    return now_in_app_tz().isoformat(timespec='seconds')


def parse_timestamp(value: TimestampInput) -> Optional[datetime]:
    """
    Parse supported timestamp formats.
    Naive timestamps are treated as UTC for backward compatibility.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        normalized = text.replace('Z', '+00:00')
        parsed = None
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            pass

        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue

        if parsed is None:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def to_app_tz_datetime(value: TimestampInput) -> Optional[datetime]:
    """Convert a timestamp to configured timezone."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.astimezone(get_app_timezone())


def to_app_tz_iso(value: TimestampInput) -> Optional[str]:
    """Convert a timestamp to configured timezone and return ISO-8601."""
    converted = to_app_tz_datetime(value)
    if converted is None:
        return None
    return converted.isoformat(timespec='seconds')
