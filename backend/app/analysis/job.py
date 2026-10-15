"""The 'analysis' job: look BPM/key up from the Discogs link; your own audio files override.

Results are stored as proposals; the owner validates them onto the tracks (see validate)."""
import sqlite3
from collections.abc import Callable
from pathlib import Path

from app.analysis import engine, lookup
from app.audio import stage as audio_stage
from app.audio.files import match_own_files
from app.db import _util, proposals, records, tracks
from app.discogs import DiscogsClient

JOB_TYPE = "analysis"


def _propose(conn: sqlite3.Connection, track_id: int, result: dict, audio_path: Path | None) -> None:
    """Keep an analysis result as a proposal; nothing reaches the track until it is validated."""
    proposals.put(conn, track_id, bpm=result["bpm"], key=result["key"], camelot_key=result["camelot_key"],
                  confidence=result["confidence"], analysis_raw=result["raw"],
                  audio_path=str(audio_path) if audio_path else None, proposed_at=_util.now())


def validate(conn: sqlite3.Connection, track_ids: list[int], overwrite_manual: bool = False) -> None:
    """Copy these tracks' proposals onto them. A hand-entered value is kept unless overwrite_manual."""
    for track_id in track_ids:
        p = proposals.get(conn, track_id)
        current = tracks.get(conn, track_id)
        values = {"analysis_raw": p["analysis_raw"], "analyzed_at": p["proposed_at"]}
        if p["bpm"] is not None and (overwrite_manual or not current["bpm_manual"]):
            values.update(bpm=p["bpm"], bpm_manual=0)
        if p["camelot_key"] is not None and (overwrite_manual or not current["key_manual"]):
            # confidence describes the analysed key, so it only travels with it
            values.update(key=p["key"], camelot_key=p["camelot_key"], confidence=p["confidence"],
                          key_manual=0)
        if p["audio_path"]:
            values["audio_path"] = p["audio_path"]
        tracks.update(conn, track_id, **values)
    proposals.delete(conn, track_ids)


def make_handler(
    discogs_factory: Callable[[], DiscogsClient],
    lookup_fn: Callable[[dict, list[dict], dict], dict[int, dict]] = lookup.lookup_tracks,
    analyze: Callable[[Path], dict] = engine.analyze,
    audio_dir: Path | None = None,
    research_fn: audio_stage.ResearchFn | None = None,
) -> Callable[[sqlite3.Connection, dict], dict]:
    def handler(conn: sqlite3.Connection, job: dict) -> dict:
        record = records.get(conn, job["record_id"])
        if record is None:
            raise ValueError("record no longer exists")
        if record["discogs_release_id"] is None:
            raise ValueError("record has no Discogs release id")
        params = job.get("params") or {}
        all_tracks = tracks.list_for_record(conn, record["id"])
        selected = set(params["track_ids"]) if params.get("track_ids") is not None else None
        track_rows = [t for t in all_tracks if selected is None or t["id"] in selected]

        # 0. Find audio for the tracks (audioresearch); a failure is reported but never stops the analysis.
        audio_report = None
        if research_fn is not None:
            audio_report = audio_stage.run(conn, record, track_rows, research_fn, audio_dir,
                                           refresh=bool(params.get("refresh_audio")))

        # 1. From the Discogs link: online databases, then audio bpmkey finds itself.
        release = discogs_factory().release(record["discogs_release_id"])
        found = lookup_fn(record, track_rows, release)
        for track_id, result in found.items():
            _propose(conn, track_id, result, None)

        # 2. Your own files in audio/<release id>/ override the lookup.
        own = match_own_files(record, all_tracks, audio_dir)
        from_files: list[int] = []
        errors: list[dict] = []
        for m in own["matched"]:
            if selected is not None and m["track_id"] not in selected:
                continue
            path = Path(own["folder"]) / m["file"]
            try:
                result = analyze(path)
            except Exception as exc:
                errors.append({"file": m["file"], "error": f"{type(exc).__name__}: {exc}"})
                continue
            _propose(conn, m["track_id"], result, path)
            from_files.append(m["track_id"])

        got_data = set(found) | set(from_files)
        return {
            "looked_up_track_ids": sorted(found),
            "from_audio_files_track_ids": from_files,
            "no_data_track_ids": [t["id"] for t in track_rows if t["id"] not in got_data],
            "audio_files": own,
            "audio_research": audio_report,
            "errors": errors,
        }

    return handler
