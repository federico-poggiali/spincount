import html as htmllib
import json
import re
from pathlib import Path

import pytest

from audioresearch.adapters.bandcamp import Bandcamp, BandcampTracks
from audioresearch.matcher import match_candidates
from audioresearch.models import Quality, ReleaseIdentity, TrackRef
from audioresearch.parsers import bandcamp as bc

FIX = Path(__file__).parent / "fixtures" / "bandcamp"
BOC = "https://boardsofcanada.bandcamp.com/album/music-has-the-right-to-children"
GHYS = "https://florentghys.bandcamp.com/album/selected-ambient-works"
WULFEN = "https://mihalywulfen.bandcamp.com/album/selected-ambient-works"


def text(name):
    return (FIX / name).read_text()


class Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return json.loads(self._b)


class FakeHttp:
    """Serves saved Bandcamp responses: search JSON by (filter), pages by url."""

    def __init__(self, searches, pages):
        self.searches, self.pages, self.log = list(searches), pages, []

    def request(self, method, url, **kw):
        self.log.append((method, url, kw.get("json")))
        return Resp(self.searches.pop(0))

    def get_text(self, url, **kw):
        self.log.append(("GET", url, None))
        return self.pages[url]

    def throttle(self, site):
        pass


def identity_from_page(page: bc.BCPage, artist, title, catno=None, durations=True):
    tracks = [TrackRef(f"{chr(65 + (i - 1) // 4)}{(i - 1) % 4 + 1}", artist, t.title, t.duration if durations else None)
              for i, t in enumerate(page.tracks, 1)]
    return ReleaseIdentity(1, artist, title, "Warp", catno, 1998, tracks)


def test_parse_album_page_tracklist_and_durations():
    page = bc.parse_page(text("album_boc.html"), BOC)
    assert (page.kind, page.artist, page.title) == ("album", "Boards of Canada", "Music Has The Right To Children")
    assert len(page.tracks) == 18 and page.tracks[0].title == "Wildlife Analysis" and page.tracks[0].duration == 76
    assert page.tracks[0].url == "https://boardsofcanada.bandcamp.com/track/wildlife-analysis" and all(t.streamable for t in page.tracks)


def test_parse_search_and_track_page():
    hits = bc.parse_search(json.loads(text("search_album_hit.json")))
    assert [(h.kind, h.title, h.artist) for h in hits] == [("album", "Music Has The Right To Children", "Boards of Canada")]
    page = bc.parse_page(text("track_roygbiv.html"), "https://boardsofcanada.bandcamp.com/track/roygbiv")
    assert page.kind == "track" and len(page.tracks) == 1 and page.tracks[0].title == "Roygbiv"
    assert bc.parse_search(json.loads(text("search_miss.json"))) == []
    with pytest.raises(bc.ParseError):
        bc.parse_page("<html>changed</html>", "u")
    with pytest.raises(bc.ParseError):
        bc.parse_search({"nope": 1})


def test_album_hit_matches_the_release_and_resolves_all_tracks():
    page = bc.parse_page(text("album_boc.html"), BOC)
    ident = identity_from_page(page, "Boards of Canada", "Music Has the Right to Children", "WARPCD55")
    http = FakeHttp([text("search_album_hit.json")], {BOC: text("album_boc.html")})
    cands = Bandcamp(http).search(ident, ident.tracks)
    assert http.log[0][2]["search_filter"] == "a" and http.log[0][2]["search_text"] == "Boards of Canada Music Has the Right to Children"
    assert len(cands) == 1 and cands[0].kind == "release" and len(cands[0].tracklist) == 18
    out = match_candidates(ident, ident.tracks, cands)
    assert len(out.releases) == 1 and len(out.matches) == 18
    assert out.matches["A2"][0].candidate.url == "https://boardsofcanada.bandcamp.com/track/an-eagle-in-your-mind"


def test_wrong_album_with_the_same_title_is_rejected():
    wulfen = bc.parse_page(text("album_wulfen.html"), WULFEN)
    ident = identity_from_page(wulfen, "Mihaly Wulfen", "Selected Ambient Works")
    search = json.loads(text("search_same_title.json"))   # real results: both albums are called "Selected Ambient Works"
    search["auto"]["results"] = [r for r in search["auto"]["results"] if r["item_url_path"] in (GHYS, WULFEN)]
    assert [r["band_name"] for r in search["auto"]["results"]] == ["Florent Ghys", "Mihaly Wulfen"]
    http = FakeHttp([json.dumps(search)], {GHYS: text("album_ghys.html"), WULFEN: text("album_wulfen.html")})
    out = match_candidates(ident, ident.tracks, Bandcamp(http).search(ident, ident.tracks))
    assert {c.url for c, _ in out.releases} == {WULFEN}
    assert any(c.url == GHYS and "release score" in why for c, why in out.rejected)


def test_non_streamable_track_is_not_fetched():
    page_html = text("album_boc.html")
    m = re.search(r'data-tralbum="([^"]*)"', page_html)
    tr = json.loads(htmllib.unescape(m.group(1)))
    tr["trackinfo"][2]["file"] = None            # edited fixture: track 3 is not streamable
    tr["trackinfo"][2]["streaming"] = 0
    edited = page_html.replace(m.group(1), htmllib.escape(json.dumps(tr), quote=True))
    page = bc.parse_page(edited, BOC)
    assert [t.streamable for t in page.tracks].count(False) == 1
    ident = identity_from_page(page, "Boards of Canada", "Music Has The Right To Children")
    http = FakeHttp([text("search_album_hit.json")], {BOC: edited})
    out = match_candidates(ident, ident.tracks, Bandcamp(http).search(ident, ident.tracks))
    third = page.tracks[2].title
    assert "A3" not in out.matches and len(out.matches) == 17
    assert any("not streamable" in why and third in c.title for c, why in out.rejected)


def test_single_track_hit_prefers_the_original_over_remixes():
    ident = ReleaseIdentity(2, "Boards of Canada", "Roygbiv", None, None, None, [TrackRef("A1", "Boards of Canada", "Roygbiv", None)])
    http = FakeHttp([text("search_track_remixes_first.json")], {})
    cands = BandcampTracks(http).search(ident, ident.tracks)
    assert http.log[0][2]["search_filter"] == "t" and cands[0].position == "A1"
    out = match_candidates(ident, ident.tracks, cands)
    best = out.matches["A1"][0].candidate
    assert (best.title, best.artist) == ("Roygbiv", "Boards of Canada") and best.extra["album"] == "Music Has The Right To Children"
    assert all("Remix" not in m.candidate.title and "Refix" not in m.candidate.title for m in out.matches["A1"])
    assert all(r for _, r in out.rejected)


def test_bandcamp_tracks_is_a_fallback_in_the_same_group():
    assert Bandcamp().group == BandcampTracks().group == "bandcamp" and Bandcamp().level == 2


@pytest.mark.live
def test_live_album_search():
    from audioresearch.http import HttpClient

    ident = ReleaseIdentity(3, "Boards of Canada", "Music Has The Right To Children", None, None, None,
                            [TrackRef("A1", "Boards of Canada", "Wildlife Analysis", 76)])
    cands = Bandcamp(HttpClient()).search(ident, ident.tracks)
    assert cands and cands[0].tracklist
