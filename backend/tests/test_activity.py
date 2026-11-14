from audioresearch.events import RunEvent
from fastapi.testclient import TestClient

from app.activity import Activity
from app.main import app


def ev(seq, type, level=None, adapter=None, stage=None, **data):
    return RunEvent("run", seq, 0, type, level, adapter, stage, None, data)


def test_a_search_job_records_its_timed_steps():
    a = Activity(enabled=True)
    a.job_started({"id": 7, "type": "audio", "record_id": 3, "params": {"refresh": True}})
    a.on_event(ev(1, "release_identified", track_count=4))
    a.on_event(ev(2, "level_started", level=2, unfound=4, adapters=["bandcamp"]))
    a.on_event(ev(3, "stage_started", 2, "bandcamp", "search", tracks=4))
    now = a.snapshot()["current"]
    assert now["tracks"] == 4 and now["steps"][0]["open"] and now["steps"][0]["ms"] is None

    a.on_event(ev(4, "stage_finished", 2, "bandcamp", "search", ms=1234, candidates=5))
    a.on_event(ev(5, "level_finished", 2, resolved=["A1"], unfound=[], ms=1500))
    a.on_event(ev(6, "run_finished", found=3))
    a.job_finished(7, "done")

    snap = a.snapshot()
    assert snap["current"] is None
    job = snap["recent"][0]
    assert job["status"] == "done" and job["found"] == 3 and job["finished"] >= job["started"]
    assert job["steps"] == [{"level": 2, "adapter": "bandcamp", "stage": "search", "started": job["steps"][0]["started"],
                             "ms": 1234, "open": False, "tracks": 4, "detail": {"candidates": 5}}]
    assert job["levels"][0]["ms"] == 1500 and job["levels"][0]["resolved"] == 1


def test_a_failed_job_closes_its_open_steps():
    a = Activity(enabled=True)
    a.job_started({"id": 1, "type": "audio"})
    a.on_event(ev(1, "stage_started", 3, "youtube", "search"))
    a.job_finished(1, "failed", "boom")
    job = a.snapshot()["recent"][0]
    assert job["error"] == "boom" and not job["steps"][0]["open"] and job["steps"][0]["ms"] is not None


def test_off_outside_the_test_run():
    a = Activity(enabled=False)
    a.job_started({"id": 1, "type": "audio"})
    a.on_event(ev(1, "stage_started", 3, "youtube", "search"))
    assert a.snapshot() == {"now": a.snapshot()["now"], "current": None, "recent": []}
    assert TestClient(app).get("/api/debug/activity").status_code == 404


def test_the_panel_feed_in_a_test_run(db_path, monkeypatch):
    from app.activity import activity
    monkeypatch.setattr(activity, "enabled", True)
    with TestClient(app) as client:
        body = client.get("/api/debug/activity").json()
    assert {"now", "current", "recent", "queued"} <= set(body)
