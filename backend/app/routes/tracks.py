import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import queries, tracks
from app.deps import get_db, library_filters, parse_key
from app.keys import key_name
from app.schemas import Page, TrackHit, TrackOut, TrackPatch

router = APIRouter(prefix="/api/tracks", tags=["tracks"])


@router.get("", response_model=Page[TrackHit])
def list_tracks(f: queries.Filters = Depends(library_filters),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    items, total = queries.list_tracks(conn, f)
    return {"items": items, "total": total, "limit": f.limit, "offset": f.offset}


@router.get("/{track_id}", response_model=TrackOut)
def get_track(track_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    detail = queries.track_detail(conn, track_id)
    if detail is None:
        raise HTTPException(404, "track not found")
    return detail


@router.patch("/{track_id}", response_model=TrackOut)
def patch_track(track_id: int, body: TrackPatch, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if tracks.get(conn, track_id) is None:
        raise HTTPException(404, "track not found")
    if "bpm" in body.unlock and body.bpm is not None or "key" in body.unlock and body.key is not None:
        raise HTTPException(422, "cannot set and unlock the same field in one request")
    changes: dict = {f"{field}_manual": 0 for field in body.unlock}
    if body.bpm is not None:
        changes.update(bpm=body.bpm, bpm_manual=1)
    if body.key is not None:
        camelot = parse_key(body.key)
        changes.update(key=key_name(camelot), camelot_key=camelot, key_manual=1)
    tracks.update(conn, track_id, **changes)
    return queries.track_detail(conn, track_id)
