"""Data model (architecture sections 6 and 8) and the JSON output contract."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Quality(str, Enum):
    FULL = "full"
    PREVIEW = "preview"
    CLIP = "clip"

    @property
    def rank(self) -> int:
        return {"full": 3, "preview": 2, "clip": 1}[self.value]


class Status(str, Enum):
    FOUND = "found"
    REVIEW = "review"
    NOT_FOUND = "not_found"


@dataclass
class Reading:
    """A BPM or key a site shows. Kept apart from audio."""
    source: str
    bpm: Optional[float] = None
    key: Optional[str] = None

    def to_dict(self) -> dict:
        return {"source": self.source, "bpm": self.bpm, "key": self.key}

    @classmethod
    def from_dict(cls, d: dict) -> "Reading":
        return cls(d["source"], d.get("bpm"), d.get("key"))


@dataclass
class TrackRef:
    """A track of a Discogs release, or an entry in a candidate's tracklist."""
    position: str
    artist: str
    title: str
    duration: Optional[int] = None  # seconds
    url: Optional[str] = None       # candidate tracklists only: where this track can be fetched

    def to_dict(self) -> dict:
        d = {"position": self.position, "artist": self.artist, "title": self.title, "duration": self.duration}
        if self.url:
            d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TrackRef":
        return cls(d["position"], d.get("artist", ""), d["title"], d.get("duration"), d.get("url"))


@dataclass
class ReleaseIdentity:
    discogs_release_id: int
    artist: str
    title: str
    label: Optional[str]
    catno: Optional[str]
    year: Optional[int]
    tracks: list[TrackRef]
    videos: list[dict] = field(default_factory=list)
    cover: Optional[str] = None   # Discogs cover image, for the viewer

    def to_dict(self) -> dict:
        return {**{k: getattr(self, k) for k in ("discogs_release_id", "artist", "title", "label", "catno", "year", "videos", "cover")},
                "tracks": [t.to_dict() for t in self.tracks]}

    @classmethod
    def from_dict(cls, d: dict) -> "ReleaseIdentity":
        return cls(d["discogs_release_id"], d["artist"], d["title"], d.get("label"), d.get("catno"), d.get("year"),
                   [TrackRef.from_dict(t) for t in d["tracks"]], d.get("videos", []), d.get("cover"))

    def track(self, position: str) -> TrackRef:
        return next(t for t in self.tracks if t.position == position)


@dataclass
class Candidate:
    """Something an adapter found that might be a track or a release (metadata only)."""
    adapter: str
    level: int
    kind: str                      # "release" | "track"
    url: str
    title: str
    artist: str
    duration: Optional[int] = None
    tracklist: Optional[list[TrackRef]] = None   # for kind == "release"
    quality_hint: Quality = Quality.FULL
    readings: list[Reading] = field(default_factory=list)
    catno: Optional[str] = None
    position: Optional[str] = None  # track candidates: the Discogs position the adapter searched for
    extra: dict[str, Any] = field(default_factory=dict)

    def for_track(self, t: TrackRef, position: Optional[str] = None) -> "Candidate":
        """The track-kind candidate for one entry of this release candidate."""
        q = self.extra.get("track_quality", {}).get(t.url)
        return replace(self, kind="track", url=t.url or self.url, title=t.title, artist=t.artist or self.artist,
                       quality_hint=Quality(q) if q else self.quality_hint,
                       readings=[Reading.from_dict(r) for r in self.extra.get("track_readings", {}).get(t.url, [])] or self.readings,
                       duration=t.duration, tracklist=None, position=position or t.position,
                       extra={**self.extra, "release_url": self.url, "release_title": self.title})

    def to_dict(self) -> dict:
        return {"adapter": self.adapter, "level": self.level, "kind": self.kind, "url": self.url, "title": self.title,
                "artist": self.artist, "duration": self.duration, "quality_hint": self.quality_hint.value,
                "catno": self.catno, "position": self.position,
                "tracklist": [t.to_dict() for t in self.tracklist] if self.tracklist is not None else None,
                "readings": [r.to_dict() for r in self.readings], "extra": self.extra}

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(d["adapter"], d["level"], d["kind"], d["url"], d["title"], d["artist"], d.get("duration"),
                   [TrackRef.from_dict(t) for t in d["tracklist"]] if d.get("tracklist") is not None else None,
                   Quality(d.get("quality_hint", "full")), [Reading.from_dict(r) for r in d.get("readings", [])],
                   d.get("catno"), d.get("position"), d.get("extra") or {})


@dataclass
class FetchedAudio:
    path: Path
    adapter: str
    url: str
    quality: Quality
    duration: Optional[float] = None   # real length in seconds
    fingerprint: Optional[list[int]] = None


@dataclass
class TrackResult:
    position: str
    status: Status = Status.NOT_FOUND
    audio_path: Optional[str] = None
    source: Optional[str] = None
    level: Optional[int] = None
    url: Optional[str] = None
    quality: Optional[Quality] = None
    confidence: float = 0.0
    reason: str = ""
    readings: list[Reading] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)
    page: Optional[str] = None   # the release page the audio came from (a store's record page)

    def to_dict(self) -> dict:
        return {"position": self.position, "status": self.status.value, "audio_path": self.audio_path, "page": self.page,
                "source": self.source, "level": self.level, "url": self.url,
                "quality": self.quality.value if self.quality else None,
                "confidence": round(self.confidence, 3), "reason": self.reason,
                "readings": [r.to_dict() for r in self.readings], "alternatives": self.alternatives}

    @classmethod
    def from_dict(cls, d: dict) -> "TrackResult":
        return cls(d["position"], Status(d["status"]), d.get("audio_path"), d.get("source"), d.get("level"),
                   d.get("url"), Quality(d["quality"]) if d.get("quality") else None, d.get("confidence", 0.0),
                   d.get("reason", ""), [Reading.from_dict(r) for r in d.get("readings", [])],
                   d.get("alternatives", []), d.get("page"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ReleaseResult:
    discogs_release_id: int
    tracks: list[TrackResult]
    adapters_off: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {"discogs_release_id": self.discogs_release_id, "tracks": [t.to_dict() for t in self.tracks],
                "adapters_off": list(self.adapters_off), "generated_at": self.generated_at}

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "ReleaseResult":
        return cls(d["discogs_release_id"], [TrackResult.from_dict(t) for t in d["tracks"]],
                   d.get("adapters_off", []), d.get("generated_at", _now()))

    @classmethod
    def from_json(cls, text: str) -> "ReleaseResult":
        return cls.from_dict(json.loads(text))

    def track(self, position: str) -> TrackResult:
        return next(t for t in self.tracks if t.position == position)

    def counts(self) -> dict[str, int]:
        return {s.value: sum(1 for t in self.tracks if t.status == s) for s in Status}
