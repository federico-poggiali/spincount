"""The app's settings, from the environment and the repo's .env (loaded once, by bpmkey.config)."""
import os
from pathlib import Path

from bpmkey.config import ROOT as REPO_ROOT
from bpmkey.config import path_setting

BACKEND_DIR = Path(__file__).resolve().parent.parent

DB_PATH = path_setting("DB_PATH", BACKEND_DIR / "data" / "vinyl.db")
AUDIO_DIR = path_setting("AUDIO_DIR", REPO_ROOT / "audio")  # your own files only: audio/<discogs release id>/
# What the audio search downloads to check a match: next to the database, never among your files.
AUDIO_STALL_SECONDS = 30  # a search that makes no progress at all for this long is stopped
AUDIO_CACHE_DIR = path_setting("AUDIO_CACHE_DIR", DB_PATH.parent / "audio_cache")
VAULT_DIR = path_setting("VAULT_DIR", REPO_ROOT / "vault")
FRONTEND_DIST = path_setting("FRONTEND_DIST", REPO_ROOT / "frontend" / "dist")
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
USER_AGENT = f"VinylSecondBrain/0.1 ( {os.environ.get('CONTACT_EMAIL', '')} )"
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
# "Add to YT playlist": your Google OAuth client of type "Desktop app", from .env or pasted in Settings (kept
# in YOUTUBE_CLIENT; .env wins). The sign-in token and today's quota count are kept next to the database too.
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_CLIENT = path_setting("YOUTUBE_CLIENT", DB_PATH.parent / "youtube_client.json")
YOUTUBE_TOKEN = path_setting("YOUTUBE_TOKEN", DB_PATH.parent / "youtube_token.json")
YOUTUBE_USAGE = path_setting("YOUTUBE_USAGE", DB_PATH.parent / "youtube_usage.json")
