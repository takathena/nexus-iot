"""
NEXUS IoT - Background Tasks

✅ P0 FIX: hanya SATU proses/worker yang menjalankan background tasks.
Menggunakan file lock (fcntl.flock). Worker lain otomatis skip.

Ini mencegah:
  - Offline alert dibuat berkali-kali
  - Backup database ganda
  - Cleanup berjalan bersamaan
"""
import os
import sqlite3
import threading
import logging
from datetime import datetime, timedelta

from config import get_config
from database import get_db_context, get_wib_time
from utils import parse_datetime
from alerts import create_offline_alert, clear_offline_alert

logger = logging.getLogger('nexus')

shutdown_event = threading.Event()
_bg_lock_file = None          # ✅ P0: file handle untuk lock
_bg_lock_acquired = False     # ✅ P0 FIX: cegah double-acquire di process yang sama


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
            with get_db_context() as conn:
                devices = conn.execute('''
                    SELECT device_id, last_seen, status,
                           offline_timeout, offline_alert_severity,
                           expected_interval
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
                        logger.info(f"Device {device_id} OFFLINE (last seen {int(time_diff)}s ago)")
                        try:
                            create_offline_alert(device_id, severity)
                        except Exception as e:
                            logger.error(f"Failed to create offline alert: {e}", exc_info=True)

                    elif time_diff <= timeout and current_status == 'offline':
                        conn.execute('UPDATE devices SET status = ? WHERE device_id = ?',
                                     ('online', device_id))
                        _log_status_change(conn, device_id, 'online', 'recovered')
                        logger.info(f"Device {device_id} back online")
                        try:
                            clear_offline_alert(device_id)
                        except Exception as e:
                            logger.error(f"Failed to clear offline alert: {e}", exc_info=True)

                conn.commit()

        except Exception as e:
            logger.error(f"Status checker error: {e}", exc_info=True)

        shutdown_event.wait(config.CHECK_INTERVAL)

    logger.info("Status checker stopped")


def cleanup_old_data():
    config = get_config()
    logger.info(f"Data cleanup started (retention={config.DATA_RETENTION_DAYS} days)")

    if shutdown_event.wait(300):
        logger.info("Data cleanup stopped (early shutdown)")
        return

    while not shutdown_event.is_set():
        try:
            cutoff = get_wib_time() - timedelta(days=config.DATA_RETENTION_DAYS)
            with get_db_context() as conn:
                result = conn.execute('DELETE FROM sensor_data WHERE timestamp < ?',
                                      (cutoff,))
                deleted = result.rowcount
                conn.commit()
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old sensor records")
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
    """
    ✅ P0 FIX: Acquire exclusive file lock.
    Return True kalau lock berhasil didapat (kita jadi satu-satunya process
    yang menjalankan background tasks).
    """
    global _bg_lock_file, _bg_lock_acquired
    import fcntl

    # ✅ Guard: kalau sudah pernah acquire di process ini, jangan acquire lagi.
    if _bg_lock_acquired:
        logger.info("Background lock already held by this process, skipping re-acquire")
        return False

    config = get_config()
    if not config.BACKGROUND_TASKS_ENABLED:
        logger.info("Background tasks disabled via BACKGROUND_TASKS_ENABLED=False")
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
        _bg_lock_acquired = True   # ✅ tandai sudah acquire
        logger.info(f"Background lock acquired (pid={os.getpid()})")
        return True
    except (IOError, OSError):
        if _bg_lock_file is not None:
            try:
                _bg_lock_file.close()
            except Exception:
                pass
            _bg_lock_file = None
        logger.info("Background lock held by another worker, skipping background tasks")
        return False


def start_background_tasks():
    """
    ✅ P0 FIX: hanya worker pertama (yang dapat lock) yang start background threads.
    """
    if not _acquire_background_lock():
        return []

    threads = []
    t1 = threading.Thread(target=check_device_status, name='status-checker', daemon=True)
    t1.start()
    threads.append(t1)

    t2 = threading.Thread(target=cleanup_old_data, name='data-cleanup', daemon=True)
    t2.start()
    threads.append(t2)

    t3 = threading.Thread(target=backup_database, name='db-backup', daemon=True)
    t3.start()
    threads.append(t3)

    logger.info(f"Started {len(threads)} background tasks (this worker owns the lock)")
    return threads


def stop_background_tasks():
    logger.info("Stopping background tasks...")
    shutdown_event.set()

    global _bg_lock_file, _bg_lock_acquired
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