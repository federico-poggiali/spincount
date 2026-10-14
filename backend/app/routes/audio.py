"""Audio found for a record's tracks: results, the preview plan, playback helpers, and searching again."""
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import config
from app.audio import job as audio_job
from app.audio.previews import plan_for_record
from app.db import records, track_audio, tracks
from app.deps import get_db, get_runner
from app.jobs.runner import JobRunner
from app.schemas import JobStarted, TrackAudioOut

router = APIRouter(tags=["audio"])


class RecordAudioOut(BaseModel):
    tracks: list[TrackAudioOut]  # tracks never searched are left out
    previews: dict  # audioresearch's plan: {tracks: {position: option | null}, families, stores}


class FindAudioRequest(BaseModel):
    refresh: bool = False  # search again even where audio was already found


class BandcampEmbed(BaseModel):
    kind: str  # "track" | "album"
    id: int


def _record(conn: sqlite3.Connection, record_id: int) -> dict:
    record = records.get(conn, record_id)
    if record is None:
        raise HTTPException(404, "record not found")
    return record


@router.get("/api/records/{record_id}/audio", response_model=RecordAudioOut)
def record_audio(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """What audioresearch found for each track, and which link each track plays."""
    _record(conn, record_id)
    return {"tracks": list(track_audio.for_record(conn, record_id).values()),
            "previews": plan_for_record(conn, record_id)}


@router.post("/api/records/{record_id}/find-audio", status_code=202, response_model=JobStarted)
def find_audio(record_id: int, body: FindAudioRequest | None = None,
               conn: sqlite3.Connection = Depends(get_db), runner: JobRunner = Depends(get_runner)) -> dict:
    """Search for this record's audio (again, with `refresh`). BPM and key are not touched."""
    if _record(conn, record_id)["discogs_release_id"] is None:
        raise HTTPException(400, "record has no Discogs release id, so nothing to search for")
    params = {"refresh": True} if body and body.refresh else None
    return {"job_id": runner.enqueue(audio_job.JOB_TYPE, record_id, params), "status": "queued"}


_BINARY = {"schema": {"type": "string", "format": "binary"}}
_AUDIO_FILE = {200: {"description": "The audio file, as stored",
                     "content": {"application/octet-stream": _BINARY}}}


@router.get("/api/tracks/{track_id}/audio-file", response_class=FileResponse, responses=_AUDIO_FILE)
def track_audio_file(track_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Your own file for a track, so the page can play it. Only files level 0 matched inside AUDIO_DIR."""
    track = tracks.get(conn, track_id)
    found = track_audio.for_record(conn, track["record_id"]).get(track_id) if track else None
    if found is None:
        raise HTTPException(404, "no audio found for this track")
    paths = ([found["audio_path"]] if found["source"] == "local_files" else []) + \
            [a.get("audio_path") for a in found["alternatives"] if a.get("source") == "local_files"]
    root = config.AUDIO_DIR.resolve()
    for p in filter(None, paths):
        path = Path(p).resolve()
        if root in path.parents and path.is_file():
            return FileResponse(path)
    raise HTTPException(404, "no file of yours for this track")


@router.get("/api/audio/bandcamp-embed", response_model=BandcampEmbed)
def bandcamp_embed(url: str) -> dict:
    """The numeric id Bandcamp's embed player needs (it is only on the page)."""
    if not url.startswith("https://") or not urlparse(url).netloc.endswith("bandcamp.com"):
        raise HTTPException(400, "not a Bandcamp link")
    from audioresearch import http
    from audioresearch.parsers.bandcamp import parse_item_id

    try:
        item = parse_item_id(http.shared().get_text(url, site="bandcamp", adapter="spincount"))
    except Exception as exc:  # any network or parse failure means no player; the page offers the link
        raise HTTPException(502, f"Bandcamp page unreadable: {exc}") from exc
    if not item:
        raise HTTPException(404, "no Bandcamp id on that page")
    return {"kind": item[0], "id": item[1]}
