"""The audio stage: audioresearch's contract is stored per track, shown by the API, and never blocks analysis."""
from app.analysis.job import make_handler
from app.audio import job as audio_job
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

    def __call__(self, release_id, audio_dir, refresh, everything=False):
        self.calls.append((release_id, refresh))
        self.everything = everything
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
    audio = {a["track_id"]: a for a in client.get(f"/api/records/{rid}/audio").json()["tracks"]}
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
    assert client.get(f"/api/records/{rid}/audio").json()["tracks"] == []


def test_an_unknown_contract_version_is_refused(client, db_path):
    rid, *_ = setup_record(db_path)
    job = run_analysis(client, rid, Research(result=contract(version=2)))
    assert job["status"] == "done"
    assert "contract version" in job["result"]["audio_research"]["error"]
    assert client.get(f"/api/records/{rid}/audio").json()["tracks"] == []


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
    body = client.post("/api/admin/find-audio").json()
    assert body["queued"] == 1
    assert client.get(f"/api/jobs/{body['job_ids'][0]}").json()["record_id"] == rid
    assert client.post("/api/admin/find-audio").json()["queued"] == 1  # nothing ran, still not searched


def test_deleting_a_track_removes_its_audio(client, db_path):
    rid, t1, _ = setup_record(db_path)
    run_analysis(client, rid, Research())
    conn = connect(db_path)
    conn.execute("DELETE FROM tracks WHERE id = ?", (t1,))
    conn.commit()
    assert t1 not in track_audio.for_record(conn, rid)
    conn.close()


def run_audio_job(client, rid, research, body=None):
    runner = JobRunner({"audio": audio_job.make_handler(research)})
    client.app.state.runner = runner
    job_id = client.post(f"/api/records/{rid}/find-audio", json=body).json()["job_id"]
    runner.run_pending()
    return client.get(f"/api/jobs/{job_id}").json()


def test_the_audio_job_finds_audio_without_analysing(client, db_path):
    rid, t1, _ = setup_record(db_path)
    job = run_audio_job(client, rid, Research())
    assert job["status"] == "done"
    detail = client.get(f"/api/records/{rid}").json()
    assert all(t["proposal"] is None and t["bpm"] is None for t in detail["tracks"])  # BPM and key untouched
    assert {a["track_id"] for a in client.get(f"/api/records/{rid}/audio").json()["tracks"]} == {t1, setup_ids(detail)[1]}


def setup_ids(detail):
    return [t["id"] for t in detail["tracks"]]


def test_the_audio_job_fails_visibly_and_can_search_again(client, db_path):
    rid, *_ = setup_record(db_path)
    research = Research(error=RuntimeError("site down"))
    job = run_audio_job(client, rid, research)
    assert job["status"] == "failed" and "site down" in job["error"]
    research.error = None
    run_audio_job(client, rid, research)
    run_audio_job(client, rid, research, {"refresh": True})
    assert [refresh for _, refresh in research.calls] == [False, False, True]


def test_finding_more_sources_searches_everything_even_when_audio_was_found(client, db_path):
    rid, *_ = setup_record(db_path)
    research = Research()
    run_audio_job(client, rid, research)
    run_audio_job(client, rid, research, {"everything": True})
    assert len(research.calls) == 2 and research.everything is True


def test_analysis_reuses_audio_found_on_add(client, db_path):
    rid, *_ = setup_record(db_path)
    research = Research()
    run_audio_job(client, rid, research)
    job = run_analysis(client, rid, research)
    assert len(research.calls) == 1
    assert job["result"]["audio_research"]["ran"] is False


def test_previews_follow_the_viewer_rules(client, db_path):
    """One source family for the whole record where possible; links that cannot play in a page are left out."""
    rid, t1, t2 = setup_record(db_path)
    yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = contract()
    result["tracks"][0].update(source="discogs_youtube", url=yt, page=None,
                               alternatives=[{"source": "bandcamp", "url": "https://a.bandcamp.com/track/1",
                                              "quality": "full", "confidence": 0.9}])
    result["tracks"][1].update(status="found", source="discogs_youtube", quality="full", confidence=0.8,
                               url="https://youtu.be/abcdefghijk")
    run_audio_job(client, rid, Research(result=result))
    previews = client.get(f"/api/records/{rid}/audio").json()["previews"]
    assert previews["families"] == [{"family": "youtube", "tracks": ["A1", "A2"]}]
    assert previews["tracks"]["A1"]["kind"] == "youtube" and previews["tracks"]["A1"]["embed_id"] == "dQw4w9WgXcQ"
    assert previews["tracks"]["A2"]["embed_id"] == "abcdefghijk"


def test_store_pages_are_offered(client, db_path):
    rid, *_ = setup_record(db_path)
    result = contract()
    result["tracks"][0].update(source="redeye", level=5, quality="clip", url="https://x.redeye/clip.mp3",
                               page="https://www.redeyerecords.co.uk/vinyl/1")
    run_audio_job(client, rid, Research(result=result))
    previews = client.get(f"/api/records/{rid}/audio").json()["previews"]
    assert previews["stores"]["A1"] == [{"source": "redeye", "page": "https://www.redeyerecords.co.uk/vinyl/1"}]
    assert previews["tracks"]["A1"]["kind"] == "audio"


def test_your_files_play_only_from_the_audio_folder(client, db_path, audio_dir):
    rid, t1, t2 = setup_record(db_path)
    mine = audio_dir / "9261843" / "A1 - First.mp3"
    mine.parent.mkdir()
    mine.write_bytes(b"ID3fake")
    result = contract()
    result["tracks"][0].update(source="local_files", level=0, audio_path=str(mine), url=None)
    result["tracks"][1].update(status="found", source="local_files", level=0, audio_path="/etc/hosts", url=None)
    run_audio_job(client, rid, Research(result=result))
    assert client.get(f"/api/tracks/{t1}/audio-file").content == b"ID3fake"
    assert client.get(f"/api/tracks/{t2}/audio-file").status_code == 404  # outside AUDIO_DIR: never served
    assert client.get(f"/api/records/{rid}/audio").json()["previews"]["tracks"]["A1"]["kind"] == "file"


def test_upload_audio_saves_into_the_records_folder(client, db_path, audio_dir):
    rid, _, _ = setup_record(db_path)
    url = f"/api/records/{rid}/upload-audio"
    sent = client.post(url, params={"filename": "A1 - First.mp3"}, content=b"ID3fake")
    assert sent.status_code == 201 and sent.json() == {"file": "A1 - First.mp3"}
    assert (audio_dir / "9261843" / "A1 - First.mp3").read_bytes() == b"ID3fake"
    assert client.post(url, params={"filename": "notes.txt"}, content=b"x").status_code == 422
    assert client.post(url, params={"filename": "../x.mp3"}, content=b"x").status_code == 422
    assert client.post(url, params={"filename": "empty.mp3"}, content=b"").status_code == 422
    assert not (audio_dir / "9261843" / "empty.mp3").exists()
    assert client.post("/api/records/999/upload-audio", params={"filename": "a.mp3"}, content=b"x").status_code == 404


def test_bandcamp_embed_rejects_other_sites(client):
    assert client.get("/api/audio/bandcamp-embed", params={"url": "https://evil.example/x"}).status_code == 400


def test_find_audio_needs_a_release(client, db_path):
    conn = connect(db_path)
    rid = records.create(conn, artist="A", title="B")
    conn.close()
    assert client.post(f"/api/records/{rid}/find-audio").status_code == 400
    assert client.post("/api/records/999/find-audio").status_code == 404
