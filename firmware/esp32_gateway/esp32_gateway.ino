/*
 * ==============================================================================
 * Project: LoRa-Based Smart Street Light Automation System
 * File: esp32_gateway.ino
 * Target Hardware: ESP32 DevKit v1 + SX1276 LoRa Module
 * Network: WiFi + HiveMQ Cloud MQTT Broker (Secure TLS / Port 8883)
 * Function: Receives LoRa Telemetry from Street Poles -> Forwards to MQTT
 *           Subscribes to MQTT Commands -> Transmits LoRa Downlinks
 * ==============================================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// -----------------------------------------------------------------------------
// GATEWAY IDENTIFICATION & RF CONFIGURATION
// -----------------------------------------------------------------------------
const char* GATEWAY_ID = "GW-LORA-CENTRAL-01";
#define LORA_FREQUENCY  868E6 // Set to match Node frequency (433E6, 868E6, 915E6)
#define SYNC_WORD       0xF3

// SX1276 LoRa SPI Pinout on ESP32
#define PIN_LORA_SS     5
#define PIN_LORA_RST    14
#define PIN_LORA_DIO0   2

// Status LED Pin
#define PIN_STATUS_LED  2

// -----------------------------------------------------------------------------
// NETWORK & HIVEMQ CLOUD MQTT CONFIGURATION
// -----------------------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// HiveMQ Cloud Broker Credentials
// (Example host: "your-cluster-id.s1.eu.hivemq.cloud")
const char* MQTT_BROKER   = "broker.hivemq.com"; // Or your cluster URL
const int   MQTT_PORT     = 1883;                 // 8883 for TLS, 1883 for plain
const char* MQTT_USER     = "";                   // Set if using HiveMQ Cloud auth
const char* MQTT_PASS     = "";                   // Set if using HiveMQ Cloud auth

const char* TOPIC_GATEWAY_STATUS = "smartlight/gateway/status";
const char* TOPIC_COMMAND_SUB    = "smartlight/command/#";

// Clients
WiFiClient espClient; // Use WiFiClientSecure for HiveMQ Cloud TLS on port 8883
PubSubClient mqttClient(espClient);

// Statistics
unsigned long packetsReceived = 0;
unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 10000; // Heartbeat every 10 seconds

// -----------------------------------------------------------------------------
// WIFI & MQTT CONNECTION MANAGEMENT
// -----------------------------------------------------------------------------
void connectWiFi() {
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected! IP Address: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Connection timeout. Retrying in loop...");
  }
}

void onMqttMessageReceived(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("[MQTT Downlink Command Received on ");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);

  // Transmit downlink command over LoRa to Streetlight nodes
  LoRa.beginPacket();
  LoRa.print(message);
  LoRa.endPacket();

  Serial.println("[LoRa TX] Downlink packet forwarded over RF.");
}

void reconnectMqtt() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return;
  }

  if (!mqttClient.connected()) {
    Serial.print("[MQTT] Connecting to HiveMQ broker: ");
    Serial.println(MQTT_BROKER);

    String clientId = "ESP32_LoRa_Gateway_" + String(random(0xffff), HEX);
    bool connected = false;

    if (strlen(MQTT_USER) > 0) {
      connected = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS);
    } else {
      connected = mqttClient.connect(clientId.c_str());
    }

    if (connected) {
      Serial.println("[MQTT] Connected successfully to HiveMQ broker!");
      mqttClient.subscribe(TOPIC_COMMAND_SUB);
      publishGatewayHeartbeat();
    } else {
      Serial.print("[MQTT] Connection failed, rc=");
      Serial.println(mqttClient.state());
    }
  }
}

void publishGatewayHeartbeat() {
  StaticJsonDocument<200> doc;
  doc["gateway_id"] = GATEWAY_ID;
  doc["status"] = "online";
  doc["packets_received"] = packetsReceived;
  doc["uptime_sec"] = millis() / 1000;
  doc["rssi_wifi"] = WiFi.RSSI();

  char buffer[256];
  serializeJson(doc, buffer);
  mqttClient.publish(TOPIC_GATEWAY_STATUS, buffer);
  Serial.print("[MQTT Gateway Heartbeat] ");
  Serial.println(buffer);
}

// -----------------------------------------------------------------------------
// LORA PACKET INGESTION & MQTT FORWARDING
// -----------------------------------------------------------------------------
void processIncomingLoRaPackets() {
  int packetSize = LoRa.parsePacket();
  if (packetSize == 0) return;

  // Flash status LED
  digitalWrite(PIN_STATUS_LED, HIGH);

  String rawPayload = "";
  while (LoRa.available()) {
    rawPayload += (char)LoRa.read();
  }

  int loraRssi = LoRa.packetRssi();
  float loraSnr = LoRa.packetSnr();
  packetsReceived++;

  Serial.print("[LoRa RX] (RSSI: ");
  Serial.print(loraRssi);
  Serial.print(" dBm, SNR: ");
  Serial.print(loraSnr);
  Serial.print(" dB) Payload: ");
  Serial.println(rawPayload);

  // Parse JSON and enrich with Gateway RF metrics
  StaticJsonDocument<384> doc;
  DeserializationError err = deserializeJson(doc, rawPayload);
  if (err) {
    Serial.print("[LoRa Parse Error] ");
    Serial.println(err.c_str());
    digitalWrite(PIN_STATUS_LED, LOW);
    return;
  }

  // Inject Gateway metrics
  doc["lora_rssi"] = loraRssi;
  doc["lora_snr"] = loraSnr;
  doc["gateway_id"] = GATEWAY_ID;

  const char* poleId = doc["pole_id"];
  String topic = "smartlight/telemetry/" + (poleId ? String(poleId) : "unknown");

  char enrichedBuffer[512];
  serializeJson(doc, enrichedBuffer);

  // Forward to HiveMQ Cloud via MQTT
  if (mqttClient.connected()) {
    mqttClient.publish(topic.c_str(), enrichedBuffer);
    Serial.print("[MQTT Forwarded to ");
    Serial.print(topic);
    Serial.println("]");
  } else {
    Serial.println("[MQTT Warning] Telemetry dropped: MQTT not connected");
  }

  digitalWrite(PIN_STATUS_LED, LOW);
}

// -----------------------------------------------------------------------------
// ARDUINO SETUP & LOOP
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println(F("\n=============================================="));
  Serial.println(F("ESP32 Central LoRa Gateway Initializing"));
  Serial.print(F("Gateway Identifier: ")); Serial.println(GATEWAY_ID);
  Serial.println(F("=============================================="));

  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, LOW);

  // Initialize LoRa SX1276
  LoRa.setPins(PIN_LORA_SS, PIN_LORA_RST, PIN_LORA_DIO0);
  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println(F("[ERROR] LoRa SX1276 initialization failed! Check wiring."));
    while (1) { delay(1000); }
  }

  LoRa.setSyncWord(SYNC_WORD);
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();
  Serial.println(F("[LoRa] Central Gateway transceiver listening..."));

  // Connect WiFi
  connectWiFi();

  // Configure MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(onMqttMessageReceived);
  mqttClient.setBufferSize(512);
}

void loop() {
  // Maintain MQTT Connection
  if (!mqttClient.connected()) {
    static unsigned long lastReconnectAttempt = 0;
    if (millis() - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = millis();
      reconnectMqtt();
    }
  } else {
    mqttClient.loop();
  }

  // Process incoming LoRa packets from street poles
  processIncomingLoRaPackets();

  // Periodic Gateway Heartbeat
  if (millis() - lastHeartbeat >= HEARTBEAT_INTERVAL) {
    lastHeartbeat = millis();
    if (mqttClient.connected()) {
      publishGatewayHeartbeat();
    }
  }

  delay(10);
}
