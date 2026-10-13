"""Beatport parsers.

STATUS: beatport.com sits behind a Cloudflare managed challenge ("Just a moment..."): plain HTTP and
headless or headed Chromium all get HTTP 403 (real response saved in tests/fixtures/beatport/). Its
v4 API answers 401 without a partner/user OAuth token. So no real page or API response could be saved,
and the JSON shape below (tracks and releases lists under "results") is written from Beatport's public
API documentation and is UNVERIFIED. The adapters need BEATPORT_TOKEN and are off without it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..adapters.base import AdapterError, AdapterUnavailable

API = "https://api.beatport.com/v4/catalog/"


class BeatportBlocked(AdapterUnavailable):
    pass


class BeatportParseError(AdapterError):
    pass


def check_response(status: int, text: str = "") -> None:
    """Raise BeatportBlocked for the Cloudflare challenge or a missing/expired token."""
    if status == 403 and ("Just a moment" in text or "cf-chl" in text or "challenge" in text.lower()):
        raise BeatportBlocked("beatport.com is behind a Cloudflare challenge")
    if status in (401, 403):
        raise BeatportBlocked(f"Beatport API refused the request (HTTP {status}): BEATPORT_TOKEN missing or expired")


@dataclass
class BPTrack:
    id: int
    name: str
    mix_name: str
    artists: str
    release_id: int | None
    release_name: str
    length: int | None          # seconds, the full track
    bpm: float | None
    key: str | None
    sample_url: str | None      # the preview excerpt
    catno: str | None = None
    label: str | None = None

    @property
    def title(self) -> str:
        """'The Bells (Original Mix)': the mix name feeds the version check."""
        return f"{self.name} ({self.mix_name})" if self.mix_name else self.name


@dataclass
class BPRelease:
    id: int
    name: str
    artists: str
    catno: str | None
    label: str | None
    track_count: int | None


def _artists(items: Any) -> str:
    return ", ".join(a.get("name", "") for a in items or [] if a.get("name"))


def parse_track(t: dict) -> BPTrack:
    try:
        rel = t.get("release") or {}
        length = t.get("length_ms")
        key = (t.get("key") or {}).get("name") if isinstance(t.get("key"), dict) else t.get("key")
        return BPTrack(int(t["id"]), t["name"].strip(), (t.get("mix_name") or "").strip(), _artists(t.get("artists")),
                       rel.get("id"), rel.get("name") or "", round(length / 1000) if length else None,
                       float(t["bpm"]) if t.get("bpm") else None, key, t.get("sample_url"),
                       t.get("catalog_number") or rel.get("catalog_number"), (t.get("label") or {}).get("name"))
    except (KeyError, TypeError, ValueError) as e:
        raise BeatportParseError(f"unexpected Beatport track: {e}") from e


def parse_tracks(payload: Any) -> list[BPTrack]:
    if not isinstance(payload, dict) or "results" not in payload:
        raise BeatportParseError("unexpected Beatport tracks response")
    return [parse_track(t) for t in payload["results"]]


def parse_releases(payload: Any) -> list[BPRelease]:
    if not isinstance(payload, dict) or "results" not in payload:
        raise BeatportParseError("unexpected Beatport releases response")
    try:
        return [BPRelease(int(r["id"]), r["name"].strip(), _artists(r.get("artists")), r.get("catalog_number"),
                          (r.get("label") or {}).get("name"), r.get("track_count")) for r in payload["results"]]
    except (KeyError, TypeError, ValueError) as e:
        raise BeatportParseError(f"unexpected Beatport release: {e}") from e
