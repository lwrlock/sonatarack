"""Architectural Acoustics Engine: Sabine/Eyring RT60, Eigenmodes, Standing-Wave Fields & 2D Ray Tracer."""

from __future__ import annotations

import math
from typing import Any
import numpy as np

OCTAVE_BANDS = [125, 250, 500, 1000, 2000, 4000]
SPEED_OF_SOUND = 343.0

MATERIALS: dict[str, dict[str, Any]] = {
    "concrete_raw": {
        "label": "Poured Raw Concrete",
        "alpha": [0.01, 0.01, 0.02, 0.02, 0.02, 0.03],
    },
    "oak_parquet": {
        "label": "Oak Hardwood / Plaster",
        "alpha": [0.14, 0.11, 0.08, 0.07, 0.06, 0.06],
    },
    "glass_curtain": {
        "label": "Acoustic Double Glazing",
        "alpha": [0.18, 0.06, 0.04, 0.03, 0.02, 0.02],
    },
    "heavy_velvet": {
        "label": "Plush Carpet & Heavy Drape",
        "alpha": [0.12, 0.30, 0.52, 0.65, 0.72, 0.75],
    },
    "acoustic_foam": {
        "label": "Studio Wedge Absorption",
        "alpha": [0.15, 0.38, 0.68, 0.85, 0.90, 0.88],
    },
    "fiberglass_panel": {
        "label": "Broadband Fiberglass Cloud (10cm)",
        "alpha": [0.42, 0.78, 0.94, 0.96, 0.95, 0.91],
    },
    "diffuser_qrd": {
        "label": "QRD Skyline Timber Diffuser",
        "alpha": [0.10, 0.18, 0.22, 0.24, 0.21, 0.19],
    },
}


def compute_rt60_spectrum(
    dims: tuple[float, float, float],
    *,
    walls: str = "oak_parquet",
    ceiling: str = "acoustic_foam",
    floor: str = "heavy_velvet",
) -> dict[str, Any]:
    """Compute multi-band Sabine & Eyring RT60 decay times, Schroeder frequency & Bolt compliance."""
    L, W, H = (max(1.5, float(x)) for x in dims)
    vol = L * W * H
    wall_area = 2.0 * (L * H + W * H)
    ceil_area = L * W
    floor_area = L * W
    total_area = wall_area + ceil_area + floor_area

    mw = MATERIALS.get(walls, MATERIALS["oak_parquet"])["alpha"]
    mc = MATERIALS.get(ceiling, MATERIALS["acoustic_foam"])["alpha"]
    mf = MATERIALS.get(floor, MATERIALS["heavy_velvet"])["alpha"]

    bands: list[dict[str, Any]] = []
    for idx, hz in enumerate(OCTAVE_BANDS):
        alpha_bar = (wall_area * mw[idx] + ceil_area * mc[idx] + floor_area * mf[idx]) / total_area
        alpha_bar = max(0.005, min(0.99, alpha_bar))
        sabine = (0.161 * vol) / (total_area * alpha_bar)
        eyring = (0.161 * vol) / (-total_area * math.log(1.0 - alpha_bar))
        bands.append(
            {
                "hz": hz,
                "alpha_avg": round(alpha_bar, 3),
                "sabine_sec": round(min(9.99, sabine), 3),
                "eyring_sec": round(min(9.99, eyring), 3),
            }
        )

    eyring_mid = round((bands[2]["eyring_sec"] + bands[3]["eyring_sec"]) / 2.0, 3)
    schroeder_hz = round(2000.0 * math.sqrt(eyring_mid / max(1.0, vol)), 1)

    # Classic Sepmeyer / Bolt proportion sanity
    ratios = sorted([L / H, W / H, 1.0])
    l_ratio = L / H
    w_ratio = W / H
    bolt_ok = (1.1 <= w_ratio <= 1.9) and (1.35 <= l_ratio <= 2.6) and (abs(l_ratio - w_ratio) >= 0.15)

    return {
        "volume_m3": round(vol, 2),
        "surface_m2": round(total_area, 2),
        "mean_absorption": round(sum(b["alpha_avg"] for b in bands) / len(bands), 3),
        "eyring_mid_rt60": eyring_mid,
        "schroeder_hz": schroeder_hz,
        "bolt_optimal": bolt_ok,
        "ratio_str": f"{L/H:.2f} : {W/H:.2f} : 1.00",
        "bands": bands,
    }


def compute_room_modes(dims: tuple[float, float, float], max_freq_hz: float = 220.0, limit: int = 24) -> list[dict[str, Any]]:
    """Calculate Axial, Tangential, and Oblique room eigenfrequencies sorted cleanly ascending."""
    L, W, H = (max(1.5, float(x)) for x in dims)
    modes: list[dict[str, Any]] = []
    max_n = 7
    for p in range(max_n):
        for q in range(max_n):
            for r in range(max_n):
                if p == 0 and q == 0 and r == 0:
                    continue
                freq = 0.5 * SPEED_OF_SOUND * math.sqrt((p / L) ** 2 + (q / W) ** 2 + (r / H) ** 2)
                if freq > max_freq_hz:
                    continue
                nonzero = int(p > 0) + int(q > 0) + int(r > 0)
                kind = {1: "Axial", 2: "Tangential", 3: "Oblique"}[nonzero]
                modes.append({"indices": [p, q, r], "label": f"({p},{q},{r})", "freq_hz": round(freq, 2), "kind": kind})

    modes.sort(key=lambda m: (m["freq_hz"], m["kind"]))
    return modes[:limit]


def compute_mode_pressure_grid(length: float, width: float, *, p: int = 2, q: int = 1, nx: int = 36, ny: int = 24) -> list[list[float]]:
    """Evaluate 2D standing-wave normalized acoustic pressure cos(p*pi*x/L)*cos(q*pi*y/W)."""
    xs = np.linspace(0.0, length, nx)
    ys = np.linspace(0.0, width, ny)
    xx, yy = np.meshgrid(xs, ys)
    field = np.cos(p * np.pi * xx / max(0.5, length)) * np.cos(q * np.pi * yy / max(0.5, width))
    return [[round(float(val), 4) for val in row] for row in field]


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        return (math.hypot(px - ax, py - ay), 0.0)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / denom))
    cx = ax + t * abx
    cy = ay + t * aby
    return (math.hypot(px - cx, py - cy), t)


def trace_room_rays(
    *,
    length: float,
    width: float,
    source: tuple[float, float],
    receiver: tuple[float, float],
    num_rays: int = 48,
    max_bounces: int = 4,
    wall_absorption: float = 0.25,
) -> dict[str, Any]:
    """Cast 2D specular acoustic rays, reflect across box boundaries, and bin impulse arrivals at listener."""
    sx = max(0.2, min(length - 0.2, float(source[0])))
    sy = max(0.2, min(width - 0.2, float(source[1])))
    rx = max(0.2, min(length - 0.2, float(receiver[0])))
    ry = max(0.2, min(width - 0.2, float(receiver[1])))
    absorb = max(0.02, min(0.95, float(wall_absorption)))
    refl_gain = math.sqrt(1.0 - absorb)

    rays_out: list[dict[str, Any]] = []
    arrivals_ms: list[tuple[float, float]] = []
    hit_radius = 0.42
    total_segments = 0

    for idx in range(num_rays):
        theta = (2.0 * math.pi * idx) / max(1, num_rays) + 0.07
        dx, dy = math.cos(theta), math.sin(theta)
        cx, cy = sx, sy
        pts = [[round(cx, 3), round(cy, 3)]]
        energy = 1.0
        dist_acc = 0.0
        hit_receiver = False

        for _ in range(max_bounces):
            # Intersect next boundary x=0, x=L, y=0, y=W
            candidates: list[tuple[float, str]] = []
            if dx > 1e-9:
                candidates.append(((length - cx) / dx, "x"))
            elif dx < -1e-9:
                candidates.append(((0.0 - cx) / dx, "x"))
            if dy > 1e-9:
                candidates.append(((width - cy) / dy, "y"))
            elif dy < -1e-9:
                candidates.append(((0.0 - cy) / dy, "y"))

            valid = [(t, ax) for t, ax in candidates if t > 1e-6]
            if not valid:
                break
            t_hit, axis = min(valid, key=lambda item: item[0])
            nx_pt = cx + t_hit * dx
            ny_pt = cy + t_hit * dy

            # Check if ray passes near receiver ear sphere along this segment
            seg_dist, frac = _dist_point_to_segment(rx, ry, cx, cy, nx_pt, ny_pt)
            if seg_dist <= hit_radius:
                hit_receiver = True
                travel_m = dist_acc + frac * t_hit
                arrivals_ms.append((travel_m / SPEED_OF_SOUND * 1000.0, energy))

            pts.append([round(nx_pt, 3), round(ny_pt, 3)])
            total_segments += 1
            dist_acc += t_hit
            cx, cy = nx_pt, ny_pt
            if axis == "x":
                dx = -dx
            else:
                dy = -dy
            energy *= refl_gain

        rays_out.append({"points": pts, "energy": round(energy, 3), "hit_receiver": hit_receiver})

    # Bin arrivals across 0..160ms into 24 Room Impulse Response bars
    num_bins = 24
    bin_ms = 160.0 / num_bins
    bins = [0.0] * num_bins
    early_e = 0.0
    late_e = 1e-6
    for ms, e in arrivals_ms:
        b = min(num_bins - 1, max(0, int(ms / bin_ms)))
        bins[b] += e
        if ms <= 80.0:
            early_e += e
        else:
            late_e += e

    max_bin = max(1e-6, max(bins))
    norm_bins = [{"ms": round((i + 0.5) * bin_ms, 1), "energy": round(v / max_bin, 4)} for i, v in enumerate(bins)]
    c80_db = round(10.0 * math.log10(max(1e-6, early_e) / late_e), 2)

    return {
        "rays": rays_out,
        "impulse_bins": norm_bins,
        "metrics": {
            "total_segments": total_segments,
            "receiver_hits": sum(1 for r in rays_out if r["hit_receiver"]),
            "clarity_c80_db": c80_db,
        },
    }
