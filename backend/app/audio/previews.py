"""Which link each track plays, for the record page: audioresearch's preview plan over the stored results.

The same rules as the audioresearch viewer (`audioresearch/previews.py`): one record should sound like one
source, your own files first. Nothing is downloaded; embeds use the sites' official players.
"""
import sqlite3

from app.db import track_audio, tracks


def plan_for_record(conn: sqlite3.Connection, record_id: int) -> dict:
    from audioresearch.models import Quality, ReleaseResult, Status, TrackResult
    from audioresearch.previews import plan

    found = track_audio.for_record(conn, record_id)
    rows = [t for t in tracks.list_for_record(conn, record_id) if t["id"] in found]
    result = ReleaseResult(0, [
        TrackResult(t["position"], Status(found[t["id"]]["status"]), found[t["id"]]["audio_path"],
                    found[t["id"]]["source"], found[t["id"]]["level"], found[t["id"]]["url"],
                    Quality(found[t["id"]]["quality"]) if found[t["id"]]["quality"] else None,
                    found[t["id"]]["confidence"] or 0.0, found[t["id"]]["reason"] or "", [],
                    found[t["id"]]["alternatives"], found[t["id"]]["page"])
        for t in rows])
    return plan(result)
