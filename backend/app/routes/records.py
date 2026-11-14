import sqlite3
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response

from app import intake as intake_service
from app import library_sync, sync
from app.analysis import job as analysis_job
from app.audio import job as audio_job
from app.db import _util, proposals, queries, records, settings, tracks
from app.deps import (
    discogs_errors,
    get_db,
    get_discogs,
    get_discogs_lazy,
    get_runner,
    library_filters,
    require_record,
)
from app.discogs import DiscogsClient, release_to_record
from app.jobs.runner import JobRunner
from app.schemas import (
    AnalyzeRequest,
    DiscardRequest,
    IntakeRequest,
    IntakeResponse,
    JobStarted,
    Page,
    RecordDetail,
    RecordOut,
    RecordPatch,
    RecordSummary,
    ValidateRequest,
)
from app.youtube import links as youtube_links

router = APIRouter(prefix="/api/records", tags=["records"])


@router.post("/intake", response_model=IntakeResponse)
def intake(body: IntakeRequest, response: Response, conn: sqlite3.Connection = Depends(get_db),
           discogs: DiscogsClient = Depends(get_discogs), runner: JobRunner = Depends(get_runner)) -> dict:
    with discogs_errors():
        result = intake_service.intake(conn, discogs, body.discogs_url, body.status)
    response.status_code = 201 if result.created else 200
    # A new record starts finding its audio straight away and, if Settings say so, goes into the Discogs
    # collection (owned) or wantlist (wishlist). BPM and key wait for "Analyse" (which reuses the audio).
    jobs = {}
    if result.created and result.record["discogs_release_id"] is not None:
        record_id = result.record["id"]
        jobs["audio"] = runner.enqueue(audio_job.JOB_TYPE, record_id)
        if settings.get(conn, "youtube_playlist"):  # after the audio job, so its YouTube links are reused
            jobs["youtube"] = runner.enqueue(youtube_links.JOB_TYPE, record_id)
        if result.record["status"] == "owned" and settings.get(conn, "auto_collection"):
            jobs["discogs_sync"] = runner.enqueue(sync.JOB_TYPE, record_id)
        elif result.record["status"] != "owned" and settings.get(conn, "auto_wantlist"):
            jobs["discogs_want"] = runner.enqueue(library_sync.WANT, record_id)
    return {**result.record, "resolved_from_master": result.resolved_from_master, "jobs": jobs or None}


@router.get("", response_model=Page[RecordSummary])
def list_records(f: queries.Filters = Depends(library_filters),
                 conn: sqlite3.Connection = Depends(get_db)) -> dict:
    items, total = queries.list_records(conn, f)
    return {"items": items, "total": total, "limit": f.limit, "offset": f.offset}


@router.get("/recently-traded", response_model=list[RecordOut])
def recently_traded(conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    """Records that moved from the wishlist to owned, newest first (the last 90 days, at most 20)."""
    rows = conn.execute(
        "SELECT * FROM records WHERE status = 'owned' "
        "AND traded_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-90 days') "
        "ORDER BY traded_at DESC LIMIT 20").fetchall()
    decoded = [records.decode(dict(r)) for r in rows]
    return [{**r, "styles": r["styles"] or []} for r in decoded]


@router.get("/{record_id}", response_model=RecordDetail)
def get_record(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    detail = queries.record_detail(conn, record_id)
    if detail is None:
        raise HTTPException(404, "record not found")
    return detail


@router.patch("/{record_id}", response_model=RecordDetail)
def patch_record(record_id: int, body: RecordPatch, conn: sqlite3.Connection = Depends(get_db),
                 runner: JobRunner = Depends(get_runner),
                 discogs: Callable[[], DiscogsClient] = Depends(get_discogs_lazy)) -> dict:
    before = require_record(conn, record_id)
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(k, "x") is None for k in ("artist", "title", "status", "styles")):
        raise HTTPException(422, "artist, title, status and styles cannot be null")
    if changes.pop("reset_styles", False):
        if "styles" in changes:
            raise HTTPException(422, "send either styles or reset_styles, not both")
        changes.update(_discogs_styles(before, discogs))
    elif "styles" in changes:
        changes["styles_manual"] = 1  # what the user types always wins over Discogs
    becomes_owned = changes.get("status") == "owned" and before["status"] != "owned"
    if becomes_owned:
        changes["traded_at"] = _util.now()  # off the wishlist: shown as recently traded
    records.update(conn, record_id, **changes)
    # A status change reaches Discogs as intake would, if Settings say so. Nothing is ever removed there.
    if before["discogs_release_id"]:
        if (becomes_owned and not before["discogs_collection_synced"]
                and settings.get(conn, "auto_collection")):
            runner.enqueue(sync.JOB_TYPE, record_id)
        elif (changes.get("status") == "wantlist" and before["status"] == "owned"
                and not before["discogs_wantlist_synced"] and settings.get(conn, "auto_wantlist")):
            runner.enqueue(library_sync.WANT, record_id)
    return queries.record_detail(conn, record_id)


def _discogs_styles(record: dict, discogs: Callable[[], DiscogsClient]) -> dict:
    """Fetch the record's styles afresh and release the manual lock."""
    if record["discogs_release_id"] is None:
        raise HTTPException(400, "record has no Discogs release id, so nothing to re-fetch")
    with discogs_errors():
        fresh = release_to_record(discogs().release(record["discogs_release_id"]))
    return {"styles": fresh["styles"], "styles_manual": 0}


@router.delete("/{record_id}", status_code=204)
def delete_record(record_id: int, from_discogs: bool = False, conn: sqlite3.Connection = Depends(get_db),
                  runner: JobRunner = Depends(get_runner)) -> Response:
    """Delete the record with its tracks, notes and tag links. An owned record that is in the Discogs
    collection leaves it too with from_discogs; otherwise it stays there and imports skip it."""
    record = require_record(conn, record_id)
    records.delete(conn, record_id)
    if record["status"] == "owned" and record["discogs_release_id"] and record["discogs_collection_synced"]:
        if from_discogs:
            runner.enqueue(library_sync.REMOVE, params={"discogs_release_id": record["discogs_release_id"]})
        else:
            library_sync.keep_on_discogs(conn, record)
    return Response(status_code=204)


@router.post("/{record_id}/sync-discogs", status_code=202, response_model=JobStarted)
def sync_discogs(record_id: int, conn: sqlite3.Connection = Depends(get_db),
                 runner: JobRunner = Depends(get_runner)) -> dict:
    record = require_record(conn, record_id)
    if record["status"] != "owned":
        raise HTTPException(400, f"only owned records are collected (status: {record['status']})")
    return {"job_id": runner.enqueue(sync.JOB_TYPE, record_id), "status": "queued"}


@router.post("/{record_id}/analyze", status_code=202, response_model=JobStarted)
def analyze(record_id: int, body: AnalyzeRequest | None = None, conn: sqlite3.Connection = Depends(get_db),
            runner: JobRunner = Depends(get_runner)) -> dict:
    """Analyse the whole record, or only `track_ids` when given, from audio that is already there: your own
    files, then what the audio search found. 409 when none of those tracks has audio yet."""
    record = require_record(conn, record_id)
    body = body or AnalyzeRequest()
    all_tracks = tracks.list_for_record(conn, record_id)
    wanted = {t["id"] for t in all_tracks}
    params = {}
    if body.track_ids is not None:
        if not body.track_ids or not set(body.track_ids) <= wanted:
            raise HTTPException(400, "track_ids must be a non-empty list of tracks on this record")
        wanted = set(body.track_ids)
        params["track_ids"] = sorted(wanted)
    if not wanted & set(analysis_job.audio_for_analysis(conn, record, all_tracks)[0]):
        raise HTTPException(409, "no audio to analyse yet: search or upload audio first")
    return {"job_id": runner.enqueue(analysis_job.JOB_TYPE, record_id, params or None), "status": "queued"}


NOT_PENDING = "track_ids must be tracks of this record with analysis waiting for validation"


@router.post("/{record_id}/validate", response_model=RecordDetail)
def validate(record_id: int, body: ValidateRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Save the chosen tracks' analysis proposals onto them. Only records you own can be validated."""
    if require_record(conn, record_id)["status"] != "owned":
        raise HTTPException(409, "only records in your library can be validated; this one is not owned")
    if not set(body.track_ids) <= set(proposals.for_record(conn, record_id)):
        raise HTTPException(400, NOT_PENDING)
    analysis_job.validate(conn, sorted(set(body.track_ids)), body.overwrite_manual)
    return queries.record_detail(conn, record_id)


@router.post("/{record_id}/discard", response_model=RecordDetail)
def discard(record_id: int, body: DiscardRequest | None = None,
            conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Drop analysis proposals (all of them, or only `track_ids`) without touching the tracks."""
    require_record(conn, record_id)
    pending = proposals.for_record(conn, record_id)
    ids = list(pending) if body is None or body.track_ids is None else body.track_ids
    if not set(ids) <= set(pending):
        raise HTTPException(400, NOT_PENDING)
    proposals.delete(conn, ids)
    return queries.record_detail(conn, record_id)
