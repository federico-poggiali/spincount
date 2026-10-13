"""Stage 4 helpers (stub until Step 8)."""
from __future__ import annotations

import re
from pathlib import Path

from .models import FetchedAudio, ReleaseIdentity


def dest_for(audio_dir: Path, identity: ReleaseIdentity, position: str, adapter: str) -> Path:
    """audio_cache/<release id>/<position>.<adapter>  (no extension: the adapter adds it)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", position) or "track"
    return audio_dir / str(identity.discogs_release_id) / f"{safe}.{adapter}"


def finalize(fetched: FetchedAudio, discogs_duration: int | None) -> FetchedAudio:
    return fetched
