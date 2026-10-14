import json
import time

from fastapi.testclient import TestClient

from audioresearch.adapters.fake import demo_registry
from audioresearch.store import Store
from audioresearch.tests.test_identify import _client
from audioresearch.viewer.app import create_app


def make(tmp_path):
    store = Store(tmp_path / "v.db")
    app = create_app(store, fake=True, discogs=_client(), audio_dir=tmp_path / "audio", poll=0.02)
    return store, TestClient(app)


def sse(client, run_id):
    events = []
    with client.stream("GET", f"/runs/{run_id}/events") as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_viewer_runs_a_release_streams_and_replays(tmp_path):
    store, client = make(tmp_path)
    assert client.get("/").status_code == 200
    run_id = client.post("/runs", json={"url": "https://www.discogs.com/release/9261843"}).json()["run_id"]
    events = sse(client, run_id)
    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[1] == "release_identified" and types[-1] == "run_finished"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    started = [e["level"] for e in events if e["type"] == "level_started"]
    # levels run in order and stop early once every track is found
    assert started == list(range(len(started))) and started
    assert types.count("level_finished") == len(started)
    stages = {(e["level"], e["stage"]) for e in events if e["type"] == "stage_finished"}
    assert (1, "search") in stages and (1, "decide") in stages
    finished = events[-1]["data"]
    result = client.get(f"/runs/{run_id}").json()
    counts = {s: sum(t["status"] == s for t in result["tracks"]) for s in ("found", "review", "not_found")}
    assert {k: finished[k] for k in counts} == counts  # summary matches the final result
    assert sse(client, run_id) == events              # a stored run replays the same events
    assert client.get("/runs").json()[0]["run_id"] == run_id


def test_viewer_reports_a_failed_run(tmp_path):
    store, client = make(tmp_path)
    run_id = client.post("/runs", json={"url": "not a discogs url"}).json()["run_id"]
    events = sse(client, run_id)
    assert events[-1]["type"] == "run_failed" and "Discogs" in events[-1]["data"]["error"]
    assert client.get("/runs/nope/events").status_code == 404


def test_viewer_result_carries_a_preview_plan(tmp_path):
    store, client = make(tmp_path)
    run_id = client.post("/runs", json={"url": "https://www.discogs.com/release/9261843"}).json()["run_id"]
    sse(client, run_id)
    result = client.get(f"/runs/{run_id}").json()
    assert set(result["previews"]["tracks"]) == {t["position"] for t in result["tracks"]}
    assert client.get("/embed/bandcamp", params={"url": "https://evil.example/x"}).status_code == 400
    assert client.get(f"/runs/{run_id}/local/ZZ9").status_code == 404
