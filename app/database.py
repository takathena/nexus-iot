"""
NEXUS IoT - Database Layer
Schema version 10: multi-dashboard + analytics tabs + widgets.
"""
import os
import sqlite3
import hashlib
from contextlib import contextmanager
from flask import g
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def get_wib_time():
    """Return current WIB time as NAIVE datetime."""
    return datetime.now(WIB).replace(tzinfo=None)


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
    from app.config import Config
    return Config.DB_PATH


def get_db():
    if 'db' not in g:
        db_path = _get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(
            db_path,
            timeout=30.0,
            check_same_thread=False,
            isolation_level='DEFERRED',
        )
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
    conn = sqlite3.connect(
        db_path,
        timeout=30.0,
        check_same_thread=False,
        isolation_level='DEFERRED',
    )
    _configure_connection(conn)
    try:
        yield conn
    finally:
        conn.close()


SCHEMA_VERSION = 10
WIB_DEFAULT = "(datetime('now', '+7 hours'))"


def init_db():
    from app.utils import process_lock

    with process_lock('db-init', blocking=True) as got_lock:
        if not got_lock:
            return
        _init_db_inner()


def _init_db_inner():
    with get_db_context() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT (datetime('now', '+7 hours'))
            )
        ''')

        row = cursor.execute('SELECT MAX(version) FROM schema_version').fetchone()
        current_version = row[0] if row and row[0] else 0

        print(f"[DB] Current schema version: {current_version}")

        migrations = [
            (1, _migrate_v1),
            (2, _migrate_v2),
            (3, _migrate_v3),
            (4, _migrate_v4),
            (5, _migrate_v5),
            (6, _migrate_v6),
            (7, _migrate_v7),
            (8, _migrate_v8),
            (9, _migrate_v9),
            (10, _migrate_v10),
        ]

        for version, migrate_fn in migrations:
            if current_version < version:
                migrate_fn(cursor)
                cursor.execute('INSERT INTO schema_version (version) VALUES (?)', (version,))
                print(f"[DB] Applied migration v{version}")

        conn.commit()
        print(f"[DB] Database initialized! (version {SCHEMA_VERSION})")


def _migrate_v1(cursor):
    cursor.execute(f'''
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
            created_at DATETIME DEFAULT {WIB_DEFAULT}
        )
    ''')
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            data TEXT NOT NULL,
            wifi_ssid TEXT DEFAULT '',
            uptime_seconds INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT {WIB_DEFAULT},
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT {WIB_DEFAULT},
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
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS cardholders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            nama TEXT NOT NULL,
            created_at DATETIME DEFAULT {WIB_DEFAULT}
        )
    ''')
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            device_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT {WIB_DEFAULT},
            FOREIGN KEY (uid) REFERENCES cardholders (uid),
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_attendance_uid_timestamp ON attendance (uid, timestamp)')


def _migrate_v4(cursor):
    cursor.execute('ALTER TABLE attendance RENAME TO attendance_old')
    cursor.execute(f'''
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT NOT NULL,
            device_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT {WIB_DEFAULT},
            FOREIGN KEY (device_id) REFERENCES devices (device_id)
        )
    ''')
    cursor.execute('INSERT INTO attendance (id, uid, device_id, timestamp) SELECT id, uid, device_id, timestamp FROM attendance_old')
    cursor.execute('DROP TABLE attendance_old')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_attendance_uid_timestamp ON attendance (uid, timestamp)')


def _migrate_v5(cursor):
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

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            value REAL,
            action TEXT NOT NULL,
            created_at DATETIME DEFAULT {WIB_DEFAULT}
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_history_device ON alert_history (device_id, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity, is_active)')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS device_status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT {WIB_DEFAULT}
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_log_device ON device_status_log (device_id, created_at DESC)')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT {WIB_DEFAULT}
        )
    ''')


def _migrate_v6(cursor):
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_alerts_active_lookup
        ON alerts (device_id, alert_type, is_active)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_alerts_active_severity
        ON alerts (is_active, severity, alert_type)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_alert_history_action
        ON alert_history (action, created_at DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp_desc
        ON sensor_data (timestamp DESC)
    ''')


def _migrate_v7(cursor):
    print("[DB] v7: standardizing timezone to naive WIB...")

    tz_fields = [
        ('devices', 'last_seen'),
        ('sensor_data', 'timestamp'),
        ('alerts', 'created_at'),
        ('alerts', 'updated_at'),
        ('alert_history', 'created_at'),
        ('attendance', 'timestamp'),
        ('device_status_log', 'created_at'),
    ]

    for table, column in tz_fields:
        try:
            result = cursor.execute(
                f"UPDATE {table} SET {column} = REPLACE({column}, '+07:00', '') "
                f"WHERE {column} LIKE '%+07:00'"
            )
            if result.rowcount > 0:
                print(f"[DB] v7: stripped tz from {table}.{column} ({result.rowcount} rows)")
        except Exception as e:
            print(f"[DB] v7 skip {table}.{column}: {e}")

    utc_fields = [
        ('devices', 'created_at'),
        ('cardholders', 'created_at'),
    ]

    for table, column in utc_fields:
        try:
            result = cursor.execute(
                f"UPDATE {table} SET {column} = datetime({column}, '+7 hours') "
                f"WHERE {column} IS NOT NULL AND {column} NOT LIKE '%+07:00'"
            )
            if result.rowcount > 0:
                print(f"[DB] v7: UTC→WIB {table}.{column} ({result.rowcount} rows)")
        except Exception as e:
            print(f"[DB] v7 skip tz-convert {table}.{column}: {e}")

    print("[DB] v7: timezone standardization complete")


def _migrate_v8(cursor):
    """Hash API key + nullify plaintext."""
    print("[DB] v8: hashing API keys...")

    cols = [row[1] for row in cursor.execute('PRAGMA table_info(devices)').fetchall()]
    if 'api_key_hash' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN api_key_hash TEXT DEFAULT NULL')
        print("[DB] v8: added column api_key_hash")

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_devices_api_key_hash ON devices (api_key_hash)')

    rows = cursor.execute(
        'SELECT device_id, api_key FROM devices WHERE api_key IS NOT NULL AND (api_key_hash IS NULL OR api_key_hash = "")'
    ).fetchall()

    hashed = 0
    for row in rows:
        device_id = row[0]
        api_key = row[1]
        if not api_key:
            continue
        key_hash = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
        cursor.execute(
            'UPDATE devices SET api_key_hash = ? WHERE device_id = ?',
            (key_hash, device_id)
        )
        hashed += 1

    cursor.execute('UPDATE devices SET api_key = NULL WHERE api_key_hash IS NOT NULL')
    print(f"[DB] v8: hashed {hashed} API keys, plaintext nullified")


def _migrate_v9(cursor):
    """Multi-dashboard + persistent widget layout."""
    print("[DB] v9: creating dashboards & widgets tables...")

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS dashboards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            icon TEXT DEFAULT 'fa-chart-line',
            is_default INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT {WIB_DEFAULT},
            updated_at DATETIME DEFAULT {WIB_DEFAULT}
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS widgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dashboard_id INTEGER NOT NULL,
            widget_type TEXT NOT NULL,
            title TEXT NOT NULL,
            device_id TEXT,
            config TEXT NOT NULL,
            grid_x INTEGER DEFAULT 0,
            grid_y INTEGER DEFAULT 0,
            grid_w INTEGER DEFAULT 2,
            grid_h INTEGER DEFAULT 2,
            created_at DATETIME DEFAULT {WIB_DEFAULT},
            updated_at DATETIME DEFAULT {WIB_DEFAULT},
            FOREIGN KEY (dashboard_id) REFERENCES dashboards (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_widgets_dashboard ON widgets (dashboard_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dashboards_slug ON dashboards (slug)')

    existing = cursor.execute('SELECT id FROM dashboards WHERE slug = ?', ('default',)).fetchone()
    if not existing:
        cursor.execute('''
            INSERT INTO dashboards (slug, name, description, icon, is_default)
            VALUES ('default', 'Dashboard Utama', 'Dashboard bawaan', 'fa-chart-pie', 1)
        ''')
        print("[DB] v9: default dashboard created")
    else:
        print("[DB] v9: default dashboard already exists")


def _migrate_v10(cursor):
    """Analytics tabs untuk multi-analitik dalam satu dashboard."""
    print("[DB] v10: creating analytics_tabs...")

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS analytics_tabs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dashboard_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            icon TEXT DEFAULT 'fa-chart-line',
            position INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT {WIB_DEFAULT},
            updated_at DATETIME DEFAULT {WIB_DEFAULT},
            FOREIGN KEY (dashboard_id) REFERENCES dashboards (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_tabs_dashboard ON analytics_tabs (dashboard_id, position)')

    cols = [row[1] for row in cursor.execute('PRAGMA table_info(widgets)').fetchall()]
    if 'analytics_tab_id' not in cols:
        cursor.execute('ALTER TABLE widgets ADD COLUMN analytics_tab_id INTEGER DEFAULT NULL')
        print("[DB] v10: added column widgets.analytics_tab_id")

    print("[DB] v10: analytics_tabs ready")