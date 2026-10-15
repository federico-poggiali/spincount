"""Find BPM/key from the Discogs link alone, using the bpmkey pipeline.

Online databases first; if they are missing or disagree, bpmkey finds the audio itself (Discogs
videos, YouTube, SoundCloud, iTunes preview) and analyzes it.
"""
import logging

from bpmkey.analyze import clamp_bpm
from bpmkey.models import Track as BpmkeyTrack
from bpmkey.pipeline import Pipeline
from bpmkey.reconcile import is_analysis

from app.analysis.engine import alternate_bpm
from app.keys import key_name

log = logging.getLogger(__name__)
ENGINE = "bpmkey-lookup"


def lookup_tracks(record: dict, tracks: list[dict], release: dict) -> dict[int, dict]:
    """Return {track_id: analyze()-shaped result} for every track that got any data.

    Tracks that fail are logged and left out; one bad track never stops the rest.
    """
    pipeline = Pipeline()  # created here so its SQLite cache belongs to the calling thread
    out: dict[int, dict] = {}
    for t in tracks:
        bt = BpmkeyTrack(release_id=record["discogs_release_id"], position=t["position"],
                         artist=t["artist"] or record["artist"], title=t["title"],
                         duration=t["duration_sec"])
        try:
            result = next(iter(pipeline.run_tracks([bt], release)))
        except Exception:
            log.exception("lookup failed for track %s", t["id"])
            continue
        if result.bpm is None and result.camelot is None:
            continue
        audio = next((m for m in bt.measurements if is_analysis(m)), None)
        bpm = clamp_bpm(result.bpm) if result.bpm else None
        out[t["id"]] = {
            "bpm": bpm,
            "key": key_name(result.camelot),
            "camelot_key": result.camelot,
            "confidence": audio.confidence if audio else None,
            "raw": {
                "engine": ENGINE,
                "status": result.status,
                "note": result.note,
                "bpm": bpm,
                "bpm_alt": alternate_bpm(bpm) if bpm else None,
                "measurements": [
                    {"origin": m.origin, "bpm": m.bpm, "camelot": m.camelot, "confidence": m.confidence}
                    for m in bt.measurements
                ],
            },
        }
    return out
