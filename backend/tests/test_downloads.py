"""Downloaded audio is temporary: deleted once its track's analysis is validated or discarded, cleared from
Settings, and downloaded again when the track is analysed again. Your own files are never touched."""
from app import config
from app.analysis.job import make_handler
from app.db import connect, records, track_audio, tracks
from app.jobs.runner import JobRunner
from tests.test_audio import Research, contract

RESULT = {"bpm": 124.0, "key": "A minor", "camelot_key": "8A", "confidence": 0.7, "raw": {}}


def download(track_id: int, name: str = "A1.discogs_youtube.webm", alternatives=()):
    """A track whose audio the search found and downloaded into the cache."""
    path = config.AUDIO_CACHE_DIR / "9261843" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 10)
    conn = connect(config.DB_PATH)
    track_audio.put(conn, track_id, status="found", source="discogs_youtube", level=1, quality="full",
                    confidence=0.9, reason="", url="https://youtu.be/x", page=None, audio_path=str(path),
                    readings=[], alternatives=list(alternatives), found_at="2026-11-14T00:00:00Z")
    conn.close()
    return path


def setup(db_path, status="owned"):
    conn = connect(db_path)
    rid = records.create(conn, artist="A", title="B", discogs_release_id=9261843, status=status)
    t1 = tracks.create(conn, rid, position="A1", title="First")
    t2 = tracks.create(conn, rid, position="A2", title="Second")
    conn.close()
    return rid, t1, t2


def analyse(client, rid, research=None, **body):
    runner = JobRunner({"analysis": make_handler(analyze=lambda path: RESULT, research_fn=research)})
    client.app.state.runner = runner
    resp = client.post(f"/api/records/{rid}/analyze", json=body or None)
    assert resp.status_code == 202, resp.json()
    runner.run_pending()
    return client.get(f"/api/jobs/{resp.json()['job_id']}").json()


def test_validating_deletes_the_download_but_keeps_the_result(client, db_path, audio_dir):
    rid, t1, _ = setup(db_path)
    alt = config.AUDIO_CACHE_DIR / "9261843" / "A1.itunes.m4a"
    path = download(t1, alternatives=[{"source": "itunes", "audio_path": str(alt)}])
    alt.write_bytes(b"y")
    analyse(client, rid)
    assert path.is_file()                                    # kept while the result waits for you
    detail = client.post(f"/api/records/{rid}/validate", json={"track_ids": [t1]}).json()
    assert detail["tracks"][0]["bpm"] == 124.0
    assert not path.exists() and not alt.exists()


def test_discarding_deletes_the_download_too(client, db_path, audio_dir):
    rid, t1, _ = setup(db_path)
    path = download(t1)
    analyse(client, rid)
    client.post(f"/api/records/{rid}/discard")
    assert not path.exists()


def test_your_own_files_are_never_deleted(client, db_path, audio_dir):
    rid, t1, _ = setup(db_path)
    mine = audio_dir / "9261843" / "A1.wav"
    mine.parent.mkdir()
    mine.write_bytes(b"x")
    conn = connect(db_path)
    track_audio.put(conn, t1, status="found", source="local_files", level=0, quality="full", confidence=1.0,
                    reason="your own file", url=str(mine), page=None, audio_path=str(mine), readings=[],
                    alternatives=[], found_at="2026-11-14T00:00:00Z")
    conn.close()
    analyse(client, rid)
    client.post(f"/api/records/{rid}/validate", json={"track_ids": [t1]})
    client.post("/api/admin/clear-downloads")
    assert mine.is_file()


def test_clear_keeps_only_what_a_track_still_needs(client, db_path, audio_dir):
    rid, t1, t2 = setup(db_path)
    waiting = download(t1)                                   # analysed, waiting for validation: kept
    never = download(t2, "A2.discogs_youtube.webm")          # never analysed: kept
    analyse(client, rid, track_ids=[t1])
    orphan = config.AUDIO_CACHE_DIR / "555" / "B1.bandcamp.mp3"   # a rejected candidate: no track uses it
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"z" * 5)
    assert client.get("/api/admin/downloads").json() == {"files": 3, "bytes": 25}
    out = client.post("/api/admin/clear-downloads").json()
    assert (out["deleted"], out["freed_bytes"], out["files"]) == (1, 5, 2)
    assert waiting.is_file() and never.is_file() and not orphan.parent.exists()


def test_analysing_again_downloads_the_audio_again(client, db_path, audio_dir):
    rid, t1, _ = setup(db_path)
    path = download(t1)
    analyse(client, rid)
    client.post(f"/api/records/{rid}/validate", json={"track_ids": [t1]})
    assert not path.exists()
    assert t1 in client.get(f"/api/records/{rid}/audio").json()["analysable_track_ids"]

    class Refetch(Research):
        def __call__(self, release_id, audio_dir, refresh, everything=False, sources_off=()):
            path.write_bytes(b"again")
            found = {**contract()["tracks"][0], "source": "discogs_youtube", "audio_path": str(path)}
            self.result = contract(tracks=[found])
            return super().__call__(release_id, audio_dir, refresh, everything, sources_off)

    research = Refetch()
    job = analyse(client, rid, research)
    assert research.calls == [(9261843, True)]
    assert job["result"]["from_found_audio_track_ids"] == [t1]
    assert job["result"]["searched_again"]["ran"] is True
