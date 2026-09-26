"""
NEXUS IoT - Authentication (Multi-User)
"""
import time
from functools import wraps
from flask import (
    session, redirect, url_for, request, jsonify,
    Blueprint, render_template, current_app,
)
from flask_wtf.csrf import validate_csrf, generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash
from app.config import get_config
from app.extensions import limiter
from app.database import get_db_context

auth_bp = Blueprint('auth', __name__)


def _is_api_polling_request():
    """Return True kalau request ini adalah polling API (bukan interaksi user).

    Polling API tidak boleh memperpanjang sesi — kalau tidak, idle timeout
    tidak akan pernah aktif selama tab terbuka.
    """
    method = request.method.upper()
    path = request.path or ''

    if method != 'GET':
        return False

    # Halaman HTML (dashboard, device detail, dsb) => interaksi user
    if not path.startswith('/api/'):
        return False

    # Endpoint API yang tidak boleh memperpanjang sesi
    polling_prefixes = (
        '/api/v1/dashboard',
        '/api/v1/devices',
        '/api/v1/alerts',
        '/api/v1/attendance',
        '/api/v1/cardholders',
        '/api/v1/dashboards',
        '/api/v1/widgets',
        '/api/v1/analytics-tabs',
        '/api/v1/system',
        '/api/v1/notifications',
    )
    return path.startswith(polling_prefixes)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            return redirect(url_for('auth.login_page'))

        config = get_config()
        idle_minutes = config.SESSION_IDLE_TIMEOUT_MINUTES
        now_ts = time.time()
        last_activity = session.get('last_activity')

        if last_activity and idle_minutes > 0:
            idle_seconds = now_ts - last_activity
            if idle_seconds > idle_minutes * 60:
                session.clear()
                if request.path.startswith('/api/'):
                    return jsonify({
                        'success': False,
                        'error': 'Session expired (idle)',
                        'code': 'SESSION_IDLE'
                    }), 401
                return redirect(url_for('auth.login_page'))

        # ✅ FIX: refresh last_activity hanya pada aksi user, bukan polling API
        if not _is_api_polling_request():
            session['last_activity'] = now_ts

        return f(*args, **kwargs)
    return decorated_function


def _authenticate(username, password):
    config = get_config()

    if config.IOT_USERNAME and config.IOT_PASSWORD:
        if username == config.IOT_USERNAME and password == config.IOT_PASSWORD:
            with get_db_context() as conn:
                user = conn.execute(
                    'SELECT id, password_hash FROM users WHERE username = ?',
                    (username,)
                ).fetchone()

                if user:
                    try:
                        if not check_password_hash(user['password_hash'], password):
                            new_hash = generate_password_hash(password)
                            conn.execute(
                                'UPDATE users SET password_hash = ? WHERE id = ?',
                                (new_hash, user['id'])
                            )
                            conn.commit()
                            current_app.logger.info(
                                f"Password hash synced for user '{username}'"
                            )
                    except Exception as e:
                        current_app.logger.error(f"Password sync failed: {e}")

                    return user['id']

                try:
                    pw_hash = generate_password_hash(password)
                    cur = conn.execute('''
                        INSERT INTO users (username, password_hash, display_name, is_admin)
                        VALUES (?, ?, 'Administrator', 1)
                    ''', (username, pw_hash))
                    conn.commit()
                    return cur.lastrowid
                except Exception as e:
                    current_app.logger.error(f"Gagal create user: {e}")
                    return None

    with get_db_context() as conn:
        user = conn.execute(
            'SELECT id, password_hash FROM users WHERE username = ?', (username,)
        ).fetchone()

    if user and check_password_hash(user['password_hash'], password):
        return user['id']

    return None


def ensure_user_dashboard(user_id, username):
    with get_db_context() as conn:
        existing = conn.execute(
            '''SELECT id FROM dashboards
               WHERE user_id = ?
               ORDER BY is_default DESC, id ASC LIMIT 1''',
            (user_id,)
        ).fetchone()

        if existing:
            return existing['id']

        orphan = conn.execute(
            '''SELECT id FROM dashboards
               WHERE user_id IS NULL
               ORDER BY is_default DESC, id ASC LIMIT 1'''
        ).fetchone()

        if orphan:
            conn.execute(
                'UPDATE dashboards SET user_id = ? WHERE user_id IS NULL',
                (user_id,)
            )
            conn.commit()
            return orphan['id']

        slug = f"u{user_id}-default"
        cur = conn.execute('''
            INSERT INTO dashboards (slug, name, description, icon, is_default, user_id)
            VALUES (?, 'Dashboard Utama', 'Dashboard bawaan', 'fa-chart-pie', 1, ?)
        ''', (slug, user_id))
        conn.commit()
        return cur.lastrowid


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_LOGIN, methods=['POST'])
def login_page():
    config = get_config()

    if request.method == 'POST':
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

        user_id = _authenticate(username, password)

        if user_id:
            session.clear()
            session['logged_in'] = True
            session['user_id'] = user_id
            session['username'] = username
            session['last_activity'] = time.time()
            session.permanent = True

            generate_csrf()

            try:
                ensure_user_dashboard(user_id, username)
            except Exception as e:
                current_app.logger.error(f"ensure_user_dashboard failed: {e}")

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