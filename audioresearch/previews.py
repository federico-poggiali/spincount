"""Preview plan: which link each track plays in the viewer.

Every playable link of a track (the chosen one and its alternatives) belongs to a family: YouTube,
Bandcamp, SoundCloud, iTunes, one record store, your files. One record should sound like one source,
so families are picked greedily: the one covering the most tracks takes all of them, the next one
covers what is left, and so on. Your own files always go first. Inside a family a track plays its
best link (quality, then confidence).

Nothing is downloaded here: embeds use the official players, clips stream from where they live.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .models import Quality, ReleaseResult, Status

STORE_LEVEL = 5
DIRECT = {".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"}
_YT_ID = re.compile(r"^[\w-]{11}$")


def youtube_id(url: str) -> str | None:
    u = urlparse(url)
    if u.netloc.endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0]
    elif "youtube" in u.netloc:
        vid = parse_qs(u.query).get("v", [""])[0] or (u.path.split("/")[2] if u.path.startswith(("/embed/", "/shorts/")) else "")
    else:
        return None
    return vid if _YT_ID.match(vid) else None


def classify(source: str, url: str | None) -> tuple[str, str] | None:
    """-> (family, kind) or None when the link cannot be played in a browser.
    kind: youtube | bandcamp | soundcloud | audio (a plain file streamed by <audio>) | file (yours, served locally)."""
    if source == "local_files":
        return "your files", "file"
    if not url or not url.startswith(("http://", "https://")):
        return None
    host = urlparse(url).netloc.lower()
    if youtube_id(url):
        return "youtube", "youtube"
    if host.endswith("bandcamp.com") and "/track/" in url:
        return "bandcamp", "bandcamp"
    if host.endswith("soundcloud.com"):
        return "soundcloud", "soundcloud"
    if Path(urlparse(url).path).suffix.lower() in DIRECT or "audio-ssl.itunes" in host or "mzstatic" in host:
        return ("itunes" if source == "itunes" else source), "audio"
    return None


def _options(result: ReleaseResult) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for t in result.tracks:
        opts = []
        if t.status != Status.NOT_FOUND and t.source:
            opts.append({"source": t.source, "url": t.url, "quality": t.quality.value if t.quality else None,
                         "confidence": t.confidence, "review": t.status == Status.REVIEW})
        opts += [{"source": a["source"], "url": a.get("url"), "quality": a.get("quality"),
                  "confidence": a.get("confidence", 0.0), "review": False} for a in t.alternatives]
        playable = []
        for o in opts:
            if c := classify(o["source"], o["url"]):
                o["family"], o["kind"] = c
                if o["kind"] == "youtube":
                    o["embed_id"] = youtube_id(o["url"])
                playable.append(o)
        out[t.position] = playable
    return out


def store_pages(result: ReleaseResult) -> dict[str, list[dict]]:
    """position -> [{"source", "page"}]: record stores that have the track, for a "Find at" button."""
    out = {}
    for t in result.tracks:
        found = [(t.source, t.page, t.level)] if t.status != Status.NOT_FOUND else []
        found += [(a["source"], a.get("page"), a.get("level")) for a in t.alternatives]
        pages = {}
        for source, page, level in found:
            if level == STORE_LEVEL and page and page.startswith(("http://", "https://")):
                pages.setdefault(source, page)
        out[t.position] = [{"source": s, "page": u} for s, u in pages.items()]
    return out


def _rank(o: dict) -> tuple:
    return (Quality(o["quality"]).rank if o["quality"] else 0, o["confidence"])


def plan(result: ReleaseResult) -> dict:
    """-> {"tracks": {position: option | None}, "families": [{"family", "tracks": [positions]}],
           "stores": {position: [{"source", "page"}]}}"""
    options = _options(result)
    left = {p for p, o in options.items() if o}
    chosen: dict[str, dict] = {}
    families: list[dict] = []
    while left:
        cover: dict[str, list[str]] = {}
        for p in left:
            for f in {o["family"] for o in options[p]}:
                cover.setdefault(f, []).append(p)

        def score(f: str):
            best = [max((o for o in options[p] if o["family"] == f), key=_rank) for p in cover[f]]
            return (f == "your files", len(cover[f]), sum(_rank(o)[0] for o in best), sum(o["confidence"] for o in best))

        fam = max(cover, key=score)
        for p in cover[fam]:
            chosen[p] = max((o for o in options[p] if o["family"] == fam), key=_rank)
        order = [t.position for t in result.tracks]
        families.append({"family": fam, "tracks": sorted(cover[fam], key=order.index)})
        left -= set(cover[fam])
    return {"tracks": {t.position: chosen.get(t.position) for t in result.tracks}, "families": families,
            "stores": store_pages(result)}
