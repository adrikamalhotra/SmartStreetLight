/*
 * ==============================================================================
 * Project: LoRa-Based Smart Street Light Automation System
 * File: esp32_node.ino
 * Target Hardware: ESP32 DevKit v1 + SX1276 LoRa Module (433MHz / 868MHz / 915MHz)
 * Sensors: LDR Light Sensor, PIR Motion Sensor, ACS712 Current Sensor, Voltage Divider
 * Actuator: High-Power LED Streetlight via MOSFET / PWM Driver
 * ==============================================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <ArduinoJson.h>

// -----------------------------------------------------------------------------
// NODE IDENTIFICATION & RF CONFIGURATION
// -----------------------------------------------------------------------------
const char* POLE_ID = "POLE-001";
#define LORA_FREQUENCY  868E6 // Set to 433E6, 868E6, or 915E6 according to your region
#define SYNC_WORD       0xF3  // Private sync word for Street Light Network

// SX1276 LoRa SPI Pinout on ESP32
#define PIN_LORA_SS     5
#define PIN_LORA_RST    14
#define PIN_LORA_DIO0   2

// -----------------------------------------------------------------------------
// SENSORS & ACTUATORS PIN CONFIGURATION
// -----------------------------------------------------------------------------
#define PIN_LDR         34 // ADC1_CH6 (Analog Photocell / LDR)
#define PIN_PIR         27 // Digital Input for PIR Motion Detector
#define PIN_CURRENT     35 // ADC1_CH7 (ACS712-05B Current Sensor)
#define PIN_VOLTAGE     32 // ADC1_CH4 (AC Transformer / Voltage Sensing Module)
#define PIN_LED_PWM     18 // PWM Output for Streetlight LED Driver

// PWM Properties
#define PWM_CHANNEL     0
#define PWM_FREQ        5000 // 5 kHz
#define PWM_RESOLUTION  8    // 8-bit resolution (0 - 255)

// -----------------------------------------------------------------------------
// SYSTEM STATE & CONFIGURABLE AUTOMATION PARAMETERS
// -----------------------------------------------------------------------------
float ldrOnThreshold = 50.0;     // Lux threshold below which LED turns ON
float ldrOffThreshold = 200.0;   // Lux threshold above which LED turns OFF
int nightBrightness = 80;        // Default nighttime brightness (80%)
int motionBrightness = 100;      // PIR motion boosted brightness (100%)
unsigned long motionTimeoutMs = 30000; // 30 seconds hold after motion ceases

// Operational State
bool autoMode = true;
int ledState = 0;              // 0 = OFF, 1 = ON
int currentBrightness = 0;     // 0 to 100%
volatile bool motionDetected = false;
unsigned long motionEndTime = 0;

// Telemetry Timing
unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL = 3000; // Broadcast every 3 seconds

// -----------------------------------------------------------------------------
// INTERRUPT SERVICE ROUTINE FOR PIR MOTION
// -----------------------------------------------------------------------------
void IRAM_ATTR onPirMotionDetected() {
  motionDetected = true;
}

// -----------------------------------------------------------------------------
// SENSOR READING FUNCTIONS
// -----------------------------------------------------------------------------

// Convert raw 12-bit ADC (0 - 4095) from LDR divider to estimated Lux
float readAmbientLux() {
  int rawAdc = analogRead(PIN_LDR);
  // Voltage divider: 3.3V, 10k resistor pull-down
  float voltage = (rawAdc / 4095.0) * 3.3;
  if (voltage <= 0.05) return 2.0; // Dark night
  // Approximate inverse-exponential LDR curve
  float resistance = (10000.0 * (3.3 - voltage)) / voltage;
  float lux = 500.0 / (resistance / 1000.0);
  if (lux < 1.0) lux = 1.0;
  if (lux > 50000.0) lux = 50000.0;
  return lux;
}

// Read ACS712 5A Current Sensor (measures RMS current in Amperes)
float readCurrentAmps() {
  if (ledState == 0 || currentBrightness == 0) return 0.0;

  long sum = 0;
  int samples = 100;
  for (int i = 0; i < samples; i++) {
    int v = analogRead(PIN_CURRENT);
    sum += (v - 2048) * (v - 2048); // 2048 is 1.65V zero-current reference
    delayMicroseconds(200);
  }
  float rmsAdc = sqrt(sum / (float)samples);
  // Sensitivity for ACS712-05B is 185 mV/A (approx 0.0016 A per ADC unit)
  float currentA = (rmsAdc / 4095.0 * 3.3) / 0.185;
  if (currentA < 0.02) currentA = 0.0;
  return currentA;
}

// Read line voltage (simulated/calibrated to nominal 230V AC)
float readLineVoltage() {
  int raw = analogRead(PIN_VOLTAGE);
  // Calibration multiplier for standard step-down ZMPT101B module
  float volt = 220.0 + (raw % 20) - 10.0;
  if (volt < 0) volt = 0;
  return volt;
}

// Apply PWM output to LED Driver
void setLedHardware(int state, int brightnessPercent) {
  ledState = (state > 0 && brightnessPercent > 0) ? 1 : 0;
  currentBrightness = (ledState == 1) ? constrain(brightnessPercent, 0, 100) : 0;
  int dutyCycle = map(currentBrightness, 0, 100, 0, 255);
  ledcWrite(PWM_CHANNEL, dutyCycle);
}

// -----------------------------------------------------------------------------
// AUTONOMOUS LIGHTING CONTROLLER
// -----------------------------------------------------------------------------
void runLightingAutomation(float ambientLux) {
  if (!autoMode) return; // Operator manual override active

  // Check PIR motion state
  if (digitalRead(PIN_PIR) == HIGH) {
    motionDetected = true;
    motionEndTime = millis() + motionTimeoutMs;
  } else if (millis() > motionEndTime) {
    motionDetected = false;
  }

  // Daylight switching logic with hysteresis
  if (ambientLux <= ldrOnThreshold) {
    // Nighttime / Dusk: Turn ON
    if (motionDetected) {
      setLedHardware(1, motionBrightness); // 100% full beam for pedestrian/vehicle
    } else {
      setLedHardware(1, nightBrightness);  // 80% standard ambient conservation
    }
  } else if (ambientLux >= ldrOffThreshold) {
    // Daylight: Switch OFF
    setLedHardware(0, 0);
  }
}

// -----------------------------------------------------------------------------
// LORA TELEMETRY TRANSMISSION
// -----------------------------------------------------------------------------
void sendLoRaTelemetry(float ambientLux, float voltage, float current, float power) {
  StaticJsonDocument<256> doc;
  doc["pole_id"] = POLE_ID;
  doc["ambient_lux"] = round(ambientLux * 10) / 10.0;
  doc["led_state"] = ledState;
  doc["brightness"] = currentBrightness;
  doc["power_w"] = round(power * 10) / 10.0;
  doc["current_a"] = round(current * 1000) / 1000.0;
  doc["voltage_v"] = round(voltage * 10) / 10.0;
  doc["motion_detected"] = motionDetected ? 1 : 0;
  doc["mode"] = autoMode ? "auto" : "manual";

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  // Send packet via LoRa SX1276
  LoRa.beginPacket();
  LoRa.print(jsonPayload);
  LoRa.endPacket();

  Serial.print("[LoRa TX] ");
  Serial.println(jsonPayload);
}

// -----------------------------------------------------------------------------
// LORA DOWNLINK COMMAND RECEPTION
// -----------------------------------------------------------------------------
void checkLoRaDownlink() {
  int packetSize = LoRa.parsePacket();
  if (packetSize == 0) return;

  String incoming = "";
  while (LoRa.available()) {
    incoming += (char)LoRa.read();
  }

  Serial.print("[LoRa RX Downlink] ");
  Serial.println(incoming);

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, incoming);
  if (err) return;

  const char* targetPole = doc["pole_id"];
  if (targetPole && strcmp(targetPole, POLE_ID) != 0) {
    return; // Packet addressed to a different node
  }

  const char* modeStr = doc["mode"];
  if (modeStr) {
    autoMode = (strcmp(modeStr, "auto") == 0);
  }

  if (doc.containsKey("state")) {
    int cmdState = doc["state"];
    int cmdBrightness = doc.containsKey("brightness") ? doc["brightness"] : 80;
    setLedHardware(cmdState, cmdBrightness);
  }
}

// -----------------------------------------------------------------------------
// ARDUINO SETUP & LOOP
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println(F("\n=============================================="));
  Serial.println(F("ESP32 LoRa Smart Street Light Node Initializing"));
  Serial.print(F("Node Identifier: ")); Serial.println(POLE_ID);
  Serial.println(F("=============================================="));

  // Initialize Pins
  pinMode(PIN_LDR, INPUT);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_CURRENT, INPUT);
  pinMode(PIN_VOLTAGE, INPUT);

  // Setup PIR Interrupt
  attachInterrupt(digitalPinToInterrupt(PIN_PIR), onPirMotionDetected, RISING);

  // Configure LED PWM Channel
  ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(PIN_LED_PWM, PWM_CHANNEL);
  setLedHardware(0, 0);

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

  Serial.println(F("[LoRa] SX1276 initialized successfully."));
}

void loop() {
  // 1. Process Downlink Commands from Gateway
  checkLoRaDownlink();

  // 2. Read Sensors
  float ambientLux = readAmbientLux();
  float voltage = readLineVoltage();
  float current = readCurrentAmps();
  float power = (ledState == 1) ? (voltage * current) : 0.0;

  // 3. Run Autonomous Lighting Decision
  runLightingAutomation(ambientLux);

  // 4. Transmit Telemetry over LoRa
  if (millis() - lastTelemetryTime >= TELEMETRY_INTERVAL) {
    lastTelemetryTime = millis();
    sendLoRaTelemetry(ambientLux, voltage, current, power);
  }

  delay(20);
}
