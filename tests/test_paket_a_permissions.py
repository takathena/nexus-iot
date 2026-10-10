"""Paket A — peran user dan izin absensi (A.5).

Skenario utama:
- migrasi v18 dan akun superadmin
- user tanpa izin ditolak (403 PERMISSION_DENIED) di semua permukaan absensi
- izin berlaku pada request berikutnya (grant dan revoke)
- attendance.manage mencakup attendance.view
- admin implisit punya semua izin
- aturan peran: admin tidak mengubah admin lain, superadmin tidak bisa dihapus/diturunkan
- system/info menyembunyikan jumlah absensi tanpa izin
- chat AI tidak menerima dan tidak menjalankan tool absensi tanpa izin
- perubahan peran dan izin tercatat di audit log
"""
import time

from werkzeug.security import generate_password_hash

from app.database import get_db_context


def _mk(username, is_admin=False, role='user'):
    with get_db_context() as conn:
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, display_name, is_admin, role) '
            'VALUES (?, ?, ?, ?, ?)',
            (username, generate_password_hash('Pass-123456'), username,
             1 if is_admin else 0, role),
        )
        conn.commit()
        return cur.lastrowid


def _client_for(app, uid, username):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['user_id'] = uid
        sess['username'] = username
        sess['last_activity'] = time.time()
        sess.permanent = True
    return client


def _superadmin(app):
    uid = _mk('root1', is_admin=True, role='superadmin')
    return _client_for(app, uid, 'root1'), uid


def _plain_user(app, name='staf1'):
    uid = _mk(name)
    return _client_for(app, uid, name), uid


def _denied(resp):
    body = resp.get_json()
    return resp.status_code == 403 and body.get('code') == 'PERMISSION_DENIED'


ATTENDANCE_GETS = [
    '/api/v1/attendance', '/api/v1/attendance/report', '/api/v1/attendance/stats',
    '/api/v1/attendance/today', '/api/v1/attendance/unregistered',
    '/api/v1/attendance/last-unknown', '/api/v1/attendance/export', '/api/v1/cardholders',
]


# ---------- Migrasi dan akun awal ----------

def test_seed_admin_is_superadmin_and_no_permissions_granted(app):
    with get_db_context() as conn:
        row = conn.execute("SELECT role FROM users WHERE username = 'admin'").fetchone()
        assert row is not None and row['role'] == 'superadmin'
        count = conn.execute('SELECT COUNT(*) FROM user_permissions').fetchone()[0]
    assert count == 0


def test_me_reports_role_and_permissions(app):
    client, _ = _plain_user(app)
    body = client.get('/api/v1/users/me').get_json()['user']
    assert body['role'] == 'user'
    assert body['permissions'] == []
    sa, _ = _superadmin(app)
    body = sa.get('/api/v1/users/me').get_json()['user']
    assert body['role'] == 'superadmin'
    assert set(body['permissions']) == {'attendance.view', 'attendance.manage'}


# ---------- Penolakan tanpa izin ----------

def test_user_without_permission_is_denied_on_all_attendance_routes(app):
    client, _ = _plain_user(app)
    for path in ATTENDANCE_GETS:
        resp = client.get(path)
        assert _denied(resp), path


def test_user_without_permission_cannot_write_cardholders(app):
    client, _ = _plain_user(app)
    add = client.post('/api/v1/cardholders', json={'uid': 'AABBCCDD', 'nama': 'X'})
    assert _denied(add)
    assert _denied(client.delete('/api/v1/cardholders/AABBCCDD'))


# ---------- Grant, revoke, dan implikasi ----------

def test_grant_view_takes_effect_on_next_request_and_revoke_removes_it(app):
    admin, _ = _superadmin(app)
    client, uid = _plain_user(app, 'staf2')
    assert _denied(client.get('/api/v1/attendance'))

    r = admin.put(f'/api/v1/users/{uid}/permissions', json={'attendance_view': True})
    assert r.status_code == 200
    assert r.get_json()['permissions'] == ['attendance.view']
    assert client.get('/api/v1/attendance').status_code == 200

    r = admin.put(f'/api/v1/users/{uid}/permissions', json={'attendance_view': False})
    assert r.status_code == 200
    assert _denied(client.get('/api/v1/attendance'))


def test_manage_implies_view(app):
    admin, _ = _superadmin(app)
    client, uid = _plain_user(app, 'staf3')
    r = admin.put(f'/api/v1/users/{uid}/permissions', json={'attendance_manage': True})
    assert r.get_json()['permissions'] == ['attendance.manage', 'attendance.view']
    assert client.get('/api/v1/attendance').status_code == 200
    assert not _denied(client.post('/api/v1/cardholders', json={'uid': 'AABBCCDD', 'nama': 'Y'}))


def test_admin_has_all_permissions_implicitly(app, admin_client):
    assert admin_client.get('/api/v1/attendance').status_code == 200
    assert admin_client.get('/api/v1/users/me').get_json()['user']['permissions']


def test_cannot_set_explicit_permissions_on_privileged_user(app):
    admin, _ = _superadmin(app)
    other_admin = _mk('adm9', is_admin=True, role='admin')
    r = admin.put(f'/api/v1/users/{other_admin}/permissions', json={'attendance_view': True})
    assert r.status_code == 400


def test_permissions_endpoints_are_admin_only(app):
    admin, _ = _superadmin(app)
    client, uid = _plain_user(app, 'staf4')
    assert client.get(f'/api/v1/users/{uid}/permissions').status_code == 403
    assert client.put(f'/api/v1/users/{uid}/permissions', json={'attendance_view': True}).status_code == 403
    assert admin.get(f'/api/v1/users/{uid}/permissions').status_code == 200


# ---------- Aturan peran ----------

def test_plain_admin_cannot_change_another_admin(app):
    _superadmin(app)
    adm2_id = _mk('adm2', is_admin=True, role='admin')
    adm2 = _client_for(app, adm2_id, 'adm2')
    sa_id = _mk('root2', is_admin=True, role='superadmin')
    r = adm2.put(f'/api/v1/users/{sa_id}', json={'display_name': 'x'})
    assert r.status_code == 403


def test_plain_admin_cannot_grant_admin_role(app):
    _superadmin(app)
    adm2_id = _mk('adm3', is_admin=True, role='admin')
    adm2 = _client_for(app, adm2_id, 'adm3')
    target = _mk('staf5')
    r = adm2.put(f'/api/v1/users/{target}', json={'role': 'admin'})
    assert r.status_code == 403


def test_superadmin_cannot_be_deleted_or_demoted(app):
    sa, sa_id = _superadmin(app)
    other_super_admin_id = _mk('adm4', is_admin=True, role='admin')
    adm4 = _client_for(app, other_super_admin_id, 'adm4')
    assert adm4.delete(f'/api/v1/users/{sa_id}').status_code == 403
    assert sa.put(f'/api/v1/users/{sa_id}', json={'role': 'user'}).status_code == 403


def test_superadmin_can_promote_and_demote_regular_admin(app):
    sa, _ = _superadmin(app)
    target = _mk('staf6')
    assert sa.put(f'/api/v1/users/{target}', json={'role': 'admin'}).status_code == 200
    with get_db_context() as conn:
        row = conn.execute('SELECT role, is_admin FROM users WHERE id = ?', (target,)).fetchone()
    assert row['role'] == 'admin' and row['is_admin'] == 1
    assert sa.put(f'/api/v1/users/{target}', json={'role': 'user'}).status_code == 200
    with get_db_context() as conn:
        row = conn.execute('SELECT role, is_admin FROM users WHERE id = ?', (target,)).fetchone()
    assert row['role'] == 'user' and row['is_admin'] == 0


def test_cannot_change_own_role_without_superadmin(app):
    _superadmin(app)
    adm2_id = _mk('adm5', is_admin=True, role='admin')
    adm2 = _client_for(app, adm2_id, 'adm5')
    r = adm2.put(f'/api/v1/users/{adm2_id}', json={'role': 'user'})
    assert r.status_code == 403


# ---------- system/info ----------

def test_system_info_hides_attendance_counts_without_permission(app):
    client, _ = _plain_user(app, 'staf7')
    info = client.get('/api/v1/system/info').get_json()['info']
    assert 'attendance_count' not in info and 'cardholder_count' not in info

    admin, _ = _superadmin(app)
    info = admin.get('/api/v1/system/info').get_json()['info']
    assert 'attendance_count' in info and 'cardholder_count' in info


# ---------- Chat AI ----------

ATT_TOOLS = {'get_present_today', 'get_absent_today', 'get_attendance_range', 'get_cardholders'}


def _tool_names_for(app, uid):
    import app.chat as chat
    with app.test_request_context():
        from flask import session
        session['user_id'] = uid
        session['logged_in'] = True
        can_att, tools = chat._current_chat_permissions()
        names = {t['function']['name'] for t in tools}
        return can_att, names


def test_chat_tools_exclude_attendance_without_permission(app):
    uid = _mk('staf8')
    can_att, names = _tool_names_for(app, uid)
    assert can_att is False
    assert not (names & ATT_TOOLS)
    assert 'get_devices_status' in names


def test_chat_tools_include_attendance_with_permission(app):
    uid = _mk('staf9')
    with get_db_context() as conn:
        conn.execute("INSERT INTO user_permissions (user_id, permission) VALUES (?, 'attendance.view')", (uid,))
        conn.commit()
    can_att, names = _tool_names_for(app, uid)
    assert can_att is True
    assert ATT_TOOLS <= names


def test_chat_refuses_attendance_tool_call_without_permission(app):
    import app.chat as chat
    uid = _mk('staf10')
    with app.test_request_context():
        from flask import session
        session['user_id'] = uid
        session['logged_in'] = True
        _, args, result = chat._run_tool_call({
            'function': {'name': 'get_cardholders', 'arguments': '{}'}
        })
    assert 'error' in result
    assert 'karyawan' not in result and 'total' not in result


# ---------- Audit ----------

def test_role_and_permission_changes_are_audited(app):
    sa, _ = _superadmin(app)
    target = _mk('staf11')
    sa.put(f'/api/v1/users/{target}', json={'role': 'moderator'})
    sa.put(f'/api/v1/users/{target}/permissions', json={'attendance_manage': True})
    with get_db_context() as conn:
        actions = [r['action'] for r in conn.execute(
            "SELECT action FROM audit_log WHERE detail LIKE ?", (f'%id={target}%',)).fetchall()]
    assert 'user.role' in actions
    assert 'user.permissions' in actions
