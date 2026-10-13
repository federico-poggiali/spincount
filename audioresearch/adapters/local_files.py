"""Level 0: your own files in audio/<discogs release id>/, matched by position, then title.

The matching logic is a port of backend/app/analysis/matching.py (copied, not imported): it never
guesses silently, and files that match no track are reported.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .. import config
from ..models import Candidate, FetchedAudio, Quality, ReleaseIdentity, TrackRef
from .base import Adapter

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg"}
TITLE_THRESHOLD = 0.8
TITLE_MARGIN = 0.05
_POSITION = re.compile(r"^\s*([A-Za-z]{1,2}\d{1,2}|\d{1,2}-\d{1,2}|\d{1,3})(?=[\s._\-)]|$)")


def normalize_position(position: str) -> str:
    return re.sub(r"\d+", lambda m: str(int(m.group())), position.strip().upper())


def file_position(stem: str) -> str | None:
    m = _POSITION.match(stem)
    return normalize_position(m.group(1)) if m else None


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _title_part(stem: str) -> str:
    m = _POSITION.match(stem)
    return _clean(stem[m.end():] if m else stem)


def find_audio_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in AUDIO_EXTENSIONS)


def match_files(files: list[Path], tracks: list[TrackRef]) -> dict:
    """-> {"matched": [{position, file, method, score}], "unmatched_files": [{file, reason}], "unmatched_tracks": [position]}"""
    matched: list[dict] = []
    unmatched_files: list[dict] = []
    free = {t.position: t for t in tracks}
    files_left: list[Path] = []

    # 1. By position in the filename ("A1 - Title.wav"); ambiguity on either side is skipped.
    by_position: dict[str, list[TrackRef]] = {}
    for t in tracks:
        if t.position:
            by_position.setdefault(normalize_position(t.position), []).append(t)
    claimed: dict[str, list[Path]] = {}
    for f in files:
        pos = file_position(f.stem)
        if pos is not None:
            claimed.setdefault(pos, []).append(f)
    for f in files:
        pos = file_position(f.stem)
        candidates = by_position.get(pos, []) if pos else []
        if pos and len(claimed[pos]) > 1:
            unmatched_files.append({"file": f.name, "reason": f"several files claim position {pos}"})
        elif len(candidates) == 1 and candidates[0].position in free:
            t = free.pop(candidates[0].position)
            matched.append({"position": t.position, "file": f.name, "method": "position", "score": 1.0})
        else:
            files_left.append(f)

    # 2. Fuzzy title for what is left, only when the best candidate is clearly ahead.
    proposals = []
    for f in files_left:
        title = _title_part(f.stem)
        scored = sorted(((SequenceMatcher(None, title, _clean(t.title)).ratio(), t.position) for t in free.values()), reverse=True)
        if not scored or scored[0][0] < TITLE_THRESHOLD:
            unmatched_files.append({"file": f.name, "reason": "no track matches this file"})
        elif len(scored) > 1 and scored[0][0] - scored[1][0] < TITLE_MARGIN:
            unmatched_files.append({"file": f.name, "reason": "title matches several tracks"})
        else:
            proposals.append((scored[0][0], f, scored[0][1]))
    for score, f, position in sorted(proposals, key=lambda p: -p[0]):
        if position in free:
            free.pop(position)
            matched.append({"position": position, "file": f.name, "method": "title", "score": round(score, 2)})
        else:
            unmatched_files.append({"file": f.name, "reason": "its best track is taken by another file"})
    return {"matched": matched, "unmatched_files": sorted(unmatched_files, key=lambda u: u["file"]),
            "unmatched_tracks": list(free)}


class LocalFiles(Adapter):
    name = "local_files"
    level = 0

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else config.LOCAL_AUDIO_DIR
        self._diag: list[dict] = []

    def folder(self, release_id: int) -> Path:
        return self.root / str(release_id)

    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]:
        folder = self.folder(release.discogs_release_id)
        res = match_files(find_audio_files(folder), release.tracks)   # always against the whole release
        self._diag = [{"url": str(folder / u["file"]), "reason": f"your file matches no track: {u['reason']}"}
                      for u in res["unmatched_files"]]
        wanted = {t.position for t in tracks}
        out = []
        for m in res["matched"]:
            if m["position"] not in wanted:
                continue
            t = release.track(m["position"])
            out.append(Candidate(self.name, 0, "track", str(folder / m["file"]), t.title, t.artist, t.duration,
                                 quality_hint=Quality.FULL, position=m["position"],
                                 extra={"trusted": True, "how": f"matched by {m['method']}"}))
        return out

    def take_diagnostics(self) -> list[dict]:
        d, self._diag = self._diag, []
        return d

    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio:
        return FetchedAudio(Path(candidate.url), self.name, candidate.url, Quality.FULL)

    def changed_since(self, release_id: int, saved_at: str) -> bool:
        folder = self.folder(release_id)
        if not folder.exists():
            return False
        since = datetime.strptime(saved_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        return max([folder.stat().st_mtime] + [p.stat().st_mtime for p in folder.iterdir()]) > since
