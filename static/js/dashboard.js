let currentStatusFilter = 'all';
let allNodesCache = [];
let powerChartInstance = null;
let statusChartInstance = null;
let activeInspectPole = null;

// ==========================================
// DATA SOURCE TOGGLE
// ==========================================
async function switchDataSource(source) {
  if (USER_ROLE !== 'admin') {
    alert("Administrative privileges required to switch Gateway Data Source.");
    return;
  }

  try {
    const res = await fetch('/api/datasource/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: source })
    });
    const data = await res.json();
    if (res.ok) {
      CURRENT_DATA_SOURCE = source;
      updateSourceToggleUI(source);
      fetchStatus();
      fetchNodes();
    } else {
      alert(data.error || "Failed to switch data source");
    }
  } catch (err) {
    console.error("Error toggling data source:", err);
  }
}

function updateSourceToggleUI(source) {
  const btnSyn = document.getElementById('btnSourceSynthetic');
  const btnHw = document.getElementById('btnSourceHardware');
  if (source === 'synthetic') {
    btnSyn.className = 'source-btn active-synthetic';
    btnHw.className = 'source-btn';
    document.getElementById('gwActiveSource').innerText = 'SYNTHETIC SIMULATION';
  } else {
    btnHw.className = 'source-btn active-hardware';
    btnSyn.className = 'source-btn';
    document.getElementById('gwActiveSource').innerText = 'ESP32 HARDWARE (LoRa)';
  }
}

// ==========================================
// SYSTEM SUMMARY & GATEWAY STATUS
// ==========================================
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();

    // 6 Summary Metrics
    document.getElementById('metricTotalNodes').innerText = data.total_nodes;
    document.getElementById('metricWorkingLights').innerText = data.working_lights;
    document.getElementById('metricFailedLights').innerText = data.failed_lights;
    document.getElementById('metricOfflineNodes').innerText = data.offline_nodes;
    document.getElementById('metricTotalPower').innerText = `${data.total_power_w} W`;
    document.getElementById('metricPowerKw').innerText = `${(data.total_power_w / 1000.0).toFixed(2)} kW current grid draw`;
    document.getElementById('metricActiveAlerts').innerText = data.active_alerts;
    document.getElementById('navAlertBadge').innerText = data.active_alerts;

    // Gateway Info
    if (data.gateway) {
      document.getElementById('gwId').innerText = data.gateway.id;
      document.getElementById('gwPackets').innerText = Number(data.gateway.packets_received).toLocaleString();
      document.getElementById('gwLastSeen').innerText = data.gateway.last_seen || 'Just now';

      const connPill = document.getElementById('gwConnStatus');
      const pulseDot = document.getElementById('gwPulseDot');
      if (data.gateway.status === 'online') {
        connPill.className = 'status-pill working';
        connPill.innerText = 'ONLINE';
        pulseDot.className = 'pulse-dot online';
      } else {
        connPill.className = 'status-pill critical';
        connPill.innerText = 'OFFLINE';
        pulseDot.className = 'pulse-dot offline';
      }

      const mqttStatusElem = document.getElementById('gwMqttStatus');
      if (data.gateway.mqtt_status === 'connected') {
        mqttStatusElem.innerText = 'CONNECTED';
        mqttStatusElem.style.color = 'var(--status-working)';
      } else {
        mqttStatusElem.innerText = 'DISCONNECTED';
        mqttStatusElem.style.color = 'var(--status-critical)';
      }
    }

    if (data.active_source) {
      updateSourceToggleUI(data.active_source);
    }

    // Update Status Breakdown Chart
    updateStatusChart(data.working_lights, data.failed_lights, data.offline_nodes);
  } catch (err) {
    console.error("Error fetching system status:", err);
  }
}

// ==========================================
// STREETLIGHT NODES MONITORING TABLE
// ==========================================
async function fetchNodes() {
  try {
    const res = await fetch('/api/nodes');
    if (!res.ok) return;
    const nodes = await res.json();
    allNodesCache = nodes;
    renderNodesTable();

    // If modal is currently open inspecting a pole, update its live view
    if (activeInspectPole) {
      const activeNode = nodes.find(n => n.pole_id === activeInspectPole);
      if (activeNode) {
        updateModalLiveReadings(activeNode);
      }
    }
  } catch (err) {
    console.error("Error fetching streetlight nodes:", err);
  }
}

function filterNodes(filterType, btn) {
  if (btn) {
    document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
  }
  currentStatusFilter = filterType;
  renderNodesTable();
}

function renderNodesTable() {
  const tbody = document.getElementById('nodesTableBody');
  if (!allNodesCache || allNodesCache.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:var(--text-dim);">No streetlight nodes registered.</td></tr>`;
    return;
  }

  let filtered = allNodesCache;
  if (currentStatusFilter !== 'all') {
    filtered = allNodesCache.filter(n => n.status === currentStatusFilter);
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:var(--text-dim);">No streetlights matching "${currentStatusFilter}" filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(node => {
    // LED State badge
    const ledOn = node.led_state === 1;
    const ledBadge = ledOn 
      ? `<span class="status-pill working" style="background:rgba(245, 158, 11, 0.2); color:#fbbf24; border-color:#f59e0b;">&#128161; ON</span>`
      : `<span class="status-pill offline">&#9675; OFF</span>`;

    // RSSI signal calculation
    const rssi = node.lora_rssi || -80;
    let signalBars = '&#128246;';
    let rssiColor = 'var(--status-working)';
    if (rssi < -110) {
      rssiColor = 'var(--status-critical)';
    } else if (rssi < -95) {
      rssiColor = 'var(--status-warning)';
    }

    // Health Status Pill
    let healthClass = 'working';
    if (node.status === 'failed') healthClass = 'critical';
    else if (node.status === 'warning') healthClass = 'warning';
    else if (node.status === 'offline') healthClass = 'offline';

    // Actions
    let actionButtons = `
      <button class="btn btn-sm" onclick="inspectNode('${node.pole_id}')">&#128269; Inspect</button>
    `;

    if (USER_ROLE === 'admin') {
      const nextToggleState = ledOn ? 0 : 1;
      const toggleLabel = ledOn ? 'Turn OFF' : 'Turn ON';
      actionButtons += `
        <button class="btn btn-sm" onclick="quickToggleLight('${node.pole_id}', ${nextToggleState})">${toggleLabel}</button>
      `;
    }

    return `
      <tr>
        <td style="font-family:var(--font-mono); font-weight:700; color:var(--accent-cyan);">
          ${node.pole_id}
          <div style="font-size:0.7rem; color:var(--text-dim); font-weight:normal;">${node.location_name || ''}</div>
        </td>
        <td>${ledBadge}</td>
        <td>
          <div class="progress-container">
            <div class="progress-bar" style="width: ${node.brightness}%;"></div>
          </div>
          <span style="font-family:var(--font-mono); font-size:0.75rem;">${node.brightness}%</span>
        </td>
        <td style="font-family:var(--font-mono);">${node.ambient_lux ? node.ambient_lux.toFixed(1) : 0} Lux</td>
        <td style="font-family:var(--font-mono); font-weight:600;">${node.power_w ? node.power_w.toFixed(1) : 0} W</td>
        <td style="font-family:var(--font-mono); color:${rssiColor};">
          ${signalBars} ${rssi} dBm
        </td>
        <td>
          <span class="status-pill ${node.mode === 'auto' ? 'working' : 'warning'}" style="font-size:0.65rem;">
            ${node.mode.toUpperCase()}
          </span>
        </td>
        <td style="font-size:0.75rem; color:var(--text-muted);">${node.last_seen || 'N/A'}</td>
        <td>
          <span class="status-pill ${healthClass}">
            ${node.status.toUpperCase()}
          </span>
          ${node.failure_type ? `<div style="font-size:0.65rem; color:var(--status-critical); margin-top:2px;">${node.failure_type}</div>` : ''}
        </td>
        <td style="text-align:right; white-space:nowrap;">
          ${actionButtons}
        </td>
      </tr>
    `;
  }).join('');
}

// ==========================================
// QUICK CONTROL & MODAL INSPECTION
// ==========================================
async function quickToggleLight(poleId, targetState) {
  try {
    const res = await fetch(`/api/nodes/${poleId}/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'manual',
        led_state: targetState,
        brightness: targetState === 1 ? 80 : 0
      })
    });
    if (res.ok) {
      fetchNodes();
      fetchStatus();
    }
  } catch (e) {
    console.error(e);
  }
}

async function inspectNode(poleId) {
  activeInspectPole = poleId;
  const modal = document.getElementById('detailModal');
  const title = document.getElementById('modalPoleTitle');
  const body = document.getElementById('modalDetailBody');

  title.innerHTML = `<span>&#128161;</span> Pole Inspection: <span style="color:var(--accent-cyan); font-family:var(--font-mono);">${poleId}</span>`;
  body.innerHTML = '<div style="text-align:center; padding:2rem; color:var(--text-dim);">Loading pole diagnostic telemetry...</div>';
  modal.style.display = 'flex';

  try {
    const res = await fetch(`/api/nodes/${poleId}`);
    if (!res.ok) throw new Error("Pole not found");
    const data = await res.json();
    renderModalContent(data);
  } catch (err) {
    body.innerHTML = `<div style="color:var(--status-critical); text-align:center;">${err.message}</div>`;
  }
}

function renderModalContent(data) {
  const node = data.node;
  const body = document.getElementById('modalDetailBody');

  let adminControls = '';
  if (USER_ROLE === 'admin') {
    adminControls = `
      <div style="background:#0b111e; border:1px solid var(--border-color); border-radius:6px; padding:1rem; margin-top:1rem;">
        <h4 style="font-size:0.85rem; font-weight:700; margin-bottom:0.75rem; color:var(--accent-cyan);">
          &#9881; Manual Streetlight Override (Downlink via LoRa Gateway)
        </h4>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:0.75rem;">
          <div>
            <label class="form-label">Control Mode</label>
            <select id="modalCtrlMode" class="form-select">
              <option value="auto" ${node.mode === 'auto' ? 'selected' : ''}>Autonomous (LDR + Motion)</option>
              <option value="manual" ${node.mode === 'manual' ? 'selected' : ''}>Manual Override</option>
            </select>
          </div>
          <div>
            <label class="form-label">LED Power State</label>
            <select id="modalCtrlState" class="form-select">
              <option value="1" ${node.led_state === 1 ? 'selected' : ''}>Lamp ON</option>
              <option value="0" ${node.led_state === 0 ? 'selected' : ''}>Lamp OFF</option>
            </select>
          </div>
        </div>
        <div style="margin-bottom:0.75rem;">
          <div style="display:flex; justify-content:space-between; margin-bottom:0.25rem;">
            <label class="form-label">LED Brightness (%)</label>
            <span id="modalValBrightness" style="font-family:var(--font-mono); font-size:0.8rem; color:var(--accent-cyan);">${node.brightness}%</span>
          </div>
          <input type="range" id="modalCtrlBrightness" min="0" max="100" step="5" value="${node.brightness}" class="form-input" style="padding:0; accent-color:var(--accent-cyan);" oninput="document.getElementById('modalValBrightness').innerText = this.value + '%'">
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <button class="btn btn-primary btn-sm" onclick="sendModalControl('${node.pole_id}')">
            &#128225; Transmit LoRa Downlink
          </button>
          <button class="btn btn-danger btn-sm" onclick="deleteNode('${node.pole_id}')">
            &#128465; Delete Pole
          </button>
        </div>
      </div>
    `;
  }

  body.innerHTML = `
    <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:0.75rem; margin-bottom:1rem;">
      <div style="background:#0b111e; padding:0.6rem; border-radius:6px; border:1px solid var(--border-subtle);">
        <div style="font-size:0.7rem; color:var(--text-dim);">Line Voltage</div>
        <div style="font-size:1.15rem; font-weight:700; font-family:var(--font-mono); color:var(--text-main);" id="liveVolt">${node.voltage_v ? node.voltage_v.toFixed(1) : 230} V</div>
      </div>
      <div style="background:#0b111e; padding:0.6rem; border-radius:6px; border:1px solid var(--border-subtle);">
        <div style="font-size:0.7rem; color:var(--text-dim);">Current Draw</div>
        <div style="font-size:1.15rem; font-weight:700; font-family:var(--font-mono); color:var(--text-main);" id="liveCurr">${node.current_a ? node.current_a.toFixed(3) : 0} A</div>
      </div>
      <div style="background:#0b111e; padding:0.6rem; border-radius:6px; border:1px solid var(--border-subtle);">
        <div style="font-size:0.7rem; color:var(--text-dim);">Active Power</div>
        <div style="font-size:1.15rem; font-weight:700; font-family:var(--font-mono); color:var(--accent-cyan);" id="livePwr">${node.power_w ? node.power_w.toFixed(1) : 0} W</div>
      </div>
      <div style="background:#0b111e; padding:0.6rem; border-radius:6px; border:1px solid var(--border-subtle);">
        <div style="font-size:0.7rem; color:var(--text-dim);">Ambient Light</div>
        <div style="font-size:1.15rem; font-weight:700; font-family:var(--font-mono); color:var(--status-warning);" id="liveLux">${node.ambient_lux ? node.ambient_lux.toFixed(1) : 0} Lux</div>
      </div>
      <div style="background:#0b111e; padding:0.6rem; border-radius:6px; border:1px solid var(--border-subtle);">
        <div style="font-size:0.7rem; color:var(--text-dim);">LoRa Link Quality</div>
        <div style="font-size:1.15rem; font-weight:700; font-family:var(--font-mono); color:var(--status-working);" id="liveRssi">${node.lora_rssi} dBm</div>
      </div>
      <div style="background:#0b111e; padding:0.6rem; border-radius:6px; border:1px solid var(--border-subtle);">
        <div style="font-size:0.7rem; color:var(--text-dim);">PIR Motion Sensor</div>
        <div style="font-size:1.15rem; font-weight:700; font-family:var(--font-mono);" id="liveMotion">${node.motion_detected === 1 ? '<span style="color:var(--status-working);">&#128102; DETECTED</span>' : '<span style="color:var(--text-dim);">CLEAR</span>'}</div>
      </div>
    </div>

    <!-- Active Alerts for Pole -->
    ${data.alerts && data.alerts.length > 0 ? `
      <div style="background:rgba(239, 68, 68, 0.15); border:1px solid rgba(239, 68, 68, 0.4); border-radius:6px; padding:0.75rem; margin-top:0.75rem;">
        <div style="font-weight:700; font-size:0.8rem; color:var(--status-critical); margin-bottom:4px;">&#9888; Active Fault Diagnosed on this Streetlight:</div>
        ${data.alerts.map(a => `<div style="font-size:0.75rem; color:var(--text-main);">&bull; [${a.fault_type}] ${a.description}</div>`).join('')}
      </div>
    ` : ''}

    ${adminControls}
  `;
}

function updateModalLiveReadings(node) {
  const v = document.getElementById('liveVolt');
  const c = document.getElementById('liveCurr');
  const p = document.getElementById('livePwr');
  const l = document.getElementById('liveLux');
  const r = document.getElementById('liveRssi');
  const m = document.getElementById('liveMotion');

  if (v) v.innerText = `${node.voltage_v ? node.voltage_v.toFixed(1) : 230} V`;
  if (c) c.innerText = `${node.current_a ? node.current_a.toFixed(3) : 0} A`;
  if (p) p.innerText = `${node.power_w ? node.power_w.toFixed(1) : 0} W`;
  if (l) l.innerText = `${node.ambient_lux ? node.ambient_lux.toFixed(1) : 0} Lux`;
  if (r) r.innerText = `${node.lora_rssi} dBm`;
  if (m) m.innerHTML = node.motion_detected === 1 ? '<span style="color:var(--status-working);">&#128102; DETECTED</span>' : '<span style="color:var(--text-dim);">CLEAR</span>';
}

async function sendModalControl(poleId) {
  const mode = document.getElementById('modalCtrlMode').value;
  const state = parseInt(document.getElementById('modalCtrlState').value);
  const brightness = parseInt(document.getElementById('modalCtrlBrightness').value);

  try {
    const res = await fetch(`/api/nodes/${poleId}/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: mode, led_state: state, brightness: brightness })
    });
    if (res.ok) {
      alert(`LoRa Downlink packet sent to ${poleId}!`);
      fetchNodes();
      fetchStatus();
    }
  } catch (e) {
    console.error(e);
  }
}

async function deleteNode(poleId) {
  if (!confirm(`Are you sure you want to decommission and remove streetlight ${poleId}?`)) return;
  try {
    const res = await fetch(`/api/nodes/${poleId}`, { method: 'DELETE' });
    if (res.ok) {
      closeModal('detailModal');
      fetchNodes();
      fetchStatus();
    }
  } catch (e) {
    console.error(e);
  }
}

function closeModal(modalId) {
  document.getElementById(modalId).style.display = 'none';
  if (modalId === 'detailModal') {
    activeInspectPole = null;
  }
}

// Add Node Modal
function openAddNodeModal() {
  document.getElementById('addNodeModal').style.display = 'flex';
}

async function submitAddNode(e) {
  e.preventDefault();
  const poleId = document.getElementById('addPoleId').value;
  const loc = document.getElementById('addLocationName').value;
  const lat = document.getElementById('addLat').value;
  const lon = document.getElementById('addLon').value;

  try {
    const res = await fetch('/api/nodes/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pole_id: poleId, location_name: loc, latitude: lat, longitude: lon })
    });
    const data = await res.json();
    if (res.ok) {
      closeModal('addNodeModal');
      fetchNodes();
      fetchStatus();
    } else {
      alert(data.error || 'Failed to add node');
    }
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// CHARTS (CHART.JS)
// ==========================================
function initCharts() {
  // Power Trend Line Chart
  const ctxPower = document.getElementById('powerChart').getContext('2d');
  powerChartInstance = new Chart(ctxPower, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Grid Power (Watts)',
        data: [],
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56, 189, 248, 0.15)',
        fill: true,
        tension: 0.35,
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: '#38bdf8'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: "'JetBrains Mono', monospace", size: 10 } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: "'JetBrains Mono', monospace", size: 10 } },
          suggestedMin: 0
        }
      }
    }
  });

  // Streetlight Health Doughnut Chart
  const ctxStatus = document.getElementById('statusChart').getContext('2d');
  statusChartInstance = new Chart(ctxStatus, {
    type: 'doughnut',
    data: {
      labels: ['Working', 'Failed', 'Offline'],
      datasets: [{
        data: [1, 0, 0],
        backgroundColor: ['#10b981', '#ef4444', '#64748b'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { size: 11 } }
        }
      },
      cutout: '70%'
    }
  });
}

async function fetchPowerChartData() {
  try {
    const res = await fetch('/api/charts/power_history');
    if (!res.ok) return;
    const history = await res.json();

    if (powerChartInstance && history.length > 0) {
      powerChartInstance.data.labels = history.map(h => h.time_slot);
      powerChartInstance.data.datasets[0].data = history.map(h => Math.round(h.total_power));
      powerChartInstance.update('none');
    }
  } catch (err) {
    console.error(err);
  }
}

function updateStatusChart(working, failed, offline) {
  if (statusChartInstance) {
    statusChartInstance.data.datasets[0].data = [working, failed, offline];
    statusChartInstance.update();
  }
}

// ==========================================
// INITIALIZATION & REAL-TIME POLLING
// ==========================================
window.addEventListener('DOMContentLoaded', () => {
  initCharts();
  fetchStatus();
  fetchNodes();
  fetchPowerChartData();

  // Fast real-time polling every 2.5 seconds (snappy IoT feel)
  setInterval(() => {
    fetchStatus();
    fetchNodes();
  }, 2500);

  // Poll power chart history every 8 seconds
  setInterval(fetchPowerChartData, 8000);
});
