"""Chromaprint fingerprints (`fpcalc -raw`) and local alignment. No AcoustID lookup: files are only
compared with each other."""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

ITEMS_PER_SECOND = 8.06      # one raw Chromaprint value per ~0.124 s
AGREE = 0.70                 # best-match bit similarity at or above this: same recording (chance is ~0.5, the best of many offsets ~0.6)
DISAGREE = 0.63              # below this: clearly different audio; in between is inconclusive
PROBE_SECONDS = 20           # the shorter file is reduced to its middle 20 s before sliding
MIN_ITEMS = 24               # under ~3 s there is nothing to align
_warned = False


def available() -> bool:
    return shutil.which("fpcalc") is not None


def compute(path: Path | str, max_seconds: int = 900) -> list[int] | None:
    """Raw fingerprint of up to `max_seconds`, or None when fpcalc is missing or cannot read the file."""
    global _warned
    if not available():
        if not _warned:
            log.warning("fpcalc (Chromaprint) not found: verification falls back to duration only")
            _warned = True
        return None
    try:
        out = subprocess.run(["fpcalc", "-raw", "-length", str(max_seconds), str(path)], capture_output=True, text=True, timeout=120)
    except subprocess.SubprocessError:
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            vals = line.split("=", 1)[1].strip()
            return [int(v) & 0xFFFFFFFF for v in vals.split(",")] if vals else None
    return None


def _popcount(a: np.ndarray) -> np.ndarray:
    a = a - ((a >> 1) & 0x55555555)
    a = (a & 0x33333333) + ((a >> 2) & 0x33333333)
    a = (a + (a >> 4)) & 0x0F0F0F0F
    return (a * 0x01010101 & 0xFFFFFFFF) >> 24


@dataclass
class Alignment:
    ratio: float          # best mean bit similarity, 0.5 is chance, 1.0 identical
    offset: float         # seconds into the longer file where the excerpt lines up


def align(short: list[int], long: list[int]) -> Alignment | None:
    """Slide (the middle of) the shorter fingerprint along the longer one; return the best match."""
    if len(short) > len(long):
        short, long = long, short
    if len(short) < MIN_ITEMS:
        return None
    n = min(len(short), int(PROBE_SECONDS * ITEMS_PER_SECOND))
    mid = len(short) // 2
    probe = np.array(short[max(0, mid - n // 2): max(0, mid - n // 2) + n], dtype=np.uint64)
    hay = np.array(long, dtype=np.uint64)
    windows = np.lib.stride_tricks.sliding_window_view(hay, len(probe))
    sims = 1 - _popcount(windows ^ probe).mean(axis=1) / 32
    best = int(sims.argmax())
    return Alignment(float(sims[best]), best / ITEMS_PER_SECOND)


def compare(a: list[int] | None, b: list[int] | None) -> bool | None:
    """True: same recording. False: different. None: cannot tell."""
    if not a or not b:
        return None
    al = align(a, b)
    if al is None:
        return None
    if al.ratio >= AGREE:
        return True
    return False if al.ratio < DISAGREE else None
