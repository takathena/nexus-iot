"""
NEXUS IoT - Background Tasks
"""
import os
import sqlite3
import threading
import logging
import time
from datetime import datetime, timedelta

from config import get_config
from database import get_db_context, get_wib_time
from utils import parse_datetime

logger = logging.getLogger('nexus')

# Event untuk graceful shutdown
shutdown_event = threading.Event()


# ==========================================
# DEVICE STATUS CHECKER
# ==========================================
def check_device_status():
    """Loop cek status online/offline device"""
    config = get_config()
    logger.info(f"Status checker started (interval={config.CHECK_INTERVAL}s, timeout={config.OFFLINE_TIMEOUT}s)")

    while not shutdown_event.is_set():
        try:
            current_time = get_wib_time()
            with get_db_context() as conn:
                devices = conn.execute(
                    'SELECT device_id, last_seen, status FROM devices'
                ).fetchall()

                for device in devices:
                    device_id = device['device_id']
                    last_seen = device['last_seen']
                    current_status = device['status']

                    if not last_seen:
                        if current_status != 'offline':
                            conn.execute(
                                'UPDATE devices SET status = ? WHERE device_id = ?',
                                ('offline', device_id)
                            )
                        continue

                    last_seen_dt = parse_datetime(last_seen)
                    if not last_seen_dt:
                        continue

                    time_diff = (current_time - last_seen_dt).total_seconds()

                    if time_diff > config.OFFLINE_TIMEOUT and current_status != 'offline':
                        conn.execute(
                            'UPDATE devices SET status = ? WHERE device_id = ?',
                            ('offline', device_id)
                        )
                        logger.info(f"Device {device_id} marked OFFLINE (last seen {int(time_diff)}s ago)")

                conn.commit()

        except Exception as e:
            logger.error(f"Status checker error: {e}", exc_info=True)

        # Sleep dengan interruptible
        shutdown_event.wait(config.CHECK_INTERVAL)

    logger.info("Status checker stopped")


# ==========================================
# DATA CLEANUP
# ==========================================
def cleanup_old_data():
    """Hapus data sensor yang lebih lama dari retention policy"""
    config = get_config()
    logger.info(f"Data cleanup started (retention={config.DATA_RETENTION_DAYS} days)")

    # Jalankan pertama kali setelah 5 menit (biar app ready dulu)
    shutdown_event.wait(300)

    while not shutdown_event.is_set():
        try:
            cutoff = get_wib_time() - timedelta(days=config.DATA_RETENTION_DAYS)

            with get_db_context() as conn:
                result = conn.execute(
                    'DELETE FROM sensor_data WHERE timestamp < ?',
                    (cutoff.replace(tzinfo=None),)
                )
                deleted = result.rowcount
                conn.commit()

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old sensor records (older than {config.DATA_RETENTION_DAYS} days)")

        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)

        # Jalankan setiap 24 jam
        shutdown_event.wait(86400)

    logger.info("Data cleanup stopped")


# ==========================================
# DATABASE BACKUP
# ==========================================
def backup_database():
    """Backup database dengan SQLite backup API"""
    config = get_config()
    if not config.BACKUP_ENABLED:
        logger.info("Backup disabled")
        return

    logger.info(f"Backup started (interval={config.BACKUP_INTERVAL_HOURS}h, retention={config.BACKUP_RETENTION_DAYS}d)")

    # Jalankan pertama kali setelah 10 menit
    shutdown_event.wait(600)

    while not shutdown_event.is_set():
        try:
            os.makedirs(config.BACKUP_DIR, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(config.BACKUP_DIR, f'iot_{timestamp}.db')

            # ✅ Pakai SQLite backup API (thread-safe & consistent)
            source = sqlite3.connect(config.DB_PATH, timeout=30.0)
            dest = sqlite3.connect(backup_path)

            with dest:
                source.backup(dest)

            dest.close()
            source.close()

            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            logger.info(f"Backup created: {backup_path} ({size_mb:.2f} MB)")

            # Hapus backup lama
            cutoff_ts = datetime.now().timestamp() - (config.BACKUP_RETENTION_DAYS * 86400)
            for filename in os.listdir(config.BACKUP_DIR):
                filepath = os.path.join(config.BACKUP_DIR, filename)
                if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff_ts:
                    os.remove(filepath)
                    logger.info(f"Old backup removed: {filename}")

        except Exception as e:
            logger.error(f"Backup failed: {e}", exc_info=True)

        # Sleep 24 jam (dengan interruptible)
        shutdown_event.wait(config.BACKUP_INTERVAL_HOURS * 3600)

    logger.info("Backup task stopped")


# ==========================================
# START ALL BACKGROUND TASKS
# ==========================================
def start_background_tasks():
    """Start semua background thread"""
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

    logger.info(f"Started {len(threads)} background tasks")
    return threads


def stop_background_tasks():
    """Trigger graceful shutdown"""
    logger.info("Stopping background tasks...")
    shutdown_event.set()