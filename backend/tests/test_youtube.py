"""Add to YT playlist: every track gets a YouTube video (the audio search's, else a search), your account
connects through Google, and the tracks you pick go into a playlist once each."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.db import connect, records, track_audio, track_youtube, tracks
from app.jobs.runner import JobRunner
from app.routes.youtube import get_youtube
from app.youtube import links
from app.youtube.account import Account

YT = "https://www.youtube.com/watch?v={}"
HIT = {"video_id": "searchedVid", "title": "B - Third", "channel": "B - Topic", "duration": 300, "confidence": 0.9}


def setup_record(db_path):
    conn = connect(db_path)
    rid = records.create(conn, artist="B", title="Rec", discogs_release_id=9261843)
    ids = [tracks.create(conn, rid, position=p, title=t) for p, t in
           [("A1", "First"), ("A2", "Second"), ("B1", "Third"), ("B2", "Fourth")]]
    found = dict(status="found", source="discogs_youtube", level=1, quality="full", confidence=0.9, reason="",
                 page=None, audio_path=None, readings=[], found_at="2026-11-03T00:00:00Z")
    track_audio.put(conn, ids[0], **{**found, "url": YT.format("discogsVid1"), "alternatives": []})
    track_audio.put(conn, ids[1], **{**found, "source": "bandcamp", "url": "https://x.bandcamp.com/track/2",
                                     "alternatives": [{"source": "discogs_youtube", "url": YT.format("altVideo002")}]})
    conn.close()
    return rid, ids


class Finder:
    def __init__(self):
        self.searched = []

    def __call__(self, identity, track):
        self.searched.append(track.position)
        return HIT if track.title == "Third" else None


def test_every_track_gets_a_video_or_a_not_found(db_path):
    rid, ids = setup_record(db_path)
    conn = connect(db_path)
    finder = Finder()
    record = records.get(conn, rid)
    assert links.find_for_record(conn, record, finder) == {"audio": 2, "search": 1, "not_found": 1}
    assert finder.searched == ["B1", "B2"]  # the audio search's YouTube links are reused, not searched again
    rows = track_youtube.for_record(conn, rid)
    assert [rows[i]["video_id"] for i in ids] == ["discogsVid1", "altVideo002", "searchedVid", None]
    assert rows[ids[0]]["source"] == "audio" and rows[ids[2]]["source"] == "search"
    assert rows[ids[2]]["title"] == "B - Third"

    assert links.find_for_record(conn, record, finder) == {"audio": 0, "search": 0, "not_found": 0}
    assert finder.searched == ["B1", "B2"]  # a second run does nothing
    links.find_for_record(conn, record, finder, refresh=True)
    assert finder.searched == ["B1", "B2", "B1", "B2"]
    conn.close()


def test_the_library_button_queues_only_records_not_searched(client, db_path):
    rid, _ = setup_record(db_path)
    runner = client.app.state.runner = JobRunner({links.JOB_TYPE: links.make_handler(Finder())})
    first = client.post("/api/admin/find-youtube").json()
    assert first["queued"] == 1
    runner.run_pending()
    assert client.get(f"/api/jobs/{first['job_ids'][0]}").json()["status"] == "done"
    assert client.post("/api/admin/find-youtube").json()["queued"] == 0
    shown = client.get(f"/api/records/{rid}/youtube").json()["tracks"]
    assert {t["video_id"] for t in shown} == {"discogsVid1", "altVideo002", "searchedVid", None}


def test_adding_a_record_looks_it_up_on_youtube_only_when_the_setting_is_on(client):
    url = "https://www.discogs.com/release/9261843"
    off = client.post("/api/records/intake", json={"discogs_url": url, "status": "wantlist"}).json()
    assert "youtube" not in off["jobs"]
    client.delete(f"/api/records/{off['id']}")
    assert client.patch("/api/settings", json={"youtube_playlist": True}).json()["youtube_playlist"] is True
    on = client.post("/api/records/intake", json={"discogs_url": url, "status": "wantlist"}).json()
    assert on["jobs"]["youtube"] > on["jobs"]["audio"]  # after the audio job, which finds the Discogs videos


# ---- the account -----------------------------------------------------------------------------------------
class Google:
    """A fake Google: the token endpoint and the two playlist endpoints."""

    def __init__(self, playlist=(), quota_after=None):
        self.playlist, self.quota_after, self.inserted, self.token_calls = list(playlist), quota_after, [], []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            self.token_calls.append(form["grant_type"][0])
            body = {"access_token": "AT", "expires_in": 3600}
            if form["grant_type"][0] == "authorization_code":
                assert form["code"] == ["the-code"] and form["code_verifier"]
                body["refresh_token"] = "RT"
            return httpx.Response(200, json=body)
        if request.url.path == "/revoke":
            self.token_calls.append("revoke")
            return httpx.Response(200)
        assert request.headers["authorization"] == "Bearer AT"
        if request.url.path.endswith("/playlists"):
            return httpx.Response(200, json={"items": [
                {"id": "PL1", "snippet": {"title": "Digging"}, "contentDetails": {"itemCount": len(self.playlist)}}]})
        if request.method == "GET":  # playlistItems
            return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": v}} for v in self.playlist]})
        if self.quota_after is not None and len(self.inserted) >= self.quota_after:
            return httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}})
        video = json.loads(request.content)["snippet"]["resourceId"]["videoId"]
        self.inserted.append(video)
        self.playlist.append(video)
        return httpx.Response(200, json={"id": "item"})


@pytest.fixture
def google(client, tmp_path):
    def make(**kw):
        fake = Google(**kw)
        account = Account("cid", "secret", tmp_path / "token.json", httpx.Client(transport=httpx.MockTransport(fake)))
        client.app.dependency_overrides[get_youtube] = lambda: account
        return fake, account
    return make


def connect_account(client):
    start = client.post("/api/youtube/connect", headers={"origin": "http://localhost:5173"}).json()["url"]
    query = parse_qs(urlparse(start).query)
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["https://www.googleapis.com/auth/youtube"]
    assert query["redirect_uri"][0].endswith("/api/youtube/callback")
    return client.get("/api/youtube/callback", params={"state": query["state"][0], "code": "the-code"},
                      follow_redirects=False)


def test_connecting_keeps_a_private_token_and_returns_to_settings(client, google, tmp_path):
    fake, _ = google()
    status = client.get("/api/youtube/status").json()
    assert status["configured"] is True and status["connected"] is False and status["source"] == "env"
    assert client.get("/api/youtube/playlists").status_code == 409
    back = connect_account(client)
    assert back.status_code == 303 and back.headers["location"] == "http://localhost:5173/settings?youtube=connected"
    token = tmp_path / "token.json"
    assert json.loads(token.read_text()) == {"refresh_token": "RT"} and token.stat().st_mode & 0o777 == 0o600
    assert client.get("/api/youtube/playlists").json() == [{"id": "PL1", "title": "Digging", "count": 0}]
    assert client.delete("/api/youtube/connection").status_code == 204
    assert not token.exists() and fake.token_calls[-1] == "revoke"


def test_a_callback_nobody_started_is_refused(client, google):
    google()
    back = client.get("/api/youtube/callback", params={"state": "forged", "code": "x"}, follow_redirects=False)
    assert "youtube=error" in back.headers["location"]


def test_connect_without_a_client_id_says_how_to_set_it_up(client, tmp_path):
    client.app.dependency_overrides[get_youtube] = lambda: Account("", "", tmp_path / "t.json")
    r = client.post("/api/youtube/connect")
    assert r.status_code == 503 and "YOUTUBE_CLIENT_ID" in r.json()["error"]["message"]


def test_tracks_are_added_in_order_once_each(client, db_path, google):
    rid, ids = setup_record(db_path)
    conn = connect(db_path)
    links.find_for_record(conn, records.get(conn, rid), Finder())
    conn.close()
    fake, _ = google(playlist=["altVideo002"])
    connect_account(client)
    out = client.post("/api/youtube/playlists/PL1/tracks", json={"track_ids": ids}).json()
    assert out == {"added": [ids[0], ids[2]], "already": [ids[1]], "no_video": [ids[3]], "failed": [],
                   "quota_exceeded": False}
    assert fake.inserted == ["discogsVid1", "searchedVid"]
    again = client.post("/api/youtube/playlists/PL1/tracks", json={"track_ids": ids}).json()
    assert again["added"] == [] and fake.inserted == ["discogsVid1", "searchedVid"]


def test_running_out_of_quota_stops_and_says_so(client, db_path, google):
    rid, ids = setup_record(db_path)
    conn = connect(db_path)
    links.find_for_record(conn, records.get(conn, rid), Finder())
    conn.close()
    fake, _ = google(quota_after=1)
    connect_account(client)
    out = client.post("/api/youtube/playlists/PL1/tracks", json={"track_ids": ids}).json()
    assert out["quota_exceeded"] is True and out["added"] == [ids[0]]
    assert [f["track_id"] for f in out["failed"]] == ids[1:]


def test_links_the_audio_search_found_show_and_add_without_a_lookup(client, db_path, google):
    rid, ids = setup_record(db_path)  # A1 and A2 have YouTube links from the audio search; nothing looked up yet
    shown = {t["track_id"]: t for t in client.get(f"/api/records/{rid}/youtube").json()["tracks"]}
    assert set(shown) == {ids[0], ids[1]}  # B1 and B2 still need a lookup
    assert shown[ids[0]]["video_id"] == "discogsVid1" and shown[ids[0]]["source"] == "audio"
    assert shown[ids[1]]["video_id"] == "altVideo002"

    fake, _ = google()
    connect_account(client)
    out = client.post("/api/youtube/playlists/PL1/tracks", json={"track_ids": ids}).json()
    assert out["added"] == [ids[0], ids[1]] and out["no_video"] == [ids[2], ids[3]]
    assert fake.inserted == ["discogsVid1", "altVideo002"]

    conn = connect(db_path)  # a stored lookup wins over the audio link
    track_youtube.put(conn, ids[0], video_id="betterVideo", source="search", found_at="2026-11-03T00:00:00Z")
    conn.close()
    shown = {t["track_id"]: t for t in client.get(f"/api/records/{rid}/youtube").json()["tracks"]}
    assert shown[ids[0]]["video_id"] == "betterVideo"


# ---- your own Google app, pasted in Settings -------------------------------------------------------------------
GOOD_ID = "123-abc.apps.googleusercontent.com"


def checking_google(request: httpx.Request) -> httpx.Response:
    """Google's token endpoint answering the credentials check: it knows GOOD_ID with the secret "s3cret"."""
    form = parse_qs(request.content.decode())
    if request.url.path == "/revoke":
        return httpx.Response(200)
    assert form["code"] == ["spincount-check"]
    if form["client_id"] == [GOOD_ID] and form["client_secret"] == ["s3cret"]:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Malformed auth code."})
    return httpx.Response(401, json={"error": "invalid_client", "error_description": "Unauthorized"})


@pytest.fixture
def own_app(client, tmp_path):
    def make(env=("", ""), transport=checking_google):
        account = Account(*env, tmp_path / "token.json", httpx.Client(transport=httpx.MockTransport(transport)),
                          client_path=tmp_path / "client.json")
        client.app.dependency_overrides[get_youtube] = lambda: account
        return account
    return make


def test_credentials_pasted_in_settings_are_checked_and_kept_privately(client, own_app, tmp_path):
    own_app()
    assert client.get("/api/youtube/status").json()["configured"] is False
    def put(cid, secret):
        return client.put("/api/youtube/credentials", json={"client_id": cid, "client_secret": secret})

    malformed = put("not-a-client-id", "s3cret")
    assert malformed.status_code == 400 and ".apps.googleusercontent.com" in malformed.json()["error"]["message"]
    wrong = put(GOOD_ID, "wrong")
    assert wrong.status_code == 400 and "Google does not know" in wrong.json()["error"]["message"]
    assert not (tmp_path / "client.json").exists()  # nothing kept until Google knows them

    assert put(f"  {GOOD_ID} ", "s3cret").json() == {"checked": True}
    saved = tmp_path / "client.json"
    assert json.loads(saved.read_text()) == {"client_id": GOOD_ID, "client_secret": "s3cret"}
    assert saved.stat().st_mode & 0o777 == 0o600
    status = client.get("/api/youtube/status").json()
    assert status["configured"] and status["source"] == "settings" and status["client_id"] == GOOD_ID
    assert status["usage"]["used"] == 0 and status["usage"]["limit"] == 10_000
    start = client.post("/api/youtube/connect").json()["url"]
    assert parse_qs(urlparse(start).query)["client_id"] == [GOOD_ID]  # sign-in uses the saved app

    assert client.delete("/api/youtube/credentials").status_code == 204
    assert not saved.exists() and client.get("/api/youtube/status").json()["configured"] is False


def test_unreachable_google_saves_unchecked(client, own_app):
    def offline(request):
        raise httpx.ConnectError("no network")
    own_app(transport=offline)
    r = client.put("/api/youtube/credentials", json={"client_id": GOOD_ID, "client_secret": "s3cret"})
    assert r.json() == {"checked": False} and client.get("/api/youtube/status").json()["configured"] is True


def test_credentials_in_env_win_and_cannot_be_changed_in_settings(client, own_app, tmp_path):
    (tmp_path / "client.json").write_text(json.dumps({"client_id": GOOD_ID, "client_secret": "s3cret"}))
    own_app(env=("env-id.apps.googleusercontent.com", "env-secret"))
    status = client.get("/api/youtube/status").json()
    assert status["source"] == "env" and status["client_id"] == "env-id.apps.googleusercontent.com"
    r = client.put("/api/youtube/credentials", json={"client_id": GOOD_ID, "client_secret": "s3cret"})
    assert r.status_code == 409 and ".env" in r.json()["error"]["message"]
    assert client.delete("/api/youtube/credentials").status_code == 409


def test_a_different_app_signs_you_out(client, own_app, tmp_path):
    account = own_app()
    (tmp_path / "client.json").write_text(json.dumps({"client_id": "old.apps.googleusercontent.com",
                                                     "client_secret": "x"}))
    (tmp_path / "token.json").write_text(json.dumps({"refresh_token": "RT"}))
    assert account.connected
    client.put("/api/youtube/credentials", json={"client_id": GOOD_ID, "client_secret": "s3cret"})
    assert not account.connected


# ---- quota -------------------------------------------------------------------------------------------------------
def test_units_are_counted_per_pacific_day(client, db_path, google, tmp_path):
    rid, ids = setup_record(db_path)
    conn = connect(db_path)
    links.find_for_record(conn, records.get(conn, rid), Finder())
    conn.close()
    fake, account = google()
    clock = [1_762_200_000.0]  # 2025-11-03 20:00 UTC = 12:00 in California
    account._now = lambda: clock[0]
    connect_account(client)
    client.post("/api/youtube/playlists/PL1/tracks", json={"track_ids": ids})  # 1 listing + 3 adds
    usage = client.get("/api/youtube/status").json()["usage"]
    assert usage == {"used": 1 + 3 * 50, "limit": 10_000, "resets_at": "2025-11-04T08:00:00Z"}
    assert (tmp_path / "youtube_usage.json").stat().st_mode & 0o777 == 0o600

    clock[0] += 12 * 3600  # past Pacific midnight: a new day
    assert client.get("/api/youtube/status").json()["usage"]["used"] == 0


def test_quota_refused_by_google_shows_as_all_used(client, db_path, google):
    rid, ids = setup_record(db_path)
    conn = connect(db_path)
    links.find_for_record(conn, records.get(conn, rid), Finder())
    conn.close()
    google(quota_after=0)
    connect_account(client)
    client.post("/api/youtube/playlists/PL1/tracks", json={"track_ids": ids})
    assert client.get("/api/youtube/status").json()["usage"]["used"] == 10_000
