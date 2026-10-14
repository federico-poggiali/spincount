"""Level 5: label shops on one storefront (soundmetaphors.com, one-eye-witness.com, smallblackdots.net). Their search
is not reachable without a browser, so the shop's sitemap (every release URL, 'Artist-Title' in the slug) is read once and
ranked against the query; the best pages give the clips (one per track, by position). No BPM on these sites."""
from __future__ import annotations

import re
from urllib.parse import unquote

from ...models import ReleaseIdentity
from ...parsers import stores as p
from ..common import search_artist, search_title
from .base import MAX_RELEASES, StoreAdapter

MIN_COVERAGE = 0.7          # share of the query words that must be in the slug


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


class EshopStore(StoreAdapter):
    base = ""

    def __init__(self, http=None):
        super().__init__(http)
        self._urls: list[str] | None = None

    def queries(self, release: ReleaseIdentity) -> list[str]:
        artist = "" if release.artist.lower().startswith("various") else search_artist(release.artist)
        return [f"{artist} {search_title(release.title)}".strip()]

    def search_url(self, query: str) -> str:
        return f"{self.base}/sitemap.xml"

    def release_urls(self) -> list[str]:
        if self._urls is None:
            self._urls = p.eshop_release_urls(self.http.get_text(self.search_url(""), site=self.site, adapter=self.name))
        return self._urls

    def parse(self, html):          # not used: get_releases reads the sitemap and the pages itself
        raise NotImplementedError

    def get_releases(self, query: str):
        want = set(_words(query))
        if len(want) < 2:
            return []
        scored = []
        for u in self.release_urls():
            words = _words(unquote(u.rsplit("/", 1)[-1]))
            flat = "".join(words)               # 'Spule/Zwei' is 'spulezwei' in the slug
            hits = sum(1 for w in want if w in words or (len(w) >= 4 and w in flat))
            if (cov := hits / len(want)) >= MIN_COVERAGE:
                scored.append((cov, -len(words), u))
        scored.sort(reverse=True)
        out = []
        for _, _, u in scored[:MAX_RELEASES]:
            r = p.parse_eshop_release(self.http.get_text(u, site=self.site, adapter=self.name), u)
            if r:
                out.append(r)
        return out


class SoundMetaphors(EshopStore):
    name = site = "soundmetaphors"
    base = "https://www.soundmetaphors.com"


class OneEyeWitness(EshopStore):
    name = site = "one_eye_witness"
    base = "https://www.one-eye-witness.com"


class SmallBlackDots(EshopStore):
    name = site = "smallblackdots"
    base = "https://www.smallblackdots.net"
