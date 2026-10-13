"""Stage 1: Discogs URL or id -> ReleaseIdentity. Reuses bpmkey.discogs."""
from __future__ import annotations

import re
from typing import Protocol

from bpmkey import discogs

from .models import ReleaseIdentity, TrackRef


class DiscogsLike(Protocol):
    def resolve(self, url: str) -> int: ...
    def release(self, release_id: int) -> dict: ...


def to_url(url_or_id: str | int) -> str:
    s = str(url_or_id).strip()
    return f"https://www.discogs.com/release/{s}" if re.fullmatch(r"\d+", s) else s


def identity_from_release(data: dict, release_id: int) -> ReleaseIdentity:
    labels = data.get("labels") or []
    first = labels[0] if labels else {}
    catno = (first.get("catno") or "").strip()
    return ReleaseIdentity(
        discogs_release_id=release_id,
        artist=discogs._join_artists(data.get("artists", [])),
        title=(data.get("title") or "").strip(),
        label=discogs._clean_artist(first["name"]) if first.get("name") else None,
        catno=catno if catno and catno.lower() != "none" else None,
        year=data.get("year") or None,
        tracks=[TrackRef(t.position, t.artist, t.title, t.duration)
                for t in discogs.parse_tracklist(data, release_id)],
        videos=list(data.get("videos") or []),
    )


def identify(url_or_id: str | int, client: DiscogsLike | None = None) -> ReleaseIdentity:
    """Master URLs resolve to the main release."""
    client = client or discogs.DiscogsClient()
    rid = client.resolve(to_url(url_or_id))
    return identity_from_release(client.release(rid), rid)
