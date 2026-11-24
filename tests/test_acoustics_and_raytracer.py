"""Tests for integrated SonataRack + EchoRoom acoustics physics: RT60, eigenmodes, pressure grid & 2D ray-tracer."""

import pytest

from sonatarack.acoustics import (
    compute_mode_pressure_grid,
    compute_room_modes,
    compute_rt60_spectrum,
    trace_room_rays,
)


def test_rt60_sabine_and_eyring_decrease_with_higher_absorption():
    dims = (6.4, 4.8, 3.0)
    hard_room = compute_rt60_spectrum(dims, walls="concrete_raw", ceiling="concrete_raw", floor="oak_parquet")
    treated_room = compute_rt60_spectrum(dims, walls="fiberglass_panel", ceiling="acoustic_foam", floor="heavy_velvet")

    assert len(hard_room["bands"]) == 6
    assert hard_room["eyring_mid_rt60"] > treated_room["eyring_mid_rt60"] * 2.5
    assert treated_room["schroeder_hz"] < hard_room["schroeder_hz"]


def test_room_eigenmodes_and_2d_pressure_grid():
    modes = compute_room_modes((6.0, 4.0, 3.0), max_freq_hz=180.0)
    assert len(modes) >= 5
    assert modes[0]["indices"] == [1, 0, 0]
    assert modes[0]["freq_hz"] == pytest.approx(28.58, abs=0.2)
    assert modes[0]["kind"] == "Axial"

    grid = compute_mode_pressure_grid(6.0, 4.0, p=2, q=1, nx=24, ny=16)
    assert len(grid) == 16
    assert len(grid[0]) == 24
    assert grid[0][0] == pytest.approx(1.0)


def test_2d_raytracer_captures_bounces_and_receiver_arrivals():
    sim = trace_room_rays(
        length=8.0,
        width=5.5,
        source=(2.0, 2.7),
        receiver=(6.2, 2.8),
        num_rays=36,
        max_bounces=4,
        wall_absorption=0.22,
    )
    assert len(sim["rays"]) == 36
    assert all(len(r["points"]) >= 2 for r in sim["rays"])
    assert sim["metrics"]["total_segments"] > 36
    assert len(sim["impulse_bins"]) == 24
