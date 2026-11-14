"""Syncing the library with Discogs (see app.library_sync) and the settings that drive it."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from app import library_sync
from app.db import settings
from app.deps import discogs_errors, get_db, get_discogs, get_runner
from app.discogs import DiscogsClient
from app.jobs.runner import JobRunner
from app.schemas import AppSettings, AppSettingsPatch, JobStarted, PushRequest, ResetRequest, SyncCompare

router = APIRouter(prefix="/api", tags=["discogs sync"])


@router.get("/settings", response_model=AppSettings)
def get_settings(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return settings.get_all(conn)


@router.patch("/settings", response_model=AppSettings)
def patch_settings(body: AppSettingsPatch, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return settings.update(conn, body.model_dump(exclude_none=True))


@router.get("/discogs-sync/compare", response_model=SyncCompare)
def sync_compare(conn: sqlite3.Connection = Depends(get_db),
            discogs: DiscogsClient = Depends(get_discogs)) -> dict:
    """What differs between the library and the Discogs collection. Changes nothing."""
    with discogs_errors():
        return library_sync.compare(conn, discogs)


@router.post("/discogs-sync/push", status_code=202, response_model=JobStarted)
def sync_push(body: PushRequest, runner: JobRunner = Depends(get_runner)) -> dict:
    """Add exactly these owned records to the Discogs collection (the ones the preview listed)."""
    job_id = runner.enqueue(library_sync.PUSH, params={"record_ids": body.record_ids})
    return {"job_id": job_id, "status": "queued"}


@router.post("/discogs-sync/pull", status_code=202, response_model=JobStarted)
def sync_pull(runner: JobRunner = Depends(get_runner)) -> dict:
    """Import the Discogs collection records missing here; wishlist ones become owned."""
    return {"job_id": runner.enqueue(library_sync.PULL), "status": "queued"}


@router.post("/discogs-sync/reset", status_code=202, response_model=JobStarted)
def sync_reset(body: ResetRequest, runner: JobRunner = Depends(get_runner)) -> dict:
    """Back up, delete every owned record and its data, then import the Discogs collection."""
    if body.confirm != library_sync.RESET_WORD:
        raise HTTPException(422, f'type "{library_sync.RESET_WORD}" to confirm the reset')
    return {"job_id": runner.enqueue(library_sync.RESET), "status": "queued"}


@router.post("/discogs-sync/wantlist", status_code=202, response_model=JobStarted)
def sync_wantlist_push(body: PushRequest, runner: JobRunner = Depends(get_runner)) -> dict:
    """Put exactly these wishlist records on the Discogs wantlist (the ones the preview listed)."""
    job_id = runner.enqueue(library_sync.WANT_PUSH, params={"record_ids": body.record_ids})
    return {"job_id": job_id, "status": "queued"}


@router.post("/discogs-sync/wantlist-tidy", status_code=202, response_model=JobStarted)
def sync_wantlist_tidy(body: PushRequest, runner: JobRunner = Depends(get_runner)) -> dict:
    """Take exactly these owned records off the Discogs wantlist."""
    job_id = runner.enqueue(library_sync.WANT_TIDY, params={"record_ids": body.record_ids})
    return {"job_id": job_id, "status": "queued"}


@router.post("/discogs-sync/refresh", status_code=202, response_model=JobStarted)
def sync_refresh(runner: JobRunner = Depends(get_runner)) -> dict:
    """Release details and tracklists again from Discogs, keeping everything you added."""
    return {"job_id": runner.enqueue(library_sync.REFRESH), "status": "queued"}


@router.delete("/discogs-sync/kept/{release_id}", status_code=204)
def sync_forget_kept(release_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    """Let imports bring a release you once deleted here back again."""
    if not library_sync.forget_kept(conn, release_id):
        raise HTTPException(404, "that release is not on the kept list")
    return Response(status_code=204)
