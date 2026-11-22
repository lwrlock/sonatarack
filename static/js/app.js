import { WebAudioStudio } from "./audio_engine.js";
import {
  buildKeyboardNotes,
  clampParam,
  escapeHtml,
  euclideanClient,
  knobValueToAngle,
  midiToNoteLabel,
} from "./synth_utils.js";

const audio = new WebAudioStudio();

const OSC_KNOBS = [
  { key: "fm_ratio", label: "FM Ratio", min: 0.5, max: 8.0, step: 0.25, unit: "x" },
  { key: "fm_index", label: "FM Index", min: 0.0, max: 6.0, step: 0.1, unit: "" },
  { key: "drive", label: "Tape Drive", min: 0.0, max: 3.0, step: 0.05, unit: "" },
  { key: "delay_mix", label: "Echo Mix", min: 0.0, max: 0.7, step: 0.02, unit: "" },
];

const ENV_KNOBS = [
  { key: "cutoff_hz", label: "Cutoff", min: 150, max: 8000, step: 50, unit: "Hz" },
  { key: "attack_ms", label: "Attack", min: 2, max: 600, step: 4, unit: "ms" },
  { key: "decay_ms", label: "Decay", min: 30, max: 1200, step: 15, unit: "ms" },
  { key: "sustain", label: "Sustain", min: 0.05, max: 1.0, step: 0.02, unit: "" },
];

const TRACK_DEFS = [
  { key: "kick", name: "KICK DRUM", melodic: false, defaultEuc: 4 },
  { key: "snare", name: "SNARE", melodic: false, defaultEuc: 2 },
  { key: "hat", name: "HI-HAT", melodic: false, defaultEuc: 9 },
  { key: "bass", name: "SUB BASS", melodic: true, defaultEuc: 5 },
  { key: "pad", name: "CHORD PAD", melodic: true, defaultEuc: 3 },
  { key: "arp", name: "ARP LEAD", melodic: true, defaultEuc: 7 },
];

const CHORD_PADS = [
  { id: "maj9", label: "Maj9 Lush", intervals: [0, 4, 7, 11, 14] },
  { id: "min11", label: "Min11 Neo", intervals: [0, 3, 7, 10, 14, 17] },
  { id: "dom7b9", label: "Dom7b9 Jazz", intervals: [0, 4, 7, 10, 13] },
  { id: "sus4", label: "Sus4 Dream", intervals: [0, 5, 7, 10] },
  { id: "triad_min", label: "Minor Triad", intervals: [0, 3, 7] },
  { id: "triad_maj", label: "Major Triad", intervals: [0, 4, 7] },
];

const KEY_TO_MIDI = {
  z: 48, s: 49, x: 50, d: 51, c: 52, v: 53, g: 54, b: 55, h: 56, n: 57, j: 58, m: 59,
  q: 60, "2": 61, w: 62, "3": 63, e: 64, r: 65, "5": 66, t: 67, "6": 68, y: 69, "7": 70, u: 71, i: 72,
};

const state = {
  patches: [],
  patterns: [],
  scales: [],
  currentPatch: null,
  currentPattern: null,
  playing: false,
  stepIdx: 0,
  stepTimer: null,
  previewWave: [],
  previewSpectrum: [],
  dragKnob: null,
  isDarkVinyl: false,
  eucCycle: {},
};

const $ = (id) => document.getElementById(id);

function showToast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove("show"), 2400);
}

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function renderKnobsGroup(containerId, specs) {
  const p = state.currentPatch;
  if (!p) return;
  $(containerId).innerHTML = specs
    .map((sp) => {
      const val = Number(p[sp.key] ?? sp.min);
      const ang = knobValueToAngle(val, sp.min, sp.max);
      const disp = sp.step < 1 ? val.toFixed(2) : Math.round(val);
      return `
        <div class="knob-cell" data-knob-key="${sp.key}" data-min="${sp.min}" data-max="${sp.max}" data-step="${sp.step}">
          <svg class="knob-svg" viewBox="0 0 60 60">
            <circle cx="30" cy="30" r="24" fill="#29201A" stroke="#786859" stroke-width="2"></circle>
            <circle cx="30" cy="30" r="18" fill="#3E3128"></circle>
            <g transform="rotate(${ang} 30 30)">
              <line x1="30" y1="30" x2="30" y2="11" stroke="#EA580C" stroke-width="3" stroke-linecap="round"></line>
            </g>
          </svg>
          <span class="knob-label">${escapeHtml(sp.label)}</span>
          <span class="knob-val mono">${disp}${sp.unit}</span>
        </div>
      `;
    })
    .join("");
}

function renderAdsrSvg() {
  const p = state.currentPatch;
  if (!p) return;
  const aX = Math.min(85, Math.max(10, (p.attack_ms / 600) * 85));
  const dX = aX + Math.min(95, Math.max(18, (p.decay_ms / 1200) * 95));
  const sY = 48 - clampParam(p.sustain, 0.05, 1) * 40;
  const d = `M 4 48 L ${aX} 8 L ${dX} ${sY} L 235 ${sY} L 276 48 Z`;
  $("adsr-path").setAttribute("d", d);
  $("adsr-readout").textContent = `LPF ${Math.round(p.cutoff_hz)}Hz`;
}

function renderWaveButtons() {
  if (!state.currentPatch) return;
  document.querySelectorAll(".wave-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.wave === state.currentPatch.waveform);
  });
  $("patch-cat-badge").textContent = String(state.currentPatch.category || "CUSTOM").toUpperCase();
}

function renderSequencer() {
  const pat = state.currentPattern;
  if (!pat) return;
  $("bpm-input").value = String(pat.bpm || 96);
  $("swing-slider").value = String(pat.swing || 0);
  $("swing-label").textContent = `${Math.round((pat.swing || 0) * 100)}%`;
  $("root-note-badge").textContent = `ROOT ${midiToNoteLabel(pat.root_midi || 57)}`;

  $("seq-grid").innerHTML = TRACK_DEFS.map((tr) => {
    const arr = pat.tracks?.[tr.key] || Array(16).fill(0);
    const cells = arr
      .map((val, step) => {
        const active = val > 0 ? "active" : "";
        const mel = tr.melodic ? "track-melodic" : "";
        const beat = step % 4 === 0 ? "beat-start" : "";
        const head = state.playing && step === state.stepIdx ? "playhead" : "";
        const txt = tr.melodic && val > 0 ? midiToNoteLabel(val) : val > 0 ? "●" : "";
        return `<button class="step-pad mono ${active} ${mel} ${beat} ${head}" data-track="${tr.key}" data-step="${step}">${escapeHtml(txt)}</button>`;
      })
      .join("");
    return `
      <div class="seq-row">
        <div class="track-meta">
          <span class="track-name mono">${tr.name}</span>
          <button class="euc-btn mono" data-euc-track="${tr.key}">E(k,16)</button>
        </div>
        ${cells}
      </div>
    `;
  }).join("");
}

function renderKeyboardAndChords() {
  const keys = buildKeyboardNotes(48, 25);
  $("piano-bed").innerHTML = keys
    .map((k) => {
      const cls = k.isBlack ? "key-black" : "key-white";
      const lbl = k.isBlack ? "" : escapeHtml(k.label);
      return `<div class="${cls} mono" data-midi="${k.midi}">${lbl}</div>`;
    })
    .join("");

  const root = state.currentPattern?.root_midi || 57;
  $("chords-grid").innerHTML = CHORD_PADS.map(
    (c) => `<button class="chord-pad mono" data-chord="${c.id}">${escapeHtml(c.label)}<br/><span style="font-size:10px;color:var(--ink-muted);">${midiToNoteLabel(root)}</span></button>`
  ).join("");
}

async function refreshDspPreview(midi = 60) {
  if (!state.currentPatch) return;
  try {
    const res = await apiJson("/api/dsp/preview", {
      method: "POST",
      body: JSON.stringify({ midi, patch: state.currentPatch }),
    });
    state.previewWave = res.waveform_points || [];
    state.previewSpectrum = (res.spectrum || []).map((b) => b.mag);
    $("oled-note-badge").textContent = `DSP ${res.note} READY`;
  } catch {}
}

function drawOledScope() {
  const canvas = $("oled-canvas");
  if (!canvas) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  const w = Math.max(260, Math.floor(rect.width - 16));
  const h = Math.max(120, Math.floor(rect.height - 16));
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  // Subtle oscilloscope grid
  ctx.strokeStyle = "rgba(255, 235, 200, 0.08)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, h * 0.5);
  ctx.lineTo(w, h * 0.5);
  ctx.stroke();

  // Bottom half: 48-band FFT bars (warm amber gold)
  const spec = audio.readLiveSpectrum(48) || state.previewSpectrum;
  if (spec && spec.length > 0) {
    const bw = w / spec.length;
    ctx.fillStyle = "rgba(251, 191, 36, 0.42)";
    spec.forEach((mag, i) => {
      const bh = Math.max(2, mag * (h * 0.52));
      ctx.fillRect(i * bw + 1, h - bh, Math.max(2, bw - 2), bh);
    });
  }

  // Waveform overlay (phosphor mint)
  const liveWave = audio.readLiveWaveform();
  const pts = liveWave ? Array.from(liveWave) : state.previewWave;
  if (pts && pts.length > 1) {
    ctx.strokeStyle = "#34D399";
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach((v, i) => {
      const x = (i / (pts.length - 1)) * w;
      const y = h * 0.44 - v * (h * 0.32);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  requestAnimationFrame(drawOledScope);
}

function triggerStepAudio(step) {
  const pat = state.currentPattern;
  const patch = state.currentPatch;
  if (!pat || !patch) return;
  const tr = pat.tracks || {};
  if (tr.kick?.[step]) audio.playKick();
  if (tr.snare?.[step]) audio.playSnare();
  if (tr.hat?.[step]) audio.playHat();
  if (tr.bass?.[step] > 0) {
    audio.playSynthNote(tr.bass[step], { ...patch, cutoff_hz: Math.min(patch.cutoff_hz, 1100) }, 0.22, 0.34);
  }
  if (tr.pad?.[step] > 0) {
    [0, 4, 7].forEach((iv) => audio.playSynthNote(tr.pad[step] + iv, patch, 0.52, 0.14));
  }
  if (tr.arp?.[step] > 0) {
    audio.playSynthNote(tr.arp[step], patch, 0.16, 0.2);
  }
}

function togglePlayback() {
  state.playing = !state.playing;
  const btn = $("play-btn");
  btn.classList.toggle("playing", state.playing);
  btn.textContent = state.playing ? "■ STOP LOOP" : "▶ PLAY LOOP";
  if (!state.playing) {
    clearTimeout(state.stepTimer);
    renderSequencer();
    return;
  }
  audio.ensureStarted();
  state.stepIdx = 0;
  const tick = () => {
    if (!state.playing) return;
    triggerStepAudio(state.stepIdx);
    renderSequencer();
    const bpm = Number(state.currentPattern?.bpm || 96);
    const baseMs = (60000 / bpm) / 4;
    const swing = Number(state.currentPattern?.swing || 0);
    const delay = state.stepIdx % 2 === 0 ? baseMs * (1 + swing) : baseMs * (1 - swing);
    state.stepIdx = (state.stepIdx + 1) % 16;
    state.stepTimer = setTimeout(tick, Math.max(40, delay));
  };
  tick();
}

function wireEvents() {
  $("play-btn").addEventListener("click", togglePlayback);

  $("theme-btn").addEventListener("click", () => {
    state.isDarkVinyl = !state.isDarkVinyl;
    document.documentElement.setAttribute("data-theme", state.isDarkVinyl ? "vinyl-dark" : "cream");
    $("theme-btn").textContent = state.isDarkVinyl ? "Walnut Cream" : "Vinyl Mode";
  });

  $("patch-select").addEventListener("change", (e) => {
    const found = state.patches.find((p) => p.id === e.target.value);
    if (found) {
      state.currentPatch = structuredClone(found);
      renderAllSynthControls();
      refreshDspPreview(60);
    }
  });

  $("pattern-select").addEventListener("change", (e) => {
    const found = state.patterns.find((p) => p.id === e.target.value);
    if (found) {
      state.currentPattern = structuredClone(found);
      $("scale-select").value = state.currentPattern.scale || "dorian";
      renderSequencer();
      renderKeyboardAndChords();
    }
  });

  $("bpm-input").addEventListener("change", (e) => {
    if (state.currentPattern) state.currentPattern.bpm = clampParam(e.target.value, 55, 210);
  });

  $("swing-slider").addEventListener("input", (e) => {
    if (state.currentPattern) {
      state.currentPattern.swing = Number(e.target.value);
      $("swing-label").textContent = `${Math.round(state.currentPattern.swing * 100)}%`;
    }
  });

  $("clear-seq-btn").addEventListener("click", () => {
    if (!state.currentPattern) return;
    Object.keys(state.currentPattern.tracks).forEach((k) => {
      state.currentPattern.tracks[k] = Array(16).fill(0);
    });
    renderSequencer();
  });

  $("save-patch-btn").addEventListener("click", async () => {
    if (!state.currentPatch) return;
    await apiJson("/api/patches", { method: "POST", body: JSON.stringify(state.currentPatch) });
    showToast(`Saved patch '${state.currentPatch.name}' to SQLite Vault`);
  });

  $("export-wav-btn").addEventListener("click", async () => {
    const res = await fetch("/api/render/wav", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch: state.currentPatch, pattern: state.currentPattern, bars: 2 }),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${state.currentPattern?.id || "sonatarack"}-loop.wav`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Rendered & downloaded 44.1kHz PCM .WAV loop!");
  });

  // Rotary knob drag
  document.body.addEventListener("mousedown", (e) => {
    const cell = e.target.closest(".knob-cell");
    if (cell && state.currentPatch) {
      state.dragKnob = {
        key: cell.dataset.knobKey,
        min: Number(cell.dataset.min),
        max: Number(cell.dataset.max),
        step: Number(cell.dataset.step),
        startY: e.clientY,
        origVal: Number(state.currentPatch[cell.dataset.knobKey]),
      };
      return;
    }

    const pianoKey = e.target.closest("[data-midi]");
    if (pianoKey) {
      const m = Number(pianoKey.dataset.midi);
      pianoKey.classList.add("lit");
      setTimeout(() => pianoKey.classList.remove("lit"), 180);
      $("active-note-label").textContent = `Playing ${midiToNoteLabel(m)} (MIDI ${m})`;
      audio.playSynthNote(m, state.currentPatch, 0.45, 0.35);
      refreshDspPreview(m);
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!state.dragKnob || !state.currentPatch) return;
    const d = state.dragKnob;
    const dy = d.startY - e.clientY;
    const span = d.max - d.min;
    const raw = d.origVal + (dy / 120) * span;
    const snapped = Math.round(raw / d.step) * d.step;
    state.currentPatch[d.key] = clampParam(Number(snapped.toFixed(3)), d.min, d.max);
    renderAllSynthControls();
  });

  window.addEventListener("mouseup", () => {
    if (state.dragKnob) {
      state.dragKnob = null;
      refreshDspPreview(60);
    }
  });

  window.addEventListener("keydown", (e) => {
    if (["INPUT", "SELECT"].includes(document.activeElement?.tagName) || e.repeat) return;
    if (e.code === "Space") {
      e.preventDefault();
      togglePlayback();
      return;
    }
    const midi = KEY_TO_MIDI[e.key.toLowerCase()];
    if (midi && state.currentPatch) {
      $("active-note-label").textContent = `Key ${midiToNoteLabel(midi)}`;
      audio.playSynthNote(midi, state.currentPatch, 0.4, 0.32);
      const keyEl = document.querySelector(`[data-midi="${midi}"]`);
      if (keyEl) {
        keyEl.classList.add("lit");
        setTimeout(() => keyEl.classList.remove("lit"), 160);
      }
    }
  });

  document.body.addEventListener("click", (e) => {
    const waveBtn = e.target.closest(".wave-btn");
    if (waveBtn && state.currentPatch) {
      state.currentPatch.waveform = waveBtn.dataset.wave;
      renderWaveButtons();
      refreshDspPreview(60);
      return;
    }

    const stepBtn = e.target.closest(".step-pad");
    if (stepBtn && state.currentPattern) {
      const tr = stepBtn.dataset.track;
      const idx = Number(stepBtn.dataset.step);
      const arr = state.currentPattern.tracks[tr];
      if (["kick", "snare", "hat"].includes(tr)) {
        arr[idx] = arr[idx] ? 0 : 1;
      } else {
        const root = state.currentPattern.root_midi || 57;
        const offset = tr === "bass" ? -12 : tr === "arp" ? 12 : 0;
        arr[idx] = arr[idx] > 0 ? 0 : root + offset + ((idx * 2) % 7);
      }
      renderSequencer();
      return;
    }

    const eucBtn = e.target.closest("[data-euc-track]");
    if (eucBtn && state.currentPattern) {
      const tr = eucBtn.dataset.eucTrack;
      const presets = [3, 5, 7, 4, 9];
      const nextIdx = ((state.eucCycle[tr] || 0) + 1) % presets.length;
      state.eucCycle[tr] = nextIdx;
      const k = presets[nextIdx];
      const bits = euclideanClient(k, 16);
      const root = state.currentPattern.root_midi || 57;
      state.currentPattern.tracks[tr] = bits.map((b, i) => {
        if (!b) return 0;
        if (["kick", "snare", "hat"].includes(tr)) return 1;
        return root + (tr === "bass" ? -12 : tr === "arp" ? 12 : 0) + [0, 3, 7, 10][i % 4];
      });
      renderSequencer();
      showToast(`Generated Euclidean E(${k}, 16) on ${tr.toUpperCase()}`);
      return;
    }

    const chordBtn = e.target.closest("[data-chord]");
    if (chordBtn && state.currentPatch) {
      const c = CHORD_PADS.find((x) => x.id === chordBtn.dataset.chord);
      const root = state.currentPattern?.root_midi || 57;
      if (c) {
        c.intervals.forEach((iv) => audio.playSynthNote(root + iv, state.currentPatch, 0.75, 0.16));
        $("active-note-label").textContent = `Chord: ${midiToNoteLabel(root)} ${c.label}`;
      }
    }
  });
}

function renderAllSynthControls() {
  renderKnobsGroup("knobs-osc", OSC_KNOBS);
  renderKnobsGroup("knobs-env", ENV_KNOBS);
  renderAdsrSvg();
  renderWaveButtons();
}

async function bootstrap() {
  const st = await apiJson("/api/studio/state");
  state.patches = st.patches || [];
  state.patterns = st.patterns || [];
  state.scales = st.scales || [];

  $("patch-select").innerHTML = state.patches.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
  $("pattern-select").innerHTML = state.patterns.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
  $("scale-select").innerHTML = state.scales.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s.toUpperCase())}</option>`).join("");

  state.currentPatch = structuredClone(state.patches[0]);
  state.currentPattern = structuredClone(state.patterns[0]);
  $("scale-select").value = state.currentPattern.scale || "dorian";

  renderAllSynthControls();
  renderSequencer();
  renderKeyboardAndChords();
  wireEvents();
  await refreshDspPreview(60);
  requestAnimationFrame(drawOledScope);
}

bootstrap();
