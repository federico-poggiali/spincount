"""The audio stage of analysis: ask audioresearch for each track's audio, keep what it found.

Spin Count only reads audioresearch's output contract (ReleaseResult); it never reads audioresearch's own
database. Results go to the `track_audio` table. A failure here never stops the analysis that follows.
"""
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app import config
from app.db import track_audio

# (release id, folder of your own audio, refresh) -> the audioresearch output contract as a dict
ResearchFn = Callable[[int, Path, bool], dict]


def research_release(release_id: int, audio_dir: Path, refresh: bool = False) -> dict:
    """The real thing: all levels, cached by audioresearch in its own database."""
    from audioresearch.pipeline import research
    from audioresearch.store import Store

    store = Store()
    try:
        return research(release_id, refresh=refresh, store=store, audio_dir=audio_dir).to_dict()
    finally:
        store.close()


def needs_audio(conn: sqlite3.Connection, track_ids: list[int], refresh: bool) -> bool:
    if refresh:
        return True
    marks = ",".join("?" * len(track_ids)) or "NULL"
    row = conn.execute(f"SELECT COUNT(*) FROM track_audio WHERE track_id IN ({marks})", track_ids).fetchone()
    return row[0] < len(track_ids)


def store_contract(conn: sqlite3.Connection, contract: dict, tracks: list[dict]) -> list[int]:
    """Save a contract's tracks onto the matching track rows (by position). Returns the track ids stored."""
    if contract.get("contract_version") != 1:
        raise ValueError(f"unsupported audioresearch contract version {contract.get('contract_version')!r}")
    by_position = {t["position"]: t for t in tracks}
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stored = []
    for item in contract["tracks"]:
        row = by_position.get(item["position"])
        if row is None:
            continue
        track_audio.put(
            conn, row["id"], status=item["status"], source=item.get("source"), level=item.get("level"),
            quality=item.get("quality"), confidence=item.get("confidence"), reason=item.get("reason"),
            url=item.get("url"), page=item.get("page"), audio_path=item.get("audio_path"),
            readings=item.get("readings"), alternatives=item.get("alternatives"), found_at=now)
        stored.append(row["id"])
    return stored


def run(conn: sqlite3.Connection, record: dict, tracks: list[dict], research_fn: ResearchFn,
        audio_dir: Path | None = None, refresh: bool = False) -> dict:
    """Find audio for these tracks unless they already have it. Returns a small report, never raises."""
    ids = [t["id"] for t in tracks]
    if not needs_audio(conn, ids, refresh):
        return {"ran": False, "reason": "audio already found", "stored_track_ids": []}
    try:
        contract = research_fn(record["discogs_release_id"], audio_dir or config.AUDIO_DIR, refresh)
        stored = store_contract(conn, contract, tracks)
    except Exception as exc:  # audio is a bonus: analysis must still run
        return {"ran": True, "error": f"{type(exc).__name__}: {exc}", "stored_track_ids": []}
    counts = {}
    for item in contract["tracks"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"ran": True, "stored_track_ids": stored, "counts": counts,
            "adapters_off": contract.get("adapters_off", [])}
