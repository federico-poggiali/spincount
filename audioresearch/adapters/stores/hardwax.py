"""Level 5: hardwax.com. Clips (about 90 s) labelled by position; no BPM on the site."""
from __future__ import annotations

from ...parsers import stores as p
from .base import StoreAdapter


class Hardwax(StoreAdapter):
    name = "hardwax"
    site = "hardwax"

    def parse(self, html):
        return p.parse_hardwax(html)

    def search_url(self, query: str) -> str:
        return f"{p.HARDWAX}/?find={self.quote(query).replace('+', '%20')}"
