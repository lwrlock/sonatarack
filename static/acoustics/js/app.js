import {
  clampRoomCoord,
  escapeHtml,
  pressureToAuroraRgba,
  rt60BandStatus,
} from "./echo_utils.js";

const state = {
  modeP: 2,
  modeQ: 1,
  srcX: 1.6,
  srcY: 2.65,
  recX: 5.6,
  recY: 2.65,
  lastSim: null,
};

async function apiJson(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

function renderRayAndModeCanvas(sim) {
  const canvas = document.getElementById("ray-canvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  ctx.fillStyle = "#040c17";
  ctx.fillRect(0, 0, w, h);

  const L = sim.dims.length;
  const W = sim.dims.width;
  const pad = 26;
  const scale = Math.min((w - pad * 2) / L, (h - pad * 2) / W);
  const boxW = L * scale;
  const boxH = W * scale;
  const ox = (w - boxW) / 2;
  const oy = (h - boxH) / 2;

  // Standing wave contour pressure cells
  const grid = sim.pressure_grid;
  const ny = grid.length;
  const nx = grid[0].length;
  const cw = boxW / nx;
  const ch = boxH / ny;
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      ctx.fillStyle = pressureToAuroraRgba(grid[r][c]);
      ctx.fillRect(ox + c * cw, oy + r * ch, cw + 0.6, ch + 0.6);
    }
  }

  // Room boundary perimeter
  ctx.strokeStyle = "rgba(56, 189, 248, 0.7)";
  ctx.lineWidth = 2;
  ctx.strokeRect(ox, oy, boxW, boxH);

  // Specular Rays
  sim.raytrace.rays.forEach((ray) => {
    ctx.beginPath();
    ray.points.forEach((pt, idx) => {
      const px = ox + pt[0] * scale;
      const py = oy + pt[1] * scale;
      if (idx === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    if (ray.hit_receiver) {
      ctx.strokeStyle = "rgba(52, 211, 153, 0.72)";
      ctx.lineWidth = 1.6;
    } else {
      ctx.strokeStyle = "rgba(56, 189, 248, 0.16)";
      ctx.lineWidth = 0.9;
    }
    ctx.stroke();
  });

  // Draw Source (Speaker) & Listener (Sweet Spot)
  const sx = ox + state.srcX * scale;
  const sy = oy + state.srcY * scale;
  const rx = ox + state.recX * scale;
  const ry = oy + state.recY * scale;

  ctx.fillStyle = "#a78bfa";
  ctx.beginPath();
  ctx.arc(sx, sy, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.font = "bold 11px monospace";
  ctx.fillText("SRC", sx + 11, sy + 4);

  ctx.strokeStyle = "#34d399";
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  ctx.arc(rx, ry, 10, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "#34d399";
  ctx.fillText("LISTENER", rx + 13, ry + 4);

  canvas.dataset.ox = String(ox);
  canvas.dataset.oy = String(oy);
  canvas.dataset.scale = String(scale);
}

function renderRt60Canvas(bands) {
  const canvas = document.getElementById("rt60-canvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#040c17";
  ctx.fillRect(0, 0, w, h);

  const maxSec = Math.max(1.2, ...bands.map((b) => Math.max(b.sabine_sec, b.eyring_sec)));
  const groupW = (w - 44) / bands.length;
  bands.forEach((b, i) => {
    const gx = 26 + i * groupW;
    const hSab = (b.sabine_sec / maxSec) * (h - 42);
    const hEyr = (b.eyring_sec / maxSec) * (h - 42);
    ctx.fillStyle = "#38bdf8";
    ctx.fillRect(gx, h - 22 - hSab, groupW * 0.34, hSab);
    ctx.fillStyle = "#34d399";
    ctx.fillRect(gx + groupW * 0.38, h - 22 - hEyr, groupW * 0.34, hEyr);
    ctx.fillStyle = "#8ea9c4";
    ctx.font = "10px monospace";
    ctx.fillText(b.hz >= 1000 ? `${b.hz / 1000}k` : `${b.hz}`, gx + 4, h - 6);
  });
  ctx.fillStyle = "#38bdf8";
  ctx.font = "10px monospace";
  ctx.fillText("■ Sabine", 16, 14);
  ctx.fillStyle = "#34d399";
  ctx.fillText("■ Eyring", 78, 14);
}

function renderRirCanvas(bins) {
  const canvas = document.getElementById("rir-canvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#040c17";
  ctx.fillRect(0, 0, w, h);

  const bw = (w - 32) / bins.length;
  bins.forEach((b, i) => {
    const bh = b.energy * (h - 36);
    const x = 16 + i * bw;
    ctx.fillStyle = b.ms <= 80 ? "#34d399" : "#a78bfa";
    ctx.fillRect(x + 1, h - 20 - bh, Math.max(2, bw - 3), Math.max(2, bh));
  });
  ctx.fillStyle = "#8ea9c4";
  ctx.font = "10px monospace";
  ctx.fillText("0 ms", 14, h - 5);
  ctx.fillText("80 ms", w * 0.48, h - 5);
  ctx.fillText("160 ms", w - 48, h - 5);
}

async function runSimulation() {
  const L = Number(document.getElementById("in-len").value);
  const W = Number(document.getElementById("in-wid").value);
  const H = Number(document.getElementById("in-hei").value);
  state.srcX = clampRoomCoord(state.srcX, L);
  state.srcY = clampRoomCoord(state.srcY, W);
  state.recX = clampRoomCoord(state.recX, L);
  state.recY = clampRoomCoord(state.recY, W);

  document.getElementById("val-len").textContent = `${L.toFixed(1)}m`;
  document.getElementById("val-wid").textContent = `${W.toFixed(1)}m`;
  document.getElementById("val-hei").textContent = `${H.toFixed(1)}m`;
  document.getElementById("val-rays").textContent = document.getElementById("in-rays").value;
  document.getElementById("val-bounces").textContent = document.getElementById("in-bounces").value;

  const sim = await apiJson("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      length: L,
      width: W,
      height: H,
      walls: document.getElementById("sel-walls").value,
      ceiling: document.getElementById("sel-ceil").value,
      floor: document.getElementById("sel-floor").value,
      source_x: state.srcX,
      source_y: state.srcY,
      receiver_x: state.recX,
      receiver_y: state.recY,
      num_rays: Number(document.getElementById("in-rays").value),
      max_bounces: Number(document.getElementById("in-bounces").value),
      mode_p: state.modeP,
      mode_q: state.modeQ,
    }),
  });
  state.lastSim = sim;

  document.getElementById("kpi-vol").textContent = `${sim.rt60.volume_m3} m³`;
  document.getElementById("kpi-rt60").textContent = `${sim.rt60.eyring_mid_rt60.toFixed(2)} s`;
  document.getElementById("kpi-schroeder").textContent = `${sim.rt60.schroeder_hz} Hz`;
  document.getElementById("kpi-c80").textContent = `${sim.raytrace.metrics.clarity_c80_db} dB`;
  document.getElementById("kpi-bolt").textContent = sim.rt60.bolt_optimal ? "OPTIMAL" : "SKEWED";
  document.getElementById("ratio-label").textContent = sim.rt60.ratio_str;
  document.getElementById("rt60-status-badge").textContent = rt60BandStatus(sim.rt60.eyring_mid_rt60);
  document.getElementById("active-mode-label").textContent = `Mode (${state.modeP},${state.modeQ})`;
  document.getElementById("ray-hit-badge").textContent = `${sim.raytrace.metrics.receiver_hits} Sweet-Spot Hits · ${sim.raytrace.metrics.total_segments} Segs`;

  const tbody = document.getElementById("modes-tbody");
  tbody.innerHTML = sim.modes
    .slice(0, 12)
    .map((m) => {
      const [mp, mq] = m.indices;
      const active = mp === state.modeP && mq === state.modeQ;
      return `
        <tr class="mode-row ${active ? "active" : ""}" data-pq="${mp},${mq}">
          <td><b>${escapeHtml(m.label)}</b></td>
          <td><span class="badge-kind">${escapeHtml(m.kind)}</span></td>
          <td style="color:var(--aurora-mint)">${m.freq_hz.toFixed(1)} Hz</td>
          <td>${m.freq_hz < sim.rt60.schroeder_hz ? "Modal" : "Diffuse"}</td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll("[data-pq]").forEach((tr) => {
    tr.addEventListener("click", () => {
      const [p, q] = tr.dataset.pq.split(",").map(Number);
      state.modeP = p;
      state.modeQ = q;
      runSimulation();
    });
  });

  renderRayAndModeCanvas(sim);
  renderRt60Canvas(sim.rt60.bands);
  renderRirCanvas(sim.raytrace.impulse_bins);
}

function applyPreset(name) {
  if (name === "mastering") {
    document.getElementById("in-len").value = 7.4;
    document.getElementById("in-wid").value = 5.3;
    document.getElementById("in-hei").value = 3.1;
    document.getElementById("sel-walls").value = "oak_parquet";
    document.getElementById("sel-ceil").value = "fiberglass_panel";
    document.getElementById("sel-floor").value = "heavy_velvet";
  } else if (name === "concert") {
    document.getElementById("in-len").value = 14.8;
    document.getElementById("in-wid").value = 9.6;
    document.getElementById("in-hei").value = 5.4;
    document.getElementById("sel-walls").value = "diffuser_qrd";
    document.getElementById("sel-ceil").value = "oak_parquet";
    document.getElementById("sel-floor").value = "oak_parquet";
  } else {
    document.getElementById("in-len").value = 3.6;
    document.getElementById("in-wid").value = 2.8;
    document.getElementById("in-hei").value = 2.5;
    document.getElementById("sel-walls").value = "acoustic_foam";
    document.getElementById("sel-ceil").value = "fiberglass_panel";
    document.getElementById("sel-floor").value = "heavy_velvet";
  }
  runSimulation();
}

async function boot() {
  const mats = await apiJson("/api/materials");
  const opts = mats.materials.map((m) => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.label)}</option>`).join("");
  document.getElementById("sel-walls").innerHTML = opts;
  document.getElementById("sel-ceil").innerHTML = opts;
  document.getElementById("sel-floor").innerHTML = opts;
  document.getElementById("sel-walls").value = "oak_parquet";
  document.getElementById("sel-ceil").value = "acoustic_foam";
  document.getElementById("sel-floor").value = "heavy_velvet";

  ["in-len", "in-wid", "in-hei", "in-rays", "in-bounces", "sel-walls", "sel-ceil", "sel-floor"].forEach((id) => {
    document.getElementById(id).addEventListener("input", runSimulation);
  });

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyPreset(btn.dataset.preset));
  });

  document.getElementById("ray-canvas").addEventListener("click", (e) => {
    const c = e.currentTarget;
    const rect = c.getBoundingClientRect();
    const ox = Number(c.dataset.ox || 26);
    const oy = Number(c.dataset.oy || 26);
    const scale = Number(c.dataset.scale || 50);
    const xCanvas = ((e.clientX - rect.left) / rect.width) * c.width;
    const yCanvas = ((e.clientY - rect.top) / rect.height) * c.height;
    const rx = (xCanvas - ox) / scale;
    const ry = (yCanvas - oy) / scale;
    if (document.getElementById("sel-place-mode").value === "source") {
      state.srcX = rx;
      state.srcY = ry;
    } else {
      state.recX = rx;
      state.recY = ry;
    }
    runSimulation();
  });

  await runSimulation();
}

boot();
