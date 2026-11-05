# ESP32 Streetlight Node Firmware (SX1276 LoRa)

This directory contains the production C/C++ firmware for individual street poles running on **ESP32 DevKit v1** paired with an **SX1276 LoRa** transceiver module.

---

## 1. Hardware Bill of Materials (BOM)

| Component | Model / Spec | Purpose |
| :--- | :--- | :--- |
| **Microcontroller** | ESP32-WROOM-32 (38-pin DevKit v1) | Core logic, PWM control, ADC reading |
| **LoRa Transceiver** | Semtech SX1276 (Ra-02 / HopeRF RFM95W) | Long-range wireless communication to Central Gateway |
| **Ambient Light Sensor** | LDR Photoresistor (GL5528) + 10kΩ pull-down | Photometric ambient light lux monitoring |
| **Motion Detector** | HC-SR501 or AM312 PIR Sensor | Pedestrian & vehicular movement detection |
| **Current Sensor** | Allegro ACS712-05B Hall-Effect Module | Measures RMS current draw of streetlamp |
| **Voltage Sensor** | ZMPT101B AC Voltage Transformer Module | Measures line voltage (230V AC) |
| **LED Driver / Switch** | High-Power MOSFET (IRF540N / AO3400) or Triac | PWM brightness modulation (0-100%) |
| **Power Supply** | AC-DC Step-Down (230V AC to 5V/3.3V DC, 2A) | Powers ESP32 and sensor modules |

---

## 2. Wiring & Pinout Diagram

### SX1276 LoRa Module to ESP32 (SPI)

| SX1276 Pin | ESP32 Pin | Description |
| :--- | :--- | :--- |
| **VCC** | 3.3V | Module operates strictly at 3.3V |
| **GND** | GND | Common ground |
| **NSS / CS** | GPIO 5 | Chip Select |
| **MOSI** | GPIO 23 | Master Out Slave In |
| **MISO** | GPIO 19 | Master In Slave Out |
| **SCK** | GPIO 18 | SPI Clock |
| **RST** | GPIO 14 | Module Reset |
| **DIO0** | GPIO 2 | Packet Tx/Rx Done Interrupt |

### Sensors & Actuators to ESP32

| Peripheral | ESP32 Pin | Function |
| :--- | :--- | :--- |
| **LDR (Photocell)** | GPIO 34 (ADC1_CH6) | Voltage divider midpoint |
| **PIR Motion Sensor** | GPIO 27 (Digital In) | Hardware interrupt on rising edge |
| **ACS712 Current** | GPIO 35 (ADC1_CH7) | Analog RMS current sampling |
| **ZMPT101B Voltage**| GPIO 32 (ADC1_CH4) | AC voltage waveform sampling |
| **LED PWM Output** | GPIO 4 | PWM channel 0 to MOSFET Gate / Driver |

---

## 3. Required Arduino IDE Libraries

Install these libraries from **Arduino IDE -> Library Manager**:
1. **LoRa** by Sandeep Mistry (v0.8.0 or higher)
2. **ArduinoJson** by Benoît Blanchon (v6.21.0 or v7.x)

---

## 4. Compilation & Flashing Instructions

1. Open `esp32_node.ino` in Arduino IDE.
2. Select Board: **ESP32 Dev Module**.
3. Set Upload Speed: **921600** (or 115200).
4. Change `POLE_ID` for each deployed pole (e.g., `"POLE-001"`, `"POLE-002"`).
5. Choose appropriate LoRa frequency for your region:
   - India: `868E6`
   - Europe: `868E6`
   - Americas: `915E6`
   - Asia (433MHz): `433E6`
6. Click **Upload**. Open Serial Monitor at **115200 baud** to verify startup and telemetry broadcasts.
