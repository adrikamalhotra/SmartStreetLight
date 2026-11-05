import threading
import time
import math
import random
import datetime
from backend.database import get_db_connection, get_system_config, set_system_config
from backend.automation_engine import AutomationEngine
from backend.config import Config

class StreetLightSimulator:
    def __init__(self):
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Track forced simulated faults: { "POLE-001": "led_failure", ... }
        self.injected_faults = {}
        # Track motion detection timestamps: { "POLE-001": expire_epoch }
        self.motion_timers = {}
        # Diurnal virtual time counter (0.0 to 24.0 hours, advances smoothly)
        self.virtual_hour = 19.5 # Start around dusk/evening for great visualization
        self.gateway_packets = 0

    def start(self):
        with self._lock:
            if not self._running:
                self._running = True
                self._thread = threading.Thread(target=self._run_loop, daemon=True, name="StreetLightSimulatorThread")
                self._thread.start()
                print("[Simulator] Synthetic Data Generator started.")

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            print("[Simulator] Synthetic Data Generator stopped.")

    def is_running(self):
        return self._running

    def inject_fault(self, pole_id, fault_type):
        """fault_type: 'led_failure', 'power_failure', 'node_disconnected', 'lora_drop', 'abnormal_power', 'gateway_disconnect'"""
        with self._lock:
            if fault_type == 'clear':
                self.injected_faults.pop(pole_id, None)
                print(f"[Simulator] Cleared fault on {pole_id}")
            else:
                self.injected_faults[pole_id] = fault_type
                print(f"[Simulator] Injected fault '{fault_type}' on {pole_id}")

    def clear_all_faults(self):
        with self._lock:
            self.injected_faults.clear()

    def get_injected_faults(self):
        with self._lock:
            return dict(self.injected_faults)

    def trigger_motion(self, pole_id):
        """Simulates PIR motion sensor trigger on pole"""
        timeout = int(get_system_config('motion_timeout_sec', Config.MOTION_TIMEOUT_SEC))
        with self._lock:
            self.motion_timers[pole_id] = time.time() + timeout

    def _calculate_ambient_lux(self, hour):
        """
        Calculates realistic outdoor ambient light in Lux according to hour of day (0-24):
        - Midnight (00:00 - 05:00): 0.1 - 5 Lux
        - Sunrise / Dawn (05:00 - 07:00): 5 -> 400 Lux
        - Daytime (07:00 - 17:00): 400 -> 15000+ Lux
        - Sunset / Dusk (17:00 - 19:30): 400 -> 10 Lux
        - Night (19:30 - 24:00): 10 -> 0.1 Lux
        """
        # Sine wave model for daylight curve: peaks at 12:00 (noon)
        if 6.0 <= hour <= 18.0:
            # Daytime
            sun_angle = math.sin((hour - 6.0) / 12.0 * math.pi)
            lux = 50.0 + (sun_angle ** 1.5) * 8000.0
        elif 18.0 < hour <= 20.0:
            # Twilight / Dusk: fast drop
            fraction = (20.0 - hour) / 2.0
            lux = 5.0 + (fraction ** 2) * 250.0
        elif 4.5 <= hour < 6.0:
            # Dawn: rising
            fraction = (hour - 4.5) / 1.5
            lux = 5.0 + (fraction ** 2) * 250.0
        else:
            # Full Night
            lux = random.uniform(1.0, 15.0)

        # Add natural cloud/atmospheric fluctuation
        lux = max(1.0, lux + random.uniform(-5.0, 5.0))
        return round(lux, 1)

    def _run_loop(self):
        while self._running:
            try:
                # Check active data source mode
                current_source = get_system_config('data_source', Config.DEFAULT_DATA_SOURCE)
                if current_source != 'synthetic':
                    # In hardware mode, simulator remains dormant but thread stays alive
                    time.sleep(2.0)
                    continue

                # Progress virtual time: advance by ~2.5 virtual minutes per tick (so full 24h cycle completes in ~10 mins)
                self.virtual_hour = (self.virtual_hour + 0.04) % 24.0

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM nodes")
                nodes = cursor.fetchall()
                conn.close()

                ldr_on = float(get_system_config('ldr_on_threshold', Config.LDR_ON_THRESHOLD))
                ldr_off = float(get_system_config('ldr_off_threshold', Config.LDR_OFF_THRESHOLD))
                night_bright = int(get_system_config('night_brightness', Config.NIGHT_BRIGHTNESS))
                motion_bright = int(get_system_config('motion_brightness', Config.MOTION_BRIGHTNESS))

                now_ts = time.time()
                current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for node in nodes:
                    pole_id = node['pole_id']
                    forced_fault = self.injected_faults.get(pole_id)

                    # Fault: Node Disconnected (skip sending telemetry, triggering timeout)
                    if forced_fault == 'node_disconnected':
                        continue

                    # Base environmental ambient lux
                    base_lux = self._calculate_ambient_lux(self.virtual_hour)
                    # Small variation per pole
                    pole_lux = max(1.0, round(base_lux + random.uniform(-3.0, 3.0), 1))

                    # PIR Motion Detection logic (random pedestrian/car triggers at night)
                    motion_active = 0
                    if pole_id in self.motion_timers:
                        if now_ts < self.motion_timers[pole_id]:
                            motion_active = 1
                        else:
                            del self.motion_timers[pole_id]
                    elif pole_lux < ldr_on and random.random() < 0.20:
                        # 20% chance of spontaneous motion event at night
                        self.motion_timers[pole_id] = now_ts + int(get_system_config('motion_timeout_sec', Config.MOTION_TIMEOUT_SEC))
                        motion_active = 1

                    # Evaluate auto state vs manual mode
                    mode = node['mode']
                    if mode == 'manual':
                        commanded_state = node['commanded_state']
                        target_brightness = node['brightness']
                    else:
                        decision = AutomationEngine.evaluate_node_control({
                            'mode': 'auto',
                            'ambient_lux': pole_lux,
                            'motion_detected': motion_active,
                            'led_state': node['led_state']
                        }, {
                            'ldr_on_threshold': ldr_on,
                            'ldr_off_threshold': ldr_off,
                            'night_brightness': night_bright,
                            'motion_brightness': motion_bright
                        })
                        commanded_state = decision['commanded_state']
                        target_brightness = decision['target_brightness']

                    # Default healthy electrical parameters
                    led_state = commanded_state
                    brightness = target_brightness
                    voltage_v = round(random.uniform(228.0, 234.0), 1)

                    if commanded_state == 1 and brightness > 0:
                        # Streetlight 70W rated LED: Power proportional to brightness %
                        # Power = (brightness / 100) * 70W +/- noise
                        base_power = (brightness / 100.0) * 70.0
                        power_w = round(base_power + random.uniform(-1.5, 1.5), 2)
                        current_a = round(power_w / voltage_v, 3)
                    else:
                        power_w = 0.0
                        current_a = 0.0
                        brightness = 0
                        led_state = 0

                    lora_rssi = random.randint(-85, -68)
                    lora_snr = round(random.uniform(7.5, 10.5), 1)

                    # Injected Fault Manifestations
                    if forced_fault == 'led_failure':
                        # Commanded ON, but LED is burnt out or driver open -> Power is 0W, LED is dark
                        led_state = 0
                        power_w = 0.0
                        current_a = 0.0
                    elif forced_fault == 'power_failure':
                        # Complete pole supply blackout
                        voltage_v = 0.0
                        current_a = 0.0
                        power_w = 0.0
                        led_state = 0
                        brightness = 0
                    elif forced_fault == 'abnormal_power':
                        # Short circuit / runaway driver: 165W power!
                        power_w = round(random.uniform(150.0, 175.0), 1)
                        current_a = round(power_w / voltage_v, 2)
                    elif forced_fault == 'lora_drop':
                        # LoRa RF signal severely degraded
                        lora_rssi = random.randint(-122, -116)
                        lora_snr = round(random.uniform(-4.0, 1.0), 1)

                    # Process synthetic telemetry into the system
                    telemetry = {
                        "pole_id": pole_id,
                        "ambient_lux": pole_lux,
                        "led_state": led_state,
                        "brightness": brightness,
                        "power_w": power_w,
                        "current_a": current_a,
                        "voltage_v": voltage_v,
                        "lora_rssi": lora_rssi,
                        "lora_snr": lora_snr,
                        "motion_detected": motion_active,
                        "source": "synthetic",
                        "forced_fault": forced_fault
                    }

                    AutomationEngine.process_telemetry(telemetry)
                    self.gateway_packets += 1

                # Check for offline nodes (timeouts)
                AutomationEngine.check_offline_nodes()

                # Update Gateway Status
                gateway_fault = self.injected_faults.get('GATEWAY')
                gw_status = 'offline' if gateway_fault == 'gateway_disconnect' else 'online'
                mqtt_status = 'disconnected' if gateway_fault == 'gateway_disconnect' else 'connected'

                conn = get_db_connection()
                conn.execute('''
                    UPDATE gateway_status SET
                        status = ?,
                        mqtt_status = ?,
                        active_source = 'synthetic',
                        packets_received = packets_received + ?,
                        last_seen = ?
                    WHERE gateway_id = 'GW-LORA-CENTRAL-01'
                ''', (gw_status, mqtt_status, len(nodes), current_time_str))
                conn.commit()
                conn.close()

            except Exception as e:
                print(f"[Simulator Error] {e}")

            # Sleep between telemetry broadcast cycles (2.5 seconds for snappy, responsive dashboard)
            time.sleep(2.5)

simulator_instance = StreetLightSimulator()
