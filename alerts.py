"""
NEXUS IoT - Alert System
Dynamic per-device rules + severity levels + history + hysteresis + notifikasi Telegram.

State machine:
    healthy → warning → danger → warning → healthy
Setiap transisi UPDATE baris yang sama, tidak INSERT baru.

✅ P1-C: integrasi notifikasi Telegram via notifier.notify_alert_event()
"""

import json
import logging
from config import get_config
from database import get_db_context, get_wib_time
from notifier import notify_alert_event

logger = logging.getLogger('nexus')

# Urutan cek: dari paling ringan (healthy) ke paling berat (danger).
SEVERITY_ORDER = ['healthy', 'warning', 'danger']
VALID_SEVERITIES = ['healthy', 'info', 'warning', 'danger']

# Hysteresis default: nilai harus melewati batas sebesar `offset` sebelum
# transisi antar severity. Mencegah flicker saat nilai fluktuasi di batas.
DEFAULT_HYSTERESIS = 0.5


def _get_global_rules():
    config = get_config()
    return {k: v for k, v in config.ALERT_RULES.items() if isinstance(v, dict)}


def _validate_rule(rule):
    """Validasi struktur rule. Return True jika valid."""
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
    """
    ✅ FIX: Evaluasi severity berdasarkan range dari yang paling sempit.

    Logika:
        1. Jika nilai di dalam range 'healthy' → healthy
        2. Jika nilai di luar healthy tapi di dalam 'warning' → warning
        3. Jika nilai di luar warning tapi di dalam 'danger' → danger
        4. Jika nilai di luar semua range → danger (paling parah)
    """
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
                return 'warning', f"nilai {value:g} di luar batas normal ({_fmt(rule.get('healthy'))})"
            elif severity == 'danger':
                return 'danger', f"nilai {value:g} di luar batas peringatan ({_fmt(rule.get('warning'))})"

    return 'danger', f"nilai {value:g} di luar semua batas yang ditentukan"


def _fmt(rng):
    if not rng:
        return "?"
    return f"{rng.get('min', '?')}-{rng.get('max', '?')}"


def _severity_rank(sev):
    """Rank lebih tinggi = lebih parah."""
    return {'healthy': 0, 'info': 1, 'warning': 2, 'danger': 3}.get(sev, 0)


def _apply_hysteresis(new_severity, old_severity, value, rule):
    """✅ HYSTERESIS: Cegah flicker saat nilai fluktuasi di batas."""
    if not old_severity or old_severity == new_severity:
        return new_severity

    old_rank = _severity_rank(old_severity)
    new_rank = _severity_rank(new_severity)

    # Kalau naik severity, langsung apply
    if new_rank > old_rank:
        return new_severity

    # Kalau turun severity, cek hysteresis
    offset = float(rule.get('_hysteresis', DEFAULT_HYSTERESIS))

    old_range = rule.get(old_severity)
    if not old_range:
        return new_severity

    try:
        rmin = float(old_range['min'])
        rmax = float(old_range['max'])
    except (TypeError, ValueError):
        return new_severity

    if (rmin - offset) <= value <= (rmax + offset):
        return old_severity

    return new_severity


def _log_history(conn, device_id, alert_type, severity, message, value, action, reason=''):
    """Catat perubahan alert ke history untuk audit trail."""
    try:
        conn.execute('''
            INSERT INTO alert_history
            (device_id, alert_type, severity, message, value, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, alert_type, severity, message, value, action, get_wib_time()))
    except Exception as e:
        logger.error(f"Failed to log alert history: {e}", exc_info=True)


def _notify_event(conn, device_id, alert_type, severity, message, value,
                  event_type, old_severity=None):
    """
    ✅ P1-C: Kirim notifikasi alert ke Telegram.
    Wrap di try/except supaya kegagalan notifikasi tidak bikin alert gagal.
    """
    try:
        device = conn.execute(
            'SELECT device_name, location FROM devices WHERE device_id = ?',
            (device_id,)
        ).fetchone()

        device_name = device['device_name'] if device else device_id
        location = device['location'] if device else ''

        event = {
            'event': event_type,
            'device_id': device_id,
            'device_name': device_name,
            'location': location,
            'alert_type': alert_type,
            'severity': severity,
            'old_severity': old_severity,
            'message': message,
            'value': value,
            'timestamp': get_wib_time().strftime('%Y-%m-%d %H:%M:%S WIB'),
        }

        notify_alert_event(event)
    except Exception as e:
        logger.warning(f"Failed to enqueue notification: {e}")


def get_device_alert_rules(conn, device_id):
    """Ambil rule alert untuk device. Fallback ke global jika tidak ada custom."""
    row = conn.execute(
        'SELECT alert_rules FROM devices WHERE device_id = ?',
        (device_id,)
    ).fetchone()

    if row and row['alert_rules']:
        try:
            parsed = json.loads(row['alert_rules'])
            if isinstance(parsed, dict) and parsed:
                valid_rules = {}
                for key, rule in parsed.items():
                    if _validate_rule(rule):
                        valid_rules[key] = rule
                    else:
                        logger.warning(f"Invalid rule for {device_id}.{key}, skipping")
                if valid_rules:
                    return valid_rules
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Invalid alert_rules JSON for {device_id}: {e}")

    return _get_global_rules()


def check_and_create_alerts(device_id, sensor_data):
    """
    Cek nilai sensor terhadap rule dan kelola state alert.

    ✅ Konsep state machine:
        - Satu device + satu sensor hanya punya SATU alert aktif.
        - Severity berubah → UPDATE baris yang sama.
        - Pulih ke healthy → set is_active = 0 (clear).
        - Nilai sama & severity sama → hanya update value & timestamp.

    ✅ P1-C: setiap transisi (created / severity_changed / cleared)
             mengirim notifikasi ke Telegram.

    Return: list perubahan alert untuk logging.
    """
    if not isinstance(sensor_data, dict):
        return []

    changes = []

    with get_db_context() as conn:
        alert_rules = get_device_alert_rules(conn, device_id)

        for key, value in sensor_data.items():
            # Skip field yang bukan sensor
            if key in ('uid', 'card_id', 'tag', 'rfid'):
                continue
            if key not in alert_rules:
                continue
            if not isinstance(value, (int, float)):
                continue

            rule = alert_rules[key]
            new_severity, reason = _evaluate_severity(value, rule)

            if new_severity is None:
                continue

            # Cari alert aktif untuk device+sensor ini
            existing = conn.execute('''
                SELECT id, severity, message, value FROM alerts
                WHERE device_id = ? AND alert_type = ? AND is_active = 1
            ''', (device_id, key)).fetchone()

            old_severity = existing['severity'] if existing else None

            # ✅ Apply hysteresis
            final_severity = _apply_hysteresis(new_severity, old_severity, value, rule)

            # === KASUS 1: Nilai healthy (clear alert) ===
            if final_severity == 'healthy':
                if existing:
                    conn.execute('''
                        UPDATE alerts
                        SET is_active = 0, updated_at = ?, value = ?
                        WHERE id = ?
                    ''', (get_wib_time(), value, existing['id']))
                    _log_history(conn, device_id, key, 'healthy',
                                 f"{key} kembali normal: {value:g}",
                                 value, 'cleared')
                    logger.info(f"✅ Alert cleared for {device_id}: {key}={value}")
                    changes.append({
                        'type': key, 'action': 'cleared',
                        'severity': 'healthy', 'value': value,
                    })

                    # ✅ P1-C: notifikasi
                    _notify_event(conn, device_id, key, 'healthy',
                                  f"{key} kembali normal: {value:g}",
                                  value, 'cleared',
                                  old_severity=existing['severity'])
                continue

            # === KASUS 2: Nilai alert (warning/danger/info) ===
            message = f"{key}={value:g} — {reason or 'di luar batas normal'}"

            if existing:
                if existing['severity'] != final_severity:
                    # Upgrade/downgrade severity: UPDATE baris yang sama
                    conn.execute('''
                        UPDATE alerts
                        SET severity = ?, message = ?, value = ?, updated_at = ?
                        WHERE id = ?
                    ''', (final_severity, message, value, get_wib_time(), existing['id']))
                    _log_history(conn, device_id, key, final_severity, message,
                                 value, 'severity_changed')
                    direction = 'upgraded' if _severity_rank(final_severity) > _severity_rank(existing['severity']) else 'downgraded'
                    logger.warning(
                        f"⚠️  Alert {direction} for {device_id}: "
                        f"{key} ({existing['severity']} → {final_severity})"
                    )
                    changes.append({
                        'type': key, 'action': 'severity_changed',
                        'severity': final_severity,
                        'old_severity': existing['severity'],
                        'value': value,
                    })

                    # ✅ P1-C: notifikasi
                    _notify_event(conn, device_id, key, final_severity,
                                  message, value, 'severity_changed',
                                  old_severity=existing['severity'])
                else:
                    # Severity sama → hanya update value & timestamp
                    conn.execute('''
                        UPDATE alerts
                        SET message = ?, value = ?, updated_at = ?
                        WHERE id = ?
                    ''', (message, value, get_wib_time(), existing['id']))
            else:
                # Alert baru: INSERT
                conn.execute('''
                    INSERT INTO alerts
                    (device_id, alert_type, severity, message, value,
                     is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ''', (device_id, key, final_severity, message, value,
                      get_wib_time(), get_wib_time()))
                _log_history(conn, device_id, key, final_severity, message,
                             value, 'created')
                logger.warning(
                    f"🚨 [{final_severity.upper()}] Alert created for "
                    f"{device_id}: {message}"
                )
                changes.append({
                    'type': key, 'action': 'created',
                    'severity': final_severity, 'value': value,
                })

                # ✅ P1-C: notifikasi
                _notify_event(conn, device_id, key, final_severity,
                              message, value, 'created', old_severity=None)

        conn.commit()

    return changes


def create_offline_alert(device_id, severity='danger'):
    """Buat alert offline. Idempotent: hanya 1 alert offline aktif per device."""
    if severity not in ('info', 'warning', 'danger'):
        severity = 'danger'

    with get_db_context() as conn:
        existing = conn.execute('''
            SELECT id, severity FROM alerts
            WHERE device_id = ? AND alert_type = 'offline' AND is_active = 1
        ''', (device_id,)).fetchone()

        if existing:
            if existing['severity'] != severity:
                conn.execute('''
                    UPDATE alerts
                    SET severity = ?, updated_at = ?
                    WHERE id = ?
                ''', (severity, get_wib_time(), existing['id']))
                _log_history(conn, device_id, 'offline', severity,
                             f"Severity offline berubah ke {severity}",
                             None, 'severity_changed')
                conn.commit()
                logger.warning(f"Offline alert severity changed for {device_id}: → {severity}")

                # ✅ P1-C: notifikasi
                _notify_event(conn, device_id, 'offline', severity,
                              f"Perangkat offline dengan severity {severity}",
                              None, 'severity_changed',
                              old_severity=existing['severity'])
                return True
            return False

        message = "Perangkat tidak mengirim data melebihi batas waktu yang ditentukan"
        conn.execute('''
            INSERT INTO alerts
            (device_id, alert_type, severity, message, is_active, created_at, updated_at)
            VALUES (?, 'offline', ?, ?, 1, ?, ?)
        ''', (device_id, severity, message, get_wib_time(), get_wib_time()))

        _log_history(conn, device_id, 'offline', severity, message, None, 'created')
        conn.commit()
        logger.warning(f"📴 [{severity.upper()}] Offline alert created for {device_id}")

        # ✅ P1-C: notifikasi
        _notify_event(conn, device_id, 'offline', severity,
                      message, None, 'created', old_severity=None)
        return True


def clear_offline_alert(device_id):
    """Clear alert offline saat device kembali online. Idempotent."""
    with get_db_context() as conn:
        result = conn.execute('''
            UPDATE alerts
            SET is_active = 0, updated_at = ?
            WHERE device_id = ? AND alert_type = 'offline' AND is_active = 1
        ''', (get_wib_time(), device_id))

        if result.rowcount > 0:
            _log_history(conn, device_id, 'offline', 'healthy',
                         'Perangkat kembali online', None, 'cleared')
            conn.commit()
            logger.info(f"✅ Offline alert cleared for {device_id}")

            # ✅ P1-C: notifikasi
            _notify_event(conn, device_id, 'offline', 'healthy',
                          'Perangkat kembali online', None, 'cleared',
                          old_severity='danger')
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
                WHEN 'danger' THEN 1
                WHEN 'warning' THEN 2
                WHEN 'info' THEN 3
                ELSE 4
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
                SELECT * FROM alert_history
                WHERE device_id = ?
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
    with get_db_context() as conn:
        alert = conn.execute('SELECT * FROM alerts WHERE id = ?', (alert_id,)).fetchone()
        if not alert or not alert['is_active']:
            return False

        conn.execute('''
            UPDATE alerts SET is_active = 0, updated_at = ? WHERE id = ?
        ''', (get_wib_time(), alert_id))

        _log_history(conn, alert['device_id'], alert['alert_type'],
                     alert['severity'], alert['message'],
                     alert['value'], 'acknowledged')
        conn.commit()
        logger.info(f"Alert {alert_id} acknowledged for {alert['device_id']}")
        return True


def bulk_acknowledge_alerts(alert_ids):
    if not alert_ids:
        return 0

    count = 0
    with get_db_context() as conn:
        now = get_wib_time()
        for alert_id in alert_ids:
            alert = conn.execute(
                'SELECT * FROM alerts WHERE id = ? AND is_active = 1',
                (alert_id,)
            ).fetchone()
            if not alert:
                continue

            conn.execute('''
                UPDATE alerts SET is_active = 0, updated_at = ? WHERE id = ?
            ''', (now, alert_id))

            _log_history(conn, alert['device_id'], alert['alert_type'],
                         alert['severity'], alert['message'],
                         alert['value'], 'acknowledged')
            count += 1

        conn.commit()

    logger.info(f"Bulk acknowledged {count} alerts")
    return count


def get_alert_summary():
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT severity, COUNT(*) as count
            FROM alerts
            WHERE is_active = 1 AND alert_type != 'uid'
            GROUP BY severity
        ''').fetchall()

    summary = {'danger': 0, 'warning': 0, 'info': 0, 'total': 0}
    for row in rows:
        if row['severity'] in summary:
            summary[row['severity']] = row['count']
        summary['total'] += row['count']
    return summary