"""Your own audio files: the folder per record (audio/<discogs release id>/) and matching them to tracks.

The matching is audioresearch's level 0 (by position in the file name, then by title; never a guess)."""
from pathlib import Path

from audioresearch.adapters.local_files import AUDIO_EXTENSIONS, find_audio_files, match_files
from audioresearch.models import TrackRef

from app import config

__all__ = ["AUDIO_EXTENSIONS", "audio_folder", "match_own_files"]


def audio_folder(record: dict, audio_dir: Path | None = None) -> Path | None:
    if record["discogs_release_id"] is None:
        return None
    return (audio_dir or config.AUDIO_DIR) / str(record["discogs_release_id"])


def match_own_files(record: dict, tracks: list[dict], audio_dir: Path | None = None) -> dict:
    """{"folder", "matched": [{track_id, position, file, method, score}], "unmatched_files": [{file, reason}],
    "unmatched_track_ids": [...]} for the record's folder against all of its tracks."""
    folder = audio_folder(record, audio_dir)
    files = find_audio_files(folder) if folder else []
    by_position = {t["position"]: t for t in tracks}
    report = match_files(files, [TrackRef(t["position"], t["artist"] or "", t["title"]) for t in tracks])
    return {
        "folder": str(folder) if folder else None,
        "matched": [{**m, "track_id": by_position[m["position"]]["id"]} for m in report["matched"]],
        "unmatched_files": report["unmatched_files"],
        "unmatched_track_ids": [by_position[p]["id"] for p in report["unmatched_tracks"]],
    }
