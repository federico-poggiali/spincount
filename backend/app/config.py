"""The app's settings, from the environment and the repo's .env (loaded once, by bpmkey.config)."""
import os
from pathlib import Path

from bpmkey.config import ROOT as REPO_ROOT
from bpmkey.config import path_setting

BACKEND_DIR = Path(__file__).resolve().parent.parent

DB_PATH = path_setting("DB_PATH", BACKEND_DIR / "data" / "vinyl.db")
AUDIO_DIR = path_setting("AUDIO_DIR", REPO_ROOT / "audio")
VAULT_DIR = path_setting("VAULT_DIR", REPO_ROOT / "vault")
FRONTEND_DIST = path_setting("FRONTEND_DIST", REPO_ROOT / "frontend" / "dist")
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
USER_AGENT = f"VinylSecondBrain/0.1 ( {os.environ.get('CONTACT_EMAIL', '')} )"
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
