"""Audio the app downloaded (YouTube, shop clips, Bandcamp...) is only needed to analyse a track: playback
uses the official players, shop links and your own files. Downloads live in AUDIO_CACHE_DIR, never in your
audio folder, and are deleted once the track's analysis is validated or discarded. Analysing that track again
searches and downloads it again.

Only files inside AUDIO_CACHE_DIR are ever deleted here."""
import json
import sqlite3
from pathlib import Path

from app import config


def _in_cache(path: str | None) -> Path | None:
    if not path:
        return None
    p = Path(path)
    try:
        p.resolve().relative_to(config.AUDIO_CACHE_DIR.resolve())
    except (ValueError, OSError):
        return None
    return p


def _remove(path: Path) -> int:
    try:
        size = path.stat().st_size
        path.unlink()
        return size
    except FileNotFoundError:
        return 0


def _rows(conn: sqlite3.Connection, track_ids: list[int]) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(track_ids)) or "NULL"
    return conn.execute(f"SELECT track_id, status, source, audio_path, alternatives FROM track_audio "
                        f"WHERE track_id IN ({marks})", track_ids).fetchall()


def release(conn: sqlite3.Connection, track_ids: list[int]) -> int:
    """Delete these tracks' downloads (their analysis was validated or discarded). Returns bytes freed."""
    freed = 0
    for row in _rows(conn, track_ids):
        paths = [row["audio_path"]] + [a.get("audio_path") for a in json.loads(row["alternatives"] or "[]")]
        for p in filter(None, map(_in_cache, paths)):
            freed += _remove(p)
    return freed


def cleaned(conn: sqlite3.Connection, track_ids: list[int]) -> set[int]:
    """Tracks whose found audio was a download that has since been deleted: analysing them searches again."""
    return {r["track_id"] for r in _rows(conn, track_ids)
            if r["status"] == "found" and r["source"] != "local_files"
            and (p := _in_cache(r["audio_path"])) is not None and not p.is_file()}


def _still_needed(conn: sqlite3.Connection) -> set[Path]:
    """Downloads a track still needs: its analysis waits for you, or it was never analysed."""
    rows = conn.execute(
        "SELECT a.audio_path FROM track_audio a JOIN tracks t ON t.id = a.track_id "
        "WHERE a.audio_path IS NOT NULL AND (t.analyzed_at IS NULL "
        "OR EXISTS (SELECT 1 FROM track_proposals p WHERE p.track_id = t.id))").fetchall()
    return {p.resolve() for r in rows if (p := _in_cache(r[0])) is not None}


def _files() -> list[Path]:
    root = config.AUDIO_CACHE_DIR
    return [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else []


def usage() -> dict:
    files = _files()
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}


def clear(conn: sqlite3.Connection) -> dict:
    """Apply the rule to the whole cache: keep only downloads a track still needs."""
    keep = _still_needed(conn)
    deleted = freed = 0
    for f in _files():
        if f.resolve() not in keep:
            freed += _remove(f)
            deleted += 1
    root = config.AUDIO_CACHE_DIR
    if root.is_dir():
        for d in sorted((d for d in root.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return {"deleted": deleted, "freed_bytes": freed, **usage()}
