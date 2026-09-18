"""
NEXUS IoT - Utility Functions
"""
import json
import os
import fcntl
import secrets
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

logger = logging.getLogger('nexus')

WIB = timezone(timedelta(hours=7))


def generate_api_key():
    return secrets.token_hex(32)


def hash_api_key(api_key):
    """
    ✅ P1-B: Hash API key device dengan SHA-256.

    Deterministic (tidak pakai salt) supaya bisa di-lookup langsung
    dari index. Untuk API key 64-char hex acak, SHA-256 tanpa salt
    tetap aman (brute-force 2^256 tidak feasible).
    """
    import hashlib
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def verify_api_key(api_key_plain, api_key_hash):
    """
    ✅ P1-B: Verifikasi API key dengan timing-safe comparison.
    Return True kalau cocok.
    """
    import hmac
    if not api_key_plain or not api_key_hash:
        return False
    computed = hash_api_key(api_key_plain)
    return hmac.compare_digest(computed, api_key_hash)


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
    """
    Return current WIB time as NAIVE datetime (no tzinfo) for SQLite storage.

    ✅ P0 FIX: sebelumnya mengembalikan aware datetime (dengan +07:00),
    sekarang naive supaya konsisten dengan query range dan parsing.
    """
    return datetime.now(WIB).replace(tzinfo=None)


def parse_datetime(value):
    """
    Parse datetime value dan normalisasi ke naive WIB.

    ✅ P0 FIX: handle aware & naive input, output selalu naive WIB.
    """
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
        # Sudah naive — anggap WIB (storage kita naive WIB)
        return dt

    return dt.astimezone(WIB).replace(tzinfo=None)


@contextmanager
def process_lock(name, blocking=True):
    """
    ✅ P0 FIX: Cross-process file lock.

    Dipakai untuk:
      - Serialize `init_db()` di multi-worker Gunicorn
      - Memastikan hanya 1 worker yang menjalankan background tasks

    Example:
        with process_lock('db-init') as got:
            if got:
                run_migration()
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
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(lock_file, flags)
            acquired = True
        except (IOError, OSError):
            acquired = False
        yield acquired
    except Exception as e:
        logger.warning(f"process_lock({name}) error: {e}")
        yield False
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


def validate_alert_rules(rules):
    if not isinstance(rules, dict):
        return False, "alert_rules harus berupa object"

    valid_severities = ['healthy', 'info', 'warning', 'danger']

    for sensor_key, rule in rules.items():
        if not isinstance(rule, dict):
            return False, f"Rule untuk '{sensor_key}' harus berupa object"
        for severity, range_dict in rule.items():
            if severity.startswith('_'):
                continue
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
            if float(range_dict['min']) > float(range_dict['max']):
                return False, f"'{sensor_key}.{severity}' min tidak boleh > max"

    return True, None


def validate_cors_origins(origins):
    if not origins:
        return ['http://localhost:5000']

    if '*' in origins:
        logger.warning(
            "[SECURITY] CORS_ORIGINS berisi '*' - ini tidak aman! "
            "Fallback ke localhost saja."
        )
        return ['http://localhost:5000']

    validated = []
    for origin in origins:
        origin = origin.strip()
        if not origin:
            continue
        if not (origin.startswith('http://') or origin.startswith('https://')):
            logger.warning(f"[SECURITY] CORS origin tidak valid (harus http/https): {origin}")
            continue
        validated.append(origin)

    return validated or ['http://localhost:5000']