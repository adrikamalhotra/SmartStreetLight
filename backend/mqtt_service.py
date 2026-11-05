import json
import ssl
import threading
import time
import datetime
import paho.mqtt.client as mqtt
from backend.config import Config
from backend.database import get_db_connection, get_system_config
from backend.automation_engine import AutomationEngine

class MQTTService:
    def __init__(self):
        self.client = None
        self.connected = False
        self.broker_host = Config.MQTT_BROKER_HOST
        self.broker_port = Config.MQTT_BROKER_PORT
        self.use_tls = Config.MQTT_USE_TLS
        self.username = Config.MQTT_USERNAME
        self.password = Config.MQTT_PASSWORD
        self.client_id = f"{Config.MQTT_CLIENT_ID}_{int(time.time())}"
        self.telemetry_topic = Config.MQTT_TOPIC_TELEMETRY
        self.command_topic = Config.MQTT_TOPIC_COMMAND
        self.gateway_topic = Config.MQTT_TOPIC_GATEWAY
        self._lock = threading.Lock()

    def start(self):
        """Initializes and connects MQTT client in a background thread."""
        try:
            # Paho MQTT v2 API compatibility
            if hasattr(mqtt, 'CallbackAPIVersion'):
                self.client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=self.client_id
                )
            else:
                self.client = mqtt.Client(client_id=self.client_id)

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            if self.use_tls or self.broker_port == 8883:
                self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            print(f"[MQTT] Connecting to {self.broker_host}:{self.broker_port}...")
            self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()

        except Exception as e:
            print(f"[MQTT Error] Failed to start MQTT client: {e}")
            self.connected = False
            self._update_gateway_mqtt_status('disconnected')

    def stop(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self.connected = False
            self._update_gateway_mqtt_status('disconnected')

    def publish_command(self, pole_id, command_payload):
        """Publishes downlink command for a specific streetlight node via LoRa Gateway"""
        if not self.client or not self.connected:
            print(f"[MQTT] Cannot publish command - client not connected to {self.broker_host}")
            return False

        topic = f"{self.command_topic.rstrip('/')}/{pole_id}"
        payload = json.dumps(command_payload)
        res = self.client.publish(topic, payload, qos=1)
        print(f"[MQTT] Published downlink to {topic}: {payload}")
        return res.is_published()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        rc_code = rc if isinstance(rc, int) else getattr(rc, 'value', 0)
        if rc_code == 0:
            self.connected = True
            print(f"[MQTT] Connected successfully to broker ({self.broker_host}:{self.broker_port})")
            client.subscribe(self.telemetry_topic)
            client.subscribe(self.gateway_topic)
            self._update_gateway_mqtt_status('connected')
        else:
            self.connected = False
            print(f"[MQTT] Connection failed with result code {rc_code}")
            self._update_gateway_mqtt_status('disconnected')

    def _on_disconnect(self, client, userdata, flags_or_rc, rc_or_props=None, properties=None):
        self.connected = False
        print("[MQTT] Disconnected from broker.")
        self._update_gateway_mqtt_status('disconnected')

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode('utf-8')
            topic = msg.topic

            # Handle Gateway Heartbeat / Status
            if topic == self.gateway_topic:
                self._handle_gateway_status_message(payload_str)
                return

            # Handle Node Telemetry
            data = json.loads(payload_str)
            active_source = get_system_config('data_source', Config.DEFAULT_DATA_SOURCE)

            # Strict source separation: Only process incoming MQTT telemetry if active mode is 'hardware'
            if active_source == 'hardware':
                data['source'] = 'hardware'
                AutomationEngine.process_telemetry(data)
                self._increment_gateway_packets()

        except Exception as e:
            print(f"[MQTT] Error handling incoming message on {msg.topic}: {e}")

    def _handle_gateway_status_message(self, payload_str):
        try:
            gw_data = json.loads(payload_str)
            gateway_id = gw_data.get('gateway_id', 'GW-LORA-CENTRAL-01')
            gw_status = gw_data.get('status', 'online')
            packets = gw_data.get('packets_received', 0)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn = get_db_connection()
            conn.execute('''
                UPDATE gateway_status SET
                    status = ?,
                    mqtt_status = ?,
                    packets_received = packets_received + ?,
                    last_seen = ?
                WHERE gateway_id = ?
            ''', (gw_status, 'connected', packets, now_str, gateway_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[MQTT] Error updating gateway status: {e}")

    def _increment_gateway_packets(self):
        try:
            conn = get_db_connection()
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute('''
                UPDATE gateway_status SET
                    packets_received = packets_received + 1,
                    last_seen = ?
                WHERE gateway_id = 'GW-LORA-CENTRAL-01'
            ''', (now_str,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _update_gateway_mqtt_status(self, mqtt_status):
        try:
            conn = get_db_connection()
            conn.execute('''
                UPDATE gateway_status SET
                    mqtt_status = ?
                WHERE gateway_id = 'GW-LORA-CENTRAL-01'
            ''', (mqtt_status,))
            conn.commit()
            conn.close()
        except Exception:
            pass

mqtt_service_instance = MQTTService()
