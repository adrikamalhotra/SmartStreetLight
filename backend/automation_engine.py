import uuid
import datetime
from backend.database import get_db_connection, get_system_config
from backend.config import Config

class AutomationEngine:
    @staticmethod
    def evaluate_node_control(node_data, config_overrides=None):
        """
        Calculates expected LED state and target brightness based on ambient lux,
        motion detection, and node mode (auto vs manual).
        """
        mode = node_data.get('mode', 'auto')
        if mode == 'manual':
            # In manual mode, keep operator's commanded state and brightness
            return {
                "commanded_state": int(node_data.get('commanded_state', node_data.get('led_state', 0))),
                "target_brightness": int(node_data.get('brightness', 0)),
                "reason": "Manual Operator Override"
            }

        # Auto Mode Evaluation
        ldr_on = float(config_overrides.get('ldr_on_threshold') if config_overrides else get_system_config('ldr_on_threshold', Config.LDR_ON_THRESHOLD))
        ldr_off = float(config_overrides.get('ldr_off_threshold') if config_overrides else get_system_config('ldr_off_threshold', Config.LDR_OFF_THRESHOLD))
        night_bright = int(config_overrides.get('night_brightness') if config_overrides else get_system_config('night_brightness', Config.NIGHT_BRIGHTNESS))
        motion_bright = int(config_overrides.get('motion_brightness') if config_overrides else get_system_config('motion_brightness', Config.MOTION_BRIGHTNESS))

        ambient_lux = float(node_data.get('ambient_lux', 100.0))
        motion_detected = int(node_data.get('motion_detected', 0))

        # Hysteresis control:
        # If lux <= ldr_on: Nighttime/Low light -> Turn ON
        # If lux >= ldr_off: Daytime/Sufficient sunlight -> Turn OFF
        # Between ldr_on and ldr_off: maintain current state unless motion triggers
        current_led_state = int(node_data.get('led_state', 0))

        if ambient_lux <= ldr_on:
            target_state = 1
            if motion_detected == 1:
                target_brightness = motion_bright
                reason = "Nighttime + Motion Detected (Full Brightness)"
            else:
                target_brightness = night_bright
                reason = "Nighttime Automation (Standard Lighting)"
        elif ambient_lux >= ldr_off:
            target_state = 0
            target_brightness = 0
            reason = "Daylight Detected (Energy Saving OFF)"
        else:
            # Twilight zone: maintain current commanded state
            target_state = current_led_state
            target_brightness = night_bright if target_state == 1 else 0
            reason = "Ambient light in transition band"

        return {
            "commanded_state": target_state,
            "target_brightness": target_brightness,
            "reason": reason
        }

    @staticmethod
    def process_telemetry(telemetry):
        """
        Main entry point for incoming telemetry (from MQTT or Simulator).
        Updates node database record, checks for faults, records history, and issues alerts.
        """
        pole_id = telemetry.get('pole_id')
        if not pole_id:
            return None

        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch existing node info
        cursor.execute("SELECT * FROM nodes WHERE pole_id = ?", (pole_id,))
        node = cursor.fetchone()

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        source = telemetry.get('source', 'synthetic')

        # Telemetry fields with safety fallbacks
        ambient_lux = float(telemetry.get('ambient_lux', 100.0))
        led_state = int(telemetry.get('led_state', 0))
        brightness = int(telemetry.get('brightness', 0))
        power_w = float(telemetry.get('power_w', 0.0))
        current_a = float(telemetry.get('current_a', 0.0))
        voltage_v = float(telemetry.get('voltage_v', 230.0))
        lora_rssi = int(telemetry.get('lora_rssi', -75))
        lora_snr = float(telemetry.get('lora_snr', 8.0))
        motion_detected = int(telemetry.get('motion_detected', 0))
        forced_fault = telemetry.get('forced_fault', None)

        mode = node['mode'] if node else 'auto'
        commanded_state = node['commanded_state'] if node else led_state

        if mode == 'auto':
            # Check automation rules to see what state is expected
            decision = AutomationEngine.evaluate_node_control({
                'mode': 'auto',
                'ambient_lux': ambient_lux,
                'motion_detected': motion_detected,
                'led_state': led_state
            })
            commanded_state = decision['commanded_state']

        # Run fault analysis
        fault_type, severity, description = AutomationEngine.detect_faults(
            pole_id=pole_id,
            commanded_state=commanded_state,
            led_state=led_state,
            brightness=brightness,
            power_w=power_w,
            current_a=current_a,
            voltage_v=voltage_v,
            lora_rssi=lora_rssi,
            forced_fault=forced_fault
        )

        # Determine node status
        status = 'working'
        if fault_type:
            status = 'failed' if severity == 'critical' else 'warning'

        # Update or insert into nodes table
        if node:
            cursor.execute('''
                UPDATE nodes SET
                    status = ?,
                    led_state = ?,
                    commanded_state = ?,
                    brightness = ?,
                    ambient_lux = ?,
                    power_w = ?,
                    current_a = ?,
                    voltage_v = ?,
                    lora_rssi = ?,
                    lora_snr = ?,
                    motion_detected = ?,
                    failure_type = ?,
                    last_seen = ?
                WHERE pole_id = ?
            ''', (status, led_state, commanded_state, brightness, ambient_lux,
                  power_w, current_a, voltage_v, lora_rssi, lora_snr,
                  motion_detected, fault_type, now_str, pole_id))
        else:
            cursor.execute('''
                INSERT INTO nodes 
                (pole_id, location_name, latitude, longitude, status, led_state, commanded_state,
                 brightness, ambient_lux, power_w, current_a, voltage_v, lora_rssi, lora_snr, mode,
                 motion_detected, failure_type, last_seen)
                VALUES (?, ?, 28.6139, 77.2090, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'auto', ?, ?, ?)
            ''', (pole_id, f"Node {pole_id}", status, led_state, commanded_state,
                  brightness, ambient_lux, power_w, current_a, voltage_v, lora_rssi, lora_snr,
                  motion_detected, fault_type, now_str))

        # Record in telemetry history
        cursor.execute('''
            INSERT INTO telemetry_history 
            (pole_id, timestamp, ambient_lux, led_state, brightness, power_w, current_a, voltage_v, lora_rssi, motion_detected, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pole_id, now_str, ambient_lux, led_state, brightness, power_w, current_a, voltage_v, lora_rssi, motion_detected, source))

        # Record or resolve alerts
        if fault_type:
            AutomationEngine._record_alert(cursor, pole_id, fault_type, severity, description)
        else:
            # Auto-resolve existing active alerts for this pole if the condition has cleared
            cursor.execute('''
                UPDATE alerts SET status = 'resolved', resolved_at = ?
                WHERE pole_id = ? AND status = 'active'
            ''', (now_str, pole_id))

        conn.commit()
        conn.close()

        return {
            "pole_id": pole_id,
            "status": status,
            "fault_type": fault_type,
            "severity": severity,
            "commanded_state": commanded_state
        }

    @staticmethod
    def detect_faults(pole_id, commanded_state, led_state, brightness, power_w, current_a, voltage_v, lora_rssi, forced_fault=None):
        """
        Executes exhaustive diagnostic checks for streetlight failures.
        Returns: (fault_type, severity, description) or (None, None, None)
        """
        min_v = float(get_system_config('min_voltage_v', Config.MIN_VOLTAGE_V))
        max_v = float(get_system_config('max_voltage_v', Config.MAX_VOLTAGE_V))
        max_p = float(get_system_config('max_power_w', Config.MAX_POWER_W))

        # Handle explicit injection first
        if forced_fault:
            if forced_fault == 'led_failure':
                return ('LED_FAILURE', 'critical', 'LED driver or lamp open circuit: Commanded ON but no light output')
            elif forced_fault == 'power_failure':
                return ('POWER_FAILURE', 'critical', 'Streetlight power failure: Zero line voltage detected')
            elif forced_fault == 'abnormal_power':
                return ('ABNORMAL_POWER', 'critical', f'Abnormally high power draw ({power_w:.1f}W > {max_p:.1f}W threshold)')
            elif forced_fault == 'lora_drop':
                return ('LORA_DEGRADATION', 'warning', f'LoRa link degradation: Weak signal ({lora_rssi} dBm)')
            elif forced_fault == 'node_disconnected':
                return ('NODE_DISCONNECTED', 'critical', 'Node disconnected from LoRa gateway')

        # 1. Commanded ON but power is zero or abnormally low
        if commanded_state == 1 and brightness > 15:
            if power_w < Config.MIN_POWER_WHEN_ON_W:
                return ('LED_BURN_OR_DRIVER_FAULT', 'critical',
                        f'LED is commanded ON ({brightness}%) but measured power is only {power_w:.1f}W (expected > {Config.MIN_POWER_WHEN_ON_W}W)')

        # 2. LED fails to turn ON when commanded
        if commanded_state == 1 and led_state == 0:
            return ('ACTUATION_FAILURE', 'critical',
                    'Streetlight relay/switch failed to turn ON when commanded')

        # 3. Unexpected LED shutdown (was ON, but switched off while commanded ON)
        if commanded_state == 1 and led_state == 0 and brightness > 0:
            return ('UNEXPECTED_SHUTDOWN', 'critical',
                    'Streetlight unexpectedly shut down while in operation')

        # 4. Abnormally high power consumption (short circuit / ballasting failure)
        if power_w > max_p:
            return ('OVERPOWER_FAULT', 'critical',
                    f'Abnormally high power consumption: {power_w:.1f}W exceeds maximum threshold of {max_p:.1f}W')

        # 5. Abnormal line voltage
        if voltage_v < min_v and voltage_v > 10.0: # (ignore 0 which is complete blackout)
            return ('UNDER_VOLTAGE', 'warning',
                    f'Low mains voltage detected: {voltage_v:.1f}V (minimum allowable is {min_v:.1f}V)')
        elif voltage_v > max_v:
            return ('OVER_VOLTAGE', 'critical',
                    f'Severe overvoltage condition: {voltage_v:.1f}V exceeds safety limit of {max_v:.1f}V')

        # 6. Abnormal current draw
        if current_a > 1.25:
            return ('OVERCURRENT', 'critical',
                    f'Excessive current draw detected: {current_a:.2f}A')

        # 7. Poor LoRa Signal
        if lora_rssi < -115:
            return ('WEAK_LORA_SIGNAL', 'warning',
                    f'LoRa link quality marginal: RSSI is {lora_rssi} dBm (packet loss likely)')

        return (None, None, None)

    @staticmethod
    def check_offline_nodes():
        """
        Scans all nodes for communication timeouts.
        If last_seen exceeds communication_timeout_sec, marks node as 'offline'.
        """
        timeout_sec = int(get_system_config('communication_timeout_sec', Config.COMMUNICATION_TIMEOUT_SEC))
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM nodes")
        nodes = cursor.fetchall()
        now = datetime.datetime.now()

        for node in nodes:
            last_seen_str = node['last_seen']
            if not last_seen_str:
                continue

            try:
                last_seen_dt = datetime.datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            elapsed = (now - last_seen_dt).total_seconds()
            if elapsed > timeout_sec:
                if node['status'] != 'offline':
                    cursor.execute("UPDATE nodes SET status = 'offline', failure_type = 'COMMUNICATION_TIMEOUT' WHERE id = ?", (node['id'],))
                    # Record alert
                    AutomationEngine._record_alert(
                        cursor,
                        node['pole_id'],
                        'COMMUNICATION_TIMEOUT',
                        'critical',
                        f"Streetlight node stopped communicating ({int(elapsed)}s since last packet)"
                    )

        conn.commit()
        conn.close()

    @staticmethod
    def _record_alert(cursor, pole_id, fault_type, severity, description):
        """Helper to create alert if an identical active alert doesn't already exist"""
        cursor.execute('''
            SELECT id FROM alerts 
            WHERE pole_id = ? AND fault_type = ? AND status = 'active'
        ''', (pole_id, fault_type))
        existing = cursor.fetchone()

        if not existing:
            alert_id = f"ALT-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute('''
                INSERT INTO alerts (alert_id, pole_id, fault_type, severity, description, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            ''', (alert_id, pole_id, fault_type, severity, description))
