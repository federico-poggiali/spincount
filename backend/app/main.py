import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from app import backfill, config, errors, library_sync, sync
from app.analysis import job as analysis_job
from app.audio import job as audio_job
from app.audio import stage as audio_stage
from app.db import connect, migrate
from app.discogs import DiscogsClient
from app.jobs.runner import JobRunner
from app.logging_config import configure as configure_logging
from app.routes import (
    admin,
    audio,
    crate,
    debug,
    jobs,
    labels,
    notes,
    records,
    search,
    styles,
    tags,
    tracks,
    youtube,
)
from app.routes import copies as copies_routes
from app.routes import library_sync as library_sync_routes
from app.sync_schedule import SyncScheduler
from app.vault import VaultSyncer
from app.youtube import links as youtube_links

log = logging.getLogger("app.request")


def _discogs() -> DiscogsClient:
    return DiscogsClient(config.DISCOGS_TOKEN)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    conn = connect()
    migrate(conn)
    conn.close()
    syncer = app.state.vault_syncer = VaultSyncer(config.VAULT_DIR)
    app.state.runner = JobRunner({
        analysis_job.JOB_TYPE: analysis_job.make_handler(research_fn=audio_stage.research_release),
        audio_job.JOB_TYPE: audio_job.make_handler(audio_stage.research_release),
        youtube_links.JOB_TYPE: youtube_links.make_handler(),
        sync.JOB_TYPE: sync.make_handler(_discogs),
        backfill.JOB_TYPE: backfill.make_handler(_discogs),
        **library_sync.make_handlers(_discogs),
    }, on_done=syncer.request)
    app.state.runner.start()
    schedule = SyncScheduler(app.state.runner)
    schedule.start()
    syncer.request()  # bring the vault up to date at startup
    yield
    schedule.stop()
    app.state.runner.stop()
    syncer.stop()


def _operation_id(route: APIRoute) -> str:
    return route.name  # readable names for the generated TypeScript client


app = FastAPI(title="Vinyl Second-Brain", lifespan=lifespan, generate_unique_id_function=_operation_id)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"],
                   allow_headers=["*"])
errors.install(app)
for module in (records, audio, tracks, notes, tags, styles, labels, search, crate, jobs, admin,
               library_sync_routes, copies_routes, youtube, debug):
    app.include_router(module.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info("request", extra={"method": request.method, "path": request.url.path,
                               "status": response.status_code,
                               "ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


READ_ONLY_POSTS = ("/sync-vault", "/render", "/from-discogs")  # label previews and lookups write nothing


@app.middleware("http")
async def refresh_vault_after_writes(request: Request, call_next):
    response = await call_next(request)
    syncer = getattr(request.app.state, "vault_syncer", None)
    if (syncer and request.method in ("POST", "PATCH", "PUT", "DELETE")
            and response.status_code < 400
            and not request.url.path.endswith(READ_ONLY_POSTS)):
        syncer.request()
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def mount_frontend(application: FastAPI, dist) -> bool:
    """Serve the built single-page app (and its client-side routes) from the same port as the API."""
    index = dist / "index.html"
    if not index.exists():
        return False
    if (dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)

    return True


mount_frontend(app, config.FRONTEND_DIST)
