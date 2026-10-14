# Audio Research and Matching: Build Plan for Claude Code

How to use this file: put it and `AUDIO_RESEARCH_ARCHITECTURE.md` in `building_plan/`. Give Claude Code one step at a time ("Do Step 4 from AUDIO_RESEARCH_BUILD_PLAN.md"). Don't move on until the step's **Done when** checks pass. Commit after every step.

> **Claude Code: read `AUDIO_RESEARCH_ARCHITECTURE.md` in full before Step 0.** It is the source of truth. When this plan and the architecture disagree, the architecture wins; stop and ask.

## Ground rules

- New package `audioresearch/` at the repo root, next to `bpmkey/`. Do **not** modify `bpmkey/` or `backend/`; import from them (`bpmkey.discogs`, `bpmkey.matching`). If something there must change, stop and ask.
- Python 3.11, same as the rest of the repo. Tests with pytest in `audioresearch/tests/`.
- **Tests never touch the network.** Every adapter is tested against saved responses in `audioresearch/tests/fixtures/<adapter>/`. Live checks are separate, marked `@pytest.mark.live`, skipped by default.
- Adapters only `search` and `fetch`. Matching, verifying and deciding live in the shared pipeline. Never put matching logic in an adapter.
- All HTTP goes through the shared client (Step 7): rate limits, retries, user agent, adapter health. No direct `requests.get` in adapters.
- Every step ends with a short note in `docs/audioresearch_progress.md`: what was built, what was not, anything that surprised you.
- Steps marked **GATE** need the owner's confirmation before you start them. Ask, then wait.
- Site details (search URLs, page structure, clip lengths) must be checked on the live site when an adapter is built, and the fixture saved from that real page. Do not invent page structures.

## Step 0: Pre-flight questions

**Goal:** confirm the open decisions before writing code.

**Instructions for Claude Code:**
1. Read section 10 of the architecture ("Open decisions"). Ask the owner, in one numbered message, whether to keep each default. Show the default in brackets.
2. Also ask: is `fpcalc` (Chromaprint) installed or installable on the owner's machine? Is `ffmpeg` available?
3. Write the answers to `docs/audioresearch_decisions.md` (question, answer, default or not).

**Done when:** the decisions file exists and the owner confirmed it.

---

# PART A: CORE (no real sites yet)

## Step 1: Package scaffold

**Goal:** an empty, runnable package.

**Instructions:**
1. Create `audioresearch/` with `__init__.py`, `__main__.py`, `cli.py`, `config.py`, `tests/`.
2. `config.py` reads `.env` like `bpmkey/config.py` does. New settings: `AUDIORESEARCH_DB` (default `audioresearch.db`), `AUDIO_CACHE_DIR` (default `audio_cache`), `REVIEW_THRESHOLD` (0.6), per-site delays.
3. Add `audio_cache/` and `audioresearch.db` to `.gitignore`. Add new dependencies to `requirements.txt` only when a step needs them.
4. CLI skeleton: `python -m audioresearch --help` lists `research`, `review`, `report`.
5. Add `make test-audioresearch` to the Makefile.

**Done when:** `python -m audioresearch --help` works and one trivial test passes.

## Step 2: Data model and output contract

**Goal:** the dataclasses of architecture sections 6 and 8.

**Instructions:**
1. `models.py`: `TrackRef`, `ReleaseIdentity`, `Candidate`, `Reading`, `FetchedAudio`, `TrackResult`, `ReleaseResult`. Quality and status as string enums (`full|preview|clip`, `found|review|not_found`).
2. `ReleaseResult.to_json()` produces exactly the JSON in section 8; `from_json()` reads it back.
3. A JSON schema file `audioresearch/output_schema.json` and a test that validates sample output against it.

**Done when:** round-trip tests pass (object → JSON → object) and the schema test passes.

## Step 3: Stage 1, identify the release

**Goal:** Discogs URL → `ReleaseIdentity`.

**Instructions:**
1. `identify.py`: use `bpmkey.discogs` for URL parsing, fetching and tracklist parsing. Master URLs resolve to the main release.
2. Fill `catno` and `label` from the first label entry, `videos` from the release's videos.
3. Tests with the Discogs fixtures already in `backend/tests/fixtures/` (copy, don't move them).

**Done when:** each fixture produces the expected identity, including per-track artists and missing durations as `None`.

## Step 4: Adapter interface and registry

**Goal:** the plug-in point for levels.

**Instructions:**
1. `adapters/base.py`: the `Adapter` class from architecture section 5 (`name`, `level`, `search`, `fetch`).
2. `adapters/__init__.py`: a registry that returns the adapters of one level, in parallel-run groups, and lets config switch adapters on and off.
3. A `FakeAdapter` in the tests, driven by a dict, so the pipeline can be tested without sites.

**Done when:** the registry returns the right adapters per level and the fake adapter returns canned candidates.

## Step 5: Stage 3, the shared matcher

**Goal:** release match, then track match, for every level.

**Instructions:**
1. `matcher.py`, built on `bpmkey.matching` (`score_candidate`, `version_penalty`, `bracket_penalty`, `dynamic_threshold`, `similarity`).
2. `match_release(identity, candidate) -> float`: catalogue number equality (strong), title and artist similarity, track count, per-track title similarity, per-track duration agreement. Document the weights at the top of the file.
3. `match_tracks_in_release(identity, candidate) -> dict[position, score]`: by position, then title and duration; version words must agree.
4. `match_track(identity, track, candidate) -> float`: `score_candidate` with `dynamic_threshold`.
5. Tests: exact release, release with one extra bonus track, wrong release with the same title, a remix posing as the original, two mixes of one song on one release, missing durations.

**Done when:** all listed cases score on the right side of the thresholds.

## Step 6: The pipeline orchestrator

**Goal:** stages 2 to 6 wired together, level by level, per release.

**Instructions:**
1. `pipeline.py`: `research(url_or_id, levels=range(0, 6), refresh=False) -> ReleaseResult`.
2. Per level: run its adapters in parallel (thread pool), only for tracks still unfound; match; fetch the top candidates (default 3 per track) best first; verify; decide. Unfound tracks go to the next level.
3. A lower-quality result found early (e.g. a clip) is kept but can be replaced by a better one at a later level. Level 0 results are never replaced.
4. For now, verification and fetching are stubs that accept everything; Steps 8 and 9 fill them in.
5. Tests with `FakeAdapter`s: a release fully found at level 1; one split across levels 1 and 3; one never found; one where level 0 overrides level 1.

**Done when:** those four scenarios produce the expected `ReleaseResult`.

## Step 6b: Run events and the process viewer (temporary debug page)

**Goal:** a local page where the owner pastes a Discogs link and watches the research happen: which level and stage is running, how many candidates and matches each step found, and how long each step took. It is a temporary tool for understanding the process, not part of Spin Count. Build it now, with fake adapters, and it keeps working as real adapters are added.

**Instructions for Claude Code:**
1. **Events from the pipeline.** Add `events.py` with one `RunEvent` dataclass: `run_id`, `seq`, `time` (monotonic ms since run start), `type`, `level`, `adapter`, `stage`, `position` (track, optional), `data` (dict). The pipeline emits events through a callback passed to `research(..., on_event=...)`; no callback means no cost.
2. **Event types** (emit all of them):
   - `run_started` (release URL), `release_identified` (artist, title, catno, track count, duration ms)
   - `level_started` (level, tracks still unfound), `level_finished` (level, tracks resolved at this level, tracks still unfound, duration ms)
   - `stage_started` / `stage_finished` for each stage 2 to 6, per adapter where it applies, with counts: search → candidates found; match → releases matched, tracks matched; fetch → files fetched, failed; verify → accepted, rejected (with reasons); decide → found, review
   - `candidate_rejected` (adapter, url, reason) and `track_resolved` (position, source, quality, confidence)
   - `adapter_off` (adapter, reason), `run_finished` (found / review / not found counts, total duration ms)
3. **Store events.** Save every event in the cache DB (`run_events` table), so a past run can be replayed in the viewer.
4. **Viewer server.** `audioresearch/viewer/` with a small FastAPI app, started by `python -m audioresearch viewer` on `127.0.0.1:8200` (localhost only, no login):
   - `POST /runs` with `{ "url": "..." }` starts a run in a background thread and returns `run_id`.
   - `GET /runs/{id}/events` streams events live as Server-Sent Events, starting with any events already stored.
   - `GET /runs` lists past runs; `GET /runs/{id}` returns the final `ReleaseResult` JSON.
   - `--fake` flag: runs use the `FakeAdapter`s, so the viewer works before any real adapter exists.
5. **Viewer page.** One static `index.html` with plain JavaScript (no build step), served by the same app:
   - **Top:** a Discogs link field and a Start button; the release once identified (artist, title, catno, tracks); a running total time.
   - **Level timeline:** one row per level (0 to 5), and per level each stage as a box showing its state (waiting, running, done, skipped), its counts (e.g. "search: 14 candidates", "match: 1 release, 6 tracks") and its duration in ms. Adapters inside a level that run in parallel are shown side by side.
   - **Track grid:** one row per track (A1, A2, B1 ...), one column per level; each cell shows found / review / not tried / not found, with source, quality and confidence once resolved.
   - **Event log:** the raw event list at the bottom, newest last, including every `candidate_rejected` reason.
   - **Summary at the end:** found / review / not found counts, total time, time per level, adapters switched off.
   - Past runs selectable from a list and replayed from stored events.
6. **Tests:** with fake adapters, a run emits events in the right order with correct counts and durations; the SSE endpoint streams a complete run; a stored run replays the same events.

**Done when:** `python -m audioresearch viewer --fake` opens a page where pasting any Discogs link (identified for real by Stage 1) shows the levels, stages, counts and timings filling in live, and the final summary matches the CLI output.

**Later, as adapters are built (Steps 11 to 16):** no viewer changes should be needed. If an adapter needs a new count, add it to the stage event's `data`, and the page shows it.

## Step 7: Shared services

**Goal:** cache, provenance log, HTTP client, rate limits, adapter health.

**Instructions:**
1. `store.py` (SQLite, `audioresearch.db`): tables for release identities, candidates, fetched audio, decisions, provenance entries, readings. Simple numbered migrations.
2. Cache: a rerun of a release makes no network calls unless `refresh=True`. `not_found` is stored with a date.
3. `http.py`: one shared session; per-site minimum delay; retry with backoff on 429/5xx; `User-Agent` with `CONTACT_EMAIL`; failures counted per adapter.
4. Adapter health: after N consecutive failures (default 5) the adapter is off for the rest of the run and listed in `adapters_off`.
5. Provenance: every candidate's adapter, URL, scores, verification results and accept/reject reason.

**Done when:** tests show a cached rerun does zero HTTP calls, the rate limiter spaces calls, and a failing fake adapter gets switched off.

## Step 8: Stage 4, fetch and the quality ladder

**Goal:** downloading audio for the chosen candidates.

**Instructions:**
1. `fetch.py`: a `yt-dlp` helper (best audio, no re-encoding, skip over 20 minutes; reuse the approach in `bpmkey/analyze.py`) and a direct HTTP download helper (for preview URLs).
2. Save to `audio_cache/<release id>/<position>.<adapter>.<ext>`. Measure the real duration of the file (with `ffprobe` or `mutagen`) and set the real quality: `clip` if under 60 s, `preview` if clearly shorter than the Discogs duration, `full` otherwise.
3. Tests with tiny audio files in fixtures; `yt-dlp` mocked.

**Done when:** fetched files land in the right place and get the right quality label.

## Step 9: Stage 5, verification

**Goal:** reject wrong recordings; confirm across sources.

**Instructions:**
1. `verify.py`: duration check (tolerance 6 s for `full`; unknown Discogs duration rejects over 15 minutes).
2. Mix and medley check: reject audio far longer than the track, and preview medleys (several tracks stitched into one upload).
3. `fingerprint.py`: Chromaprint via `fpcalc` (raw fingerprints). An alignment function that slides a short fingerprint (clip, preview) along a long one and returns the best match ratio. Store fingerprints in the DB.
4. Cross-check: when a track has two fetched sources, align them; agreement raises confidence, disagreement sends the track to review.
5. Tests: the same audio file trimmed into a clip aligns; two different files do not.

**Done when:** those tests pass, and a missing `fpcalc` makes verification fall back to duration only, with a warning, not a crash.

## Step 10: Stage 6, decide, review and report

**Goal:** final choice, confidence, reasons, review queue, CLI output.

**Instructions:**
1. `decide.py`: per track, best verified candidate by quality then confidence; build `confidence` (0 to 1) from match score, verification and source agreement; write a one-line `reason`. Below `REVIEW_THRESHOLD` → status `review`.
2. CLI: `research` prints a table (position, status, source, quality, confidence) and writes JSON with `--json`. `report <id>` shows the provenance log. `review <id>` lets the owner accept, reject or paste a manual link per track.
3. Tests for the confidence rules and the review threshold.

**Done when:** a fake end-to-end run prints a readable table and valid JSON.

---

# PART B: ADAPTERS (one level at a time)

For every adapter: (1) check the live site and save real responses as fixtures, (2) write the parser and the adapter, (3) unit tests on fixtures, (4) one `@pytest.mark.live` test on a real release the owner picks, (5) note in the progress file what worked and what did not.

## Step 11: Level 0, your files and manual links

**Instructions:**
1. `adapters/local_files.py`: files in `audio/<release id>/`, matched by position, then title; unmatched files listed. Port the logic of `backend/app/analysis/matching.py` (copy, don't import from the backend).
2. `adapters/manual_link.py`: a URL per track, stored in the DB, fetched with `yt-dlp` or direct download.
3. Results from level 0 always win and are never replaced.

**Done when:** a fixture folder with `A1 - Title.wav`-style files matches correctly, with unmatched files reported.

## Step 12: Level 1, Discogs find

**Instructions:**
1. `adapters/discogs_youtube.py`: candidates from the release's linked videos; port the scoring from `bpmkey/sources/youtube.py`.
3. `adapters/itunes.py`: iTunes Search API, as in `bpmkey/sources/itunes.py`; quality `preview` or `clip`.
4. The YouTube route and the iTunes route run in parallel.

**Done when:** fixture tests pass for all three, and one live release returns audio for at least one track.

## Step 13: Level 2, Bandcamp

**Instructions:**
1. `adapters/bandcamp.py` with a `parsers/bandcamp.py`: search Bandcamp's public search page by artist and release title, albums first, then tracks. Album candidates carry their tracklist and durations.
2. Fetch with `yt-dlp`. Mark tracks that are not streamable or preview-only.
3. Rate limit: at least 1 s between requests.

**Done when:** fixture tests cover an album hit, a single-track hit, a wrong album with the same title, and a non-streamable track.

## Step 14: Level 3, SoundCloud — GATE

Ask the owner to confirm the SoundCloud level as described in the architecture before starting.

**Instructions:**
1. `adapters/soundcloud_tracks.py`: `yt-dlp` `scsearch` by artist and title, as in `bpmkey/sources/soundcloud.py`.
2. `adapters/soundcloud_sets.py`: search sets by artist and release title; candidates carry the set's tracklist.
3. Both in parallel. Fixture cases must include a DJ mix and a label preview medley, both rejected.

**Done when:** fixture tests pass, including the two rejections.

## Step 15: Level 4, Beatport (dropped)

Not built. Beatport cannot be read without a partner OAuth token (see progress notes, Step 15). Level 4 stays empty so the other level numbers do not change.

---

## Step 16: Level 5, record stores — GATE

Ask the owner to confirm the record-store level, whether clips count as results, and the store order, before starting. Then build **one store at a time**, each as its own sub-step with its own commit.

**Instructions (per store):**
1. `adapters/stores/<store>.py` with its own parser: search by catalogue number first, then artist and title; read clips by position (`A1`, `B1`).
2. Rate limit: at least 2 s between requests.
3. For `deejay_de` and `decks_de`, store the shown BPM as a `Reading`.
4. Default order: `deejay_de`, `decks_de`, `hardwax`, `clone`, `kalahari_oyster_cult`.

**Done when (per store):** fixture tests pass for a catalogue-number hit, an artist/title hit and a miss.

---

# PART C: CHECK IT FOR REAL

## Step 17: Live run on the owner's records

**Instructions:**
1. Ask the owner for 10 to 20 Discogs links covering easy and hard cases (well-known release, vinyl-only, white label, compilation, multiple mixes of one song).
2. Run all levels with `--json`. Write `docs/audioresearch_live_report.md`: per release, which level found each track, the quality, the confidence, and every track that went to review or was not found, with the reason.
3. List adapters that failed or broke, and fixes needed.

**Done when:** the report exists and the owner has read it. Fixes become new steps.

---

# LATER (not part of this plan)

- Adapt the tool into `bpmkey`: `bpmkey` reads the output contract (section 8) instead of finding audio itself.
- Change `bpmkey` to take audio directly instead of a Discogs link.
- Apple Music API as an alternative to the iTunes API in level 1.
- Decide what analysis goes "beyond BPM and key".
- Connect the tool to the Spin Count app.
