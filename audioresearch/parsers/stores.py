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


# ---- redeyerecords.co.uk ---------------------------------------------------------------------------------
REDEYE = "https://www.redeyerecords.co.uk"
REDEYE_CLIPS = "https://sounds.redeyerecords.co.uk"


def redeye_clip_url(release_id: str, side: str) -> str:
    """From the site's player script: <id>.mp3 for side a, <id><side>.mp3 for the others (one clip per side)."""
    return f"{REDEYE_CLIPS}/{release_id}{'' if side == 'a' else side}.mp3"


def parse_redeye(html: str) -> list[StoreRelease]:
    out = []
    for g in _soup(html).select("div.releaseGrid"):
        rid = g.get("id") or ""
        link = g.select_one("a.link")
        listing = g.select_one(".listing")
        if not rid.isdigit() or link is None or listing is None:
            raise StoreParseError("redeye: release without id, link or listing")
        heading = _text(listing.select_one("p.artist"))
        artist, _, title = heading.partition(" - ")
        if not title:
            artist, title = "", heading
        names = [n.strip() for n in _text(listing.select_one("p.tracks")).split(" / ") if n.strip()]
        sides = [b["data-sample"] for b in g.select("a.btn-play[data-sample]")]
        if sides and len(sides) == len(names):         # one track per side: the clip is that track
            tracks = [StoreTrack(f"{s.upper()}1", n, redeye_clip_url(rid, s)) for s, n in zip(sides, names)]
        else:                                          # clips are whole sides: the title is the side's content, unknown
            tracks = [StoreTrack(s.upper(), f"Side {s.upper()}", redeye_clip_url(rid, s)) for s in sides]
        label_p = listing.select_one("p.label")
        catno = next(iter(label_p.stripped_strings), None) if label_p else None
        label = _text(label_p.select_one("a")) if label_p else ""
        out.append(StoreRelease(rid, urljoin(REDEYE, link.get("href", "")), artist.title() if artist.isupper() else artist,
                                title.title() if title.isupper() else title, catno, label or None, tracks))
    return out


# ---- Shopify stores with audio on the product page (Runas Distribution, Orbit Wax) ------------------------
def shopify_product_links(html: str, base: str) -> list[str]:
    seen: dict[str, None] = {}
    for a in _soup(html).select('a[href^="/products/"]'):
        seen.setdefault(urljoin(base, a["href"].split("?")[0]), None)
    return list(seen)


_MP3 = re.compile(r"https:[^\"'\s<>]+?\.mp3[^\"'\s<>]*")
_POS_NAME = re.compile(r"^\s*([A-Za-z]{1,2}\d{0,2})\s*[.:_\- ]+\s*(.+)$")


def _split_pos(text: str) -> tuple[str, str]:
    m = _POS_NAME.match(text)
    return (m.group(1).upper(), m.group(2).strip()) if m else ("", text.strip())


def parse_shopify_product(html: str, url: str) -> StoreRelease | None:
    """Tracks come from the audio player: the Audioly app (data-track-title / data-track-url) or a list of mp3 files
    named '<position>_<title>.mp3' in the page script. None when the page has no audio."""
    soup = _soup(html)
    og = soup.select_one('meta[property="og:title"]')
    heading = " ".join((og.get("content") if og else _text(soup.title)).split())
    catno_in_title = re.search(r"\[([^\]]+)\]\s*$", heading)
    heading = re.sub(r"\s*\[[^\]]+\]\s*$", "", heading)
    artist, _, title = heading.partition(" - ")
    if not title:
        artist, title = "", heading
    tracks = []
    for el in soup.find_all("audioly-track"):
        pos, name = _split_pos(el.get("data-track-title", ""))
        if el.get("data-track-url") and name:
            tracks.append(StoreTrack(pos or f"T{len(tracks) + 1}", name, el["data-track-url"]))
    if not tracks:
        seen: dict[str, None] = {}
        for u in _MP3.findall(html.replace("\\/", "/")):
            if "cdn.shopify.com" in u:
                seen.setdefault(u, None)
        for u in seen:
            fname = re.sub(r"\.mp3.*$", "", u.rsplit("/", 1)[-1])
            fname = re.sub(r"[_\s-]*snippet\s*$", "", fname.replace("%20", " "), flags=re.I)
            pos, name = _split_pos(re.sub(r"\s*-\s*", " - ", fname.replace("_-_", " - ")).replace("_", " "))
            tracks.append(StoreTrack(pos or f"T{len(tracks) + 1}", name, u))
    if not tracks:
        return None
    for s in soup(["script", "style"]):
        s.decompose()
    text = " ".join(soup.get_text(" ").split())
    m = re.search(r"Label:\s*(.+?)\s*Cat\.? ?No\.?:\s*([A-Za-z0-9][A-Za-z0-9 ./-]*?)\s*(?=Format|Release|Country|$)", text)
    catno = m.group(2).strip() if m else (catno_in_title.group(1) if catno_in_title else None)
    return StoreRelease(url.rstrip("/").rsplit("/", 1)[-1], url, artist, title, catno, m.group(1).strip() if m else None, tracks)


# ---- shops built on the same storefront (soundmetaphors.com, one-eye-witness.com, smallblackdots.net) ----
def eshop_release_urls(sitemap: str) -> list[str]:
    return re.findall(r"<loc>([^<]*/release/\d+/[^<]*)</loc>", sitemap)


_SNIPPET = re.compile(r"https://[^\"'\\\s]*audio-snippets[^\"'\\\s]*?/(\d+)/([A-Za-z0-9]+)\.mp3[^\"'\\\s]*")


def parse_eshop_release(html: str, url: str) -> StoreRelease | None:
    """The page is 'Artist - Title | Label (CATNO)'; the track rows give position and title, and the snippets
    (one number per release, <number>/<position>.mp3) are in the page data."""
    soup = _soup(html)
    og = soup.select_one('meta[property="og:title"]')
    heading = " ".join((og.get("content") if og else _text(soup.title)).split())
    main, _, tail = heading.partition(" | ")
    m = re.match(r"(.*?)\s*\(([^()]+)\)\s*$", tail)
    label, catno = (m.group(1), m.group(2)) if m else (tail or None, None)
    artist, _, title = main.partition(" - ")
    if not title:
        artist, title = "", main
    rows = [(r.get("data-track-position", ""), _text(r.select_one(".description"))) for r in soup.select('[data-testid="release-track-row"]')]
    by_release: dict[str, dict[str, str]] = {}
    for m2 in _SNIPPET.finditer(html):
        by_release.setdefault(m2.group(1), {}).setdefault(m2.group(2), m2.group(0).replace("\\u0026", "&"))
    wanted = {pos for pos, _ in rows}
    best = max(by_release.values(), key=lambda d: len(wanted & d.keys()), default={})
    tracks = [StoreTrack(pos, name, best[pos]) for pos, name in rows if pos in best and name]
    if not tracks:
        return None
    return StoreRelease(url.rstrip("/").split("/release/")[1].split("/")[0], url, artist, title, catno, label or None, tracks)
