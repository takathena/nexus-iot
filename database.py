"""
NEXUS IoT - Database Layer
Schema version 7: timezone standardization + indexes.

✅ P0 FIX: semua datetime disimpan sebagai naive WIB (tanpa +07:00 suffix).
Migrasi v7 akan:
  1. Strip suffix '+07:00' dari datetime yang sudah ada
  2. Konversi created_at yang UTC (dari DEFAULT CURRENT_TIMESTAMP) ke WIB
"""
import os
import sqlite3
from contextlib import contextmanager
from flask import g
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def get_wib_time():
    """
    ✅ P0 FIX: sekarang mengembalikan NAIVE WIB datetime.
    Sebelumnya aware (+07:00) yang menyebabkan inkonsistensi di query range.
    """
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
    from config import Config
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


SCHEMA_VERSION = 8

# ✅ P0 FIX: default WIB untuk fresh install (bukan UTC)
WIB_DEFAULT = "(datetime('now', '+7 hours'))"


def init_db():
    """
    ✅ P0 FIX: dibungkus process_lock supaya tidak race di multi-worker Gunicorn.
    Worker pertama menjalankan migrasi; worker lain menunggu dan langsung
    melihat schema version sudah terbaru.
    """
    from utils import process_lock

    with process_lock('db-init', blocking=True) as got_lock:
        if not got_lock:
            # Tidak mungkin terjadi dengan blocking=True, tapi jaga-jaga
            print("[DB] Failed to acquire init lock, skipping")
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

        if current_version < 6:
            _migrate_v6(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (6)')
            print("[DB] Applied migration v6")

        if current_version < 7:
            _migrate_v7(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (7)')
            print("[DB] Applied migration v7 (timezone standardization)")

        if current_version < 8:
            _migrate_v8(cursor)
            cursor.execute('INSERT INTO schema_version (version) VALUES (8)')
            print("[DB] Applied migration v8 (hash API key)")

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
    """
    ✅ P0 FIX: Standarisasi semua datetime ke naive WIB.

    Sebelumnya:
      - Kolom yang diset eksplisit pakai get_wib_time() → tersimpan sebagai
        '2026-09-12 14:30:25+07:00' (aware)
      - Kolom created_at yang pakai DEFAULT CURRENT_TIMESTAMP → tersimpan
        sebagai '2026-09-12 07:30:25' (UTC naive)

    Sesudah:
      - Semua kolom → naive WIB '2026-09-12 14:30:25'
    """
    print("[DB] v7: standardizing timezone to naive WIB...")

    # 1. Kolom yang sebelumnya di-set eksplisit sebagai WIB aware (+07:00)
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

    # 2. Kolom yang pakai DEFAULT CURRENT_TIMESTAMP (UTC) → konversi ke WIB
    #    devices.created_at & cardholders.created_at tidak pernah di-set eksplisit,
    #    jadi semua existing row adalah UTC naive.
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
    """
    ✅ P1-B FIX: Hash API key device dengan SHA-256.

    Sebelumnya api_key disimpan plaintext. Sekarang:
      - api_key_hash: SHA-256(api_key) — untuk verifikasi
      - api_key: tetap ada untuk kompatibilitas mundur (di-null-kan nanti)

    Migrasi:
      1. Tambah kolom api_key_hash (kalau belum ada)
      2. Isi hash untuk semua device dari api_key plaintext yang ada
    """
    import hashlib

    print("[DB] v8: hashing API keys...")

    # 1. Tambah kolom api_key_hash
    cols = [row[1] for row in cursor.execute('PRAGMA table_info(devices)').fetchall()]
    if 'api_key_hash' not in cols:
        cursor.execute('ALTER TABLE devices ADD COLUMN api_key_hash TEXT DEFAULT NULL')
        print("[DB] v8: added column api_key_hash")

    # 2. Index untuk lookup cepat saat validasi
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_devices_api_key_hash ON devices (api_key_hash)'
    )

    # 3. Isi hash untuk semua row yang punya api_key plaintext tapi hash-nya kosong
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

    print(f"[DB] v8: hashed {hashed} API keys")
    print("[DB] v8: hash API key migration complete")