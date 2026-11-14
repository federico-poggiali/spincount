"""Test-run activity log: what the background is doing right now, and how long each step took.

Only on in `make run-test` (SPINCOUNT_TEST_RUN=1); otherwise every call here does nothing. Kept in memory,
never in the database: the job runner reports each job's start and end, and the audio search reports its
timed steps (search, match, fetch, verify, decide, per level and per source) through audioresearch's events.
The runner runs one job at a time, so every event belongs to the job that is running.
"""
import logging
import os
import threading
import time
from collections import deque

log = logging.getLogger("app.testrun")

ENABLED = os.environ.get("SPINCOUNT_TEST_RUN") == "1"
MAX_JOBS = 25      # finished jobs kept
MAX_STEPS = 400    # steps kept per job


def _now_ms() -> int:
    return int(time.time() * 1000)


class Activity:
    def __init__(self, enabled: bool = ENABLED):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._done: deque[dict] = deque(maxlen=MAX_JOBS)

    # ---- the job runner ------------------------------------------------------------------------
    def job_started(self, job: dict) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._current = {"id": job["id"], "type": job["type"], "record_id": job.get("record_id"),
                             "params": job.get("params") or {}, "started": _now_ms(), "finished": None,
                             "status": "running", "error": None, "cached": False, "steps": [], "levels": [],
                             "tracks": None, "found": None}
        log.info("job started",
                 extra={"job": job["id"], "type": job["type"], "record_id": job.get("record_id")})

    def job_finished(self, job_id: int, status: str, error: str | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            job = self._current
            if job is None or job["id"] != job_id:
                return
            job.update(finished=_now_ms(), status=status, error=error)
            for step in job["steps"]:  # a step left open by a failure ends with its job
                if step["ms"] is None:
                    step["ms"], step["open"] = job["finished"] - step["started"], False
            self._done.appendleft(job)
            self._current = None
        log.info("job finished", extra={"job": job_id, "type": job["type"], "status": status,
                                        "seconds": round((job["finished"] - job["started"]) / 1000, 1),
                                        "error": error})

    # ---- audioresearch events ------------------------------------------------------------------
    def on_event(self, e) -> None:
        """audioresearch's `on_event`: a RunEvent with type, level, adapter, stage and data."""
        if not self.enabled:
            return
        now = _now_ms()
        with self._lock:
            job = self._current
            if job is None:
                return
            if e.type == "release_identified":
                job["tracks"] = e.data.get("track_count")
            elif e.type == "cache_hit":
                job["cached"] = True
            elif e.type == "level_started":
                job["levels"].append({"level": e.level, "started": now, "ms": None,
                                      "unfound": e.data.get("unfound"),
                                      "adapters": e.data.get("adapters", [])})
            elif e.type == "level_finished":
                for lv in reversed(job["levels"]):
                    if lv["level"] == e.level and lv["ms"] is None:
                        lv["ms"] = e.data.get("ms", now - lv["started"])
                        lv["resolved"] = len(e.data.get("resolved", []))
                        break
            elif e.type == "stage_started" and len(job["steps"]) < MAX_STEPS:
                job["steps"].append({"level": e.level, "adapter": e.adapter, "stage": e.stage, "started": now,
                                     "ms": None, "open": True, "tracks": e.data.get("tracks"), "detail": {}})
            elif e.type == "stage_finished":
                key = (e.level, e.adapter, e.stage)
                for step in reversed(job["steps"]):
                    if step["open"] and (step["level"], step["adapter"], step["stage"]) == key:
                        step["ms"], step["open"] = e.data.get("ms", now - step["started"]), False
                        step["detail"] = {k: v for k, v in e.data.items()
                                          if k != "ms" and not isinstance(v, (dict, list))}
                        break
                else:
                    return
                log.info("step", extra={"job": job["id"], "level": e.level, "source": e.adapter,
                                        "stage": e.stage, "seconds": round(e.data.get("ms", 0) / 1000, 2),
                                        **({"error": e.data["error"]} if e.data.get("error") else {})})
            elif e.type == "run_finished":
                job["found"] = e.data.get("found")

    # ---- the panel -----------------------------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            current = _copy(self._current) if self._current else None
            done = [_copy(j) for j in self._done]
        return {"now": _now_ms(), "current": current, "recent": done}


def _copy(job: dict) -> dict:
    return {**job, "steps": [dict(s, detail=dict(s["detail"])) for s in job["steps"]],
            "levels": [dict(lv) for lv in job["levels"]]}


activity = Activity()
