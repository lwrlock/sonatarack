import test from "node:test";
import assert from "node:assert/strict";

import {
  escapeHtml,
  midiToNoteLabel,
  euclideanClient,
  knobValueToAngle,
  clampParam,
  buildKeyboardNotes,
} from "../static/js/synth_utils.js";
import {
  pressureToAuroraRgba,
  rt60BandStatus,
  clampRoomCoord,
} from "../static/acoustics/js/echo_utils.js";

test("escapeHtml neutralizes XSS vectors", () => {
  assert.equal(escapeHtml(`<img src=x onerror="1">`), "&lt;img src=x onerror=&quot;1&quot;&gt;");
});

test("midiToNoteLabel maps MIDI integers cleanly", () => {
  assert.equal(midiToNoteLabel(60), "C4");
  assert.equal(midiToNoteLabel(69), "A4");
  assert.equal(midiToNoteLabel(57), "A3");
});

test("euclideanClient distributes pulses evenly", () => {
  assert.deepEqual(euclideanClient(3, 8), [1, 0, 0, 1, 0, 0, 1, 0]);
  assert.deepEqual(euclideanClient(0, 8), [0, 0, 0, 0, 0, 0, 0, 0]);
});

test("knobValueToAngle maps min..max across -135..+135 deg", () => {
  assert.equal(knobValueToAngle(0, 0, 100), -135);
  assert.equal(knobValueToAngle(50, 0, 100), 0);
  assert.equal(knobValueToAngle(100, 0, 100), 135);
  assert.equal(clampParam(999, 10, 500), 500);
});

test("buildKeyboardNotes creates 2 full octaves starting at C3 (48)", () => {
  const keys = buildKeyboardNotes(48, 25);
  assert.equal(keys.length, 25);
  assert.equal(keys[0].label, "C3");
  assert.equal(keys[1].isBlack, true);
  assert.equal(keys[24].label, "C5");
});

test("pressureToAuroraRgba & rt60BandStatus classify room acoustics cleanly", () => {
  assert.match(pressureToAuroraRgba(0.9), /^rgba\(52, 211, 153,/);
  assert.equal(rt60BandStatus(0.32), "DRY CONTROL");
  assert.equal(rt60BandStatus(1.45), "CONCERT HALL");
  assert.equal(clampRoomCoord(9.5, 8.0), 7.75);
});
