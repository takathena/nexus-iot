"""
NEXUS IoT - Alert System
State machine: healthy → warning → danger → warning → healthy
"""
import json
import logging
from datetime import timedelta
from app.config import get_config
from app.database import get_db_context, get_wib_time
from app.notifier import notify_alert_event

logger = logging.getLogger('nexus')

SEVERITY_ORDER = ['healthy', 'warning', 'danger']
VALID_SEVERITIES = ['healthy', 'info', 'warning', 'danger']
DEFAULT_HYSTERESIS = 0.5

SENSOR_LABELS = {
    'temperature': ('Suhu', '°C'),
    'humidity': ('Kelembaban', '%'),
    'gas_level': ('Level Gas', 'ppm'),
    'smoke': ('Asap', 'ppm'),
    'moisture': ('Kelembaban Tanah', '%'),
    'lux': ('Cahaya', 'lux'),
    'co2': ('CO2', 'ppm'),
    'voc': ('VOC', 'ppb'),
    'air_quality': ('Kualitas Udara', 'AQI'),
    'motion': ('Gerakan', ''),
    'rfid': ('RFID', ''),
}


def _get_sensor_label(key):
    return SENSOR_LABELS.get(key, (key.replace('_', ' ').title(), ''))


def _get_global_rules():
    config = get_config()
    return {k: v for k, v in config.ALERT_RULES.items() if isinstance(v, dict)}


def _validate_rule(rule):
    if not isinstance(rule, dict):
        return False
    for severity, range_dict in rule.items():
        if severity.startswith('_'):
            continue
        if severity not in VALID_SEVERITIES:
            return False
        if not isinstance(range_dict, dict):
            return False
        if 'min' not in range_dict or 'max' not in range_dict:
            return False
        try:
            float(range_dict['min'])
            float(range_dict['max'])
        except (TypeError, ValueError):
            return False
    return True


def _evaluate_severity(value, rule):
    if not _validate_rule(rule):
        return None, None

    for severity in SEVERITY_ORDER:
        r = rule.get(severity)
        if not r:
            continue
        try:
            rmin = float(r['min'])
            rmax = float(r['max'])
        except (TypeError, ValueError):
            continue

        if rmin <= value <= rmax:
            if severity == 'healthy':
                return 'healthy', None
            elif severity == 'warning':
                return 'warning', None
            elif severity == 'danger':
                return 'danger', None

    return 'danger', None


def _severity_rank(sev):
    return {'healthy': 0, 'info': 1, 'warning': 2, 'danger': 3}.get(sev, 0)


def _apply_hysteresis(new_severity, old_severity, value, rule):
    if not old_severity or old_severity == new_severity:
        return new_severity

    old_rank = _severity_rank(old_severity)
    new_rank = _severity_rank(new_severity)

    if new_rank > old_rank:
        return new_severity

    offset = float(rule.get('_hysteresis', DEFAULT_HYSTERESIS))
    new_range = rule.get(new_severity)
    if not new_range:
        return new_severity

    try:
        n_min = float(new_range['min'])
        n_max = float(new_range['max'])
    except (TypeError, ValueError):
        return new_severity

    if (n_min + offset) <= value <= (n_max - offset):
        return new_severity
    return old_severity


def _format_alert_message(key, value, severity, rule):
    label, unit = _get_sensor_label(key)
    value_str = f"{value:g}{unit}" if unit else f"{value:g}"

    healthy = rule.get('healthy', {})
    h_min = healthy.get('min')
    h_max = healthy.get('max')

    if h_min is not None and h_max is not None:
        try:
            normal_str = f"{float(h_min):g}–{float(h_max):g}{unit}"
            return f"{value_str} — di luar batas normal ({normal_str})"
        except (TypeError, ValueError):
            pass

    return f"{value_str} — di luar batas normal"


def _format_recovery_message(key, value):
    label, unit = _get_sensor_label(key)
    value_str = f"{value:g}{unit}" if unit else f"{value:g}"
    return f"kembali normal: {value_str}"


def _log_history(conn, device_id, alert_type, severity, message, value, action):
    try:
        conn.execute('''
            INSERT INTO alert_history
            (device_id, alert_type, severity, message, value, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, alert_type, severity, message, value, action, get_wib_time()))
    except Exception as e:
        logger.error(f"Failed to log alert history: {e}", exc_info=True)


def _build_notify_event(conn, device_id, alert_type, severity, message, value,
                        event_type, old_severity=None):
    try:
        device = conn.execute(
            'SELECT device_name, location FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        return {
            'event': event_type,
            'device_id': device_id,
            'device_name': device['device_name'] if device else device_id,
            'location': device['location'] if device else '',
            'alert_type': alert_type,
            'severity': severity,
            'old_severity': old_severity,
            'message': message,
            'value': value,
            'timestamp': get_wib_time().strftime('%Y-%m-%d %H:%M:%S WIB'),
        }
    except Exception as e:
        logger.warning(f"Failed to build notify event: {e}")
        return None


def _is_alert_acknowledged_and_not_recovered(conn, device_id, alert_type):
    """Return True jika alert terakhir untuk (device, type) di-ack user
    DAN belum ada 'cleared' setelahnya.

    Artinya user sudah acknowledge, tapi kondisi belum pulih ke healthy.
    Jangan re-trigger sampai device kirim nilai healthy (yang akan tercatat
    sebagai action='cleared').
    """
    last = conn.execute('''
        SELECT action FROM alert_history
        WHERE device_id = ? AND alert_type = ?
        ORDER BY created_at DESC, id DESC LIMIT 1
    ''', (device_id, alert_type)).fetchone()

    if not last:
        return False
    return last['action'] == 'acknowledged'


def _log_implicit_recovery_if_needed(conn, device_id, alert_type, value):
    last = conn.execute('''
        SELECT action FROM alert_history
        WHERE device_id = ? AND alert_type = ?
        ORDER BY created_at DESC LIMIT 1
    ''', (device_id, alert_type)).fetchone()

    if last and last['action'] == 'acknowledged':
        _log_history(conn, device_id, alert_type, 'healthy',
                     _format_recovery_message(alert_type, value),
                     value, 'cleared')


def get_device_alert_rules(conn, device_id):
    row = conn.execute(
        'SELECT alert_rules FROM devices WHERE device_id = ?',
        (device_id,)
    ).fetchone()

    if row and row['alert_rules']:
        try:
            parsed = json.loads(row['alert_rules'])
            if isinstance(parsed, dict) and parsed:
                valid_rules = {k: v for k, v in parsed.items() if _validate_rule(v)}
                if valid_rules:
                    return valid_rules
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Invalid alert_rules JSON for {device_id}: {e}")

    return _get_global_rules()


def check_and_create_alerts(device_id, sensor_data):
    if not isinstance(sensor_data, dict):
        return []

    changes = []
    pending_notifications = []

    with get_db_context() as conn:
        alert_rules = get_device_alert_rules(conn, device_id)

        for key, value in sensor_data.items():
            if key in ('uid', 'card_id', 'tag', 'rfid'):
                continue
            if key not in alert_rules:
                continue
            if isinstance(value, bool):
                continue
            if not isinstance(value, (int, float)):
                continue

            rule = alert_rules[key]
            new_severity, _ = _evaluate_severity(value, rule)
            if new_severity is None:
                continue

            existing = conn.execute('''
                SELECT id, severity, message, value FROM alerts
                WHERE device_id = ? AND alert_type = ? AND is_active = 1
            ''', (device_id, key)).fetchone()

            old_severity = existing['severity'] if existing else None
            final_severity = _apply_hysteresis(new_severity, old_severity, value, rule)

            # RECOVERY
            if final_severity == 'healthy':
                if existing:
                    conn.execute('''
                        UPDATE alerts SET is_active = 0, updated_at = ?, value = ?
                        WHERE id = ?
                    ''', (get_wib_time(), value, existing['id']))

                    recovery_msg = _format_recovery_message(key, value)
                    _log_history(conn, device_id, key, 'healthy', recovery_msg,
                                 value, 'cleared')
                    changes.append({'type': key, 'action': 'cleared',
                                    'severity': 'healthy', 'value': value})

                    evt = _build_notify_event(
                        conn, device_id, key, 'healthy', recovery_msg,
                        value, 'cleared', old_severity=existing['severity']
                    )
                    if evt:
                        pending_notifications.append(evt)
                else:
                    _log_implicit_recovery_if_needed(conn, device_id, key, value)
                continue

            # ALERT
            message = _format_alert_message(key, value, final_severity, rule)

            if existing:
                if existing['severity'] != final_severity:
                    conn.execute('''
                        UPDATE alerts
                        SET severity = ?, message = ?, value = ?, updated_at = ?
                        WHERE id = ?
                    ''', (final_severity, message, value, get_wib_time(), existing['id']))
                    _log_history(conn, device_id, key, final_severity, message,
                                 value, 'severity_changed')
                    changes.append({'type': key, 'action': 'severity_changed',
                                    'severity': final_severity,
                                    'old_severity': existing['severity'],
                                    'value': value})

                    evt = _build_notify_event(
                        conn, device_id, key, final_severity, message,
                        value, 'severity_changed', old_severity=existing['severity']
                    )
                    if evt:
                        pending_notifications.append(evt)
                else:
                    conn.execute('''
                        UPDATE alerts SET message = ?, value = ?, updated_at = ?
                        WHERE id = ?
                    ''', (message, value, get_wib_time(), existing['id']))
            else:
                # ✅ FIX: skip kalau sudah di-ack dan belum pulih
                if _is_alert_acknowledged_and_not_recovered(conn, device_id, key):
                    continue

                conn.execute('''
                    INSERT INTO alerts
                    (device_id, alert_type, severity, message, value,
                     is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ''', (device_id, key, final_severity, message, value,
                      get_wib_time(), get_wib_time()))
                _log_history(conn, device_id, key, final_severity, message,
                             value, 'created')
                changes.append({'type': key, 'action': 'created',
                                'severity': final_severity, 'value': value})

                evt = _build_notify_event(
                    conn, device_id, key, final_severity, message,
                    value, 'created', old_severity=None
                )
                if evt:
                    pending_notifications.append(evt)

        conn.commit()

    for evt in pending_notifications:
        try:
            notify_alert_event(evt)
        except Exception as e:
            logger.warning(f"Failed to enqueue notification: {e}")

    return changes


def create_offline_alert(device_id, severity='danger'):
    if severity not in ('info', 'warning', 'danger'):
        severity = 'danger'

    pending_notifications = []

    with get_db_context() as conn:
        existing = conn.execute('''
            SELECT id, severity FROM alerts
            WHERE device_id = ? AND alert_type = 'offline' AND is_active = 1
        ''', (device_id,)).fetchone()

        if existing:
            if existing['severity'] != severity:
                conn.execute('''
                    UPDATE alerts SET severity = ?, updated_at = ? WHERE id = ?
                ''', (severity, get_wib_time(), existing['id']))
                _log_history(conn, device_id, 'offline', severity,
                             f"Severity offline berubah ke {severity}", None, 'severity_changed')

                evt = _build_notify_event(
                    conn, device_id, 'offline', severity,
                    f"Perangkat offline dengan severity {severity}",
                    None, 'severity_changed', old_severity=existing['severity']
                )
                if evt:
                    pending_notifications.append(evt)

                conn.commit()
                for e in pending_notifications:
                    try:
                        notify_alert_event(e)
                    except Exception as e2:
                        logger.warning(f"Failed to enqueue notification: {e2}")
                return True
            return False

        # ✅ FIX: skip kalau sudah di-ack dan belum pulih
        if _is_alert_acknowledged_and_not_recovered(conn, device_id, 'offline'):
            return False

        message = "Perangkat tidak mengirim data melebihi batas waktu"
        conn.execute('''
            INSERT INTO alerts
            (device_id, alert_type, severity, message, is_active, created_at, updated_at)
            VALUES (?, 'offline', ?, ?, 1, ?, ?)
        ''', (device_id, severity, message, get_wib_time(), get_wib_time()))
        _log_history(conn, device_id, 'offline', severity, message, None, 'created')

        evt = _build_notify_event(
            conn, device_id, 'offline', severity, message, None, 'created'
        )
        if evt:
            pending_notifications.append(evt)

        conn.commit()

        for e in pending_notifications:
            try:
                notify_alert_event(e)
            except Exception as e2:
                logger.warning(f"Failed to enqueue notification: {e2}")
        return True


def clear_offline_alert(device_id):
    with get_db_context() as conn:
        result = conn.execute('''
            UPDATE alerts SET is_active = 0, updated_at = ?
            WHERE device_id = ? AND alert_type = 'offline' AND is_active = 1
        ''', (get_wib_time(), device_id))

        if result.rowcount > 0:
            _log_history(conn, device_id, 'offline', 'healthy',
                         'Perangkat kembali online', None, 'cleared')

            evt = _build_notify_event(
                conn, device_id, 'offline', 'healthy',
                'Perangkat kembali online', None, 'cleared', old_severity='danger'
            )

            conn.commit()

            if evt:
                try:
                    notify_alert_event(evt)
                except Exception as e:
                    logger.warning(f"Failed to enqueue notification: {e}")
            return True
    return False


def get_active_alerts(limit=100, severity=None, device_id=None):
    query = '''
        SELECT a.*, d.device_name, d.location, d.offline_timeout, d.expected_interval
        FROM alerts a
        JOIN devices d ON a.device_id = d.device_id
        WHERE a.is_active = 1 AND a.alert_type != 'uid'
    '''
    params = []
    if severity:
        query += ' AND a.severity = ?'
        params.append(severity)
    if device_id:
        query += ' AND a.device_id = ?'
        params.append(device_id)

    query += '''
        ORDER BY
            CASE a.severity
                WHEN 'danger' THEN 1 WHEN 'warning' THEN 2
                WHEN 'info' THEN 3 ELSE 4
            END,
            a.updated_at DESC, a.created_at DESC
        LIMIT ?
    '''
    params.append(limit)

    with get_db_context() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_alert_history(device_id=None, limit=200):
    with get_db_context() as conn:
        if device_id:
            rows = conn.execute('''
                SELECT * FROM alert_history WHERE device_id = ?
                ORDER BY created_at DESC LIMIT ?
            ''', (device_id, limit)).fetchall()
        else:
            rows = conn.execute('''
                SELECT h.*, d.device_name
                FROM alert_history h
                LEFT JOIN devices d ON h.device_id = d.device_id
                ORDER BY h.created_at DESC LIMIT ?
            ''', (limit,)).fetchall()
    return [dict(r) for r in rows]


def acknowledge_alert(alert_id):
    """Acknowledge alert.

    Menerima ID dari tabel `alerts` ATAU dari tabel `alert_history`
    (fallback, karena frontend lama mengirim history.id).
    """
    if alert_id is None:
        return False

    try:
        alert_id_int = int(alert_id)
    except (ValueError, TypeError):
        return False

    with get_db_context() as conn:
        alert = conn.execute(
            'SELECT * FROM alerts WHERE id = ?', (alert_id_int,)
        ).fetchone()

        # Fallback: mungkin ini history.id
        if not alert:
            hist = conn.execute(
                'SELECT device_id, alert_type FROM alert_history WHERE id = ?',
                (alert_id_int,)
            ).fetchone()
            if hist:
                alert = conn.execute('''
                    SELECT * FROM alerts
                    WHERE device_id = ? AND alert_type = ? AND is_active = 1
                    ORDER BY created_at DESC LIMIT 1
                ''', (hist['device_id'], hist['alert_type'])).fetchone()

        if not alert or not alert['is_active']:
            return False

        conn.execute(
            'UPDATE alerts SET is_active = 0, updated_at = ? WHERE id = ?',
            (get_wib_time(), alert['id'])
        )
        _log_history(conn, alert['device_id'], alert['alert_type'],
                     alert['severity'], alert['message'],
                     alert['value'], 'acknowledged')
        conn.commit()
        return True


def bulk_acknowledge_alerts(alert_ids):
    if not alert_ids:
        return 0

    count = 0
    with get_db_context() as conn:
        now = get_wib_time()
        for raw_id in alert_ids:
            try:
                alert_id = int(raw_id)
            except (ValueError, TypeError):
                continue

            alert = conn.execute(
                'SELECT * FROM alerts WHERE id = ? AND is_active = 1', (alert_id,)
            ).fetchone()

            # Fallback via history
            if not alert:
                hist = conn.execute(
                    'SELECT device_id, alert_type FROM alert_history WHERE id = ?',
                    (alert_id,)
                ).fetchone()
                if hist:
                    alert = conn.execute('''
                        SELECT * FROM alerts
                        WHERE device_id = ? AND alert_type = ? AND is_active = 1
                        ORDER BY created_at DESC LIMIT 1
                    ''', (hist['device_id'], hist['alert_type'])).fetchone()

            if not alert:
                continue

            conn.execute(
                'UPDATE alerts SET is_active = 0, updated_at = ? WHERE id = ?',
                (now, alert['id'])
            )
            _log_history(conn, alert['device_id'], alert['alert_type'],
                         alert['severity'], alert['message'],
                         alert['value'], 'acknowledged')
            count += 1
        conn.commit()

    return count