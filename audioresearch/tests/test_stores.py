from pathlib import Path

import pytest

from audioresearch.adapters.stores.clone import Clone
from audioresearch.adapters.stores.decks_de import DecksDe
from audioresearch.adapters.stores.deejay_de import DeejayDe
from audioresearch.adapters.stores.eshop import SoundMetaphors
from audioresearch.adapters.stores.hardwax import Hardwax
from audioresearch.adapters.stores.redeye import Redeye
from audioresearch.adapters.stores.shopify import OrbitWax
from audioresearch.adapters.stores.redeye import Redeye
from audioresearch.http import HttpError
from audioresearch.matcher import match_candidates
from audioresearch.models import Quality, ReleaseIdentity, TrackRef
from audioresearch.parsers import stores as p

F = Path(__file__).parent / "fixtures" / "stores"


def page(name):
    return (F / name).read_text(errors="replace")


class FakeHttp:
    """url -> saved page (or status error). Records every request."""

    def __init__(self, pages, bpms=None, errors=None):
        self.pages, self.bpms, self.errors, self.urls = pages, bpms or {}, errors or {}, []

    def get_text(self, url, **kw):
        self.urls.append(url)
        if url in self.errors:
            raise HttpError("blocked", self.errors[url])
        if "getBPM" in url:
            return self.bpms.get(url.rsplit("=", 1)[1], "")
        return self.pages[url]


def directors_cut(catno="AX 084 DC", **kw):
    return ReleaseIdentity(9, "Jeff Mills", "The Director's Cut Chapter 6", "Axis", catno, 2026, [
        TrackRef("A1", "Jeff Mills", "The Bells", None), TrackRef("B1", "Jeff Mills", "The Bells (Blue Potential Version)", None),
        TrackRef("B2", "Jeff Mills", "The Homosapien Sapiens", None)], **kw)


# ---- parsers --------------------------------------------------------------------------------------------
def test_parse_deejay_release_tracks_and_clip_urls():
    rels = p.parse_deejay(page("deejay_de_catno.html"))
    assert len(rels) == 1
    r = rels[0]
    assert (r.id, r.artist, r.catno, r.label) == ("942166", "JEFF MILLS", "AX084DC", "Axis Records")
    assert [(t.position, t.title) for t in r.tracks] == [("A1", "The Bells"), ("B1", "The Bells (Blue Potential version)"), ("B2", "The Homosapien Sapiens")]
    assert r.tracks[0].clip_url == "https://www.deejay.de/streamit/6/6/942166a.mp3"
    assert p.parse_deejay(page("deejay_de_miss.html")) == []


def test_parse_hardwax_release_tracks_and_clip_urls():
    r = p.parse_hardwax(page("hardwax_catno.html"))[0]
    assert (r.id, r.artist, r.title, r.catno, r.label) == ("81971", "Jeff Mills", "The Director’s Cut Chapter 6", "084 DC", "Axis")
    assert [(t.position, t.clip_url) for t in r.tracks][0] == ("A1", "https://media.hardwax.com/audio/81971_A1.mp3")
    assert p.parse_hardwax(page("hardwax_miss.html")) == []


def test_parse_bpm():
    assert p.parse_bpm("137") == 137.0 and p.parse_bpm("") is None and p.parse_bpm("N/A") is None


def test_parsers_complain_when_the_page_changes():
    with pytest.raises(p.StoreParseError):
        p.parse_deejay('<article class="product" id="a12"><h2>no title link</h2></article>')


# ---- deejay.de ------------------------------------------------------------------------------------------
def test_deejay_catalogue_number_hit_stops_after_the_first_query_and_keeps_bpm():
    http = FakeHttp({"https://www.deejay.de/AX084DC": page("deejay_de_catno.html")}, bpms={"942166a": "137", "942166b": "132", "942166c": ""})
    cands = DeejayDe(http).search(directors_cut(), directors_cut().tracks)
    assert [u for u in http.urls if "getBPM" not in u] == ["https://www.deejay.de/AX084DC"]    # catalogue number first, and enough
    assert len(cands) == 1 and cands[0].kind == "release" and cands[0].catno == "AX084DC"
    out = match_candidates(directors_cut(), directors_cut().tracks, cands)
    assert len(out.releases) == 1 and set(out.matches) == {"A1", "B1", "B2"}
    a1 = out.matches["A1"][0].candidate
    assert a1.url == "https://www.deejay.de/streamit/6/6/942166a.mp3" and a1.readings[0].source == "deejay_de" and a1.readings[0].bpm == 137.0
    assert out.matches["B2"][0].candidate.readings == []             # the store showed no BPM for that track


def test_deejay_artist_and_title_hit_without_catalogue_number():
    ident = directors_cut(catno=None)
    http = FakeHttp({"https://www.deejay.de/Jeff+Mills+The+Director%27s+Cut+Chapter+6": page("deejay_de_artist_title.html")})
    cands = DeejayDe(http).search(ident, ident.tracks)
    assert http.urls[0].endswith("Jeff+Mills+The+Director%27s+Cut+Chapter+6")
    out = match_candidates(ident, ident.tracks, cands)
    assert [c.catno for c, _ in out.releases] == ["AX084DC"]
    assert {c.title for c, why in out.rejected} >= {"Cosmic Distance Markers"}      # other releases on the page are rejected


def test_deejay_miss_falls_back_to_one_query_per_track_and_finds_nothing():
    ident = ReleaseIdentity(3, "Zzyzx", "Nonexistent", None, None, None, [TrackRef("A1", "Zzyzx", "Qwerty", None)])
    http = FakeHttp({"https://www.deejay.de/Zzyzx+Nonexistent": page("deejay_de_miss.html"), "https://www.deejay.de/Zzyzx+Qwerty": page("deejay_de_miss.html")})
    assert DeejayDe(http).search(ident, ident.tracks) == []
    assert len(http.urls) == 2


# ---- hardwax --------------------------------------------------------------------------------------------
def test_hardwax_catalogue_number_hit_matches_despite_the_dropped_label_prefix():
    ident = directors_cut()
    http = FakeHttp({"https://hardwax.com/?find=AX%20084%20DC": page("hardwax_catno.html")})
    cands = Hardwax(http).search(ident, ident.tracks)
    assert cands[0].catno == "084 DC" and cands[0].quality_hint == Quality.CLIP
    out = match_candidates(ident, ident.tracks, cands)
    assert out.releases and set(out.matches) == {"A1", "B1", "B2"}
    assert out.matches["A1"][0].candidate.url == "https://media.hardwax.com/audio/81971_A1.mp3"
    assert out.matches["A1"][0].candidate.readings == []                  # hardwax shows no BPM


def test_hardwax_artist_and_title_hit_and_version_labels_are_respected():
    ident = directors_cut(catno=None)
    http = FakeHttp({"https://hardwax.com/?find=Jeff%20Mills%20The%20Director%27s%20Cut%20Chapter%206": page("hardwax_artist_title.html")})
    cands = Hardwax(http).search(ident, ident.tracks)
    out = match_candidates(ident, ident.tracks, cands)
    assert out.matches["A1"][0].candidate.title == "The Bells (Original Version)"
    assert out.matches["B1"][0].candidate.url.endswith("81971_B1.mp3")


def test_hardwax_miss():
    ident = ReleaseIdentity(3, "Zzyzx", "Nonexistent", None, None, None, [TrackRef("A1", "Zzyzx", "Qwerty", None)])
    http = FakeHttp({"https://hardwax.com/?find=Zzyzx%20Nonexistent": page("hardwax_miss.html"), "https://hardwax.com/?find=Zzyzx%20Qwerty": page("hardwax_miss.html")})
    assert Hardwax(http).search(ident, ident.tracks) == []


# ---- redeye ---------------------------------------------------------------------------------------------
def test_parse_redeye_one_track_per_side_and_clip_urls():
    r = p.parse_redeye(page("redeye_catno.html"))[0]
    assert (r.id, r.artist, r.title, r.catno, r.label) == ("141884", "Jeff Mills", "The Directors Cut Chapter 6", "AX084DC", "Axis")
    assert [(t.position, t.title, t.clip_url) for t in r.tracks][:2] == [
        ("A1", "The Bells (Original Version)", "https://sounds.redeyerecords.co.uk/141884.mp3"),
        ("B1", "The Bells (Blue Potential Version)", "https://sounds.redeyerecords.co.uk/141884b.mp3")]
    assert p.parse_redeye(page("redeye_miss.html")) == []


def test_redeye_catalogue_number_then_title_only_and_matches():
    ident = directors_cut()
    http = FakeHttp({"https://www.redeyerecords.co.uk/search/?searchType=CAT&keywords=AX084DC": page("redeye_catno.html")})
    cands = Redeye(http).search(ident, ident.tracks)
    assert http.urls == ["https://www.redeyerecords.co.uk/search/?searchType=CAT&keywords=AX084DC"]
    out = match_candidates(ident, ident.tracks, cands)
    assert out.releases and out.matches["B2"][0].candidate.url == "https://sounds.redeyerecords.co.uk/141884c.mp3"


def test_redeye_title_search_has_no_artist_and_no_punctuation():
    ident = directors_cut(catno=None)
    url = "https://www.redeyerecords.co.uk/search/?searchType=Artist&keywords=The+Directors+Cut+Chapter+6"
    http = FakeHttp({url: page("redeye_title.html")})
    assert Redeye(http).search(ident, ident.tracks) and http.urls == [url]


# ---- redeye ---------------------------------------------------------------------------------------------
def test_parse_redeye_one_track_per_side_and_clip_urls():
    r = p.parse_redeye(page("redeye_catno.html"))[0]
    assert (r.id, r.artist, r.title, r.catno, r.label) == ("141884", "Jeff Mills", "The Directors Cut Chapter 6", "AX084DC", "Axis")
    assert [(t.position, t.title, t.clip_url) for t in r.tracks][:2] == [
        ("A1", "The Bells (Original Version)", "https://sounds.redeyerecords.co.uk/141884.mp3"),
        ("B1", "The Bells (Blue Potential Version)", "https://sounds.redeyerecords.co.uk/141884b.mp3")]
    assert p.parse_redeye(page("redeye_miss.html")) == []


def test_redeye_catalogue_number_first_and_enough_and_matches():
    ident = directors_cut()
    http = FakeHttp({"https://www.redeyerecords.co.uk/search/?searchType=CAT&keywords=AX084DC": page("redeye_catno.html")})
    cands = Redeye(http).search(ident, ident.tracks)
    assert len(http.urls) == 1
    out = match_candidates(ident, ident.tracks, cands)
    assert out.releases and out.matches["B2"][0].candidate.url == "https://sounds.redeyerecords.co.uk/141884c.mp3"


def test_redeye_title_search_has_no_artist_and_no_punctuation():
    ident = directors_cut(catno=None)
    url = "https://www.redeyerecords.co.uk/search/?searchType=Artist&keywords=The+Directors+Cut+Chapter+6"
    http = FakeHttp({url: page("redeye_title.html")})
    assert Redeye(http).search(ident, ident.tracks) and http.urls == [url]


# ---- blocked sites --------------------------------------------------------------------------------------
@pytest.mark.parametrize("cls,fixture", [(DecksDe, "decks_de_cloudflare_challenge.html"), (Clone, "clone_cloudflare_challenge.html")])
def test_cloudflare_blocked_stores_are_off_by_default_and_say_why(cls, fixture):
    assert "Just a moment" in page(fixture) and cls.enabled_by_default is False
    a = cls(FakeHttp({}, errors={a_url: 403 for a_url in [cls(FakeHttp({})).search_url(q) for q in ("AX 084 DC", "AX084DC")]}))
    with pytest.raises(p.StoreBlocked):
        a.search(directors_cut(), directors_cut().tracks)


OPEN_STORES = {"deejay_de", "hardwax", "redeye", "runas", "orbitwax", "soundmetaphors", "one_eye_witness", "smallblackdots"}


def test_default_registry_leaves_blocked_stores_out_unless_enabled(monkeypatch):
    from audioresearch.adapters import default_registry

    assert {a.name for a in default_registry(disabled=set()).for_level(5)} == OPEN_STORES
    monkeypatch.setenv("AUDIORESEARCH_ENABLE", "decks_de,clone")
    assert {a.name for a in default_registry(disabled=set()).for_level(5)} == OPEN_STORES | {"decks_de", "clone"}


@pytest.mark.live
@pytest.mark.parametrize("cls", [DeejayDe, Hardwax, Redeye])
def test_live_catalogue_number_search(cls):
    from audioresearch.http import HttpClient

    ident = directors_cut()
    cands = cls(HttpClient()).search(ident, ident.tracks)
    assert cands and cands[0].tracklist
