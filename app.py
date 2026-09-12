"""
NEXUS IoT - Flask Application Factory
"""
import os
import signal
import sys
import logging
from flask import Flask, jsonify, request

from config import get_config
from logging_config import setup_logging
from database import init_db, close_db, get_wib_time
from extensions import cors, csrf, limiter

# Setup logging PERTAMA sebelum apapun
config = get_config()
logger = setup_logging(config)

# Validasi config
try:
    config.validate()
    logger.info("✅ Configuration validated")
except ValueError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)


def create_app(config_override=None):
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(config)

    if config_override:
        app.config.update(config_override)

    # ==========================================
    # EXTENSIONS
    # ==========================================
    cors.init_app(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type"],
            "max_age": 3600,
        }
    })

    # CSRF hanya untuk form web (bukan API)
    csrf.init_app(app)

    # Rate limiter
    limiter.init_app(app)
    limiter._default_limits = [config.RATE_LIMIT_DEFAULT]

    # ==========================================
    # DATABASE
    # ==========================================
    app.teardown_appcontext(close_db)

    # ==========================================
    # BLUEPRINTS
    # ==========================================
    from auth import auth_bp
    from api import api_bp
    from views import views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # ==========================================
    # ✅ CSRF EXEMPT UNTUK API
    # API pakai API key (bukan session), jadi aman di-exempt dari CSRF.
    # CSRF hanya untuk form HTML seperti login.
    # ==========================================
    csrf.exempt(api_bp)
    logger.info("✅ API blueprint exempted from CSRF")

    # ==========================================
    # HEALTH CHECK
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
                'version': '3.0.0',
            }), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 503

    @app.route('/ready')
    @limiter.exempt
    def readiness_check():
        return jsonify({'status': 'ready'}), 200

    # ==========================================
    # ERROR HANDLERS
    # ==========================================
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({'success': False, 'error': 'Not found'}), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Coba lagi nanti.'
        }), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Internal server error'}), 500
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    # ==========================================
    # REQUEST LOGGING (hanya di debug)
    # ==========================================
    if config.DEBUG:
        @app.before_request
        def log_request():
            logger.debug(f"{request.method} {request.path}")

    # ==========================================
    # INIT DATABASE
    # ==========================================
    with app.app_context():
        init_db()

    # ==========================================
    # START BACKGROUND TASKS (kecuali saat testing)
    # ==========================================
    if not app.config.get('TESTING'):
        from background import start_background_tasks, stop_background_tasks
        start_background_tasks()

        # Graceful shutdown handler
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            stop_background_tasks()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    logger.info("✅ Application ready")
    return app


# ==========================================
# ENTRY POINT
# ==========================================
# Instance untuk gunicorn: `gunicorn wsgi:app`
app = create_app()


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 NEXUS IoT starting...")
    logger.info(f"   Host    : {config.HOST}")
    logger.info(f"   Port    : {config.PORT}")
    logger.info(f"   Debug   : {config.DEBUG}")
    logger.info(f"   Database: {config.DB_PATH}")
    logger.info(f"   URL     : http://{config.HOST}:{config.PORT}")
    logger.info("=" * 60)

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
        threaded=True,
    )