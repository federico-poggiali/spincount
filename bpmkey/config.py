"""Settings shared by the whole repo: reads .env once (bpmkey, audioresearch and the app all import this)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def path_setting(name: str, default: Path) -> Path:
    """A path from the environment; a relative one resolves against the repo root."""
    value = os.environ.get(name)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


_load_dotenv()

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
GETSONGBPM_KEY = os.environ.get("GETSONGBPM_KEY", "")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
USER_AGENT = f"BpmKeyTool/0.1 ( {CONTACT_EMAIL} )"
# The app's database folder (DB_PATH, e.g. Application Support) also holds the engines' caches, so nothing
# they download or look up is written into the repo. Without DB_PATH that folder is the repo.
DATA_DIR = path_setting("DB_PATH", ROOT).parent if os.environ.get("DB_PATH") else ROOT
CACHE_PATH = path_setting("BPMKEY_CACHE", DATA_DIR / "cache.sqlite")
