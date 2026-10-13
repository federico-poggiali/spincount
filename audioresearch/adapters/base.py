"""The plug-in point for levels. An adapter only searches and fetches; matching, verifying and
deciding live in the shared pipeline."""
from __future__ import annotations

from pathlib import Path

from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef


class AdapterError(Exception):
    """A search or fetch failed (network, parser, site change). Counted by adapter health."""


class AdapterUnavailable(AdapterError):
    """The adapter cannot work at all right now (blocked by the site, no credentials): switched off at once."""


class Adapter:
    name: str = ""
    level: int = 0
    # Adapters sharing a group run one after another (a fallback sees only the tracks its
    # predecessor did not match); different groups of one level run in parallel.
    group: str | None = None
    # Best quality this adapter can deliver; lets the pipeline skip it for tracks that already
    # have a result of that quality.
    max_quality: Quality = Quality.FULL
    enabled_by_default: bool = True   # False: built but off until AUDIORESEARCH_ENABLE names it (site not readable yet)

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        """Metadata only. `tracks` are the tracks still to find at this level."""
        raise NotImplementedError

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        """Download the audio of a track-kind candidate. `dest` is the target path WITHOUT an
        extension (audio_cache/<release id>/<position>.<adapter>); the adapter adds it."""
        raise NotImplementedError

    def take_diagnostics(self) -> list[dict]:
        """Things the adapter noticed but cannot return as candidates, e.g. [{"url": ..., "reason": ...}]
        for your files that match no track. The pipeline logs them as rejected candidates."""
        return []

    def changed_since(self, release_id: int, saved_at: str) -> bool:
        """True when this adapter's own inputs (your files, pasted links) changed after a cached result."""
        return False

    @property
    def group_key(self) -> str:
        return self.group or self.name

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} L{self.level}>"
