"""FastAPI server for SonataRack Studio: patches, Euclidean patterns, DSP preview & WAV export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .dsp import SynthPatch, compute_fft_spectrum, render_note, render_pattern_wav
from .storage import StudioStore
from .theory import CHORDS, SCALES, build_chord, euclidean_rhythm, midi_to_name, scale_notes


class PatchUpsertReq(SynthPatch):
    id: str = Field(min_length=1, max_length=64)
    category: str = "Custom"


class PatternUpsertReq(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    scale: str = "dorian"
    root_midi: int = Field(default=60, ge=24, le=96)
    bpm: int = Field(default=105, ge=50, le=220)
    swing: float = Field(default=0.12, ge=0.0, le=0.4)
    tracks: dict[str, list[int]]


class DspPreviewReq(BaseModel):
    midi: int = Field(default=60, ge=21, le=108)
    patch: SynthPatch = Field(default_factory=SynthPatch)


class WavRenderReq(BaseModel):
    patch_id: str | None = None
    pattern_id: str | None = None
    patch: SynthPatch | None = None
    pattern: dict[str, Any] | None = None
    bars: int = Field(default=2, ge=1, le=8)


def _static_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "static"


def create_app(*, db_path: Path | str | None = None) -> FastAPI:
    store = StudioStore(db_path=db_path)
    app = FastAPI(title="SonataRack", version="0.1.0")
    app.state.store = store

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

    return app
