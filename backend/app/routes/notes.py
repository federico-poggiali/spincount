import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import notes, records, tracks
from app.deps import get_db
from app.schemas import NoteCreate, NoteOut, NotePatch

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.post("", status_code=201, response_model=NoteOut)
def create_note(body: NoteCreate, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if (body.record_id is None) == (body.track_id is None):
        raise HTTPException(422, "a note belongs to exactly one of record_id or track_id")
    if body.record_id is not None and records.get(conn, body.record_id) is None:
        raise HTTPException(404, "record not found")
    if body.track_id is not None and tracks.get(conn, body.track_id) is None:
        raise HTTPException(404, "track not found")
    note_id = notes.create(conn, body=body.body, record_id=body.record_id, track_id=body.track_id)
    return notes.get(conn, note_id)


@router.patch("/{note_id}", response_model=NoteOut)
def patch_note(note_id: int, body: NotePatch, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if notes.get(conn, note_id) is None:
        raise HTTPException(404, "note not found")
    notes.update(conn, note_id, body.body)
    return notes.get(conn, note_id)


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    if not notes.delete(conn, note_id):
        raise HTTPException(404, "note not found")
    return Response(status_code=204)
