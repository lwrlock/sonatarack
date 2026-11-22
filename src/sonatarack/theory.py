"""Music theory utilities: Bjorklund Euclidean rhythms, scales, and chord voicings."""

from __future__ import annotations

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

SCALES: dict[str, tuple[int, ...]] = {
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "hijaz": (0, 1, 4, 5, 7, 8, 10),
    "pentatonic_minor": (0, 3, 5, 7, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "blues": (0, 3, 5, 6, 7, 10),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "major": (0, 2, 4, 5, 7, 9, 11),
}

CHORDS: dict[str, tuple[int, ...]] = {
    "triad_maj": (0, 4, 7),
    "triad_min": (0, 3, 7),
    "maj9": (0, 4, 7, 11, 14),
    "min11": (0, 3, 7, 10, 14, 17),
    "dom7b9": (0, 4, 7, 10, 13),
    "sus4": (0, 5, 7, 10),
}


def midi_to_hz(midi: int | float) -> float:
    return float(440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0)))


def midi_to_name(midi: int) -> str:
    octave = (int(midi) // 12) - 1
    return f"{NOTE_NAMES[int(midi) % 12]}{octave}"


def scale_notes(root_midi: int, scale_name: str, *, octaves: int = 1) -> list[int]:
    intervals = SCALES.get(scale_name.lower())
    if not intervals:
        raise ValueError(f"Unknown scale: {scale_name}")
    notes: list[int] = []
    for oct_idx in range(max(1, octaves)):
        base = root_midi + 12 * oct_idx
        for iv in intervals:
            m = base + iv
            if 0 <= m <= 127:
                notes.append(m)
    return notes


def build_chord(root_midi: int, chord_name: str) -> list[int]:
    intervals = CHORDS.get(chord_name.lower())
    if not intervals:
        raise ValueError(f"Unknown chord: {chord_name}")
    return [root_midi + iv for iv in intervals if 0 <= (root_midi + iv) <= 127]


def euclidean_rhythm(pulses: int, steps: int, rotation: int = 0) -> list[int]:
    """Bjorklund algorithm distributing k pulses maximally evenly across n steps."""
    n = max(1, int(steps))
    k = max(0, min(n, int(pulses)))
    if k == 0:
        return [0] * n
    if k == n:
        return [1] * n

    groups = [[1] for _ in range(k)] + [[0] for _ in range(n - k)]
    pivot = k
    remainder = n - k

    while remainder > 1:
        count = min(pivot, remainder)
        new_groups = [groups[i] + groups[pivot + i] for i in range(count)]
        leftover_a = groups[count:pivot]
        leftover_b = groups[pivot + count :]
        groups = new_groups + leftover_a + leftover_b
        pivot = count
        remainder = len(leftover_a) + len(leftover_b)
        if not leftover_b and len(leftover_a) <= 1:
            break

    pattern = [bit for grp in groups for bit in grp]
    rot = rotation % n
    if rot:
        pattern = pattern[-rot:] + pattern[:-rot]
    return pattern
