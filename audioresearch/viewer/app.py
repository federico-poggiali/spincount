"""Temporary process viewer: paste a Discogs link, watch the research run. Localhost only, no login."""
from __future__ import annotations

import asyncio
import json
import threading
import traceback
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .. import events as ev
from ..adapters import Registry, default_registry
from ..adapters.fake import demo_registry
from ..identify import identify
from ..pipeline import research
from ..store import Store

STATIC = Path(__file__).parent / "static"
TERMINAL = {ev.RUN_FINISHED, "run_failed"}


class StartRun(BaseModel):
    url: str
    refresh: bool = True   # watching a run is the point; a cached rerun would finish instantly


def create_app(store: Store, *, fake: bool = False, discogs=None, audio_dir: Path | None = None,
               registry_factory: Callable | None = None, poll: float = 0.1) -> FastAPI:
    app = FastAPI(title="Audio research viewer")
    factory = registry_factory or (demo_registry if fake else (lambda identity: default_registry()))
    running: set[str] = set()

    def worker(run_id: str, url: str, refresh: bool) -> None:
        try:
            identity = identify(url, discogs, store, refresh)
            research(url, range(6), refresh, registry=factory(identity), identity=identity, store=store,
                     audio_dir=audio_dir, run_id=run_id)
        except Exception as e:  # shown in the viewer, never crashes the server
            last = store.get_events(run_id)
            store.add_event(ev.RunEvent(run_id, (last[-1].seq if last else 0) + 1, last[-1].time if last else 0,
                                        "run_failed", data={"error": f"{type(e).__name__}: {e}",
                                                            "trace": traceback.format_exc()[-1500:]}))
        finally:
            running.discard(run_id)

    @app.post("/runs")
    def start(body: StartRun):
        run_id = ev.new_run_id()
        store.start_run(run_id, body.url)
        running.add(run_id)
        threading.Thread(target=worker, args=(run_id, body.url, body.refresh), daemon=True).start()
        return {"run_id": run_id}

    @app.get("/runs")
    def runs():
        return store.list_runs()

    @app.get("/runs/{run_id}")
    def run_result(run_id: str):
        result = store.get_run_result(run_id)
        if result is None:
            raise HTTPException(404, "no result (yet) for this run")
        return result.to_dict()

    @app.get("/runs/{run_id}/events")
    async def stream(run_id: str, last: int = 0):
        if store.get_run(run_id) is None:
            raise HTTPException(404, "unknown run")

        async def gen():
            seq = last
            while True:
                batch = store.get_events(run_id, seq)
                for e in batch:
                    seq = e.seq
                    yield f"id: {e.seq}\nevent: run\ndata: {json.dumps(e.to_dict())}\n\n"
                    if e.type in TERMINAL:
                        return
                if not batch and run_id not in running and not store.get_events(run_id, seq):
                    return  # a run that is neither live nor stored to the end (e.g. server restarted)
                await asyncio.sleep(poll)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def serve(fake: bool, port: int = 8200) -> int:
    import uvicorn

    app = create_app(Store(), fake=fake)
    print(f"Viewer on http://127.0.0.1:{port}  ({'fake adapters' if fake else 'real adapters'})")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0
