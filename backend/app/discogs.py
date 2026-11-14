"""Discogs API client and release mapping. URL/tracklist parsing is shared with bpmkey."""
import time
from collections.abc import Callable

import httpx
from bpmkey.discogs import _join_artists, parse_tracklist, parse_url

from app import config

API = "https://api.discogs.com"
DEFAULT_FOLDER = 1  # "Uncategorized"


class DiscogsError(Exception):
    pass


class DiscogsNotFound(DiscogsError):
    pass


class DiscogsBadUrl(DiscogsError):
    pass


class DiscogsClient:
    def __init__(self, token: str, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep, max_retries: int = 5):
        if not token:
            raise DiscogsError("DISCOGS_TOKEN is not set (see .env)")
        self._http = client or httpx.Client(timeout=20)
        self._headers = {"User-Agent": config.USER_AGENT, "Authorization": f"Discogs token={token}"}
        self._sleep = sleep
        self._max_retries = max_retries
        self._username: str | None = None

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            resp = self._http.request(method, f"{API}{path}", headers=self._headers, **kwargs)
            if resp.status_code == 429 and attempt < self._max_retries:
                retry_after = resp.headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after else min(2 ** attempt * 2, 60))
                continue
            if resp.status_code == 404:
                raise DiscogsNotFound(f"not found on Discogs: {path}")
            if resp.status_code == 429:
                raise DiscogsError("Discogs rate limit: gave up after retries")
            if resp.status_code >= 400:
                raise DiscogsError(f"Discogs returned {resp.status_code} for {path}")
            return resp
        raise DiscogsError("unreachable")

    def release(self, release_id: int) -> dict:
        return self._request("GET", f"/releases/{release_id}").json()

    def master_main_release(self, master_id: int) -> int:
        return self._request("GET", f"/masters/{master_id}").json()["main_release"]

    @property
    def username(self) -> str:
        if self._username is None:
            self._username = self._request("GET", "/oauth/identity").json()["username"]
        return self._username

    def collection_instances(self, release_id: int) -> list[int]:
        """Instance ids of this release in the user's collection (any folder)."""
        return [i for i, _ in self._instances(release_id)]

    def _instances(self, release_id: int) -> list[tuple[int, int]]:
        data = self._request("GET", f"/users/{self.username}/collection/releases/{release_id}").json()
        return [(r["instance_id"], r.get("folder_id", DEFAULT_FOLDER)) for r in data.get("releases", [])]

    def remove_from_collection(self, release_id: int) -> int:
        """Remove every copy of a release from the collection. Returns how many were removed."""
        found = self._instances(release_id)
        for instance_id, folder_id in found:
            self._request("DELETE", f"/users/{self.username}/collection/folders/{folder_id}"
                                    f"/releases/{release_id}/instances/{instance_id}")
        return len(found)

    def add_to_collection(self, release_id: int, folder_id: int = DEFAULT_FOLDER) -> tuple[int, bool]:
        """Add a release unless it is already collected. Returns (instance_id, added)."""
        existing = self.collection_instances(release_id)
        if existing:
            return existing[0], False
        path = f"/users/{self.username}/collection/folders/{folder_id}/releases/{release_id}"
        return self._request("POST", path).json()["instance_id"], True

    def collection_releases(self) -> list[dict]:
        """Every release in the user's collection (all folders), once per release, as a light record
        with how many copies of it the collection holds."""
        found: dict[int, dict] = {}
        for item in self._pages(f"/users/{self.username}/collection/folders/0/releases", "releases"):
            if item["id"] in found:
                found[item["id"]]["copies"] += 1
                continue
            info = item.get("basic_information") or {}
            found[item["id"]] = {
                "discogs_release_id": item["id"],
                "artist": _join_artists(info.get("artists", [])) or "Unknown artist",
                "title": info.get("title") or "",
                "year": info.get("year") or None,
                "cover_url": info.get("thumb") or None,
                "copies": 1,
            }
        return list(found.values())

    def wantlist_ids(self) -> set[int]:
        return {w["id"] for w in self._pages(f"/users/{self.username}/wants", "wants")}

    def add_to_wantlist(self, release_id: int) -> None:
        """Put a release on the user's wantlist (Discogs keeps one entry per release)."""
        self._request("PUT", f"/users/{self.username}/wants/{release_id}")

    def remove_from_wantlist(self, release_id: int) -> None:
        self._request("DELETE", f"/users/{self.username}/wants/{release_id}")

    def _pages(self, path: str, key: str):
        page = 1
        while True:
            data = self._request("GET", path, params={"per_page": 100, "page": page}).json()
            yield from data.get(key, [])
            if page >= (data.get("pagination") or {}).get("pages", 1):
                return
            page += 1

    def resolve(self, url: str) -> tuple[int, int | None]:
        """Return (release_id, master_id); master_id is set when the URL was a master."""
        try:
            kind, id_ = parse_url(url)
        except ValueError as exc:
            raise DiscogsBadUrl(str(exc)) from exc
        if kind == "master":
            return self.master_main_release(id_), id_
        return id_, None


def _format_text(formats: list[dict]) -> str | None:
    if not formats:
        return None
    first = formats[0]
    parts = [first.get("name", "")]
    if first.get("qty") not in (None, "1"):
        parts[0] = f"{first['qty']}x{parts[0]}"
    parts += first.get("descriptions", [])
    return ", ".join(p for p in parts if p) or None


def _year(data: dict) -> int | None:
    """Discogs' year, else the year of its 'released' date ('2018-05-01', '2018-05', '2018')."""
    if data.get("year"):
        return data["year"]
    released = str(data.get("released") or "")[:4]
    return int(released) if released.isdigit() and int(released) > 0 else None


def release_to_record(data: dict) -> dict:
    images = data.get("images") or []
    labels = data.get("labels") or []
    return {
        "discogs_release_id": data["id"],
        "artist": _join_artists(data.get("artists", [])) or "Unknown artist",
        "title": data["title"],
        "label": labels[0]["name"] if labels else None,
        "catno": (labels[0].get("catno") or None) if labels else None,
        "year": _year(data),
        "format": _format_text(data.get("formats", [])),
        # Styles only. Broad genres are not imported, except as a stand-in when a release has no style.
        "styles": data.get("styles") or data.get("genres") or [],
        "cover_url": (images[0].get("uri") or images[0].get("uri150")) if images else None,
    }


def release_to_tracks(data: dict) -> list[dict]:
    return [
        {"position": t.position, "artist": t.artist, "title": t.title, "duration_sec": t.duration}
        for t in parse_tracklist(data, data["id"])
    ]
