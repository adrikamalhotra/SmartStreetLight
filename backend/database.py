import sqlite3
import datetime
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from backend.config import Config

DB_PATH = Config.DATABASE_PATH

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            full_name TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Nodes Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pole_id TEXT UNIQUE NOT NULL,
            location_name TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT DEFAULT 'working',
            led_state INTEGER DEFAULT 0,
            commanded_state INTEGER DEFAULT 0,
            brightness INTEGER DEFAULT 0,
            ambient_lux REAL DEFAULT 150.0,
            power_w REAL DEFAULT 0.0,
            current_a REAL DEFAULT 0.0,
            voltage_v REAL DEFAULT 230.0,
            lora_rssi INTEGER DEFAULT -75,
            lora_snr REAL DEFAULT 8.0,
            mode TEXT DEFAULT 'auto',
            motion_detected INTEGER DEFAULT 0,
            failure_type TEXT DEFAULT NULL,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Telemetry History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pole_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ambient_lux REAL,
            led_state INTEGER,
            brightness INTEGER,
            power_w REAL,
            current_a REAL,
            voltage_v REAL,
            lora_rssi INTEGER,
            motion_detected INTEGER DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'synthetic'
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_pole_time ON telemetry_history(pole_id, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_telemetry_source ON telemetry_history(source)')

    # Alerts Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id TEXT UNIQUE NOT NULL,
            pole_id TEXT NOT NULL,
            fault_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at DATETIME,
            acknowledged_by TEXT,
            resolved_at DATETIME
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_pole_status ON alerts(pole_id, status)')

    # Gateway Status Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gateway_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gateway_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'online',
            mqtt_status TEXT DEFAULT 'connected',
            active_source TEXT DEFAULT 'synthetic',
            packets_received INTEGER DEFAULT 0,
            packets_failed INTEGER DEFAULT 0,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # System Configuration Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT
        )
    ''')

    conn.commit()

    # Seed Default Users
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        admin_pwd = generate_password_hash("admin123")
        user_pwd = generate_password_hash("user123")
        cursor.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                       ("admin", admin_pwd, "admin", "System Administrator"))
        cursor.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                       ("user", user_pwd, "user", "Field Operator"))
        conn.commit()

    # Seed Default Nodes
    cursor.execute("SELECT COUNT(*) FROM nodes")
    if cursor.fetchone()[0] == 0:
        default_nodes = [
            ("POLE-001", "North Blvd - Cross 1", 28.6139, 77.2090),
            ("POLE-002", "North Blvd - Cross 2", 28.6145, 77.2100),
            ("POLE-003", "Main Ave - Sector 4", 28.6152, 77.2112),
            ("POLE-004", "Main Ave - Sector 5", 28.6160, 77.2125),
            ("POLE-005", "Industrial Ring East", 28.6171, 77.2138),
            ("POLE-006", "Industrial Ring West", 28.6180, 77.2150),
            ("POLE-007", "South Express Corridor", 28.6192, 77.2162),
            ("POLE-008", "Tech Park Avenue", 28.6205, 77.2175)
        ]
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pole_id, loc, lat, lon in default_nodes:
            cursor.execute('''
                INSERT INTO nodes 
                (pole_id, location_name, latitude, longitude, status, led_state, commanded_state, 
                 brightness, ambient_lux, power_w, current_a, voltage_v, lora_rssi, lora_snr, mode, last_seen)
                VALUES (?, ?, ?, ?, 'working', 0, 0, 0, 220.0, 0.0, 0.0, 230.0, -78, 9.2, 'auto', ?)
            ''', (pole_id, loc, lat, lon, now))
        conn.commit()

    # Seed Default Gateway
    cursor.execute("SELECT COUNT(*) FROM gateway_status")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO gateway_status 
            (gateway_id, status, mqtt_status, active_source, packets_received, packets_failed, last_seen)
            VALUES ('GW-LORA-CENTRAL-01', 'online', 'connected', ?, 0, 0, CURRENT_TIMESTAMP)
        ''', (Config.DEFAULT_DATA_SOURCE,))
        conn.commit()

    # Seed Default Config
    default_configs = [
        ("data_source", Config.DEFAULT_DATA_SOURCE, "Active data source: synthetic or hardware"),
        ("ldr_on_threshold", str(Config.LDR_ON_THRESHOLD), "Lux threshold below which lights switch ON"),
        ("ldr_off_threshold", str(Config.LDR_OFF_THRESHOLD), "Lux threshold above which lights switch OFF"),
        ("night_brightness", str(Config.NIGHT_BRIGHTNESS), "Default LED brightness percentage at night"),
        ("motion_brightness", str(Config.MOTION_BRIGHTNESS), "LED brightness percentage when PIR motion detected"),
        ("motion_timeout_sec", str(Config.MOTION_TIMEOUT_SEC), "Seconds to stay at motion brightness before dimming"),
        ("communication_timeout_sec", str(Config.COMMUNICATION_TIMEOUT_SEC), "Seconds without LoRa message before node is offline"),
        ("min_voltage_v", str(Config.MIN_VOLTAGE_V), "Minimum acceptable line voltage"),
        ("max_voltage_v", str(Config.MAX_VOLTAGE_V), "Maximum acceptable line voltage"),
        ("max_power_w", str(Config.MAX_POWER_W), "Maximum safe wattage before overcurrent alert")
    ]
    for key, val, desc in default_configs:
        cursor.execute("INSERT OR IGNORE INTO system_config (key, value, description) VALUES (?, ?, ?)",
                       (key, val, desc))
    conn.commit()

    conn.close()

def get_system_config(key, default=None):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = ?", (key,)
        ).fetchone()

        if row:
            return row['value']
        return default
    finally:
        conn.close()

def set_system_config(key, value):
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO system_config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        conn.commit()
    finally:
        conn.close()
