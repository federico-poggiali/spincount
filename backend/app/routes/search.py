import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.db import queries
from app.deps import get_db
from app.schemas import ExactResults

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search/exact", response_model=ExactResults)
def exact(q: Annotated[str, Query(min_length=1)], limit: Annotated[int, Query(ge=1, le=100)] = 20,
          conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Notes with a highlighted snippet, plus records whose artist, title or label match."""
    return queries.exact_search(conn, q, limit)
