"""C2 — semua route tulis harus admin-only (backend sumber kebenaran)."""
import pytest

from app.database import get_db_context

WRITE_ROUTES = [
    ('POST', '/api/v1/devices', {'device_id': 'new-x', 'device_name': 'Baru'}),
    ('PUT', '/api/v1/devices/dev-x', {'device_name': 'Diubah'}),
    ('DELETE', '/api/v1/devices/dev-x', None),
    ('POST', '/api/v1/devices/dev-x/regenerate-key', None),
    ('PUT', '/api/v1/devices/dev-x/alert-rules',
     {'temperature': {'healthy': {'min': 0, 'max': 30}}}),
    ('DELETE', '/api/v1/devices/dev-x/alert-rules', None),
    ('POST', '/api/v1/devices/bulk-import',
     {'devices': [{'device_id': 'bulk-x', 'device_name': 'B'}]}),
    ('POST', '/api/v1/cardholders', {'uid': 'AABBCCDD', 'nama': 'Budi'}),
    ('DELETE', '/api/v1/cardholders/CARD0001', None),
    ('POST', '/api/v1/notifications/test', {}),
    ('POST', '/api/v1/notifications/test-channel', {'channel': 'telegram'}),
]


@pytest.fixture(autouse=True)
def _stub_notifier(monkeypatch):
    # Tes tidak boleh menyentuh jaringan.
    monkeypatch.setattr('app.api.send_test_notification',
                        lambda: {'telegram': {'success': True}})


@pytest.fixture
def seeded(make_device):
    make_device('dev-x', 'Device X')
    with get_db_context() as conn:
        conn.execute("INSERT INTO cardholders (uid, nama) VALUES ('CARD0001', 'Ani')")
        conn.commit()


def _call(client, method, path, body):
    kwargs = {'json': body} if body is not None else {}
    return client.open(path, method=method, **kwargs)


@pytest.mark.parametrize('method,path,body', WRITE_ROUTES)
def test_non_admin_gets_403(user_client, seeded, method, path, body):
    resp = _call(user_client, method, path, body)
    assert resp.status_code == 403
    assert resp.get_json()['success'] is False


@pytest.mark.parametrize('method,path,body', WRITE_ROUTES)
def test_admin_is_not_blocked(admin_client, seeded, method, path, body):
    resp = _call(admin_client, method, path, body)
    assert resp.status_code != 403
    assert resp.status_code < 500


@pytest.mark.parametrize('method,path,body', WRITE_ROUTES)
def test_anonymous_gets_401(anon_client, seeded, method, path, body):
    assert _call(anon_client, method, path, body).status_code == 401


def test_non_admin_cannot_change_or_delete_device(user_client, seeded):
    assert user_client.put('/api/v1/devices/dev-x',
                           json={'device_name': 'Diretas'}).status_code == 403
    assert user_client.delete('/api/v1/devices/dev-x').status_code == 403
    assert user_client.post('/api/v1/devices/dev-x/regenerate-key').status_code == 403

    with get_db_context() as conn:
        row = conn.execute(
            'SELECT device_name, api_key_hash FROM devices WHERE device_id = ?', ('dev-x',)
        ).fetchone()
        card = conn.execute("SELECT uid FROM cardholders WHERE uid = 'CARD0001'").fetchone()
    assert row is not None
    assert row['device_name'] == 'Device X'
    assert card is not None


def test_non_admin_key_not_rotated(user_client, seeded):
    with get_db_context() as conn:
        before = conn.execute(
            'SELECT api_key_hash FROM devices WHERE device_id = ?', ('dev-x',)
        ).fetchone()['api_key_hash']
    user_client.post('/api/v1/devices/dev-x/regenerate-key')
    with get_db_context() as conn:
        after = conn.execute(
            'SELECT api_key_hash FROM devices WHERE device_id = ?', ('dev-x',)
        ).fetchone()['api_key_hash']
    assert before == after


def test_non_admin_can_still_read(user_client, seeded):
    assert user_client.get('/api/v1/devices').status_code == 200
    assert user_client.get('/api/v1/devices/dev-x').status_code == 200
    assert user_client.get('/api/v1/cardholders').status_code == 200
    assert user_client.get('/api/v1/devices/dev-x/alert-rules').status_code == 200
    assert user_client.get('/api/v1/users/me').status_code == 200


def test_users_me_reports_is_admin(admin_client, user_client):
    assert admin_client.get('/api/v1/users/me').get_json()['user']['is_admin'] is True
    assert user_client.get('/api/v1/users/me').get_json()['user']['is_admin'] is False
