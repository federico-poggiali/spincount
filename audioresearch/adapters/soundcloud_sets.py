"""Level 3, route 3b: SoundCloud sets (albums, playlists) by artist and release title. A set candidate
carries its tracklist, so it is matched like a Bandcamp album."""
from __future__ import annotations

from pathlib import Path

from .. import fetch, http as http_mod
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from ..parsers import soundcloud as sc
from .base import Adapter

MAX_SETS = 5
MAX_SET_TRACKS = 60


class SoundCloudSets(Adapter):
    name = "soundcloud_sets"
    level = 3

    def __init__(self, api: sc.SoundcloudApi | None = None):
        self.api = api or sc.SoundcloudApi(lambda: http_mod.shared().throttle("soundcloud"))

    def _resolve(self, s: sc.SCSet) -> list[sc.SCTrack]:
        """The set's tracks in set order; the search only resolves the first few."""
        known = dict(s.tracks)
        todo = [i for i in s.track_ids[:MAX_SET_TRACKS] if i not in known]
        for i in range(0, len(todo), 50):
            for t in sc.parse_tracks(self.api.call("tracks", ids=",".join(map(str, todo[i:i + 50])))):
                known[t.id] = t
        return [known[i] for i in s.track_ids[:MAX_SET_TRACKS] if i in known]

    def set_candidate(self, s: sc.SCSet) -> Candidate:
        tracks = self._resolve(s)
        return Candidate(self.name, self.level, "release", s.url, s.title, s.artist, quality_hint=Quality.FULL,
                         tracklist=[TrackRef(str(i), t.artist, t.title, t.duration, t.url) for i, t in enumerate(tracks, 1)],
                         extra={"set_type": s.set_type, "unavailable": [t.url for t in tracks if t.blocked],
                                "track_quality": {t.url: t.quality.value for t in tracks}})

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        query = f"{'' if release.artist.lower().startswith('various') else release.artist} {release.title}".strip()
        sets: list[sc.SCSet] = []
        for endpoint in ("search/albums", "search/playlists_without_albums"):   # albums first
            sets += sc.parse_sets(self.api.call(endpoint, q=query, limit=MAX_SETS))
        return [self.set_candidate(s) for s in sets[:MAX_SETS] if s.track_ids]

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.ytdlp_download(candidate.url, dest, throttle=lambda: http_mod.shared().throttle("soundcloud"))
        return FetchedAudio(path, self.name, candidate.url, candidate.quality_hint)
