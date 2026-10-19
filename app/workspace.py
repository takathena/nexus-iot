"""
NEXUS IoT - Workspace (dashboard = ruang kerja)

Satu sumber kebenaran untuk:
  - peran per dashboard (owner / editor / viewer) + admin yang selalu bebas,
  - lingkup data (scope) sebuah request: dashboard mana yang sedang dilihat,
  - penyimpanan token bot Telegram per dashboard (terenkripsi),
  - audit log aksi sensitif.

Aturan akses:
  owner  : pemilik dashboard (dashboards.user_id). Boleh semuanya, termasuk
           mengatur anggota, Telegram, dan menghapus dashboard.
  editor : anggota. Boleh menambah/ubah/hapus perangkat, widget, tab, kartu.
  viewer : anggota. Hanya melihat.
  admin  : (users.is_admin) diperlakukan sebagai owner di semua dashboard.
"""
import base64
import hashlib
import logging

from flask import g, jsonify, request, session

from app.database import get_wib_time

logger = logging.getLogger('nexus')

ROLE_RANK = {'viewer': 1, 'editor': 2, 'owner': 3}
MEMBER_ROLES = ('viewer', 'editor')


# ==========================================
# USER / ADMIN
# ==========================================
def current_user_id():
    return session.get('user_id')


def is_admin_user(conn, user_id):
    if not user_id:
        return False
    cache = g.setdefault('_nx_admin_cache', {})
    if user_id not in cache:
        row = conn.execute(
            'SELECT is_admin FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        cache[user_id] = bool(row and row['is_admin'])
    return cache[user_id]


# ==========================================
# PERAN
# ==========================================
def get_dashboard_role(conn, dashboard_id, user_id):
    """Return 'owner' | 'editor' | 'viewer' | None."""
    if not user_id or dashboard_id is None:
        return 'owner' if (user_id and is_admin_user(conn, user_id)) else None
    if is_admin_user(conn, user_id):
        return 'owner'
    row = conn.execute(
        'SELECT user_id FROM dashboards WHERE id = ?', (dashboard_id,)
    ).fetchone()
    if not row:
        return None
    if row['user_id'] == user_id:
        return 'owner'
    m = conn.execute(
        'SELECT role FROM dashboard_members WHERE dashboard_id = ? AND user_id = ?',
        (dashboard_id, user_id)
    ).fetchone()
    return m['role'] if m else None


def role_allows(role, minimum):
    return bool(role) and ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]


def accessible_dashboard_ids(conn, user_id, minimum='viewer'):
    """Daftar id dashboard yang boleh diakses dengan peran minimal.

    Return None bila admin (artinya: semua dashboard, termasuk perangkat
    yang belum punya dashboard).
    """
    if is_admin_user(conn, user_id):
        return None
    ids = set()
    for r in conn.execute(
        'SELECT id FROM dashboards WHERE user_id = ?', (user_id,)
    ).fetchall():
        ids.add(r['id'])
    for r in conn.execute(
        'SELECT dashboard_id, role FROM dashboard_members WHERE user_id = ?', (user_id,)
    ).fetchall():
        if role_allows(r['role'], minimum):
            ids.add(r['dashboard_id'])
    return sorted(ids)


# ==========================================
# SCOPE REQUEST
# ==========================================
def resolve_scope(conn, minimum='viewer'):
    """Tentukan lingkup data request ini.

    Frontend mengirim header `X-Dashboard-Id` (atau query `dashboard_id`).
      - angka  : hanya dashboard itu (harus punya peran >= minimum)
      - 'all'/kosong : semua dashboard yang boleh diakses user
                       (admin: semua perangkat, termasuk yang belum dimiliki)

    Return dict: user_id, is_admin, dashboard_ids (list | None=semua),
                 dashboard_id (int | None), error (None | (msg, status)).
    """
    user_id = current_user_id()
    admin = is_admin_user(conn, user_id)
    raw = request.headers.get('X-Dashboard-Id') or request.args.get('dashboard_id')
    raw = (raw or '').strip().lower()

    scope = {
        'user_id': user_id, 'is_admin': admin,
        'dashboard_ids': None, 'dashboard_id': None, 'error': None,
    }

    if raw in ('', 'all', 'null', 'undefined', '0'):
        scope['dashboard_ids'] = accessible_dashboard_ids(conn, user_id, minimum)
        return scope

    try:
        did = int(raw)
    except ValueError:
        scope['error'] = ('dashboard_id tidak valid', 400)
        return scope

    role = get_dashboard_role(conn, did, user_id)
    if role is None:
        scope['error'] = ('Dashboard tidak ditemukan', 404)
        return scope
    if not role_allows(role, minimum):
        scope['error'] = ('Peran Anda di dashboard ini tidak cukup untuk aksi tersebut', 403)
        return scope

    scope['dashboard_ids'] = [did]
    scope['dashboard_id'] = did
    return scope


def scope_error_response(scope):
    msg, code = scope['error']
    return jsonify({'success': False, 'error': msg}), code


def dashboard_in_sql(scope, column='dashboard_id'):
    """Potongan SQL: `<column> IN (...)` untuk kolom yang berisi dashboard id."""
    ids = scope['dashboard_ids']
    if ids is None:
        return '1=1', []
    if not ids:
        return '0=1', []
    return f"{column} IN ({','.join('?' * len(ids))})", list(ids)


def device_in_sql(scope, column='device_id'):
    """Potongan SQL: `<column> IN (perangkat dalam scope)` untuk kolom device_id."""
    ids = scope['dashboard_ids']
    if ids is None:
        return '1=1', []
    if not ids:
        return '0=1', []
    ph = ','.join('?' * len(ids))
    return (f"{column} IN (SELECT device_id FROM devices WHERE dashboard_id IN ({ph}))",
            list(ids))


# ==========================================
# AKSES PER PERANGKAT / KARTU
# ==========================================
def device_allowed(conn, scope, device_id):
    """True bila perangkat termasuk dalam scope request (dashboard terpilih / yang boleh diakses)."""
    ids = scope['dashboard_ids']
    if ids is None:
        return True
    if not ids:
        return False
    row = conn.execute(
        f"SELECT 1 FROM devices WHERE device_id = ? AND dashboard_id IN ({','.join('?' * len(ids))})",
        [device_id] + list(ids)
    ).fetchone()
    return row is not None


def device_role(conn, device_row, user_id):
    """Peran user pada dashboard pemilik perangkat. Perangkat tanpa dashboard = admin saja."""
    if device_row['dashboard_id'] is None:
        return 'owner' if is_admin_user(conn, user_id) else None
    return get_dashboard_role(conn, device_row['dashboard_id'], user_id)


def load_device(conn, device_id, minimum='viewer', columns='*'):
    """Ambil perangkat + cek peran.

    Return (row, None) bila boleh, atau (None, (response, status)).
      - perangkat tidak ada / tidak terlihat -> 404
      - terlihat tapi peran kurang          -> 403
    """
    user_id = current_user_id()
    cols = columns if 'dashboard_id' in columns or columns == '*' else columns + ', dashboard_id'
    row = conn.execute(
        f'SELECT {cols} FROM devices WHERE device_id = ?', (device_id,)
    ).fetchone()
    if not row:
        return None, (jsonify({'success': False, 'error': 'Device not found'}), 404)

    role = device_role(conn, row, user_id)
    if role is None:
        return None, (jsonify({'success': False, 'error': 'Device not found'}), 404)
    if not role_allows(role, minimum):
        return None, (jsonify({
            'success': False,
            'error': 'Anda tidak punya izin untuk mengubah perangkat ini',
        }), 403)
    return row, None


def pick_write_dashboard(conn, scope, requested_id=None, minimum='editor'):
    """Tentukan dashboard tujuan untuk membuat sesuatu (perangkat, kartu).

    Urutan: id eksplisit -> dashboard yang sedang dipilih -> dashboard default user.
    Return (dashboard_id, None) atau (None, (response, status)).
    """
    user_id = scope['user_id']
    did = None
    if requested_id not in (None, '', 0, '0'):
        try:
            did = int(requested_id)
        except (ValueError, TypeError):
            return None, (jsonify({'success': False, 'error': 'dashboard_id tidak valid'}), 400)
    elif scope['dashboard_id']:
        did = scope['dashboard_id']
    else:
        row = conn.execute(
            'SELECT id FROM dashboards WHERE user_id = ? '
            'ORDER BY is_default DESC, id ASC LIMIT 1', (user_id,)
        ).fetchone()
        did = row['id'] if row else None

    if did is None:
        if is_admin_user(conn, user_id):
            # Admin tanpa dashboard: data dibiarkan "belum dimiliki" (hanya terlihat admin).
            return None, None
        return None, (jsonify({
            'success': False,
            'error': 'Anda belum punya dashboard yang boleh diubah',
        }), 403)

    exists = conn.execute('SELECT id FROM dashboards WHERE id = ?', (did,)).fetchone()
    if not exists:
        return None, (jsonify({'success': False, 'error': 'Dashboard tidak ditemukan'}), 404)

    role = get_dashboard_role(conn, did, user_id)
    if role is None:
        return None, (jsonify({'success': False, 'error': 'Dashboard tidak ditemukan'}), 404)
    if not role_allows(role, minimum):
        return None, (jsonify({
            'success': False,
            'error': 'Anda hanya boleh melihat dashboard ini (peran viewer)',
        }), 403)
    return did, None


# ==========================================
# TOKEN TELEGRAM (terenkripsi)
# ==========================================
_ENC_PREFIX = 'enc:v1:'


def _fernet():
    from cryptography.fernet import Fernet
    from app.config import get_config
    config = get_config()
    secret = getattr(config, 'TELEGRAM_TOKEN_KEY', None) or config.SECRET_KEY
    if not secret:
        raise RuntimeError('SECRET_KEY / TELEGRAM_TOKEN_KEY belum di-set')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest())
    return Fernet(key)


def encrypt_token(plain):
    return _ENC_PREFIX + _fernet().encrypt(plain.encode('utf-8')).decode('ascii')


def decrypt_token(stored):
    if not stored:
        return ''
    if not stored.startswith(_ENC_PREFIX):
        return stored
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(stored[len(_ENC_PREFIX):].encode('ascii')).decode('utf-8')
    except InvalidToken:
        logger.error('Token Telegram tidak bisa didekripsi (SECRET_KEY berubah?)')
        return ''


def mask_token(plain):
    if not plain:
        return ''
    return '••••' + plain[-4:] if len(plain) > 4 else '••••'


def get_dashboard_telegram(conn, dashboard_id):
    """Konfigurasi Telegram dashboard (token sudah didekripsi) atau None."""
    row = conn.execute(
        'SELECT dashboard_id, bot_token_enc, chat_id, enabled FROM dashboard_telegram '
        'WHERE dashboard_id = ?', (dashboard_id,)
    ).fetchone()
    if not row:
        return None
    return {
        'dashboard_id': row['dashboard_id'],
        'token': decrypt_token(row['bot_token_enc']),
        'chat_id': row['chat_id'] or '',
        'enabled': bool(row['enabled']),
    }


# ==========================================
# AUDIT
# ==========================================
def audit(conn, action, detail=''):
    """Catat aksi sensitif. Gagal mencatat tidak boleh menggagalkan aksinya."""
    try:
        conn.execute(
            'INSERT INTO audit_log (user_id, username, action, detail, ip, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (session.get('user_id'), session.get('username') or '', action,
             str(detail)[:2000], request.remote_addr or '', get_wib_time())
        )
    except Exception as e:
        logger.warning(f'Gagal menulis audit log: {e}')
    logger.warning(f"AUDIT {action} by={session.get('username')} {detail}")

