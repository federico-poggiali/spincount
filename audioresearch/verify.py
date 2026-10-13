"""Stage 5: verification (stub until Step 9)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import FetchedAudio, TrackRef


@dataclass
class Verification:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    duration_ok: bool | None = None


def verify(track: TrackRef, fetched: FetchedAudio) -> Verification:
    return Verification(True, [])


def cross_check(a: FetchedAudio, b: FetchedAudio) -> bool | None:
    return None
