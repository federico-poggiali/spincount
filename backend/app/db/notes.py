import sqlite3

from app.db import _util


def create(conn: sqlite3.Connection, *, body: str, record_id: int | None = None,
           track_id: int | None = None) -> int:
    """Raises sqlite3.IntegrityError unless exactly one of record_id / track_id is set."""
    return _util.insert(conn, "notes", {"body": body, "record_id": record_id, "track_id": track_id})


def get(conn: sqlite3.Connection, note_id: int) -> dict | None:
    return _util.get(conn, "notes", note_id)


def list_for_record(conn: sqlite3.Connection, record_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM notes WHERE record_id = ? ORDER BY id", (record_id,))
    return [dict(r) for r in rows]


def list_for_track(conn: sqlite3.Connection, track_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM notes WHERE track_id = ? ORDER BY id", (track_id,))
    return [dict(r) for r in rows]


def update(conn: sqlite3.Connection, note_id: int, body: str) -> None:
    _util.update(conn, "notes", note_id, {"body": body, "updated_at": _util.now()}, {"body", "updated_at"})


def delete(conn: sqlite3.Connection, note_id: int) -> bool:
    return _util.delete(conn, "notes", note_id)
