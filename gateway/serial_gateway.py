"""
Python Serial LoRa Gateway Bridge
---------------------------------
For setups where an ESP32 or LoRa USB Dongle is connected directly
to the host computer (Windows/Linux/Mac) via USB / COM port.

Reads JSON telemetry over Serial, forwards to HiveMQ Cloud MQTT,
and forwards downlink MQTT commands back out over the serial port.
"""

import sys
import time
import json
import os
from pathlib import Path

# Try importing serial and paho.mqtt
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

import paho.mqtt.client as mqtt

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
from backend.config import Config

class SerialLoRaGateway:
    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.mqtt_client = None
        self.running = False

    def find_serial_port(self):
        if not serial:
            print("[Gateway] pyserial is not installed. Run: pip install pyserial")
            return None
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("[Gateway] No serial COM ports detected on host machine.")
            return None
        print("[Gateway] Detected COM ports:")
        for p in ports:
            print(f"  - {p.device}: {p.description}")
        return ports[0].device

    def start_mqtt(self):
        client_id = f"SerialGatewayBridge_{int(time.time())}"
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if Config.MQTT_USERNAME and Config.MQTT_PASSWORD:
            self.mqtt_client.username_pw_set(Config.MQTT_USERNAME, Config.MQTT_PASSWORD)

        def on_connect(client, userdata, flags, rc, props=None):
            print(f"[Gateway MQTT] Connected to {Config.MQTT_BROKER_HOST}:{Config.MQTT_BROKER_PORT}")
            client.subscribe("smartlight/command/#")

        def on_message(client, userdata, msg):
            try:
                payload = msg.payload.decode('utf-8')
                print(f"[Gateway MQTT Downlink] {msg.topic} -> {payload}")
                if self.serial_conn and self.serial_conn.is_open:
                    self.serial_conn.write((payload + "\n").encode('utf-8'))
            except Exception as e:
                print(f"[Gateway Error forwarding downlink] {e}")

        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = on_message
        self.mqtt_client.connect_async(Config.MQTT_BROKER_HOST, Config.MQTT_BROKER_PORT, 60)
        self.mqtt_client.loop_start()

    def run(self):
        port_to_use = self.port or self.find_serial_port()
        if not port_to_use:
            print("[Gateway] Aborting serial gateway: No serial device available.")
            return

        print(f"[Gateway] Opening serial port {port_to_use} at {self.baudrate} baud...")
        try:
            self.serial_conn = serial.Serial(port_to_use, self.baudrate, timeout=1.0)
        except Exception as e:
            print(f"[Gateway Error] Could not open serial port {port_to_use}: {e}")
            return

        self.start_mqtt()
        self.running = True
        print("[Gateway] Serial-to-MQTT Bridge is active. Listening for LoRa packets...")

        while self.running:
            try:
                line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            telemetry = json.loads(line)
                            pole_id = telemetry.get('pole_id', 'unknown')
                            topic = f"smartlight/telemetry/{pole_id}"
                            self.mqtt_client.publish(topic, line, qos=1)
                            print(f"[Gateway Ingested & Published] {topic} -> {line}")
                        except json.JSONDecodeError:
                            print(f"[Serial Debug] {line}")
                    else:
                        print(f"[Serial Log] {line}")
            except KeyboardInterrupt:
                print("\n[Gateway] Shutting down bridge...")
                self.running = False
            except Exception as e:
                print(f"[Gateway Loop Error] {e}")
                time.sleep(1.0)

        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()

if __name__ == '__main__':
    port_arg = sys.argv[1] if len(sys.argv) > 1 else None
    gw = SerialLoRaGateway(port=port_arg)
    gw.run()
