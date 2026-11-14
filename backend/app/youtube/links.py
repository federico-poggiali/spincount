"""The 'youtube' job: a YouTube video for every track of a record, for "Add to YT playlist".

A YouTube link the audio search already found (a video linked on Discogs) is used as it is; every other track
is searched on YouTube (audioresearch.youtube_search: links only, nothing downloaded). Queued after the audio
job when a record is added, if Settings say so, and from Settings for the whole library.
"""
import sqlite3
from collections.abc import Callable

from app.db import _util, records, track_audio, track_youtube, tracks

JOB_TYPE = "youtube"

# (identity, track) -> best video or None; see audioresearch.youtube_search.find_track
FindFn = Callable[..., dict | None]


def from_audio(found: dict | None) -> str | None:
    """The YouTube video among what the audio search found for a track: its chosen link, else another."""
    from audioresearch.previews import youtube_id

    if not found:
        return None
    for url in [found.get("url"), *(a.get("url") for a in found["alternatives"])]:
        if url and (vid := youtube_id(url)):
            return vid
    return None


def _merge(stored: dict[int, dict], audio: dict[int, dict]) -> dict[int, dict]:
    """The stored videos, plus the audio search's YouTube link for every track not looked up for the playlist
    yet: a link that is already known shows (and can be added) without running the youtube job first."""
    out = dict(stored)
    for track_id, found in audio.items():
        if track_id not in out and (vid := from_audio(found)):
            out[track_id] = {"track_id": track_id, "video_id": vid, "source": "audio",
                             "found_at": found["found_at"], "title": None, "channel": None, "duration": None,
                             "confidence": None}
    return out


def videos_for_record(conn: sqlite3.Connection, record_id: int) -> dict[int, dict]:
    return _merge(track_youtube.for_record(conn, record_id), track_audio.for_record(conn, record_id))


def videos_for_tracks(conn: sqlite3.Connection, track_ids: list[int]) -> dict[int, dict]:
    return _merge(track_youtube.for_tracks(conn, track_ids), track_audio.for_tracks(conn, track_ids))


def find_for_record(conn: sqlite3.Connection, record: dict, find_fn: FindFn | None = None,
                    refresh: bool = False) -> dict:
    """Store a video (or "not on YouTube") for each track not searched yet; `refresh` searches them all again.
    Each track is stored as soon as it is done, so a failure part way keeps what was found."""
    from audioresearch.models import ReleaseIdentity, TrackRef
    from audioresearch.youtube_search import find_track

    find_fn = find_fn or find_track
    rows = tracks.list_for_record(conn, record["id"])
    done = {} if refresh else track_youtube.for_tracks(conn, [t["id"] for t in rows])
    refs = {t["id"]: TrackRef(t["position"], t["artist"] or record["artist"], t["title"], t["duration_sec"])
            for t in rows}
    identity = ReleaseIdentity(record["discogs_release_id"] or 0, record["artist"], record["title"],
                               record.get("label"), record.get("catno"), record.get("year"),
                               list(refs.values()))
    audio = track_audio.for_record(conn, record["id"])
    counts = {"audio": 0, "search": 0, "not_found": 0}
    for t in rows:
        if t["id"] in done:
            continue
        if vid := from_audio(audio.get(t["id"])):
            track_youtube.put(conn, t["id"], video_id=vid, source="audio", found_at=_util.now())
            counts["audio"] += 1
        elif hit := find_fn(identity, refs[t["id"]]):
            track_youtube.put(conn, t["id"], source="search", found_at=_util.now(), **hit)
            counts["search"] += 1
        else:
            track_youtube.put(conn, t["id"], video_id=None, found_at=_util.now())
            counts["not_found"] += 1
    return counts


def make_handler(find_fn: FindFn | None = None) -> Callable[[sqlite3.Connection, dict], dict]:
    def handler(conn: sqlite3.Connection, job: dict) -> dict:
        record = records.get(conn, job["record_id"])
        if record is None:
            raise ValueError("record no longer exists")
        return find_for_record(conn, record, find_fn, refresh=bool((job.get("params") or {}).get("refresh")))

    return handler
