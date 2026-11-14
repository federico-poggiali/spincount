"""Copies of an owned record and the shelf place of each (copy 1's place is the record's own)."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import copies, crate, records
from app.deps import get_db, require_record
from app.schemas import CopyOut, CopyPlace

router = APIRouter(prefix="/api", tags=["copies"])


def _owned(conn: sqlite3.Connection, record_id: int) -> None:
    if require_record(conn, record_id)["status"] != "owned":
        raise HTTPException(409, "only records you own have copies")


def _section(conn: sqlite3.Connection, section_id: int | None) -> None:
    if section_id is not None and not crate.section_exists(conn, section_id):
        raise HTTPException(404, "section not found")


def _copy(conn: sqlite3.Connection, copy_id: int) -> dict:
    copy = copies.get(conn, copy_id)
    if copy is None:
        raise HTTPException(404, "copy not found")
    return copy


@router.get("/records/{record_id}/copies", response_model=list[CopyOut])
def list_copies(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    require_record(conn, record_id)
    return copies.for_record(conn, record_id)


@router.post("/records/{record_id}/copies", status_code=201, response_model=list[CopyOut])
def add_copy(record_id: int, body: CopyPlace | None = None,
             conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    """One more copy of the record, unsorted unless a section is given."""
    _owned(conn, record_id)
    section_id = body.section_id if body else None
    _section(conn, section_id)
    copies.add(conn, record_id, section_id)
    return copies.for_record(conn, record_id)


@router.patch("/copies/{copy_id}", response_model=list[CopyOut])
def place_copy(copy_id: int, body: CopyPlace, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    copy = _copy(conn, copy_id)
    _section(conn, body.section_id)
    copies.place(conn, copy_id, body.section_id)
    return copies.for_record(conn, copy["record_id"])


@router.delete("/copies/{copy_id}", response_model=list[CopyOut])
def delete_copy(copy_id: int, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    """Drop a second (or later) copy. Copy 1 is the record itself: delete the record instead."""
    copy = _copy(conn, copy_id)
    copies.delete(conn, copy_id)
    if records.get(conn, copy["record_id"]) is None:
        return []
    return copies.for_record(conn, copy["record_id"])
