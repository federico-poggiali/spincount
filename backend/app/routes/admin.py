import sqlite3
import subprocess
import sys

from fastapi import APIRouter, Depends, HTTPException, Request

from app import backfill, config
from app.audio import downloads
from app.audio import job as audio_job
from app.db import track_audio, track_youtube
from app.deps import get_db, get_runner
from app.jobs.runner import JobRunner
from app.schemas import (
    DownloadsCleared,
    DownloadsUsage,
    JobStarted,
    LibraryAudioStarted,
    OpenedPath,
    VaultStatus,
    VaultSyncOut,
)
from app.vault import EXAMPLES_FILE, VaultSyncer
from app.youtube import links as youtube_links

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _syncer(request: Request) -> VaultSyncer:
    syncer = getattr(request.app.state, "vault_syncer", None)
    if syncer is None:
        raise HTTPException(503, "vault sync is not running")
    return syncer


@router.post("/sync-vault", response_model=VaultSyncOut)
def sync_vault_now(request: Request) -> dict:
    return _syncer(request).run_now()


@router.get("/vault-status", response_model=VaultStatus)
def vault_status(request: Request) -> dict:
    syncer = _syncer(request)
    return {"vault_dir": str(syncer.vault_dir), "last_sync": syncer.last_result,
            "last_error": syncer.last_error}


@router.post("/backfill-styles", status_code=202, response_model=JobStarted)
def backfill_styles(runner: JobRunner = Depends(get_runner)) -> dict:
    """Fetch styles for records that have none yet. Runs as a job (Discogs allows 60 calls a minute)."""
    return {"job_id": runner.enqueue(backfill.JOB_TYPE), "status": "queued"}


@router.post("/find-audio", status_code=202, response_model=LibraryAudioStarted)
def find_audio_for_library(conn: sqlite3.Connection = Depends(get_db),
                           runner: JobRunner = Depends(get_runner)) -> dict:
    """Find audio for every record that has not been searched yet, one after the other. Records already
    searched are skipped, so running it again only continues where it stopped. BPM and key are not touched."""
    ids = [runner.enqueue(audio_job.JOB_TYPE, record_id)
           for record_id in track_audio.records_without_audio(conn)]
    return {"queued": len(ids), "job_ids": ids}


@router.post("/find-youtube", status_code=202, response_model=LibraryAudioStarted)
def find_youtube_for_library(conn: sqlite3.Connection = Depends(get_db),
                             runner: JobRunner = Depends(get_runner)) -> dict:
    """Find every track not searched yet on YouTube, record by record (links only, no quota used). Running it
    again only continues where it stopped."""
    ids = [runner.enqueue(youtube_links.JOB_TYPE, record_id)
           for record_id in track_youtube.records_without_youtube(conn)]
    return {"queued": len(ids), "job_ids": ids}


@router.get("/downloads", response_model=DownloadsUsage)
def downloads_usage() -> dict:
    """How much audio the app has downloaded and still keeps (never your own files)."""
    return downloads.usage()


@router.post("/clear-downloads", response_model=DownloadsCleared)
def clear_downloads(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Delete every download no track still needs (kept: analysis waiting for you, or never analysed)."""
    return downloads.clear(conn)


@router.post("/open-vault", response_model=OpenedPath)
def open_vault() -> dict:
    """Reveal the Dataview examples file in Finder (macOS only; elsewhere just report the path)."""
    target = config.VAULT_DIR / EXAMPLES_FILE
    if sys.platform != "darwin" or not target.exists():
        return {"opened": False, "path": str(target)}
    subprocess.run(["open", "-R", str(target)], check=False)
    return {"opened": True, "path": str(target)}
