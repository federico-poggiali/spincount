"""Level 1, route 1b: the YouTube videos linked on the Discogs release itself."""
from __future__ import annotations

from pathlib import Path

from .. import fetch, http
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from .base import Adapter


class DiscogsYouTube(Adapter):
    name = "discogs_youtube"
    level = 1
    group = "youtube"          # youtube_music follows in this group, for tracks no video matched

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        """One track candidate per linked video; the shared matcher pairs them with tracks."""
        out = []
        for v in release.videos:
            uri = v.get("uri") or v.get("url")
            if not uri or "youtu" not in uri:
                continue
            out.append(Candidate(self.name, self.level, "track", uri, (v.get("title") or "").strip(), "",
                                 v.get("duration") or None, quality_hint=Quality.FULL,
                                 extra={"description": (v.get("description") or "")[:200]}))
        return out

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        path = fetch.ytdlp_download(candidate.url, dest, throttle=lambda: http.shared().throttle("youtube"))
        return FetchedAudio(path, self.name, candidate.url, Quality.FULL)
