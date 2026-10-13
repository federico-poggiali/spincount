"""Run events: what the pipeline reports while it works (start, finish, counts, durations)."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

RUN_STARTED = "run_started"
RELEASE_IDENTIFIED = "release_identified"
LEVEL_STARTED = "level_started"
LEVEL_FINISHED = "level_finished"
STAGE_STARTED = "stage_started"
STAGE_FINISHED = "stage_finished"
CANDIDATE_REJECTED = "candidate_rejected"
TRACK_RESOLVED = "track_resolved"
ADAPTER_OFF = "adapter_off"
RUN_FINISHED = "run_finished"

SEARCH, MATCH, FETCH, VERIFY, DECIDE = "search", "match", "fetch", "verify", "decide"
STAGES = (SEARCH, MATCH, FETCH, VERIFY, DECIDE)  # stages 2 to 6


@dataclass
class RunEvent:
    run_id: str
    seq: int
    time: int                      # ms since the run started
    type: str
    level: Optional[int] = None
    adapter: Optional[str] = None
    stage: Optional[str] = None
    position: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RunEvent":
        return cls(**d)


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


class Emitter:
    """Thread-safe: adapters of one level run in parallel and all report here."""

    def __init__(self, run_id: str | None = None, callback: Callable[[RunEvent], None] | None = None):
        self.run_id = run_id or new_run_id()
        self.callback = callback
        self._t0 = time.monotonic()
        self._seq = 0
        self._lock = threading.Lock()

    def now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def emit(self, type: str, *, level: int | None = None, adapter: str | None = None, stage: str | None = None,
             position: str | None = None, **data: Any) -> None:
        if self.callback is None:
            return
        with self._lock:  # the callback runs under the lock so events arrive in seq order
            self._seq += 1
            self.callback(RunEvent(self.run_id, self._seq, self.now_ms(), type, level, adapter, stage, position, data))

    def timer(self) -> "Timer":
        return Timer()


class Timer:
    def __init__(self):
        self._t = time.monotonic()

    @property
    def ms(self) -> int:
        return int((time.monotonic() - self._t) * 1000)
