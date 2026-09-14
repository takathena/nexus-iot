"""
NEXUS IoT - API Routes (v1)
"""
import json
import logging
from datetime import timedelta
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError

from database import get_db_context, get_wib_time
from validators import device_create_schema, device_update_schema, sensor_data_schema
from utils import generate_api_key, safe_json_loads, validate_alert_rules
from alerts import (
    check_and_create_alerts,
    get_active_alerts,
    get_alert_history,
    get_alert_summary,
    acknowledge_alert,
    clear_offline_alert,
    get_device_alert_rules,
)
from extensions import limiter
from config import get_config

logger = logging.getLogger('nexus')
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


# ==========================================
# HELPERS
# ==========================================
def validate_device_api_key(device_id, api_key):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ? AND api_key = ?',
            (device_id, api_key)
        ).fetchone()
    return device is not None


def update_device_status(device_id, status, ip=None):
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

    if status == 'online':
        try:
            clear_offline_alert(device_id)
        except Exception as e:
            logger.error(f"Failed to clear offline alert: {e}", exc_info=True)


def _alert_label(alert_type, severity):
    """Label readable untuk alert"""
    type_labels = {
        'temperature': 'Suhu',
        'humidity': 'Kelembaban',
        'gas_level': 'Level Gas',
        'offline': 'Perangkat Offline',
        'smoke': 'Asap',
        'motion': 'Gerakan',
        'co2': 'CO2',
        'moisture': 'Kelembaban Tanah',
        'lux': 'Cahaya',
    }
    base = type_labels.get(alert_type, alert_type.replace('_', ' ').title())
    sev_labels = {
        'danger': 'Bahaya',
        'warning': 'Peringatan',
        'info': 'Info',
        'healthy': 'Normal',
    }
    return f"{base} — {sev_labels.get(severity, severity)}"


# ==========================================
# RECEIVE DATA
# ==========================================
@api_bp.route('/data', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DATA)
def receive_data():
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        try:
            data = sensor_data_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        if not validate_device_api_key(data['device_id'], data['api_key']):
            logger.warning(
                f"Invalid API key attempt: device={data['device_id']} "
                f"ip={request.remote_addr}"
            )
            return jsonify({
                'success': False,
                'error': 'Invalid device_id or api_key'
            }), 401

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

        update_device_status(data['device_id'], 'online', request.remote_addr)

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
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


# ==========================================
# DEVICES
# ==========================================
@api_bp.route('/devices', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_devices():
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
        d.pop('api_key', None)
        if d.get('alert_rules'):
            try:
                d['alert_rules'] = json.loads(d['alert_rules'])
            except (json.JSONDecodeError, TypeError):
                d['alert_rules'] = None
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
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        try:
            data = device_create_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        alert_rules = data.get('alert_rules')
        if alert_rules:
            is_valid, err_msg = validate_alert_rules(alert_rules)
            if not is_valid:
                return jsonify({'success': False, 'error': err_msg}), 400

        api_key = generate_api_key()

        expected_interval = data.get('expected_interval', 60)
        offline_timeout = data.get('offline_timeout')
        if offline_timeout is None:
            offline_timeout = max(300, expected_interval * 3)

        alert_rules_json = json.dumps(alert_rules) if alert_rules else None
        offline_severity = data.get('offline_alert_severity', 'danger')

        with get_db_context() as conn:
            existing = conn.execute(
                'SELECT device_id FROM devices WHERE device_id = ?',
                (data['device_id'],)
            ).fetchone()

            if existing:
                return jsonify({
                    'success': False,
                    'error': 'Device ID already exists'
                }), 400

            conn.execute('''
                INSERT INTO devices
                (device_id, device_name, device_type, location, description,
                 api_key, offline_timeout, expected_interval,
                 alert_rules, offline_alert_severity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['device_id'], data['device_name'], data['device_type'],
                data['location'], data['description'], api_key,
                offline_timeout, expected_interval,
                alert_rules_json, offline_severity
            ))
            conn.commit()

        logger.info(f"Device added: {data['device_id']}")

        return jsonify({
            'success': True,
            'device': {
                'device_id': data['device_id'],
                'device_name': data['device_name'],
                'api_key': api_key,
                'offline_timeout': offline_timeout,
                'expected_interval': expected_interval,
                'offline_alert_severity': offline_severity,
                'warning': 'Simpan API key ini! Tidak akan ditampilkan lagi.'
            }
        }), 201

    except Exception as e:
        logger.error(f"Error adding device: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@api_bp.route('/devices/<device_id>', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_detail(device_id):
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

        active_alerts = conn.execute('''
            SELECT * FROM alerts
            WHERE device_id = ? AND is_active = 1
            ORDER BY
                CASE severity
                    WHEN 'danger' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'info' THEN 3
                    ELSE 4
                END,
                created_at DESC
        ''', (device_id,)).fetchall()

    device_info = dict(device)
    device_info.pop('api_key', None)

    if device_info.get('alert_rules'):
        try:
            device_info['alert_rules'] = json.loads(device_info['alert_rules'])
        except (json.JSONDecodeError, TypeError):
            device_info['alert_rules'] = None

    device_info['latest_data'] = None
    if latest:
        device_info['latest_data'] = {
            'sensor_type': latest['sensor_type'],
            'data': safe_json_loads(latest['data']),
            'wifi_ssid': latest['wifi_ssid'] or '',
            'uptime_seconds': latest['uptime_seconds'] or 0,
            'timestamp': latest['timestamp'],
        }

    device_info['active_alerts'] = [dict(a) for a in active_alerts]

    return jsonify({'success': True, 'device': device_info}), 200


@api_bp.route('/devices/<device_id>/history', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_history(device_id):
    hours = min(request.args.get('hours', 3, type=int), 720)
    limit = min(request.args.get('limit', 500, type=int), 5000)

    since = get_wib_time().replace(tzinfo=None) - timedelta(hours=hours)

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
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        try:
            data = device_update_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        alert_rules = data.get('alert_rules')
        if alert_rules is not None:
            is_valid, err_msg = validate_alert_rules(alert_rules)
            if not is_valid:
                return jsonify({'success': False, 'error': err_msg}), 400

        with get_db_context() as conn:
            device = conn.execute(
                'SELECT * FROM devices WHERE device_id = ?',
                (device_id,)
            ).fetchone()

            if not device:
                return jsonify({'success': False, 'error': 'Device not found'}), 404

            if alert_rules is not None:
                alert_rules_json = json.dumps(alert_rules) if alert_rules else None
            else:
                alert_rules_json = device['alert_rules']

            updates = {
                'device_name': data.get('device_name', device['device_name']),
                'device_type': data.get('device_type', device['device_type']),
                'location': data.get('location', device['location']),
                'description': data.get('description', device['description']),
                'latitude': data.get('latitude', device['latitude']),
                'longitude': data.get('longitude', device['longitude']),
                'offline_timeout': data.get('offline_timeout', device['offline_timeout']),
                'expected_interval': data.get('expected_interval', device['expected_interval']),
                'offline_alert_severity': data.get(
                    'offline_alert_severity', device['offline_alert_severity']
                ),
                'alert_rules': alert_rules_json,
            }

            conn.execute('''
                UPDATE devices SET
                    device_name = ?, device_type = ?, location = ?,
                    description = ?, latitude = ?, longitude = ?,
                    offline_timeout = ?, expected_interval = ?,
                    offline_alert_severity = ?, alert_rules = ?
                WHERE device_id = ?
            ''', (
                updates['device_name'], updates['device_type'], updates['location'],
                updates['description'], updates['latitude'], updates['longitude'],
                updates['offline_timeout'], updates['expected_interval'],
                updates['offline_alert_severity'], updates['alert_rules'],
                device_id
            ))
            conn.commit()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error updating device {device_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@api_bp.route('/devices/<device_id>', methods=['DELETE'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_device(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        conn.execute('DELETE FROM sensor_data WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM alerts WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM alert_history WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))
        conn.commit()

    logger.info(f"Device deleted: {device_id}")
    return jsonify({'success': True}), 200


@api_bp.route('/devices/<device_id>/regenerate-key', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_LOGIN)
def regenerate_api_key(device_id):
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
# DEVICE ALERT RULES
# ==========================================
@api_bp.route('/devices/<device_id>/alert-rules', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_alert_rules_endpoint(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id, alert_rules FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        rules = get_device_alert_rules(conn, device_id)
        is_custom = device['alert_rules'] is not None

    return jsonify({
        'success': True,
        'device_id': device_id,
        'alert_rules': rules,
        'is_custom': is_custom,
    }), 200


@api_bp.route('/devices/<device_id>/alert-rules', methods=['PUT'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def update_device_alert_rules_endpoint(device_id):
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        is_valid, err_msg = validate_alert_rules(payload)
        if not is_valid:
            return jsonify({'success': False, 'error': err_msg}), 400

        with get_db_context() as conn:
            device = conn.execute(
                'SELECT device_id FROM devices WHERE device_id = ?',
                (device_id,)
            ).fetchone()

            if not device:
                return jsonify({'success': False, 'error': 'Device not found'}), 404

            conn.execute(
                'UPDATE devices SET alert_rules = ? WHERE device_id = ?',
                (json.dumps(payload), device_id)
            )
            conn.commit()

        logger.info(f"Alert rules updated for {device_id}")
        return jsonify({'success': True, 'alert_rules': payload}), 200

    except Exception as e:
        logger.error(f"Error updating alert rules: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@api_bp.route('/devices/<device_id>/alert-rules', methods=['DELETE'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def reset_device_alert_rules(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        conn.execute(
            'UPDATE devices SET alert_rules = NULL WHERE device_id = ?',
            (device_id,)
        )
        conn.commit()

    logger.info(f"Alert rules reset to global for {device_id}")
    return jsonify({'success': True}), 200


# ==========================================
# DASHBOARD
# ==========================================
@api_bp.route('/dashboard', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_dashboard_data():
    with get_db_context() as conn:
        total = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
        online = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE status = 'online'"
        ).fetchone()[0]

        alert_rows = conn.execute('''
            SELECT severity, COUNT(*) as count
            FROM alerts
            WHERE is_active = 1
            GROUP BY severity
        ''').fetchall()

        alert_summary = {'danger': 0, 'warning': 0, 'info': 0, 'total': 0}
        for row in alert_rows:
            if row['severity'] in alert_summary:
                alert_summary[row['severity']] = row['count']
            alert_summary['total'] += row['count']

        rows = conn.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()

        device_list = []
        for device in rows:
            latest = conn.execute('''
                SELECT wifi_ssid, uptime_seconds FROM sensor_data
                WHERE device_id = ?
                ORDER BY timestamp DESC LIMIT 1
            ''', (device['device_id'],)).fetchone()

            top_alert = conn.execute('''
                SELECT severity, alert_type, message FROM alerts
                WHERE device_id = ? AND is_active = 1
                ORDER BY
                    CASE severity
                        WHEN 'danger' THEN 1
                        WHEN 'warning' THEN 2
                        WHEN 'info' THEN 3
                        ELSE 4
                    END
                LIMIT 1
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
                'offline_timeout': device['offline_timeout'] or 900,
                'expected_interval': device['expected_interval'] or 60,
                'offline_alert_severity': device['offline_alert_severity'] or 'danger',
                'latest_wifi_ssid': latest['wifi_ssid'] if latest else '',
                'latest_uptime_seconds': latest['uptime_seconds'] if latest else 0,
                'has_alert': top_alert is not None,
                'top_alert_severity': top_alert['severity'] if top_alert else None,
                'top_alert_type': top_alert['alert_type'] if top_alert else None,
                'top_alert_message': top_alert['message'] if top_alert else None,
            })

    return jsonify({
        'success': True,
        'summary': {
            'total_devices': total,
            'online_devices': online,
            'offline_devices': total - online,
            'active_alerts': alert_summary['total'],
            'danger_alerts': alert_summary['danger'],
            'warning_alerts': alert_summary['warning'],
            'info_alerts': alert_summary['info'],
        },
        'devices': device_list
    }), 200


# ==========================================
# ALERTS
# ==========================================
@api_bp.route('/alerts', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alerts():
    severity = request.args.get('severity')
    device_id = request.args.get('device_id')
    limit = min(request.args.get('limit', 100, type=int), 500)

    alerts = get_active_alerts(limit=limit, severity=severity, device_id=device_id)

    return jsonify({
        'success': True,
        'alerts': alerts,
        'count': len(alerts)
    }), 200


@api_bp.route('/alerts/summary', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alerts_summary_endpoint():
    return jsonify({
        'success': True,
        'summary': get_alert_summary()
    }), 200


@api_bp.route('/alerts/history', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alerts_history():
    device_id = request.args.get('device_id')
    limit = min(request.args.get('limit', 200, type=int), 1000)
    return jsonify({
        'success': True,
        'history': get_alert_history(device_id, limit)
    }), 200


@api_bp.route('/alerts/stats', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alert_stats():
    """Statistik alert"""
    from datetime import timedelta

    with get_db_context() as conn:
        summary = {'danger': 0, 'warning': 0, 'info': 0, 'total': 0}
        rows = conn.execute('''
            SELECT severity, COUNT(*) as count
            FROM alerts WHERE is_active = 1
            GROUP BY severity
        ''').fetchall()
        for r in rows:
            if r['severity'] in summary:
                summary[r['severity']] = r['count']
            summary['total'] += r['count']

        top_devices = conn.execute('''
            SELECT a.device_id, d.device_name,
                   COUNT(*) as alert_count,
                   SUM(CASE WHEN a.severity = 'danger' THEN 1 ELSE 0 END) as danger_count,
                   SUM(CASE WHEN a.severity = 'warning' THEN 1 ELSE 0 END) as warning_count
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            WHERE a.is_active = 1
            GROUP BY a.device_id
            ORDER BY alert_count DESC
            LIMIT 5
        ''').fetchall()

        total_history = conn.execute(
            'SELECT COUNT(*) FROM alert_history'
        ).fetchone()[0]

        active_count = conn.execute(
            'SELECT COUNT(*) FROM alerts WHERE is_active = 1'
        ).fetchone()[0]

    return jsonify({
        'success': True,
        'summary': summary,
        'top_devices': [dict(r) for r in top_devices],
        'total_history': total_history,
        'active_count': active_count,
    }), 200


@api_bp.route('/alerts/all', methods=['GET'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_all_alerts():
    """Ambil semua alert (aktif + history) untuk Alert Center"""
    status = request.args.get('status', 'all')
    severity = request.args.get('severity')
    device_id = request.args.get('device_id')
    limit = min(request.args.get('limit', 200, type=int), 1000)

    with get_db_context() as conn:
        query = '''
            SELECT
                h.id,
                h.device_id,
                h.alert_type,
                h.severity,
                h.message,
                h.value,
                h.action,
                h.created_at,
                d.device_name,
                d.location,
                CASE
                    WHEN h.action = 'cleared' OR h.action = 'acknowledged' THEN 0
                    WHEN EXISTS (
                        SELECT 1 FROM alerts a
                        WHERE a.device_id = h.device_id
                          AND a.alert_type = h.alert_type
                          AND a.is_active = 1
                    ) THEN 1
                    ELSE 0
                END as is_still_active
            FROM alert_history h
            LEFT JOIN devices d ON h.device_id = d.device_id
            WHERE 1=1
        '''
        params = []

        if severity:
            query += ' AND h.severity = ?'
            params.append(severity)

        if device_id:
            query += ' AND h.device_id = ?'
            params.append(device_id)

        if status == 'active':
            query += ''' AND h.action != 'cleared'
                        AND h.action != 'acknowledged'
                        AND EXISTS (
                            SELECT 1 FROM alerts a
                            WHERE a.device_id = h.device_id
                              AND a.alert_type = h.alert_type
                              AND a.is_active = 1
                        )'''
        elif status == 'resolved':
            query += ''' AND (h.action = 'cleared'
                            OR h.action = 'acknowledged'
                            OR NOT EXISTS (
                                SELECT 1 FROM alerts a
                                WHERE a.device_id = h.device_id
                                  AND a.alert_type = h.alert_type
                                  AND a.is_active = 1
                            ))'''

        query += ' ORDER BY h.created_at DESC LIMIT ?'
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

    alerts = []
    for r in rows:
        d = dict(r)
        d['label'] = _alert_label(d['alert_type'], d['severity'])
        alerts.append(d)

    return jsonify({
        'success': True,
        'alerts': alerts,
        'count': len(alerts)
    }), 200


@api_bp.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def acknowledge_alert_endpoint(alert_id):
    success = acknowledge_alert(alert_id)
    if not success:
        return jsonify({
            'success': False,
            'error': 'Alert not found or already acknowledged'
        }), 404
    return jsonify({'success': True}), 200