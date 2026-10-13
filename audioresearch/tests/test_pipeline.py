import pytest

from audioresearch.adapters import Registry
from audioresearch.adapters.fake import FakeAdapter
from audioresearch.models import Candidate, Quality, ReleaseIdentity, Status, TrackRef
from audioresearch.pipeline import research


def identity():
    return ReleaseIdentity(77, "Foo", "Night Drive EP", "Label", "ABC001", 2020, [
        TrackRef("A1", "Foo", "Night Drive", 360), TrackRef("A2", "Foo", "Morning Light", 400),
        TrackRef("B1", "Foo", "Deep Water", 380)])


def tc(adapter, level, pos, title, dur=None, q=Quality.FULL, url=None, **kw):
    return Candidate(adapter, level, "track", url or f"https://{adapter}/{pos}", title, "Foo", dur, quality_hint=q, position=pos, **kw)


def run(registry, tmp_path, levels=range(6), **kw):
    return research("77", levels, identity=identity(), registry=registry, audio_dir=tmp_path, **kw)


def test_full_release_found_at_level_1(tmp_path):
    reg = Registry([FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360), tc("yt", 1, "A2", "Morning Light", 400),
                                           tc("yt", 1, "B1", "Deep Water", 380)]),
                    FakeAdapter("bc", 2, [tc("bc", 2, "A1", "Night Drive", 360)])], disabled=set())
    res = run(reg, tmp_path)
    assert [t.status for t in res.tracks] == [Status.FOUND] * 3
    assert {t.level for t in res.tracks} == {1}
    assert reg.get("bc").searched == []  # nothing left to search at level 2


def test_split_across_levels_1_and_3(tmp_path):
    reg = Registry([FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360)]),
                    FakeAdapter("sc", 3, [tc("sc", 3, "A2", "Morning Light", 400), tc("sc", 3, "B1", "Deep Water", 380)])],
                   disabled=set())
    res = run(reg, tmp_path)
    assert [(t.position, t.level, t.source) for t in res.tracks] == [("A1", 1, "yt"), ("A2", 3, "sc"), ("B1", 3, "sc")]
    assert reg.get("sc").searched == [["A2", "B1"]]


def test_never_found(tmp_path):
    reg = Registry([FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360)])], disabled=set())
    res = run(reg, tmp_path)
    assert res.track("A2").status == Status.NOT_FOUND and res.track("B1").status == Status.NOT_FOUND
    assert res.track("A2").audio_path is None


def test_level_0_overrides_level_1_and_is_never_replaced(tmp_path):
    local = tc("local", 0, "A1", "Night Drive", 360, extra={"trusted": True})
    reg = Registry([FakeAdapter("local", 0, [local]),
                    FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360), tc("yt", 1, "A2", "Morning Light", 400)])],
                   disabled=set())
    res = run(reg, tmp_path)
    assert (res.track("A1").source, res.track("A1").level) == ("local", 0)
    assert reg.get("yt").searched == [["A2", "B1"]]  # A1 is not even searched


def test_lower_quality_early_result_is_replaced_by_a_better_later_one(tmp_path):
    reg = Registry([FakeAdapter("itunes", 1, [tc("itunes", 1, "A1", "Night Drive", 360, Quality.PREVIEW)], max_quality=Quality.PREVIEW),
                    FakeAdapter("bc", 2, [tc("bc", 2, "A1", "Night Drive", 360)])], disabled=set())
    res = run(reg, tmp_path)
    a1 = res.track("A1")
    assert (a1.source, a1.quality) == ("bc", Quality.FULL)
    assert [a["source"] for a in a1.alternatives] == ["itunes"]


def test_release_candidate_resolves_all_tracks_together(tmp_path):
    rel = Candidate("bc", 2, "release", "https://bc/r", "Night Drive EP", "Foo", catno="ABC001", tracklist=[
        TrackRef("1", "Foo", "Night Drive", 360, "https://bc/1"), TrackRef("2", "Foo", "Morning Light", 400, "https://bc/2"),
        TrackRef("3", "Foo", "Deep Water", 380, "https://bc/3")])
    res = run(Registry([FakeAdapter("bc", 2, [rel])], disabled=set()), tmp_path)
    assert [t.url for t in res.tracks] == ["https://bc/1", "https://bc/2", "https://bc/3"]


def test_events_are_emitted_in_order(tmp_path):
    events = []
    reg = Registry([FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360)])], disabled=set())
    run(reg, tmp_path, levels=[1], on_event=events.append)
    types = [e.type for e in events]
    assert types[0] == "run_started" and types[1] == "release_identified" and types[-1] == "run_finished"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    finished = next(e for e in events if e.type == "stage_finished" and e.stage == "search")
    assert finished.data["candidates"] == 1
