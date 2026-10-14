"""Stage 6: pick the best verified candidate per track, give it a confidence and a reason.

Confidence (0..1) = 0.60 * match score + 0.15 * verification + 0.25 * agreement between sources.
  verification: duration checked and agrees 1.0; preview/clip (no duration check) 0.7; duration unknown 0.6
  agreement:    another source's fingerprint aligns 1.0; no second source or inconclusive 0.5; disagrees 0.0
Disagreement always sends the track to review (confidence capped just under the threshold).
Your own files score 1.0 and pasted links 0.95: you are the authority.
Best candidate = highest quality first, then highest confidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .matcher import Match
from .models import FetchedAudio, Quality, Reading, Status, TrackResult
from .verify import Verification

W_MATCH, W_VERIFY, W_AGREE = 0.60, 0.15, 0.25


@dataclass
class Accepted:
    """A fetched, verified candidate for one track."""
    match: Match
    fetched: FetchedAudio
    verification: Verification
    level: int
    agreement: Optional[bool] = None   # fingerprint cross-check against another source


def confidence(a: Accepted, review_threshold: float = 0.6) -> float:
    if a.match.via == "trusted":
        return 0.95 if a.match.candidate.extra.get("manual") else 1.0
    v = a.verification
    verify_part = 1.0 if v.duration_ok else (0.6 if a.fetched.duration is None else 0.7)
    agree_part = {True: 1.0, None: 0.5, False: 0.0}[a.agreement]
    c = W_MATCH * a.match.score + W_VERIFY * verify_part + W_AGREE * agree_part
    if a.agreement is False:
        c = min(c, review_threshold - 0.01)
    return max(0.0, min(1.0, c))


def _label(a: Accepted) -> str:
    return f"{a.fetched.adapter} {a.fetched.quality.value}"


def reason_for(a: Accepted, others: list[Accepted], conf: float, review_threshold: float) -> str:
    m = a.match
    if m.via == "trusted":
        kind = "your pasted link" if m.candidate.extra.get("manual") else "your own file"
        return f"{kind} ({m.candidate.extra.get('how', 'matched')})".replace(" (matched)", "")
    how = {"release": f"{a.fetched.adapter} release matched on tracklist", "track": f"{a.fetched.adapter} track matched"}[m.via]
    parts = [f"{how} ({m.score:.2f})"]
    if a.verification.reasons:
        parts.append(a.verification.reasons[0])
    if a.fetched.quality != Quality.FULL:
        parts.append(f"{a.fetched.quality.value} only")
    for o in others:
        if a.agreement is True:
            parts.append(f"fingerprint agrees with {_label(o)}")
            break
    if a.agreement is False:
        parts.append("fingerprint DISAGREES with " + ", ".join(_label(o) for o in others))
    if conf < review_threshold:
        parts.append("sources disagree: needs review" if a.agreement is False else f"confidence {conf:.2f} below {review_threshold:.2f}: needs review")
    return "; ".join(parts)


def decide_track(position: str, accepted: list[Accepted], readings: list[Reading],
                 review_threshold: float = 0.6) -> TrackResult:
    if not accepted:
        return TrackResult(position, Status.NOT_FOUND, reason="no matching audio found", readings=readings)
    scored = [(confidence(a, review_threshold), a) for a in accepted]
    # level 0 always wins; otherwise quality, then confidence
    conf, best = max(scored, key=lambda s: (s[1].level == 0, s[1].fetched.quality.rank, s[0]))
    others = [a for _, a in scored if a is not best]
    status = Status.FOUND if conf >= review_threshold else Status.REVIEW
    return TrackResult(position, status, str(best.fetched.path), best.fetched.adapter, best.level, best.fetched.url,
                       best.fetched.quality, conf, reason_for(best, others, conf, review_threshold), readings,
                       page=best.match.candidate.extra.get("release_url"))
