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


def youtube_then_itunes(fetch_errors=None):
    yt = FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360), tc("yt", 1, "A2", "Morning Light", 400)],
                     group="youtube", fetch_errors=fetch_errors)
    it = FakeAdapter("it", 1, [tc("it", 1, p, t, q=Quality.PREVIEW) for p, t in
                               (("A1", "Night Drive"), ("A2", "Morning Light"), ("B1", "Deep Water"))],
                     group="youtube", max_quality=Quality.PREVIEW)
    return Registry([yt, it], disabled=set())


def test_fallback_searches_only_the_tracks_its_group_did_not_match(tmp_path):
    reg = youtube_then_itunes()
    res = run(reg, tmp_path)
    assert reg.get("it").searched == [["B1"]]   # not A1/A2: the YouTube links matched them
    assert [(t.position, t.source) for t in res.tracks] == [("A1", "yt"), ("A2", "yt"), ("B1", "it")]


def test_fallback_searches_again_when_its_groups_match_failed(tmp_path):
    reg = youtube_then_itunes(fetch_errors={"https://yt/A2"})   # matched, but the download is refused
    res = run(reg, tmp_path)
    assert reg.get("it").searched == [["B1"], ["A2"]]   # second pass: only A2, B1 is not searched twice
    assert [(t.position, t.source) for t in res.tracks] == [("A1", "yt"), ("A2", "it"), ("B1", "it")]


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


def test_search_all_never_stops_and_searches_every_level_for_every_track(tmp_path):
    def reg():
        return Registry([FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360), tc("yt", 1, "A2", "Morning Light", 400),
                                               tc("yt", 1, "B1", "Deep Water", 380)]),
                         FakeAdapter("bc", 2, [tc("bc", 2, "A1", "Night Drive", 360)])], disabled=set())
    normal, everything = reg(), reg()
    run(normal, tmp_path)
    assert normal.get("bc").searched == []
    events = []
    res = run(everything, tmp_path, search_all=True, on_event=events.append)
    assert everything.get("bc").searched == [["A1", "A2", "B1"]]
    assert all(t.status == Status.FOUND for t in res.tracks)
    matched = [(e.level, e.position) for e in events if e.type == "candidate_matched"]
    assert (1, "A1") in matched and (2, "A1") in matched
    assert [a["source"] for a in res.track("A1").alternatives] in (["bc"], ["yt"])
    assert next(e for e in events if e.type == "run_started").data["search_all"] is True


def test_a_track_with_a_file_of_yours_is_not_searched_even_when_searching_everything(tmp_path):
    mine = FakeAdapter("mine", 0, [tc("mine", 0, "A1", "Night Drive", extra={"trusted": True})])
    yt = FakeAdapter("yt", 1, [tc("yt", 1, p, t, d) for p, t, d in (("A1", "Night Drive", 360), ("A2", "Morning Light", 400))])
    res = run(Registry([mine, yt], disabled=set()), tmp_path, search_all=True)
    assert yt.searched == [["A2", "B1"]]
    assert [(t.position, t.level) for t in res.tracks][:2] == [("A1", 0), ("A2", 1)]


def test_a_search_that_stops_progressing_is_halted_and_keeps_what_it_found(tmp_path):
    import time

    yt = FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360)])
    stuck = FakeAdapter("stuck", 2, [tc("stuck", 2, "A2", "Morning Light", 400)], delay=5)   # a site that hangs
    started = time.monotonic()
    res = run(Registry([yt, stuck], disabled=set()), tmp_path, stall_seconds=0.5)
    assert time.monotonic() - started < 3
    assert res.halted == "nothing progressed for 0 s"
    assert [(t.position, t.status) for t in res.tracks] == [("A1", Status.FOUND), ("A2", Status.NOT_FOUND), ("B1", Status.NOT_FOUND)]
    assert res.tracks[1].reason.startswith("search stopped")


def test_a_search_that_keeps_progressing_is_not_halted(tmp_path):
    yt = FakeAdapter("yt", 1, [tc("yt", 1, "A1", "Night Drive", 360)], delay=0.2)
    res = run(Registry([yt], disabled=set()), tmp_path, stall_seconds=5)
    assert res.halted is None and res.tracks[0].status == Status.FOUND
