"""Stage 3: the shared matcher. Release match first, then track match, for every level.

Built on bpmkey.matching. Weights of the release score (a weighted mean over the parts that
can be computed: a part with no data, e.g. missing durations, is left out, not counted as 0):

    catalogue number equal      0.35   strong; only when both sides have one (a mismatch scores 0)
    release title similarity    0.15
    artist similarity           0.10   skipped for "Various" releases
    track count                 0.10   6 vs 7 tracks (a bonus track) still scores high
    per-track title similarity  0.20   version words (remix, dub, live ...) must agree
    per-track duration          0.10   within DURATION_TOLERANCE seconds

A release candidate is accepted at RELEASE_THRESHOLD. Inside it, a track pairs with a candidate
track at TRACK_IN_RELEASE_THRESHOLD (title 0.65, position 0.20, duration 0.15, same leave-out rule).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from bpmkey.matching import (DURATION_TOLERANCE, bracket_penalty, dynamic_threshold, norm, score_candidate,
                             similarity, version_penalty)

from .models import Candidate, ReleaseIdentity, TrackRef

W_CATNO, W_TITLE, W_ARTIST, W_COUNT, W_TRACK_TITLES, W_DURATIONS = 0.35, 0.15, 0.10, 0.10, 0.20, 0.10
RELEASE_THRESHOLD = 0.70
TRACK_IN_RELEASE_THRESHOLD = 0.60
MIN_PAIR_TITLE = 0.50          # a track never pairs on position alone
VERSION_CONFLICT_PENALTY = 0.5  # Original Mix vs Dub Mix: in either direction
AMBIGUITY_MARGIN = 0.03


def norm_catno(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_position(p: str) -> str:
    return re.sub(r"\d+", lambda m: str(int(m.group())), p.strip().upper())


def _is_various(artist: str) -> bool:
    return norm(artist).startswith("various")


def version_conflict(a: str, b: str) -> bool:
    """True when one title is a different version (remix, dub, live ...) than the other."""
    return version_penalty(a, b) > 0 or version_penalty(b, a) > 0


def title_score(a: str, b: str) -> float:
    """0..1 similarity of two track titles; a version conflict costs 0.5 in either direction."""
    s = similarity(a, b)
    if version_conflict(a, b):
        s -= VERSION_CONFLICT_PENALTY
    s -= max(bracket_penalty(a, b), bracket_penalty(b, a))
    return max(0.0, s)


def _wmean(parts: list[tuple[float, float]]) -> float:
    total = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / total if total else 0.0


def _duration_agrees(a: int | None, b: int | None) -> float | None:
    if not a or not b:
        return None
    return 1.0 if abs(a - b) <= DURATION_TOLERANCE else 0.0


def _position_agrees(track: TrackRef, ordinal: int, cand_track: TrackRef, cand_ordinal: int) -> float | None:
    if not cand_track.position:
        return None
    cp = norm_position(cand_track.position)
    if cp == norm_position(track.position):
        return 1.0
    if cp.isdigit():                       # "1", "2" ... on Bandcamp and the like
        return 1.0 if int(cp) == ordinal else 0.0
    return 0.0


def _pair_score(track: TrackRef, ordinal: int, ct: TrackRef, cand_ordinal: int) -> float:
    ts = title_score(track.title, ct.title)
    if ts < MIN_PAIR_TITLE:
        return 0.0
    parts = [(0.65, ts)]
    pos = _position_agrees(track, ordinal, ct, cand_ordinal)
    if pos is not None:
        parts.append((0.20, pos))
    dur = _duration_agrees(track.duration, ct.duration)
    if dur is not None:
        parts.append((0.15, dur))
    return _wmean(parts)


def assign_tracks(identity: ReleaseIdentity, cand: Candidate) -> dict[str, tuple[float, TrackRef]]:
    """Greedy one-to-one pairing of Discogs tracks with a release candidate's tracks, best pairs first."""
    pairs = []
    for i, t in enumerate(identity.tracks, 1):
        for j, ct in enumerate(cand.tracklist or [], 1):
            s = _pair_score(t, i, ct, j)
            if s > 0:
                pairs.append((s, i, j))
    out: dict[str, tuple[float, TrackRef]] = {}
    used: set[int] = set()
    for s, i, j in sorted(pairs, key=lambda p: (-p[0], p[1], p[2])):
        t = identity.tracks[i - 1]
        if t.position in out or j in used:
            continue
        out[t.position] = (s, cand.tracklist[j - 1])
        used.add(j)
    return out


def match_release(identity: ReleaseIdentity, cand: Candidate) -> float:
    """0..1 score of how likely a release candidate is this Discogs release."""
    parts: list[tuple[float, float]] = []
    if identity.catno and cand.catno:
        parts.append((W_CATNO, 1.0 if norm_catno(identity.catno) == norm_catno(cand.catno) else 0.0))
    if cand.title:
        parts.append((W_TITLE, similarity(identity.title, cand.title)))
    if cand.artist and not _is_various(identity.artist) and not _is_various(cand.artist):
        parts.append((W_ARTIST, similarity(identity.artist, cand.artist)))
    if cand.tracklist:
        n1, n2 = len(identity.tracks), len(cand.tracklist)
        parts.append((W_COUNT, min(n1, n2) / max(n1, n2) if n1 and n2 else 0.0))
        best = [max(title_score(t.title, ct.title) for ct in cand.tracklist) for t in identity.tracks]
        if best:
            parts.append((W_TRACK_TITLES, sum(best) / len(best)))
        assigned = assign_tracks(identity, cand)
        agree = [a for p, (_, ct) in assigned.items()
                 if (a := _duration_agrees(identity.track(p).duration, ct.duration)) is not None]
        if agree:
            parts.append((W_DURATIONS, sum(agree) / len(agree)))
    return _wmean(parts)


def match_tracks_in_release(identity: ReleaseIdentity, cand: Candidate) -> dict[str, float]:
    """position -> score for the tracks that pair with a track of the release candidate."""
    return {p: s for p, (s, _) in assign_tracks(identity, cand).items() if s >= TRACK_IN_RELEASE_THRESHOLD}


def track_threshold(identity: ReleaseIdentity) -> float:
    """Bar for a lone track candidate; rises when the release's titles are alike (many mixes of one song)."""
    return dynamic_threshold([t.title for t in identity.tracks])


def match_track(identity: ReleaseIdentity, track: TrackRef, cand: Candidate) -> float:
    """0..1 score of a track candidate against one track (compare with track_threshold)."""
    s = score_candidate(track.artist, track.title, track.duration, cand.title, cand.artist, cand.duration)
    if s and version_conflict(track.title, cand.title):
        # bpmkey only checks one direction and charges 0.4; here a conflict always costs 0.5
        s -= VERSION_CONFLICT_PENALTY - version_penalty(track.title, cand.title)
    return max(0.0, s)


@dataclass
class Match:
    position: str
    candidate: Candidate          # always kind == "track"
    score: float
    via: str                      # "track" | "release"
    release_score: float | None = None


@dataclass
class MatchOutcome:
    matches: dict[str, list[Match]] = field(default_factory=dict)      # position -> best first
    releases: list[tuple[Candidate, float]] = field(default_factory=list)  # accepted release candidates
    rejected: list[tuple[Candidate, str]] = field(default_factory=list)


def match_candidates(identity: ReleaseIdentity, tracks: list[TrackRef], candidates: list[Candidate],
                     top: int = 3) -> MatchOutcome:
    """Match an adapter's candidates against the tracks still to find; keep the top few per track."""
    out = MatchOutcome()
    bar = track_threshold(identity)
    wanted = {t.position for t in tracks}
    found: list[Match] = []
    for c in candidates:
        if c.kind == "release":
            rs = match_release(identity, c)
            if rs < RELEASE_THRESHOLD:
                out.rejected.append((c, f"release score {rs:.2f} below {RELEASE_THRESHOLD}"))
                continue
            out.releases.append((c, rs))
            hit = False
            for pos, (s, ct) in assign_tracks(identity, c).items():
                if pos in wanted and s >= TRACK_IN_RELEASE_THRESHOLD:
                    found.append(Match(pos, c.for_track(ct, pos), s, "release", rs))
                    hit = True
            if not hit:
                out.rejected.append((c, "release matched but none of the wanted tracks"))
        else:
            scored = sorted(((match_track(identity, t, c), t.position) for t in tracks), reverse=True)
            if not scored or scored[0][0] < bar:
                out.rejected.append((c, f"track score {scored[0][0] if scored else 0:.2f} below {bar:.2f}"))
            elif len(scored) > 1 and scored[0][0] - scored[1][0] < AMBIGUITY_MARGIN and scored[1][0] >= bar:
                out.rejected.append((c, f"ambiguous: fits {scored[0][1]} and {scored[1][1]} equally"))
            else:
                found.append(Match(scored[0][1], c, scored[0][0], "track"))
    for m in found:
        out.matches.setdefault(m.position, []).append(m)
    for pos, ms in out.matches.items():
        ms.sort(key=lambda m: (-m.candidate.quality_hint.rank, -m.score))
        out.matches[pos] = ms[:top]
    return out
