"""Adapter health: consecutive failures switch an adapter off for the rest of the run."""
from __future__ import annotations

import threading

from . import config


class AdapterHealth:
    def __init__(self, max_failures: int | None = None):
        self.max_failures = max_failures or config.HEALTH_MAX_FAILURES
        self._fails: dict[str, int] = {}
        self._off: dict[str, str] = {}
        self._lock = threading.Lock()

    def is_off(self, name: str) -> bool:
        return name in self._off

    def ok(self, name: str) -> None:
        with self._lock:
            self._fails[name] = 0

    def fail(self, name: str, error: object) -> bool:
        """Count a failure; True when this one switches the adapter off."""
        with self._lock:
            self._fails[name] = self._fails.get(name, 0) + 1
            if self._fails[name] >= self.max_failures and name not in self._off:
                self._off[name] = str(error)[:200]
                return True
            return False

    def disable(self, name: str, reason: object) -> bool:
        """Switch an adapter off now; True when it was on."""
        with self._lock:
            new = name not in self._off
            self._off.setdefault(name, str(reason)[:200])
            return new

    @property
    def off(self) -> dict[str, str]:
        return dict(self._off)
