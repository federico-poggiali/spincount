"""The 'analysis' job: BPM and key from audio that is already there. Nothing is searched or downloaded.

A track is analysed from your own file when it has one (the reference), otherwise from the file the audio
search found and checked. A track with neither is left alone: search or upload its audio first.

Results are stored as proposals; the owner validates them onto the tracks (see validate)."""
import sqlite3
from collections.abc import Callable
from pathlib import Path

from app.analysis import engine
from app.audio.files import match_own_files
from app.db import _util, proposals, records, track_audio, tracks

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


def audio_for_analysis(conn: sqlite3.Connection, record: dict, all_tracks: list[dict],
                       audio_dir: Path | None = None) -> tuple[dict[int, dict], dict]:
    """({track id: {"path", "own", "source", "quality"}}, the own-files match report): the file each track
    would be analysed from. Your own file first, then the audio search's file when the track was found."""
    own = match_own_files(record, all_tracks, audio_dir)
    out = {m["track_id"]: {"path": Path(own["folder"]) / m["file"], "own": True, "source": "local_files",
                           "quality": "full"} for m in own["matched"]}
    for track_id, a in track_audio.for_record(conn, record["id"]).items():
        if track_id in out or a["status"] != "found" or not a["audio_path"]:
            continue
        path = Path(a["audio_path"])
        if path.is_file():
            out[track_id] = {"path": path, "own": a["source"] == "local_files", "source": a["source"],
                             "quality": a["quality"]}
    return out, own


def make_handler(analyze: Callable[[Path], dict] = engine.analyze, audio_dir: Path | None = None,
                 research_fn: Callable | None = None) -> Callable[[sqlite3.Connection, dict], dict]:
    """`research_fn` (the audio search) is used only when a track's download was deleted after an earlier
    validation (`fetch_again`): the record is searched again first, which downloads it again."""
    def handler(conn: sqlite3.Connection, job: dict) -> dict:
        record = records.get(conn, job["record_id"])
        if record is None:
            raise ValueError("record no longer exists")
        params = job.get("params") or {}
        all_tracks = tracks.list_for_record(conn, record["id"])
        selected = set(params["track_ids"]) if params.get("track_ids") is not None else None
        searched_again = None
        if params.get("fetch_again") and research_fn is not None:
            from app.audio import stage
            searched_again = stage.run(conn, record, all_tracks, research_fn, refresh=True)
        audio, own = audio_for_analysis(conn, record, all_tracks, audio_dir)

        from_files: list[int] = []
        from_found: list[int] = []
        no_audio: list[int] = []
        errors: list[dict] = []
        for t in all_tracks:
            if selected is not None and t["id"] not in selected:
                continue
            a = audio.get(t["id"])
            if a is None:
                no_audio.append(t["id"])
                continue
            try:
                result = analyze(a["path"])
            except Exception as exc:
                errors.append({"file": a["path"].name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            _propose(conn, t["id"], result, a["path"] if a["own"] else None)
            (from_files if a["own"] else from_found).append(t["id"])

        return {
            "from_audio_files_track_ids": from_files,
            "from_found_audio_track_ids": from_found,
            "no_data_track_ids": no_audio,
            "audio_files": own,
            "errors": errors,
            **({"searched_again": searched_again} if searched_again is not None else {}),
        }

    return handler
