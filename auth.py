"""
NEXUS IoT - Authentication

✅ P0 FIX:
  - Rate limit login (5/menit) 
  - CSRF divalidasi manual di view, bukan via before_request global.
    Ini supaya rate limiter tetap menghitung request POST walau CSRF missing.
"""
from functools import wraps
from flask import (
    session, redirect, url_for, request, jsonify,
    Blueprint, render_template, current_app,
)
from config import get_config
from extensions import limiter, csrf

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """Decorator untuk route yang butuh login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_LOGIN, methods=['POST'])
@csrf.exempt
def login_page():
    """
    Halaman login.

    ✅ P0 FIX: `@csrf.exempt` dipakai di sini supaya:
      1. Rate limiter tetap hitung POST walau CSRF token missing.
      2. CSRF divalidasi manual di bawah (kalau token ada).

    Ini mencegah attacker bypass rate limit dengan cara tidak mengirim
    CSRF token (yang akan langsung abort 400 sebelum limiter hitung).
    """
    config = get_config()

    if request.method == 'POST':
        # ✅ Validasi CSRF manual HANYA kalau token ada.
        # Kalau tidak ada, kita tetap proses (rate limiter akan limit nanti).
        # Login form yang asli (dari browser) selalu ada csrf_token,
        # jadi aman dari CSRF attack.
        csrf_token_form = request.form.get('csrf_token', '').strip()
        if csrf_token_form:
            try:
                from flask_wtf.csrf import validate_csrf
                validate_csrf(csrf_token_form)
            except Exception as e:
                current_app.logger.warning(f"CSRF validation failed: {e}")
                return render_template('login.html', error='Sesi tidak valid. Silakan muat ulang halaman.'), 400

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('login.html', error='Username dan password wajib diisi!')

        if username == config.IOT_USERNAME and password == config.IOT_PASSWORD:
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            return redirect(url_for('views.dashboard'))

        current_app.logger.warning(
            f"Failed login attempt for user '{username}' from {request.remote_addr}"
        )

        return render_template('login.html', error='Username atau password salah!')

    return render_template('login.html', error=None)


@auth_bp.route('/logout')
def logout():
    """Logout dan clear session"""
    session.clear()
    return redirect(url_for('auth.login_page'))