"""
NEXUS IoT - Background Tasks
Hanya satu worker yang menjalankan background tasks via file lock.
"""
import os
import sqlite3
import threading
import logging
from datetime import datetime, timedelta

from app.config import get_config
from app.database import get_db_context, get_wib_time
from app.utils import parse_datetime
from app.alerts import create_offline_alert, clear_offline_alert

logger = logging.getLogger('nexus')

# ✅ FIX #5: shutdown_event dibuat fresh setiap start, tidak global mutable
shutdown_event = threading.Event()
_bg_lock_file = None
_bg_lock_acquired = False
_bg_lock = threading.Lock()


def _log_status_change(conn, device_id, status, reason=''):
    try:
        conn.execute('''
            INSERT INTO device_status_log (device_id, status, reason, created_at)
            VALUES (?, ?, ?, ?)
        ''', (device_id, status, reason, get_wib_time()))
    except Exception as e:
        logger.error(f"Failed to log status change: {e}")


def check_device_status():
    config = get_config()
    logger.info(f"Status checker started (interval={config.CHECK_INTERVAL}s, "
                f"default_timeout={config.OFFLINE_TIMEOUT}s)")

    while not shutdown_event.is_set():
        try:
            current_time = get_wib_time()
            # Alert dibuat SETELAH koneksi ini commit & tutup. Sebelumnya
            # create_offline_alert() membuka koneksi kedua saat koneksi ini masih
            # menahan write-lock -> "database is locked" setelah 30 detik, dan alert
            # offline tidak pernah terbuat.
            to_offline = []   # (device_id, severity)
            to_online = []    # device_id

            with get_db_context() as conn:
                devices = conn.execute('''
                    SELECT device_id, last_seen, status,
                           offline_timeout, offline_alert_severity
                    FROM devices
                ''').fetchall()

                for device in devices:
                    device_id = device['device_id']
                    last_seen = device['last_seen']
                    current_status = device['status']

                    timeout = device['offline_timeout'] or config.OFFLINE_TIMEOUT
                    severity = device['offline_alert_severity'] or config.DEFAULT_OFFLINE_SEVERITY

                    if not last_seen:
                        if current_status != 'offline':
                            conn.execute('UPDATE devices SET status = ? WHERE device_id = ?',
                                         ('offline', device_id))
                            _log_status_change(conn, device_id, 'offline', 'never_seen')
                        continue

                    last_seen_dt = parse_datetime(last_seen)
                    if not last_seen_dt:
                        continue

                    time_diff = (current_time - last_seen_dt).total_seconds()

                    if time_diff > timeout and current_status != 'offline':
                        conn.execute('UPDATE devices SET status = ? WHERE device_id = ?',
                                     ('offline', device_id))
                        _log_status_change(conn, device_id, 'offline',
                                           f'timeout_{int(time_diff)}s')
                        logger.info(f"Device {device_id} OFFLINE")
                        to_offline.append((device_id, severity))

                    elif time_diff <= timeout and current_status == 'offline':
                        conn.execute('UPDATE devices SET status = ? WHERE device_id = ?',
                                     ('online', device_id))
                        _log_status_change(conn, device_id, 'online', 'recovered')
                        logger.info(f"Device {device_id} back online")
                        to_online.append(device_id)

                    elif current_status == 'offline' and time_diff > timeout:
                        # Self-healing: device sudah offline tapi alert untuk outage ini
                        # belum pernah dibuat (mis. gagal karena bug lock sebelumnya).
                        # Tidak membuat ulang alert yang sudah di-ack pada outage yang sama.
                        raised = conn.execute('''
                            SELECT 1 FROM alert_history
                            WHERE device_id = ? AND alert_type = 'offline'
                              AND action IN ('created', 'acknowledged')
                              AND created_at >= ?
                            LIMIT 1
                        ''', (device_id, last_seen)).fetchone()
                        if not raised:
                            to_offline.append((device_id, severity))

                conn.commit()

            # Koneksi sudah ditutup -> aman menulis alert lewat koneksi lain.
            for device_id, severity in to_offline:
                try:
                    create_offline_alert(device_id, severity)
                except Exception as e:
                    logger.error(f"Failed to create offline alert: {e}", exc_info=True)

            for device_id in to_online:
                try:
                    clear_offline_alert(device_id)
                except Exception as e:
                    logger.error(f"Failed to clear offline alert: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Status checker error: {e}", exc_info=True)

        shutdown_event.wait(config.CHECK_INTERVAL)

    logger.info("Status checker stopped")


def cleanup_old_data():
    """Cleanup data lama di 5 tabel dengan retention berbeda."""
    config = get_config()
    retention_sensor = config.DATA_RETENTION_DAYS
    retention_history = config.ALERT_HISTORY_RETENTION_DAYS
    retention_log = config.STATUS_LOG_RETENTION_DAYS
    retention_attendance = config.ATTENDANCE_RETENTION_DAYS

    logger.info(
        f"Data cleanup started "
        f"(sensor={retention_sensor}d, history={retention_history}d, "
        f"status_log={retention_log}d, attendance={retention_attendance}d)"
    )

    if shutdown_event.wait(300):
        logger.info("Data cleanup stopped (early shutdown)")
        return

    while not shutdown_event.is_set():
        try:
            now = get_wib_time()
            cutoff_sensor = now - timedelta(days=retention_sensor)
            cutoff_history = now - timedelta(days=retention_history)
            cutoff_log = now - timedelta(days=retention_log)
            cutoff_attendance = now - timedelta(days=retention_attendance)

            with get_db_context() as conn:
                total_deleted = 0
                results = {}

                r = conn.execute(
                    'DELETE FROM sensor_data WHERE timestamp < ?',
                    (cutoff_sensor,)
                )
                results['sensor_data'] = r.rowcount
                total_deleted += r.rowcount

                r = conn.execute(
                    'DELETE FROM alert_history WHERE created_at < ?',
                    (cutoff_history,)
                )
                results['alert_history'] = r.rowcount
                total_deleted += r.rowcount

                r = conn.execute(
                    'DELETE FROM device_status_log WHERE created_at < ?',
                    (cutoff_log,)
                )
                results['device_status_log'] = r.rowcount
                total_deleted += r.rowcount

                r = conn.execute(
                    'DELETE FROM attendance WHERE timestamp < ?',
                    (cutoff_attendance,)
                )
                results['attendance'] = r.rowcount
                total_deleted += r.rowcount

                r = conn.execute(
                    '''DELETE FROM alerts
                       WHERE is_active = 0
                       AND updated_at IS NOT NULL
                       AND updated_at < ?''',
                    (cutoff_history,)
                )
                results['alerts_inactive'] = r.rowcount
                total_deleted += r.rowcount

                conn.commit()

                if total_deleted > 0:
                    details = ', '.join(
                        f"{k}={v}" for k, v in results.items() if v > 0
                    )
                    logger.info(f"Cleaned up {total_deleted} records: {details}")

                if total_deleted > 1000:
                    logger.info("Running VACUUM to reclaim space...")
                    conn.execute('VACUUM')
                    logger.info("VACUUM complete")

        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)

        shutdown_event.wait(86400)

    logger.info("Data cleanup stopped")


def backup_database():
    config = get_config()
    if not config.BACKUP_ENABLED:
        logger.info("Backup disabled")
        return

    logger.info(f"Backup started (interval={config.BACKUP_INTERVAL_HOURS}h)")

    if shutdown_event.wait(600):
        logger.info("Backup task stopped (early shutdown)")
        return

    while not shutdown_event.is_set():
        try:
            os.makedirs(config.BACKUP_DIR, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(config.BACKUP_DIR, f'iot_{timestamp}.db')

            source = sqlite3.connect(config.DB_PATH, timeout=30.0)
            dest = sqlite3.connect(backup_path)
            with dest:
                source.backup(dest)
            dest.close()
            source.close()

            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            logger.info(f"Backup created: {backup_path} ({size_mb:.2f} MB)")

            cutoff_ts = datetime.now().timestamp() - (config.BACKUP_RETENTION_DAYS * 86400)
            for filename in os.listdir(config.BACKUP_DIR):
                filepath = os.path.join(config.BACKUP_DIR, filename)
                if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff_ts:
                    os.remove(filepath)
                    logger.info(f"Old backup removed: {filename}")
        except Exception as e:
            logger.error(f"Backup failed: {e}", exc_info=True)
        shutdown_event.wait(config.BACKUP_INTERVAL_HOURS * 3600)

    logger.info("Backup task stopped")


def _acquire_background_lock():
    """Acquire exclusive file lock. Return True jika berhasil."""
    global _bg_lock_file, _bg_lock_acquired
    import fcntl

    with _bg_lock:
        if _bg_lock_acquired:
            logger.info("Background lock already held by this process")
            return False

        config = get_config()
        if not config.BACKGROUND_TASKS_ENABLED:
            logger.info("Background tasks disabled via BACKGROUND_TASKS_ENABLED=False")
            return False

        lock_dir = os.environ.get('NEXUS_LOCK_DIR', '/tmp')
        try:
            os.makedirs(lock_dir, exist_ok=True)
        except Exception:
            lock_dir = '/tmp'

        lock_path = os.path.join(lock_dir, 'nexus-background.lock')

        try:
            _bg_lock_file = open(lock_path, 'w')
            fcntl.flock(_bg_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _bg_lock_file.write(f"pid={os.getpid()}\n")
            _bg_lock_file.flush()
            _bg_lock_acquired = True
            logger.info(f"Background lock acquired (pid={os.getpid()})")
            return True
        except (IOError, OSError):
            if _bg_lock_file is not None:
                try:
                    _bg_lock_file.close()
                except Exception:
                    pass
                _bg_lock_file = None
            logger.info("Background lock held by another worker, skipping")
            return False


# ✅ FIX #5: reset shutdown_event sebelum start, dan guard double-start
def start_background_tasks():
    global shutdown_event

    with _bg_lock:
        # Reset event setiap start — fix untuk reload Gunicorn
        shutdown_event = threading.Event()

    if not _acquire_background_lock():
        return []

    threads = []
    for target, name in [
        (check_device_status, 'status-checker'),
        (cleanup_old_data, 'data-cleanup'),
        (backup_database, 'db-backup'),
    ]:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        threads.append(t)

    logger.info(f"Started {len(threads)} background tasks (this worker owns the lock)")
    return threads


def stop_background_tasks():
    global _bg_lock_file, _bg_lock_acquired
    logger.info("Stopping background tasks...")
    shutdown_event.set()

    with _bg_lock:
        if _bg_lock_file is not None:
            try:
                import fcntl
                fcntl.flock(_bg_lock_file, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                _bg_lock_file.close()
            except Exception:
                pass
            _bg_lock_file = None
        _bg_lock_acquired = False