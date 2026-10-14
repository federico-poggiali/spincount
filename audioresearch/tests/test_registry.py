from pathlib import Path

from audioresearch.adapters import Registry, default_registry
from audioresearch.adapters.fake import FakeAdapter
from audioresearch.models import Candidate, Quality, ReleaseIdentity, TrackRef


def cand(adapter, level, pos, title="One"):
    return Candidate(adapter, level, "track", f"https://{adapter}/{pos}", title, "Art", 200, position=pos)


def registry():
    return Registry([
        FakeAdapter("local", 0), FakeAdapter("yt", 1, group="youtube"), FakeAdapter("yt2", 1, group="youtube"),
        FakeAdapter("itunes", 1, max_quality=Quality.PREVIEW), FakeAdapter("bc", 2),
    ], disabled=set())


def test_adapters_per_level_and_groups():
    r = registry()
    assert [a.name for a in r.for_level(1)] == ["yt", "yt2", "itunes"]
    assert [[a.name for a in g] for g in r.groups(1)] == [["yt", "yt2"], ["itunes"]]
    assert r.for_level(5) == []


def test_config_switch():
    r = registry()
    r.switch("yt2", False)
    assert [[a.name for a in g] for g in r.groups(1)] == [["yt"], ["itunes"]]
    r.switch("yt2", True)
    assert len(r.for_level(1)) == 3
    assert Registry([FakeAdapter("x", 1)], disabled={"x"}).for_level(1) == []


def test_fake_adapter_returns_canned_candidates(tmp_path):
    a = FakeAdapter("fake", 1, [cand("fake", 1, "A1"), cand("fake", 1, "B1")])
    rel = ReleaseIdentity(1, "Art", "Rel", None, None, None, [])
    got = a.search(rel, [TrackRef("A1", "Art", "One", 200)])
    assert [c.position for c in got] == ["A1"] and a.searched == [["A1"]]
    f = a.fetch(got[0], tmp_path / "A1.fake")
    assert Path(f.path).exists() and f.duration == 200.0


def test_default_registry_builds_without_error():
    default_registry(disabled=set())
