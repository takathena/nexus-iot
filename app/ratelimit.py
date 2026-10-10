"""
NEXUS IoT - Helper rate limiting (tanpa dependensi flask_limiter agar mudah dites).
"""
import logging
import os
import re

logger = logging.getLogger('nexus')

_DEVICE_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')


def data_rate_limit_key(get_ip=None):
    """Key limiter untuk /api/v1/data: device_id dari body JSON bila valid, selain itu IP.

    Aman terhadap body invalid / terlalu besar / bukan object: tidak pernah raise.
    Body hanya di-parse bila Content-Length ada dan di bawah batas DATA_MAX_BYTES,
    supaya limiter tidak menjadi jalur untuk mem-parse body raksasa.
    """
    from flask import request, current_app
    from app.config import get_config

    if get_ip is None:
        from flask_limiter.util import get_remote_address as get_ip

    try:
        max_bytes = int(current_app.config.get('DATA_MAX_BYTES') or get_config().DATA_MAX_BYTES)
        length = request.content_length
        if length is not None and 0 < length <= max_bytes:
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                device_id = body.get('device_id')
                if isinstance(device_id, str) and _DEVICE_ID_RE.match(device_id):
                    return f"device:{device_id}"
    except Exception:  # key function tidak boleh membuat request gagal
        pass
    return get_ip()


def count_workers(env=None):
    """Perkirakan jumlah worker Gunicorn dari WEB_CONCURRENCY (default 1)."""
    env = os.environ if env is None else env
    try:
        return max(1, int(env.get('WEB_CONCURRENCY', '1')))
    except (TypeError, ValueError):
        return 1


def warn_if_memory_limiter_multiworker(storage_uri, workers=None, log=None):
    """Peringatkan bila limiter memory:// dipakai dengan >1 worker (kuota jadi per-worker)."""
    log = log or logger
    workers = count_workers() if workers is None else workers
    if str(storage_uri).startswith('memory://') and workers > 1:
        log.warning(
            f"RATE_LIMIT_STORAGE=memory:// dengan {workers} worker: kuota rate limit dihitung "
            f"per worker (efektif ~{workers}x lebih longgar). Gunakan storage bersama, "
            f"mis. RATE_LIMIT_STORAGE=redis://host:6379."
        )
        return True
    return False
