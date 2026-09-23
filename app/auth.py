"""
NEXUS IoT - Authentication
"""
from functools import wraps
from flask import (
    session, redirect, url_for, request, jsonify,
    Blueprint, render_template, current_app,
)
from flask_wtf.csrf import validate_csrf
from app.config import get_config
from app.extensions import limiter

auth_bp = Blueprint('auth', __name__)


def login_required(f):
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
def login_page():
    config = get_config()

    if request.method == 'POST':
        # ✅ CSRF wajib — tidak ada bypass
        csrf_token_form = request.form.get('csrf_token', '').strip()
        if not csrf_token_form:
            return render_template('login.html', error='Sesi tidak valid. Muat ulang halaman.'), 400

        try:
            validate_csrf(csrf_token_form)
        except Exception as e:
            current_app.logger.warning(f"CSRF validation failed: {e}")
            return render_template('login.html', error='Sesi tidak valid. Muat ulang halaman.'), 400

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
    session.clear()
    return redirect(url_for('auth.login_page'))