import os
import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, Response
from backend.config import Config
from backend.database import init_db, get_db_connection, get_system_config, set_system_config
from backend.auth import authenticate_user, login_user_session, logout_user_session, get_current_user, login_required, admin_required
from backend.automation_engine import AutomationEngine
from backend.simulator import simulator_instance
from backend.mqtt_service import mqtt_service_instance
from backend.reports import generate_telemetry_csv, generate_alerts_csv, generate_summary_pdf

BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static")
)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)

# Context processor for templates
@app.context_processor
def inject_global_template_data():
    return {
        'current_user': get_current_user(),
        'active_source': get_system_config('data_source', Config.DEFAULT_DATA_SOURCE)
    }

# ==========================================
# PAGE ROUTES
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = authenticate_user(username, password)
        if user:
            login_user_session(user)
            next_url = request.args.get('next') or url_for('dashboard_page')
            return redirect(next_url)
        return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

@app.route('/logout')
def logout_page():
    logout_user_session()
    return redirect(url_for('login_page'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard_page():
    return render_template('index.html')

@app.route('/alerts')
@login_required
def alerts_page():
    return render_template('alerts.html')

@app.route('/simulation')
@admin_required
def simulation_page():
    return render_template('simulation.html')

@app.route('/reports')
@login_required
def reports_page():
    return render_template('reports.html')

# ==========================================
# SYSTEM & SUMMARY API
# ==========================================

@app.route('/api/status', methods=['GET'])
@login_required
def api_status():
    conn = get_db_connection()
    nodes = conn.execute("SELECT * FROM nodes").fetchall()
    alerts = conn.execute("SELECT * FROM alerts WHERE status = 'active'").fetchall()
    gw = conn.execute("SELECT * FROM gateway_status WHERE gateway_id = 'GW-LORA-CENTRAL-01'").fetchone()
    conn.close()

    total_nodes = len(nodes)
    working_lights = sum(1 for n in nodes if n['status'] == 'working')
    failed_lights = sum(1 for n in nodes if n['status'] in ('failed', 'warning'))
    offline_nodes = sum(1 for n in nodes if n['status'] == 'offline')
    total_power_w = round(sum(n['power_w'] for n in nodes), 1)
    active_alerts = len(alerts)

    active_source = get_system_config('data_source', Config.DEFAULT_DATA_SOURCE)

    return jsonify({
        "total_nodes": total_nodes,
        "working_lights": working_lights,
        "failed_lights": failed_lights,
        "offline_nodes": offline_nodes,
        "total_power_w": total_power_w,
        "active_alerts": active_alerts,
        "active_source": active_source,
        "virtual_hour": round(simulator_instance.virtual_hour, 2) if active_source == 'synthetic' else None,
        "gateway": {
            "id": gw['gateway_id'] if gw else 'GW-01',
            "status": gw['status'] if gw else 'online',
            "mqtt_status": gw['mqtt_status'] if gw else 'connected',
            "packets_received": gw['packets_received'] if gw else 0,
            "last_seen": gw['last_seen'] if gw else ''
        }
    })

# ==========================================
# DATA SOURCE TOGGLE (SYNTHETIC vs HARDWARE)
# ==========================================

@app.route('/api/datasource/toggle', methods=['POST'])
@admin_required
def api_toggle_datasource():
    req_data = request.get_json() or {}
    new_source = req_data.get('source')
    if new_source not in ('synthetic', 'hardware'):
        return jsonify({"error": "Invalid source. Must be 'synthetic' or 'hardware'"}), 400

    set_system_config('data_source', new_source)

    # Sync gateway table
    conn = get_db_connection()
    conn.execute("UPDATE gateway_status SET active_source = ? WHERE gateway_id = 'GW-LORA-CENTRAL-01'", (new_source,))
    conn.commit()
    conn.close()

    print(f"[System] Switched active Gateway Data Source to: {new_source.upper()}")
    return jsonify({
        "success": True,
        "active_source": new_source,
        "message": f"Successfully activated {new_source.capitalize()} Data Mode"
    })

# ==========================================
# STREETLIGHT NODES API
# ==========================================

@app.route('/api/nodes', methods=['GET'])
@login_required
def api_get_nodes():
    conn = get_db_connection()
    nodes = conn.execute("SELECT * FROM nodes ORDER BY pole_id ASC").fetchall()
    conn.close()

    result = []
    for n in nodes:
        result.append({
            "id": n['id'],
            "pole_id": n['pole_id'],
            "location_name": n['location_name'],
            "latitude": n['latitude'],
            "longitude": n['longitude'],
            "status": n['status'],
            "led_state": n['led_state'],
            "commanded_state": n['commanded_state'],
            "brightness": n['brightness'],
            "ambient_lux": n['ambient_lux'],
            "power_w": n['power_w'],
            "current_a": n['current_a'],
            "voltage_v": n['voltage_v'],
            "lora_rssi": n['lora_rssi'],
            "lora_snr": n['lora_snr'],
            "mode": n['mode'],
            "motion_detected": n['motion_detected'],
            "failure_type": n['failure_type'],
            "last_seen": n['last_seen']
        })
    return jsonify(result)

@app.route('/api/nodes/<pole_id>', methods=['GET'])
@login_required
def api_get_node_detail(pole_id):
    conn = get_db_connection()
    node = conn.execute("SELECT * FROM nodes WHERE pole_id = ?", (pole_id,)).fetchone()
    if not node:
        conn.close()
        return jsonify({"error": "Node not found"}), 404

    # Fetch last 15 telemetry entries for history graph
    history = conn.execute('''
        SELECT timestamp, power_w, ambient_lux, brightness, voltage_v, lora_rssi
        FROM telemetry_history 
        WHERE pole_id = ? 
        ORDER BY timestamp DESC LIMIT 20
    ''', (pole_id,)).fetchall()

    # Fetch active alerts for this pole
    alerts = conn.execute('''
        SELECT * FROM alerts 
        WHERE pole_id = ? AND status = 'active'
        ORDER BY created_at DESC
    ''', (pole_id,)).fetchall()
    conn.close()

    return jsonify({
        "node": dict(node),
        "history": [dict(h) for h in reversed(history)],
        "alerts": [dict(a) for a in alerts]
    })

@app.route('/api/nodes/<pole_id>/control', methods=['POST'])
@admin_required
def api_control_node(pole_id):
    data = request.get_json() or {}
    mode = data.get('mode') # 'auto' or 'manual'
    led_state = data.get('led_state') # 0 or 1
    brightness = data.get('brightness') # 0-100

    conn = get_db_connection()
    node = conn.execute("SELECT * FROM nodes WHERE pole_id = ?", (pole_id,)).fetchone()
    if not node:
        conn.close()
        return jsonify({"error": "Node not found"}), 404

    new_mode = mode if mode in ('auto', 'manual') else node['mode']
    new_cmd_state = int(led_state) if led_state is not None else node['commanded_state']
    new_brightness = int(brightness) if brightness is not None else node['brightness']

    # If manual mode, calculate power & apply directly
    if new_mode == 'manual':
        if new_cmd_state == 1:
            calculated_power = round((new_brightness / 100.0) * 70.0, 1)
            calculated_current = round(calculated_power / 230.0, 3)
        else:
            calculated_power = 0.0
            calculated_current = 0.0
            new_brightness = 0

        conn.execute('''
            UPDATE nodes SET
                mode = ?,
                commanded_state = ?,
                led_state = ?,
                brightness = ?,
                power_w = ?,
                current_a = ?
            WHERE pole_id = ?
        ''', (new_mode, new_cmd_state, new_cmd_state, new_brightness, calculated_power, calculated_current, pole_id))
    else:
        conn.execute('''
            UPDATE nodes SET mode = ? WHERE pole_id = ?
        ''', (new_mode, pole_id))

    conn.commit()
    conn.close()

    # Also forward downlink command via MQTT for actual hardware
    mqtt_service_instance.publish_command(pole_id, {
        "command": "SET_CONTROL",
        "mode": new_mode,
        "state": new_cmd_state,
        "brightness": new_brightness
    })

    return jsonify({
        "success": True,
        "message": f"Updated control settings for {pole_id}",
        "pole_id": pole_id,
        "mode": new_mode,
        "commanded_state": new_cmd_state,
        "brightness": new_brightness
    })

@app.route('/api/nodes/add', methods=['POST'])
@admin_required
def api_add_node():
    data = request.get_json() or {}
    pole_id = data.get('pole_id', '').strip().upper()
    location_name = data.get('location_name', f"Pole {pole_id}")
    lat = float(data.get('latitude', 28.6139))
    lon = float(data.get('longitude', 77.2090))

    if not pole_id:
        return jsonify({"error": "Pole ID is required"}), 400

    conn = get_db_connection()
    try:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('''
            INSERT INTO nodes 
            (pole_id, location_name, latitude, longitude, status, led_state, commanded_state, 
             brightness, ambient_lux, power_w, current_a, voltage_v, lora_rssi, lora_snr, mode, last_seen)
            VALUES (?, ?, ?, ?, 'working', 0, 0, 0, 200.0, 0.0, 0.0, 230.0, -75, 9.0, 'auto', ?)
        ''', (pole_id, location_name, lat, lon, now_str))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Node {pole_id} already exists or error: {str(e)}"}), 400

    conn.close()
    return jsonify({"success": True, "message": f"Added node {pole_id}"})

@app.route('/api/nodes/<pole_id>', methods=['DELETE'])
@admin_required
def api_delete_node(pole_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM nodes WHERE pole_id = ?", (pole_id,))
    conn.execute("DELETE FROM alerts WHERE pole_id = ?", (pole_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Deleted node {pole_id}"})

# ==========================================
# ALERTS API
# ==========================================

@app.route('/api/alerts', methods=['GET'])
@login_required
def api_get_alerts():
    status_filter = request.args.get('status', 'all')
    conn = get_db_connection()

    if status_filter in ('active', 'acknowledged', 'resolved'):
        rows = conn.execute("SELECT * FROM alerts WHERE status = ? ORDER BY created_at DESC LIMIT 100", (status_filter,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 100").fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
@login_required
def api_acknowledge_alert(alert_id):
    user = get_current_user()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    conn.execute('''
        UPDATE alerts SET
            status = 'acknowledged',
            acknowledged_at = ?,
            acknowledged_by = ?
        WHERE alert_id = ?
    ''', (now_str, user['username'], alert_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Alert {alert_id} acknowledged"})

@app.route('/api/alerts/<alert_id>/resolve', methods=['POST'])
@admin_required
def api_resolve_alert(alert_id):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    alert = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
    if alert:
        conn.execute('''
            UPDATE alerts SET
                status = 'resolved',
                resolved_at = ?
            WHERE alert_id = ?
        ''', (now_str, alert_id))
        
        # Reset node failure type if no other active alerts
        pole_id = alert['pole_id']
        other_active = conn.execute("SELECT COUNT(*) FROM alerts WHERE pole_id = ? AND status = 'active' AND alert_id != ?", (pole_id, alert_id)).fetchone()[0]
        if other_active == 0:
            conn.execute("UPDATE nodes SET status = 'working', failure_type = NULL WHERE pole_id = ?", (pole_id,))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Alert {alert_id} marked resolved"})

# ==========================================
# FAULT SIMULATION API (ADMIN ONLY)
# ==========================================

@app.route('/api/simulation/faults', methods=['GET'])
@admin_required
def api_get_sim_faults():
    return jsonify(simulator_instance.get_injected_faults())

@app.route('/api/simulation/inject', methods=['POST'])
@admin_required
def api_inject_fault():
    data = request.get_json() or {}
    pole_id = data.get('pole_id')
    fault_type = data.get('fault_type')

    if not pole_id or not fault_type:
        return jsonify({"error": "pole_id and fault_type are required"}), 400

    simulator_instance.inject_fault(pole_id, fault_type)
    return jsonify({
        "success": True,
        "message": f"Applied fault action '{fault_type}' on {pole_id}"
    })

@app.route('/api/simulation/motion', methods=['POST'])
def api_trigger_motion():
    data = request.get_json() or {}
    pole_id = data.get('pole_id')
    if not pole_id:
        return jsonify({"error": "pole_id is required"}), 400

    simulator_instance.trigger_motion(pole_id)
    return jsonify({"success": True, "message": f"PIR motion triggered on {pole_id}"})

# ==========================================
# AUTOMATION SETTINGS & CONFIG API
# ==========================================

@app.route('/api/config', methods=['GET'])
@login_required
def api_get_config():
    conn = get_db_connection()
    rows = conn.execute("SELECT key, value, description FROM system_config").fetchall()
    conn.close()
    return jsonify({r['key']: r['value'] for r in rows})

@app.route('/api/config', methods=['POST'])
@admin_required
def api_update_config():
    data = request.get_json() or {}
    for key, val in data.items():
        set_system_config(key, str(val))
    return jsonify({"success": True, "message": "Configuration updated successfully"})

# ==========================================
# CHARTS & ANALYTICS API
# ==========================================

@app.route('/api/charts/power_history', methods=['GET'])
@login_required
def api_power_history():
    """Returns power and energy consumption over recent timestamp intervals"""
    conn = get_db_connection()
    # Group by minute/time slices
    rows = conn.execute('''
        SELECT strftime('%H:%M', timestamp) as time_slot,
               AVG(power_w) as avg_power,
               SUM(power_w) as total_power,
               AVG(ambient_lux) as avg_lux
        FROM telemetry_history
        GROUP BY time_slot
        ORDER BY timestamp DESC
        LIMIT 20
    ''').fetchall()
    conn.close()

    result = [dict(r) for r in reversed(rows)]
    return jsonify(result)

# ==========================================
# REPORTS & EXPORTS
# ==========================================

@app.route('/api/reports/telemetry/csv', methods=['GET'])
@login_required
def api_download_telemetry_csv():
    pole_id = request.args.get('pole_id', 'all')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    source = request.args.get('source', 'all')

    csv_data = generate_telemetry_csv(pole_id, start_date, end_date, source)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=telemetry_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.route('/api/reports/alerts/csv', methods=['GET'])
@login_required
def api_download_alerts_csv():
    csv_data = generate_alerts_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=alerts_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.route('/api/reports/summary/pdf', methods=['GET'])
@login_required
def api_download_summary_pdf():
    pdf_bytes = generate_summary_pdf()
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename=streetlight_system_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
    )

_services_started = False

def start_services():
    """Initializes database and launches background services"""
    global _services_started

    if _services_started:
        return

    init_db()
    simulator_instance.start()
    mqtt_service_instance.start()

    _services_started = True

if __name__ == '__main__':
    start_services()
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
