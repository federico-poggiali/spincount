"""Stage 5: verify the recording. Duration check, mix/medley check, fingerprint cross-check."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bpmkey.matching import DURATION_TOLERANCE, MAX_UNKNOWN_DURATION

from . import fingerprint
from .models import Candidate, FetchedAudio, Quality, TrackRef

log = logging.getLogger(__name__)

FAR_LONGER_RATIO = 1.5
FAR_LONGER_MIN_EXTRA = 60
_MIX = re.compile(r"\b(dj[ -]?mix|promo ?mix|mini ?mix|medley|mixtape|podcast|live set|continuous mix|snippets?|sampler|"
                  r"(ep|lp|album|vinyl|all tracks|full) (preview|snippets?)|(preview|snippets?) (of )?(the )?(ep|lp|album|vinyl|all tracks))\b",
                  re.I)


@dataclass
class Verification:
    ok: bool
    reasons: list[str] = field(default_factory=list)      # why accepted or rejected, one line each
    warnings: list[str] = field(default_factory=list)
    duration_ok: Optional[bool] = None                    # None: not checked (preview/clip, or no duration)


_PREVIEW = re.compile(r"\bpreview\b|\bsnippets?\b", re.I)
_RELEASE_WORD = re.compile(r"\b(ep|lp|album|vinyl|all tracks)\b", re.I)


def _looks_like_mix(track: TrackRef, candidate: Candidate | None) -> str | None:
    if candidate is None:
        return None
    text = f"{candidate.title} {candidate.extra.get('release_title', '')}"
    m = _MIX.search(text)
    if m and not _MIX.search(track.title):
        return f"looks like a mix or medley ('{m.group(0)}')"
    if text.count(" / ") >= 2 and track.title.count(" / ") < 2:
        return "title lists several tracks (' / '): a label preview medley"
    if _PREVIEW.search(text) and _RELEASE_WORD.search(text) and not _PREVIEW.search(track.title):
        return "an EP/album preview, not this track alone: a label preview medley"
    return None


def verify(track: TrackRef, fetched: FetchedAudio, candidate: Candidate | None = None, *,
           tolerance: int = DURATION_TOLERANCE, with_fingerprint: bool = True) -> Verification:
    v = Verification(True)
    dur, ref = fetched.duration, track.duration

    if (why := _looks_like_mix(track, candidate)):
        return Verification(False, [why])
    if dur is None:
        v.warnings.append("real duration unknown")
    elif ref is None and dur > MAX_UNKNOWN_DURATION:
        return Verification(False, [f"{dur / 60:.0f} min with no reference duration: a DJ mix or full album"])
    elif ref and dur > max(ref * FAR_LONGER_RATIO, ref + FAR_LONGER_MIN_EXTRA):
        return Verification(False, [f"{dur:.0f}s is far longer than the {ref}s track: mix or medley"], duration_ok=False)
    elif fetched.quality == Quality.FULL and ref:
        if abs(dur - ref) > tolerance:
            return Verification(False, [f"duration {dur:.0f}s vs Discogs {ref}s (tolerance {tolerance}s)"], duration_ok=False)
        v.duration_ok = True
        v.reasons.append(f"duration {dur:.0f}s agrees with Discogs {ref}s")
    elif fetched.quality == Quality.FULL:
        v.reasons.append("full length, no Discogs duration to compare")
    else:
        v.reasons.append(f"{fetched.quality.value}: duration check skipped")

    if with_fingerprint and fetched.fingerprint is None:
        fetched.fingerprint = fingerprint.compute(fetched.path)
        if fetched.fingerprint is None:
            v.warnings.append("no fingerprint (fpcalc missing or file unreadable): duration only")
    return v


def cross_check(a: FetchedAudio, b: FetchedAudio) -> bool | None:
    """Do two fetched sources of one track carry the same recording? None when it cannot be told."""
    for f in (a, b):
        if f.fingerprint is None:
            f.fingerprint = fingerprint.compute(f.path)
    return fingerprint.compare(a.fingerprint, b.fingerprint)


def cross_check_all(item, items) -> bool | None:
    """Against every other source of the track: agreement with any (and no outvoting) is True."""
    agree = disagree = 0
    for other in items:
        if other is item or other.fetched.adapter == item.fetched.adapter and other.fetched.url == item.fetched.url:
            continue
        r = cross_check(item.fetched, other.fetched)
        agree += r is True
        disagree += r is False
    if agree:
        return True
    return False if disagree else None
