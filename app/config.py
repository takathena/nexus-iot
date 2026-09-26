"""
NEXUS IoT - Configuration
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    TESTING = False

    SECRET_KEY = os.getenv('SECRET_KEY')
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv('SESSION_LIFETIME_HOURS', 24)))
    SESSION_REFRESH_EACH_REQUEST = False
    SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv('SESSION_IDLE_TIMEOUT_MINUTES', 120))

    WTF_CSRF_ENABLED = True
    # CSRF token ikut lifetime session, bukan fixed 1 jam.
    # Tab yang dibiarkan terbuka lama tidak akan gagal save.
    WTF_CSRF_TIME_LIMIT = None

    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 2 * 1024 * 1024))
    ENABLE_HSTS = os.getenv('ENABLE_HSTS', 'False').lower() == 'true'
    CSP_REPORT_ONLY = os.getenv('CSP_REPORT_ONLY', 'False').lower() == 'true'

    NOTIFY_ENABLED = os.getenv('NOTIFY_ENABLED', 'False').lower() == 'true'
    NOTIFY_MIN_SEVERITY = os.getenv('NOTIFY_MIN_SEVERITY', 'warning')
    NOTIFY_ON_CLEARED = os.getenv('NOTIFY_ON_CLEARED', 'True').lower() == 'true'
    TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'False').lower() == 'true'
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    CSP_SCRIPT_SRC = os.getenv(
        'CSP_SCRIPT_SRC',
        "'self' 'unsafe-inline' "
        "https://cdnjs.cloudflare.com https://unpkg.com "
        "https://cdn.jsdelivr.net https://fonts.googleapis.com"
    )
    CSP_STYLE_SRC = os.getenv(
        'CSP_STYLE_SRC',
        "'self' 'unsafe-inline' "
        "https://cdnjs.cloudflare.com https://unpkg.com "
        "https://fonts.googleapis.com"
    )
    CSP_FONT_SRC = os.getenv(
        'CSP_FONT_SRC',
        "'self' data: https://cdnjs.cloudflare.com https://fonts.gstatic.com"
    )
    CSP_IMG_SRC = os.getenv(
        'CSP_IMG_SRC',
        "'self' data: blob: "
        "https://*.tile.openstreetmap.org https://unpkg.com"
    )
    CSP_CONNECT_SRC = os.getenv(
        'CSP_CONNECT_SRC',
        "'self' https://*.tile.openstreetmap.org"
    )

    IOT_USERNAME = os.getenv('IOT_USERNAME', 'admin')
    IOT_PASSWORD = os.getenv('IOT_PASSWORD')

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_PATH = os.getenv('DB_PATH', os.path.join(BASE_DIR, 'database', 'iot.db'))
    DATA_RETENTION_DAYS = int(os.getenv('DATA_RETENTION_DAYS', 30))
    ALERT_HISTORY_RETENTION_DAYS = int(os.getenv('ALERT_HISTORY_RETENTION_DAYS', 90))
    STATUS_LOG_RETENTION_DAYS = int(os.getenv('STATUS_LOG_RETENTION_DAYS', 30))
    ATTENDANCE_RETENTION_DAYS = int(os.getenv('ATTENDANCE_RETENTION_DAYS', 365))

    BACKUP_ENABLED = os.getenv('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_INTERVAL_HOURS = int(os.getenv('BACKUP_INTERVAL_HOURS', 24))
    BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', 7))
    BACKUP_DIR = os.getenv('BACKUP_DIR', os.path.join(BASE_DIR, 'backup'))

    OFFLINE_TIMEOUT = int(os.getenv('OFFLINE_TIMEOUT', 900))
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))
    DEFAULT_EXPECTED_INTERVAL = int(os.getenv('DEFAULT_EXPECTED_INTERVAL', 60))
    DEFAULT_OFFLINE_SEVERITY = os.getenv('DEFAULT_OFFLINE_SEVERITY', 'danger')
    BACKGROUND_TASKS_ENABLED = os.getenv('BACKGROUND_TASKS_ENABLED', 'True').lower() == 'true'

    RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '200 per minute')
    RATE_LIMIT_DATA = os.getenv('RATE_LIMIT_DATA', '60 per minute')
    RATE_LIMIT_LOGIN = os.getenv('RATE_LIMIT_LOGIN', '5 per minute')
    RATE_LIMIT_REGENERATE = os.getenv('RATE_LIMIT_REGENERATE', '10 per minute')
    RATE_LIMIT_STORAGE = os.getenv('RATE_LIMIT_STORAGE', 'memory://')

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', os.path.join(BASE_DIR, 'logs', 'nexus.log'))
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 10485760))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))

    ALERT_RULES = {
        'temperature': {
            'healthy': {'min': float(os.getenv('ALERT_TEMP_HEALTHY_MIN', 6)),
                        'max': float(os.getenv('ALERT_TEMP_HEALTHY_MAX', 28))},
            'warning': {'min': float(os.getenv('ALERT_TEMP_WARNING_MIN', 0)),
                        'max': float(os.getenv('ALERT_TEMP_WARNING_MAX', 32))},
            'danger': {'min': float(os.getenv('ALERT_TEMP_DANGER_MIN', -10)),
                       'max': float(os.getenv('ALERT_TEMP_DANGER_MAX', 40))},
            '_hysteresis': 0.5,
        },
        'humidity': {
            'healthy': {'min': 20, 'max': 90},
            'warning': {'min': 10, 'max': 95},
            'danger':  {'min': 0,  'max': 100},
            '_hysteresis': 1.0,
        },
        'gas_level': {
            'healthy': {'min': 0, 'max': 70},
            'warning': {'min': 0, 'max': 85},
            'danger':  {'min': 0, 'max': 100},
            '_hysteresis': 2.0,
        },
        'moisture': {
            'healthy': {'min': 40, 'max': 70},
            'warning': {'min': 30, 'max': 80},
            'danger':  {'min': 20, 'max': 90},
            '_hysteresis': 1.0,
        },
        'lux': {
            'healthy': {'min': 100, 'max': 800},
            'warning': {'min': 50, 'max': 1000},
            'danger':  {'min': 0, 'max': 2000},
            '_hysteresis': 50.0,
        },
        'co2': {
            'healthy': {'min': 300, 'max': 1000},
            'warning': {'min': 300, 'max': 1500},
            'danger':  {'min': 300, 'max': 5000},
            '_hysteresis': 50.0,
        },
        'smoke': {
            'healthy': {'min': 0, 'max': 200},
            'warning': {'min': 0, 'max': 500},
            'danger':  {'min': 0, 'max': 1000},
            '_hysteresis': 20.0,
        },
        'motion': {
            'healthy': {'min': 0, 'max': 0},
            'warning': {'min': 0, 'max': 1},
            'danger':  {'min': 0, 'max': 1},
            '_hysteresis': 0.0,
        },
        'voc': {
            'healthy': {'min': 0, 'max': 250},
            'warning': {'min': 0, 'max': 500},
            'danger':  {'min': 0, 'max': 1000},
            '_hysteresis': 20.0,
        },
        'air_quality': {
            'healthy': {'min': 0, 'max': 100},
            'warning': {'min': 0, 'max': 200},
            'danger':  {'min': 0, 'max': 500},
            '_hysteresis': 10.0,
        },
    }

    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False

    @staticmethod
    def _parse_cors_origins():
        raw = os.getenv('CORS_ORIGINS', 'http://localhost:5000')
        origins = [o.strip() for o in raw.split(',') if o.strip()]
        if '*' in origins:
            import logging
            logging.getLogger('nexus').warning(
                "[SECURITY] CORS_ORIGINS='*' ditolak. Menggunakan localhost."
            )
            return ['http://localhost:5000']
        validated = [o for o in origins if o.startswith(('http://', 'https://'))]
        return validated or ['http://localhost:5000']

    CORS_ORIGINS = _parse_cors_origins.__func__()

    @classmethod
    def validate(cls):
        errors = []
        if not cls.SECRET_KEY:
            errors.append("SECRET_KEY wajib di-set di .env")
        elif len(cls.SECRET_KEY) < 32:
            errors.append("SECRET_KEY minimal 32 karakter")
        elif cls.SECRET_KEY.startswith('CHANGE_ME'):
            errors.append("SECRET_KEY masih default, generate yang baru!")

        if not cls.IOT_PASSWORD:
            errors.append("IOT_PASSWORD wajib di-set di .env")
        elif cls.IOT_PASSWORD in ('admin', 'password', 'change-me-to-strong-password'):
            errors.append("IOT_PASSWORD masih default, ganti dengan yang kuat!")

        if not cls.IOT_USERNAME:
            errors.append("IOT_USERNAME wajib di-set")

        if not (1 <= cls.PORT <= 65535):
            errors.append(f"PORT harus antara 1-65535, dapat: {cls.PORT}")

        if cls.OFFLINE_TIMEOUT < 10:
            errors.append("OFFLINE_TIMEOUT minimal 10 detik")
        if cls.CHECK_INTERVAL < 10:
            errors.append("CHECK_INTERVAL minimal 10 detik")

        if cls.NOTIFY_ENABLED:
            if cls.TELEGRAM_ENABLED:
                if not cls.TELEGRAM_BOT_TOKEN:
                    errors.append("TELEGRAM_ENABLED=True tapi TELEGRAM_BOT_TOKEN kosong")
                if not cls.TELEGRAM_CHAT_ID:
                    errors.append("TELEGRAM_ENABLED=True tapi TELEGRAM_CHAT_ID kosong")
            else:
                errors.append("NOTIFY_ENABLED=True tapi TELEGRAM_ENABLED=False")

        if errors:
            raise ValueError(
                "\n\nCONFIGURATION ERRORS:\n" +
                "\n".join(f"  - {e}" for e in errors) +
                "\n\nPerbaiki file .env Anda!\n"
            )


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    IOT_USERNAME = 'test'
    IOT_PASSWORD = 'test'
    SECRET_KEY = 'test-secret-key-for-testing-only-32chars-minimum'


def get_config():
    env = os.getenv('FLASK_ENV', 'production').lower()
    if env == 'development':
        return DevelopmentConfig
    elif env == 'testing':
        return TestingConfig
    return ProductionConfig