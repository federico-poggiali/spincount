"""SQLite cache and log (`audioresearch.db`): identities, candidates, fetched audio, decisions,
provenance, run events, manual links and review overrides. Simple numbered migrations."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import config
from .events import RunEvent
from .models import Candidate, FetchedAudio, Quality, ReleaseIdentity, ReleaseResult, Status

NOT_FOUND_RETRY_DAYS = 30

MIGRATIONS: list[str] = [
    """
    CREATE TABLE releases (release_id INTEGER PRIMARY KEY, identity TEXT NOT NULL, saved_at TEXT NOT NULL);
    CREATE TABLE aliases (key TEXT PRIMARY KEY, release_id INTEGER NOT NULL);
    CREATE TABLE candidates (release_id INTEGER, adapter TEXT, positions TEXT, payload TEXT NOT NULL, saved_at TEXT NOT NULL,
                             PRIMARY KEY (release_id, adapter, positions));
    CREATE TABLE fetched (release_id INTEGER, position TEXT, adapter TEXT, url TEXT, path TEXT NOT NULL, quality TEXT NOT NULL,
                          duration REAL, fingerprint TEXT, saved_at TEXT NOT NULL,
                          PRIMARY KEY (release_id, position, adapter, url));
    CREATE TABLE decisions (release_id INTEGER PRIMARY KEY, result TEXT NOT NULL, levels TEXT NOT NULL,
                            run_id TEXT, decided_at TEXT NOT NULL);
    CREATE TABLE provenance (id INTEGER PRIMARY KEY AUTOINCREMENT, release_id INTEGER, run_id TEXT, adapter TEXT, url TEXT,
                             position TEXT, score REAL, outcome TEXT, reason TEXT, extra TEXT, created_at TEXT);
    CREATE TABLE readings (release_id INTEGER, position TEXT, source TEXT, bpm REAL, key TEXT, run_id TEXT);
    CREATE TABLE runs (run_id TEXT PRIMARY KEY, url TEXT, release_id INTEGER, title TEXT, started_at TEXT, finished_at TEXT,
                       summary TEXT);
    CREATE TABLE run_events (run_id TEXT, seq INTEGER, payload TEXT NOT NULL, PRIMARY KEY (run_id, seq));
    """,
    """
    CREATE TABLE manual_links (release_id INTEGER, position TEXT, url TEXT NOT NULL, saved_at TEXT, PRIMARY KEY (release_id, position));
    CREATE TABLE overrides (release_id INTEGER, position TEXT, action TEXT NOT NULL, detail TEXT, saved_at TEXT,
                            PRIMARY KEY (release_id, position));
    """,
    """
    CREATE TABLE run_results (run_id TEXT PRIMARY KEY, result TEXT NOT NULL);
    """,
]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: Path | str | None = None):
        path = config.AUDIORESEARCH_DB if path is None else path
        self.path = path
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self.lock:
            v = self.db.execute("PRAGMA user_version").fetchone()[0]
            for i, sql in enumerate(MIGRATIONS[v:], v + 1):
                self.db.executescript(sql)
                self.db.execute(f"PRAGMA user_version = {i}")
            self.db.commit()

    def _run(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def close(self) -> None:
        self.db.close()

    # ---- identities ----------------------------------------------------------------------------
    def save_identity(self, identity: ReleaseIdentity, alias: str | None = None) -> None:
        self._run("INSERT OR REPLACE INTO releases VALUES (?,?,?)",
                  (identity.discogs_release_id, json.dumps(identity.to_dict()), now()))
        if alias:
            self._run("INSERT OR REPLACE INTO aliases VALUES (?,?)", (alias, identity.discogs_release_id))

    def get_identity(self, release_id: int) -> Optional[ReleaseIdentity]:
        rows = self._all("SELECT identity FROM releases WHERE release_id=?", (release_id,))
        return ReleaseIdentity.from_dict(json.loads(rows[0][0])) if rows else None

    def resolve_alias(self, alias: str) -> Optional[int]:
        rows = self._all("SELECT release_id FROM aliases WHERE key=?", (alias,))
        return rows[0][0] if rows else None

    # ---- candidates ----------------------------------------------------------------------------
    @staticmethod
    def _pos_key(positions: list[str]) -> str:
        return ",".join(sorted(positions))

    def save_candidates(self, release_id: int, adapter: str, positions: list[str], cands: list[Candidate]) -> None:
        self._run("INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?)",
                  (release_id, adapter, self._pos_key(positions), json.dumps([c.to_dict() for c in cands]), now()))

    def get_candidates(self, release_id: int, adapter: str, positions: list[str]) -> Optional[list[Candidate]]:
        rows = self._all("SELECT payload FROM candidates WHERE release_id=? AND adapter=? AND positions=?",
                         (release_id, adapter, self._pos_key(positions)))
        return [Candidate.from_dict(d) for d in json.loads(rows[0][0])] if rows else None

    # ---- fetched audio -------------------------------------------------------------------------
    def save_fetched(self, release_id: int, position: str, f: FetchedAudio) -> None:
        self._run("INSERT OR REPLACE INTO fetched VALUES (?,?,?,?,?,?,?,?,?)",
                  (release_id, position, f.adapter, f.url, str(f.path), f.quality.value, f.duration,
                   json.dumps(f.fingerprint) if f.fingerprint is not None else None, now()))

    def get_fetched(self, release_id: int, position: str, adapter: str, url: str) -> Optional[FetchedAudio]:
        rows = self._all("SELECT * FROM fetched WHERE release_id=? AND position=? AND adapter=? AND url=?",
                         (release_id, position, adapter, url))
        if not rows or not Path(rows[0]["path"]).exists():
            return None
        r = rows[0]
        return FetchedAudio(Path(r["path"]), adapter, url, Quality(r["quality"]), r["duration"],
                            json.loads(r["fingerprint"]) if r["fingerprint"] else None)

    def set_fingerprint(self, release_id: int, position: str, adapter: str, url: str, fp: list[int]) -> None:
        self._run("UPDATE fetched SET fingerprint=? WHERE release_id=? AND position=? AND adapter=? AND url=?",
                  (json.dumps(fp), release_id, position, adapter, url))

    # ---- decisions -----------------------------------------------------------------------------
    def save_result(self, result: ReleaseResult, levels: list[int], run_id: str | None = None) -> None:
        self._run("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?)",
                  (result.discogs_release_id, result.to_json(None), json.dumps(sorted(levels)), run_id, now()))

    def get_result(self, release_id: int) -> Optional[tuple[ReleaseResult, list[int], str]]:
        rows = self._all("SELECT * FROM decisions WHERE release_id=?", (release_id,))
        if not rows:
            return None
        r = rows[0]
        return ReleaseResult.from_json(r["result"]), json.loads(r["levels"]), r["decided_at"]

    def cached_result(self, release_id: int, levels: list[int]) -> Optional[ReleaseResult]:
        """The stored result if it covers `levels` and its not_found tracks are not due for a retry."""
        got = self.get_result(release_id)
        if not got:
            return None
        result, done, decided_at = got
        if not set(levels) <= set(done):
            return None
        age = datetime.now(timezone.utc) - datetime.strptime(decided_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if age > timedelta(days=NOT_FOUND_RETRY_DAYS) and any(t.status == Status.NOT_FOUND for t in result.tracks):
            return None
        return result

    # ---- provenance and readings ---------------------------------------------------------------
    def add_provenance(self, release_id: int, run_id: str, adapter: str, url: str, position: str | None,
                       score: float | None, outcome: str, reason: str, extra: dict[str, Any] | None = None) -> None:
        self._run("INSERT INTO provenance (release_id, run_id, adapter, url, position, score, outcome, reason, extra, created_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (release_id, run_id, adapter, url, position, score, outcome, reason, json.dumps(extra or {}), now()))

    def get_provenance(self, release_id: int, run_id: str | None = None) -> list[dict]:
        if run_id is None:
            rows = self._all("SELECT run_id FROM provenance WHERE release_id=? ORDER BY id DESC LIMIT 1", (release_id,))
            if not rows:
                return []
            run_id = rows[0][0]
        rows = self._all("SELECT * FROM provenance WHERE release_id=? AND run_id=? ORDER BY id", (release_id, run_id))
        return [{**dict(r), "extra": json.loads(r["extra"] or "{}")} for r in rows]

    def save_readings(self, release_id: int, run_id: str, readings: dict[str, list]) -> None:
        with self.lock:
            self.db.execute("DELETE FROM readings WHERE release_id=?", (release_id,))
            self.db.executemany("INSERT INTO readings VALUES (?,?,?,?,?,?)",
                                [(release_id, pos, r.source, r.bpm, r.key, run_id) for pos, rs in readings.items() for r in rs])
            self.db.commit()

    # ---- runs and events -----------------------------------------------------------------------
    def start_run(self, run_id: str, url: str) -> None:
        self._run("INSERT OR REPLACE INTO runs (run_id, url, started_at) VALUES (?,?,?)", (run_id, url, now()))

    def update_run(self, run_id: str, **fields: Any) -> None:
        for k, v in fields.items():
            self._run(f"UPDATE runs SET {k}=? WHERE run_id=?", (json.dumps(v) if k == "summary" else v, run_id))

    def add_event(self, e: RunEvent) -> None:
        self._run("INSERT OR REPLACE INTO run_events VALUES (?,?,?)", (e.run_id, e.seq, json.dumps(e.to_dict())))
        if e.type == "release_identified":
            self.update_run(e.run_id, release_id=e.data.get("release_id"), title=f"{e.data.get('artist')} - {e.data.get('title')}")
        elif e.type == "run_finished":
            self.update_run(e.run_id, finished_at=now(), summary={k: e.data.get(k) for k in ("found", "review", "not_found", "ms")})

    def get_events(self, run_id: str, after_seq: int = 0) -> list[RunEvent]:
        rows = self._all("SELECT payload FROM run_events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after_seq))
        return [RunEvent.from_dict(json.loads(r[0])) for r in rows]

    def list_runs(self, limit: int = 50) -> list[dict]:
        out = []
        for r in self._all("SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)):
            d = dict(r)
            d["summary"] = json.loads(d["summary"]) if d.get("summary") else None
            out.append(d)
        return out

    def save_run_result(self, run_id: str, result: ReleaseResult) -> None:
        self._run("INSERT OR REPLACE INTO run_results VALUES (?,?)", (run_id, result.to_json(None)))

    def get_run_result(self, run_id: str) -> Optional[ReleaseResult]:
        rows = self._all("SELECT result FROM run_results WHERE run_id=?", (run_id,))
        return ReleaseResult.from_json(rows[0][0]) if rows else None

    def get_run(self, run_id: str) -> Optional[dict]:
        return next((r for r in self.list_runs(1000) if r["run_id"] == run_id), None)

    # ---- manual links and review overrides -----------------------------------------------------
    def set_manual_link(self, release_id: int, position: str, url: str) -> None:
        self._run("INSERT OR REPLACE INTO manual_links VALUES (?,?,?,?)", (release_id, position, url, now()))

    def manual_links(self, release_id: int) -> dict[str, str]:
        return {r["position"]: r["url"] for r in self._all("SELECT * FROM manual_links WHERE release_id=?", (release_id,))}

    def manual_links_changed(self, release_id: int, saved_at: str) -> bool:
        return bool(self._all("SELECT 1 FROM manual_links WHERE release_id=? AND saved_at>?", (release_id, saved_at)))

    def set_override(self, release_id: int, position: str, action: str, detail: str | None = None) -> None:
        self._run("INSERT OR REPLACE INTO overrides VALUES (?,?,?,?,?)", (release_id, position, action, detail, now()))

    def overrides(self, release_id: int) -> dict[str, dict]:
        return {r["position"]: {"action": r["action"], "detail": r["detail"]}
                for r in self._all("SELECT * FROM overrides WHERE release_id=?", (release_id,))}
