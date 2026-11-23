/* PHOS Viewer — Run Detail page */

const API_BASE = ""; // Same origin

const state = {
    run: null,
    structure: null,
    timeline: [],
    telemetryIndex: null,
    observations: {}, // tag -> {timestamps: [], values: []}
    currentTimeIndex: 0,
    timestamps: [],
    isPlaying: false,
    playTimer: null,
    speed: 1,
    selectedTag: null,
};

const runTitleEl = document.getElementById("run-title");
const kindBadgeEl = document.getElementById("kind-badge");
const poolBadgeEl = document.getElementById("pool-badge");
const runIdEl = document.getElementById("run-id");
const runSummaryEl = document.getElementById("run-summary");
const plantDrawingEl = document.getElementById("plant-drawing");
const plantInfoEl = document.getElementById("plant-info");
const timeDisplayEl = document.getElementById("time-display");
const scrubberEl = document.getElementById("scrubber");
const playPauseBtn = document.getElementById("play-pause");
const stepBackBtn = document.getElementById("step-back");
const stepFwdBtn = document.getElementById("step-fwd");
const speedDisplayEl = document.getElementById("speed-display");
const speedSelectEl = document.getElementById("speed-select");
const traceChartsEl = document.getElementById("trace-charts");
const atlasLanesEl = document.getElementById("atlas-lanes");
const eventMarkersEl = document.getElementById("event-markers");
const evidenceDrawerEl = document.getElementById("evidence-drawer");
const evidenceDrawerHeaderEl = document.getElementById("evidence-title");
const evidenceContentEl = document.getElementById("evidence-content");
const closeDrawerBtn = document.getElementById("close-drawer");

async function init() {
    const runName = getRunNameFromUrl();
    if (!runName) {
        document.body.innerHTML = "<p>No run specified.</p>";
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/run/${runName}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        state.run = await response.json();
    } catch (err) {
        document.body.innerHTML = `<p>Error loading run: ${err.message}</p>`;
        return;
    }

    renderHeader();
    renderPlantDrawing();
    renderPlantInfo();
    renderTimeline();
    initPlayback();
    renderTraceCharts();
    renderAtlasLanes();
    renderPerformanceMetrics();
    renderEventMarkers();

    playPauseBtn.addEventListener("click", togglePlay);
    stepBackBtn.addEventListener("click", () => step(-1));
    stepFwdBtn.addEventListener("click", () => step(1));
    scrubberEl.addEventListener("input", onScrubberChange);
    speedSelectEl.addEventListener("change", (e) => {
        state.speed = parseFloat(e.target.value);
        speedDisplayEl.textContent = state.speed + "×";
    });
    closeDrawerBtn.addEventListener("click", () => {
        evidenceDrawerEl.style.display = "none";
    });
}

function getRunNameFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("run");
}

function renderHeader() {
    const h = state.run.header;
    runTitleEl.textContent = h.title || state.run.name;
    kindBadgeEl.textContent = h.kind;
    poolBadgeEl.textContent = h.pool;
    runIdEl.textContent = state.run.run_id.substring(0, 12) + "…";
    runSummaryEl.textContent = h.plain_language_summary || "No summary available.";
}

function getNodeColor(type) {
    const colors = {
        subsystem: "#4a90e2",
        plc: "#27ae60",
        scada: "#e67e22",
        hmi: "#9b59b6",
        engineering: "#e74c3c",
        sensor: "#f39c12",
        actuator: "#3498db",
        setpoint: "#95a5a6",
    };
    return colors[type] || "#7f8c8d";
}

function renderPlantDrawing() {
    const structure = state.run.header?.structure;
    if (!structure || !structure.nodes || structure.nodes.length === 0) {
        plantDrawingEl.innerHTML = "<p>No plant structure available.</p>";
        return;
    }

    const nodes = structure.nodes;
    const edges = structure.edges || [];

    // Deterministic layout: grid-based, subsystems on left, control network top-right,
    // signals grouped by physical unit below their subsystem.
    const nodeMap = new Map();
    nodes.forEach(n => nodeMap.set(n.id, n));

    // Position nodes deterministically by type
    const subsystemNodes = nodes.filter(n => n.type === "subsystem");
    const deviceNodes = nodes.filter(n => n.type === "plc" || n.type === "scada" || n.type === "hmi" || n.type === "engineering");
    const signalNodes = nodes.filter(n => n.type === "sensor" || n.type === "actuator" || n.type === "setpoint");

    const width = 800;
    const height = 400;
    const subsystemX = 80;
    const deviceX = 620;
    const signalStartX = 220;
    const signalYStart = 60;
    const signalYStep = 40;

    const positions = new Map();

    // Subsystems down the left side
    subsystemNodes.forEach((n, i) => {
        positions.set(n.id, { x: subsystemX, y: 60 + i * 70 });
    });

    // Control devices top-right
    deviceNodes.forEach((n, i) => {
        positions.set(n.id, { x: deviceX, y: 60 + i * 50 });
    });

    // Signals: group by physical unit (tags), place below their subsystem
    signalNodes.forEach((n, i) => {
        const unitTag = (n.tags && n.tags[0]) || "";
        const unitNode = [...subsystemNodes].find(sn => sn.tags && sn.tags.includes(unitTag));
        let baseY = 60;
        if (unitNode) {
            const unitPos = positions.get(unitNode.id);
            if (unitPos) baseY = unitPos.y + 40;
        }
        positions.set(n.id, { x: signalStartX + (i % 4) * 140, y: baseY + Math.floor(i / 4) * 50 });
    });

    // Clamp positions into viewBox
    for (const [id, pos] of positions) {
        pos.x = Math.min(Math.max(pos.x, 40), width - 40);
        pos.y = Math.min(Math.max(pos.y, 40), height - 40);
    }

    let html = `<div class="plant-svg-container"><svg class="plant-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">`;

    // Arrowhead marker
    html += '<defs><marker id="arrowhead" markerWidth="10" markerHeight="7" refX="0" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#999"/></marker></defs>';

    // Draw edges first (behind nodes)
    edges.forEach(edge => {
        const fromPos = positions.get(edge.from);
        const toPos = positions.get(edge.to);
        if (!fromPos || !toPos) return;
        const writable = edge.writable ? "stroke-dasharray:5,5;" : "";
        html += `<line x1="${fromPos.x}" y1="${fromPos.y}" x2="${toPos.x}" y2="${toPos.y}" stroke="#999" stroke-width="1.5" marker-end="url(#arrowhead)" style="${writable}"/>`;
    });

    // Draw nodes
    nodes.forEach(node => {
        const pos = positions.get(node.id);
        if (!pos) return;
        const color = getNodeColor(node.type);
        const tag = node.tags && node.tags[0] ? node.tags[0] : "";
        html += `
            <circle class="plant-node" cx="${pos.x}" cy="${pos.y}" r="14" fill="${color}" stroke="#333" stroke-width="1"
                    data-node-id="${escapeHtml(node.id)}" data-tag="${escapeHtml(tag)}" data-type="${escapeHtml(node.type)}"
                    title="${escapeHtml(node.label || node.id)}"/>
            <text x="${pos.x}" y="${pos.y + 22}" text-anchor="middle" font-size="10" fill="#333" pointer-events="none">${escapeHtml(node.label || node.id)}</text>
        `;
    });

    html += "</svg></div>";
    plantDrawingEl.innerHTML = html;

    // Add click handlers
    document.querySelectorAll(".plant-node").forEach(node => {
        node.addEventListener("click", () => {
            const tag = node.getAttribute("data-tag");
            const nodeId = node.getAttribute("data-node-id");
            const nodeType = node.getAttribute("data-type");
            // Highlight selected node
            document.querySelectorAll(".plant-node").forEach(n => n.classList.remove("selected"));
            node.classList.add("selected");
            if (tag && (nodeType === "sensor" || nodeType === "actuator" || nodeType === "setpoint")) {
                state.selectedTag = tag;
                showTrace(tag);
            }
            showNodeDetail(node);
        });
    });
}

function renderPlantInfo() {
    const plant = state.run.header?.plant;
    if (!plant) {
        plantInfoEl.innerHTML = "<p>No plant information available.</p>";
        return;
    }

    let html = "<h3>Plant Information</h3>";
    if (plant.label) html += `<p><strong>Name:</strong> ${escapeHtml(plant.label)}</p>`;
    if (plant.plant_id) html += `<p><strong>ID:</strong> ${escapeHtml(plant.plant_id)}</p>`;
    if (plant.industry) html += `<p><strong>Industry:</strong> ${escapeHtml(plant.industry)}</p>`;
    if (plant.summary) html += `<p><strong>Summary:</strong> ${escapeHtml(plant.summary)}</p>`;

    plantInfoEl.innerHTML = html;
}

function renderTimeline() {
    const timeline = state.run.header?.timeline || [];
    state.timeline = timeline;

    const listEl = document.getElementById("timeline-list");
    if (!timeline || timeline.length === 0) {
        listEl.innerHTML = "<p>No timeline events.</p>";
        return;
    }

    listEl.innerHTML = timeline.map(ev => {
        const isAttack = ev.kind === "attack";
        const cls = isAttack ? "timeline-event attack" : "timeline-event";
        const start = ev.start || "—";
        const end = ev.end || "—";
        return `
            <div class="${cls}">
                <div class="time">${escapeHtml(start)} → ${escapeHtml(end)}</div>
                <div class="label"><strong>${escapeHtml(ev.label || ev.kind)}:</strong> ${escapeHtml(ev.description || "")}</div>
                ${ev.affected_tags && ev.affected_tags.length > 0
                    ? `<div class="tags">Tags: ${ev.affected_tags.map(t => escapeHtml(t)).join(", ")}</div>`
                    : ""}
            </div>
        `;
    }).join("");

    renderEventMarkers();
}

function renderEventMarkers() {
    const timeline = state.timeline;
    if (!timeline || timeline.length === 0) {
        eventMarkersEl.innerHTML = '<p class="no-events">No events.</p>';
        return;
    }

    // Map event start times to scrubber positions
    const total = state.timestamps.length || 1;
    let html = "";
    timeline.forEach(ev => {
        const start = ev.start || "";
        const end = ev.end || "";
        if (!start) return;
        // Find approximate index by time
        const idx = timeToIndex(start);
        const pct = total > 1 ? (idx / (total - 1)) * 100 : 0;
        const color = ev.kind === "attack" ? "#e74c3c" : "#f39c12";
        html += `<div class="event-marker" style="left:${pct}%; background:${color}" title="${escapeHtml(ev.description || ev.kind)} @ ${start}"></div>`;
    });

    eventMarkersEl.innerHTML = html;
}

function timeToIndex(isoTime) {
    if (!state.timestamps || state.timestamps.length === 0) return 0;
    const t = new Date(isoTime).getTime();
    let best = 0;
    let bestDiff = Infinity;
    state.timestamps.forEach((ts, i) => {
        const d = Math.abs(new Date(ts).getTime() - t);
        if (d < bestDiff) {
            bestDiff = d;
            best = i;
        }
    });
    return best;
}

function initPlayback() {
    const idx = state.run.header?.timestamps;
    // The .phosrun doesn't store timestamps as a flat list; build from telemetry index
    const telemetryIndex = state.run.header?.telemetry_index;
    if (telemetryIndex && telemetryIndex.start_time) {
        const start = new Date(telemetryIndex.start_time).getTime();
        const period = telemetryIndex.sample_period || 30;
        const totalSamples = telemetryIndex.chunks.reduce((sum, c) => sum + c.samples, 0);
        state.timestamps = Array.from({ length: totalSamples }, (_, i) => {
            return new Date(start + i * period * 1000).toISOString();
        });
    } else {
        state.timestamps = [];
    }

    scrubberEl.max = state.timestamps.length - 1;
    scrubberEl.value = 0;
    state.currentTimeIndex = 0;
    updateTimeDisplay();

    scrubberEl.addEventListener("input", (e) => {
        state.currentTimeIndex = parseInt(e.target.value);
        updateTimeDisplay();
        updatePlayback(state.currentTimeIndex);
    });
}

function updateTimeDisplay() {
    const cur = state.currentTimeIndex;
    const total = state.timestamps.length - 1;
    timeDisplayEl.textContent = `${String(cur).padStart(4, "0")} / ${String(total).padStart(4, "0")}`;
}

function togglePlay() {
    state.isPlaying = !state.isPlaying;
    playPauseBtn.textContent = state.isPlaying ? "⏸ Pause" : "▶ Play";
    if (state.isPlaying) {
        playLoop();
    } else {
        if (state.playTimer) {
            clearTimeout(state.playTimer);
            state.playTimer = null;
        }
    }
}

function playLoop() {
    if (!state.isPlaying) return;
    step(1);
    state.playTimer = setTimeout(() => playLoop(), 1000 / state.speed);
}

function step(delta) {
    const max = state.timestamps.length - 1;
    state.currentTimeIndex = Math.max(0, Math.min(max, state.currentTimeIndex + delta));
    scrubberEl.value = state.currentTimeIndex;
    updateTimeDisplay();
    updatePlayback(state.currentTimeIndex);
}

function onScrubberChange() {
    state.currentTimeIndex = parseInt(scrubberEl.value);
    updateTimeDisplay();
    updatePlayback(state.currentTimeIndex);
}

function updatePlayback(timeIndex) {
    const isoTime = state.timestamps[timeIndex] || "";
    // Update plant drawing: highlight nodes affected by events at this time
    document.querySelectorAll(".plant-node").forEach(n => n.classList.remove("active"));

    const now = new Date(isoTime).getTime();
    const activeTags = new Set();
    (state.timeline || []).forEach(ev => {
        const start = ev.start ? new Date(ev.start).getTime() : Infinity;
        const end = ev.end ? new Date(ev.end).getTime() : Infinity;
        if (start <= now && now <= end) {
            (ev.affected_tags || []).forEach(t => activeTags.add(t));
        }
    });

    document.querySelectorAll(".plant-node").forEach(n => {
        const tag = n.getAttribute("data-tag");
        if (tag && activeTags.has(tag)) {
            n.classList.add("active");
        }
    });

    // Update trace chart playhead if visible
    if (state.selectedTag) {
        updateTracePlayhead(timeIndex);
    }
}

function renderTraceCharts() {
    traceChartsEl.innerHTML = "<p>Click a signal node in the plant drawing to view its trace.</p>";
}

function showTrace(tag) {
    traceChartsEl.innerHTML = `<h3>${escapeHtml(tag)}</h3><div class="trace-chart-container"><div class="trace-chart" id="trace-${escapeCssId(tag)}"></div></div>`;

    const runName = getRunNameFromUrl();
    if (!runName) return;

    const params = new URLSearchParams({
        tag: tag,
        start: state.timestamps[0] || "",
        end: state.timestamps[state.timestamps.length - 1] || "",
        max_points: 400,
    });

    fetch(`${API_BASE}/api/telemetry/${runName}?${params}`)
        .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
        .then(data => {
            renderTraceChart(tag, data.timestamps, data.values);
        })
        .catch(err => {
            console.error("Failed to load trace:", err);
            traceChartsEl.innerHTML = `<p>Error loading trace for ${escapeHtml(tag)}.</p>`;
        });
}

function escapeCssId(id) {
    return id.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function renderTraceChart(tag, timestamps, values) {
    const container = document.getElementById(`trace-${escapeCssId(tag)}`);
    if (!container) return;

    if (!values || values.length === 0) {
        container.innerHTML = "<p>No data available.</p>";
        return;
    }

    const width = container.clientWidth || 500;
    const height = 180;
    const margin = { top: 20, right: 30, bottom: 30, left: 50 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;

    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal || 1;

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);

    // Axis labels
    const labelX = document.createElementNS(svgNS, "text");
    labelX.setAttribute("x", margin.left + plotWidth / 2);
    labelX.setAttribute("y", height - 5);
    labelX.setAttribute("text-anchor", "middle");
    labelX.setAttribute("font-size", "10");
    labelX.setAttribute("fill", "#666");
    labelX.textContent = "Time →";
    svg.appendChild(labelX);

    const labelY = document.createElementNS(svgNS, "text");
    labelY.setAttribute("x", 12);
    labelY.setAttribute("y", margin.top + plotHeight / 2);
    labelY.setAttribute("text-anchor", "middle");
    labelY.setAttribute("transform", `rotate(-90 12,${margin.top + plotHeight / 2})`);
    labelY.setAttribute("font-size", "10");
    labelY.setAttribute("fill", "#666");
    labelY.textContent = tag;
    svg.appendChild(labelY);

    // Line
    const points = values.map((v, i) => {
        const x = margin.left + (i / (values.length - 1)) * plotWidth;
        const y = margin.top + plotHeight - ((v - minVal) / range) * plotHeight;
        return `${x},${y}`;
    }).join(" ");

    const polyline = document.createElementNS(svgNS, "polyline");
    polyline.setAttribute("points", points);
    polyline.setAttribute("fill", "none");
    polyline.setAttribute("stroke", "#2563eb");
    polyline.setAttribute("stroke-width", "1.5");
    svg.appendChild(polyline);

    // Playhead line (updated during playback)
    const playhead = document.createElementNS(svgNS, "line");
    playhead.setAttribute("id", `playhead-${escapeCssId(tag)}`);
    playhead.setAttribute("x1", margin.left);
    playhead.setAttribute("y1", margin.top);
    playhead.setAttribute("x2", margin.left);
    playhead.setAttribute("y2", margin.top + plotHeight);
    playhead.setAttribute("stroke", "#e74c3c");
    playhead.setAttribute("stroke-width", "2");
    playhead.setAttribute("opacity", "0.7");
    svg.appendChild(playhead);

    container.innerHTML = "";
    container.appendChild(svg);
}

function updateTracePlayhead(timeIndex) {
    if (!state.selectedTag) return;
    const playhead = document.getElementById(`playhead-${escapeCssId(state.selectedTag)}`);
    if (!playhead) return;
    const total = state.timestamps.length - 1;
    const pct = total > 0 ? timeIndex / total : 0;
    const svg = playhead.parentElement;
    if (!svg) return;
    const margin = 50;
    const plotWidth = svg.clientWidth - margin * 2;
    const x = margin + pct * plotWidth;
    playhead.setAttribute("x1", x);
    playhead.setAttribute("x2", x);
}

function renderAtlasLanes() {
    const atlas = state.run.atlas;
    if (!atlas) {
        atlasLanesEl.innerHTML = '<p class="no-atlas">Atlas has not been run on this corpus yet.</p>';
        return;
    }

    const detections = atlas.alerts || [];
    const hypotheses = atlas.hypotheses || [];
    const narratives = atlas.narratives || [];

    let html = '<div class="atlas-lanes-container">';

    // Truth lane (from timeline attacks)
    html += '<div class="lane"><div class="lane-label">Truth</div><div class="lane-events">';
    (state.timeline || []).forEach(ev => {
        if (ev.kind !== "attack") return;
        const pct = timeToIndexPct(ev.start);
        html += `<div class="truth-marker" style="left:${pct}%" title="${escapeHtml(ev.description || ev.kind)}"></div>`;
    });
    html += '</div></div>';

    // Alerts lane
    html += '<div class="lane"><div class="lane-label">Atlas Alerts</div><div class="lane-events">';
    detections.forEach(d => {
        const pct = timeToIndexPct(d.timestamp);
        const severity = d.score > 2.0 ? "high" : d.score > 1.0 ? "med" : "low";
        html += `<div class="alert-marker" style="left:${pct}%" title="${escapeHtml(d.feature || 'alert')} @ ${d.timestamp} (score ${d.score?.toFixed(2) ?? 'N/A'})" onclick="showAlertDetail('${escapeJs(d.id || '')}')">${severityMarker(severity)}</div>`;
    });
    html += '</div></div>';

    // Confidence lane
    html += '<div class="lane"><div class="lane-label">Atlas Confidence</div><div class="lane-events">';
    hypotheses.forEach(h => {
        html += `<div class="hyp-marker" title="${escapeHtml(h.template_id || 'hypothesis')} confidence ${h.confidence?.toFixed(2) ?? 'N/A'}"></div>`;
    });
    html += '</div></div>';

    // Narratives summary
    if (narratives.length > 0) {
        html += '<div class="lane"><div class="lane-label">Narratives</div><div class="lane-events">';
        narratives.forEach(n => {
            html += `<div class="narrative-marker" title="${escapeHtml(n.title || 'narrative')}">${n.confidence?.toFixed(2) ?? '?'}</div>`;
        });
        html += '</div></div>';
    }

    html += '</div>';
    atlasLanesEl.innerHTML = html;
}

function renderPerformanceMetrics() {
    const atlas = state.run.atlas;
    const timeline = state.timeline || [];
    const metricsEl = document.getElementById("performance-metrics");
    if (!metricsEl) return;

    const attacks = timeline.filter(e => e.kind === "attack");
    const detections = atlas ? atlas.alerts || [] : [];
    const hypotheses = atlas ? atlas.hypotheses || [] : [];
    const narratives = atlas ? atlas.narratives || [] : [];

    // Count detections during attack windows vs normal
    let truePositives = 0;
    let falsePositives = 0;
    detections.forEach(d => {
        const dTime = new Date(d.timestamp).getTime();
        const inAttack = attacks.some(atk => {
            const s = new Date(atk.start).getTime();
            const e = new Date(atk.end).getTime();
            return dTime >= s && dTime <= e;
        });
        if (inAttack) truePositives++;
        else falsePositives++;
    });

    const totalAttacks = attacks.length;
    const attacksWithDetection = attacks.filter(atk => {
        const s = new Date(atk.start).getTime();
        const e = new Date(atk.end).getTime();
        return detections.some(d => {
            const dTime = new Date(d.timestamp).getTime();
            return dTime >= s && dTime <= e;
        });
    }).length;

    const html = `
        <div class="perf-grid">
            <div class="perf-card">
                <div class="perf-value">${detections.length}</div>
                <div class="perf-label">Total Alerts</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${truePositives}</div>
                <div class="perf-label">In Attack Windows</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${falsePositives}</div>
                <div class="perf-label">Outside Attack Windows</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${totalAttacks}</div>
                <div class="perf-label">Labeled Attacks</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${attacksWithDetection}</div>
                <div class="perf-label">Attacks Detected</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${hypotheses.length}</div>
                <div class="perf-label">Hypotheses</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${narratives.length}</div>
                <div class="perf-label">Narratives</div>
            </div>
            <div class="perf-card">
                <div class="perf-value">${atlas ? atlas.detector?.name || "—" : "—"}</div>
                <div class="perf-label">Detector</div>
            </div>
        </div>
    `;
    metricsEl.innerHTML = html;
}

function timeToIndexPct(isoTime) {
    if (!state.timestamps || state.timestamps.length === 0) return 0;
    const idx = timeToIndex(isoTime);
    const total = state.timestamps.length - 1;
    return total > 0 ? (idx / total) * 100 : 0;
}

function severityMarker(sev) {
    const colors = { high: "#e74c3c", med: "#f39c12", low: "#2ecc71" };
    return `<span style="color:${colors[sev] || '#999'}">▲</span>`;
}

function showAlertDetail(alertId) {
    const atlas = state.run.atlas;
    if (!atlas) return;

    const alert = (atlas.alerts || []).find(a => a.id === alertId);
    if (!alert) return;

    evidenceDrawerHeaderEl.textContent = `Alert: ${escapeHtml(alert.feature || alert.id)}`;
    evidenceContentEl.innerHTML = `
        <p><strong>Time:</strong> ${escapeHtml(alert.timestamp)}</p>
        <p><strong>Score:</strong> ${alert.score != null ? alert.score.toFixed(3) : "N/A"}</p>
        <p><strong>Confidence:</strong> ${alert.confidence != null ? alert.confidence.toFixed(3) : "N/A"}</p>
        <p><strong>Feature:</strong> ${escapeHtml(alert.feature || "N/A")}</p>
        <p><strong>Entities:</strong> ${(alert.entity_ids || []).map(escapeHtml).join(", ") || "none"}</p>
    `;
    evidenceDrawerEl.style.display = "block";
}

function showNodeDetail(node) {
    const nodeId = node.getAttribute("data-node-id");
    const nodeType = node.getAttribute("data-type");
    const nodeTag = node.getAttribute("data-tag");

    evidenceDrawerHeaderEl.textContent = `Node: ${escapeHtml(node.getAttribute("title") || nodeId)}`;
    evidenceContentEl.innerHTML = `
        <p><strong>ID:</strong> ${escapeHtml(nodeId || "")}</p>
        <p><strong>Type:</strong> ${escapeHtml(nodeType || "")}</p>
        <p><strong>Tag:</strong> ${escapeHtml(nodeTag || "none")}</p>
    `;
    evidenceDrawerEl.style.display = "block";
}

function escapeHtml(text) {
    if (text == null) return "";
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
}

function escapeJs(text) {
    return String(text).replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\n/g, "\\n");
}

init();