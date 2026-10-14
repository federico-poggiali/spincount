"""Is a YouTube / SoundCloud link one track or the whole record? A flag only, never a reject."""
from __future__ import annotations

import re

from .models import Candidate, ReleaseIdentity

TRACK = "track"
RELEASE = "release"          # the whole record (or a mix of it) in one file
UNKNOWN = "unknown"          # no duration data and no timestamps: cannot tell

WHOLE_SHARE = 0.85           # candidate this close to the summed track durations = whole record
SAME_TRACK = 0.10            # within 10% of one Discogs track = that track
MIN_STAMPS = 3               # timestamps in the description that make it a tracklist
_STAMP = re.compile(r"(?m)^\W*(?:\d{1,2}:)?\d{1,2}:\d{2}\b")


def has_timestamps(text: str | None) -> bool:
    return len(_STAMP.findall(text or "")) >= MIN_STAMPS


def classify(identity: ReleaseIdentity, cand: Candidate) -> tuple[str, str]:
    """(scope, why). Timestamps in the description are a sign of a whole record; durations decide when the
    Discogs tracks have them; with neither, say so rather than guess."""
    if has_timestamps(cand.extra.get("description")):
        return RELEASE, "timestamps in the description"
    durs = [t.duration for t in identity.tracks if t.duration]
    if not cand.duration or not durs:
        return UNKNOWN, "no duration to compare"
    if any(abs(cand.duration - d) <= SAME_TRACK * d for d in durs):
        return TRACK, "duration fits one track"
    if len(durs) > 1 and len(durs) == len(identity.tracks) and cand.duration >= WHOLE_SHARE * sum(durs):
        return RELEASE, f"{cand.duration}s vs {sum(durs)}s for all tracks"
    return TRACK, "shorter than the whole record"
