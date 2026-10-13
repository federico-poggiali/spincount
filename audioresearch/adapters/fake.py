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
        path = dest.with_suffix(".fake")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake audio")
        dur = self.durations.get(candidate.url, candidate.duration)
        return FetchedAudio(path, self.name, candidate.url, candidate.quality_hint, float(dur) if dur else None)
