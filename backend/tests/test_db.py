import sqlite3

import pytest

from app.db import connect, migrate, notes, records, tags, tracks
from app.db.migrate import MIGRATIONS_DIR


@pytest.fixture
def conn():
    c = connect(":memory:")
    migrate(c)
    yield c
    c.close()


@pytest.fixture
def record(conn):
    rid = records.create(conn, artist="Daft Punk", title="Discovery", label="Virgin",
                         year=2001, discogs_release_id=123)
    t1 = tracks.create(conn, rid, position="A1", title="One More Time", duration_sec=320)
    t2 = tracks.create(conn, rid, position="A2", title="Aerodynamic")
    return rid, t1, t2


def test_migrate_is_idempotent(conn):
    latest = len(list(MIGRATIONS_DIR.glob("*.sql")))
    assert migrate(conn) == latest
    assert conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == latest


def test_record_and_tracks_crud(conn, record):
    rid, t1, _ = record
    assert records.get(conn, rid)["status"] == "owned"
    assert records.get_by_discogs_id(conn, 123)["id"] == rid
    assert [t["position"] for t in tracks.list_for_record(conn, rid)] == ["A1", "A2"]
    tracks.update(conn, t1, bpm=123.0, analysis_raw={"bpm_alt": 61.5})
    assert tracks.get(conn, t1)["analysis_raw"] == {"bpm_alt": 61.5}
    records.update(conn, rid, status="wantlist")
    assert records.get(conn, rid)["status"] == "wantlist"
    with pytest.raises(ValueError):
        records.update(conn, rid, id=99)


def test_invalid_status_and_duplicate_release_rejected(conn, record):
    with pytest.raises(sqlite3.IntegrityError):
        records.create(conn, artist="x", title="y", status="bogus")
    with pytest.raises(sqlite3.IntegrityError):
        records.create(conn, artist="x", title="y", discogs_release_id=123)


def test_notes_record_and_track_level(conn, record):
    rid, t1, _ = record
    n1 = notes.create(conn, body="Shelf B", record_id=rid)
    n2 = notes.create(conn, body="huge energy", track_id=t1)
    assert [n["id"] for n in notes.list_for_record(conn, rid)] == [n1]
    assert [n["id"] for n in notes.list_for_track(conn, t1)] == [n2]


def test_note_requires_exactly_one_parent(conn, record):
    rid, t1, _ = record
    with pytest.raises(sqlite3.IntegrityError):
        notes.create(conn, body="none")
    with pytest.raises(sqlite3.IntegrityError):
        notes.create(conn, body="both", record_id=rid, track_id=t1)


def test_tags(conn, record):
    rid, t1, _ = record
    tags.create_tag(conn, 2, "house")
    tags.create_tag(conn, 1, "peak")
    tags.add(conn, "record", rid, " House ")
    tags.add(conn, "record", rid, "house")
    tags.add(conn, "track", t1, "House")
    tags.add(conn, "track", t1, "peak")
    assert tags.for_item(conn, "record", rid) == ["house"]
    assert tags.for_item(conn, "track", t1) == ["house", "peak"]
    counts = {t["name"]: t for t in tags.list_with_counts(conn)}
    assert counts["house"]["record_count"] == 1 and counts["house"]["track_count"] == 1
    assert tags.remove(conn, "track", t1, "peak")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tags(name) VALUES ('UPPER')")
    with pytest.raises(LookupError):
        tags.add(conn, "record", rid, "undefined")


def test_full_text_search_tracks_changes(conn, record):
    rid, _, _ = record
    assert [r["id"] for r in records.search(conn, "daft")] == [rid]
    records.update(conn, rid, artist="Justice")
    assert records.search(conn, "daft") == []
    assert [r["id"] for r in records.search(conn, "justice")] == [rid]
    nid = notes.create(conn, body="floor erupted", record_id=rid)
    assert note_hits(conn, "erupted") == [nid]
    notes.update(conn, nid, body="calm")
    assert note_hits(conn, "erupted") == []
    notes.delete(conn, nid)
    assert note_hits(conn, "calm") == []


def note_hits(conn, word):
    return [r[0] for r in conn.execute("SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?", (word,))]


def test_cascade_delete(conn, record):
    rid, t1, _ = record
    notes.create(conn, body="x", track_id=t1)
    tags.create_tag(conn, 1, "a")
    tags.add(conn, "track", t1, "a")
    records.delete(conn, rid)
    assert tracks.get(conn, t1) is None
    assert conn.execute("SELECT count(*) FROM notes").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM track_tags").fetchone()[0] == 0
    assert records.search(conn, "daft") == []


def test_styles_migration_applies_to_an_existing_database():
    old = connect(":memory:")
    old.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    for path in sorted(MIGRATIONS_DIR.glob("000[1-3]_*.sql")):
        old.executescript(f"BEGIN;\n{path.read_text()}\nINSERT INTO schema_version VALUES "
                          f"({int(path.name[:4])});\nCOMMIT;")
    rid = records.create(old, artist="A", title="B", discogs_release_id=5)
    assert migrate(old) == len(list(MIGRATIONS_DIR.glob("*.sql")))
    row = records.get(old, rid)
    assert (row["styles"], row["styles_manual"], row["catno"]) == (None, 0, None)  # never fetched
    old.close()


def test_styles_round_trip_and_are_cleaned(conn):
    rid = records.create(conn, artist="A", title="B", styles=["Deep House", " deep  house ", "", "Techno"])
    assert records.get(conn, rid)["styles"] == ["Deep House", "Techno"]
    assert records.get_by_discogs_id(conn, 1) is None
    records.update(conn, rid, styles=[])
    assert records.get(conn, rid)["styles"] == []  # "Discogs has none" differs from never fetched
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE records SET styles = 'not json' WHERE id = ?", (rid,))
