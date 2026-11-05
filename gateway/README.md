# Central LoRa Gateway & Serial Bridge

The Central Gateway can be operated in two modular ways:

1. **Standalone ESP32 Gateway**: An ESP32 connected to WiFi that bridges LoRa packets directly to HiveMQ Cloud over MQTT (see `firmware/esp32_gateway`).
2. **PC/Host Connected Serial Gateway Bridge**: An ESP32 or USB LoRa dongle plugged into a PC/Raspberry Pi running `serial_gateway.py`.

---

## Running the Python Serial Gateway Bridge

If your LoRa gateway receiver is connected to your computer via USB:

```bash
# Optional dependency
pip install pyserial

# Run gateway bridge (auto-detects COM port)
python gateway/serial_gateway.py

# Or specify a specific COM port (e.g. COM3 or /dev/ttyUSB0)
python gateway/serial_gateway.py COM3
```

This bridge reads incoming JSON strings over serial, publishes them to HiveMQ Cloud (`smartlight/telemetry/<pole_id>`), and forwards downlink commands from the web dashboard back to the streetlights.
