"""
NEXUS IoT - Authentication
"""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify, Blueprint, render_template
from config import get_config

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """Decorator untuk route yang butuh login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # Jika request API, return 401 JSON
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    """Halaman login"""
    config = get_config()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validasi input
        if not username or not password:
            return render_template('login.html', error='Username dan password wajib diisi!')

        # Cek credential
        if username == config.IOT_USERNAME and password == config.IOT_PASSWORD:
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            return redirect(url_for('views.dashboard'))

        # Log percobaan login gagal
        from flask import current_app
        current_app.logger.warning(f"Failed login attempt for user '{username}' from {request.remote_addr}")

        return render_template('login.html', error='Username atau password salah!')

    return render_template('login.html', error=None)


@auth_bp.route('/logout')
def logout():
    """Logout dan clear session"""
    session.clear()
    return redirect(url_for('auth.login_page'))