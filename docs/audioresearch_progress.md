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
