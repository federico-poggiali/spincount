"""Tiny synthetic audio for tests: real WAV files, no binary fixtures."""
import wave
from pathlib import Path

import numpy as np

SR = 11025


def melody(seed: int, seconds: float) -> np.ndarray:
    """A seeded random tune: different seeds give clearly different music."""
    rng = np.random.default_rng(seed)
    out, t0 = [], 0.0
    while t0 < seconds:
        dur = float(rng.choice([0.25, 0.375, 0.5]))
        f = 220 * 2 ** (rng.integers(0, 24) / 12)
        t = np.arange(int(dur * SR)) / SR
        note = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2 * f * t) + 0.2 * np.sin(2 * np.pi * 3 * f * t)
        out.append(note * np.exp(-3 * t / dur))
        t0 += dur
    y = np.concatenate(out)[: int(seconds * SR)]
    return y / (np.abs(y).max() or 1)


def write_wav(path: Path, samples: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32000).astype("<i2").tobytes())
    return path


def make_wav(path: Path, seconds: float, seed: int = 1) -> Path:
    return write_wav(path, melody(seed, seconds))
