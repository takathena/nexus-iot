"""
NEXUS IoT - Peran user dan izin granular (Paket A).

Sumber kebenaran tetap di backend. UI hanya menyembunyikan kontrol.

Peran (users.role):
  superadmin  akun awal dari .env. Tidak bisa dihapus, diturunkan, atau diubah peran-nya.
  admin       semua izin. Hanya superadmin yang bisa memberi peran admin.
  moderator   saat ini berperilaku seperti user (lihat dashboard di Paket B).
  user        hanya dashboard yang dimiliki / dibagikan, plus izin eksplisit.

Izin (user_permissions):
  attendance.view    melihat absensi dan daftar kartu
  attendance.manage  mengelola kartu (mencakup attendance.view)

Admin dan superadmin implisit punya semua izin. Migrasi tidak memberi izin ke siapa pun.

Penentuan admin memakai users.is_admin (sudah dipakai backend sejak v1). Peran
di kolom role hanya membedakan superadmin, admin, moderator, dan user. Keduanya
harus selalu konsisten; set_role() menjaga itu.
"""
from functools import wraps

from flask import jsonify, session

from app.database import get_db_context

ROLE_SUPERADMIN = 'superadmin'
ROLE_ADMIN = 'admin'
ROLE_MODERATOR = 'moderator'
ROLE_USER = 'user'
ROLES = (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MODERATOR, ROLE_USER)

PERM_ATTENDANCE_VIEW = 'attendance.view'
PERM_ATTENDANCE_MANAGE = 'attendance.manage'
ALL_PERMISSIONS = (PERM_ATTENDANCE_VIEW, PERM_ATTENDANCE_MANAGE)

# Izin yang otomatis ikut ketika izin kunci diberikan.
IMPLIES = {PERM_ATTENDANCE_MANAGE: {PERM_ATTENDANCE_VIEW}}

PERMISSION_DENIED_ERROR = 'Anda tidak punya izin untuk fitur ini'


def resolve_role(is_admin, stored_role):
    """Peran efektif dari (is_admin, role). is_admin menang untuk admin/superadmin."""
    if is_admin:
        return ROLE_SUPERADMIN if stored_role == ROLE_SUPERADMIN else ROLE_ADMIN
    if stored_role == ROLE_MODERATOR:
        return ROLE_MODERATOR
    return ROLE_USER


def is_privileged(role):
    return role in (ROLE_SUPERADMIN, ROLE_ADMIN)


def get_user_info(conn, user_id):
    """Return dict {id, role, is_admin} atau None bila user tidak ada."""
    if not user_id:
        return None
    row = conn.execute(
        'SELECT id, is_admin, role FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    if not row:
        return None
    return {
        'id': row['id'],
        'role': resolve_role(row['is_admin'], row['role']),
        'is_admin': bool(row['is_admin']),
    }


def explicit_permissions(conn, user_id):
    rows = conn.execute(
        'SELECT permission FROM user_permissions WHERE user_id = ?', (user_id,)
    ).fetchall()
    return {r['permission'] for r in rows}


def effective_permissions(conn, user_id):
    """Semua izin yang berlaku saat ini untuk user (dibaca dari DB setiap kali)."""
    info = get_user_info(conn, user_id)
    if not info:
        return set()
    if is_privileged(info['role']):
        return set(ALL_PERMISSIONS)
    granted = explicit_permissions(conn, user_id)
    result = set(granted)
    for perm in granted:
        result |= IMPLIES.get(perm, set())
    return result & set(ALL_PERMISSIONS)


def has_permission(conn, user_id, permission):
    return permission in effective_permissions(conn, user_id)


def set_user_permissions(conn, user_id, granted_by, view, manage):
    """Ganti izin eksplisit user. manage menyertakan view. Caller harus commit."""
    keep = set()
    if manage:
        keep.add(PERM_ATTENDANCE_MANAGE)
        keep.add(PERM_ATTENDANCE_VIEW)
    elif view:
        keep.add(PERM_ATTENDANCE_VIEW)
    conn.execute('DELETE FROM user_permissions WHERE user_id = ?', (user_id,))
    from app.database import get_wib_time
    now = get_wib_time()
    for perm in sorted(keep):
        conn.execute(
            'INSERT INTO user_permissions (user_id, permission, granted_by, granted_at) '
            'VALUES (?, ?, ?, ?)',
            (user_id, perm, granted_by, now),
        )
    return keep


def permission_denied_response():
    return jsonify({
        'success': False,
        'error': PERMISSION_DENIED_ERROR,
        'code': 'PERMISSION_DENIED',
    }), 403


def permission_required(permission):
    """Batasi route ke pemegang izin. Pasang SETELAH @login_required."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            uid = session.get('user_id')
            with get_db_context() as conn:
                allowed = has_permission(conn, uid, permission)
            if not allowed:
                return permission_denied_response()
            return f(*args, **kwargs)
        return decorated
    return decorator


def role_required(*roles):
    """Batasi route ke peran tertentu. Pasang SETELAH @login_required."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            uid = session.get('user_id')
            with get_db_context() as conn:
                info = get_user_info(conn, uid)
            if not info or info['role'] not in roles:
                return jsonify({
                    'success': False,
                    'error': 'Peran Anda tidak mengizinkan aksi ini',
                    'code': 'ROLE_DENIED',
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
