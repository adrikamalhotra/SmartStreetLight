# ESP32 Central LoRa Gateway Firmware

This directory contains the firmware for the **ESP32 Central Gateway** equipped with an **SX1276 LoRa transceiver** and an integrated **WiFi + MQTT client** connecting to **HiveMQ Cloud**.

---

## 1. Architectural Role

1. **LoRa Receiver**: Listens continuously for RF packets broadcasted by distributed ESP32 streetlight poles (`POLE-001`, `POLE-002`, etc.).
2. **Metadata Enrichment**: Captures LoRa link quality metrics (**RSSI** in dBm and **SNR** in dB) and attaches them to the telemetry payload.
3. **MQTT Forwarder**: Forwards telemetry to HiveMQ Cloud topic `smartlight/telemetry/<pole_id>`.
4. **Bidirectional Downlink Bridge**: Subscribes to `smartlight/command/#` on HiveMQ Cloud. When an operator triggers manual override or adjustments from the dashboard, the gateway converts the MQTT command into a LoRa downlink packet and broadcasts it over the air.
5. **Gateway Heartbeat**: Periodically broadcasts health and total packet counts to `smartlight/gateway/status`.

---

## 2. Pinout Configuration

| SX1276 Pin | ESP32 Pin | Description |
| :--- | :--- | :--- |
| **VCC** | 3.3V | Operating voltage |
| **GND** | GND | Ground |
| **NSS / CS** | GPIO 5 | SPI Slave Select |
| **MOSI** | GPIO 23 | Master Out Slave In |
| **MISO** | GPIO 19 | Master In Slave Out |
| **SCK** | GPIO 18 | SPI Clock |
| **RST** | GPIO 14 | LoRa Hardware Reset |
| **DIO0** | GPIO 2 | Packet Rx/Tx Interrupt |

---

## 3. HiveMQ Cloud Configuration

To use your dedicated HiveMQ Cloud cluster:
1. Log in to [HiveMQ Cloud Console](https://console.hivemq.cloud/).
2. Create a free serverless cluster.
3. Set the cluster URL as `MQTT_BROKER` in `esp32_gateway.ino`.
4. Create cluster credentials (username & password) and set `MQTT_USER` & `MQTT_PASS`.
5. For SSL/TLS (port 8883), change `WiFiClient` to `WiFiClientSecure` and call `espClient.setInsecure();` or load root CA.
