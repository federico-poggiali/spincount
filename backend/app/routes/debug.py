"""The test-run panel's feed: what runs in the background now, what waits, and how long recent jobs took.

Answers only in `make run-test`; otherwise 404, and the panel stays hidden. Not part of the API schema.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.activity import activity
from app.deps import get_db

router = APIRouter(prefix="/api/debug", tags=["debug"], include_in_schema=False)


@router.get("/activity")
def get_activity(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if not activity.enabled:
        raise HTTPException(404, "not found")
    snap = activity.snapshot()
    queued = [dict(r) for r in conn.execute(
        "SELECT id, type, record_id, created_at FROM jobs WHERE status = 'queued' ORDER BY id")]
    jobs = ([snap["current"]] if snap["current"] else []) + snap["recent"] + queued
    ids = sorted({j["record_id"] for j in jobs if j.get("record_id") is not None})
    names = {}
    if ids:
        marks = ",".join("?" * len(ids))
        names = {r["id"]: f"{r['artist']} – {r['title']}" for r in conn.execute(
            f"SELECT id, artist, title FROM records WHERE id IN ({marks})", ids)}
    for j in jobs:
        j["record"] = names.get(j.get("record_id"))
    return {**snap, "queued": queued}
