# LoRa-Based Smart Street Light Automation System with Wireless Automation Nodes and Central Gateway

A comprehensive, production-grade IoT streetlight management and automation platform powered by **ESP32**, **SX1276 LoRa wireless communication**, **HiveMQ Cloud MQTT**, **Python Flask**, and a **dark industrial monitoring dashboard**.

**Live Demo:** https://smartstreetlight-0rz0.onrender.com
---

## 1. System Overview & Architecture

```
+-----------------------------------------------------------------------------------------+
|                                STREETLIGHT NODES (ESP32)                                |
|  - LDR Ambient Lux Sensor      - PIR Motion Detector (Adaptive Boost)                   |
|  - ACS712 Current Sensor       - Line Voltage AC Monitor                                |
|  - PWM Streetlight LED Driver  - SX1276 LoRa Transceiver (868/915/433 MHz)               |
+-----------------------------------------------------------------------------------------+
                                          │
                                 [LoRa Wireless RF]
                                          ▼
+-----------------------------------------------------------------------------------------+
|                               CENTRAL LORA GATEWAY                                      |
|  - SX1276 LoRa RF Receiver     - Enriches with Gateway RSSI & SNR                       |
|  - Forwarding to HiveMQ Cloud  - Downlink LoRa Command Broadcaster                       |
+-----------------------------------------------------------------------------------------+
                                          │
                            [MQTT Protocol / TLS Port 8883]
                                          ▼
+-----------------------------------------------------------------------------------------+
|                               HIVEMQ CLOUD MQTT BROKER                                  |
|  Topics: smartlight/telemetry/<pole_id>  |  smartlight/command/<pole_id>                |
+-----------------------------------------------------------------------------------------+
                                          │
                                    [MQTT Client]
                                          ▼
+-----------------------------------------------------------------------------------------+
|                           PYTHON FLASK BACKEND & DIAGNOSTICS                            |
|  - Dual Data Source Manager (Hardware vs Synthetic Mode)                                |
|  - Autonomous Lighting Decision Engine (LDR Hysteresis + PIR Boost)                     |
|  - Streetlight Failure Detection & Triage Engine                                        |
|  - SQLite Time-Series Database                                                          |
|  - RESTful APIs + CSV & PDF Report Generators                                           |
+-----------------------------------------------------------------------------------------+
                                          │
                                   [HTTP / Web UI]
                                          ▼
+-----------------------------------------------------------------------------------------+
|                            RESPONSIVE WEB DASHBOARD                                     |
|  - Dark Industrial Control Console                                                      |
|  - 6 Real-Time Core KPI Cards                                                           |
|  - Streetlight Grid & Detail Inspection Modal                                           |
|  - Real-Time Alerts Management Table                                                    |
|  - Admin Fault Simulation Panel & Threshold Calibration                                 |
|  - Grafana Analytics Dashboard Integration                                              |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Technology Stack

- **Microcontroller**: ESP32-WROOM-32
- **LoRa Transceiver**: Semtech SX1276 (Ra-02 / RFM95W)
- **Firmware Development**: C/C++ (Arduino IDE / ESP-IDF)
- **Wireless RF Protocol**: LoRa (Long Range RF, 868 / 915 / 433 MHz)
- **Messaging Protocol**: MQTT v5 / v3.1.1
- **MQTT Broker**: HiveMQ Cloud (TLS encrypted on port 8883 or standard port 1883)
- **Backend Application**: Python 3.12+ / Flask
- **Database Engine**: SQLite 3 (with time-series indexing)
- **Frontend Dashboard**: HTML5, Responsive CSS3 (Dark Slate Industrial Theme), Vanilla JavaScript, Chart.js
- **Report Generation**: ReportLab (PDF), CSV export engine
- **Data Visualization**: Native Dashboard + Grafana Dashboard Export
- **Simulation**: Python-based multi-node diurnal synthetic sensor generator

---

## 3. Dual Data Source Architecture

A prominent toggle switch is integrated into the dashboard header:

1. **Synthetic Simulation Data**:
   - Generates realistic diurnal daylight cycles (sunrise, noon, sunset, night).
   - Generates dynamic ambient light (Lux), power draw (W), line voltage (V), current (A), and LoRa RSSI (-65 to -105 dBm).
   - Simulates sporadic pedestrian and vehicular motion triggers (PIR) with dynamic brightness boosting (100%).
   - Ready to run immediately **out-of-the-box** without physical hardware connected!
2. **ESP32 + LoRa Hardware Data**:
   - Receives live telemetry from physical ESP32 nodes forwarded by the LoRa Gateway through HiveMQ Cloud.
   - Forwards manual downlink commands directly to the hardware.
   - Strict source separation ensures synthetic and actual hardware readings are never mixed.

---

## 4. Default Demo User Accounts

| Role | Username | Password | Access Privileges |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | Full control: Data source toggle, manual overrides, node management, fault simulation, automation calibration, alert resolution, reports. |
| **Field Operator** | `user` | `user123` | Operational access: Live dashboard monitoring, inspection modal, alert acknowledgment, report downloads. |

---

## 5. Streetlight Failure Detection Engine

The diagnostic engine continuously compares electrical telemetry against commanded states and ambient conditions:

| Fault Type | Trigger Condition | Severity | System Action |
| :--- | :--- | :--- | :--- |
| `LED_BURN_OR_DRIVER_FAULT` | Commanded ON at &gt;15% brightness, but measured power is zero or abnormally low (&lt;8W) | **Critical** | Triggers critical alert; flags lamp as defective. |
| `ACTUATION_FAILURE` | Streetlight commanded ON but switch fails to close (`led_state == 0`) | **Critical** | Alerts field technician of relay failure. |
| `UNEXPECTED_SHUTDOWN` | LED was operating and commanded ON, but extinguished unexpectedly | **Critical** | Logs sudden shutdown. |
| `OVERPOWER_FAULT` | Measured wattage exceeds safety threshold (&gt;120W) | **Critical** | Flags short circuit / ballasting hazard. |
| `UNDER_VOLTAGE` / `OVER_VOLTAGE` | Mains voltage falls below 185V or rises above 265V | **Warning / Critical** | Alerts grid power quality issues. |
| `COMMUNICATION_TIMEOUT` | LoRa heartbeat packet missing for &gt;45 seconds | **Critical** | Marks pole as `OFFLINE` and generates lost-link alert. |
| `WEAK_LORA_SIGNAL` | LoRa RSSI drops below -115 dBm | **Warning** | Flags RF antenna or path obstruction. |

*Note: Streetlights are never marked as failed simply because they are OFF during normal daylight hours.*

---

## 6. Admin Fault Simulation Testing Panel

Accessible at `/simulation` for the Administrator account:
- **LED Failure**: Simulates open driver or burnt diode (0W power while commanded ON).
- **Mains Power Failure**: Simulates grid feeder cut (0V power blackout).
- **Node Disconnection**: Halts LoRa packets to test offline timeout detection.
- **LoRa Signal Drop**: Degrades RSSI to -120 dBm to test signal degradation alerts.
- **Power Surge**: Injects 165W overcurrent draw to trigger over-power warnings.
- **Gateway Disconnect**: Simulates central gateway going offline.
- **PIR Motion Trigger**: Triggers motion event boosting light to 100%.

---

## 7. Quick Start Guide

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure HiveMQ Cloud (Optional)
Edit `.env` to configure your HiveMQ Cloud cluster:
```ini
MQTT_BROKER_HOST=broker.hivemq.com
MQTT_BROKER_PORT=1883
MQTT_USE_TLS=False
MQTT_USERNAME=
MQTT_PASSWORD=
```
*(By default, the system uses public HiveMQ and starts in Synthetic Mode with 8 pre-seeded street poles).*

### Step 3: Launch the Application
```bash
python run.py
```

### Step 4: Access the Web Dashboard
Open your browser and navigate to:
```
https://smartstreetlight-0rz0.onrender.com
```
Log in using:
- Admin: `admin` / `admin123`
- User: `user` / `user123`

---

## 8. Hardware Deployment Guide

### ESP32 Streetlight Node Wiring
See `firmware/esp32_node/README.md` for pinouts, schematics, and Arduino flashing steps.

### ESP32 LoRa Gateway
See `firmware/esp32_gateway/README.md` for gateway setup and WiFi/HiveMQ credentials configuration.

### USB/Serial Gateway Bridge
If connecting your LoRa receiver to a PC or Raspberry Pi via USB:
```bash
python gateway/serial_gateway.py
```

---

## 9. Grafana Integration

1. Install the SQLite data source plugin in Grafana:
   ```bash
   grafana-cli plugins install frser-sqlite-datasource
   ```
2. Add `smart_street_light.db` as your SQLite data source.
3. Import `grafana/smart_street_light_dashboard.json`.
4. Monitor the complete network on your Grafana displays.

## 10. Deployment Platform: Render
 Include:
- Hosting platform: Render
- Runtime: Python 3
- Build command: pip install -r requirements.txt
- Start command: gunicorn --workers 1 --bind 0.0.0.0:$PORT wsgi:app
- Live URL: https://smartstreetlight-0rz0.onrender.com
