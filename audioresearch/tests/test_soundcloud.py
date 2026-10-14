import json
from pathlib import Path

from audioresearch.adapters.soundcloud_sets import SoundCloudSets
from audioresearch.adapters.soundcloud_tracks import SoundCloudTracks
from audioresearch.matcher import match_candidates
from audioresearch.models import FetchedAudio, Quality, ReleaseIdentity, TrackRef
from audioresearch.parsers import soundcloud as sc
from audioresearch.verify import verify

FIX = Path(__file__).parent / "fixtures" / "soundcloud"


def load(name):
    return json.loads((FIX / name).read_text())


class Seq(list):
    """Successive responses of one endpoint (one per call)."""


class FakeApi:
    """Replays saved api-v2 responses; remembers the calls."""

    def __init__(self, **by_endpoint):
        self.by_endpoint, self.calls = by_endpoint, []

    def call(self, endpoint, **q):
        self.calls.append((endpoint, q))
        r = self.by_endpoint[endpoint]
        return r.pop(0) if isinstance(r, Seq) else r


def mills(duration=289, title="The Bells", artist="Jeff Mills"):
    return ReleaseIdentity(1, artist, title, "Purpose Maker", "PM 1", 1996,
                           [TrackRef("A1", artist, title, duration), TrackRef("B1", artist, "Other Tune", 300)])


def test_parse_track_search():
    ts = sc.parse_tracks(load("search_tracks_the_bells.json"))
    assert ts[0].title == "The Bells" and ts[0].artist == "Jeff Mills" and ts[0].duration == 289 and ts[0].quality == Quality.FULL
    assert sc.parse_tracks(load("search_tracks_miss.json")) == []


def test_track_search_finds_the_original_and_not_the_remixes():
    ident = mills()
    api = FakeApi(**{"search/tracks": Seq([load("search_tracks_the_bells.json"), {"collection": []}])})
    cands = SoundCloudTracks(api).search(ident, ident.tracks)
    assert api.calls[0] == ("search/tracks", {"q": "Jeff Mills The Bells", "limit": 12})
    best = match_candidates(ident, ident.tracks, cands)
    top = best.matches["A1"][0].candidate
    assert (top.title, top.artist) == ("The Bells", "Jeff Mills")
    shown = {m.candidate.title for m in best.matches["A1"]}
    assert not any(w in t for t in shown for w in ("Schranz", "EDIT", "REMIX", "Bootleg", "Remix"))
    assert any("Remix" in c.title.title() or "Schranz" in c.title for c, _ in best.rejected)


def test_dj_mix_is_rejected_by_duration_whether_or_not_discogs_has_one():
    ident = mills(duration=None)    # no reference duration: the 15 minute rule applies
    ident.title = ident.tracks[0].title = "Essential Mix"
    api = FakeApi(**{"search/tracks": Seq([load("search_tracks_dj_mix.json"), {"collection": []}])})
    out = match_candidates(ident, ident.tracks[:1], SoundCloudTracks(api).search(ident, ident.tracks[:1]))
    assert not any((m.candidate.duration or 0) > 15 * 60 for ms in out.matches.values() for m in ms)
    long_ones = [c for c, _ in out.rejected if (c.duration or 0) > 15 * 60]
    assert long_ones, "the saved results contain hour-long sets"
    # and the verifier catches one that slips through with a known track length
    f = FetchedAudio(Path("x"), "soundcloud_tracks", "u", Quality.FULL, 7201.0)
    v = verify(TrackRef("A1", "Jeff Mills", "The Bells", 289), f, long_ones[0])
    assert not v.ok and "mix or medley" in v.reasons[0]


def test_label_preview_medley_is_rejected():
    ident = mills(duration=None, title="Purpose Maker")
    api = FakeApi(**{"search/tracks": Seq([load("search_tracks_ep_preview.json"), {"collection": []}])})
    cands = SoundCloudTracks(api).search(ident, ident.tracks[:1])
    medleys = [c for c in cands if " / " in c.title or "Preview" in c.title or "preview" in c.title]
    assert medleys
    track = ident.tracks[0]
    flagged = [c for c in medleys if not verify(track, FetchedAudio(Path("x"), "sc", c.url, Quality.FULL, 344.0), c).ok]
    titles = {c.title for c in flagged}
    assert any(t.startswith("ALARM / STEAMPIT EP") for t in titles)             # three tracks joined with ' / '
    assert any("EP](Preview)" in t or "(preview)" in t.lower() for t in titles)  # an EP preview


def test_sets_search_resolves_the_tracklist_and_matches_the_album():
    albums = load("search_albums_boc.json")
    batch = load("tracks_batch_boc_album.json")
    api = FakeApi(**{"search/albums": albums, "search/playlists_without_albums": {"collection": []}, "tracks": batch})
    titles = [t["title"] for t in sorted(batch, key=lambda t: albums["collection"][0]["tracks"].index(
        next(x for x in albums["collection"][0]["tracks"] if x["id"] == t["id"])))]
    durations = {t["title"]: round(t["full_duration"] / 1000) for t in batch}
    ident = ReleaseIdentity(2, "Boards of Canada", "Music Has The Right To Children", "Warp", "WARPCD55", 1998,
                            [TrackRef(f"{chr(65 + i // 4)}{i % 4 + 1}", "Boards of Canada", t, durations[t]) for i, t in enumerate(titles)])
    cands = SoundCloudSets(api).search(ident, ident.tracks)
    assert api.calls[0][0] == "search/albums" and any(c[0] == "tracks" for c in api.calls)
    assert len(cands) == 2 and cands[0].kind == "release" and len(cands[0].tracklist) == 18
    out = match_candidates(ident, ident.tracks, cands)
    assert [c.title for c, _ in out.releases] == ["Music Has The Right To Children"]       # the "inspired album" is rejected
    assert len(out.matches) == 18 and out.matches["A1"][0].candidate.url.startswith("https://soundcloud.com/")


def test_snippet_policy_means_preview_quality_and_blocked_is_unavailable():
    t = {"id": 1, "title": "X", "permalink_url": "https://soundcloud.com/a/x", "user": {"username": "A"},
         "full_duration": 300000, "duration": 30000, "policy": "SNIP"}
    assert sc.parse_track(t).quality == Quality.PREVIEW and sc.parse_track(t).duration == 300
    assert sc.parse_track({**t, "policy": "BLOCK"}).blocked and sc.parse_track({"id": 2}) is None


def test_unexpected_responses_raise_parser_errors():
    import pytest

    with pytest.raises(sc.SoundcloudError):
        sc.parse_sets({"nope": 1})
    with pytest.raises(sc.SoundcloudError):
        sc.parse_tracks({"nope": 1})


def test_both_routes_run_in_parallel_groups():
    from audioresearch.adapters import Registry

    reg = Registry([SoundCloudTracks(FakeApi()), SoundCloudSets(FakeApi())], disabled=set())
    assert len(reg.groups(3)) == 2


import pytest  # noqa: E402


@pytest.mark.live
def test_live_track_and_set_search():
    ident = mills()
    tracks = SoundCloudTracks().search(ident, ident.tracks[:1])
    assert any(c.title == "The Bells" for c in tracks)
    sets = SoundCloudSets().search(ReleaseIdentity(2, "Boards of Canada", "Music Has The Right To Children", None, None, None, []), [])
    assert sets and sets[0].tracklist
