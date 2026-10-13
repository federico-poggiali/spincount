import json
from pathlib import Path

from audioresearch.adapters.discogs_youtube import DiscogsYouTube
from audioresearch.adapters.itunes import ITunesPreview
from audioresearch.adapters.youtube_music import YouTubeMusic
from audioresearch.adapters import Registry
from audioresearch.matcher import match_candidates
from audioresearch.models import Quality, ReleaseIdentity, TrackRef
from audioresearch.pipeline import research
from audioresearch.tests.test_identify import _client
from audioresearch.identify import identify

FIX = Path(__file__).parent / "fixtures"


def load(rel):
    return json.loads((FIX / rel).read_text())


def bells():
    return ReleaseIdentity(1, "Jeff Mills", "The Bells", "Purpose Maker", "PM 1", 1996,
                           [TrackRef("A1", "Jeff Mills", "The Bells", 286), TrackRef("B1", "Jeff Mills", "Other Tune", 300)])


class FakeJsonHttp:
    def __init__(self, payloads):
        self.payloads, self.calls = list(payloads), []

    def get_json(self, url, **kw):
        self.calls.append(kw.get("params"))
        return self.payloads.pop(0)


class FakeYTM:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def search(self, q, filter=None, limit=None):
        self.queries.append(q)
        return self.rows


def test_discogs_youtube_matches_the_linked_video_to_its_track():
    ident = identify(137924, _client())          # Gusgus - Be Brave (master 137924 main release)
    ident = identify("https://www.discogs.com/release/%d" % ident.discogs_release_id, _client())
    cands = DiscogsYouTube().search(ident, ident.tracks)
    assert len(cands) == len(ident.videos) and all(c.quality_hint == Quality.FULL for c in cands)
    out = match_candidates(ident, ident.tracks, cands)
    assert all(c.adapter == "discogs_youtube" for ms in out.matches.values() for c in [m.candidate for m in ms])
    # unrelated videos on the release are rejected with a reason, not silently dropped
    assert all(reason for _, reason in out.rejected)


def test_discogs_youtube_with_a_matching_video():
    ident = bells()
    ident.videos = [{"uri": "https://www.youtube.com/watch?v=AAA", "title": "Jeff Mills - The Bells", "duration": 287},
                    {"uri": "https://www.youtube.com/watch?v=BBB", "title": "Jeff Mills - Other Tune (live)", "duration": 301},
                    {"uri": "https://vimeo.com/1", "title": "x"}]
    cands = DiscogsYouTube().search(ident, ident.tracks)
    assert len(cands) == 2
    out = match_candidates(ident, ident.tracks, cands)
    assert out.matches["A1"][0].candidate.url.endswith("AAA")
    assert "B1" not in out.matches                    # the live version is not the original


def test_youtube_music_parses_and_matches():
    rows = load("youtube_music/jeff_mills_the_bells.json")
    ytm = YouTubeMusic(FakeYTM(rows))
    ident = bells()
    cands = ytm.search(ident, [ident.tracks[0]])
    assert cands[0].url == "https://music.youtube.com/watch?v=S-BlgAQ7uRQ" and cands[0].artist == "Jeff Mills"
    assert ytm.client.queries == ["Jeff Mills The Bells"]
    best = match_candidates(ident, ident.tracks, cands).matches["A1"][0]
    assert best.candidate.title == "The Bells" and best.score > 0.8
    assert all("Blue Potential" not in m.candidate.title for m in match_candidates(ident, ident.tracks, cands).matches["A1"][:1])


def test_youtube_music_is_only_a_fallback_inside_the_youtube_group():
    from audioresearch.adapters.fake import FakeAdapter
    ident = bells()
    ident.videos = [{"uri": "https://www.youtube.com/watch?v=AAA", "title": "Jeff Mills - The Bells", "duration": 287}]
    ytm = YouTubeMusic(FakeYTM(load("youtube_music/jeff_mills_the_bells.json")))
    itunes_http = FakeJsonHttp([{"results": []}, {"results": []}])
    reg = Registry([DiscogsYouTube(), ytm, ITunesPreview(itunes_http)], disabled=set())
    # stop before fetching: only the search and match stages matter here
    reg.get("discogs_youtube").fetch = lambda c, d: (_ for _ in ()).throw(RuntimeError("no network in tests"))
    research("1", [1], identity=ident, registry=reg)
    assert [q for q in ytm.client.queries] == ["Jeff Mills Other Tune"]   # A1 had a Discogs video; only B1 went on


def test_itunes_parses_previews_with_the_full_track_length():
    ident = bells()
    it = ITunesPreview(FakeJsonHttp([load("itunes/jeff_mills_the_bells.json")]))
    cands = it.search(ident, [ident.tracks[0]])
    assert cands and all(c.quality_hint == Quality.PREVIEW and c.url.startswith("http") for c in cands)
    assert it.http.calls[0]["term"] == "Jeff Mills The Bells"
    assert cands[0].duration == 285
    best = match_candidates(ident, ident.tracks, cands).matches["A1"][0]
    assert best.candidate.artist == "Jeff Mills" and best.score > 0.8


def test_itunes_miss_returns_no_candidates():
    it = ITunesPreview(FakeJsonHttp([load("itunes/miss.json")]))
    assert it.search(bells(), [bells().tracks[0]]) == []
