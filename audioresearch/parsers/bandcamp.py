"""Bandcamp parsers. A site change is fixed here and nowhere else.

Bandcamp's HTML search page sits behind a JavaScript client challenge, so searching uses the same
public JSON endpoint the site's own search box calls (`bcsearch_public_api`). Album and track pages
are plain HTML and carry the whole tracklist in a `data-tralbum` attribute (JSON) plus JSON-LD.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from ..adapters.base import AdapterError

SEARCH_URL = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"


class ParseError(AdapterError):
    """The page no longer looks the way this parser expects."""


@dataclass
class SearchHit:
    kind: str            # "album" | "track" | "band"
    title: str
    artist: str
    album: str | None
    url: str


@dataclass
class BCTrack:
    number: int
    title: str
    url: str
    duration: int | None
    streamable: bool


@dataclass
class BCPage:
    kind: str            # "album" | "track"
    url: str
    title: str
    artist: str
    catno: str | None
    tracks: list[BCTrack] = field(default_factory=list)


def search_payload(text: str, kind: str) -> dict:
    """kind: "a" albums, "t" tracks."""
    return {"search_text": text, "search_filter": kind, "full_page": True, "fan_id": None}


def parse_search(payload: dict) -> list[SearchHit]:
    try:
        results = payload["auto"]["results"]
    except (KeyError, TypeError) as e:
        raise ParseError("unexpected Bandcamp search response") from e
    kinds = {"a": "album", "t": "track", "b": "band"}
    return [SearchHit(kinds[r["type"]], r.get("name") or "", r.get("band_name") or "", r.get("album_name"),
                      r.get("item_url_path") or "") for r in results if r.get("type") in kinds and r.get("item_url_path")]


def _find_catno(node) -> str | None:
    if isinstance(node, dict):
        if node.get("catalogNumber"):
            return str(node["catalogNumber"]).strip()
        return next((c for v in node.values() if (c := _find_catno(v))), None)
    if isinstance(node, list):
        return next((c for v in node if (c := _find_catno(v))), None)
    return None


def parse_page(page: str, url: str) -> BCPage:
    m = re.search(r'data-tralbum="([^"]*)"', page)
    if not m:
        raise ParseError(f"no data-tralbum on {url}")
    try:
        tr = json.loads(htmllib.unescape(m.group(1)))
        info = tr["trackinfo"]
    except (ValueError, KeyError) as e:
        raise ParseError(f"unreadable data-tralbum on {url}") from e
    ld = {}
    lm = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    if lm:
        try:
            ld = json.loads(lm.group(1))
        except ValueError:
            pass
    kind = "album" if tr.get("item_type") == "album" else "track"
    title = ld.get("name") or (tr.get("current") or {}).get("title") or ""
    artist = tr.get("artist") or (ld.get("byArtist") or {}).get("name") or ""
    tracks = []
    for i, t in enumerate(info, 1):
        link = t.get("title_link") or ""
        dur = t.get("duration")
        tracks.append(BCTrack(t.get("track_num") or i, (t.get("title") or "").strip(), urljoin(url, link) if link else url,
                              round(dur) if dur else None, bool(t.get("file")) and t.get("streaming", 1) != 0))
    if not tracks:
        raise ParseError(f"no tracks on {url}")
    return BCPage(kind, url, title, artist, _find_catno(ld), tracks)


def parse_item_id(page: str) -> tuple[str, int] | None:
    """-> ("track"|"album", numeric id) from a page's data-tralbum; the official embed player needs it."""
    m = re.search(r'data-tralbum="([^"]*)"', page)
    try:
        tr = json.loads(htmllib.unescape(m.group(1))) if m else {}
    except ValueError:
        return None
    if not isinstance(tr.get("id"), int):
        return None
    return ("album" if tr.get("item_type") == "album" else "track"), tr["id"]
