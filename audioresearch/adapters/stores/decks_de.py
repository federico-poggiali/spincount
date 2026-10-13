"""Level 5: decks.de. NOT AVAILABLE: the site is behind a Cloudflare challenge (HTTP 403 "Just a moment...",
real response in tests/fixtures/stores/). Off by default; the adapter stays so it can be enabled
(AUDIORESEARCH_ENABLE=decks_de) the day a search page can be read, and a parser added for it."""
from __future__ import annotations

from ...parsers import stores as p
from .base import StoreAdapter


class DecksDe(StoreAdapter):
    name = "decks_de"
    site = "decks_de"
    enabled_by_default = False

    def parse(self, html):
        raise p.StoreParseError("decks.de has no parser yet: the site could not be read")

    def search_url(self, query: str) -> str:
        return f"https://www.decks.de/decks.php?search={self.quote(query)}"
