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
