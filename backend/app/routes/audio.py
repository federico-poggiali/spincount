"""Audio for a record's tracks: what was found, which link plays, playback helpers, uploads, search again."""
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app import config
from app.analysis import job as analysis_job
from app.audio import downloads, sources, stage
from app.audio import job as audio_job
from app.audio.files import AUDIO_EXTENSIONS, audio_folder
from app.audio.previews import plan_for_record
from app.db import track_audio, tracks
from app.deps import get_db, get_runner, require_record
from app.jobs.runner import JobRunner
from app.schemas import AudioSourceGroup, BandcampEmbed, JobStarted, RecordAudioOut, Uploaded

router = APIRouter(tags=["audio"])

MAX_UPLOAD = 1024 * 1024 * 1024  # one file


@router.get("/api/records/{record_id}/audio", response_model=RecordAudioOut)
def record_audio(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """What audioresearch found for each track, and which link each track plays."""
    record = require_record(conn, record_id)
    all_tracks = tracks.list_for_record(conn, record_id)
    usable, _ = analysis_job.audio_for_analysis(conn, record, all_tracks)
    usable = set(usable) | downloads.cleaned(conn, [t["id"] for t in all_tracks])  # fetched again on analyse
    return {"tracks": list(track_audio.for_record(conn, record_id).values()),
            "previews": plan_for_record(conn, record_id), "analysable_track_ids": sorted(usable)}


@router.post("/api/records/{record_id}/find-audio", status_code=202, response_model=JobStarted)
def find_audio(record_id: int, conn: sqlite3.Connection = Depends(get_db),
               runner: JobRunner = Depends(get_runner)) -> dict:
    """Search this record's audio from scratch; tracks covered by your own files are left alone. Fast or
    lengthy, and which sources, come from Settings. BPM and key are not touched."""
    if require_record(conn, record_id)["discogs_release_id"] is None:
        raise HTTPException(400, "record has no Discogs release id, so nothing to search for")
    return {"job_id": runner.enqueue(audio_job.JOB_TYPE, record_id, {"refresh": True}), "status": "queued"}


@router.get("/api/audio/sources", response_model=list[AudioSourceGroup])
def audio_sources() -> list[dict]:
    """The sources the audio search can use, grouped as Settings shows them."""
    return sources.groups()


@router.post("/api/records/{record_id}/upload-audio", status_code=201, response_model=Uploaded)
async def upload_audio(record_id: int, request: Request, filename: str = Query(min_length=1),
                       conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Put one of your own files in the record's audio folder (the request body is the file) and match it
    to its track by its name. Nothing is searched; your file becomes that track's audio."""
    record = require_record(conn, record_id)
    folder = audio_folder(record)
    if folder is None:
        raise HTTPException(400, "record has no Discogs release id, so it has no audio folder")
    if Path(filename).name != filename or filename.startswith("."):
        raise HTTPException(422, "filename must be a plain file name")
    if Path(filename).suffix.lower() not in AUDIO_EXTENSIONS:
        raise HTTPException(422, f"not an audio file (use {', '.join(sorted(AUDIO_EXTENSIONS))})")
    folder.mkdir(parents=True, exist_ok=True)
    target, size = folder / filename, 0
    try:
        with target.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "file is too large")
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "the file is empty")
    matched = stage.store_own_files(conn, record, tracks.list_for_record(conn, record_id))
    return {"file": filename, "matched_track_ids": matched}


_BINARY = {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}
_AUDIO_FILE = {200: {"description": "The audio file, as stored", "content": _BINARY}}


@router.get("/api/tracks/{track_id}/audio-file", response_class=FileResponse, responses=_AUDIO_FILE)
def track_audio_file(track_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Your own file for a track, for the player: only files level 0 matched, inside AUDIO_DIR."""
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
