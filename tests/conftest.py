"""Fixture bersama untuk tes NEXUS IoT.

Env harus di-set SEBELUM `app` diimpor, karena app/__init__.py memvalidasi
konfigurasi saat import.
"""
import os
import re
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='nexus-tests-')
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only-32chars-minimum'
os.environ['IOT_USERNAME'] = 'admin'
os.environ['IOT_PASSWORD'] = 'AdminPass-12345'
os.environ['DB_PATH'] = os.path.join(_TMP, 'boot.db')
os.environ['LOG_FILE'] = os.path.join(_TMP, 'nexus.log')
os.environ['NEXUS_LOCK_DIR'] = _TMP
os.environ['BACKUP_DIR'] = os.path.join(_TMP, 'backup')

# app/config.py memanggil load_dotenv() saat import. Tanpa ini, file .env
# sungguhan di root repo ikut terbaca dan test yang bergantung pada "env var
# tidak di-set" ikut gagal (mis. test SESSION_COOKIE_SECURE vs ENABLE_HSTS).
# Test harus hermetik: hanya env yang disetel di sini/oleh monkeypatch yang berlaku.
os.environ['PYTHON_DOTENV_DISABLED'] = '1'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.database import get_db_context  # noqa: E402
from app.utils import generate_api_key, hash_api_key  # noqa: E402
from app import alerts as alerts_module  # noqa: E402


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / 'iot.db')
    monkeypatch.setattr(Config, 'DB_PATH', path)
    return path


@pytest.fixture
def app(db_path):
    alerts_module.invalidate_global_rules_cache()
    application = create_app(config_override={
        'TESTING': True,
        'RATELIMIT_ENABLED': False,
        'WTF_CSRF_ENABLED': False,
        'SESSION_COOKIE_SECURE': False,
    })
    yield application
    alerts_module.invalidate_global_rules_cache()


def _make_user(username, password, is_admin):
    with get_db_context() as conn:
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, display_name, is_admin) '
            'VALUES (?, ?, ?, ?)',
            (username, generate_password_hash(password), username, 1 if is_admin else 0),
        )
        conn.commit()
        return cur.lastrowid


def _login_session(client, user_id, username):
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['user_id'] = user_id
        sess['username'] = username
        sess['last_activity'] = time.time()
        sess.permanent = True


@pytest.fixture
def admin_client(app):
    uid = _make_user('adm1', 'AdminPass-12345', True)
    client = app.test_client()
    _login_session(client, uid, 'adm1')
    return client


@pytest.fixture
def user_client(app):
    uid = _make_user('usr1', 'UserPass-12345', False)
    client = app.test_client()
    _login_session(client, uid, 'usr1')
    return client


@pytest.fixture
def anon_client(app):
    return app.test_client()


@pytest.fixture
def make_device(app):
    """Buat device langsung di DB; return API key (plain)."""
    def _make(device_id='dev-1', device_name='Device 1', device_type='ESP32',
              alert_rules_json=None, expected_interval=60, offline_timeout=900):
        api_key = generate_api_key()
        with get_db_context() as conn:
            conn.execute(
                'INSERT INTO devices (device_id, device_name, device_type, '
                'api_key, api_key_hash, alert_rules, expected_interval, offline_timeout) '
                'VALUES (?, ?, ?, NULL, ?, ?, ?, ?)',
                (device_id, device_name, device_type, hash_api_key(api_key),
                 alert_rules_json, expected_interval, offline_timeout),
            )
            conn.commit()
        return api_key
    return _make


def csrf_token(client):
    """Ambil token CSRF dari halaman login (untuk app dengan CSRF aktif)."""
    html = client.get('/login').get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html) or \
        re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
    return m.group(1) if m else ''


def post_data(client, device_id, api_key, data, sensor_type='sensor'):
    return client.post('/api/v1/data', json={
        'device_id': device_id,
        'api_key': api_key,
        'sensor_type': sensor_type,
        'data': data,
    })


def active_alert_types(device_id):
    with get_db_context() as conn:
        rows = conn.execute(
            'SELECT alert_type FROM alerts WHERE device_id = ? AND is_active = 1',
            (device_id,),
        ).fetchall()
    return {r['alert_type'] for r in rows}
