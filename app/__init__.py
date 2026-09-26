"""
NEXUS IoT - Application Factory
"""
import os
import sys
import signal
import logging
from flask import Flask, jsonify, request

from app.config import get_config
from app.logging_config import setup_logging
from app.database import init_db, close_db, get_wib_time
from app.extensions import cors, csrf, limiter

config = get_config()
logger = setup_logging(config)

try:
    config.validate()
    logger.info("Configuration validated")
except ValueError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)


def create_app(config_override=None):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config)

    if config_override:
        app.config.update(config_override)

    # ✅ FIX Tier 1 #5: ProxyFix — dapat IP device asli di belakang Nginx
    from werkzeug.middleware.proxy_fix import ProxyFix
    if not app.config.get('TESTING'):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )

    # CORS
    cors.init_app(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "X-CSRFToken"],
            "max_age": 3600,
        }
    })

    limiter.init_app(app)
    csrf.init_app(app)

    app.teardown_appcontext(close_db)

    # Cache-busting: Nginx menyajikan /static/ dengan "immutable 30d". Tanpa versi di URL,
    # browser terus memakai JS/CSS lama setelah update. Tambahkan ?v=<mtime> otomatis
    # ke setiap url_for('static', ...) supaya URL berubah saat file berubah.
    @app.url_defaults
    def _static_cache_bust(endpoint, values):
        if endpoint == 'static' and 'v' not in values:
            filename = values.get('filename')
            if filename:
                try:
                    values['v'] = int(os.path.getmtime(
                        os.path.join(app.static_folder, filename)
                    ))
                except OSError:
                    pass

    from app.auth import auth_bp
    from app.api import api_bp
    from app.views import views_bp
    from app.dashboards import dashboards_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(dashboards_bp)
    from app.chat import chat_bp
    app.register_blueprint(chat_bp)


    logger.info("CSRF: only /api/v1/data is exempt (device endpoint)")

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = (
            'geolocation=(), microphone=(), camera=(), payment=(), usb=()'
        )

        if config.SESSION_COOKIE_SECURE or config.ENABLE_HSTS:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )

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

    @app.errorhandler(400)
    def bad_request(e):
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

    @app.errorhandler(413)
    def payload_too_large(e):
        max_mb = config.MAX_CONTENT_LENGTH / (1024 * 1024)
        logger.warning(
            f"Payload too large from {request.remote_addr}: "
            f"{request.content_length} bytes"
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
        try:
            from app.database import get_db
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
        logger.error(f"Unhandled exception on {request.method} {request.path}: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': 'Internal server error',
                'type': type(e).__name__,
            }), 500
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    @app.route('/health')
    @limiter.exempt
    def health_check():
        try:
            from app.database import get_db_context
            with get_db_context() as conn:
                conn.execute('SELECT 1').fetchone()
            return jsonify({
                'status': 'healthy',
                'timestamp': get_wib_time().isoformat(),
                'database': 'connected',
                'version': '4.1',
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
        from app.background import start_background_tasks
        start_background_tasks()

    logger.info("Application ready")
    return app