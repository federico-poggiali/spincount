"""Level 5: Shopify record shops that put the sound clips on the product page: Runas Distribution and Orbit Wax.
Search page -> product links (at most MAX_RELEASES) -> product page -> clips by position. No BPM on either."""
from __future__ import annotations

from ...parsers import stores as p
from .base import MAX_RELEASES, StoreAdapter


class ShopifyStore(StoreAdapter):
    base = ""

    def search_url(self, query: str) -> str:
        return f"{self.base}/search?q={self.quote(query)}&type=product"

    def parse(self, html):
        return [r for r in (p.parse_shopify_product(self._page(u), u) for u in p.shopify_product_links(html, self.base)[:MAX_RELEASES]) if r]

    def _page(self, url: str) -> str:
        return self.http.get_text(url, site=self.site, adapter=self.name)


class RunasDistribution(ShopifyStore):
    name = site = "runas"
    base = "https://runasdistribution.com"


class OrbitWax(ShopifyStore):
    name = site = "orbitwax"
    base = "https://orbitwax.com"
