"""Settings. Reads .env through bpmkey.config (same file, same keys)."""
from __future__ import annotations

import os
from pathlib import Path

from bpmkey import config as _bpm  # loads .env into os.environ

ROOT: Path = _bpm.ROOT
CONTACT_EMAIL: str = _bpm.CONTACT_EMAIL
USER_AGENT: str = f"AudioResearch/0.1 ( {CONTACT_EMAIL} )"


def _path(name: str, default: str) -> Path:
    p = Path(os.environ.get(name, default)).expanduser()
    return p if p.is_absolute() else ROOT / p


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Spin Count's database folder (DB_PATH in .env, e.g. Application Support) also holds this tool's cache and audio,
# so gigabytes of downloads stay out of the repo (and out of OneDrive). Without DB_PATH it is the repo, as before.
_DATA_DIR = Path(os.environ["DB_PATH"]).expanduser().parent if os.environ.get("DB_PATH") else ROOT
AUDIORESEARCH_DB: Path = _path("AUDIORESEARCH_DB", str(_DATA_DIR / "audioresearch.db"))
AUDIO_CACHE_DIR: Path = _path("AUDIO_CACHE_DIR", str(_DATA_DIR / "audio_cache"))
# level 0: <folder>/<release id>/. The same folder Spin Count reads (AUDIO_DIR), so there is one place for your files.
LOCAL_AUDIO_DIR: Path = _path("AUDIORESEARCH_LOCAL_AUDIO", os.environ.get("AUDIO_DIR") or "audio")
REVIEW_THRESHOLD: float = _float("REVIEW_THRESHOLD", 0.6)
HEALTH_MAX_FAILURES: int = int(_float("AUDIORESEARCH_MAX_FAILURES", 5))
MAX_VIDEO_SECONDS: int = 20 * 60

DEFAULT_DELAY = 1.0
STORE_DELAY = 2.0
_STORES = ("deejay_de", "decks_de", "hardwax", "redeye", "runas", "orbitwax", "soundmetaphors", "one_eye_witness", "smallblackdots", "clone", "kalahari_oyster_cult")


def site_delay(site: str) -> float:
    """Minimum seconds between two requests to one site (env: AUDIORESEARCH_DELAY_<SITE>)."""
    default = STORE_DELAY if site in _STORES else DEFAULT_DELAY
    return _float(f"AUDIORESEARCH_DELAY_{site.upper()}", default)


def enabled_adapters() -> set[str]:
    """Adapters that are off by default but switched on (env: AUDIORESEARCH_ENABLE=decks_de,clone)."""
    return {s.strip() for s in os.environ.get("AUDIORESEARCH_ENABLE", "").split(",") if s.strip()}


def disabled_adapters() -> set[str]:
    """Adapters switched off in config (env: AUDIORESEARCH_DISABLED=bandcamp,clone)."""
    return {s.strip() for s in os.environ.get("AUDIORESEARCH_DISABLED", "").split(",") if s.strip()}

