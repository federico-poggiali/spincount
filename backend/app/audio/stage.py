"""The audio stage of analysis: ask audioresearch for each track's audio, keep what it found.

Spin Count only reads audioresearch's output contract (ReleaseResult); it never reads audioresearch's own
database. Results go to the `track_audio` table. A failure here never stops the analysis that follows.
"""
import sqlite3
from collections.abc import Callable
from pathlib import Path

from app import config
from app.db import _util, settings, track_audio

# (release id, folder for downloads, refresh, everything, sources switched off) -> audioresearch's output
# contract as a dict
ResearchFn = Callable[[int, Path, bool, bool, list], dict]


def research_release(release_id: int, audio_dir: Path, refresh: bool = False, everything: bool = False,
                     sources_off: list[str] | tuple = ()) -> dict:
    """The real thing, cached by audioresearch in its own database. Fast: source after source, stopping as
    soon as every track has audio. `everything` (lengthy): every source for every track, for alternatives.
    A track covered by one of your own files is never searched; `sources_off` are skipped."""
    from audioresearch import config as ar_config
    from audioresearch.adapters import default_registry
    from audioresearch.pipeline import research
    from audioresearch.store import Store

    from app.activity import activity

    store = Store()
    try:
        registry = default_registry(disabled=ar_config.disabled_adapters() | set(sources_off), store=store)
        result = research(release_id, refresh=refresh, store=store, audio_dir=audio_dir, registry=registry,
                          search_all=everything, stall_seconds=config.AUDIO_STALL_SECONDS,
                          on_event=activity.on_event if activity.enabled else None)
        return {**result.to_dict(), "halted": result.halted}
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
    now = _util.now()
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


def store_own_files(conn: sqlite3.Connection, record: dict, tracks: list[dict]) -> list[int]:
    """Your own files, matched to their tracks without searching anything: each becomes its track's audio, and
    what the track had before stays as an alternative. Returns the track ids that changed."""
    from app.audio.files import match_own_files

    own = match_own_files(record, tracks)
    had = track_audio.for_record(conn, record["id"])
    changed = []
    for m in own["matched"]:
        path = str(Path(own["folder"]) / m["file"])
        old = had.get(m["track_id"])
        if old and old["source"] == "local_files" and old["audio_path"] == path:
            continue
        alternatives = [a for a in (old["alternatives"] if old else []) if a.get("source") != "local_files"]
        if old and old["status"] != "not_found" and old["source"] != "local_files":
            keys = ("source", "quality", "confidence", "audio_path", "url", "level", "page")
            alternatives.insert(0, {k: old[k] for k in keys})
        track_audio.put(conn, m["track_id"], status="found", source="local_files", level=0, quality="full",
                        confidence=1.0, reason="your own file", url=path, page=None, audio_path=path,
                        readings=old["readings"] if old else [], alternatives=alternatives,
                        found_at=_util.now())
        changed.append(m["track_id"])
    return changed


def run(conn: sqlite3.Connection, record: dict, tracks: list[dict], research_fn: ResearchFn,
        audio_dir: Path | None = None, refresh: bool = False) -> dict:
    """Find audio for these tracks unless they all have a result already; `refresh` searches from scratch
    (your own files stay). Fast or lengthy, and which sources, come from Settings. `audio_dir` is where
    downloads go. Returns a small report, never raises."""
    ids = [t["id"] for t in tracks]
    if not needs_audio(conn, ids, refresh):
        return {"ran": False, "reason": "audio already found", "stored_track_ids": []}
    lengthy, off = settings.get(conn, "audio_search_lengthy"), settings.get(conn, "audio_sources_off")
    try:
        release_id, folder = record["discogs_release_id"], audio_dir or config.AUDIO_CACHE_DIR
        contract = research_fn(release_id, folder, refresh, lengthy, off)
        stored = store_contract(conn, contract, tracks)
    except Exception as exc:  # audio is a bonus: analysis must still run
        return {"ran": True, "error": f"{type(exc).__name__}: {exc}", "stored_track_ids": []}
    counts = {}
    for item in contract["tracks"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    report = {"ran": True, "stored_track_ids": stored, "counts": counts,
              "adapters_off": contract.get("adapters_off", [])}
    if contract.get("halted"):   # stopped early: what was found is kept, the rest was not searched
        report["halted"] = contract["halted"]
    return report
