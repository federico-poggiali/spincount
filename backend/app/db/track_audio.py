"""What audioresearch found for each track (one row per track; a new run replaces it)."""
import json
import sqlite3

_JSON = ("readings", "alternatives")


def _out(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in _JSON:
        d[key] = json.loads(d[key]) if d[key] is not None else []
    return d


def put(conn: sqlite3.Connection, track_id: int, *, status: str, source, level, quality, confidence, reason,
        url, page, audio_path, readings, alternatives, found_at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO track_audio (track_id, status, source, level, quality, confidence, reason,"
        " url, page, audio_path, readings, alternatives, found_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (track_id, status, source, level, quality, confidence, reason, url, page, audio_path,
         json.dumps(readings or []), json.dumps(alternatives or []), found_at))
    conn.commit()


def for_record(conn: sqlite3.Connection, record_id: int) -> dict[int, dict]:
    rows = conn.execute(
        "SELECT a.* FROM track_audio a JOIN tracks t ON t.id = a.track_id"
        " WHERE t.record_id = ?", (record_id,))
    return {r["track_id"]: _out(r) for r in rows}


def for_tracks(conn: sqlite3.Connection, track_ids: list[int]) -> dict[int, dict]:
    marks = ",".join("?" * len(track_ids)) or "NULL"
    rows = conn.execute(f"SELECT * FROM track_audio WHERE track_id IN ({marks})", track_ids)
    return {r["track_id"]: _out(r) for r in rows}


def records_without_audio(conn: sqlite3.Connection) -> list[int]:
    """Records with a Discogs id and tracks, none of which has an audio row yet."""
    rows = conn.execute(
        "SELECT r.id FROM records r WHERE r.discogs_release_id IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM tracks t WHERE t.record_id = r.id)"
        " AND NOT EXISTS (SELECT 1 FROM tracks t JOIN track_audio a ON a.track_id = t.id"
        "                 WHERE t.record_id = r.id)"
        " ORDER BY r.id")
    return [r["id"] for r in rows]
