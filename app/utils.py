"""
NEXUS IoT - Utilities
"""
import json
import os
import fcntl
import secrets
import logging
import hmac
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

logger = logging.getLogger('nexus')

WIB = timezone(timedelta(hours=7))


def generate_api_key():
    return secrets.token_hex(32)


def hash_api_key(api_key):
    """SHA-256 hash API key (deterministic untuk lookup)."""
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def verify_api_key(api_key_plain, api_key_hash):
    """Timing-safe comparison."""
    if not api_key_plain or not api_key_hash:
        return False
    computed = hash_api_key(api_key_plain)
    return hmac.compare_digest(computed, api_key_hash)


_CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def csv_safe(value):
    """Cegah CSV/formula injection: sel string berawalan = + - @ TAB CR diberi awalan '.

    Hanya string yang diubah; angka/None dikembalikan apa adanya.
    """
    if isinstance(value, str) and value and value[0] in _CSV_FORMULA_PREFIXES:
        return "'" + value
    return value


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


def parse_datetime(value):
    """Parse datetime → naive WIB."""
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
        return dt
    return dt.astimezone(WIB).replace(tzinfo=None)


# ✅ FIX #10: process_lock tidak swallow exception
# Kalau lock gagal karena error sistem (bukan karena lock dipegang proses lain),
# kita raise supaya caller tahu.
@contextmanager
def process_lock(name, blocking=True):
    """Cross-process file lock.

    Yield True jika lock didapat, False jika lock dipegang proses lain.
    Raise OSError jika ada error sistem (permission, disk, dll).
    """
    lock_dir = os.environ.get('NEXUS_LOCK_DIR', '/tmp')
    try:
        os.makedirs(lock_dir, exist_ok=True)
    except Exception:
        lock_dir = '/tmp'

    lock_path = os.path.join(lock_dir, f'nexus-{name}.lock')
    lock_file = None
    acquired = False

    try:
        lock_file = open(lock_path, 'w')
    except OSError as e:
        # Tidak bisa buka file lock → error sistem, raise
        logger.error(f"process_lock({name}): cannot open lock file: {e}")
        raise

    try:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(lock_file, flags)
            acquired = True
        except (IOError, OSError):
            # Lock dipegang proses lain → yield False, bukan raise
            acquired = False

        yield acquired
    finally:
        if lock_file is not None:
            try:
                if acquired:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_file.close()
            except Exception:
                pass


VALID_ALERT_SEVERITIES = ['healthy', 'info', 'warning', 'danger']


def validate_single_alert_rule(rule):
    """Validasi satu rule sensor. Return (bool, pesan_error|None).

    Satu-satunya sumber aturan validitas rule, dipakai oleh API (lewat
    validate_alert_rules) dan oleh mesin alert (alerts._validate_rule).
    """
    if not isinstance(rule, dict):
        return False, 'harus berupa object'
    for severity, range_dict in rule.items():
        if severity.startswith('_'):
            continue
        if severity not in VALID_ALERT_SEVERITIES:
            return False, f"severity '{severity}' tidak valid"
        if not isinstance(range_dict, dict):
            return False, f"'{severity}' harus berupa object"
        if 'min' not in range_dict or 'max' not in range_dict:
            return False, f"'{severity}' wajib punya 'min' dan 'max'"
        try:
            lo = float(range_dict['min'])
            hi = float(range_dict['max'])
        except (TypeError, ValueError):
            return False, f"'{severity}' min/max harus angka"
        if lo > hi:
            return False, f"'{severity}' min tidak boleh > max"
    return True, None


def validate_alert_rules(rules):
    if not isinstance(rules, dict):
        return False, "alert_rules harus berupa object"

    for sensor_key, rule in rules.items():
        ok, reason = validate_single_alert_rule(rule)
        if not ok:
            return False, f"Rule '{sensor_key}' {reason}"

    return True, None