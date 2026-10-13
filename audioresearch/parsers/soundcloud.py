"""SoundCloud: the API client (through yt-dlp's own extractor, which finds and refreshes the
client_id) and the parsers for its api-v2 JSON. A site change is fixed here and nowhere else.

yt-dlp has no set search, so this calls the same search endpoints its `scsearch` uses, through the
extractor's `_call_api` (private, so pinned by tests on saved responses).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..adapters.base import AdapterError
from ..models import Quality

API_V2 = "https://api-v2.soundcloud.com/"


class SoundcloudError(AdapterError):
    pass


class SoundcloudApi:
    """`call(endpoint, **query) -> JSON`. Swap it for a fake in tests."""

    def __init__(self, throttle: Callable[[], None] | None = None):
        self._ie = None
        self._throttle = throttle

    def _extractor(self):
        if self._ie is None:
            import yt_dlp

            ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
            self._ie = ydl.get_info_extractor("SoundcloudSearch")
            self._ie.initialize()
        return self._ie

    def call(self, endpoint: str, **query: Any):
        from yt_dlp.utils import update_url_query

        if self._throttle:
            self._throttle()
        try:
            ie = self._extractor()
            return ie._call_api(update_url_query(API_V2 + endpoint, query), endpoint, "Downloading SoundCloud API",
                                "Unable to download SoundCloud API", headers=ie._HEADERS)
        except Exception as e:  # yt-dlp raises ExtractorError and friends
            raise SoundcloudError(f"SoundCloud API {endpoint}: {str(e).splitlines()[0][:200]}") from e


@dataclass
class SCTrack:
    id: int
    title: str
    artist: str            # the uploader's name
    url: str               # permalink
    duration: int | None   # FULL length in seconds (not the 30 s a snippet plays)
    quality: Quality
    blocked: bool = False
    policy: str = ""


@dataclass
class SCSet:
    id: int
    title: str
    artist: str
    url: str
    set_type: str | None
    track_ids: list[int] = field(default_factory=list)
    tracks: dict[int, SCTrack] = field(default_factory=dict)   # the ones the search already resolved


def parse_track(t: dict) -> SCTrack | None:
    """api-v2 track -> SCTrack; None for the half-filled stubs sets contain (id only)."""
    if not t.get("title") or not t.get("permalink_url"):
        return None
    policy = t.get("policy") or ""
    full = t.get("full_duration") or t.get("duration")
    return SCTrack(t["id"], t["title"].strip(), (t.get("user") or {}).get("username") or "", t["permalink_url"],
                   round(full / 1000) if full else None, Quality.PREVIEW if policy == "SNIP" else Quality.FULL,
                   policy == "BLOCK", policy)


def parse_tracks(payload: Any) -> list[SCTrack]:
    items = payload.get("collection") if isinstance(payload, dict) else payload
    if items is None:
        raise SoundcloudError("unexpected SoundCloud track response")
    return [t for x in items if (t := parse_track(x))]


def parse_sets(payload: Any) -> list[SCSet]:
    try:
        items = payload["collection"]
    except (KeyError, TypeError) as e:
        raise SoundcloudError("unexpected SoundCloud set response") from e
    out = []
    for p in items:
        if not p.get("permalink_url") or not p.get("title"):
            continue
        tracks = p.get("tracks") or []
        s = SCSet(p["id"], p["title"].strip(), (p.get("user") or {}).get("username") or "", p["permalink_url"], p.get("set_type"),
                  [t["id"] for t in tracks if t.get("id")])
        for t in tracks:
            if (tr := parse_track(t)):
                s.tracks[tr.id] = tr
        out.append(s)
    return out
