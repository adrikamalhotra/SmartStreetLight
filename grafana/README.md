# Grafana Visualization Setup

This directory contains the ready-to-import Grafana dashboard specification for the **LoRa-Based Smart Street Light Automation System**.

---

## 1. Prerequisites

- [Grafana OSS / Enterprise](https://grafana.com/grafana/download) (v9+ or v10+)
- **SQLite Data Source Plugin** for Grafana:
  ```bash
  grafana-cli plugins install frser-sqlite-datasource
  ```
  *(Restart Grafana server after installing)*

---

## 2. Setting Up the SQLite Data Source

1. In Grafana, navigate to **Configuration &rarr; Data Sources &rarr; Add data source**.
2. Select **SQLite**.
3. Name: `SmartStreetLight-DB`
4. Path: Provide the absolute path to your `smart_street_light.db` file (e.g. `g:/SmartStreetLight/smart_street_light.db`).
5. Click **Save & Test**.

---

## 3. Importing the Dashboard

1. Navigate to **Dashboards &rarr; Import**.
2. Upload `smart_street_light_dashboard.json` or paste its contents into the JSON text area.
3. Select your SQLite data source.
4. Click **Import**.

The dashboard includes:
- **6 Top KPI Stat Panels**: Total Nodes, Working Lights, Failed Lights, Offline Nodes, Total Grid Power, Active Alerts.
- **Power Draw Time-Series Graph**: Real-time grid wattage trend.
- **Streetlight Health Distribution**: Working vs Failed vs Offline breakdown.
- **Node Telemetry Table**: Real-time Pole ID, brightness, ambient lux, watts, and LoRa RSSI.
- **Active Diagnostic Alerts Table**: Live incident triage.
