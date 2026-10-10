"""N3 + N4 — validasi UID, statistik absensi, CSV injection."""
import pytest

from app.database import get_db_context
from app.utils import csv_safe
from tests.conftest import post_data


def _rfid(client, key, uid, device_id='rfid-1'):
    return post_data(client, device_id, key, {'uid': uid}, sensor_type='RFID')


@pytest.fixture
def reader(make_device):
    return make_device('rfid-1', 'Reader', device_type='RFID')


def _counts():
    with get_db_context() as conn:
        a = conn.execute('SELECT COUNT(*) FROM attendance').fetchone()[0]
        s = conn.execute('SELECT COUNT(*) FROM sensor_data').fetchone()[0]
    return a, s


@pytest.mark.parametrize('bad_uid', ['A' * 5000, 123, 'bukan-hex!', 'AB', '0x', '', ' ', 'AB CD EF'])
def test_invalid_uid_rejected_and_not_stored(admin_client, reader, bad_uid):
    resp = _rfid(admin_client, reader, bad_uid)
    assert resp.status_code in (400, 413)
    assert _counts() == (0, 0)


@pytest.mark.parametrize('uid', ['0x010dd605', '04:A3:2B:1C', '04-A3-2B-1C', 'DEADBEEF'])
def test_valid_uid_accepted(admin_client, reader, uid):
    assert _rfid(admin_client, reader, uid).status_code == 200
    assert _counts()[0] == 1


def test_stats_count_only_registered_cards(admin_client, reader):
    admin_client.post('/api/v1/cardholders', json={'uid': 'AABB0001', 'nama': 'Ani'})
    _rfid(admin_client, reader, 'AABB0001')
    _rfid(admin_client, reader, 'CCDD0002')           # kartu asing
    stats = admin_client.get('/api/v1/attendance/stats').get_json()['stats']
    assert stats['hadir_hari_ini'] == 1
    assert stats['total_kartu_aktif'] == 1
    assert stats['kartu_belum_terdaftar'] == 1


def test_cardholder_uid_validation(admin_client):
    assert admin_client.post('/api/v1/cardholders',
                             json={'uid': 123, 'nama': 'X'}).status_code == 400
    assert admin_client.post('/api/v1/cardholders',
                             json={'uid': 'zzzz!', 'nama': 'X'}).status_code == 400
    assert admin_client.post('/api/v1/cardholders',
                             json={'uid': 'AABB0009', 'nama': 123}).status_code == 400
    assert admin_client.post('/api/v1/cardholders',
                             json={'uid': 'AABB0009', 'nama': 'Ok'}).status_code == 201


@pytest.mark.parametrize('value,expected', [
    ('=cmd|x', "'=cmd|x"), ('+1', "'+1"), ('-1', "'-1"), ('@SUM(A1)', "'@SUM(A1)"),
    ('\tx', "'\tx"), ('\rx', "'\rx"), ('aman', 'aman'), ('', ''),
    (5, 5), (-3.2, -3.2), (None, None),
])
def test_csv_safe_unit(value, expected):
    assert csv_safe(value) == expected


def test_attendance_export_neutralises_formulas(admin_client, reader):
    admin_client.post('/api/v1/cardholders', json={'uid': 'EE11FF22', 'nama': '=cmd|x'})
    _rfid(admin_client, reader, 'EE11FF22')
    body = admin_client.get('/api/v1/attendance/export').get_data(as_text=True)
    assert "'=cmd|x" in body
    assert ",=cmd|x" not in body


def test_device_export_neutralises_formulas(admin_client, make_device):
    key = make_device('x-1')
    post_data(admin_client, 'x-1', key, {'note': '=1+1', 'temperature': 25})
    body = admin_client.get('/api/v1/devices/x-1/export?format=csv&hours=1').get_data(as_text=True)
    assert "'=1+1" in body
    assert ",=1+1" not in body
