"""
NEXUS IoT - Configuration Management
Semua konfigurasi dibaca dari environment variable.
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""

    # ==========================================
    # SERVER
    # ==========================================
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    WORKERS = int(os.getenv('WORKERS', 2))
    THREADS = int(os.getenv('THREADS', 4))

    # ==========================================
    # SECURITY
    # ==========================================
    SECRET_KEY = os.getenv('SECRET_KEY')
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.getenv('SESSION_LIFETIME_HOURS', 24))
    )
    SESSION_REFRESH_EACH_REQUEST = True

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Selama session

    # ==========================================
    # AUTHENTICATION
    # ==========================================
    IOT_USERNAME = os.getenv('IOT_USERNAME', 'admin')
    IOT_PASSWORD = os.getenv('IOT_PASSWORD')

    # ==========================================
    # DATABASE
    # ==========================================
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.getenv('DB_PATH', os.path.join(BASE_DIR, 'database', 'iot.db'))
    DATA_RETENTION_DAYS = int(os.getenv('DATA_RETENTION_DAYS', 30))

    # Backup
    BACKUP_ENABLED = os.getenv('BACKUP_ENABLED', 'True').lower() == 'true'
    BACKUP_INTERVAL_HOURS = int(os.getenv('BACKUP_INTERVAL_HOURS', 24))
    BACKUP_RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', 7))
    BACKUP_DIR = os.getenv('BACKUP_DIR', os.path.join(BASE_DIR, 'backup'))

    # ==========================================
    # DEVICE MONITORING
    # ==========================================
    OFFLINE_TIMEOUT = int(os.getenv('OFFLINE_TIMEOUT', 900))  # 15 menit
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))     # 1 menit

    # ==========================================
    # CORS
    # ==========================================
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv('CORS_ORIGINS', 'http://localhost:5000').split(',')
        if origin.strip()
    ]

    # ==========================================
    # RATE LIMITING
    # ==========================================
    RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '200 per minute')
    RATE_LIMIT_DATA = os.getenv('RATE_LIMIT_DATA', '60 per minute')
    RATE_LIMIT_LOGIN = os.getenv('RATE_LIMIT_LOGIN', '5 per minute')

    # ==========================================
    # LOGGING
    # ==========================================
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', os.path.join(BASE_DIR, 'logs', 'nexus.log'))
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 10485760))  # 10 MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))

    # ==========================================
    # ALERTS
    # ==========================================
    ALERT_RULES = {
        'temperature': {
            'min': float(os.getenv('ALERT_TEMP_MIN', 0)),
            'max': float(os.getenv('ALERT_TEMP_MAX', 40)),
            'message': 'Suhu di luar batas normal',
        },
        'humidity': {
            'min': float(os.getenv('ALERT_HUMIDITY_MIN', 20)),
            'max': float(os.getenv('ALERT_HUMIDITY_MAX', 90)),
            'message': 'Kelembaban di luar batas normal',
        },
        'gas_level': {
            'min': 0,
            'max': float(os.getenv('ALERT_GAS_MAX', 70)),
            'message': 'Level gas berbahaya',
        },
    }

    # ==========================================
    # JSON
    # ==========================================
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False

    @classmethod
    def validate(cls):
        """Validasi config wajib. Raise ValueError jika ada yang salah."""
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

        # Validasi port
        if not (1 <= cls.PORT <= 65535):
            errors.append(f"PORT harus antara 1-65535, dapat: {cls.PORT}")

        # Validasi timeout
        if cls.OFFLINE_TIMEOUT < 60:
            errors.append("OFFLINE_TIMEOUT minimal 60 detik")
        if cls.CHECK_INTERVAL < 10:
            errors.append("CHECK_INTERVAL minimal 10 detik")

        if errors:
            raise ValueError(
                "\n\n❌ CONFIGURATION ERRORS:\n" +
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
    """Ambil config berdasarkan FLASK_ENV"""
    env = os.getenv('FLASK_ENV', 'production').lower()

    if env == 'development':
        return DevelopmentConfig
    elif env == 'testing':
        return TestingConfig
    return ProductionConfig