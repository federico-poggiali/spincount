"""Small helpers shared by adapters (no matching logic)."""
from __future__ import annotations

import re

_BRACKETS = re.compile(r"\(.*?\)|\[.*?\]")


def search_title(title: str) -> str:
    """Title for a site's search box: version brackets removed (the matcher checks versions later)."""
    return " ".join(_BRACKETS.sub(" ", title).split()) or title


def search_artist(artist: str) -> str:
    return "" if artist.lower().startswith("various") else artist
