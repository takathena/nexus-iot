"""
NEXUS IoT - API Routes (v1)
"""
from app.auth import login_required
import json
import logging
import csv
import io
import os
from datetime import timedelta, datetime
from flask import Blueprint, request, jsonify, Response
from marshmallow import ValidationError

from app.database import get_db_context, get_wib_time
from app.validators import device_create_schema, device_update_schema, sensor_data_schema
from app.utils import (
    generate_api_key, safe_json_loads, validate_alert_rules,
    hash_api_key, verify_api_key,
)
from app.alerts import (
    check_and_create_alerts, get_active_alerts, get_alert_history,
    acknowledge_alert, bulk_acknowledge_alerts,
    clear_offline_alert, get_device_alert_rules,
)
from app.extensions import limiter, csrf
from app.config import get_config
from app.notifier import send_test_notification, get_notification_status

logger = logging.getLogger('nexus')
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


def validate_device_api_key(device_id, api_key):
    if not device_id or not api_key:
        return False

    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id, api_key, api_key_hash FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

    if not device:
        return False

    if device['api_key_hash']:
        return verify_api_key(api_key, device['api_key_hash'])

    # Fallback plaintext (device lama yang belum migrate)
    if device['api_key']:
        import hmac
        return hmac.compare_digest(device['api_key'], api_key)
    return False


def update_device_status(device_id, status, ip=None):
    with get_db_context() as conn:
        prev = conn.execute(
            'SELECT status FROM devices WHERE device_id = ?', (device_id,)
        ).fetchone()
        prev_status = prev['status'] if prev else None

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

        # Catat transisi ke online (sebelumnya hanya 'offline' yang tercatat,
        # karena data masuk langsung men-set online sebelum status checker sempat).
        if prev_status is not None and prev_status != status:
            conn.execute(
                'INSERT INTO device_status_log (device_id, status, reason, created_at) '
                'VALUES (?, ?, ?, ?)',
                (device_id, status, 'data_received', get_wib_time())
            )
        conn.commit()

    if status == 'online':
        try:
            clear_offline_alert(device_id)
        except Exception as e:
            logger.error(f"Failed to clear offline alert: {e}", exc_info=True)


def _alert_label(alert_type, severity):
    type_labels = {
        'temperature': 'Suhu', 'humidity': 'Kelembaban', 'gas_level': 'Level Gas',
        'offline': 'Perangkat Offline', 'smoke': 'Asap', 'motion': 'Gerakan',
        'co2': 'CO2', 'moisture': 'Kelembaban Tanah', 'lux': 'Cahaya',
    }
    base = type_labels.get(alert_type, alert_type.replace('_', ' ').title())
    sev_labels = {'danger': 'Bahaya', 'warning': 'Peringatan', 'info': 'Info', 'healthy': 'Normal'}
    return f"{base} — {sev_labels.get(severity, severity)}"


# ==========================================
# DEVICE-FACING ENDPOINT
# ==========================================
@api_bp.route('/data', methods=['POST'])
@csrf.exempt
@limiter.limit(lambda: get_config().RATE_LIMIT_DATA)
def receive_data():
    from werkzeug.exceptions import RequestEntityTooLarge

    try:
        payload = request.get_json(silent=True)
    except RequestEntityTooLarge:
        max_mb = get_config().MAX_CONTENT_LENGTH / (1024 * 1024)
        return jsonify({
            'success': False,
            'error': f'Payload terlalu besar. Maksimal {max_mb:.1f} MB.',
        }), 413

    try:
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        try:
            data = sensor_data_schema.load(payload)
        except ValidationError as err:
            return jsonify({'success': False, 'error': err.messages}), 400

        if not validate_device_api_key(data['device_id'], data['api_key']):
            logger.warning(f"Invalid API key attempt: device={data['device_id']}")
            return jsonify({'success': False, 'error': 'Invalid device_id or api_key'}), 401

        with get_db_context() as conn:
            conn.execute('''
                INSERT INTO sensor_data
                (device_id, sensor_type, data, wifi_ssid, uptime_seconds, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data['device_id'], data['sensor_type'],
                json.dumps(data['data']), data.get('wifi_ssid', ''),
                data.get('uptime_seconds', 0), get_wib_time()
            ))
            conn.commit()

        update_device_status(data['device_id'], 'online', request.remote_addr)

        if data['sensor_type'] == 'RFID':
            uid = data['data'].get('uid')
            if uid:
                with get_db_context() as conn:
                    conn.execute(
                        'INSERT INTO attendance (uid, device_id, timestamp) VALUES (?, ?, ?)',
                        (uid, data['device_id'], get_wib_time())
                    )
                    conn.commit()

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
# ALERT TREND
# ==========================================
@api_bp.route('/alerts/trend', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alert_trend():
    hours = min(request.args.get('hours', 24, type=int), 168)
    since = get_wib_time() - timedelta(hours=hours)

    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT strftime('%Y-%m-%d %H:00', created_at) AS hour_bucket,
                   severity, COUNT(*) AS count
            FROM alert_history
            WHERE created_at >= ? AND action = 'created'
            GROUP BY hour_bucket, severity
            ORDER BY hour_bucket ASC
        ''', (since,)).fetchall()

    return jsonify({'success': True, 'trend': [dict(r) for r in rows], 'range_hours': hours}), 200


# ==========================================
# DEVICES
# ==========================================
@api_bp.route('/devices', methods=['GET'])
@login_required
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
        d.pop('api_key_hash', None)
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
            'page': page, 'per_page': per_page, 'total': total,
            'total_pages': (total + per_page - 1) // per_page,
        }
    }), 200


@api_bp.route('/devices', methods=['POST'])
@login_required
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
        api_key_hash = hash_api_key(api_key)

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
                return jsonify({'success': False, 'error': 'Device ID already exists'}), 400

            conn.execute('''
                INSERT INTO devices
                (device_id, device_name, device_type, location, description,
                 api_key, api_key_hash, offline_timeout, expected_interval,
                 alert_rules, offline_alert_severity, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['device_id'], data['device_name'], data['device_type'],
                data['location'], data['description'],
                None, api_key_hash,
                offline_timeout, expected_interval,
                alert_rules_json, offline_severity, get_wib_time()
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
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/devices/<device_id>', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_detail(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT * FROM devices WHERE device_id = ?', (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        latest = conn.execute('''
            SELECT * FROM sensor_data WHERE device_id = ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (device_id,)).fetchone()

        active_alerts = conn.execute('''
            SELECT * FROM alerts
            WHERE device_id = ? AND is_active = 1 AND alert_type != 'uid'
            ORDER BY
                CASE severity
                    WHEN 'danger' THEN 1 WHEN 'warning' THEN 2
                    WHEN 'info' THEN 3 ELSE 4
                END,
                created_at DESC
        ''', (device_id,)).fetchall()

    device_info = dict(device)
    device_info.pop('api_key', None)
    device_info.pop('api_key_hash', None)

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
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_history(device_id):
    hours = min(request.args.get('hours', 3, type=int), 720)
    limit = min(request.args.get('limit', 500, type=int), 5000)
    since = get_wib_time() - timedelta(hours=hours)

    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT * FROM sensor_data
            WHERE device_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC LIMIT ?
        ''', (device_id, since, limit)).fetchall()

    history = [{
        'sensor_type': item['sensor_type'],
        'data': safe_json_loads(item['data']),
        'wifi_ssid': item['wifi_ssid'] or '',
        'uptime_seconds': item['uptime_seconds'] or 0,
        'timestamp': item['timestamp'],
    } for item in rows]

    return jsonify({'success': True, 'history': history, 'data_count': len(history)}), 200


@api_bp.route('/devices/<device_id>', methods=['PUT'])
@login_required
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
                'SELECT * FROM devices WHERE device_id = ?', (device_id,)
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
                'offline_alert_severity': data.get('offline_alert_severity', device['offline_alert_severity']),
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
                updates['offline_alert_severity'], updates['alert_rules'], device_id
            ))
            conn.commit()

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error updating device {device_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/devices/<device_id>', methods=['DELETE'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_device(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?', (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        conn.execute('DELETE FROM sensor_data WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM alerts WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM alert_history WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM device_status_log WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM attendance WHERE device_id = ?', (device_id,))
        conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))
        conn.commit()

    logger.info(f"Device deleted: {device_id}")
    return jsonify({'success': True}), 200


@api_bp.route('/devices/<device_id>/regenerate-key', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_REGENERATE)
def regenerate_api_key(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?', (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        new_key = generate_api_key()
        new_hash = hash_api_key(new_key)
        conn.execute(
            'UPDATE devices SET api_key = NULL, api_key_hash = ? WHERE device_id = ?',
            (new_hash, device_id)
        )
        conn.commit()

    logger.warning(f"API key regenerated for {device_id}")
    return jsonify({
        'success': True, 'api_key': new_key,
        'warning': 'Update firmware perangkat dengan API key baru!'
    }), 200


@api_bp.route('/devices/<device_id>/alert-rules', methods=['GET'])
@login_required
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
        'success': True, 'device_id': device_id,
        'alert_rules': rules, 'is_custom': is_custom,
    }), 200


@api_bp.route('/devices/<device_id>/alert-rules', methods=['PUT'])
@login_required
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
                'SELECT device_id FROM devices WHERE device_id = ?', (device_id,)
            ).fetchone()

            if not device:
                return jsonify({'success': False, 'error': 'Device not found'}), 404

            conn.execute('UPDATE devices SET alert_rules = ? WHERE device_id = ?',
                         (json.dumps(payload), device_id))
            conn.commit()

        return jsonify({'success': True, 'alert_rules': payload}), 200

    except Exception as e:
        logger.error(f"Error updating alert rules: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/devices/<device_id>/alert-rules', methods=['DELETE'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def reset_device_alert_rules(device_id):
    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_id FROM devices WHERE device_id = ?', (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        conn.execute('UPDATE devices SET alert_rules = NULL WHERE device_id = ?', (device_id,))
        conn.commit()

    return jsonify({'success': True}), 200


# ==========================================
# DASHBOARD
# ==========================================
@api_bp.route('/dashboard', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_dashboard_data():
    with get_db_context() as conn:
        counts = conn.execute('''
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) AS online,
                SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) AS offline
            FROM devices
        ''').fetchone()

        total = counts['total'] or 0
        online = counts['online'] or 0
        offline = counts['offline'] or 0

        alert_rows = conn.execute('''
            SELECT severity, COUNT(*) AS count
            FROM alerts
            WHERE is_active = 1 AND alert_type != 'uid'
            GROUP BY severity
        ''').fetchall()

        alert_summary = {'danger': 0, 'warning': 0, 'info': 0, 'total': 0}
        for row in alert_rows:
            if row['severity'] in alert_summary:
                alert_summary[row['severity']] = row['count']
            alert_summary['total'] += row['count']

        rows = conn.execute('''
            SELECT
                d.device_id, d.device_name, d.device_type, d.location,
                d.latitude, d.longitude, d.status, d.last_seen,
                d.offline_timeout, d.expected_interval, d.offline_alert_severity,
                d.firmware_version, d.last_ip,
                sd.wifi_ssid AS latest_wifi_ssid,
                sd.uptime_seconds AS latest_uptime_seconds,
                sd.timestamp AS latest_data_at,
                a.severity AS top_alert_severity,
                a.alert_type AS top_alert_type,
                a.message AS top_alert_message,
                a.created_at AS top_alert_created_at,
                ac.alert_count AS total_active_alerts
            FROM devices d
            LEFT JOIN (
                SELECT device_id, wifi_ssid, uptime_seconds, timestamp,
                       ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY timestamp DESC) AS rn
                FROM sensor_data
            ) sd ON d.device_id = sd.device_id AND sd.rn = 1
            LEFT JOIN (
                SELECT device_id, severity, alert_type, message, created_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY device_id
                           ORDER BY CASE severity
                               WHEN 'danger' THEN 1 WHEN 'warning' THEN 2
                               WHEN 'info' THEN 3 ELSE 4
                           END, created_at DESC
                       ) AS rn
                FROM alerts
                WHERE is_active = 1 AND alert_type != 'uid'
            ) a ON d.device_id = a.device_id AND a.rn = 1
            LEFT JOIN (
                SELECT device_id, COUNT(*) AS alert_count
                FROM alerts
                WHERE is_active = 1 AND alert_type != 'uid'
                GROUP BY device_id
            ) ac ON d.device_id = ac.device_id
            ORDER BY
                CASE WHEN a.severity = 'danger' THEN 1
                     WHEN a.severity = 'warning' THEN 2
                     WHEN a.severity = 'info' THEN 3
                     ELSE 4 END,
                d.created_at DESC
        ''').fetchall()

        device_list = []
        healthy_count = 0
        for row in rows:
            has_alert = row['top_alert_severity'] is not None
            is_online = row['status'] == 'online'
            if is_online and not has_alert:
                healthy_count += 1

            device_list.append({
                'device_id': row['device_id'],
                'device_name': row['device_name'],
                'device_type': row['device_type'],
                'location': row['location'],
                'latitude': row['latitude'] or 0,
                'longitude': row['longitude'] or 0,
                'status': row['status'],
                'last_seen': row['last_seen'],
                'last_ip': row['last_ip'] or '',
                'firmware_version': row['firmware_version'] or '',
                'offline_timeout': row['offline_timeout'] or 900,
                'expected_interval': row['expected_interval'] or 60,
                'offline_alert_severity': row['offline_alert_severity'] or 'danger',
                'latest_wifi_ssid': row['latest_wifi_ssid'] or '',
                'latest_uptime_seconds': row['latest_uptime_seconds'] or 0,
                'latest_data_at': row['latest_data_at'],
                'has_alert': has_alert,
                'top_alert_severity': row['top_alert_severity'],
                'top_alert_type': row['top_alert_type'],
                'top_alert_message': row['top_alert_message'],
                'top_alert_created_at': row['top_alert_created_at'],
                'total_active_alerts': row['total_active_alerts'] or 0,
            })

    return jsonify({
        'success': True,
        'summary': {
            'total_devices': total,
            'online_devices': online,
            'offline_devices': offline,
            'healthy_devices': healthy_count,
            'active_alerts': alert_summary['total'],
            'danger_alerts': alert_summary['danger'],
            'warning_alerts': alert_summary['warning'],
            'info_alerts': alert_summary['info'],
        },
        'devices': device_list,
    }), 200


# ==========================================
# ALERTS
# ==========================================
@api_bp.route('/alerts', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alerts():
    severity = request.args.get('severity')
    device_id = request.args.get('device_id')
    limit = min(request.args.get('limit', 100, type=int), 500)
    alerts = get_active_alerts(limit=limit, severity=severity, device_id=device_id)
    return jsonify({'success': True, 'alerts': alerts, 'count': len(alerts)}), 200


@api_bp.route('/alerts/history', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alerts_history():
    device_id = request.args.get('device_id')
    limit = min(request.args.get('limit', 200, type=int), 1000)
    return jsonify({'success': True, 'history': get_alert_history(device_id, limit)}), 200


@api_bp.route('/alerts/stats', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_alert_stats():
    with get_db_context() as conn:
        summary = {'danger': 0, 'warning': 0, 'info': 0, 'total': 0}
        rows = conn.execute('''
            SELECT severity, COUNT(*) as count
            FROM alerts WHERE is_active = 1 AND alert_type != 'uid'
            GROUP BY severity
        ''').fetchall()
        for r in rows:
            if r['severity'] in summary:
                summary[r['severity']] = r['count']
            summary['total'] += r['count']

        top_devices = conn.execute('''
            SELECT a.device_id, d.device_name, COUNT(*) as alert_count,
                   SUM(CASE WHEN a.severity = 'danger' THEN 1 ELSE 0 END) as danger_count,
                   SUM(CASE WHEN a.severity = 'warning' THEN 1 ELSE 0 END) as warning_count
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            WHERE a.is_active = 1 AND a.alert_type != 'uid'
            GROUP BY a.device_id
            ORDER BY alert_count DESC LIMIT 5
        ''').fetchall()

        total_history = conn.execute('SELECT COUNT(*) FROM alert_history').fetchone()[0]
        active_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE is_active = 1 AND alert_type != 'uid'"
        ).fetchone()[0]

    return jsonify({
        'success': True,
        'summary': summary,
        'top_devices': [dict(r) for r in top_devices],
        'total_history': total_history,
        'active_count': active_count,
    }), 200


@api_bp.route('/alerts/all', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_all_alerts():
    status = request.args.get('status', 'all')
    severity = request.args.get('severity')
    device_id = request.args.get('device_id')
    limit = min(request.args.get('limit', 200, type=int), 1000)

    with get_db_context() as conn:
        # ✅ FIX #14: pakai LEFT JOIN ke subquery aktif, bukan correlated EXISTS
        # Jauh lebih cepat untuk history besar.
        base_query = '''
            SELECT h.id, h.device_id, h.alert_type, h.severity, h.message,
                   h.value, h.action, h.created_at,
                   d.device_name, d.location,
                   CASE
                       WHEN h.action IN ('cleared', 'acknowledged') THEN 0
                       WHEN active_alerts.device_id IS NOT NULL THEN 1
                       ELSE 0
                   END as is_still_active
            FROM alert_history h
            LEFT JOIN devices d ON h.device_id = d.device_id
            LEFT JOIN (
                SELECT DISTINCT device_id, alert_type
                FROM alerts
                WHERE is_active = 1
            ) active_alerts
                ON active_alerts.device_id = h.device_id
               AND active_alerts.alert_type = h.alert_type
            WHERE h.alert_type != 'uid'
        '''
        params = []

        if severity:
            base_query += ' AND h.severity = ?'
            params.append(severity)

        if device_id:
            base_query += ' AND h.device_id = ?'
            params.append(device_id)

        if status == 'active':
            base_query += ''' AND h.action NOT IN ('cleared', 'acknowledged')
                              AND active_alerts.device_id IS NOT NULL'''
        elif status == 'resolved':
            base_query += ''' AND (h.action IN ('cleared', 'acknowledged')
                                   OR active_alerts.device_id IS NULL)'''

        base_query += ' ORDER BY h.created_at DESC LIMIT ?'
        params.append(limit)

        rows = conn.execute(base_query, params).fetchall()

    alerts = []
    for r in rows:
        d = dict(r)
        d['label'] = _alert_label(d['alert_type'], d['severity'])
        alerts.append(d)

    return jsonify({'success': True, 'alerts': alerts, 'count': len(alerts)}), 200


@api_bp.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def acknowledge_alert_endpoint(alert_id):
    success = acknowledge_alert(alert_id)
    if not success:
        return jsonify({'success': False, 'error': 'Alert not found or already acknowledged'}), 404
    return jsonify({'success': True}), 200


@api_bp.route('/alerts/bulk-acknowledge', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def bulk_acknowledge():
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload.get('ids'), list):
        return jsonify({'success': False, 'error': 'Kirim {"ids": [1, 2, 3]}'}), 400

    ids = []
    for i in payload['ids']:
        try:
            ids.append(int(i))
        except (ValueError, TypeError):
            continue

    if not ids:
        return jsonify({'success': False, 'error': 'Tidak ada ID valid'}), 400

    count = bulk_acknowledge_alerts(ids)
    return jsonify({'success': True, 'acknowledged': count}), 200


@api_bp.route('/devices/<device_id>/status-history', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_device_status_history(device_id):
    limit = min(request.args.get('limit', 100, type=int), 500)
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT status, reason, created_at FROM device_status_log
            WHERE device_id = ? ORDER BY created_at DESC LIMIT ?
        ''', (device_id, limit)).fetchall()

    return jsonify({
        'success': True,
        'history': [dict(r) for r in rows],
        'count': len(rows)
    }), 200


@api_bp.route('/devices/<device_id>/export', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def export_device_data(device_id):
    format_type = request.args.get('format', 'csv').lower()
    hours = min(request.args.get('hours', 24, type=int), 8760)
    limit = min(request.args.get('limit', 10000, type=int), 50000)
    since = get_wib_time() - timedelta(hours=hours)

    with get_db_context() as conn:
        device = conn.execute(
            'SELECT device_name FROM devices WHERE device_id = ?', (device_id,)
        ).fetchone()

        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        rows = conn.execute('''
            SELECT sensor_type, data, wifi_ssid, uptime_seconds, timestamp
            FROM sensor_data
            WHERE device_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC LIMIT ?
        ''', (device_id, since, limit)).fetchall()

    records = []
    all_keys = set()
    for item in rows:
        parsed = safe_json_loads(item['data'])
        record = {
            'timestamp': item['timestamp'],
            'sensor_type': item['sensor_type'],
            'wifi_ssid': item['wifi_ssid'] or '',
            'uptime_seconds': item['uptime_seconds'] or 0,
        }
        for k, v in parsed.items():
            record[k] = v
            all_keys.add(k)
        records.append(record)

    sorted_keys = sorted(all_keys)

    if format_type == 'csv':
        output = io.StringIO()
        headers = ['timestamp', 'sensor_type', 'wifi_ssid', 'uptime_seconds'] + sorted_keys
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        for r in records:
            writer.writerow(r)

        filename = f"{device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(output.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    filename = f"{device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        json.dumps({
            'device_id': device_id,
            'device_name': device['device_name'],
            'exported_at': get_wib_time().isoformat(),
            'range_hours': hours,
            'count': len(records),
            'data': records,
        }, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ==========================================
# CARDHOLDERS
# ==========================================
@api_bp.route('/cardholders', methods=['POST'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def add_cardholder():
    try:
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

        uid = payload.get('uid', '').strip()
        nama = payload.get('nama', '').strip()

        if not uid or not nama:
            return jsonify({'success': False, 'error': 'uid dan nama wajib diisi'}), 400

        with get_db_context() as conn:
            existing = conn.execute(
                'SELECT uid FROM cardholders WHERE uid = ?', (uid,)
            ).fetchone()
            if existing:
                return jsonify({'success': False, 'error': 'UID sudah terdaftar'}), 400

            conn.execute(
                'INSERT INTO cardholders (uid, nama, created_at) VALUES (?, ?, ?)',
                (uid, nama, get_wib_time())
            )
            conn.commit()

        return jsonify({'success': True, 'cardholder': {'uid': uid, 'nama': nama}}), 201

    except Exception as e:
        logger.error(f"Error adding cardholder: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api_bp.route('/cardholders', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_cardholders():
    with get_db_context() as conn:
        rows = conn.execute(
            'SELECT uid, nama, created_at FROM cardholders ORDER BY created_at DESC'
        ).fetchall()
    return jsonify({'success': True, 'cardholders': [dict(row) for row in rows]}), 200


@api_bp.route('/cardholders/<uid>', methods=['DELETE'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def delete_cardholder(uid):
    with get_db_context() as conn:
        existing = conn.execute(
            'SELECT uid FROM cardholders WHERE uid = ?', (uid,)
        ).fetchone()
        if not existing:
            return jsonify({'success': False, 'error': 'Kartu tidak ditemukan'}), 404

        conn.execute('DELETE FROM cardholders WHERE uid = ?', (uid,))
        conn.commit()

    return jsonify({'success': True}), 200


@api_bp.route('/attendance', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_attendance():
    limit = min(request.args.get('limit', 100, type=int), 1000)
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT a.id, a.uid, a.device_id, a.timestamp,
                   COALESCE(c.nama, 'Tidak dikenal') AS nama
            FROM attendance a
            LEFT JOIN cardholders c ON a.uid = c.uid
            ORDER BY a.timestamp DESC LIMIT ?
        ''', (limit,)).fetchall()

    return jsonify({'success': True, 'attendance': [dict(row) for row in rows]}), 200


@api_bp.route('/attendance/stats', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_attendance_stats():
    now_wib = get_wib_time()
    today_start = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    with get_db_context() as conn:
        hadir_hari_ini = conn.execute('''
            SELECT COUNT(DISTINCT uid) FROM attendance
            WHERE timestamp >= ? AND timestamp < ?
        ''', (today_start, tomorrow_start)).fetchone()[0]

        total_kartu_aktif = conn.execute('SELECT COUNT(*) FROM cardholders').fetchone()[0]

        kartu_belum_terdaftar = conn.execute('''
            SELECT COUNT(DISTINCT a.uid) FROM attendance a
            WHERE NOT EXISTS (SELECT 1 FROM cardholders c WHERE c.uid = a.uid)
        ''').fetchone()[0]

    return jsonify({
        'success': True,
        'stats': {
            'hadir_hari_ini': hadir_hari_ini,
            'total_kartu_aktif': total_kartu_aktif,
            'kartu_belum_terdaftar': kartu_belum_terdaftar
        }
    }), 200


@api_bp.route('/attendance/today', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_attendance_today():
    now_wib = get_wib_time()
    today_start = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT COALESCE(c.nama, 'Tidak dikenal') AS nama, a.uid,
                   MIN(a.timestamp) AS pertama_tap
            FROM attendance a
            LEFT JOIN cardholders c ON a.uid = c.uid
            WHERE a.timestamp >= ? AND a.timestamp < ?
            GROUP BY a.uid
            ORDER BY pertama_tap ASC
        ''', (today_start, tomorrow_start)).fetchall()

    return jsonify({'success': True, 'hadir': [dict(r) for r in rows]}), 200


@api_bp.route('/attendance/unregistered', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_unregistered_cards():
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT a.uid, MAX(a.timestamp) AS terakhir_tap
            FROM attendance a
            WHERE NOT EXISTS (SELECT 1 FROM cardholders c WHERE c.uid = a.uid)
            GROUP BY a.uid
            ORDER BY terakhir_tap DESC
        ''').fetchall()

    return jsonify({'success': True, 'kartu': [dict(r) for r in rows]}), 200


@api_bp.route('/attendance/last-unknown', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_last_unknown_tap():
    with get_db_context() as conn:
        row = conn.execute('''
            SELECT a.uid, a.timestamp FROM attendance a
            WHERE NOT EXISTS (SELECT 1 FROM cardholders c WHERE c.uid = a.uid)
            ORDER BY a.timestamp DESC LIMIT 1
        ''').fetchone()

    if not row:
        return jsonify({'success': True, 'uid': None}), 200

    return jsonify({'success': True, 'uid': row['uid'], 'timestamp': row['timestamp']}), 200

@api_bp.route('/attendance/export', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def export_attendance():
    """Export data absensi dengan filter tanggal."""
    from flask import Response
    import csv
    import io as _io

    start_date = request.args.get('start')
    end_date = request.args.get('end')
    uid = request.args.get('uid')

    query = '''
        SELECT a.id, a.uid, a.device_id, a.timestamp,
               COALESCE(c.nama, 'Tidak dikenal') AS nama
        FROM attendance a
        LEFT JOIN cardholders c ON a.uid = c.uid
        WHERE 1=1
    '''
    params = []

    if start_date:
        try:
            query += ' AND a.timestamp >= ?'
            params.append(f"{start_date} 00:00:00")
        except Exception:
            pass

    if end_date:
        try:
            query += ' AND a.timestamp <= ?'
            params.append(f"{end_date} 23:59:59")
        except Exception:
            pass

    if uid:
        query += ' AND a.uid = ?'
        params.append(uid)

    query += ' ORDER BY a.timestamp DESC LIMIT 50000'

    with get_db_context() as conn:
        rows = conn.execute(query, params).fetchall()

    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'UID', 'Nama', 'Device ID', 'Timestamp'])

    for r in rows:
        writer.writerow([r['id'], r['uid'], r['nama'], r['device_id'], r['timestamp']])

    filename = f"attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@api_bp.route('/system/info', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def get_system_info():
    config = get_config()

    with get_db_context() as conn:
        device_count = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
        sensor_count = conn.execute('SELECT COUNT(*) FROM sensor_data').fetchone()[0]
        alert_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE is_active = 1 AND alert_type != 'uid'"
        ).fetchone()[0]
        history_count = conn.execute('SELECT COUNT(*) FROM alert_history').fetchone()[0]
        attendance_count = conn.execute('SELECT COUNT(*) FROM attendance').fetchone()[0]
        cardholder_count = conn.execute('SELECT COUNT(*) FROM cardholders').fetchone()[0]

    db_size = 0
    db_path = config.DB_PATH
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path)
    wal_path = db_path + '-wal'
    if os.path.exists(wal_path):
        db_size += os.path.getsize(wal_path)

    return jsonify({
        'success': True,
        'info': {
            'version': '4.0',
            'device_count': device_count,
            'sensor_data_count': sensor_count,
            'active_alerts': alert_count,
            'alert_history_count': history_count,
            'attendance_count': attendance_count,
            'cardholder_count': cardholder_count,
            'database_size_bytes': db_size,
            'database_size_mb': round(db_size / (1024 * 1024), 2),
            'data_retention_days': config.DATA_RETENTION_DAYS,
        }
    }), 200


# ==========================================
# NOTIFICATIONS
# ==========================================
@api_bp.route('/notifications/test', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def test_notification():
    try:
        results = send_test_notification()
        all_success = all(
            r.get('success', False)
            for k, r in results.items()
            if not k.startswith('_')
        )
        return jsonify({'success': all_success, 'results': results}), 200 if all_success else 500
    except Exception as e:
        logger.error(f"Test notification failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/notifications/config', methods=['GET'])
@login_required
@limiter.limit(lambda: get_config().RATE_LIMIT_DEFAULT)
def notification_config():
    return jsonify({'success': True, 'config': get_notification_status()}), 200