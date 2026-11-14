"""The one HTTP client for all adapters: per-site minimum delay, retries with backoff on 429/5xx,
one User-Agent with a contact email, request and failure counts per adapter."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Callable

import requests

from . import config, progress
from .adapters.base import AdapterError


class HttpError(AdapterError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpClient:
    def __init__(self, session: Any = None, *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, delay_for: Callable[[str], float] = config.site_delay,
                 max_retries: int = 3, backoff: float = 1.0):
        self.session = session or requests.Session()
        if hasattr(self.session, "headers"):
            self.session.headers.setdefault("User-Agent", config.USER_AGENT)
        self._sleep, self._clock, self._delay_for = sleep, clock, delay_for
        self.max_retries, self.backoff = max_retries, backoff
        self._last: dict[str, float] = {}
        self._site_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._guard = threading.Lock()
        self.calls = 0   # every request that reached the network layer
        self.stats: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "failures": 0})

    def _wait(self, site: str) -> None:
        """Hold the site's lock until at least its minimum delay has passed since the last request."""
        gap = self._delay_for(site)
        last = self._last.get(site)
        if last is not None and (wait := gap - (self._clock() - last)) > 0:
            self._sleep(wait)
        self._last[site] = self._clock()

    def throttle(self, site: str) -> None:
        """Wait for the site's minimum delay before something that bypasses this client (yt-dlp)."""
        with self._site_locks[site]:
            self._wait(site)

    def request(self, method: str, url: str, *, site: str, adapter: str | None = None, **kw: Any):
        adapter = adapter or site
        kw.setdefault("timeout", 20)
        last_err = "unknown error"
        for attempt in range(self.max_retries + 1):
            with self._site_locks[site]:
                self._wait(site)
                with self._guard:
                    self.calls += 1
                    self.stats[adapter]["requests"] += 1
                try:
                    r = self.session.request(method, url, **kw)
                except requests.RequestException as e:
                    r, last_err = None, f"{type(e).__name__}: {e}"
            if r is not None:
                progress.beat()   # a site answered: the search is alive
                if r.status_code < 400:
                    return r
                last_err = f"HTTP {r.status_code} for {url}"
                if r.status_code not in RETRY_STATUS:
                    self._fail(adapter)
                    raise HttpError(last_err, r.status_code)
                retry_after = r.headers.get("Retry-After", "") if getattr(r, "headers", None) else ""
                extra = float(retry_after) if retry_after.isdigit() else 0.0
            else:
                extra = 0.0
            if attempt < self.max_retries:
                self._sleep(min(30.0, max(extra, self.backoff * 2 ** attempt)))
        self._fail(adapter)
        raise HttpError(f"{last_err} (gave up after {self.max_retries + 1} tries)", getattr(r, "status_code", None))

    def _fail(self, adapter: str) -> None:
        with self._guard:
            self.stats[adapter]["failures"] += 1

    def get(self, url: str, *, site: str, adapter: str | None = None, **kw: Any):
        return self.request("GET", url, site=site, adapter=adapter, **kw)

    def get_text(self, url: str, **kw: Any) -> str:
        return self.get(url, **kw).text

    def get_json(self, url: str, **kw: Any) -> Any:
        try:
            return self.get(url, **kw).json()
        except ValueError as e:
            raise HttpError(f"not JSON: {url}") from e


_shared: HttpClient | None = None


def shared() -> HttpClient:
    global _shared
    if _shared is None:
        _shared = HttpClient()
    return _shared
