"""Is a search still getting anywhere? Every event, finished request and downloaded chunk is a beat.

A search that has had no beat for a while is stalled and gets halted: `Watch.halted` is set, and the next beat
on any of the run's threads raises `Halted`, so they stop instead of working on for nobody."""
from __future__ import annotations

import threading
import time


class Halted(BaseException):
    """Raised inside a halted run's threads. Not an Exception: the adapter guards must not swallow it."""


class Watch:
    def __init__(self) -> None:
        self.last = time.monotonic()
        self.halted = False

    def beat(self) -> None:
        if self.halted:
            raise Halted()
        self.last = time.monotonic()

    def quiet_for(self) -> float:
        return time.monotonic() - self.last


_local = threading.local()


def bind(watch: Watch | None) -> None:
    """The watch this thread's beats count for (a run binds each of its threads)."""
    _local.watch = watch


def beat() -> None:
    watch = getattr(_local, "watch", None)
    if watch is not None:
        watch.beat()
