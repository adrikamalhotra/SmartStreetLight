import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "smartstreetlight-lora-super-secret-key-2026")
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "smart_street_light.db"))
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # Data Source: 'synthetic' or 'hardware'
    DEFAULT_DATA_SOURCE = os.getenv("DEFAULT_DATA_SOURCE", "synthetic")

    # MQTT Settings
    MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
    MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
    MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "False").lower() in ("true", "1", "yes")
    MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
    MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "SmartStreetLight_Server_01")
    MQTT_TOPIC_TELEMETRY = os.getenv("MQTT_TOPIC_TELEMETRY", "smartlight/telemetry/#")
    MQTT_TOPIC_COMMAND = os.getenv("MQTT_TOPIC_COMMAND", "smartlight/command/")
    MQTT_TOPIC_GATEWAY = os.getenv("MQTT_TOPIC_GATEWAY", "smartlight/gateway/status")

    # Thresholds
    LDR_ON_THRESHOLD = float(os.getenv("DEFAULT_LDR_ON_THRESHOLD", 50.0))
    LDR_OFF_THRESHOLD = float(os.getenv("DEFAULT_LDR_OFF_THRESHOLD", 200.0))
    NIGHT_BRIGHTNESS = int(os.getenv("DEFAULT_NIGHT_BRIGHTNESS", 80))
    MOTION_BRIGHTNESS = int(os.getenv("DEFAULT_MOTION_BRIGHTNESS", 100))
    MOTION_TIMEOUT_SEC = int(os.getenv("DEFAULT_MOTION_TIMEOUT_SEC", 30))
    COMMUNICATION_TIMEOUT_SEC = int(os.getenv("COMMUNICATION_TIMEOUT_SEC", 45))

    # Electrical thresholds for fault detection
    MIN_VOLTAGE_V = 185.0
    MAX_VOLTAGE_V = 265.0
    RATED_VOLTAGE_V = 230.0
    MAX_POWER_W = 120.0       # Standard 60W-90W street light; >120W is short/overload
    MIN_POWER_WHEN_ON_W = 8.0 # If commanded ON at >=20% and W < 8, LED failure
