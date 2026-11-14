from datetime import UTC, datetime, timedelta

import pytest

from app import backup, library_sync, sync
from app.db import connect, crate, notes, records, settings
from app.jobs.runner import JobRunner
from tests.conftest import make_discogs

SIMPLE, HEADING, CD = 9261843, 46673, 12472  # releases the fake Discogs knows


def url(release_id: int) -> str:
    return f"https://www.discogs.com/release/{release_id}"


@pytest.fixture
def runner(client, collection, wants):
    def factory():
        return make_discogs(collection=collection, wants=wants)
    client.app.state.runner = r = JobRunner({**library_sync.make_handlers(factory),
                                             sync.JOB_TYPE: sync.make_handler(factory)})
    return r


@pytest.fixture
def backups(tmp_path, monkeypatch):
    path = tmp_path / "backups"
    monkeypatch.setattr(backup, "BACKUP_DIR", path)
    return path


def add(client, release_id: int, status: str = "owned") -> dict:
    return client.post("/api/records/intake", json={"discogs_url": url(release_id), "status": status}).json()


def job(client, job_id: int) -> dict:
    return client.get(f"/api/jobs/{job_id}").json()


def library(client):
    """Owned SIMPLE (not on Discogs) and wishlist CD; each test fills the fake collection itself."""
    client.patch("/api/settings", json={"auto_collection": False})  # adding must not reach Discogs here
    owned = add(client, SIMPLE)
    wished = add(client, CD, "wantlist")
    return owned, wished


# ---- settings ----

def test_settings_default_to_collection_on_and_wantlist_off(client):
    off = {"auto_collection": True, "auto_wantlist": False, "import_every_min": 0, "push_every_min": 0,
           "youtube_playlist": False, "audio_search_lengthy": False, "audio_sources_off": []}
    assert client.get("/api/settings").json() == off
    assert client.patch("/api/settings", json={"auto_wantlist": True}).json() == {**off, "auto_wantlist": True}


def test_intake_follows_the_settings(client, runner, wants, collection):
    client.patch("/api/settings", json={"auto_collection": False, "auto_wantlist": True})
    owned = add(client, SIMPLE)
    assert set(owned["jobs"]) == {"audio"}  # nothing goes to the Discogs collection
    wished = add(client, CD, "wantlist")
    assert set(wished["jobs"]) == {"audio", "discogs_want"}
    runner.run_pending()
    assert wants == {CD} and collection == {}
    assert client.get(f"/api/records/{wished['id']}").json()["status"] == "wantlist"


def test_moving_to_owned_skips_discogs_when_auto_collection_is_off(client, runner, collection):
    client.patch("/api/settings", json={"auto_collection": False})
    wished = add(client, CD, "wantlist")
    client.patch(f"/api/records/{wished['id']}", json={"status": "owned"})
    runner.run_pending()
    assert collection == {}


# ---- compare and the three syncs ----

def test_compare_lists_what_differs_and_changes_nothing(client, collection):
    owned, wished = library(client)
    collection.update({HEADING: [1], CD: [2]})
    out = client.get("/api/discogs-sync/compare").json()
    assert [i["id"] for i in out["to_discogs"]] == [owned["id"]]
    assert [i["discogs_release_id"] for i in out["to_import"]] == [HEADING]
    assert out["to_import"][0]["id"] is None
    assert [i["id"] for i in out["to_trade"]] == [wished["id"]]
    assert out["discogs_count"] == 2 and out["owned_count"] == 1
    assert out["reset"]["records"] == 1
    assert collection == {HEADING: [1], CD: [2]}


def test_push_adds_only_the_confirmed_owned_records(client, runner, collection):
    owned, wished = library(client)
    job_id = client.post("/api/discogs-sync/push", json={"record_ids": [owned["id"], wished["id"]]}).json()["job_id"]
    runner.run_pending()
    result = job(client, job_id)["result"]
    assert result["added"] == [owned["id"]] and result["skipped"] == [wished["id"]]
    assert SIMPLE in collection and CD not in collection
    assert client.get(f"/api/records/{owned['id']}").json()["discogs_collection_synced"] is True
    assert client.post("/api/discogs-sync/push", json={"record_ids": []}).status_code == 422


def test_pull_imports_missing_records_and_trades_wishlist_ones(client, runner, collection):
    owned, wished = library(client)
    collection.update({HEADING: [1], CD: [2]})
    job_id = client.post("/api/discogs-sync/pull").json()["job_id"]
    runner.run_pending()
    result = job(client, job_id)["result"]
    assert len(result["imported"]) == 1 and result["traded"] == [wished["id"]]
    imported = client.get(f"/api/records/{result['imported'][0]}").json()
    assert imported["discogs_release_id"] == HEADING and imported["status"] == "owned"
    assert imported["discogs_collection_synced"] is True and imported["tracks"]
    traded = client.get(f"/api/records/{wished['id']}").json()
    assert traded["status"] == "owned" and traded["traded_at"]
    assert [r["id"] for r in client.get("/api/records/recently-traded").json()] == [wished["id"]]
    assert client.get(f"/api/records/{owned['id']}").json()["status"] == "owned"  # pull never deletes


def test_reset_needs_the_word(client):
    assert client.post("/api/discogs-sync/reset", json={"confirm": "reset"}).status_code == 422
    assert client.post("/api/discogs-sync/reset", json={}).status_code == 422


def test_reset_backs_up_replaces_owned_records_and_keeps_the_wishlist(client, runner, collection, db_path,
                                                                     backups):
    owned, wished = library(client)
    kept = add(client, HEADING, "wantlist")  # on the wishlist, not on Discogs
    conn = connect(db_path)
    notes.create(conn, body="a note that goes with the record", record_id=owned["id"])
    conn.close()
    collection.update({CD: [2]})
    job_id = client.post("/api/discogs-sync/reset", json={"confirm": "RESET"}).json()["job_id"]
    runner.run_pending()
    result = job(client, job_id)["result"]
    assert result["deleted"] == 1 and result["traded"] == [wished["id"]] and result["imported"] == []
    assert list(backups.glob("*.db"))
    conn = connect(db_path)
    assert records.get(conn, owned["id"]) is None
    assert conn.execute("SELECT count(*) FROM notes").fetchone()[0] == 0
    assert records.get(conn, kept["id"])["status"] == "wantlist"
    assert records.get(conn, wished["id"])["status"] == "owned"
    conn.close()


def test_moving_off_the_wishlist_by_hand_counts_as_traded(client):
    wished = add(client, CD, "wantlist")
    client.patch(f"/api/records/{wished['id']}", json={"status": "owned"})
    assert [r["id"] for r in client.get("/api/records/recently-traded").json()] == [wished["id"]]


# ---- copies ----

def test_a_record_can_have_copies_each_with_its_own_shelf_place(client, db_path):
    owned = add(client, SIMPLE)
    conn = connect(db_path)
    unit = crate.create_unit(conn, "Kallax", 1, 2)
    first, second = [r[0] for r in conn.execute(
        "SELECT s.id FROM cube_sections s JOIN cubes c ON c.id = s.cube_id WHERE c.unit_id = ? ORDER BY c.col", (unit,))]
    conn.close()
    assert client.get(f"/api/records/{owned['id']}/copies").json() == [{"number": 1, "copy_id": None, "section_id": None}]
    both = client.post(f"/api/records/{owned['id']}/copies", json={"section_id": second}).json()
    assert [(c["number"], c["section_id"]) for c in both] == [(1, None), (2, second)]
    client.put("/api/crate/place", json={"record_ids": [owned["id"]], "section_id": first})
    layout = client.get("/api/crate").json()
    sections = [s for u in layout["units"] for c in u["cubes"] for s in c["sections"]]
    placed = {s["id"]: [(r["id"], r["copy_number"]) for r in s["records"]] for s in sections}
    assert placed[first] == [(owned["id"], 1)] and placed[second] == [(owned["id"], 2)]
    copy_id = both[1]["copy_id"]
    assert client.patch(f"/api/copies/{copy_id}", json={"section_id": None}).json()[1]["section_id"] is None
    assert len(client.delete(f"/api/copies/{copy_id}").json()) == 1
    assert client.post(f"/api/records/{add(client, CD, 'wantlist')['id']}/copies").status_code == 409


def test_pull_adds_copies_discogs_has_more_of(client, runner, collection):
    owned, _ = library(client)
    collection.update({SIMPLE: [1, 2]})
    assert client.get("/api/discogs-sync/compare").json()["to_copy"][0]["copies"] == 2
    job_id = client.post("/api/discogs-sync/pull").json()["job_id"]
    runner.run_pending()
    assert job(client, job_id)["result"]["copies_added"] == 1
    assert len(client.get(f"/api/records/{owned['id']}/copies").json()) == 2


# ---- deleting, and what Discogs keeps ----

def test_deleting_can_remove_the_record_from_discogs_too(client, runner, collection):
    owned = add(client, SIMPLE)
    runner.run_pending()  # the intake sync puts it in the collection
    assert SIMPLE in collection
    client.delete(f"/api/records/{owned['id']}?from_discogs=true")
    runner.run_pending()
    assert collection[SIMPLE] == []


def test_deleting_here_only_keeps_it_on_discogs_and_imports_skip_it(client, runner, collection):
    owned = add(client, SIMPLE)
    runner.run_pending()
    client.delete(f"/api/records/{owned['id']}")
    runner.run_pending()
    assert collection[SIMPLE]
    out = client.get("/api/discogs-sync/compare").json()
    assert out["to_import"] == [] and [k["discogs_release_id"] for k in out["kept"]] == [SIMPLE]
    pulled = client.post("/api/discogs-sync/pull").json()["job_id"]
    runner.run_pending()
    assert job(client, pulled)["result"]["imported"] == []
    assert client.delete(f"/api/discogs-sync/kept/{SIMPLE}").status_code == 204
    assert [i["discogs_release_id"] for i in client.get("/api/discogs-sync/compare").json()["to_import"]] == [SIMPLE]


# ---- wantlist ----

def test_wishlist_goes_to_the_wantlist_and_owned_records_come_off_it(client, runner, wants):
    owned, wished = library(client)
    wants.add(SIMPLE)  # owned here but still wanted on Discogs
    out = client.get("/api/discogs-sync/compare").json()
    assert [i["id"] for i in out["to_wantlist"]] == [wished["id"]]
    assert [i["id"] for i in out["owned_wanted"]] == [owned["id"]]
    client.post("/api/discogs-sync/wantlist", json={"record_ids": [wished["id"], owned["id"]]})
    client.post("/api/discogs-sync/wantlist-tidy", json={"record_ids": [owned["id"]]})
    runner.run_pending()
    assert wants == {CD}


# ---- metadata refresh ----

def test_refresh_updates_details_but_keeps_your_data(client, runner, db_path):
    owned = add(client, SIMPLE)
    conn = connect(db_path)
    records.update(conn, owned["id"], title="typo", styles=["Mine"], styles_manual=1)
    first = owned["tracks"][0]
    conn.execute("UPDATE tracks SET title = 'old', bpm = 128 WHERE id = ?", (first["id"],))
    conn.execute("DELETE FROM tracks WHERE id = ?", (owned["tracks"][-1]["id"],))
    conn.commit()
    conn.close()
    job_id = client.post("/api/discogs-sync/refresh").json()["job_id"]
    runner.run_pending()
    assert job(client, job_id)["result"]["tracks_added"] == 1
    after = client.get(f"/api/records/{owned['id']}").json()
    assert after["title"] == owned["title"] and after["styles"] == ["Mine"]
    track = next(t for t in after["tracks"] if t["id"] == first["id"])
    assert track["title"] == first["title"] and track["bpm"] == 128
    assert len(after["tracks"]) == len(owned["tracks"])


# ---- the schedule ----

def test_tick_starts_due_syncs_once(db_path):
    conn = connect(db_path)
    started = []

    def enqueue(job_type, record_id, params):
        started.append((job_type, params))
        return len(started)

    t0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    assert library_sync.tick(conn, enqueue, t0) == []  # both off
    settings.update(conn, {"import_every_min": 60, "push_every_min": 30})
    assert library_sync.tick(conn, enqueue, t0) == [library_sync.PULL, library_sync.PUSH]
    assert started[1] == (library_sync.PUSH, {"all": True})
    assert library_sync.tick(conn, enqueue, t0 + timedelta(minutes=31)) == [library_sync.PUSH]
    assert library_sync.tick(conn, enqueue, t0 + timedelta(minutes=60)) == [library_sync.PULL]
    conn.close()


def test_scheduled_push_adds_every_missing_owned_record(client, runner, collection):
    owned, _ = library(client)
    runner.enqueue(library_sync.PUSH, params={"all": True})
    runner.run_pending()
    assert SIMPLE in collection
    assert client.patch("/api/settings", json={"push_every_min": -1}).status_code == 422
