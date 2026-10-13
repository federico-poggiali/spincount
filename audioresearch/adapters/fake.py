"""FakeAdapter: an adapter driven by canned data, for tests and the viewer's --fake mode."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from .base import Adapter, AdapterError


class FakeAdapter(Adapter):
    """`candidates`: what search returns. Track candidates with a `position` are returned only when
    that track is still being searched; release candidates and position-less ones always are.
    `durations`: real length by url for fetched files (default: the candidate's duration)."""

    def __init__(self, name: str, level: int, candidates: list[Candidate] | None = None, *,
                 group: str | None = None, max_quality: Quality = Quality.FULL,
                 durations: dict[str, float] | None = None, fetch_errors: set[str] | None = None,
                 search_error: bool = False, delay: float = 0.0):
        self.name, self.level, self.group, self.max_quality = name, level, group, max_quality
        self.candidates = candidates or []
        self.durations = durations or {}
        self.fetch_errors = fetch_errors or set()
        self.search_error = search_error
        self.delay = delay
        self.searched: list[list[str]] = []   # positions asked, per search call
        self.fetched: list[str] = []          # urls fetched
        self._lock = threading.Lock()

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        with self._lock:
            self.searched.append([t.position for t in tracks])
        if self.delay:
            time.sleep(self.delay)
        if self.search_error:
            raise AdapterError(f"{self.name}: simulated search failure")
        wanted = {t.position for t in tracks}
        return [c for c in self.candidates if c.kind == "release" or c.position is None or c.position in wanted]

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        if self.delay:
            time.sleep(self.delay / 2)
        with self._lock:
            self.fetched.append(candidate.url)
        if candidate.url in self.fetch_errors:
            raise AdapterError(f"{self.name}: simulated fetch failure")
        path = dest.parent / (dest.name + ".fake")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake audio")
        dur = self.durations.get(candidate.url, candidate.duration)
        return FetchedAudio(path, self.name, candidate.url, candidate.quality_hint, float(dur) if dur else None)


def demo_registry(identity: ReleaseIdentity, delay: float = 0.35):
    """Fake adapters for any release (viewer --fake): each level finds a deterministic share of the
    tracks, with some wrong candidates mixed in, and takes a moment so the viewer shows progress."""
    import random

    from . import Registry

    rng = random.Random(identity.discogs_release_id)
    positions = [t.position for t in identity.tracks]
    pick = lambda p: [t for t in identity.tracks if rng.random() < p]  # noqa: E731

    def track_cand(adapter: str, level: int, t: TrackRef, q: Quality, title: str | None = None) -> Candidate:
        return Candidate(adapter, level, "track", f"https://{adapter}.example/{identity.discogs_release_id}/{t.position}",
                         title or t.title, t.artist or identity.artist, t.duration or 300, quality_hint=q, position=t.position)

    yt = [track_cand("discogs_youtube", 1, t, Quality.FULL) for t in pick(0.4)]
    yt.append(track_cand("discogs_youtube", 1, identity.tracks[0], Quality.FULL, "Completely Different Song"))
    it = [track_cand("itunes", 1, t, Quality.PREVIEW) for t in pick(0.4)]
    tracklist = [TrackRef(str(i), t.artist, t.title, t.duration or 300, f"https://bandcamp.example/{t.position}")
                 for i, t in enumerate(identity.tracks, 1)]
    bc = [Candidate("bandcamp", 2, "release", "https://bandcamp.example/release", identity.title, identity.artist,
                    tracklist=tracklist, catno=identity.catno)] if identity.discogs_release_id % 2 == 0 else []
    sc = [track_cand("soundcloud_tracks", 3, t, Quality.FULL) for t in pick(0.5)]
    bp = [track_cand("beatport_tracks", 4, t, Quality.PREVIEW) for t in pick(0.5)]
    st = [track_cand("deejay_de", 5, t, Quality.CLIP) for t in pick(0.7)]
    return Registry([
        FakeAdapter("discogs_youtube", 1, yt, group="youtube", delay=delay),
        FakeAdapter("itunes", 1, it, max_quality=Quality.PREVIEW, delay=delay * 0.7),
        FakeAdapter("bandcamp", 2, bc, delay=delay),
        FakeAdapter("soundcloud_tracks", 3, sc, delay=delay),
        FakeAdapter("beatport_tracks", 4, bp, max_quality=Quality.PREVIEW, delay=delay),
        FakeAdapter("deejay_de", 5, st, max_quality=Quality.CLIP, delay=delay),
    ], disabled=set())
