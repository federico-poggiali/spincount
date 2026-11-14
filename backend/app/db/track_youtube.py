"""Each track's YouTube video (one row per track searched; a new search replaces it)."""
import sqlite3


def put(conn: sqlite3.Connection, track_id: int, *, video_id: str | None, source: str | None = None,
        title: str | None = None, channel: str | None = None, duration: int | None = None,
        confidence: float | None = None, found_at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO track_youtube"
        " (track_id, video_id, source, title, channel, duration, confidence, found_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (track_id, video_id, source, title, channel, duration, confidence, found_at))
    conn.commit()


def for_record(conn: sqlite3.Connection, record_id: int) -> dict[int, dict]:
    rows = conn.execute(
        "SELECT y.* FROM track_youtube y JOIN tracks t ON t.id = y.track_id WHERE t.record_id = ?",
        (record_id,))
    return {r["track_id"]: dict(r) for r in rows}


def for_tracks(conn: sqlite3.Connection, track_ids: list[int]) -> dict[int, dict]:
    marks = ",".join("?" * len(track_ids)) or "NULL"
    rows = conn.execute(f"SELECT * FROM track_youtube WHERE track_id IN ({marks})", track_ids)
    return {r["track_id"]: dict(r) for r in rows}


def records_without_youtube(conn: sqlite3.Connection) -> list[int]:
    """Records with at least one track never searched on YouTube."""
    rows = conn.execute(
        "SELECT DISTINCT t.record_id FROM tracks t LEFT JOIN track_youtube y ON y.track_id = t.id"
        " WHERE y.track_id IS NULL ORDER BY t.record_id")
    return [r[0] for r in rows]
