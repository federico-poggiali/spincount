"""Record-store parsers: one function per site, all returning the same StoreRelease. A site change is
fixed in that site's function and nowhere else."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..adapters.base import AdapterError, AdapterUnavailable


class StoreBlocked(AdapterUnavailable):
    pass


class StoreParseError(AdapterError):
    pass


@dataclass
class StoreTrack:
    position: str
    title: str
    clip_url: str
    letter: str | None = None     # deejay.de: the suffix of the clip and BPM requests


@dataclass
class StoreRelease:
    id: str
    url: str
    artist: str
    title: str
    catno: str | None
    label: str | None
    tracks: list[StoreTrack] = field(default_factory=list)


def check_challenge(status: int, text: str, site: str) -> None:
    if status == 403 and ("Just a moment" in text or "cf-chl" in text):
        raise StoreBlocked(f"{site} is behind a Cloudflare challenge")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


# ---- deejay.de -------------------------------------------------------------------------------------------
DEEJAY = "https://www.deejay.de"


def deejay_clip_url(article_id: str, letter: str) -> str:
    """Rebuilt from the site's player script: /streamit/<2nd-last digit>/<last digit>/<id><letter>.mp3"""
    return f"{DEEJAY}/streamit/{article_id[-2]}/{article_id[-1]}/{article_id}{letter}.mp3"


def deejay_bpm_url(article_id: str, letter: str) -> str:
    return f"{DEEJAY}/ajaxHelper/getBPM.php?a={article_id}{letter}"


def parse_bpm(text: str) -> float | None:
    m = re.fullmatch(r"\s*(\d{2,3}(?:[.,]\d+)?)\s*", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def parse_deejay(html: str) -> list[StoreRelease]:
    out = []
    for art in _soup(html).select("article.product"):
        aid = (art.get("id") or "")[1:]
        title_a = art.select_one("h3.title a")
        if not aid.isdigit() or title_a is None:
            raise StoreParseError("deejay.de: product without id or title")
        tracks = []
        for a in art.select("ul.playtrack a.track"):
            m = re.fullmatch(r"playTrack_(\d+)_([a-z]+)", a.get("id") or "")
            if m:
                tracks.append(StoreTrack(_text(a.select_one(".track-pos")), _text(a.select_one(".track-title")),
                                         deejay_clip_url(aid, m.group(2)), m.group(2)))
        label = art.select_one(".musiclabel a")
        out.append(StoreRelease(aid, urljoin(DEEJAY, title_a.get("href", "")), ", ".join(_text(a) for a in art.select("h2.artist a")),
                                _text(title_a), _text(art.select_one(".musiclabel strong")) or None, _text(label) or None, tracks))
    return out


# ---- hardwax.com -----------------------------------------------------------------------------------------
HARDWAX = "https://hardwax.com"


def parse_hardwax(html: str) -> list[StoreRelease]:
    out = []
    for rec in _soup(html).select('div[id^="record-"]'):
        rid = rec["id"].split("-", 1)[1]
        path = f"/{rid}/"
        h2 = rec.find("h2")
        if h2 is None:
            raise StoreParseError("hardwax: record without a heading")
        artists = [_text(a).rstrip(":") for a in h2.select('a[href^="/act/"]')]
        title_span = h2.select("span > span")
        title = _text(title_span[-1]) if title_span else ""
        # the catalogue number is the text of the record link that sits next to the label link
        catno = next((_text(a) for a in rec.select(f'a[href^="{path}"]') if _text(a) and a.find_parent("h2") is None), None)
        label = rec.select_one('a[href^="/label/"]')
        tracks = []
        for li in rec.select('li[id^="track-"]'):
            a = li.select_one('a[href$=".mp3"]')
            m = re.fullmatch(rf"track-{rid}_(.+)", li.get("id", ""))
            if a and m:
                tracks.append(StoreTrack(m.group(1), _text(a).strip(), a["href"]))
        out.append(StoreRelease(rid, urljoin(HARDWAX, rec.select_one(f'a[href^="{path}"]')["href"] if rec.select_one(f'a[href^="{path}"]') else path),
                                ", ".join(artists), title, catno, _text(label) or None, tracks))
    return out
