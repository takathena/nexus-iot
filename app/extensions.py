"""
NEXUS IoT - Flask Extensions
"""
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.config import get_config

_config = get_config()

cors = CORS()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    strategy="fixed-window",
    default_limits=[_config.RATE_LIMIT_DEFAULT],
)