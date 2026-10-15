import os
import time

from audioresearch.adapters import Registry
from audioresearch.adapters.local_files import LocalFiles, file_position, match_files
from audioresearch.adapters.manual_link import ManualLink
from audioresearch.models import Candidate, FetchedAudio, Quality, ReleaseIdentity, Status, TrackRef
from audioresearch.pipeline import research
from audioresearch.store import Store
from audioresearch.tests.audio_utils import make_wav
from audioresearch.adapters.fake import FakeAdapter


def ident():
    return ReleaseIdentity(55, "Foo", "EP", "L", "C1", 2020, [
        TrackRef("A1", "Foo", "Night Drive", 360), TrackRef("A2", "Foo", "Morning Light", 400),
        TrackRef("B1", "Foo", "Deep Water", 380), TrackRef("B2", "Foo", "Last Train", 300)])


def folder(tmp_path, names):
    d = tmp_path / "audio" / "55"
    for i, n in enumerate(names):
        make_wav(d / n, 1.0, i + 1)
    return d


def test_position_then_title_with_unmatched_reported(tmp_path):
    d = folder(tmp_path, ["A1 - Night Drive.wav", "a2_morning_light.wav", "Deep Water.wav", "notes.wav"])
    res = match_files(sorted(d.iterdir()), ident().tracks)
    assert {(m["position"], m["method"]) for m in res["matched"]} == {("A1", "position"), ("A2", "position"), ("B1", "title")}
    assert [u["file"] for u in res["unmatched_files"]] == ["notes.wav"]
    assert res["unmatched_tracks"] == ["B2"]


def test_two_files_claiming_one_position_are_not_guessed():
    from pathlib import Path
    res = match_files([Path("A1 - x.wav"), Path("A1 - y.wav")], ident().tracks)
    assert res["matched"] == [] and len(res["unmatched_files"]) == 2
    assert file_position("A01 - x") == "A1" and file_position("Night Drive") is None


def test_a_title_matching_two_tracks_equally_is_not_guessed():
    from pathlib import Path
    tracks = [TrackRef("A1", "Foo", "Mix Part 1"), TrackRef("A2", "Foo", "Mix Part 2")]
    res = match_files([Path("Mix Part.wav")], tracks)
    assert res["matched"] == [] and res["unmatched_files"][0]["reason"] == "title matches several tracks"


def test_local_files_win_over_everything_and_report_unmatched(tmp_path):
    folder(tmp_path, ["A1 - Night Drive.wav", "junk.wav"])
    events = []
    online = Candidate("yt", 1, "track", "https://yt/1", "Night Drive", "Foo", 360, position="A1")
    reg = Registry([LocalFiles(tmp_path / "audio"), FakeAdapter("yt", 1, [online])], disabled=set())
    res = research("55", range(2), identity=ident(), registry=reg, audio_dir=tmp_path / "ac", on_event=events.append)
    a1 = res.track("A1")
    assert (a1.source, a1.level, a1.status, a1.confidence) == ("local_files", 0, Status.FOUND, 1.0)
    assert a1.audio_path.endswith("A1 - Night Drive.wav")
    assert reg.get("yt").searched == [["A2", "B1", "B2"]]
    assert any(e.type == "candidate_rejected" and "junk.wav" in e.data["url"] for e in events)


def test_manual_link_is_level_0_and_invalidates_the_cache(tmp_path):
    store = Store(tmp_path / "t.db")
    fake_yt = FakeAdapter("yt", 1, [Candidate("yt", 1, "track", "https://yt/1", "Night Drive", "Foo", 360, position="A1")])
    ml = ManualLink(store)
    reg = Registry([ml, fake_yt], disabled=set())
    r1 = research("55", range(2), identity=ident(), registry=reg, store=store, audio_dir=tmp_path / "ac")
    assert r1.track("A1").source == "yt"
    time.sleep(1.1)
    store.set_manual_link(55, "A1", "https://example.com/mine.mp3")
    assert ml.changed_since(55, store.get_result(55)[2])
    # the real fetch would hit the network: serve a local file instead
    ml.fetch = lambda c, dest: FetchedAudio(make_wav(dest.parent / "m.wav", 2), "manual_link", c.url, Quality.FULL)
    r2 = research("55", range(2), identity=ident(), registry=reg, store=store, audio_dir=tmp_path / "ac")
    assert (r2.track("A1").source, r2.track("A1").level) == ("manual_link", 0)
    assert "pasted link" in r2.track("A1").reason and r2.track("A1").confidence == 0.95
