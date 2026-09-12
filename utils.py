"""
NEXUS IoT - Utility Functions
"""
import json
import secrets
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def generate_api_key():
    """Generate 32-byte hex API key (64 karakter)"""
    return secrets.token_hex(32)


def safe_json_loads(data, default=None):
    """Parse JSON dengan aman"""
    if default is None:
        default = {}
    if not data:
        return default
    if isinstance(data, (dict, list)):
        return data
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default


def get_wib_time():
    """Waktu WIB (UTC+7)"""
    return datetime.now(WIB)


def parse_datetime(value):
    """Parse datetime string ke timezone-aware datetime"""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WIB)
    return dt