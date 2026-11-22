"""NumPy DSP synthesis engine: FM/subtractive synth, drums, SVF filter, FFT, and PCM WAV export."""

from __future__ import annotations

import io
import math
from typing import Any
import wave

import numpy as np
from pydantic import BaseModel, Field

from .theory import midi_to_hz


class SynthPatch(BaseModel):
    name: str = "Walnut Keys"
    waveform: str = "saw"  # sine | triangle | saw | square
    fm_ratio: float = Field(default=2.0, ge=0.25, le=12.0)
    fm_index: float = Field(default=0.8, ge=0.0, le=8.0)
    cutoff_hz: float = Field(default=2600.0, ge=80.0, le=16000.0)
    resonance: float = Field(default=0.25, ge=0.0, le=0.92)
    attack_ms: float = Field(default=14.0, ge=1.0, le=2000.0)
    decay_ms: float = Field(default=160.0, ge=5.0, le=4000.0)
    sustain: float = Field(default=0.55, ge=0.0, le=1.0)
    release_ms: float = Field(default=220.0, ge=10.0, le=4000.0)
    drive: float = Field(default=0.2, ge=0.0, le=4.0)
    delay_mix: float = Field(default=0.18, ge=0.0, le=0.75)
    delay_ms: float = Field(default=240.0, ge=40.0, le=900.0)


def _adsr_envelope(total_samples: int, patch: SynthPatch, sr: int) -> np.ndarray:
    a_n = max(1, int((patch.attack_ms / 1000.0) * sr))
    d_n = max(1, int((patch.decay_ms / 1000.0) * sr))
    r_n = max(1, int((patch.release_ms / 1000.0) * sr))
    env = np.full(total_samples, patch.sustain, dtype=np.float32)

    a_end = min(total_samples, a_n)
    env[:a_end] = np.linspace(0.0, 1.0, a_end, dtype=np.float32)
    d_end = min(total_samples, a_end + d_n)
    if d_end > a_end:
        env[a_end:d_end] = np.linspace(1.0, patch.sustain, d_end - a_end, dtype=np.float32)

    r_start = max(0, total_samples - r_n)
    if total_samples > r_start:
        start_val = float(env[r_start - 1]) if r_start > 0 else patch.sustain
        env[r_start:] *= np.linspace(1.0, 0.0, total_samples - r_start, dtype=np.float32)
        if r_start == 0:
            env[:] = np.linspace(start_val, 0.0, total_samples, dtype=np.float32)
    return env


def _one_pole_lpf(samples: np.ndarray, cutoff_hz: float, sr: int) -> np.ndarray:
    rc = 1.0 / (2.0 * math.pi * max(40.0, min(cutoff_hz, sr * 0.45)))
    dt = 1.0 / sr
    alpha = float(dt / (rc + dt))
    out = np.empty_like(samples)
    y = 0.0
    one_m = 1.0 - alpha
    for i in range(len(samples)):
        y = alpha * float(samples[i]) + one_m * y
        out[i] = y
    return out


def render_note(
    *,
    midi: int,
    duration_sec: float,
    patch: SynthPatch,
    sample_rate: int = 44100,
    gain: float = 0.65,
) -> np.ndarray:
    n = max(1, int(duration_sec * sample_rate))
    freq = midi_to_hz(midi)
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    mod = patch.fm_index * np.sin(2.0 * math.pi * (freq * patch.fm_ratio) * t) if patch.fm_index > 0 else 0.0
    phase = 2.0 * math.pi * freq * t + mod

    wf = patch.waveform.lower()
    if wf == "sine":
        sig = np.sin(phase)
    elif wf == "triangle":
        sig = (2.0 / math.pi) * np.arcsin(np.sin(phase))
    elif wf == "square":
        sig = np.sign(np.sin(phase))
    else:  # band-warmed sawtooth
        cyc = (phase / (2.0 * math.pi)) % 1.0
        sig = 2.0 * cyc - 1.0

    sig = _one_pole_lpf(sig.astype(np.float32), patch.cutoff_hz, sample_rate)
    env = _adsr_envelope(n, patch, sample_rate)
    sig *= env * float(gain)
    if patch.drive > 0.05:
        sig = np.tanh(sig * (1.0 + patch.drive)) / math.tanh(1.0 + patch.drive)
    return np.clip(sig, -1.0, 1.0).astype(np.float32)


def _render_kick(sr: int) -> np.ndarray:
    n = int(0.24 * sr)
    t = np.arange(n, dtype=np.float32) / sr
    freq = 48.0 + 110.0 * np.exp(-t * 32.0)
    phase = 2.0 * math.pi * np.cumsum(freq) / sr
    amp = np.exp(-t * 11.0)
    return np.tanh(np.sin(phase) * amp * 1.4).astype(np.float32) * 0.85


def _render_snare(sr: int, rng: np.random.Generator) -> np.ndarray:
    n = int(0.18 * sr)
    t = np.arange(n, dtype=np.float32) / sr
    body = np.sin(2.0 * math.pi * 185.0 * t) * np.exp(-t * 22.0) * 0.45
    noise = rng.uniform(-1.0, 1.0, n).astype(np.float32) * np.exp(-t * 16.0) * 0.55
    return np.clip(body + noise, -1.0, 1.0).astype(np.float32) * 0.75


def _render_hat(sr: int, rng: np.random.Generator) -> np.ndarray:
    n = int(0.065 * sr)
    t = np.arange(n, dtype=np.float32) / sr
    raw = rng.uniform(-1.0, 1.0, n).astype(np.float32)
    hp = np.diff(raw, prepend=0.0)
    return np.clip(hp * np.exp(-t * 48.0), -1.0, 1.0).astype(np.float32) * 0.42


def compute_fft_spectrum(samples: np.ndarray, *, sample_rate: int = 44100, num_bins: int = 48) -> list[dict[str, float]]:
    if len(samples) < 32:
        return [{"freq_hz": 0.0, "mag": 0.0} for _ in range(num_bins)]
    win_len = min(4096, len(samples))
    seg = samples[:win_len] * np.hanning(win_len)
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(win_len, d=1.0 / sample_rate)

    # Group linearly into visual harmonic bands up to 6kHz
    edges = np.linspace(40.0, min(6000.0, sample_rate * 0.45), num_bins + 1)
    out: list[dict[str, float]] = []
    max_val = max(float(spec.max()), 1e-6)
    for i in range(num_bins):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        val = float(spec[mask].max()) / max_val if np.any(mask) else 0.0
        out.append({"freq_hz": round(float((edges[i] + edges[i + 1]) * 0.5), 1), "mag": round(val, 4)})
    return out


def render_pattern_wav(
    pattern: dict[str, Any],
    *,
    patch: SynthPatch,
    bars: int = 2,
    sample_rate: int = 44100,
) -> bytes:
    """Synthesize a 16-step polyrhythmic pattern + synth bass/pad into 16-bit PCM WAV bytes."""
    bpm = max(50.0, min(220.0, float(pattern.get("bpm", 116.0))))
    swing = max(0.0, min(0.4, float(pattern.get("swing", 0.0))))
    tracks = pattern.get("tracks") or {}

    step_sec = (60.0 / bpm) / 4.0
    total_steps = 16 * max(1, min(8, int(bars)))
    total_samples = int((total_steps * step_sec + 0.5) * sample_rate)
    mix = np.zeros(total_samples, dtype=np.float32)
    rng = np.random.default_rng(42)

    kick_buf = _render_kick(sample_rate)
    snare_buf = _render_snare(sample_rate, rng)
    hat_buf = _render_hat(sample_rate, rng)

    def mix_in(buf: np.ndarray, offset_idx: int) -> None:
        end = min(total_samples, offset_idx + len(buf))
        if end > offset_idx:
            mix[offset_idx:end] += buf[: end - offset_idx]

    for s in range(total_steps):
        idx = s % 16
        swing_delay = (swing * step_sec) if (s % 2 == 1) else 0.0
        pos = int((s * step_sec + swing_delay) * sample_rate)

        if (tracks.get("kick") or [0] * 16)[idx]:
            mix_in(kick_buf, pos)
        if (tracks.get("snare") or [0] * 16)[idx]:
            mix_in(snare_buf, pos)
        if (tracks.get("hat") or [0] * 16)[idx]:
            mix_in(hat_buf, pos)

        bass_midi = (tracks.get("bass") or [0] * 16)[idx]
        if bass_midi and int(bass_midi) > 0:
            note_buf = render_note(
                midi=int(bass_midi),
                duration_sec=step_sec * 1.4,
                patch=patch.model_copy(update={"cutoff_hz": min(patch.cutoff_hz, 1200.0)}),
                sample_rate=sample_rate,
                gain=0.45,
            )
            mix_in(note_buf, pos)

        pad_midi = (tracks.get("pad") or [0] * 16)[idx]
        if pad_midi and int(pad_midi) > 0:
            for offset in (0, 4, 7):
                chord_buf = render_note(
                    midi=int(pad_midi) + offset,
                    duration_sec=step_sec * 3.5,
                    patch=patch,
                    sample_rate=sample_rate,
                    gain=0.22,
                )
                mix_in(chord_buf, pos)

    # Tape Delay echo pass
    if patch.delay_mix > 0.01:
        d_samp = int((patch.delay_ms / 1000.0) * sample_rate)
        if 0 < d_samp < total_samples:
            mix[d_samp:] += mix[:-d_samp] * float(patch.delay_mix)

    peak = float(np.max(np.abs(mix)))
    if peak > 0.92:
        mix = (mix / peak) * 0.92
    pcm = (np.clip(mix, -1.0, 1.0) * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
