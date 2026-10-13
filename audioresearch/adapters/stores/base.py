"""Shared plumbing of the record-store adapters: search by catalogue number first, then artist and
title; a store release becomes a release candidate whose tracks are the store's clips, labelled by
position (A1, B1). At least 2 s between requests (config.site_delay)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus

from ... import fetch, http as http_mod
from ...matcher import catno_score
from ...models import Candidate, FetchedAudio, Quality, Reading, ReleaseIdentity, TrackRef
from ...parsers.stores import StoreBlocked, StoreRelease, check_challenge
from ..base import Adapter
from ..common import search_artist, search_title

log = logging.getLogger(__name__)
MAX_RELEASES = 3
MAX_TRACK_QUERIES = 5


class StoreAdapter(Adapter):
    level = 5
    max_quality = Quality.PREVIEW        # clips of 60 s or more measure as preview, shorter ones as clip
    site: str = ""
    parse: Callable[[str], list[StoreRelease]]

    def __init__(self, http=None):
        self._http = http

    @property
    def http(self):
        return self._http or http_mod.shared()

    # ---- to override ---------------------------------------------------------------------------
    def search_url(self, query: str) -> str:
        raise NotImplementedError

    def readings(self, rel: StoreRelease) -> dict[str, list[Reading]]:
        """clip url -> readings the store shows (BPM); none by default."""
        return {}

    # ---- shared --------------------------------------------------------------------------------
    def get_releases(self, query: str) -> list[StoreRelease]:
        try:
            html = self.http.get_text(self.search_url(query), site=self.site, adapter=self.name)
        except http_mod.HttpError as e:
            if e.status == 403:
                raise StoreBlocked(f"{self.site}: HTTP 403 (blocked)") from e
            raise
        check_challenge(200, "", self.site)
        return self.parse(html)

    def catno_query(self, catno: str) -> str:
        return catno

    def queries(self, release: ReleaseIdentity) -> list[str]:
        qs = [self.catno_query(release.catno)] if release.catno else []
        if not release.artist.lower().startswith("various"):
            qs.append(f"{release.artist} {release.title}")
        else:
            qs.append(release.title)
        return qs

    def find(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[StoreRelease]:
        found: dict[str, StoreRelease] = {}
        for i, q in enumerate(self.queries(release)):
            new = self.get_releases(q)
            for r in new:
                found.setdefault(r.id, r)
            if i == 0 and release.catno and any((catno_score(release.catno, r.catno) or 0) >= 0.9 for r in new):
                break                                  # a catalogue number hit is conclusive
        if not found:                                  # compilations, odd titles: one query per track
            for t in tracks[:MAX_TRACK_QUERIES]:
                for r in self.get_releases(f"{search_artist(t.artist)} {search_title(t.title)}".strip()):
                    found.setdefault(r.id, r)
        return list(found.values())[:MAX_RELEASES]

    def candidate(self, release: ReleaseIdentity, r: StoreRelease) -> Candidate:
        readings = self.readings(r) if self.relevant(release, r) else {}
        return Candidate(self.name, self.level, "release", r.url, r.title, r.artist, quality_hint=Quality.CLIP, catno=r.catno,
                         tracklist=[TrackRef(t.position, r.artist, t.title, None, t.clip_url) for t in r.tracks],
                         extra={"label": r.label, "track_readings": {u: [x.to_dict() for x in rs] for u, rs in readings.items()}})

    def relevant(self, release: ReleaseIdentity, r: StoreRelease) -> bool:
        """Cheap filter before spending requests on extras (BPM): same catalogue number or a similar title."""
        from bpmkey.matching import similarity

        return (catno_score(release.catno, r.catno) or 0) >= 0.9 or similarity(release.title, r.title) >= 0.6

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        return [self.candidate(release, r) for r in self.find(release, tracks) if r.tracks]

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.http_download(candidate.url, dest, site=self.site, adapter=self.name, http=self.http)
        return FetchedAudio(path, self.name, candidate.url, Quality.CLIP)

    @staticmethod
    def quote(query: str) -> str:
        return quote_plus(query)
