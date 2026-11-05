import csv
import io
import datetime
from backend.database import get_db_connection
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_telemetry_csv(pole_id=None, start_date=None, end_date=None, source=None):
    """Generates CSV bytes of telemetry history"""
    conn = get_db_connection()
    query = "SELECT * FROM telemetry_history WHERE 1=1"
    params = []

    if pole_id and pole_id != 'all':
        query += " AND pole_id = ?"
        params.append(pole_id)
    if start_date:
        query += " AND timestamp >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query += " AND timestamp <= ?"
        params.append(f"{end_date} 23:59:59")
    if source and source != 'all':
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY timestamp DESC LIMIT 2000"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Record ID", "Pole ID", "Timestamp", "Ambient Lux", "LED State",
        "Brightness (%)", "Power (W)", "Current (A)", "Voltage (V)",
        "LoRa RSSI (dBm)", "Motion Detected", "Data Source"
    ])

    for r in rows:
        writer.writerow([
            r['id'], r['pole_id'], r['timestamp'], r['ambient_lux'],
            "ON" if r['led_state'] == 1 else "OFF",
            r['brightness'], r['power_w'], r['current_a'], r['voltage_v'],
            r['lora_rssi'], "YES" if r['motion_detected'] == 1 else "NO",
            r['source']
        ])

    output.seek(0)
    return output.getvalue().encode('utf-8')

def generate_alerts_csv():
    """Generates CSV bytes of alerts history"""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 1000").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Alert ID", "Pole ID", "Fault Type", "Severity", "Description",
        "Status", "Created At", "Acknowledged At", "Acknowledged By", "Resolved At"
    ])

    for r in rows:
        writer.writerow([
            r['alert_id'], r['pole_id'], r['fault_type'], r['severity'].upper(),
            r['description'], r['status'].upper(), r['created_at'],
            r['acknowledged_at'] or "N/A", r['acknowledged_by'] or "N/A",
            r['resolved_at'] or "N/A"
        ])

    output.seek(0)
    return output.getvalue().encode('utf-8')

def generate_summary_pdf():
    """Generates a professional PDF report using ReportLab"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#475569'),
        spaceAfter=14
    )
    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=12,
        spaceAfter=8
    )

    # Document Header
    now_str = datetime.datetime.now().strftime("%B %d, %Y - %H:%M:%S")
    elements.append(Paragraph("Smart Street Light Automation System", title_style))
    elements.append(Paragraph(f"Network Performance & Fault Diagnostic Report &bull; Generated: {now_str}", subtitle_style))
    elements.append(Spacer(1, 10))

    # Fetch System Metrics
    conn = get_db_connection()
    nodes = conn.execute("SELECT * FROM nodes").fetchall()
    alerts = conn.execute("SELECT * FROM alerts WHERE status = 'active'").fetchall()
    gw = conn.execute("SELECT * FROM gateway_status WHERE gateway_id = 'GW-LORA-CENTRAL-01'").fetchone()
    conn.close()

    total_nodes = len(nodes)
    working_nodes = sum(1 for n in nodes if n['status'] == 'working')
    failed_nodes = sum(1 for n in nodes if n['status'] == 'failed')
    offline_nodes = sum(1 for n in nodes if n['status'] == 'offline')
    warning_nodes = sum(1 for n in nodes if n['status'] == 'warning')
    total_power = sum(n['power_w'] for n in nodes)
    active_alerts_count = len(alerts)

    # Executive Summary Table
    summary_data = [
        ["Metric", "Value", "Metric", "Value"],
        ["Total Streetlight Nodes", str(total_nodes), "Working Streetlights", f"{working_nodes} ({round(working_nodes/max(1, total_nodes)*100)}%)"],
        ["Failed / Defective Lights", str(failed_nodes), "Offline / Unresponsive", str(offline_nodes)],
        ["Total Grid Power Draw", f"{total_power:.1f} W ({total_power/1000.0:.2f} kW)", "Active System Alerts", str(active_alerts_count)],
        ["LoRa Gateway Status", f"ONLINE ({gw['gateway_id'] if gw else 'GW-01'})", "Active Data Source", gw['active_source'].upper() if gw else "SYNTHETIC"]
    ]

    t_summary = Table(summary_data, colWidths=[150, 120, 150, 120])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_summary)
    elements.append(Spacer(1, 14))

    # Streetlight Nodes Status Breakdown Table
    elements.append(Paragraph("Streetlight Nodes Real-Time Telemetry", h2_style))
    node_table_data = [
        ["Pole ID", "Status", "LED State", "Brightness", "Lux", "Power (W)", "Voltage", "LoRa RSSI"]
    ]
    for n in nodes:
        node_table_data.append([
            n['pole_id'],
            n['status'].upper(),
            "ON" if n['led_state'] == 1 else "OFF",
            f"{n['brightness']}%",
            f"{n['ambient_lux']:.1f}",
            f"{n['power_w']:.1f}",
            f"{n['voltage_v']:.1f}V",
            f"{n['lora_rssi']} dBm"
        ])

    t_nodes = Table(node_table_data, colWidths=[70, 65, 60, 65, 60, 70, 70, 80])
    t_nodes.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F1F5F9')]),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_nodes)
    elements.append(Spacer(1, 14))

    # Active Alerts Table
    elements.append(Paragraph(f"Active System Alerts ({len(alerts)} pending)", h2_style))
    if alerts:
        alert_data = [["Alert ID", "Pole", "Severity", "Fault Type", "Description", "Triggered At"]]
        for a in alerts[:8]: # Up to 8 in summary PDF
            alert_data.append([
                a['alert_id'],
                a['pole_id'],
                a['severity'].upper(),
                a['fault_type'],
                Paragraph(a['description'], ParagraphStyle('AlertDesc', fontName='Helvetica', fontSize=7.5)),
                a['created_at']
            ])
        t_alerts = Table(alert_data, colWidths=[65, 55, 55, 85, 180, 100])
        t_alerts.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#991B1B')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('FONTSIZE', (0, 1), (-1, -1), 7.5),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_alerts)
    else:
        elements.append(Paragraph("<i>No active alerts in the system. All streetlights and gateways operating normally.</i>", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
