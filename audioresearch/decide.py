"""Stage 6: decide (stub until Step 10)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .matcher import Match
from .models import FetchedAudio, Quality, Reading, Status, TrackResult
from .verify import Verification


@dataclass
class Accepted:
    """A fetched, verified candidate for one track."""
    match: Match
    fetched: FetchedAudio
    verification: Verification
    level: int
    agreement: Optional[bool] = None   # fingerprint cross-check against another source


def decide_track(position: str, accepted: list[Accepted], readings: list[Reading],
                 review_threshold: float = 0.6) -> TrackResult:
    if not accepted:
        return TrackResult(position, Status.NOT_FOUND, reason="no matching audio found", readings=readings)
    best = max(accepted, key=lambda a: (a.fetched.quality.rank, a.match.score))
    return TrackResult(position, Status.FOUND, str(best.fetched.path), best.fetched.adapter, best.level, best.fetched.url,
                       best.fetched.quality, best.match.score, "stub", readings)
