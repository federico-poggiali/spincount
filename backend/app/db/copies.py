"""Copies of a record. Copy 1 is the record itself (its section_id is copy 1's shelf place); copies
2 and up are rows in record_copies, each with its own place."""
import sqlite3

from app.db import _util


def for_record(conn: sqlite3.Connection, record_id: int) -> list[dict]:
    """Every copy in order: {number, copy_id (None for copy 1), section_id}."""
    first = conn.execute("SELECT section_id FROM records WHERE id = ?", (record_id,)).fetchone()
    if first is None:
        return []
    extra = conn.execute("SELECT id, section_id FROM record_copies WHERE record_id = ? ORDER BY id",
                         (record_id,)).fetchall()
    return [{"number": 1, "copy_id": None, "section_id": first["section_id"]},
            *({"number": i + 2, "copy_id": r["id"], "section_id": r["section_id"]}
              for i, r in enumerate(extra))]


def count(conn: sqlite3.Connection, record_id: int) -> int:
    row = conn.execute("SELECT count(*) FROM record_copies WHERE record_id = ?", (record_id,)).fetchone()
    return 1 + row[0]


def add(conn: sqlite3.Connection, record_id: int, section_id: int | None = None) -> int:
    return _util.insert(conn, "record_copies", {"record_id": record_id, "section_id": section_id})


def get(conn: sqlite3.Connection, copy_id: int) -> dict | None:
    return _util.get(conn, "record_copies", copy_id)


def place(conn: sqlite3.Connection, copy_id: int, section_id: int | None) -> None:
    conn.execute("UPDATE record_copies SET section_id = ? WHERE id = ?", (section_id, copy_id))
    conn.commit()


def delete(conn: sqlite3.Connection, copy_id: int) -> bool:
    return _util.delete(conn, "record_copies", copy_id)
