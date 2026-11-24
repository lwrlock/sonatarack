import asyncio
from contextlib import asynccontextmanager
import socket
from pathlib import Path

import aiohttp
import pytest
import uvicorn


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@asynccontextmanager
async def live_sonatarack(tmp_path: Path):
    from sonatarack.app import create_app

    port = _free_port()
    app = create_app(db_path=tmp_path / "studio.db")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    srv.install_signal_handlers = lambda: None
    t = asyncio.create_task(srv.serve())
    while not srv.started:
        if t.done():
            t.result()
        await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.should_exit = True
        await t


def test_sonatarack_api_presets_euclidean_fft_and_wav_export(tmp_path: Path):
    async def go():
        async with live_sonatarack(tmp_path) as base:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{base}/api/studio/state") as r:
                    assert r.status == 200
                    st = await r.json()
                    assert len(st["patches"]) >= 4
                    assert len(st["patterns"]) >= 3

                async with sess.get(f"{base}/api/theory/euclidean?pulses=5&steps=16&rotation=2") as r:
                    eu = await r.json()
                    assert len(eu["steps"]) == 16
                    assert sum(eu["steps"]) == 5

                async with sess.post(
                    f"{base}/api/patches",
                    json={"id": "p-test", "name": "Warm Tape", "waveform": "triangle", "fm_index": 1.4, "cutoff_hz": 1800},
                ) as r:
                    assert r.status == 200

                async with sess.post(
                    f"{base}/api/dsp/preview",
                    json={"midi": 60, "patch": {"waveform": "saw", "fm_index": 0.5, "cutoff_hz": 2400}},
                ) as r:
                    prev = await r.json()
                    assert len(prev["waveform_points"]) >= 64
                    assert len(prev["spectrum"]) == 48

                async with sess.post(
                    f"{base}/api/render/wav",
                    json={"patch_id": "walnut-keys", "pattern_id": "neo-soul-groove", "bars": 1},
                ) as r:
                    assert r.status == 200
                    assert r.headers["Content-Type"] == "audio/wav"
                    assert r.headers.get("X-Content-Type-Options") == "nosniff"
                    assert r.headers.get("X-Frame-Options") == "DENY"
                    wav_data = await r.read()
                    assert wav_data[:4] == b"RIFF"

                # Reject unsafe IDs and oversized step arrays (DoS guard)
                async with sess.post(
                    f"{base}/api/patches",
                    json={"id": "../<script>", "name": "Bad", "waveform": "sine"},
                ) as r_bad_id:
                    assert r_bad_id.status == 422

                async with sess.post(
                    f"{base}/api/patterns",
                    json={"id": "pat-dos", "name": "DoS", "tracks": {"kick": [1] * 256}},
                ) as r_bad_steps:
                    assert r_bad_steps.status == 422

                # Integrated Room Acoustics Observatory endpoints
                async with sess.get(f"{base}/acoustics") as r_page:
                    assert r_page.status == 200
                async with sess.get(f"{base}/api/acoustics/materials") as r_mats:
                    assert r_mats.status == 200
                    assert len((await r_mats.json())["materials"]) >= 5
                async with sess.post(
                    f"{base}/api/acoustics/simulate",
                    json={"length": 7.4, "width": 5.3, "height": 3.1},
                ) as r_sim:
                    assert r_sim.status == 200
                    sim_data = await r_sim.json()
                    assert len(sim_data["rt60"]["bands"]) == 6
                    assert len(sim_data["raytrace"]["rays"]) == 44

    asyncio.run(go())
