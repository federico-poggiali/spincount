"""The audio stage: audioresearch's contract is stored per track, shown by the API, and never blocks analysis."""
from app.analysis.job import make_handler
from app.db import connect, records, track_audio, tracks
from app.jobs.runner import JobRunner
from tests.conftest import make_discogs


def contract(release_id=9261843, version=1, **extra):
    return {"contract_version": version, "discogs_release_id": release_id, "adapters_off": ["decks_de"],
            "generated_at": "2026-10-14T00:00:00Z",
            "tracks": [
                {"position": "A1", "status": "found", "audio_path": "/x/A1.mp3", "page": "https://a.bandcamp.com/album/b",
                 "source": "bandcamp", "level": 2, "url": "https://a.bandcamp.com/track/1", "quality": "full",
                 "confidence": 0.92, "reason": "Bandcamp release matched on tracklist",
                 "readings": [{"source": "deejay_de", "bpm": 124.0, "key": None}], "alternatives": [{"source": "itunes"}]},
                {"position": "A2", "status": "not_found", "audio_path": None, "page": None, "source": None, "level": None,
                 "url": None, "quality": None, "confidence": 0.0, "reason": "not found at any level",
                 "readings": [], "alternatives": []},
                {"position": "Z9", "status": "found", "source": "bandcamp", "confidence": 0.9, "reason": "no such track"},
            ], **extra}


def setup_record(db_path):
    conn = connect(db_path)
    rid = records.create(conn, artist="A", title="B", discogs_release_id=9261843)
    t1 = tracks.create(conn, rid, position="A1", title="First")
    t2 = tracks.create(conn, rid, position="A2", title="Second")
    conn.close()
    return rid, t1, t2


class Research:
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    def __call__(self, release_id, audio_dir, refresh):
        self.calls.append((release_id, refresh))
        if self.error:
            raise self.error
        return self.result or contract()


def run_analysis(client, rid, research, body=None):
    runner = JobRunner({"analysis": make_handler(make_discogs, lookup_fn=lambda r, t, rel: {}, research_fn=research)})
    client.app.state.runner = runner
    job_id = client.post(f"/api/records/{rid}/analyze", json=body).json()["job_id"]
    runner.run_pending()
    return client.get(f"/api/jobs/{job_id}").json()


def test_audio_is_found_stored_and_shown(client, db_path):
    rid, t1, t2 = setup_record(db_path)
    research = Research()
    job = run_analysis(client, rid, research)
    assert job["status"] == "done"
    assert research.calls == [(9261843, False)]
    assert job["result"]["audio_research"]["counts"] == {"found": 2, "not_found": 1}
    audio = {a["track_id"]: a for a in client.get(f"/api/records/{rid}/audio").json()}
    assert set(audio) == {t1, t2}  # the contract's unknown track Z9 is ignored
    assert (audio[t1]["status"], audio[t1]["source"], audio[t1]["quality"], audio[t1]["confidence"]) == \
        ("found", "bandcamp", "full", 0.92)
    assert audio[t1]["page"] == "https://a.bandcamp.com/album/b"
    assert audio[t1]["readings"][0]["bpm"] == 124.0
    assert audio[t2]["status"] == "not_found"


def test_analysing_again_reuses_the_audio_unless_asked(client, db_path):
    rid, *_ = setup_record(db_path)
    research = Research()
    run_analysis(client, rid, research)
    again = run_analysis(client, rid, research)
    assert len(research.calls) == 1
    assert again["result"]["audio_research"] == {"ran": False, "reason": "audio already found", "stored_track_ids": []}
    run_analysis(client, rid, research, {"refresh_audio": True})
    assert research.calls[-1] == (9261843, True)


def test_a_failed_audio_search_never_stops_the_analysis(client, db_path):
    rid, *_ = setup_record(db_path)
    job = run_analysis(client, rid, Research(error=RuntimeError("site down")))
    assert job["status"] == "done"
    assert "site down" in job["result"]["audio_research"]["error"]
    assert client.get(f"/api/records/{rid}/audio").json() == []


def test_an_unknown_contract_version_is_refused(client, db_path):
    rid, *_ = setup_record(db_path)
    job = run_analysis(client, rid, Research(result=contract(version=2)))
    assert job["status"] == "done"
    assert "contract version" in job["result"]["audio_research"]["error"]
    assert client.get(f"/api/records/{rid}/audio").json() == []


def test_audio_endpoint_404_for_unknown_record(client):
    assert client.get("/api/records/999/audio").status_code == 404


def test_library_run_queues_only_records_without_audio(client, db_path):
    rid, t1, _ = setup_record(db_path)
    conn = connect(db_path)
    done = records.create(conn, artist="C", title="D", discogs_release_id=111)
    d1 = tracks.create(conn, done, position="A1", title="x")
    records.create(conn, artist="E", title="F", discogs_release_id=222)  # no tracks: nothing to search for
    track_audio.put(conn, d1, status="found", source="s", level=1, quality="full", confidence=0.9, reason="",
                    url=None, page=None, audio_path=None, readings=[], alternatives=[], found_at="2026-10-14T00:00:00Z")
    conn.close()
    body = client.post("/api/admin/find-audio-and-analyse").json()
    assert body["queued"] == 1
    assert client.get(f"/api/jobs/{body['job_ids'][0]}").json()["record_id"] == rid
    assert client.post("/api/admin/find-audio-and-analyse").json()["queued"] == 1  # nothing ran, still not searched


def test_deleting_a_track_removes_its_audio(client, db_path):
    rid, t1, _ = setup_record(db_path)
    run_analysis(client, rid, Research())
    conn = connect(db_path)
    conn.execute("DELETE FROM tracks WHERE id = ?", (t1,))
    conn.commit()
    assert t1 not in track_audio.for_record(conn, rid)
    conn.close()
