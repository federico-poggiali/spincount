"""Settings. Reads .env through bpmkey.config (same file, same keys)."""
from __future__ import annotations

import os
from pathlib import Path

from bpmkey import config as _bpm  # loads .env into os.environ

ROOT: Path = _bpm.ROOT
CONTACT_EMAIL: str = _bpm.CONTACT_EMAIL
USER_AGENT: str = f"AudioResearch/0.1 ( {CONTACT_EMAIL} )"


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Next to Spin Count's database (bpmkey.config.DATA_DIR), so gigabytes of downloads stay out of the repo.
AUDIORESEARCH_DB: Path = _bpm.path_setting("AUDIORESEARCH_DB", _bpm.DATA_DIR / "audioresearch.db")
AUDIO_CACHE_DIR: Path = _bpm.path_setting("AUDIO_CACHE_DIR", _bpm.DATA_DIR / "audio_cache")
# level 0: <folder>/<release id>/. The same folder Spin Count reads (AUDIO_DIR), so there is one place for your files.
LOCAL_AUDIO_DIR: Path = _bpm.path_setting("AUDIORESEARCH_LOCAL_AUDIO", _bpm.path_setting("AUDIO_DIR", ROOT / "audio"))
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

