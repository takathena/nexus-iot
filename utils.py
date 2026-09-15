"""
NEXUS IoT - Utility Functions
"""
import json
import secrets
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def generate_api_key():
    return secrets.token_hex(32)


def safe_json_loads(data, default=None):
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
    return datetime.now(WIB)


def parse_datetime(value):
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


def validate_alert_rules(rules):
    """Validasi struktur alert_rules. Return (is_valid, error_message)"""
    if not isinstance(rules, dict):
        return False, "alert_rules harus berupa object"

    valid_severities = ['healthy', 'info', 'warning', 'danger']

    for sensor_key, rule in rules.items():
        if not isinstance(rule, dict):
            return False, f"Rule untuk '{sensor_key}' harus berupa object"
        for severity, range_dict in rule.items():
            if severity not in valid_severities:
                return False, f"Severity '{severity}' tidak valid. Pilih: {', '.join(valid_severities)}"
            if not isinstance(range_dict, dict):
                return False, f"'{sensor_key}.{severity}' harus berupa object"
            if 'min' not in range_dict or 'max' not in range_dict:
                return False, f"'{sensor_key}.{severity}' wajib punya 'min' dan 'max'"
            try:
                float(range_dict['min'])
                float(range_dict['max'])
            except (TypeError, ValueError):
                return False, f"'{sensor_key}.{severity}' min/max harus angka"

    return True, None