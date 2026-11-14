"""Your YouTube account: Google sign-in and the few YouTube Data API calls "Add to YT playlist" makes.

Needs your own OAuth client of type "Desktop app" from a Google Cloud project with the YouTube Data API v3
on: pasted in Settings (kept in a private file next to the database) or YOUTUBE_CLIENT_ID and
YOUTUBE_CLIENT_SECRET in .env, which win. Your own project means your own 10,000 quota units a day. Sign-in is
Google's loopback flow with PKCE: Google sends the browser back to this app's /api/youtube/callback. The
refresh token is kept in a file next to the database (YOUTUBE_TOKEN), readable only by you.

Google has no API for the quota left, so the units this app spends are counted here (listing costs 1 unit,
adding a video 50), per Pacific day, which is when Google resets it.
"""
import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
SCOPE = "https://www.googleapis.com/auth/youtube"
DAILY_QUOTA = 10_000  # a Google Cloud project's default YouTube Data API quota
ADD_COST, LIST_COST = 50, 1
CLIENT_SUFFIX = ".apps.googleusercontent.com"

try:
    PACIFIC: dt.tzinfo = ZoneInfo("America/Los_Angeles")
except ZoneInfoNotFoundError:  # no time zone data: Pacific standard time is close enough
    PACIFIC = dt.timezone(dt.timedelta(hours=-8))


class YouTubeError(Exception):
    pass


class NotConfigured(YouTubeError):
    pass


class NotConnected(YouTubeError):
    pass


class QuotaExceeded(YouTubeError):
    pass


class BadCredentials(YouTubeError):
    """The client ID or secret is malformed, or Google does not know them."""


class CredentialsFromEnv(YouTubeError):
    """The credentials come from .env, so Settings cannot change them."""


def _reason(response: httpx.Response) -> str:
    try:
        error = response.json().get("error")
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(error, dict):
        reasons = [e.get("reason") for e in error.get("errors") or [] if e.get("reason")]
        return reasons[0] if reasons else error.get("message", "")
    return str(error or f"HTTP {response.status_code}")


def _write_private(path: Path, data: dict) -> None:
    """Write JSON readable only by you."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)


def _read(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class Account:
    def __init__(self, client_id: str, client_secret: str, token_path: Path,
                 http: httpx.Client | None = None, client_path: Path | None = None,
                 usage_path: Path | None = None, now=time.time):
        self._env = (client_id, client_secret)
        self.token_path, self.client_path = token_path, client_path
        self.usage_path = usage_path or token_path.with_name("youtube_usage.json")
        self.http = http or httpx.Client(timeout=20)
        self._now = now
        self._pending: dict[str, tuple[str, str, str]] = {}  # state -> (PKCE verifier, redirect, return to)
        self._access: tuple[str, float] | None = None         # (token, expires at)
        self._lock = threading.Lock()
        self._usage_lock = threading.Lock()

    # ---- your Google app (client ID and secret) ----------------------------------------------
    @property
    def source(self) -> Literal["env", "settings"] | None:
        if all(self._env):
            return "env"
        saved = _read(self.client_path)
        return "settings" if saved.get("client_id") and saved.get("client_secret") else None

    def _credentials(self) -> tuple[str, str]:
        if all(self._env):
            return self._env
        saved = _read(self.client_path)
        return saved.get("client_id", ""), saved.get("client_secret", "")

    @property
    def client_id(self) -> str:
        return self._credentials()[0]

    @property
    def client_secret(self) -> str:
        return self._credentials()[1]

    @property
    def configured(self) -> bool:
        return self.source is not None

    def check(self, client_id: str, client_secret: str) -> bool:
        """Ask Google whether it knows this client, with a sign-in code that cannot work: a known client gets
        "invalid_grant", an unknown one or a wrong secret "invalid_client". Uses no quota. False: Google could
        not be reached, so nothing was checked."""
        try:
            r = self.http.post(TOKEN_URL, data={
                "client_id": client_id, "client_secret": client_secret, "code": "spincount-check",
                "grant_type": "authorization_code", "redirect_uri": "http://127.0.0.1"})
        except httpx.HTTPError:
            return False
        if _reason(r) == "invalid_client" or r.status_code == 401:
            raise BadCredentials("Google does not know this client ID and secret: copy both again from the"
                                 " Google Cloud page of your OAuth client")
        return True

    def save_credentials(self, client_id: str, client_secret: str) -> bool:
        """Keep your Google app's client ID and secret, checked with Google first (returns whether it could
        be). A different app signs you out, since a sign-in belongs to the app it was made with."""
        if self.source == "env":
            raise CredentialsFromEnv("The client ID and secret come from .env: change or remove them there")
        client_id, client_secret = client_id.strip(), client_secret.strip()
        if not client_id.endswith(CLIENT_SUFFIX) or len(client_id) <= len(CLIENT_SUFFIX):
            raise BadCredentials(f"A client ID ends in {CLIENT_SUFFIX}: copy it from your OAuth client's"
                                 " page")
        if not client_secret:
            raise BadCredentials("The client secret is missing")
        checked = self.check(client_id, client_secret)
        if client_id != self.client_id:
            self.disconnect()
        assert self.client_path is not None
        _write_private(self.client_path, {"client_id": client_id, "client_secret": client_secret})
        return checked

    def remove_credentials(self) -> None:
        """Forget the client ID and secret saved in Settings, and sign out."""
        if self.source == "env":
            raise CredentialsFromEnv("The client ID and secret come from .env: remove them there")
        self.disconnect()
        if self.client_path is not None:
            self.client_path.unlink(missing_ok=True)

    # ---- quota -------------------------------------------------------------------------------
    def _day(self) -> dt.date:
        return dt.datetime.fromtimestamp(self._now(), PACIFIC).date()

    def usage(self) -> dict:
        """Units spent today (Pacific day), the daily quota, and when it resets."""
        day = self._day()
        saved = _read(self.usage_path)
        used = int(saved.get("used", 0)) if saved.get("day") == day.isoformat() else 0
        midnight = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), PACIFIC)
        return {"used": min(used, DAILY_QUOTA), "limit": DAILY_QUOTA,
                "resets_at": midnight.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")}

    def _spend(self, units: int, *, all_of_it: bool = False) -> None:
        with self._usage_lock:
            used = DAILY_QUOTA if all_of_it else self.usage()["used"] + units
            _write_private(self.usage_path, {"day": self._day().isoformat(), "used": used})

    # ---- sign-in -----------------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.token_path.is_file()

    def start(self, redirect_uri: str, return_to: str) -> str:
        """The Google sign-in page to send the browser to."""
        if not self.configured:
            raise NotConfigured("YouTube is not set up: paste your Google app's client ID and secret in"
                                " Settings (or set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env)")
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self._pending[state] = (verifier, redirect_uri, return_to)
        return AUTH_URL + "?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": SCOPE,
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
            "access_type": "offline", "prompt": "consent"})

    def return_to(self, state: str) -> str | None:
        pending = self._pending.get(state)
        return pending[2] if pending else None

    def finish(self, state: str, code: str) -> None:
        """Trade Google's code for tokens and keep the refresh token."""
        if state not in self._pending:
            raise YouTubeError("sign-in expired or was not started here; connect again")
        verifier, redirect_uri, _ = self._pending.pop(state)
        r = self.http.post(TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self.client_secret, "code": code,
            "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
        if r.status_code != 200 or "refresh_token" not in r.json():
            raise YouTubeError(f"Google refused the sign-in: {_reason(r)}")
        body = r.json()
        _write_private(self.token_path, {"refresh_token": body["refresh_token"]})
        self._access = (body["access_token"], time.time() + body.get("expires_in", 3600) - 60)

    def disconnect(self) -> None:
        """Forget the token here and ask Google to revoke it (best effort)."""
        if self.connected:
            try:
                self.http.post(REVOKE_URL, data={"token": self._refresh_token()})
            except (httpx.HTTPError, KeyError, ValueError):
                pass
            self.token_path.unlink(missing_ok=True)
        self._access = None

    # ---- API ---------------------------------------------------------------------------------
    def _refresh_token(self) -> str:
        return json.loads(self.token_path.read_text())["refresh_token"]

    def _token(self) -> str:
        with self._lock:
            if self._access and self._access[1] > time.time():
                return self._access[0]
            if not self.connected:
                raise NotConnected("YouTube is not connected: connect it in Settings")
            r = self.http.post(TOKEN_URL, data={
                "client_id": self.client_id, "client_secret": self.client_secret,
                "refresh_token": self._refresh_token(), "grant_type": "refresh_token"})
            if r.status_code == 400 and _reason(r) == "invalid_grant":  # revoked, or a "Testing" project
                self.token_path.unlink(missing_ok=True)
                raise NotConnected("YouTube access was revoked or expired: connect it again in Settings")
            if r.status_code != 200:
                raise YouTubeError(f"Google token refresh failed: {_reason(r)}")
            body = r.json()
            self._access = (body["access_token"], time.time() + body.get("expires_in", 3600) - 60)
            return self._access[0]

    def _call(self, method: str, path: str, params: dict, body: dict | None = None, *, cost: int) -> dict:
        def send() -> httpx.Response:
            r = self.http.request(method, f"{API}/{path}", params=params, json=body,
                                  headers={"Authorization": f"Bearer {self._token()}"})
            if r.status_code != 401:  # Google charges every request it handles, failed or not
                self._spend(cost)
            return r

        r = send()
        if r.status_code == 401:
            self._access = None
            r = send()
        if r.status_code == 403 and _reason(r) in ("quotaExceeded", "rateLimitExceeded"):
            if _reason(r) == "quotaExceeded":
                self._spend(0, all_of_it=True)
            raise QuotaExceeded("YouTube's daily quota is used up; try again tomorrow")
        if r.status_code >= 400:
            raise YouTubeError(f"YouTube said: {_reason(r)}")
        return r.json()

    def _pages(self, path: str, params: dict):
        token = None
        while True:
            more = {"pageToken": token} if token else {}
            page = self._call("GET", path, {**params, "maxResults": 50, **more}, cost=LIST_COST)
            yield from page.get("items", [])
            if not (token := page.get("nextPageToken")):
                return

    def playlists(self) -> list[dict]:
        """Your own playlists (1 quota unit per 50)."""
        return [{"id": p["id"], "title": p["snippet"]["title"], "count": p["contentDetails"]["itemCount"]}
                for p in self._pages("playlists", {"part": "snippet,contentDetails", "mine": "true"})]

    def video_ids(self, playlist_id: str) -> set[str]:
        """The videos already in a playlist (1 quota unit per 50)."""
        return {i["contentDetails"]["videoId"]
                for i in self._pages("playlistItems", {"part": "contentDetails", "playlistId": playlist_id})}

    def add(self, playlist_id: str, video_id: str) -> None:
        """Append one video (50 quota units)."""
        self._call("POST", "playlistItems", {"part": "snippet"}, {"snippet": {
            "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
            cost=ADD_COST)


_account: Account | None = None


def account() -> Account:
    global _account
    if _account is None:
        _account = Account(config.YOUTUBE_CLIENT_ID, config.YOUTUBE_CLIENT_SECRET, config.YOUTUBE_TOKEN,
                           client_path=config.YOUTUBE_CLIENT, usage_path=config.YOUTUBE_USAGE)
    return _account
