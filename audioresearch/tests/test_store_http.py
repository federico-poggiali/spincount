import pytest
import requests

from audioresearch.adapters import Registry
from audioresearch.adapters.base import AdapterError
from audioresearch.adapters.fake import FakeAdapter
from audioresearch.health import AdapterHealth
from audioresearch.http import HttpClient, HttpError
from audioresearch.models import Candidate, Quality, ReleaseIdentity, Status, TrackRef
from audioresearch.pipeline import research
from audioresearch.store import MIGRATIONS, Store


def identity():
    return ReleaseIdentity(77, "Foo", "EP", "L", "C1", 2020,
                           [TrackRef("A1", "Foo", "Night Drive", 360), TrackRef("A2", "Foo", "Morning Light", 400)])


def cand(adapter, pos, title, dur):
    return Candidate(adapter, 1, "track", f"https://{adapter}/{pos}", title, "Foo", dur, position=pos)


def test_cached_rerun_makes_no_adapter_calls_and_refresh_does(tmp_path):
    store = Store(tmp_path / "t.db")
    a = FakeAdapter("yt", 1, [cand("yt", "A1", "Night Drive", 360)])
    reg = Registry([a], disabled=set())
    r1 = research("77", [1], identity=identity(), registry=reg, store=store, audio_dir=tmp_path)
    assert len(a.searched) == 1 and a.fetched == ["https://yt/A1"]
    r2 = research("77", [1], identity=identity(), registry=reg, store=store, audio_dir=tmp_path)
    assert len(a.searched) == 1 and len(a.fetched) == 1
    assert r2.to_dict() == r1.to_dict()
    research("77", [1], refresh=True, identity=identity(), registry=reg, store=store, audio_dir=tmp_path)
    assert len(a.searched) == 2


def test_wider_levels_reuse_cached_searches(tmp_path):
    store = Store(tmp_path / "t.db")
    a1, a2 = FakeAdapter("yt", 1, [cand("yt", "A1", "Night Drive", 360)]), FakeAdapter("bc", 2, [cand("bc", "A2", "Morning Light", 400)])
    reg = Registry([a1, a2], disabled=set())
    research("77", [1], identity=identity(), registry=reg, store=store, audio_dir=tmp_path)
    research("77", [1, 2], identity=identity(), registry=reg, store=store, audio_dir=tmp_path)
    assert len(a1.searched) == 1 and len(a2.searched) == 1


def test_not_found_is_stored_with_a_date_and_events_replay(tmp_path):
    store = Store(tmp_path / "t.db")
    events = []
    res = research("77", [1], identity=identity(), registry=Registry([FakeAdapter("yt", 1)], disabled=set()),
                   store=store, audio_dir=tmp_path, on_event=events.append, run_id="r1")
    assert res.track("A1").status == Status.NOT_FOUND
    result, levels, when = store.get_result(77)
    assert levels == [1] and when.endswith("Z") and result.track("A2").status == Status.NOT_FOUND
    assert [e.to_dict() for e in store.get_events("r1")] == [e.to_dict() for e in events]
    assert store.list_runs()[0]["title"] == "Foo - EP"


def test_provenance_records_accepted_and_rejected(tmp_path):
    store = Store(tmp_path / "t.db")
    a = FakeAdapter("yt", 1, [cand("yt", "A1", "Night Drive", 360), cand("yt", "A2", "Totally Different Song", 100)])
    research("77", [1], identity=identity(), registry=Registry([a], disabled=set()), store=store, audio_dir=tmp_path, run_id="r2")
    prov = store.get_provenance(77)
    assert {(p["url"], p["outcome"]) for p in prov} == {("https://yt/A1", "accepted"), ("https://yt/A2", "rejected")}


def test_migrations_are_idempotent(tmp_path):
    Store(tmp_path / "m.db").close()
    s = Store(tmp_path / "m.db")
    assert s.db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_failing_adapter_is_switched_off(tmp_path):
    events = []
    a = FakeAdapter("bad", 1, search_error=True)
    reg = Registry([a], disabled=set())
    ident = identity()
    # five consecutive failures across levels/calls switch it off: simulate with a health object
    h = AdapterHealth(max_failures=2)
    assert not h.fail("bad", "x") and h.fail("bad", "y") and h.is_off("bad") and h.off == {"bad": "y"}
    res = research("77", [1, 1], identity=ident, registry=reg, audio_dir=tmp_path, on_event=events.append)
    assert res.adapters_off == [] and all(t.status == Status.NOT_FOUND for t in res.tracks)  # one failure: still on


def test_adapter_off_after_n_failures_in_one_run(tmp_path, monkeypatch):
    from audioresearch import config
    monkeypatch.setattr(config, "HEALTH_MAX_FAILURES", 2)
    events = []
    a = FakeAdapter("bad", 1, [cand("bad", "A1", "Night Drive", 360), cand("bad", "A2", "Morning Light", 400)],
                    fetch_errors={"https://bad/A1", "https://bad/A2"})
    res = research("77", [1], identity=identity(), registry=Registry([a], disabled=set()), audio_dir=tmp_path,
                   on_event=events.append)
    assert res.adapters_off == ["bad"] and any(e.type == "adapter_off" for e in events)


class FakeResp:
    def __init__(self, status=200, text="ok", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}

    def json(self):
        return {"a": 1}


class FakeSession:
    def __init__(self, script):
        self.script, self.headers, self.n = list(script), {}, 0

    def request(self, method, url, **kw):
        self.n += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(script, sleeps, delay=2.0, now=[0.0]):
    clock = lambda: now[0]  # noqa: E731
    def sleep(s):
        sleeps.append(s)
        now[0] += s
    return HttpClient(FakeSession(script), sleep=sleep, clock=clock, delay_for=lambda site: delay, backoff=1.0)


def test_rate_limiter_spaces_calls():
    sleeps = []
    c = client([FakeResp(), FakeResp(), FakeResp()], sleeps)
    for _ in range(3):
        c.get("https://x/", site="deejay_de")
    assert sleeps == [2.0, 2.0] and c.calls == 3


def test_retries_429_then_succeeds_and_counts():
    sleeps = []
    c = client([FakeResp(429), FakeResp(503), FakeResp(200, "fine")], sleeps, delay=0)
    assert c.get_text("https://x/", site="s", adapter="a") == "fine"
    assert sleeps == [1.0, 2.0] and c.stats["a"] == {"requests": 3, "failures": 0}


def test_gives_up_and_404_is_not_retried():
    c = client([requests.ConnectionError("down")] * 4, [], delay=0)
    with pytest.raises(HttpError):
        c.get("https://x/", site="s", adapter="a")
    assert c.stats["a"]["failures"] == 1 and c.calls == 4
    c2 = client([FakeResp(404)], [], delay=0)
    with pytest.raises(HttpError) as e:
        c2.get("https://x/", site="s")
    assert e.value.status == 404 and c2.calls == 1 and isinstance(e.value, AdapterError)
