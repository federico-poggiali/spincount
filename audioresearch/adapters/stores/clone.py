"""Level 5: clone.nl. NOT AVAILABLE: its search (https://clone.nl/all/search?query=...) is behind a
Cloudflare challenge (HTTP 403, real response in tests/fixtures/stores/). Off by default, like decks_de."""
from __future__ import annotations

from ...parsers import stores as p
from .base import StoreAdapter


class Clone(StoreAdapter):
    name = "clone"
    site = "clone"
    enabled_by_default = False

    def parse(self, html):
        raise p.StoreParseError("clone.nl has no parser yet: the site could not be read")

    def search_url(self, query: str) -> str:
        return f"https://clone.nl/all/search?query={self.quote(query)}"
