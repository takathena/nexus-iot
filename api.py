"""
NEXUS IoT - API Routes (v1)
"""
import json
import logging
from flask import Blueprint, request, jsonify, current_app
from marshmallow import ValidationError

from database import get_db, get_db_context, get_wib_time
from validators import device_create_schema, device_update_schema, sensor_data_schema
from utils import generate_api_key, safe_json_loads
from alerts import check_and_create_alerts
from extensions import limiter
from config import get_config

logger = logging.getLogger('nexus')
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


# ==========================================
# HELPER
# ==========================================
def validate_device_api_key(device_id, api_key):
    """Validasi device_id + api_key"""
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ? AND api_key = ?',
            (device_id, api_key)
        ).fetchone()
    return device is not None


def update_device_status(device_id, status, ip=None):
    """Update device status"""
    with get_db_context() as conn:
        if ip:
            conn.execute(
                'UPDATE devices SET status = ?, last_seen = ?, last_ip = ? WHERE device_id = ?',
                (status, get_wib_time(), ip, device_id)
            )
        else:
            conn.execute(
                'UPDATE devices SET status = ?, last_seen = ? WHERE device_id = ?',
                (status, get_wib_time(), device_id)
            )
        conn.commit()


# ==========================================
# DATA RECEPTION
# ==========================================
@api_bp.route('/data', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DATA)
def receive_data():
    """Terima data sensor dari device IoT"""
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        # Validasi payload
        try:
            data = sensor_data_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        # Validasi device + API key
        if not validate_device_api_key(data['device_id'], data['api_key']):
            logger.warning(f"Invalid API key attempt: device={data['device_id']} ip={request.remote_addr}")
            return jsonify({'success': False, 'error': 'Invalid device_id or api_key'}), 401

        # Simpan data
        with get_db_context() as conn:
            conn.execute('''
                INSERT INTO sensor_data
                (device_id, sensor_type, data, wifi_ssid, uptime_seconds, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data['device_id'],
                data['sensor_type'],
                json.dumps(data['data']),
                data.get('wifi_ssid', ''),
                data.get('uptime_seconds', 0),
                get_wib_time()
            ))
            conn.commit()

        # Update status device
        update_device_status(data['device_id'], 'online', request.remote_addr)

        # Cek alerts (non-blocking, error tidak menggagalkan response)
        try:
            check_and_create_alerts(data['device_id'], data['data'])
        except Exception as e:
            logger.error(f"Alert check failed: {e}", exc_info=True)

        return jsonify({
            'success': True,
            'message': 'Data received',
            'timestamp': get_wib_time().isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Error in receive_data: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ==========================================
# DEVICE MANAGEMENT
# ==========================================
@api_bp.route('/devices', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_devices():
    """List semua device dengan pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 100, type=int), 500)
    offset = (page - 1) * per_page

    with get_db_context() as conn:
        total = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
        rows = conn.execute(
            'SELECT * FROM devices ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (per_page, offset)
        ).fetchall()

    devices = []
    for device in rows:
        d = dict(device)
        d.pop('api_key', None)  # Jangan expose API key
        devices.append(d)

    return jsonify({
        'success': True,
        'devices': devices,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': (total + per_page - 1) // per_page,
        }
    }), 200


@api_bp.route('/devices', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def add_device():
    """Tambah device baru"""
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        try:
            data = device_create_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        api_key = generate_api_key()

        with get_db_context() as conn:
            # Cek apakah device sudah ada
            existing = conn.execute(
                'SELECT device_id FROM devices WHERE device_id = ?',
                (data['device_id'],)
            ).fetchone()

            if existing:
                return jsonify({'success': False, 'error': 'Device ID already exists'}), 400

            conn.execute('''
                INSERT INTO devices
                (device_id, device_name, device_type, location, description, api_key)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data['device_id'],
                data['device_name'],
                data['device_type'],
                data['location'],
                data['description'],
                api_key
            ))
            conn.commit()

        logger.info(f"Device added: {data['device_id']}")

        return jsonify({
            'success': True,
            'device': {
                'device_id': data['device_id'],
                'device_name': data['device_name'],
                'api_key': api_key,
                'warning': 'Simpan API key ini! Tidak akan ditampilkan lagi.'
            }
        }), 201

    except Exception as e:
        logger.error(f"Error adding device: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/devices/<device_id>', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_detail(device_id):
    """Detail device + data terbaru"""
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT * FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        latest = conn.execute('''
            SELECT * FROM sensor_data
            WHERE device_id = ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (device_id,)).fetchone()

    device_info = dict(device)
    device_info.pop('api_key', None)

    device_info['latest_data'] = None
    if latest:
        device_info['latest_data'] = {
            'sensor_type': latest['sensor_type'],
            'data': safe_json_loads(latest['data']),
            'wifi_ssid': latest['wifi_ssid'] or '',
            'uptime_seconds': latest['uptime_seconds'] or 0,
            'timestamp': latest['timestamp'],
        }

    return jsonify({'success': True, 'device': device_info}), 200


@api_bp.route('/devices/<device_id>/history', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_history(device_id):
    """Histori data sensor"""
    hours = min(request.args.get('hours', 3, type=int), 720)  # Max 30 hari
    limit = min(request.args.get('limit', 500, type=int), 5000)

    since = get_wib_time().replace(tzinfo=None) - __import__('datetime').timedelta(hours=hours)

    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT * FROM sensor_data
            WHERE device_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (device_id, since, limit)).fetchall()

    history = []
    for item in rows:
        history.append({
            'sensor_type': item['sensor_type'],
            'data': safe_json_loads(item['data']),
            'wifi_ssid': item['wifi_ssid'] or '',
            'uptime_seconds': item['uptime_seconds'] or 0,
            'timestamp': item['timestamp'],
        })

    return jsonify({
        'success': True,
        'history': history,
        'data_count': len(history)
    }), 200


@api_bp.route('/devices/<device_id>', methods=['PUT'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def update_device(device_id):
    """Update info device"""
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        try:
            data = device_update_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        with get_db_context() as conn:
            device = conn.execute(
                'SELECT * FROM devices WHERE device_id = ?',
                (device_id,)
            ).fetchone()

            if not device:
                return jsonify({'success': False, 'error': 'Device not found'}), 404

            # Merge data lama dengan data baru
            updates = {
                'device_name': data.get('device_name', device['device_name']),
                'device_type': data.get('device_type', device['device_type']),
                'location': data.get('location', device['location']),
                'description': data.get('description', device['description']),
                'latitude': data.get('latitude', device['latitude']),
                'longitude': data.get('longitude', device['longitude']),
            }

            conn.execute('''
                UPDATE devices SET
                    device_name = ?, device_type = ?, location = ?,
                    description = ?, latitude = ?, longitude = ?
                WHERE device_id = ?
            ''', (
                updates['device_name'], updates['device_type'], updates['location'],
                updates['description'], updates['latitude'], updates['longitude'],
                device_id
            ))
            conn.commit()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error updating device {device_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/devices/<device_id>', methods=['DELETE'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_device(device_id):
    """Hapus device (cascade)"""
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        conn.execute('DELETE FROM sensor_data WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM alerts WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))
        conn.commit()

    logger.info(f"Device deleted: {device_id}")
    return jsonify({'success': True}), 200


@api_bp.route('/devices/<device_id>/regenerate-key', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_LOGIN)
def regenerate_api_key(device_id):
    """Regenerate API key (jika bocor)"""
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        new_key = generate_api_key()
        conn.execute(
            'UPDATE devices SET api_key = ? WHERE device_id = ?',
            (new_key, device_id)
        )
        conn.commit()

    logger.warning(f"API key regenerated for {device_id}")
    return jsonify({
        'success': True,
        'api_key': new_key,
        'warning': 'Update firmware perangkat dengan API key baru!'
    }), 200


# ==========================================
# DASHBOARD
# ==========================================
@api_bp.route('/dashboard', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_dashboard_data():
    """Data dashboard"""
    with get_db_context() as conn:
        total = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
        online = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE status = 'online'"
        ).fetchone()[0]
        alert_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE is_active = 1"
        ).fetchone()[0]

        rows = conn.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()

        device_list = []
        for device in rows:
            latest = conn.execute('''
                SELECT wifi_ssid, uptime_seconds FROM sensor_data
                WHERE device_id = ?
                ORDER BY timestamp DESC LIMIT 1
            ''', (device['device_id'],)).fetchone()

            device_list.append({
                'device_id': device['device_id'],
                'device_name': device['device_name'],
                'device_type': device['device_type'],
                'location': device['location'],
                'latitude': device['latitude'] or 0,
                'longitude': device['longitude'] or 0,
                'status': device['status'],
                'last_seen': device['last_seen'],
                'latest_wifi_ssid': latest['wifi_ssid'] if latest else '',
                'latest_uptime_seconds': latest['uptime_seconds'] if latest else 0,
            })

    return jsonify({
        'success': True,
        'summary': {
            'total_devices': total,
            'online_devices': online,
            'offline_devices': total - online,
            'active_alerts': alert_count,
        },
        'devices': device_list
    }), 200


# ==========================================
# ALERTS
# ==========================================
@api_bp.route('/alerts', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alerts():
    """Ambil alert aktif"""
    from alerts import get_active_alerts
    return jsonify({
        'success': True,
        'alerts': get_active_alerts()
    }), 200


@api_bp.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def acknowledge_alert(alert_id):
    """Acknowledge alert"""
    with get_db_context() as conn:
        result = conn.execute(
            'UPDATE alerts SET is_active = 0 WHERE id = ?',
            (alert_id,)
        )
        conn.commit()

    if result.rowcount == 0:
        return jsonify({'success': False, 'error': 'Alert not found'}), 404

    return jsonify({'success': True}), 200