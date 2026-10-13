"""Level 2: Bandcamp. Albums first (a release candidate carries the album's tracklist, so the release
match runs before any track is trusted), then single tracks as a fallback for tracks the albums missed.
Fetch with yt-dlp. At least 1 s between requests."""
from __future__ import annotations

import logging
from pathlib import Path

from .. import fetch, http as http_mod
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from ..parsers import bandcamp as bc
from .base import Adapter, AdapterError
from .common import search_artist, search_title

log = logging.getLogger(__name__)
MAX_ALBUMS = 3
MAX_TRACK_HITS = 20


class _BandcampBase(Adapter):
    level = 2
    group = "bandcamp"

    def __init__(self, http=None):
        self._http = http

    @property
    def http(self):
        return self._http or http_mod.shared()

    def _search(self, text: str, kind: str) -> list[bc.SearchHit]:
        r = self.http.request("POST", bc.SEARCH_URL, site="bandcamp", adapter=self.name, json=bc.search_payload(text, kind))
        try:
            return bc.parse_search(r.json())
        except ValueError as e:
            raise bc.ParseError("Bandcamp search did not return JSON") from e

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.ytdlp_download(candidate.url, dest, throttle=lambda: self.http.throttle("bandcamp"))
        return FetchedAudio(path, self.name, candidate.url, Quality.FULL)


class Bandcamp(_BandcampBase):
    name = "bandcamp"

    def page_candidate(self, page: bc.BCPage) -> Candidate:
        tracklist = [TrackRef(str(t.number), page.artist, t.title, t.duration, t.url) for t in page.tracks]
        return Candidate(self.name, self.level, "release", page.url, page.title, page.artist, tracklist=tracklist,
                         quality_hint=Quality.FULL, catno=page.catno,
                         extra={"unavailable": [t.url for t in page.tracks if not t.streamable]})

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        query = f"{search_artist(release.artist)} {release.title}".strip()
        hits = [h for h in self._search(query, "a") if h.kind == "album"][:MAX_ALBUMS]
        out, errors = [], []
        for h in hits:
            try:
                out.append(self.page_candidate(bc.parse_page(self.http.get_text(h.url, site="bandcamp", adapter=self.name), h.url)))
            except AdapterError as e:   # one broken page must not hide the others
                errors.append(e)
                log.warning("bandcamp page %s: %s", h.url, e)
        if hits and not out:
            raise errors[0]
        return out


class BandcampTracks(_BandcampBase):
    name = "bandcamp_tracks"

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        out = []
        for t in tracks:
            query = f"{search_artist(t.artist)} {search_title(t.title)}".strip()
            for h in [h for h in self._search(query, "t") if h.kind == "track"][:MAX_TRACK_HITS]:
                out.append(Candidate(self.name, self.level, "track", h.url, h.title, h.artist, None, quality_hint=Quality.FULL,
                                     position=t.position, extra={"album": h.album}))
        return out
