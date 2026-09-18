"""
NEXUS IoT - Flask Application Factory

✅ P0 FIX:
  - limiter.init_app SEBELUM csrf.init_app (rate limit jalan walau CSRF gagal)
  - module-level app = create_app() tetap ada (untuk Gunicorn)
  - signal handler dibungkus try/except (bisa dipanggil dari non-main thread)

✅ P1-A FIX:
  - Security headers (X-Content-Type-Options, X-Frame-Options, CSP, dll)
  - MAX_CONTENT_LENGTH handler (413 Payload Too Large)
"""
import os
import signal
import sys
import logging
import traceback
from flask import Flask, jsonify, request

from config import get_config
from logging_config import setup_logging
from database import init_db, close_db, get_wib_time
from extensions import cors, csrf, limiter

config = get_config()
logger = setup_logging(config)

try:
    config.validate()
    logger.info("Configuration validated")
except ValueError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)


def create_app(config_override=None):
    app = Flask(__name__)
    app.config.from_object(config)

    if config_override:
        app.config.update(config_override)

    cors.init_app(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "X-CSRFToken"],
            "max_age": 3600,
        }
    })

    # ✅ P0 FIX: limiter didaftarkan SEBELUM CSRF
    # supaya request POST tanpa CSRF token tetap dihitung untuk rate limit.
    limiter.init_app(app)
    csrf.init_app(app)

    app.teardown_appcontext(close_db)

    from auth import auth_bp
    from api import api_bp
    from views import views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # CSRF: hanya endpoint /api/v1/data yang di-exempt (lihat api.py)
    logger.info("CSRF: only /api/v1/data is exempt (device endpoint)")

    # ==========================================
    # ✅ P1-A: Security headers
    # ==========================================
    @app.after_request
    def add_security_headers(response):
        # Header dasar — selalu ditambahkan
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = (
            'geolocation=(), microphone=(), camera=(), payment=(), usb=()'
        )

        # HSTS hanya kalau HTTPS aktif (SESSION_COOKIE_SECURE=True)
        # atau dipaksa via ENABLE_HSTS
        if config.SESSION_COOKIE_SECURE or config.ENABLE_HSTS:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )

        # Content-Security-Policy
        csp = (
            f"default-src 'self'; "
            f"script-src {config.CSP_SCRIPT_SRC}; "
            f"style-src {config.CSP_STYLE_SRC}; "
            f"font-src {config.CSP_FONT_SRC}; "
            f"img-src {config.CSP_IMG_SRC}; "
            f"connect-src {config.CSP_CONNECT_SRC}; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"frame-ancestors 'self'"
        )
        if config.CSP_REPORT_ONLY:
            response.headers['Content-Security-Policy-Report-Only'] = csp
        else:
            response.headers['Content-Security-Policy'] = csp

        return response

    # ==========================================
    # Error handlers
    # ==========================================
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': 'Bad request',
                'detail': str(e.description) if hasattr(e, 'description') else None,
            }), 400
        return jsonify({'success': False, 'error': 'Bad request'}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'success': False, 'error': 'Not found'}), 404

    # ✅ P1-A: handler untuk payload terlalu besar
    @app.errorhandler(413)
    def payload_too_large(e):
        max_mb = config.MAX_CONTENT_LENGTH / (1024 * 1024)
        logger.warning(
            f"Payload too large from {request.remote_addr}: "
            f"{request.content_length} bytes > {config.MAX_CONTENT_LENGTH} bytes"
        )
        return jsonify({
            'success': False,
            'error': f'Payload terlalu besar. Maksimal {max_mb:.1f} MB.',
            'max_bytes': config.MAX_CONTENT_LENGTH,
        }), 413

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Coba lagi nanti.',
        }), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error on {request.method} {request.path}")
        logger.error(traceback.format_exc())

        try:
            from database import get_db
            db = get_db()
            db.rollback()
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e

        logger.error(f"Unhandled exception on {request.method} {request.path}: {e}")
        logger.error(traceback.format_exc())

        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': 'Internal server error',
                'type': type(e).__name__,
            }), 500
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    # ==========================================
    # Health check & readiness
    # ==========================================
    @app.route('/health')
    @limiter.exempt
    def health_check():
        try:
            from database import get_db_context
            with get_db_context() as conn:
                conn.execute('SELECT 1').fetchone()
            return jsonify({
                'status': 'healthy',
                'timestamp': get_wib_time().isoformat(),
                'database': 'connected',
                'version': '3.6',
            }), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

    @app.route('/ready')
    @limiter.exempt
    def readiness_check():
        return jsonify({'status': 'ready'}), 200

    if config.DEBUG:
        @app.before_request
        def log_request():
            logger.debug(f"{request.method} {request.path}")

    with app.app_context():
        init_db()

    if not app.config.get('TESTING'):
        from background import start_background_tasks, stop_background_tasks

        # ✅ P0: hanya 1 process yang dapat lock (lihat background.py)
        start_background_tasks()

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            stop_background_tasks()
            sys.exit(0)

        # ✅ signal.signal hanya bisa dipanggil di main thread
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except ValueError:
            pass

    logger.info("Application ready")
    return app


# ==========================================
# Module-level app untuk Gunicorn (`wsgi:app`)
# ==========================================
# Ini dieksekusi SATU KALI per worker saat pertama kali `app.py` di-import.
# wsgi.py cuma `from app import app` — tidak panggil create_app lagi.
app = create_app()


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("NEXUS IoT starting (dev mode)...")
    logger.info(f"   Host    : {config.HOST}")
    logger.info(f"   Port    : {config.PORT}")
    logger.info(f"   Debug   : {config.DEBUG}")
    logger.info(f"   Database: {config.DB_PATH}")
    logger.info(f"   URL     : http://{config.HOST}:{config.PORT}")
    logger.info("=" * 60)

    try:
        app.run(
            host=config.HOST,
            port=config.PORT,
            debug=config.DEBUG,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
        try:
            from background import stop_background_tasks
            stop_background_tasks()
        except Exception:
            pass