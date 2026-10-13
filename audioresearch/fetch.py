"""Stage 4: downloading audio. Helpers adapters share, plus the quality ladder.

The adapter that found a candidate fetches it; `finalize` then measures the real file and sets the
real quality: `clip` under 60 s, `preview` when clearly shorter than the Discogs duration, else `full`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import config
from .adapters.base import AdapterError
from .models import FetchedAudio, Quality, ReleaseIdentity

CLIP_MAX_SECONDS = 60
PREVIEW_RATIO = 0.8          # under 80% of the Discogs duration (and 15+ s short) counts as a preview
PREVIEW_MIN_GAP = 15
CONTENT_TYPES = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac",
                 "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/wav": ".wav", "audio/x-wav": ".wav", "video/mp4": ".m4a"}


def dest_for(audio_dir: Path, identity: ReleaseIdentity, position: str, adapter: str) -> Path:
    """audio_cache/<release id>/<position>.<adapter>  (no extension: the adapter adds it)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", position) or "track"
    return audio_dir / str(identity.discogs_release_id) / f"{safe}.{adapter}"


def probe_duration(path: Path) -> float | None:
    """Real length in seconds: mutagen first, ffprobe as the fallback; None when neither can tell."""
    try:
        import mutagen

        f = mutagen.File(str(path))
        if f is not None and f.info is not None and getattr(f.info, "length", None):
            return float(f.info.length)
    except Exception:
        pass
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            return float(out) if out else None
        except (ValueError, subprocess.SubprocessError):
            return None
    return None


def classify(real_duration: float | None, discogs_duration: int | None, hint: Quality) -> Quality:
    if real_duration is None:
        return hint
    if real_duration < CLIP_MAX_SECONDS:
        return Quality.CLIP
    if discogs_duration:
        if real_duration < PREVIEW_RATIO * discogs_duration and discogs_duration - real_duration > PREVIEW_MIN_GAP:
            return Quality.PREVIEW
        return Quality.FULL
    return Quality.FULL if hint == Quality.FULL else Quality.PREVIEW   # a 60 s+ clip or excerpt is a preview


def finalize(fetched: FetchedAudio, discogs_duration: int | None) -> FetchedAudio:
    """Measure the real file; the adapter's quality is only a hint."""
    real = probe_duration(fetched.path)
    if real is None:
        real = fetched.duration
    fetched.duration = real
    fetched.quality = classify(real, discogs_duration, fetched.quality)
    return fetched


def ytdlp_download(url: str, dest: Path, *, max_seconds: int = config.MAX_VIDEO_SECONDS, throttle: Callable[[], None] | None = None) -> Path:
    """Best audio stream as the site delivers it (no re-encoding). `dest` has no extension."""
    import yt_dlp

    dest.parent.mkdir(parents=True, exist_ok=True)
    opts = {"format": "bestaudio/best", "outtmpl": f"{dest}.%(ext)s", "noplaylist": True, "quiet": True, "noprogress": True,
            "no_warnings": True, "match_filter": yt_dlp.utils.match_filter_func(f"duration<={max_seconds}")}
    if throttle:
        throttle()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info and "entries" in info:
                info = next((e for e in info["entries"] if e), None)
            if not info:
                raise AdapterError("nothing downloaded (unavailable, or longer than the limit)")
            path = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.YoutubeDLError as e:
        raise AdapterError(str(e).splitlines()[0][:200]) from e
    if not path.exists():
        raise AdapterError("download failed or was filtered out")
    return path


def http_download(url: str, dest: Path, *, site: str, adapter: str, http=None) -> Path:
    """Plain download of a direct media URL (previews, clips) through the shared HTTP client."""
    from . import http as http_mod

    client = http or http_mod.shared()
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = client.get(url, site=site, adapter=adapter, stream=True, timeout=60)
    ext = Path(url.split("?")[0]).suffix.lower()
    if ext not in {".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wav", ".mp4"}:
        ext = CONTENT_TYPES.get((r.headers.get("Content-Type") or "").split(";")[0].strip().lower(), ".mp3")
    path = dest.parent / (dest.name + ext)
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)
    if path.stat().st_size == 0:
        path.unlink()
        raise AdapterError(f"empty download from {url}")
    return path
