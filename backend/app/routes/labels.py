"""Labels: for a record you own, or for any release (blank or from a Discogs link). Never stored."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import label_presets, queries, records
from app.deps import discogs_errors, get_db, get_discogs, require_record
from app.discogs import DiscogsClient, release_to_record, release_to_tracks
from app.labels import data as label_data
from app.labels.api import LabelRender, draw
from app.labels.data import LabelData
from app.schemas import FromDiscogs, LabelPresetIn, LabelPresetList

router = APIRouter(prefix="/api", tags=["labels"])


def require_owned(conn: sqlite3.Connection, record_id: int) -> None:
    """A record's label goes on the shelf, so only records you own get one."""
    if require_record(conn, record_id)["status"] != "owned":
        raise HTTPException(409, "only records in your library get a label; this one is not owned")


@router.get("/records/{record_id}/label", response_model=LabelData)
def get_label(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> LabelData:
    """The label as the database describes it: the starting point for the editor."""
    require_owned(conn, record_id)
    return label_data.build(queries.record_detail(conn, record_id))


@router.post("/records/{record_id}/label/render", response_model=LabelRender)
def render_label(record_id: int, body: LabelData, conn: sqlite3.Connection = Depends(get_db)) -> LabelRender:
    """Draw the (possibly edited) label. Nothing is stored: edits apply to this print only."""
    require_owned(conn, record_id)
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


# ---- presets: a saved look any label can start from ----

@router.get("/label-presets", response_model=LabelPresetList)
def list_label_presets(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {"items": label_presets.list_all(conn)}


@router.post("/label-presets", status_code=201, response_model=LabelPresetList)
def save_label_preset(body: LabelPresetIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Save the look under a name; an existing preset with that name is replaced."""
    try:
        label_presets.save(conn, body.name, body.look.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"items": label_presets.list_all(conn)}


@router.delete("/label-presets/{preset_id}", response_model=LabelPresetList)
def delete_label_preset(preset_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        label_presets.delete(conn, preset_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"items": label_presets.list_all(conn)}
