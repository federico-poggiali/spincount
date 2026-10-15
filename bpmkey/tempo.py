"""BPM: two fast Essentia estimators and the onset tempogram vote on a tempo, a log-normal prior picks the octave.

Every reading votes for its tempo and for its double and half (that finds the tempo class); an extra vote
for the reading's own value, the tempogram strength at each tempo and the prior then decide between
x1/2, x1 and x2. Without a prior the default one (all of GiantSteps Tempo + GiantSteps-MTG) is used; a
caller that knows the music's style can pass a narrower one, e.g. from `fit_prior` over the owner's own
BPMs for that style. Weights: `benchmark/tempo_fit_ship.py` (git-ignored, on the owner's computer).

Within 4% of the label, default prior, against RhythmExtractor2013(multifeature) folded into 70-180 (the
previous method): GiantSteps Tempo, hand-checked, 62.5% -> 76.7%; GiantSteps-MTG, Beatport's listed BPM,
94.4% -> 91.2%. The two sets write some genres an octave apart (drum & bass ~174 vs ~88), so a style prior
learned from the owner's own BPMs is what settles the octave. About 2.5 s per full track instead of 4.7 s.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_MODEL = json.loads((Path(__file__).parent / "data" / "tempo_vote.json").read_text())
WEIGHTS = _MODEL["weights"]
DEFAULT_PRIOR = (_MODEL["prior"]["mu"], _MODEL["prior"]["sd"])
GRID = np.exp(np.arange(np.log(55), np.log(210), 0.005))  # candidate tempi, 0.5% apart
SIGMA = 0.02  # width of a vote, in log units (about 2%)
TEMPOGRAM_SR = 22050


def _kernel(values) -> np.ndarray:
    v = np.asarray([x for x in values if x and x > 0], dtype=float)
    if not len(v):
        return np.zeros_like(GRID)
    d = np.log(GRID)[:, None] - np.log(v)[None, :]
    return np.exp(-d ** 2 / (2 * SIGMA ** 2)).sum(axis=1)


def readings(audio: np.ndarray, sr: int = 44100) -> dict:
    """degara and Percival BPMs plus the mean tempogram as [[bpm, strength], ...]."""
    import essentia.standard as es
    import librosa

    out = {"degara": float(es.RhythmExtractor2013(method="degara")(audio)[0]),
           "percival": float(es.PercivalBpmEstimator()(audio))}
    y = librosa.resample(audio, orig_sr=sr, target_sr=TEMPOGRAM_SR) if sr != TEMPOGRAM_SR else audio
    oenv = librosa.onset.onset_strength(y=y, sr=TEMPOGRAM_SR)
    tg = librosa.feature.tempogram(onset_envelope=oenv, sr=TEMPOGRAM_SR).mean(axis=1)
    freqs = librosa.tempo_frequencies(len(tg), sr=TEMPOGRAM_SR)
    keep = (freqs >= 50) & (freqs <= 220)
    out["tempogram"] = [[float(f), float(v)] for f, v in zip(freqs[keep], tg[keep])]
    return out


def vote(r: dict, prior: tuple[float, float] | None = None, weights: dict | None = None) -> float | None:
    """One BPM from `readings`. prior: (mean, sd) of log BPM."""
    w = weights or WEIGHTS
    mu, sd = prior or DEFAULT_PRIOR
    vals = [r.get("degara"), r.get("percival")]
    n = sum(1 for v in vals if v and v > 0)
    if not n:
        return None
    score = _kernel([v * f for v in vals if v for f in (0.5, 1, 2)]) / n
    score += w["exact"] * _kernel(vals) / n
    tg = np.array(r.get("tempogram") or [])
    if len(tg):  # tempogram rows run from fast to slow
        s = np.interp(np.log(GRID), np.log(tg[::-1, 0]), tg[::-1, 1])
        score += w["tempogram"] * s / (s.max() or 1)
    score += w["prior"] * -((np.log(GRID) - mu) ** 2) / (2 * sd ** 2)
    return float(GRID[int(score.argmax())])


def estimate(audio: np.ndarray, sr: int = 44100, prior: tuple[float, float] | None = None) -> float | None:
    return vote(readings(audio, sr), prior)


def fit_prior(bpms, min_tracks: int = 5) -> tuple[float, float] | None:
    """A prior from known BPMs (e.g. the owner's hand-entered ones for one style); None when too few."""
    v = np.log([b for b in bpms if b and b > 0])
    if len(v) < min_tracks:
        return None
    return float(v.mean()), float(max(v.std(), 0.05))
