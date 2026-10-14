"""Temporary process viewer: paste a Discogs link, watch the research run. Localhost only, no login."""
from __future__ import annotations

import asyncio
import json
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .. import events as ev
from ..adapters import Registry, default_registry
from ..adapters.fake import demo_registry
from ..identify import identify
from ..pipeline import research
from ..previews import plan
from ..store import Store

STATIC = Path(__file__).parent / "static"
TERMINAL = {ev.RUN_FINISHED, "run_failed"}


class StartRun(BaseModel):
    url: str
    search_all: bool = False   # test mode: search every level for every track, never stop
    refresh: bool = True   # watching a run is the point; a cached rerun would finish instantly


def create_app(store: Store, *, fake: bool = False, discogs=None, audio_dir: Path | None = None,
               registry_factory: Callable | None = None, poll: float = 0.1) -> FastAPI:
    app = FastAPI(title="Audio research viewer")
    factory = registry_factory or (demo_registry if fake else (lambda identity: default_registry()))
    running: set[str] = set()

    def worker(run_id: str, url: str, refresh: bool, search_all: bool) -> None:
        try:
            identity = identify(url, discogs, store, refresh)
            research(url, range(6), refresh, registry=factory(identity), identity=identity, store=store,
                     audio_dir=audio_dir, run_id=run_id, search_all=search_all)
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
        threading.Thread(target=worker, args=(run_id, body.url, body.refresh, body.search_all), daemon=True).start()
        return {"run_id": run_id}

    @app.get("/runs")
    def runs():
        return store.list_runs()

    @app.get("/runs/{run_id}")
    def run_result(run_id: str):
        result = store.get_run_result(run_id)
        if result is None:
            raise HTTPException(404, "no result (yet) for this run")
        return {**result.to_dict(), "previews": plan(result)}

    @app.get("/runs/{run_id}/local/{position}")
    def local_file(run_id: str, position: str):
        """Your own file for a track, so the viewer can play it. Only files level 0 matched."""
        result = store.get_run_result(run_id)
        t = next((t for t in result.tracks if t.position == position), None) if result else None
        paths = ([t.audio_path] if t and t.source == "local_files" else []) + \
                [a["audio_path"] for a in (t.alternatives if t else []) if a["source"] == "local_files"]
        if not paths or not Path(paths[0]).is_file():
            raise HTTPException(404, "no file of yours for this track")
        return FileResponse(paths[0])

    @app.get("/embed/bandcamp")
    def bandcamp_embed(url: str):
        """The numeric id Bandcamp's embed player needs (it is only on the page)."""
        if not url.startswith("https://") or not urlparse(url).netloc.endswith("bandcamp.com"):
            raise HTTPException(400, "not a Bandcamp link")
        from .. import http as http_mod
        from ..parsers.bandcamp import parse_item_id
        try:
            item = parse_item_id(http_mod.shared().get_text(url, site="bandcamp", adapter="viewer"))
        except Exception as e:
            raise HTTPException(502, f"Bandcamp page unreadable: {e}")
        if not item:
            raise HTTPException(404, "no Bandcamp id on that page")
        return {"kind": item[0], "id": item[1]}

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
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})   # always the current page

    return app


def serve(fake: bool, port: int = 8200) -> int:
    import uvicorn

    app = create_app(Store(), fake=fake)
    print(f"Viewer on http://127.0.0.1:{port}  ({'fake adapters' if fake else 'real adapters'})")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0
