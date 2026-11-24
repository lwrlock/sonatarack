"""FastAPI server for SonataRack Studio: patches, Euclidean patterns, DSP preview & WAV export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .acoustics import (
    MATERIALS,
    compute_mode_pressure_grid,
    compute_room_modes,
    compute_rt60_spectrum,
    trace_room_rays,
)
from .dsp import SynthPatch, compute_fft_spectrum, render_note, render_pattern_wav
from .storage import StudioStore
from .theory import CHORDS, SCALES, build_chord, euclidean_rhythm, midi_to_name, scale_notes


class PatchUpsertReq(SynthPatch):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    category: str = Field(default="Custom", max_length=32)


class PatternUpsertReq(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    scale: str = Field(default="dorian", max_length=32)
    root_midi: int = Field(default=60, ge=24, le=96)
    bpm: int = Field(default=105, ge=50, le=220)
    swing: float = Field(default=0.12, ge=0.0, le=0.4)
    tracks: dict[str, list[int]]

    @field_validator("tracks")
    @classmethod
    def validate_tracks(cls, v: dict[str, list[int]]) -> dict[str, list[int]]:
        if len(v) > 12:
            raise ValueError("Too many sequencer tracks (max 12)")
        for lane, steps in v.items():
            if len(lane) > 32 or len(steps) > 64:
                raise ValueError("Invalid track lane or step count exceeds 64")
            if any(not isinstance(s, int) or s < 0 or s > 127 for s in steps):
                raise ValueError("Step values must be integers in [0, 127]")
        return v


class DspPreviewReq(BaseModel):
    midi: int = Field(default=60, ge=21, le=108)
    patch: SynthPatch = Field(default_factory=SynthPatch)


class WavRenderReq(BaseModel):
    patch_id: str | None = None
    pattern_id: str | None = None
    patch: SynthPatch | None = None
    pattern: dict[str, Any] | None = None
    bars: int = Field(default=2, ge=1, le=8)


class AcousticsSimReq(BaseModel):
    length: float = Field(default=7.4, ge=2.5, le=20.0)
    width: float = Field(default=5.3, ge=2.0, le=16.0)
    height: float = Field(default=3.1, ge=2.0, le=8.0)
    walls: str = Field(default="oak_parquet", max_length=64)
    ceiling: str = Field(default="acoustic_foam", max_length=64)
    floor: str = Field(default="heavy_velvet", max_length=64)
    source_x: float = Field(default=1.6, ge=0.2)
    source_y: float = Field(default=2.65, ge=0.2)
    receiver_x: float = Field(default=5.6, ge=0.2)
    receiver_y: float = Field(default=2.65, ge=0.2)
    num_rays: int = Field(default=44, ge=12, le=96)
    max_bounces: int = Field(default=4, ge=1, le=7)
    mode_p: int = Field(default=2, ge=0, le=6)
    mode_q: int = Field(default=1, ge=0, le=6)


def _static_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "static"


def create_app(*, db_path: Path | str | None = None) -> FastAPI:
    store = StudioStore(db_path=db_path)
    app = FastAPI(title="SonataRack", version="0.1.0")
    app.state.store = store

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    sdir = _static_dir()
    if sdir.exists():
        app.mount("/static", StaticFiles(directory=str(sdir)), name="static")

    @app.get("/")
    async def index() -> Response:
        idx = sdir / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return JSONResponse({"service": "SonataRack", "status": "ok"})

    @app.get("/api/studio/state")
    async def studio_state() -> dict[str, Any]:
        return {
            "patches": store.list_patches(),
            "patterns": store.list_patterns(),
            "scales": sorted(SCALES.keys()),
            "chords": sorted(CHORDS.keys()),
        }

    @app.post("/api/patches")
    async def save_patch(req: PatchUpsertReq) -> dict[str, Any]:
        data = req.model_dump()
        store.save_patch(data)
        return {"ok": True, "patch": data}

    @app.post("/api/patterns")
    async def save_pattern(req: PatternUpsertReq) -> dict[str, Any]:
        data = req.model_dump()
        store.save_pattern(data)
        return {"ok": True, "pattern": data}

    @app.get("/api/theory/euclidean")
    async def api_euclidean(
        pulses: int = Query(default=5, ge=0, le=32),
        steps: int = Query(default=16, ge=1, le=32),
        rotation: int = Query(default=0, ge=0, le=31),
    ) -> dict[str, Any]:
        return {"pulses": pulses, "steps": euclidean_rhythm(pulses, steps, rotation=rotation)}

    @app.get("/api/theory/scale")
    async def api_scale(
        root: int = Query(default=60, ge=24, le=96),
        scale: str = Query(default="dorian"),
        chord: str = Query(default="maj9"),
    ) -> dict[str, Any]:
        try:
            notes = scale_notes(root, scale, octaves=2)
            chord_midis = build_chord(root, chord)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "root": root,
            "root_name": midi_to_name(root),
            "scale_notes": notes,
            "chord_notes": chord_midis,
            "chord_names": [midi_to_name(m) for m in chord_midis],
        }

    @app.post("/api/dsp/preview")
    async def dsp_preview(req: DspPreviewReq) -> dict[str, Any]:
        samples = render_note(midi=req.midi, duration_sec=0.25, patch=req.patch, sample_rate=44100)
        # Downsample first cycle window for smooth SVG/Canvas waveform plot
        step = max(1, len(samples[:1400]) // 140)
        wave_pts = [round(float(v), 4) for v in samples[:1400:step][:140]]
        spectrum = compute_fft_spectrum(samples, sample_rate=44100, num_bins=48)
        return {"waveform_points": wave_pts, "spectrum": spectrum, "note": midi_to_name(req.midi)}

    @app.post("/api/render/wav")
    async def render_wav(req: WavRenderReq) -> Response:
        patch_dict = req.patch.model_dump() if req.patch else (
            store.get_patch(req.patch_id) if req.patch_id else store.list_patches()[0]
        )
        pat_dict = req.pattern if req.pattern else (
            store.get_pattern(req.pattern_id) if req.pattern_id else store.list_patterns()[0]
        )
        if not patch_dict or not pat_dict:
            raise HTTPException(status_code=404, detail="Patch or pattern not found")
        patch = SynthPatch.model_validate(patch_dict)
        wav_bytes = render_pattern_wav(pat_dict, patch=patch, bars=req.bars, sample_rate=44100)
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": 'attachment; filename="sonatarack-loop.wav"'},
        )

    @app.get("/acoustics")
    async def acoustics_page() -> Response:
        page = sdir / "acoustics.html"
        if page.exists():
            return FileResponse(page)
        return JSONResponse({"service": "SonataRack Acoustics", "status": "ok"})

    @app.get("/api/acoustics/materials")
    @app.get("/api/materials")
    async def acoustics_materials() -> dict[str, Any]:
        return {
            "materials": [
                {"id": k, "label": v["label"], "alpha": v["alpha"]}
                for k, v in MATERIALS.items()
            ]
        }

    @app.post("/api/acoustics/simulate")
    @app.post("/api/simulate")
    async def acoustics_simulate(req: AcousticsSimReq) -> dict[str, Any]:
        dims = (req.length, req.width, req.height)
        rt60 = compute_rt60_spectrum(dims, walls=req.walls, ceiling=req.ceiling, floor=req.floor)
        modes = compute_room_modes(dims, max_freq_hz=230.0, limit=20)
        pressure_grid = compute_mode_pressure_grid(req.length, req.width, p=req.mode_p, q=req.mode_q, nx=36, ny=24)
        wall_alpha = MATERIALS.get(req.walls, MATERIALS["oak_parquet"])["alpha"][2]
        raytrace = trace_room_rays(
            length=req.length,
            width=req.width,
            source=(req.source_x, req.source_y),
            receiver=(req.receiver_x, req.receiver_y),
            num_rays=req.num_rays,
            max_bounces=req.max_bounces,
            wall_absorption=wall_alpha,
        )
        return {
            "dims": {"length": req.length, "width": req.width, "height": req.height},
            "rt60": rt60,
            "modes": modes,
            "pressure_grid": pressure_grid,
            "raytrace": raytrace,
        }

    return app
