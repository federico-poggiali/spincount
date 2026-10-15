"""FastAPI dependencies and the small guards every route shares."""
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import HTTPException, Query, Request

from app import config, keys
from app.db import connect, queries, records
from app.discogs import DiscogsBadUrl, DiscogsClient, DiscogsError, DiscogsNotFound
from app.jobs.runner import JobRunner
from app.schemas import Status


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def get_discogs() -> DiscogsClient:
    try:
        return DiscogsClient(config.DISCOGS_TOKEN)
    except DiscogsError as exc:
        raise HTTPException(503, str(exc)) from exc


def get_discogs_lazy(request: Request) -> Callable[[], DiscogsClient]:
    """The Discogs client factory, called only if a request needs Discogs (a missing token is
    then a 503 for that request alone). Honours test overrides of get_discogs."""
    return request.app.dependency_overrides.get(get_discogs, get_discogs)


def get_runner(request: Request) -> JobRunner:
    return request.app.state.runner


def library_filters(
    bpm_min: Annotated[float | None, Query(ge=0)] = None,
    bpm_max: Annotated[float | None, Query(ge=0)] = None,
    key: str | None = None,
    tag: Annotated[list[str], Query()] = [],  # noqa: B006 (FastAPI query default)
    style: Annotated[list[str], Query()] = [],  # noqa: B006
    status: Status | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> queries.Filters:
    """The filters shared by the record and track lists."""
    return queries.Filters(bpm_min=bpm_min, bpm_max=bpm_max, camelot=parse_key(key) if key else None,
                           tags=[t.strip().lower() for t in tag if t.strip()],
                           styles=records.clean_styles(style), status=status, q=q, limit=limit, offset=offset)


def require_record(conn: sqlite3.Connection, record_id: int) -> dict:
    record = records.get(conn, record_id)
    if record is None:
        raise HTTPException(404, "record not found")
    return record


def parse_key(text: str) -> str:
    """A key as typed ('F# minor', 'Am', '11A') -> its Camelot code, or a 422."""
    camelot = keys.to_camelot(text)
    if camelot is None:
        raise HTTPException(422, f"unrecognised key '{text}' (use e.g. 'F# minor', 'Am' or '11A')")
    return camelot


@contextmanager
def discogs_errors():
    """Discogs failures as HTTP: unknown release 404, not a Discogs link 400, anything else 502."""
    try:
        yield
    except DiscogsNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except DiscogsBadUrl as exc:
        raise HTTPException(400, str(exc)) from exc
    except DiscogsError as exc:
        raise HTTPException(502, str(exc)) from exc
