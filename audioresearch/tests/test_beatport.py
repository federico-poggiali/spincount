"""Beatport tests. The challenge fixtures are real; the API fixtures are hand-written (see fixtures/beatport/README.md)."""
import json
from pathlib import Path

import pytest

from audioresearch.adapters import Registry
from audioresearch.adapters.base import AdapterUnavailable
from audioresearch.adapters.beatport import BeatportReleases, BeatportTracks
from audioresearch.matcher import match_candidates
from audioresearch.models import FetchedAudio, Quality, ReleaseIdentity, TrackRef
from audioresearch.parsers import beatport as bp
from audioresearch.pipeline import research

FIX = Path(__file__).parent / "fixtures" / "beatport"


def load(name):
    return json.loads((FIX / name).read_text())


class Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, by_path):
        self.by_path, self.calls = by_path, []

    def get(self, url, **kw):
        self.calls.append((url, kw.get("params"), kw.get("headers")))
        for path, data in self.by_path.items():
            if url.endswith(path):
                return Resp(data)
        raise AssertionError(url)


def bells(track_title="The Bells (Original Mix)"):
    return ReleaseIdentity(1, "Jeff Mills", "The Bells", "Purpose Maker", "PM-001", 1996,
                           [TrackRef("A1", "Jeff Mills", track_title, 289), TrackRef("B1", "Jeff Mills", "The Bells (Dub Mix)", 301)])


def test_the_real_cloudflare_challenge_is_recognised():
    html = (FIX / "cloudflare_challenge.html").read_text()
    assert "Just a moment" in html
    with pytest.raises(bp.BeatportBlocked):
        bp.check_response(403, html)
    with pytest.raises(bp.BeatportBlocked):
        bp.check_response(401, load("api_unauthenticated.json")["detail"])
    bp.check_response(200, "")


def test_without_a_token_the_adapter_says_so_and_is_switched_off_at_once(tmp_path):
    a = BeatportTracks(FakeHttp({}), token="")
    with pytest.raises(AdapterUnavailable):
        a.search(bells(), bells().tracks)
    events = []
    res = research("1", [4], identity=bells(), registry=Registry([a], disabled=set()), audio_dir=tmp_path, on_event=events.append)
    assert res.adapters_off == ["beatport_tracks"] and any(e.type == "adapter_off" for e in events)


def test_track_candidates_carry_mix_names_readings_and_preview_quality():
    http = FakeHttp({"tracks/": load("UNVERIFIED_api_tracks.json")})
    ident = bells()
    cands = BeatportTracks(http, token="t").search(ident, ident.tracks[:1])
    assert http.calls[0][2] == {"Authorization": "Bearer t"} and http.calls[0][1]["q"] == "Jeff Mills The Bells"
    assert all(c.quality_hint == Quality.PREVIEW for c in cands)
    assert cands[0].title == "The Bells (Original Mix)" and cands[0].readings[0].bpm == 132.0 and cands[0].readings[0].key == "A Minor"


def test_a_remix_or_dub_is_not_matched_to_the_original():
    http = FakeHttp({"tracks/": load("UNVERIFIED_api_tracks.json")})
    ident = bells()
    cands = BeatportTracks(http, token="t").search(ident, ident.tracks[:1])
    out = match_candidates(ident, ident.tracks[:1], cands)
    assert [m.candidate.title for m in out.matches["A1"]] == ["The Bells (Original Mix)"]
    assert {c.title for c, _ in out.rejected} == {"The Bells (Dub Mix)", "The Bells (Schranz Remix)"}


def test_readings_appear_in_the_output_json(tmp_path):
    http = FakeHttp({"tracks/": load("UNVERIFIED_api_tracks.json")})
    ident = bells()
    a = BeatportTracks(http, token="t")
    a.fetch = lambda c, dest: FetchedAudio(dest.parent / "x.fake", a.name, c.url, Quality.PREVIEW, 120.0)
    res = research("1", [4], identity=ident, registry=Registry([a], disabled=set()), audio_dir=tmp_path)
    j = json.loads(res.to_json())
    assert j["tracks"][0]["readings"] == [{"source": "beatport", "bpm": 132.0, "key": "A Minor"}]
    assert j["tracks"][0]["quality"] == "preview"


def test_release_search_by_catno_first_then_title_and_matches_the_tracklist():
    http = FakeHttp({"releases/": load("UNVERIFIED_api_releases.json"), "releases/10/tracks/": load("UNVERIFIED_api_release_tracks.json")})
    ident = bells()
    cands = BeatportReleases(http, token="t").search(ident, ident.tracks)
    qs = [c[1]["q"] for c in http.calls if c[0].endswith("releases/")]
    assert qs == ["PM-001", "Jeff Mills The Bells"]
    assert len(cands) == 1 and cands[0].catno == "PM-001" and len(cands[0].tracklist) == 2
    out = match_candidates(ident, ident.tracks, cands)
    assert out.releases and "A1" in out.matches
    assert any("not streamable" in why for _, why in out.rejected)   # the Dub Mix has no excerpt
    assert out.matches["A1"][0].candidate.readings[0].bpm == 132.0


def test_parse_errors_are_parser_errors():
    with pytest.raises(bp.BeatportParseError):
        bp.parse_tracks({"nope": 1})
    with pytest.raises(bp.BeatportParseError):
        bp.parse_releases({"results": [{"id": "x"}]})
