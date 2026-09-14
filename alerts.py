"""
NEXUS IoT - Alert System (Dynamic per-device rules)

Format alert_rules di devices.alert_rules (JSON):
{
  "temperature": {
    "healthy": {"min": 6, "max": 28},
    "warning": {"min": 0, "max": 32},
    "danger":  {"min": -10, "max": 40}
  },
  "humidity": {...}
}

Aturan evaluasi:
- Cek dari severity tertinggi (danger) ke terendah (healthy)
- Kalau value masuk range danger -> severity = danger
- Kalau tidak, cek warning, lalu info
- Kalau value masuk healthy -> alert clear
- Kalau di luar healthy tapi tidak masuk warning/danger -> warning
"""
import json
import logging
from config import get_config
from database import get_db_context, get_wib_time

logger = logging.getLogger('nexus')

# Urutan severity dari paling bahaya
SEVERITY_PRIORITY = ['danger', 'warning', 'info']
VALID_SEVERITIES = ['healthy', 'info', 'warning', 'danger']


# ==========================================
# HELPERS
# ==========================================
def _get_global_rules():
    """Build fallback rules dari config global"""
    config = get_config()
    return {
        key: value
        for key, value in config.ALERT_RULES.items()
        if isinstance(value, dict)
    }


def _validate_rule(rule):
    """Validasi struktur rule: {severity: {min, max}}"""
    if not isinstance(rule, dict):
        return False
    for severity, range_dict in rule.items():
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
    Tentukan severity berdasarkan value & rule.
    Return: (severity, reason) atau (None, None)
    """
    if not _validate_rule(rule):
        return None, None

    # Cek dari paling bahaya
    for severity in SEVERITY_PRIORITY:
        r = rule.get(severity)
        if not r:
            continue
        rmin = float(r['min'])
        rmax = float(r['max'])
        if value < rmin or value > rmax:
            return severity, f"di luar batas {severity.upper()} ({rmin:g}-{rmax:g})"

    # Cek healthy
    healthy = rule.get('healthy')
    if healthy:
        hmin = float(healthy['min'])
        hmax = float(healthy['max'])
        if value < hmin or value > hmax:
            return 'warning', f"di luar batas normal ({hmin:g}-{hmax:g})"

    return 'healthy', None


# ==========================================
# DEVICE RULES
# ==========================================
def get_device_alert_rules(conn, device_id):
    """
    Ambil alert_rules per device.
    Fallback ke global config kalau device.alert_rules NULL/invalid.
    """
    row = conn.execute(
        'SELECT alert_rules FROM devices WHERE device_id = ?',
        (device_id,)
    ).fetchone()

    if row and row['alert_rules']:
        try:
            parsed = json.loads(row['alert_rules'])
            if isinstance(parsed, dict) and parsed:
                # Validasi tiap rule
                valid_rules = {}
                for key, rule in parsed.items():
                    if _validate_rule(rule):
                        valid_rules[key] = rule
                    else:
                        logger.warning(
                            f"Invalid rule for {device_id}.{key}, skipping"
                        )
                if valid_rules:
                    return valid_rules
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Invalid alert_rules JSON for {device_id}: {e}")

    return _get_global_rules()


# ==========================================
# HISTORY LOGGING
# ==========================================
def _log_history(conn, device_id, alert_type, severity, message, value, action):
    """Catat perubahan alert ke alert_history"""
    try:
        conn.execute('''
            INSERT INTO alert_history
            (device_id, alert_type, severity, message, value, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_id, alert_type, severity, message, value, action, get_wib_time()))
    except Exception as e:
        logger.error(f"Failed to log alert history: {e}", exc_info=True)


# ==========================================
# MAIN ALERT CHECKER
# ==========================================
def check_and_create_alerts(device_id, sensor_data):
    """
    Cek data sensor dan buat/update/clear alert.
    Return: list of created alerts info.
    """
    if not isinstance(sensor_data, dict):
        return []

    created_alerts = []

    with get_db_context() as conn:
        alert_rules = get_device_alert_rules(conn, device_id)

        for key, value in sensor_data.items():
            if key not in alert_rules:
                continue
            if not isinstance(value, (int, float)):
                continue

            rule = alert_rules[key]
            severity, reason = _evaluate_severity(value, rule)

            if severity is None:
                continue

            # Cari alert aktif
            existing = conn.execute('''
                SELECT id, severity FROM alerts
                WHERE device_id = ? AND alert_type = ? AND is_active = 1
            ''', (device_id, key)).fetchone()

            # ───── CASE 1: HEALTHY → clear alert ─────
            if severity == 'healthy':
                if existing:
                    conn.execute('''
                        UPDATE alerts
                        SET is_active = 0, updated_at = ?
                        WHERE id = ?
                    ''', (get_wib_time(), existing['id']))

                    _log_history(
                        conn, device_id, key, 'healthy',
                        f"{key} kembali normal: {value}",
                        value, 'cleared'
                    )
                    logger.info(f"Alert cleared for {device_id}: {key}={value}")
                    created_alerts.append({
                        'type': key,
                        'action': 'cleared',
                        'severity': 'healthy',
                        'value': value,
                    })
                continue

            # ───── CASE 2: ADA ALERT AKTIF ─────
            message = f"{key}={value} — {reason}"

            if existing:
                if existing['severity'] != severity:
                    # Severity berubah → update
                    conn.execute('''
                        UPDATE alerts
                        SET severity = ?, message = ?, value = ?, updated_at = ?
                        WHERE id = ?
                    ''', (severity, message, value, get_wib_time(), existing['id']))

                    _log_history(
                        conn, device_id, key, severity, message,
                        value, f"severity_changed_from_{existing['severity']}"
                    )
                    logger.warning(
                        f"Alert severity changed for {device_id}: "
                        f"{key} ({existing['severity']} -> {severity})"
                    )
                    created_alerts.append({
                        'type': key,
                        'action': 'updated',
                        'severity': severity,
                        'old_severity': existing['severity'],
                        'value': value,
                    })
                else:
                    # Severity sama → cuma update value
                    conn.execute('''
                        UPDATE alerts
                        SET message = ?, value = ?, updated_at = ?
                        WHERE id = ?
                    ''', (message, value, get_wib_time(), existing['id']))

            # ───── CASE 3: BUAT ALERT BARU ─────
            else:
                conn.execute('''
                    INSERT INTO alerts
                    (device_id, alert_type, severity, message, value,
                     is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ''', (device_id, key, severity, message, value,
                      get_wib_time(), get_wib_time()))

                _log_history(
                    conn, device_id, key, severity, message,
                    value, 'created'
                )
                logger.warning(
                    f"[{severity.upper()}] Alert created for {device_id}: {message}"
                )
                created_alerts.append({
                    'type': key,
                    'action': 'created',
                    'severity': severity,
                    'value': value,
                })

        conn.commit()

    return created_alerts


# ==========================================
# OFFLINE ALERT
# ==========================================
def create_offline_alert(device_id, severity='danger'):
    """Buat offline alert kalau belum ada"""
    if severity not in ['info', 'warning', 'danger']:
        severity = 'danger'

    with get_db_context() as conn:
        existing = conn.execute('''
            SELECT id FROM alerts
            WHERE device_id = ? AND alert_type = 'offline' AND is_active = 1
        ''', (device_id,)).fetchone()

        if existing:
            return False

        message = "Perangkat tidak mengirim data melebihi batas waktu yang ditentukan"
        conn.execute('''
            INSERT INTO alerts
            (device_id, alert_type, severity, message, is_active, created_at, updated_at)
            VALUES (?, 'offline', ?, ?, 1, ?, ?)
        ''', (device_id, severity, message, get_wib_time(), get_wib_time()))

        _log_history(
            conn, device_id, 'offline', severity, message,
            None, 'created'
        )
        conn.commit()

        logger.warning(f"[{severity.upper()}] Offline alert created for {device_id}")
        return True


def clear_offline_alert(device_id):
    """Clear offline alert saat device kembali online"""
    with get_db_context() as conn:
        result = conn.execute('''
            UPDATE alerts
            SET is_active = 0, updated_at = ?
            WHERE device_id = ? AND alert_type = 'offline' AND is_active = 1
        ''', (get_wib_time(), device_id))

        if result.rowcount > 0:
            _log_history(
                conn, device_id, 'offline', 'healthy',
                'Perangkat kembali online', None, 'cleared'
            )
            conn.commit()
            logger.info(f"Offline alert cleared for {device_id}")
            return True

    return False


# ==========================================
# QUERIES
# ==========================================
def get_active_alerts(limit=100, severity=None, device_id=None):
    """Ambil alert aktif, diurutkan dari severity paling bahaya"""
    query = '''
        SELECT a.*, d.device_name, d.location, d.offline_timeout,
               d.expected_interval
        FROM alerts a
        JOIN devices d ON a.device_id = d.device_id
        WHERE a.is_active = 1
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
            a.updated_at DESC,
            a.created_at DESC
        LIMIT ?
    '''
    params.append(limit)

    with get_db_context() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


def get_alert_history(device_id=None, limit=200):
    """Ambil history alert"""
    with get_db_context() as conn:
        if device_id:
            rows = conn.execute('''
                SELECT * FROM alert_history
                WHERE device_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (device_id, limit)).fetchall()
        else:
            rows = conn.execute('''
                SELECT h.*, d.device_name
                FROM alert_history h
                JOIN devices d ON h.device_id = d.device_id
                ORDER BY h.created_at DESC
                LIMIT ?
            ''', (limit,)).fetchall()

    return [dict(r) for r in rows]


def acknowledge_alert(alert_id):
    """Tandai alert sudah dibaca (nonaktifkan)"""
    with get_db_context() as conn:
        result = conn.execute('''
            UPDATE alerts
            SET is_active = 0, updated_at = ?
            WHERE id = ? AND is_active = 1
        ''', (get_wib_time(), alert_id))
        conn.commit()

        if result.rowcount > 0:
            alert = conn.execute(
                'SELECT * FROM alerts WHERE id = ?', (alert_id,)
            ).fetchone()
            if alert:
                _log_history(
                    conn, alert['device_id'], alert['alert_type'],
                    alert['severity'], alert['message'],
                    alert['value'], 'acknowledged'
                )
                conn.commit()
            return True

    return False


def get_alert_summary():
    """Ringkasan alert per severity"""
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT severity, COUNT(*) as count
            FROM alerts
            WHERE is_active = 1
            GROUP BY severity
        ''').fetchall()

    summary = {'danger': 0, 'warning': 0, 'info': 0, 'total': 0}
    for row in rows:
        if row['severity'] in summary:
            summary[row['severity']] = row['count']
        summary['total'] += row['count']
    return summary