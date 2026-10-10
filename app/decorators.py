"""
NEXUS IoT - Reusable Decorators
"""
from functools import wraps
from flask import jsonify


def api_error_handler(f):
    """Bungkus route dengan try/except standar untuk API.

    Semua exception akan di-log & di-return sebagai JSON error.
    """
    from flask import current_app
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            current_app.logger.error(
                f"Error in {f.__name__}: {e}", exc_info=True
            )
            return jsonify({
                'success': False,
                'error': 'Internal server error',
            }), 500
    return wrapper


def get_json_or_400():
    """Helper: ambil JSON payload, return None kalau invalid."""
    from flask import request
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None