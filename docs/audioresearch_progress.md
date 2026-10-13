# Audio research: progress

## Step 0: pre-flight
Decisions in `audioresearch_decisions.md` (all defaults). `fpcalc`, `ffmpeg`, `ffprobe` not installed at the start; `.venv` is Python 3.11.7.

## Step 1: scaffold
Built: `audioresearch/` package, `config.py` (reads `.env` through `bpmkey.config`), CLI skeleton (`research`, `review`, `report`, `viewer`; a bare URL means `research`), `make test-audioresearch`, `.gitignore` entries, `--live` pytest flag.
Not built: command bodies (stubs).

## Step 2: data model and output contract
Built: `models.py` (all dataclasses, `Quality`/`Status` enums, JSON round trip), `output_schema.json`, tests.
Additions to the architecture's model, needed by later steps: `TrackRef.url` (a release candidate's tracks must be fetchable), `Candidate.catno`, `Candidate.position`, `Candidate.extra`, `Candidate.for_track()`.

## Step 3: identify
Built: `identify.py` on `bpmkey.discogs` (uses its private `_join_artists`/`_clean_artist` helpers rather than copying them). Fixtures copied to `tests/fixtures/discogs/`.
Note: `bpmkey.discogs.DiscogsClient` makes its own HTTP calls, outside the shared client of Step 7.

## Step 4: adapter interface and registry
Built: `adapters/base.py` (`Adapter`, `AdapterError`), `adapters/__init__.py` (`Registry`, `default_registry`; adapters switched off with `AUDIORESEARCH_DISABLED=a,b` or `registry.switch`), `adapters/fake.py` (`FakeAdapter`, kept outside `tests/` because the viewer's `--fake` mode needs it).
Additions: `Adapter.group` (adapters in a group run one after another, so `youtube_music` can fall back after `discogs_youtube`; groups run in parallel) and `Adapter.max_quality` (lets the pipeline skip adapters that cannot improve a track).

## Step 5: matcher
Built: `matcher.py` (weights documented at the top), `match_release`, `match_tracks_in_release`, `match_track`, `match_candidates` (top 3 per track, ambiguity and rejection reasons).
Surprise: `bpmkey.matching.version_penalty` only checks one direction (a plain title passes for a "Dub Mix" track) and charges 0.4, which lets a remix pass the 0.55 bar for unrelated titles. The matcher checks both directions and always charges 0.5, without touching `bpmkey`.

## Step 6: pipeline orchestrator
Built: `pipeline.py` (`research()`, `Run`), `events.py`, `health.py`; stubs for `fetch.py`, `verify.py`, `decide.py` (replaced in Steps 8 to 10).
Design points: adapters of a level run in parallel groups; a track keeps being searched at later levels only by adapters that can beat its current quality (`max_quality`); level 0 is never searched again once found; candidates marked `extra["trusted"]` (your files, pasted links) skip the matcher.
Candidate durations should be the FULL track length even for previews (iTunes `trackTimeMillis`); the real length of the downloaded file is measured on fetch.

## Step 6b: viewer
Built: `viewer/app.py` (FastAPI, SSE, localhost:8200), `viewer/static/index.html` (plain JS), `adapters/fake.py:demo_registry` for `--fake`. Checked in a real browser (Playwright) against a real Discogs release: no console errors, levels/stages/grid/summary fill in live; a stored run replays the same events (test).
Not built: nothing skipped. Past runs list is the 50 latest.

## Step 7: shared services
Built: `store.py` (migrations; identities, candidates, fetched audio, decisions with date, provenance, readings, run events, run results, manual links, review overrides), `http.py` (per-site delay, retry/backoff on 429/5xx and network errors, `Retry-After`, per-adapter stats), adapter health (5 consecutive failures, `AUDIORESEARCH_MAX_FAILURES`).
Cache rule: a stored result is reused when it covers the requested levels, no adapter reports changed inputs (`Adapter.changed_since`), and any `not_found` is younger than 30 days.

## Step 8: fetch and quality ladder
Built: `fetch.py` (`ytdlp_download`, `http_download`, `probe_duration` via mutagen then ffprobe, `classify`, `finalize`), `HttpClient.throttle` so yt-dlp calls respect the per-site delay. Quality: clip under 60 s; preview when under 80% of the Discogs duration and 15+ s short; otherwise full; with no Discogs duration the adapter's hint stands.
Tests generate tiny WAVs at run time (`tests/audio_utils.py`) instead of committing binaries; yt-dlp is mocked.
Installed with Homebrew: `ffmpeg`, `chromaprint` (provides `fpcalc`).

## Step 9: verification
Built: `verify.py` (duration check 6 s for full; unknown Discogs duration rejects over 15 min; far-longer audio and mix/medley titles rejected; preview/clip skip the duration check), `fingerprint.py` (`fpcalc -raw`, numpy sliding alignment of the middle 20 s of the shorter file, `compare` = agree / disagree / inconclusive), cross-check between sources, fingerprints stored in the DB with each fetched file.
A missing `fpcalc` gives a warning and duration-only verification (tested).
Thresholds: agree at 0.70 bit similarity, disagree below 0.63. Unrelated synthetic tunes reach ~0.59 at their best offset, so the first guess of 0.65/0.58 was too tight. These need checking on real audio in Step 17.
Medley detection is keyword based (title words such as "DJ mix", "medley", "EP preview"); the length rule catches the rest.

## Step 10: decide, review and report
Built: `decide.py` (confidence formula documented at the top of the file; disagreement always means review; level 0 always wins), CLI `research` (table, `--json`), `report <id>` (stored result and the provenance log of the latest run), `review <id>` (accept / reject / paste a link per track; reject remembers the URL so reruns skip it; a pasted link triggers a full rerun that uses the caches).
Part A is complete: a fake end-to-end run prints a table and writes JSON that passes the schema.

## Step 11: level 0
Built: `adapters/local_files.py` (port of `backend/app/analysis/matching.py`, copied; position first, then title; ambiguous files are never guessed; unmatched files appear as rejected candidates in the events and provenance), `adapters/manual_link.py` (links stored in the DB, fetched with yt-dlp or direct download). Level 0 candidates carry `extra["trusted"]` and skip the matcher; confidence is 1.0 for files and 0.95 for pasted links.
Level 0 is never cached (your folder and links are read fresh), and `changed_since` invalidates a cached result when files or links changed.
Not built: assigning an unmatched file to a track by hand (rename the file for now).

## Step 12: level 1
Built: `adapters/discogs_youtube.py` (linked videos as candidates; matching left to the shared matcher), `adapters/youtube_music.py` (ytmusicapi 1.12.3 pinned; fallback inside the `youtube` group, so only tracks no Discogs video matched are searched), `adapters/itunes.py` (previews; candidate duration is the full track length, the 30 s file turns into `clip` at fetch). `adapters/common.py` strips version brackets from search terms.
Fixtures from live calls: iTunes (hit and miss) and ytmusicapi (`tests/fixtures/itunes`, `.../youtube_music`).
Live check (`tests/test_live.py --live`) on Discogs 249504: track A found via the linked video (full, 213 s vs 212 s), track B (a different version) not found at level 1.

## Step 13: level 2, Bandcamp
Built: `parsers/bandcamp.py`, `adapters/bandcamp.py` (`Bandcamp` for albums, `BandcampTracks` as the single-track fallback in the same `bandcamp` group), matcher support for `Candidate.extra["unavailable"]` (non-streamable tracks of a matched release are rejected with a reason) and `extra["track_quality"]`.
Surprise (checked on the live site): Bandcamp's HTML search page (`/search?q=`) is behind a JavaScript "Client Challenge" and returns no results to a plain HTTP client. The adapter uses the public JSON endpoint the site's own search box calls (`/api/bcsearch_public_api/1/autocomplete_elastic`, POST, filter `a` albums or `t` tracks), which works with our normal User-Agent. Album and track pages are plain HTML; the whole tracklist, durations and streamability are in the `data-tralbum` attribute. If that endpoint changes, only `parsers/bandcamp.py` and `_search` need fixing.
Fixtures are real responses (Boards of Canada album and track pages, search JSON hit/miss, two different albums both called "Selected Ambient Works"). The non-streamable case is the real album page edited at test time (one track's `file` set to null), because no real example was at hand.
Live: album search returned the tracklist; yt-dlp downloaded a Bandcamp track (152 s mp3).
No preview-only tracks were seen on Bandcamp; every streamable track plays in full. A track with no `file` or `streaming: 0` counts as unavailable.
Also: matcher tie-break by artist similarity (a fan re-upload titled "Artist - Track" no longer outranks the artist's own upload).

## Step 14: level 3, SoundCloud (gate: the owner chose the default content in Step 0)
Built: `parsers/soundcloud.py` (`SoundcloudApi` + parsers), `adapters/soundcloud_tracks.py`, `adapters/soundcloud_sets.py`; the two run in parallel groups.
How it works (checked live): yt-dlp has no set search and no public API key exists, so the client reuses yt-dlp's own SoundCloud extractor (`_call_api`, which finds and refreshes the client_id) to call the api-v2 endpoints `search/tracks`, `search/albums`, `search/playlists_without_albums` and `tracks?ids=`. This uses yt-dlp's private `_call_api`/`_API_V2_BASE`; if a yt-dlp upgrade breaks it, the fixture tests pin the response format and only `parsers/soundcloud.py` needs a fix. Audio is fetched with yt-dlp from the permalink.
SoundCloud's `policy` field gives the quality hint: `SNIP` = 30 s snippet (preview, measured as a clip on fetch), `BLOCK` = unavailable. Candidate durations use `full_duration`, not the snippet length.
Sets only resolve their first five tracks in the search; the rest are fetched in batches of 50 with `tracks?ids=` and re-ordered into set order.
Fixtures are real responses. Rejections covered: hour-long DJ mixes ("Essential Mix", "Live Mix At Liquid Room") fail the duration rules in the matcher and the verifier; label preview medleys ("ALARM / STEAMPIT EP / JEFF MILLS - PURPOSE MAKER / ...", "...[WASP EP](Preview)") are caught by two new verifier rules (3+ tracks joined with " / ", or "preview" together with ep/lp/album/vinyl). Remixes, edits and bootlegs of the wanted track are rejected by the version check.

## Step 15: level 4, Beatport  (BLOCKED: needs a decision)
Built: `parsers/beatport.py`, `adapters/beatport.py` (`BeatportTracks`, `BeatportReleases`; catalogue number first, then title; mix name appended to the title as "Name (Mix Name)"; BPM and key stored as `Reading`s with source `beatport`; quality `preview`), `AdapterUnavailable` (an adapter that cannot work at all is switched off at once instead of after 5 failures), `BEATPORT_TOKEN` setting.
What the live check found: **beatport.com cannot be read.** Every page, including search, answers HTTP 403 "Just a moment..." (a Cloudflare managed challenge) to plain HTTP, headless Chromium and headed Chromium; `api.beatport.com/v4` answers 401 without an OAuth token. The architecture assumed public pages. Real responses are saved in `tests/fixtures/beatport/` (`cloudflare_challenge.html`, `api_unauthenticated.json`).
Consequence: no real Beatport data was available, so the API fixtures `UNVERIFIED_*.json` are hand-written in the shape of Beatport's public v4 API documentation and the parser is UNVERIFIED against a real response. Without `BEATPORT_TOKEN` both adapters report "unavailable" and are switched off (visible in the run's `adapters_off`). The tests cover that, the remix/dub rejection, the readings in the output JSON and the catalogue-number-first search.
Decision for the owner: (a) supply a Beatport OAuth token (`BEATPORT_TOKEN=...`) and run `pytest audioresearch/tests --live`, then replace the unverified fixtures with real responses; or (b) drop level 4 and rely on level 5 stores for BPM readings (deejay.de and decks.de also show BPM).

## Step 16: level 5, record stores (gate: the owner chose the default content in Step 0)
Built one store at a time against the live sites; shared plumbing in `adapters/stores/base.py` (catalogue number first, then artist and title, then one query per track if nothing was found; release candidates whose tracks are the store's clips labelled by position), parsers in `parsers/stores.py`.
- **deejay_de: works.** Search is `https://www.deejay.de/<query>`; the store only finds the catalogue number written without spaces ("AX084DC"). Clips are not in the page: the site's player script builds `/streamit/<2nd-last digit>/<last digit>/<article id><letter>.mp3` (about 150 s, 320 kbps); the BPM comes from `/ajaxHelper/getBPM.php?a=<id><letter>` and is stored as a `Reading` (source `deejay_de`). Real fetch checked: 149 s mp3.
- **hardwax: works.** Search is `https://hardwax.com/?find=<query>`; clips are `https://media.hardwax.com/audio/<id>_<position>.mp3` (about 90 s, position in the name). No BPM on the site. Its catalogue numbers drop the label prefix ("084 DC" vs "AX 084 DC"), so the matcher now scores a contained catalogue number (4+ characters) at 0.9.
- **decks_de: blocked.** Cloudflare challenge (HTTP 403 "Just a moment...", real response saved). Adapter exists, off by default (`AUDIORESEARCH_ENABLE=decks_de` turns it on), no parser. BPM readings from decks.de are therefore not available.
- **clone: blocked.** Its real search is `https://clone.nl/all/search?query=...` (found in the page's form) and is behind the same Cloudflare challenge. Same handling.
- **kalahari_oyster_cult: not built.** No working web address could be found (tried the obvious domains; none resolve), so there is nothing to read. Needs the shop's URL from the owner.
Fixtures are real pages (deejay.de and hardwax: catalogue number hit, artist/title hit, miss).
Clips of 60 s or more now measure as `preview` (not `full`) when there is no Discogs duration to compare; under 60 s they stay `clip`.

## Step 17: live run
16 releases from your library, 87 tracks: 73 found, 3 review, 11 not found. Details in `audioresearch_live_report.md`. The owner has not read the report yet, so by the plan this step is not closed: fixes become new steps.
