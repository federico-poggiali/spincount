"""Add to YT playlist: each track's YouTube video, your YouTube account, and adding the tracks you pick to
one of your playlists. Nothing is added to YouTube by itself."""
import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app import config
from app.db import tracks
from app.deps import get_db, get_runner, require_record
from app.jobs.runner import JobRunner
from app.schemas import (
    AddedToPlaylist,
    AddToPlaylist,
    FindYouTubeRequest,
    JobStarted,
    RecordYouTubeOut,
    YouTubeConnect,
    YouTubeCredentials,
    YouTubeCredentialsSaved,
    YouTubePlaylist,
    YouTubeStatus,
)
from app.youtube import links
from app.youtube.account import (
    Account,
    BadCredentials,
    CredentialsFromEnv,
    NotConfigured,
    NotConnected,
    QuotaExceeded,
    YouTubeError,
    account,
)

router = APIRouter(tags=["youtube"])


def get_youtube() -> Account:
    return account()


def _api_errors(exc: YouTubeError) -> HTTPException:
    if isinstance(exc, NotConfigured):
        return HTTPException(503, str(exc))
    if isinstance(exc, NotConnected | CredentialsFromEnv):
        return HTTPException(409, str(exc))
    if isinstance(exc, BadCredentials):
        return HTTPException(400, str(exc))
    return HTTPException(502, str(exc))


@router.get("/api/records/{record_id}/youtube", response_model=RecordYouTubeOut)
def record_youtube(record_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Each track's YouTube video, found or not, including the YouTube links the audio search already found;
    tracks with neither are left out."""
    require_record(conn, record_id)
    return {"tracks": list(links.videos_for_record(conn, record_id).values())}


@router.post("/api/records/{record_id}/find-youtube", status_code=202, response_model=JobStarted)
def find_youtube(record_id: int, body: FindYouTubeRequest | None = None,
                 conn: sqlite3.Connection = Depends(get_db), runner: JobRunner = Depends(get_runner)) -> dict:
    """Find this record's tracks on YouTube (again, with `refresh`). Links only, nothing is downloaded."""
    require_record(conn, record_id)
    params = {"refresh": True} if body and body.refresh else None
    return {"job_id": runner.enqueue(links.JOB_TYPE, record_id, params), "status": "queued"}


@router.get("/api/youtube/status", response_model=YouTubeStatus)
def youtube_status(yt: Account = Depends(get_youtube)) -> dict:
    if not yt.configured:
        return {"configured": False, "connected": False}
    return {"configured": True, "connected": yt.connected, "source": yt.source, "client_id": yt.client_id,
            "usage": yt.usage()}


@router.put("/api/youtube/credentials", response_model=YouTubeCredentialsSaved)
def youtube_save_credentials(body: YouTubeCredentials, yt: Account = Depends(get_youtube)) -> dict:
    """Keep your own Google app's client ID and secret (your own 10,000 units a day), checked with Google
    first. A different app than before signs you out of YouTube."""
    try:
        return {"checked": yt.save_credentials(body.client_id, body.client_secret)}
    except YouTubeError as exc:
        raise _api_errors(exc) from exc


@router.delete("/api/youtube/credentials", status_code=204)
def youtube_remove_credentials(yt: Account = Depends(get_youtube)) -> Response:
    """Forget the client ID and secret saved in Settings, and sign out."""
    try:
        yt.remove_credentials()
    except YouTubeError as exc:
        raise _api_errors(exc) from exc
    return Response(status_code=204)


@router.post("/api/youtube/connect", response_model=YouTubeConnect)
def youtube_connect(request: Request, yt: Account = Depends(get_youtube)) -> dict:
    """Start the Google sign-in: open the returned page; Google comes back to the callback, which returns to
    Settings on the page that asked (this app, or the dev server)."""
    origin = request.headers.get("origin")
    own = str(request.base_url).rstrip("/")
    return_to = origin if origin in (*config.CORS_ORIGINS, own) else own
    try:
        return {"url": yt.start(str(request.url_for("youtube_callback")), return_to)}
    except YouTubeError as exc:
        raise _api_errors(exc) from exc


@router.get("/api/youtube/callback", include_in_schema=False)
def youtube_callback(request: Request, state: str = "", code: str = "", error: str = "",
                     yt: Account = Depends(get_youtube)) -> RedirectResponse:
    back = yt.return_to(state) or str(request.base_url).rstrip("/")
    try:
        if error:
            raise YouTubeError(f"Google sign-in was cancelled ({error})")
        yt.finish(state, code)
    except YouTubeError as exc:
        query = urlencode({"youtube": "error", "message": str(exc)})
        return RedirectResponse(f"{back}/settings?{query}", 303)
    return RedirectResponse(f"{back}/settings?youtube=connected", 303)


@router.delete("/api/youtube/connection", status_code=204)
def youtube_disconnect(yt: Account = Depends(get_youtube)) -> Response:
    yt.disconnect()
    return Response(status_code=204)


@router.get("/api/youtube/playlists", response_model=list[YouTubePlaylist])
def youtube_playlists(yt: Account = Depends(get_youtube)) -> list[dict]:
    """Your playlists, to pick where tracks go."""
    try:
        return yt.playlists()
    except YouTubeError as exc:
        raise _api_errors(exc) from exc


@router.post("/api/youtube/playlists/{playlist_id}/tracks", response_model=AddedToPlaylist)
def add_to_playlist(playlist_id: str, body: AddToPlaylist, conn: sqlite3.Connection = Depends(get_db),
                    yt: Account = Depends(get_youtube)) -> dict:
    """Add these tracks' videos to one of your playlists, in the order given. A video already in it is
    skipped, so adding twice is safe. Each video added costs 50 of YouTube's 10,000 daily quota units."""
    if missing := [i for i in body.track_ids if tracks.get(conn, i) is None]:
        raise HTTPException(404, f"no such tracks: {missing}")
    videos = links.videos_for_tracks(conn, body.track_ids)
    out = {"added": [], "already": [], "no_video": [], "failed": [], "quota_exceeded": False}
    try:
        present = yt.video_ids(playlist_id)
    except YouTubeError as exc:
        raise _api_errors(exc) from exc
    for i, track_id in enumerate(body.track_ids):
        vid = (videos.get(track_id) or {}).get("video_id")
        if not vid:
            out["no_video"].append(track_id)
        elif vid in present:
            out["already"].append(track_id)
        else:
            try:
                yt.add(playlist_id, vid)
            except QuotaExceeded as exc:
                out["quota_exceeded"] = True
                out["failed"] += [{"track_id": t, "error": str(exc)} for t in body.track_ids[i:]]
                break
            except NotConnected as exc:
                raise _api_errors(exc) from exc
            except YouTubeError as exc:
                out["failed"].append({"track_id": track_id, "error": str(exc)})
                continue
            present.add(vid)
            out["added"].append(track_id)
    return out
