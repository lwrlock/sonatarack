/** Pure color, acoustic classification, and coordinate clamp helpers for EchoRoom. */

export function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function pressureToAuroraRgba(val) {
  const v = Math.max(-1, Math.min(1, Number(val) || 0));
  const alpha = (0.14 + Math.abs(v) * 0.42).toFixed(2);
  if (v >= 0) {
    return `rgba(52, 211, 153, ${alpha})`;
  }
  return `rgba(167, 139, 250, ${alpha})`;
}

export function rt60BandStatus(sec) {
  const t = Number(sec) || 0;
  if (t <= 0.4) return "DRY CONTROL";
  if (t <= 0.85) return "WARM STUDIO";
  return "CONCERT HALL";
}

export function clampRoomCoord(val, maxSpan) {
  const v = Number(val) || 0;
  const lim = Math.max(0.5, Number(maxSpan) || 2.0);
  return Math.max(0.25, Math.min(lim - 0.25, Number(v.toFixed(2))));
}
