"""Sync the library with Discogs. Everything that writes runs as a job: Discogs allows about 60 calls
a minute and an import asks for each release.

- compare: what differs, read-only.
- push: owned records Discogs lacks go into the collection: the ones you confirmed, or all of them
  when the schedule runs it.
- pull: collection records Spin Count lacks are imported as owned (no audio search); a wishlist record
  found in the collection becomes owned and "recently traded"; extra Discogs copies become copies here.
  Releases you deleted here but kept on Discogs are skipped.
- reset: back up the database, delete every owned record and its data, then pull everything. The
  wishlist stays.
- wantlist: wishlist records onto the Discogs wantlist (one way), and owned records off it.
- remove: a release you deleted here, out of the Discogs collection.
- refresh: titles, covers, labels and tracklists again from Discogs; your own data stays.
- tick: starts the scheduled import and push when they are due.
"""
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app import backup
from app.db import _util, copies, records, settings, tracks
from app.discogs import DiscogsClient, DiscogsError, release_to_record, release_to_tracks
from app.intake import create_from_release

PUSH, PULL, RESET, WANT = "discogs_push", "discogs_pull", "discogs_reset", "discogs_want"
WANT_PUSH, WANT_TIDY, REMOVE, REFRESH = "wantlist_push", "wantlist_tidy", "discogs_remove", "discogs_refresh"
RESET_WORD = "RESET"
_TIME = "%Y-%m-%dT%H:%M:%SZ"


def _ref(record: dict, **extra) -> dict:
    keys = ("id", "discogs_release_id", "artist", "title", "year", "cover_url")
    return {**{k: record[k] for k in keys}, **extra}


def _all_records(conn: sqlite3.Connection) -> list[dict]:
    return [records.decode(dict(r)) for r in conn.execute("SELECT * FROM records ORDER BY artist, title")]


def kept_ids(conn: sqlite3.Connection) -> set[int]:
    return {r[0] for r in conn.execute("SELECT discogs_release_id FROM discogs_kept")}


def keep_on_discogs(conn: sqlite3.Connection, record: dict) -> None:
    """Remember a release deleted here but left in the Discogs collection, so imports skip it."""
    conn.execute("INSERT OR REPLACE INTO discogs_kept VALUES (?, ?, ?, ?)",
                 (record["discogs_release_id"], record["artist"], record["title"], _util.now()))
    conn.commit()


def forget_kept(conn: sqlite3.Connection, release_id: int) -> bool:
    cur = conn.execute("DELETE FROM discogs_kept WHERE discogs_release_id = ?", (release_id,))
    conn.commit()
    return cur.rowcount > 0


def _missing_on_discogs(rows: list[dict], remote: set[int]) -> list[dict]:
    return [r for r in rows if r["status"] == "owned" and r["discogs_release_id"]
            and r["discogs_release_id"] not in remote]


def compare(conn: sqlite3.Connection, discogs: DiscogsClient) -> dict:
    remote = {r["discogs_release_id"]: r for r in discogs.collection_releases()}
    wanted = discogs.wantlist_ids()
    rows = _all_records(conn)
    local = {r["discogs_release_id"]: r for r in rows if r["discogs_release_id"] is not None}
    owned = [r for r in rows if r["status"] == "owned"]
    kept = kept_ids(conn)
    owned_ids = [r["id"] for r in owned]
    marks = ",".join("?" * len(owned_ids)) or "NULL"
    notes = conn.execute(
        f"SELECT count(*) FROM notes WHERE record_id IN ({marks}) "
        f"OR track_id IN (SELECT id FROM tracks WHERE record_id IN ({marks}))", owned_ids * 2).fetchone()[0]
    analysed = conn.execute(
        f"SELECT count(*) FROM tracks WHERE bpm IS NOT NULL AND record_id IN ({marks})",
        owned_ids).fetchone()[0]
    to_copy = []
    for release_id, item in remote.items():
        record = local.get(release_id)
        if not record or record["status"] != "owned":
            continue
        if (here := copies.count(conn, record["id"])) < item["copies"]:
            to_copy.append(_ref(record, copies=item["copies"], here=here))
    return {
        "discogs_count": len(remote),
        "owned_count": len(owned),
        "to_discogs": [_ref(r) for r in _missing_on_discogs(rows, set(remote))],
        "to_import": [{"id": None, **remote[i]} for i in remote if i not in local and i not in kept],
        "to_trade": [_ref(local[i]) for i in remote if i in local and local[i]["status"] != "owned"],
        "to_copy": to_copy,
        "kept": [{"id": None, "year": None, "cover_url": None, **dict(r)} for r in conn.execute(
            "SELECT discogs_release_id, artist, title FROM discogs_kept ORDER BY artist, title")
            if r["discogs_release_id"] in remote],
        "to_wantlist": [_ref(r) for r in rows if r["status"] != "owned" and r["discogs_release_id"]
                        and r["discogs_release_id"] not in wanted],
        "owned_wanted": [_ref(r) for r in owned if r["discogs_release_id"] in wanted],
        "reset": {"records": len(owned), "notes": notes, "analysed_tracks": analysed},
    }


def push(conn: sqlite3.Connection, discogs: DiscogsClient, record_ids: list[int] | None) -> dict:
    """record_ids None: every owned record the collection lacks (the scheduled push)."""
    if record_ids is None:
        remote = {r["discogs_release_id"] for r in discogs.collection_releases()}
        record_ids = [r["id"] for r in _missing_on_discogs(_all_records(conn), remote)]
    added, already, skipped = [], [], []
    for record_id in record_ids:
        record = records.get(conn, record_id)
        if record is None or record["status"] != "owned" or record["discogs_release_id"] is None:
            skipped.append(record_id)
            continue
        _, was_added = discogs.add_to_collection(record["discogs_release_id"])
        records.update(conn, record_id, discogs_collection_synced=1)
        (added if was_added else already).append(record_id)
    return {"added": added, "already_there": already, "skipped": skipped}


def pull(conn: sqlite3.Connection, discogs: DiscogsClient, remote: list[dict] | None = None) -> dict:
    kept = kept_ids(conn)
    imported, traded, failed, copies_added = [], [], [], 0
    for item in remote if remote is not None else discogs.collection_releases():
        release_id = item["discogs_release_id"]
        if release_id in kept:
            continue
        record = records.get_by_discogs_id(conn, release_id)
        if record is None:
            try:
                data = discogs.release(release_id)
            except DiscogsError as exc:  # one bad release never stops the rest
                failed.append({"discogs_release_id": release_id, "title": item["title"], "error": str(exc)})
                continue
            record_id = create_from_release(conn, data, "owned", discogs_collection_synced=1)
            imported.append(record_id)
        else:
            record_id = record["id"]
            if record["status"] != "owned":
                records.update(conn, record_id, status="owned", traded_at=_util.now(),
                               discogs_collection_synced=1)
                traded.append(record_id)
            elif not record["discogs_collection_synced"]:
                records.update(conn, record_id, discogs_collection_synced=1)
        for _ in range(item.get("copies", 1) - copies.count(conn, record_id)):  # only ever adds copies
            copies.add(conn, record_id)
            copies_added += 1
    return {"imported": imported, "traded": traded, "copies_added": copies_added, "failed": failed}


def reset(conn: sqlite3.Connection, discogs: DiscogsClient) -> dict:
    """A full mirror: releases you once kept off the library come back too."""
    remote = discogs.collection_releases()  # read Discogs before deleting anything
    saved = backup.backup()
    deleted = conn.execute("DELETE FROM records WHERE status = 'owned'").rowcount
    conn.execute("DELETE FROM discogs_kept")
    conn.commit()
    return {"backup": str(saved), "deleted": deleted, **pull(conn, discogs, remote)}


def want(conn: sqlite3.Connection, discogs: DiscogsClient, record_id: int) -> dict:
    record = records.get(conn, record_id)
    if record is None:
        raise ValueError("record no longer exists")
    if record["status"] == "owned":
        return {"skipped": "the record is owned; only wishlist records go on the wantlist"}
    if record["discogs_release_id"] is None:
        raise ValueError("record has no Discogs release id")
    discogs.add_to_wantlist(record["discogs_release_id"])
    records.update(conn, record_id, discogs_wantlist_synced=1)
    return {"wanted": record["discogs_release_id"]}


def want_push(conn: sqlite3.Connection, discogs: DiscogsClient, record_ids: list[int]) -> dict:
    added, skipped = [], []
    for record_id in record_ids:
        record = records.get(conn, record_id)
        if record is None or record["status"] == "owned" or record["discogs_release_id"] is None:
            skipped.append(record_id)
            continue
        discogs.add_to_wantlist(record["discogs_release_id"])
        records.update(conn, record_id, discogs_wantlist_synced=1)
        added.append(record_id)
    return {"wanted": added, "skipped": skipped}


def want_tidy(conn: sqlite3.Connection, discogs: DiscogsClient, record_ids: list[int]) -> dict:
    """Take owned records off the Discogs wantlist."""
    removed, skipped = [], []
    for record_id in record_ids:
        record = records.get(conn, record_id)
        if record is None or record["status"] != "owned" or record["discogs_release_id"] is None:
            skipped.append(record_id)
            continue
        discogs.remove_from_wantlist(record["discogs_release_id"])
        records.update(conn, record_id, discogs_wantlist_synced=0)
        removed.append(record_id)
    return {"unwanted": removed, "skipped": skipped}


def remove(discogs: DiscogsClient, release_id: int) -> dict:
    return {"discogs_release_id": release_id, "removed_copies": discogs.remove_from_collection(release_id)}


def refresh(conn: sqlite3.Connection, discogs: DiscogsClient) -> dict:
    """Release details and tracklists again from Discogs. BPM, key, notes, tags, shelf places and styles
    you edited stay; tracks are updated by position and new ones added, never deleted."""
    updated, failed, tracks_added = 0, [], 0
    rows = conn.execute("SELECT * FROM records WHERE discogs_release_id IS NOT NULL ORDER BY id").fetchall()
    for row in rows:
        record = records.decode(dict(row))
        try:
            data = discogs.release(record["discogs_release_id"])
        except DiscogsError as exc:
            failed.append({"id": record["id"], "title": record["title"], "error": str(exc)})
            continue
        fresh = release_to_record(data)
        fresh.pop("discogs_release_id")
        if record["styles_manual"]:
            fresh.pop("styles")
        records.update(conn, record["id"], **fresh)
        by_position = {t["position"]: t for t in tracks.list_for_record(conn, record["id"])}
        for t in release_to_tracks(data):
            if (current := by_position.get(t["position"])) is None:
                tracks.create(conn, record["id"], **t)
                tracks_added += 1
            else:
                tracks.update(conn, current["id"], title=t["title"], artist=t["artist"],
                              duration_sec=t["duration_sec"])
        updated += 1
    return {"updated": updated, "tracks_added": tracks_added, "failed": failed}


# ---- the schedule ----

def _busy(conn: sqlite3.Connection, job_type: str) -> bool:
    return conn.execute("SELECT 1 FROM jobs WHERE type = ? AND status IN ('queued', 'running') LIMIT 1",
                        (job_type,)).fetchone() is not None


def tick(conn: sqlite3.Connection, enqueue: Callable[..., int], now: datetime | None = None) -> list[str]:
    """Start the scheduled import and push that are due. Returns the job types started."""
    now = now or datetime.now(UTC)
    values = settings.get_all(conn)
    started = []
    for every_key, last_key, job_type, params in (("import_every_min", "last_import_at", PULL, None),
                                                  ("push_every_min", "last_push_at", PUSH, {"all": True})):
        minutes = int(values[every_key])
        if minutes <= 0 or _busy(conn, job_type):
            continue
        last = settings.get_state(conn, last_key)
        if last and datetime.strptime(last, _TIME).replace(tzinfo=UTC) + timedelta(minutes=minutes) > now:
            continue
        settings.set_state(conn, last_key, now.strftime(_TIME))
        enqueue(job_type, None, params)
        started.append(job_type)
    return started


Handler = Callable[[sqlite3.Connection, dict], dict]


def make_handlers(discogs_factory: Callable[[], DiscogsClient]) -> dict[str, Handler]:
    def ids(job: dict) -> list[int]:
        return (job.get("params") or {})["record_ids"]

    return {
        PUSH: lambda conn, job: push(conn, discogs_factory(),
                                     None if (job.get("params") or {}).get("all") else ids(job)),
        PULL: lambda conn, job: pull(conn, discogs_factory()),
        RESET: lambda conn, job: reset(conn, discogs_factory()),
        WANT: lambda conn, job: want(conn, discogs_factory(), job["record_id"]),
        WANT_PUSH: lambda conn, job: want_push(conn, discogs_factory(), ids(job)),
        WANT_TIDY: lambda conn, job: want_tidy(conn, discogs_factory(), ids(job)),
        REMOVE: lambda conn, job: remove(discogs_factory(), job["params"]["discogs_release_id"]),
        REFRESH: lambda conn, job: refresh(conn, discogs_factory()),
    }
