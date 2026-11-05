"""
LoRa-Based Smart Street Light Automation System
One-click Application Launcher
"""

import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import Config
from backend.database import init_db
from backend.simulator import simulator_instance
from backend.mqtt_service import mqtt_service_instance
from backend.app import app

def print_banner():
    banner = f"""
================================================================================
   LoRa-Based Smart Street Light Automation System with Central Gateway
================================================================================
  [>] Mode:           DUAL (Hardware LoRa SX1276 & Synthetic Simulation)
  [>] Active Source:  {Config.DEFAULT_DATA_SOURCE.upper()}
  [>] Web Dashboard:  http://127.0.0.1:{Config.PORT}
  [>] MQTT Broker:    {Config.MQTT_BROKER_HOST}:{Config.MQTT_BROKER_PORT}
--------------------------------------------------------------------------------
  [+] Default Demo User Accounts:
      - Administrator:  admin  /  admin123  (Full control, simulations, configs)
      - Field Operator: user   /  user123   (Read-only telemetry & alerts)
================================================================================
"""
    print(banner)

def main():
    print("[1/3] Initializing SQLite database...")
    init_db()

    print(f"[2/3] Starting Synthetic IoT Generator (Default: {Config.DEFAULT_DATA_SOURCE})...")
    simulator_instance.start()

    print("[3/3] Initializing MQTT Service for HiveMQ Cloud...")
    mqtt_service_instance.start()

    print_banner()

    # Run Flask Application
    try:
        app.run(
            host="0.0.0.0",
            port=Config.PORT,
            debug=False,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n[System] Gracefully stopping simulator and MQTT services...")
        simulator_instance.stop()
        mqtt_service_instance.stop()
        print("[System] Stopped.")

if __name__ == '__main__':
    main()
