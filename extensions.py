"""
NEXUS IoT - Flask Extensions
Inisialisasi semua extension di sini untuk avoid circular import.
"""
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

cors = CORS()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    strategy="fixed-window"
)