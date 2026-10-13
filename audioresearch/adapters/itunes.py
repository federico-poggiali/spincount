"""Level 1, route 1a: iTunes Search API (no key). Previews are ~30 s, so the real quality becomes `clip`."""
from __future__ import annotations

from pathlib import Path

from .. import fetch, http as http_mod
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from .base import Adapter
from .common import search_artist, search_title

API = "https://itunes.apple.com/search"


def parse_results(data: dict, position: str | None = None, adapter: str = "itunes", level: int = 1) -> list[Candidate]:
    out = []
    for r in (data.get("results") if isinstance(data, dict) else None) or []:
        if not r.get("previewUrl"):
            continue
        # duration = the FULL track length (trackTimeMillis); the preview itself is measured on fetch
        dur = round(r["trackTimeMillis"] / 1000) if r.get("trackTimeMillis") else None
        out.append(Candidate(adapter, level, "track", r["previewUrl"], r.get("trackName", ""), r.get("artistName", ""), dur,
                             quality_hint=Quality.PREVIEW, position=position,
                             extra={"album": r.get("collectionName"), "track_url": r.get("trackViewUrl")}))
    return out


class ITunesPreview(Adapter):
    name = "itunes"
    level = 1
    max_quality = Quality.PREVIEW

    def __init__(self, http=None):
        self._http = http

    @property
    def http(self):
        return self._http or http_mod.shared()

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        out = []
        for t in tracks:
            data = self.http.get_json(API, site="itunes", adapter=self.name, params={
                "term": f"{search_artist(t.artist)} {search_title(t.title)}".strip(), "entity": "song", "limit": 10})
            out += parse_results(data, t.position, self.name, self.level)
        return out

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.http_download(candidate.url, dest, site="itunes", adapter=self.name, http=self.http)
        return FetchedAudio(path, self.name, candidate.url, Quality.PREVIEW)
