"""Level 3, route 3a: SoundCloud track search by artist and title (the API behind yt-dlp's `scsearch`)."""
from __future__ import annotations

from pathlib import Path

from .. import fetch, http as http_mod
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from ..parsers import soundcloud as sc
from .base import Adapter
from .common import search_artist, search_title

PER_TRACK = 12


class SoundCloudTracks(Adapter):
    name = "soundcloud_tracks"
    level = 3

    def __init__(self, api: sc.SoundcloudApi | None = None):
        self.api = api or sc.SoundcloudApi(lambda: http_mod.shared().throttle("soundcloud"))

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        out = []
        for t in tracks:
            query = f"{search_artist(t.artist)} {search_title(t.title)}".strip()
            for r in sc.parse_tracks(self.api.call("search/tracks", q=query, limit=PER_TRACK))[:PER_TRACK]:
                if r.blocked:
                    continue
                out.append(Candidate(self.name, self.level, "track", r.url, r.title, r.artist, r.duration,
                                     quality_hint=r.quality, position=t.position, extra={"policy": r.policy}))
        return out

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.ytdlp_download(candidate.url, dest, throttle=lambda: http_mod.shared().throttle("soundcloud"))
        return FetchedAudio(path, self.name, candidate.url, candidate.quality_hint)
