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
