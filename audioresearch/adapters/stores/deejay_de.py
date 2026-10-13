"""Level 5: deejay.de. Clips (about 2.5 minutes) per position plus the store's BPM for each track."""
from __future__ import annotations

from ...models import Reading
from ...parsers import stores as p
from .base import StoreAdapter


class DeejayDe(StoreAdapter):
    name = "deejay_de"
    site = "deejay_de"

    def parse(self, html):
        return p.parse_deejay(html)

    def catno_query(self, catno: str) -> str:
        return "".join(catno.split())    # the store only finds 'AX084DC', not 'AX 084 DC'

    def search_url(self, query: str) -> str:
        return f"{p.DEEJAY}/{self.quote(query)}"

    def readings(self, rel):
        """The BPM is not on the page: the store's player asks /ajaxHelper/getBPM.php per track."""
        out = {}
        for t in rel.tracks:
            if not t.letter:
                continue
            text = self.http.get_text(p.deejay_bpm_url(rel.id, t.letter), site=self.site, adapter=self.name)
            if (bpm := p.parse_bpm(text)) is not None:
                out[t.clip_url] = [Reading(self.name, bpm, None)]
        return out
