"""Labels: for a record in the library, or for any release (blank or from a Discogs link). Never stored."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import queries, records
from app.deps import discogs_errors, get_db, get_discogs
from app.discogs import DiscogsClient, release_to_record, release_to_tracks
from app.labels import data as label_data
from app.labels.api import LabelRender, draw
from app.labels.data import LabelData
from app.schemas import FromDiscogs

router = APIRouter(prefix="/api", tags=["labels"])


@router.get("/records/{record_id}/label", response_model=LabelData)
def get_label(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> LabelData:
    """The label as the database describes it: the starting point for the editor."""
    detail = queries.record_detail(conn, record_id)
    if detail is None:
        raise HTTPException(404, "record not found")  # a label only exists for a record in the library
    return label_data.build(detail)


@router.post("/records/{record_id}/label/render", response_model=LabelRender)
def render_label(record_id: int, body: LabelData, conn: sqlite3.Connection = Depends(get_db)) -> LabelRender:
    """Draw the (possibly edited) label. Nothing is stored: edits apply to this print only."""
    if records.get(conn, record_id) is None:
        raise HTTPException(404, "record not found")
    return draw(body)


@router.post("/labels/from-discogs", response_model=LabelData)
def label_from_discogs(body: FromDiscogs, conn: sqlite3.Connection = Depends(get_db),
                       discogs: DiscogsClient = Depends(get_discogs)) -> LabelData:
    """Look a release up and describe it as a label. Nothing is stored; a record already in the
    library brings its BPM, key, tags and notes along."""
    with discogs_errors():
        release_id, _ = discogs.resolve(body.discogs_url)
        existing = records.get_by_discogs_id(conn, release_id)
        if existing:
            return label_data.build(queries.record_detail(conn, existing["id"]))
        release = discogs.release(release_id)
    return label_data.build({
        **release_to_record(release), "notes": [],
        "tracks": [{**t, "bpm": None, "key": None, "camelot_key": None, "tags": [], "notes": []}
                   for t in release_to_tracks(release)],
    })


@router.post("/labels/render", response_model=LabelRender)
def render_loose_label(body: LabelData) -> LabelRender:
    """Draw a label that belongs to no record. Nothing is stored."""
    return draw(body)
