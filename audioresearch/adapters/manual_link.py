"""Level 0: a URL you pasted for one track (any site yt-dlp can read, or a direct audio URL)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .. import fetch, http
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from .base import Adapter

DIRECT = {".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wav"}


class ManualLink(Adapter):
    name = "manual_link"
    level = 0

    def __init__(self, store=None):
        self.store = store

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        if self.store is None:
            return []
        links = self.store.manual_links(release.discogs_release_id)
        return [Candidate(self.name, 0, "track", links[t.position], t.title, t.artist, t.duration, quality_hint=Quality.FULL,
                          position=t.position, extra={"trusted": True, "manual": True})
                for t in tracks if t.position in links]

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        client = http.shared()
        host = urlparse(candidate.url).netloc or "manual"
        if Path(urlparse(candidate.url).path).suffix.lower() in DIRECT:
            path = fetch.http_download(candidate.url, dest, site=host, adapter=self.name, http=client)
        else:
            path = fetch.ytdlp_download(candidate.url, dest, throttle=lambda: client.throttle(host))
        return FetchedAudio(path, self.name, candidate.url, Quality.FULL)

    def changed_since(self, release_id: int, saved_at: str) -> bool:
        return self.store is not None and self.store.manual_links_changed(release_id, saved_at)
