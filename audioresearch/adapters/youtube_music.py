"""Level 1, route 1b fallback: YouTube Music search (ytmusicapi, unofficial), only for tracks the
Discogs videos did not match."""
from __future__ import annotations

from pathlib import Path

from .. import fetch, http
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from .base import Adapter, AdapterError
from .common import search_artist, search_title

WATCH = "https://music.youtube.com/watch?v={}"


def parse_results(results: list[dict], position: str | None = None, adapter: str = "youtube_music", level: int = 1) -> list[Candidate]:
    """ytmusicapi `search(filter="songs")` rows -> candidates."""
    out = []
    for r in results:
        if not r.get("videoId"):
            continue
        out.append(Candidate(adapter, level, "track", WATCH.format(r["videoId"]), r.get("title") or "",
                             ", ".join(a["name"] for a in r.get("artists") or []), r.get("duration_seconds"),
                             quality_hint=Quality.FULL, position=position,
                             extra={"album": (r.get("album") or {}).get("name")}))
    return out


class YouTubeMusic(Adapter):
    name = "youtube_music"
    level = 1
    group = "youtube"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from ytmusicapi import YTMusic

            self._client = YTMusic()
        return self._client

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        out = []
        for t in tracks:
            http.shared().throttle("youtube_music")
            query = f"{search_artist(t.artist)} {search_title(t.title)}".strip()
            try:
                rows = self.client.search(query, filter="songs", limit=5)
            except Exception as e:  # ytmusicapi raises many kinds of errors when the site changes
                raise AdapterError(f"ytmusicapi search failed: {type(e).__name__}: {e}") from e
            out += parse_results(rows, t.position, self.name, self.level)
        return out

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.ytdlp_download(candidate.url, dest, throttle=lambda: http.shared().throttle("youtube"))
        return FetchedAudio(path, self.name, candidate.url, Quality.FULL)
