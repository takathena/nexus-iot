"""
NEXUS IoT - Database Layer
Schema version 5: alerting + absensi RFID.
"""
import os
import sqlite3
from contextlib import contextmanager
from flask import g
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def get_wib_time():
    return datetime.now(WIB)


def _configure_connection(conn):
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('PRAGMA temp_store=MEMORY')
    conn.execute('PRAGMA cache_size=-64000')
    return conn


def _get_db_path():
    from config import Config
    return Config.DB_PATH


def get_db():
    if 'db' not in g:
        db_path = _get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False, isolation_level=None)
        _configure_connection(g.db)
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


@contextmanager
def get_db_context():
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False, isolation_level=None)
    _configure_connection(conn)
    try:
        yield conn
    finally:
        conn.close()


SCHEMA_VERSION = 5


def init_db():
    with get_db_context() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        row = cursor.execute('SELECT MAX(version) FROM schema_version').fetchone()
        current_version = row[0] if row and row[0] else 0

        print(f"[DB] Current schema version: {current_version}")

        if current_version < 1:
            _migrate_v1(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (1)')
            print("[DB] Applied migration v1")

        if current_version < 2:
            _migrate_v2(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (2)')
            print("[DB] Applied migration v2")

        if current_version < 3:
            _migrate_v3(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (3)')
            print("[DB] Applied migration v3")

        if current_version < 4:
            _migrate_v4(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (4)')
            print("[DB] Applied migration v4")

        if current_version < 5:
            _migrate_v5(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (5)')
            print("[DB] Applied migration v5")

        conn.commit()
        print(f"[DB] Database initialized! (version {SCHEMA_VERSION})")


def _migrate_v1(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            device_name TEXT NOT NULL,
            device_type TEXT DEFAULT 'ESP32',
            location TEXT DEFAULT '',
            latitude REAL DEFAULT 0,
            longitude REAL DEFAULT 0,
            description TEXT DEFAULT '',
            api_key TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'offline',
            last_seen DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            data TEXT NOT NULL,
            wifi_ssid TEXT DEFAULT '',
            uptime_seconds INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor_data_device_timestamp ON sensor_data (device_id, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data (timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_devices_status ON devices (status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_device_active ON alerts (device_id, is_active)')


def _migrate_v2(cursor):
    cols = [row[1] for row in cursor.execute('PRAGMA table_info(devices)').fetchall()]
    if 'last_ip' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN last_ip TEXT DEFAULT ""')
    if 'firmware_version' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN firmware_version TEXT DEFAULT ""')


def _migrate_v3(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cardholders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            nama TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            device_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uid) REFERENCES cardholders (uid),
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_attendance_uid_timestamp ON attendance (uid, timestamp)')


def _migrate_v4(cursor):
    cursor.execute('ALTER TABLE attendance RENAME TO attendance_old')
    cursor.execute('''
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            device_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute('INSERT INTO attendance (id, uid, device_id, timestamp) SELECT id, uid, device_id, timestamp FROM attendance_old')
    cursor.execute('DROP TABLE attendance_old')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_attendance_uid_timestamp ON attendance (uid, timestamp)')


def _migrate_v5(cursor):
    """Dynamic alerting + per-device offline timeout + alert history"""
    cols = [row[1] for row in cursor.execute('PRAGMA table_info(devices)').fetchall()]

    if 'offline_timeout' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN offline_timeout INTEGER DEFAULT 900')
    if 'expected_interval' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN expected_interval INTEGER DEFAULT 60')
    if 'alert_rules' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN alert_rules TEXT DEFAULT NULL')
    if 'offline_alert_severity' not in cols:
        cursor.execute("ALTER TABLE devices ADD COLUMN offline_alert_severity TEXT DEFAULT 'danger'")

    alert_cols = [row[1] for row in cursor.execute('PRAGMA table_info(alerts)').fetchall()]
    if 'severity' not in alert_cols:
        cursor.execute("ALTER TABLE alerts ADD COLUMN severity TEXT DEFAULT 'warning'")
    if 'value' not in alert_cols:
        cursor.execute('ALTER TABLE alerts ADD COLUMN value REAL DEFAULT NULL')
    if 'updated_at' not in alert_cols:
        cursor.execute('ALTER TABLE alerts ADD COLUMN updated_at DATETIME DEFAULT NULL')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            value REAL,
            action TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_history_device ON alert_history (device_id, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity, is_active)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS device_status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_log_device ON device_status_log (device_id, created_at DESC)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')