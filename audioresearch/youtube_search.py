"""A YouTube video for one track, by search: links only, nothing downloaded.

For Spin Count's "Add to YT playlist": every track gets a YouTube video when YouTube has it, whatever its audio
came from. yt-dlp searches YouTube (no API key, no quota); the shared matcher checks each hit on title, uploader
and duration, so a wrong song is left out rather than guessed.
"""
from __future__ import annotations

from typing import Callable

from . import http
from .adapters.common import search_artist, search_title
from .matcher import match_track, track_threshold
from .models import Candidate, ReleaseIdentity, TrackRef

RESULTS = 5
WATCH = "https://www.youtube.com/watch?v={}"

# query -> yt-dlp's flat search rows ({"id", "title", "channel" or "uploader", "duration"})
SearchFn = Callable[[str], list[dict]]


def search(query: str, limit: int = RESULTS) -> list[dict]:
    """yt-dlp's YouTube search, metadata only."""
    import yt_dlp

    http.shared().throttle("youtube")
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False) or {}
    return [e for e in info.get("entries") or [] if e and e.get("id")]


def _channel(row: dict) -> str:
    """The uploader, as the matcher's artist: YouTube's own artist channels are named "<artist> - Topic"."""
    return (row.get("channel") or row.get("uploader") or "").removesuffix(" - Topic")


def find_track(identity: ReleaseIdentity, track: TrackRef, search_fn: SearchFn = search) -> dict | None:
    """-> {"video_id", "title", "channel", "duration", "confidence"} of the best hit over the matcher's bar, or None."""
    bar = track_threshold(identity)
    best = None
    for row in search_fn(f"{search_artist(track.artist)} {search_title(track.title)}".strip()):
        duration = int(row["duration"]) if row.get("duration") else None
        cand = Candidate("youtube_search", 1, "track", WATCH.format(row["id"]), row.get("title") or "", _channel(row), duration)
        score = match_track(identity, track, cand)
        if score >= bar and (best is None or score > best["confidence"]):
            best = {"video_id": row["id"], "title": cand.title, "channel": row.get("channel") or row.get("uploader"),
                    "duration": duration, "confidence": round(score, 3)}
    return best
