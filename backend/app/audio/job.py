"""The 'audio' job: find audio for a record's tracks (audioresearch), nothing else.

Queued when a record is added and from Settings for the whole library. Analysis later reuses what it found.
"""
import sqlite3
from collections.abc import Callable
from pathlib import Path

from app.audio import stage
from app.db import records, tracks

JOB_TYPE = "audio"


def make_handler(research_fn: stage.ResearchFn,
                 audio_dir: Path | None = None) -> Callable[[sqlite3.Connection, dict], dict]:
    def handler(conn: sqlite3.Connection, job: dict) -> dict:
        record = records.get(conn, job["record_id"])
        if record is None:
            raise ValueError("record no longer exists")
        if record["discogs_release_id"] is None:
            raise ValueError("record has no Discogs release id")
        params = job.get("params") or {}
        report = stage.run(conn, record, tracks.list_for_record(conn, record["id"]), research_fn, audio_dir,
                           refresh=bool(params.get("refresh")), everything=bool(params.get("everything")))
        if "error" in report:  # here finding audio is the whole job, so a failure shows (and can be retried)
            raise RuntimeError(report["error"])
        return report

    return handler
