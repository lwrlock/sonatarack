/**
 * Pure synth UI math: Euclidean rhythm, MIDI naming, rotary knob angle, keyboard layout, XSS escape.
 */

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const BLACK_PITCH_CLASSES = new Set([1, 3, 6, 8, 10]);

export function escapeHtml(val) {
  if (val === null || val === undefined) return "";
  return String(val).replace(/[&<>"']/g, (c) => ESC[c]);
}

export function midiToNoteLabel(midi) {
  const m = Math.round(Number(midi) || 60);
  const oct = Math.floor(m / 12) - 1;
  return `${NOTE_NAMES[((m % 12) + 12) % 12]}${oct}`;
}

export function clampParam(val, min, max) {
  return Math.max(min, Math.min(max, Number(val)));
}

export function knobValueToAngle(val, min, max) {
  const span = Math.max(1e-6, max - min);
  const norm = clampParam((val - min) / span, 0, 1);
  return Number((-135 + norm * 270).toFixed(2));
}

export function euclideanClient(pulses, steps = 16) {
  const n = Math.max(1, Math.floor(steps));
  const k = Math.max(0, Math.min(n, Math.floor(pulses)));
  if (k === 0) return Array(n).fill(0);
  if (k === n) return Array(n).fill(1);

  let groups = Array.from({ length: n }, (_, i) => [i < k ? 1 : 0]);
  let pivot = k;
  let rem = n - k;
  while (rem > 1) {
    const count = Math.min(pivot, rem);
    const merged = [];
    for (let i = 0; i < count; i++) merged.push([...groups[i], ...groups[pivot + i]]);
    const leftA = groups.slice(count, pivot);
    const leftB = groups.slice(pivot + count);
    groups = [...merged, ...leftA, ...leftB];
    pivot = count;
    rem = leftA.length + leftB.length;
    if (leftB.length === 0 && leftA.length <= 1) break;
  }
  return groups.flat();
}

export function buildKeyboardNotes(startMidi = 48, count = 25) {
  const keys = [];
  for (let i = 0; i < count; i++) {
    const midi = startMidi + i;
    keys.push({
      midi,
      label: midiToNoteLabel(midi),
      isBlack: BLACK_PITCH_CLASSES.has(midi % 12),
    });
  }
  return keys;
}
