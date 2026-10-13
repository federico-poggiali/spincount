"""Level 4: Beatport (two routes in parallel: `beatport_tracks`, `beatport_releases`).

Beatport only plays excerpts (quality `preview`, about 2 minutes, measured on fetch). Its BPM and key
are kept as `Reading`s (source "beatport"), separate from the audio. Needs BEATPORT_TOKEN, see
parsers/beatport.py for why."""
from __future__ import annotations

from pathlib import Path

from .. import config, fetch, http as http_mod
from ..models import Candidate, FetchedAudio, Quality, Reading, ReleaseIdentity, TrackRef
from ..parsers import beatport as bp
from .base import Adapter, AdapterUnavailable
from .common import search_artist, search_title

PER_PAGE = 25
MAX_RELEASES = 5


class _BeatportBase(Adapter):
    level = 4
    max_quality = Quality.PREVIEW

    def __init__(self, http=None, token: str | None = None):
        self._http = http
        self._token = token

    @property
    def http(self):
        return self._http or http_mod.shared()

    @property
    def token(self) -> str:
        return self._token if self._token is not None else config.BEATPORT_TOKEN

    def _get(self, path: str, **params):
        if not self.token:
            raise AdapterUnavailable("Beatport needs BEATPORT_TOKEN (beatport.com is behind a Cloudflare challenge, the API needs a token)")
        try:
            r = self.http.get(bp.API + path, site="beatport", adapter=self.name, params=params,
                              headers={"Authorization": f"Bearer {self.token}"})
        except http_mod.HttpError as e:
            if e.status in (401, 403):
                bp.check_response(e.status)
            raise
        return r.json()

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.http_download(candidate.url, dest, site="beatport", adapter=self.name, http=self.http)
        return FetchedAudio(path, self.name, candidate.url, Quality.PREVIEW)


def _reading(t: bp.BPTrack) -> list[Reading]:
    return [Reading("beatport", t.bpm, t.key)] if t.bpm or t.key else []


class BeatportTracks(_BeatportBase):
    name = "beatport_tracks"

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        out = []
        for t in tracks:
            query = f"{search_artist(t.artist)} {search_title(t.title)}".strip()
            for r in bp.parse_tracks(self._get("tracks/", q=query, per_page=PER_PAGE)):
                if not r.sample_url:
                    continue
                out.append(Candidate(self.name, self.level, "track", r.sample_url, r.title, r.artists, r.length,
                                     quality_hint=Quality.PREVIEW, readings=_reading(r), catno=r.catno, position=t.position,
                                     extra={"release": r.release_name, "beatport_id": r.id}))
        return out


class BeatportReleases(_BeatportBase):
    name = "beatport_releases"

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        queries = ([release.catno] if release.catno else []) + [f"{search_artist(release.artist)} {release.title}".strip()]
        seen: dict[int, bp.BPRelease] = {}
        for q in queries:                                  # catalogue number first, then the title
            for r in bp.parse_releases(self._get("releases/", q=q, per_page=MAX_RELEASES)):
                seen.setdefault(r.id, r)
        out = []
        for r in list(seen.values())[:MAX_RELEASES]:
            bt = [t for t in bp.parse_tracks(self._get(f"releases/{r.id}/tracks/", per_page=100))]
            page = f"https://www.beatport.com/release/{r.id}"
            urls = [t.sample_url or f"{page}#no-sample-{i}" for i, t in enumerate(bt, 1)]   # no excerpt: listed, not fetchable
            out.append(Candidate(self.name, self.level, "release", page, r.name, r.artists,
                                 tracklist=[TrackRef(str(i), t.artists, t.title, t.length, u) for i, (t, u) in enumerate(zip(bt, urls), 1)],
                                 quality_hint=Quality.PREVIEW, catno=r.catno,
                                 extra={"unavailable": [u for t, u in zip(bt, urls) if not t.sample_url],
                                        "track_readings": {u: [x.to_dict() for x in _reading(t)] for t, u in zip(bt, urls)}}))
        return out
