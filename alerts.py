"""
NEXUS IoT - Alert System
"""
import logging
from config import get_config
from database import get_db_context

logger = logging.getLogger('nexus')


def check_and_create_alerts(device_id, sensor_data):
    """Cek data sensor dan buat/clear alert sesuai threshold"""
    config = get_config()
    alert_rules = config.ALERT_RULES
    created_alerts = []

    if not isinstance(sensor_data, dict):
        return created_alerts

    with get_db_context() as conn:
        for key, value in sensor_data.items():
            if key not in alert_rules:
                continue

            rule = alert_rules[key]
            if not isinstance(value, (int, float)):
                continue

            is_out_of_range = value < rule['min'] or value > rule['max']

            if is_out_of_range:
                existing = conn.execute('''
                    SELECT id FROM alerts
                    WHERE device_id = ? AND alert_type = ? AND is_active = 1
                ''', (device_id, key)).fetchone()

                if not existing:
                    message = (
                        f"{rule['message']}: {key}={value} "
                        f"(normal: {rule['min']}-{rule['max']})"
                    )
                    conn.execute('''
                        INSERT INTO alerts (device_id, alert_type, message, is_active)
                        VALUES (?, ?, ?, 1)
                    ''', (device_id, key, message))
                    created_alerts.append(key)
                    logger.warning(f"Alert created for {device_id}: {message}")
            else:
                result = conn.execute('''
                    UPDATE alerts SET is_active = 0
                    WHERE device_id = ? AND alert_type = ? AND is_active = 1
                ''', (device_id, key))
                if result.rowcount > 0:
                    logger.info(f"Alert cleared for {device_id}: {key}")

        conn.commit()

    return created_alerts


def get_active_alerts(limit=100):
    """Ambil semua alert aktif"""
    with get_db_context() as conn:
        rows = conn.execute('''
            SELECT a.*, d.device_name
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            WHERE a.is_active = 1
            ORDER BY a.created_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
    return [dict(r) for r in rows]