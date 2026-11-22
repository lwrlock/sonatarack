import io
import wave
import pytest


def test_euclidean_rhythm_bjorklund_spacing_and_rotation():
    from sonatarack.theory import euclidean_rhythm

    tresillo = euclidean_rhythm(3, 8)
    assert len(tresillo) == 8
    assert sum(tresillo) == 3
    assert tresillo == [1, 0, 0, 1, 0, 0, 1, 0]

    cinquillo = euclidean_rhythm(5, 8)
    assert sum(cinquillo) == 5
    rot = euclidean_rhythm(3, 8, rotation=1)
    assert rot == [0, 1, 0, 0, 1, 0, 0, 1]

    assert euclidean_rhythm(0, 16) == [0] * 16
    assert euclidean_rhythm(16, 16) == [1] * 16


def test_midi_scale_and_chord_voicings():
    from sonatarack.theory import build_chord, midi_to_hz, scale_notes

    assert midi_to_hz(69) == pytest.approx(440.0, rel=1e-4)
    assert midi_to_hz(57) == pytest.approx(220.0, rel=1e-4)

    hijaz = scale_notes(60, "hijaz", octaves=1)
    assert hijaz == [60, 61, 64, 65, 67, 68, 70]

    maj9 = build_chord(60, "maj9")
    assert maj9 == [60, 64, 67, 71, 74]


def test_dsp_synth_adsr_fft_and_wav_export():
    from sonatarack.dsp import SynthPatch, compute_fft_spectrum, render_note, render_pattern_wav

    patch = SynthPatch(waveform="saw", fm_index=0.0, cutoff_hz=4500.0, drive=0.2)
    samples = render_note(midi=69, duration_sec=0.35, patch=patch, sample_rate=44100)
    assert len(samples) == int(0.35 * 44100)
    assert float(samples.max()) <= 1.0 and float(samples.min()) >= -1.0

    bins = compute_fft_spectrum(samples, sample_rate=44100, num_bins=48)
    assert len(bins) == 48
    peak_bin = max(bins, key=lambda b: b["mag"])
    assert 350.0 <= peak_bin["freq_hz"] <= 550.0

    pattern = {
        "bpm": 118,
        "swing": 0.12,
        "tracks": {
            "kick": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
            "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
            "hat": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1],
            "bass": [36, 0, 0, 36, 0, 0, 39, 0, 41, 0, 0, 0, 39, 0, 43, 0],
            "pad": [60, 0, 0, 0, 0, 0, 0, 0, 65, 0, 0, 0, 0, 0, 0, 0],
        },
    }
    wav_bytes = render_pattern_wav(pattern, patch=patch, bars=1, sample_rate=22050)
    assert wav_bytes[:4] == b"RIFF"
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 22050
        assert wf.getnframes() > 10000
