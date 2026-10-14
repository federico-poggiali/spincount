"""Level 5: redeyerecords.co.uk. One clip per side (about 1 to 2 minutes); when a side holds one track the clip is
that track. The search matches one field at a time, so artist and title are not combined: the catalogue number
goes to the catalogue search, the title alone to the artist/title search. No BPM on the site."""
from __future__ import annotations

import re

from ...models import ReleaseIdentity
from ...parsers import stores as p
from .base import StoreAdapter


class Redeye(StoreAdapter):
    name = "redeye"
    site = "redeye"

    def parse(self, html):
        return p.parse_redeye(html)

    def catno_query(self, catno: str) -> str:
        return "".join(catno.split())

    def queries(self, release: ReleaseIdentity) -> list[str]:
        qs = [self.catno_query(release.catno)] if release.catno else []
        qs.append(re.sub(r"[^\w\s]", "", release.title).strip() or release.title)
        return qs

    def search_url(self, query: str) -> str:
        # a catalogue number has no space and a digit; titles and track names are searched as artist/title
        kind = "CAT" if " " not in query and re.search(r"\d", query) and re.search(r"[A-Za-z]", query) else "Artist"
        return f"{p.REDEYE}/search/?searchType={kind}&keywords={self.quote(query)}"
