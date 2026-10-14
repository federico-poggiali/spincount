# Integration: audioresearch into Spin Count

How to use: give Claude Code one step at a time ("Do Step I2 from INTEGRATION_BUILD_PLAN.md"). Ask the owner the open questions of a step before building it. Commit after every step and note it in `docs/integration_progress.md`.

## Decisions (owner, 2026-10-14; row 1 revised the same day)

| # | Question | Answer |
|---|----------|--------|
| 1 | When does audio research run | Only as the first stage of analysis: when a record is added and analysis starts, or when you press Analyze. Never on its own at add time. A Settings option runs it for the whole existing library. Applies to every record that gets analysed (owned and wantlist) |
| 2 | Found audio in the app | Shown directly; only `review` tracks need the owner; uncertain audio may feed analysis, marked "audio uncertain" |
| 3 | Audio cache and `audioresearch.db` | Application Support, next to `vinyl.db` (outside OneDrive) |
| 4 | bpmkey CLI and web page (:8765) | Keep working; its own audio search stays behind a flag until the new path is proven, then it is removed |

## Principles

1. **The output contract is the only link.** The backend calls `audioresearch.research()` and stores each track's result in `vinyl.db`. It never reads `audioresearch.db`, which stays the tool's own cache and provenance log. `bpmkey` never imports `audioresearch` (the reverse import already exists).
2. **Owner decisions live in `vinyl.db` only.** Hand-assigned files, pasted links, accepted or rejected candidates are stored there and passed into `research()` on each run.
3. **Audio is a stage of analysis.** Asking for analysis (intake, the Analyze button, a Settings run) queues an `audio` job followed by the `analysis` job; nothing queues `audio` alone except the Settings library run. Two jobs, because finding audio is minutes of network and analysis is seconds on a local file: a re-analysis reuses the audio already found and does not search again unless you ask.
4. **bpmkey receives audio, it does not find it.** New entry point taking `{position: (path, quality)}` plus store readings (deejay.de BPM) as one more vote.
5. **One setting per folder.** `AUDIO_DIR` and `AUDIORESEARCH_LOCAL_AUDIO` become one.
6. **Tests never touch the network.** The backend injects a fake `research` function (as it does `lookup_fn`); saved contract JSON is the test data.

## Phase 0: settle the tool (done except two items)

Done: tool committed (`609b70f`), tests pass, docs match the code.
Open, to settle at the start of I1: (a) the owner reads `docs/audioresearch_live_report.md` (Step 17 stays open until then); (b) is confidence 0.62 acceptable when Discogs has no durations (it is what Barker and Neurø got)?

## Phase 1: audio in the app, read-only (steps I1 to I3 built; see `docs/integration_progress.md` for the differences)

### Step I1: contract v1 and one config
1. Add `contract_version: 1` to `ReleaseResult` JSON and `output_schema.json`; test it.
2. `AUDIORESEARCH_DB`, `AUDIO_CACHE_DIR` default to `~/Library/Application Support/vinyl-second-brain/` (same folder as `DB_PATH`); `AUDIORESEARCH_LOCAL_AUDIO` defaults to the backend's `AUDIO_DIR`. Move the existing `audio_cache/` (93 MB) and `audioresearch.db` there once, with the owner's OK.
**Done when:** both tools read the same audio folder and nothing audio-related is written inside the repo.

### Step I2: `track_audio` table and the `audio` job
1. Migration: `track_audio` (track_id, status, source, level, quality, confidence, reason, url, page, audio_path, readings JSON, alternatives JSON, run_id, found_at). One row per track; a new run replaces it.
2. `backend/app/audio/job.py`: handler that builds a `ReleaseIdentity` from the record (`identity=`), passes manual links, rejections and assigned files from `vinyl.db`, calls `research()`, maps positions to track ids, stores rows. Injectable `research_fn`.
3. Own queue (second worker) so long audio jobs never block Discogs sync or analysis.
4. Wherever analysis is requested today (intake, `POST /api/records/{id}/analyze`) the request now queues `audio` then `analysis`. Re-analysis skips `audio` when `track_audio` rows exist, unless the request says `refresh_audio`.
**Done when:** with a saved contract JSON, adding a record fills `track_audio` and then queues analysis; analysing again does not call `research`; the e2e server fakes it.

### Step I3: record page and Settings backfill
1. API: `GET /api/records/{id}/audio` (per track: status, source, quality, confidence, reason, page link, alternatives); `POST /api/records/{id}/find-audio`.
2. Record page: per track source, quality badge, confidence, link to the page it came from, and a player built on the rules in `audioresearch/previews.py` (one family per record).
3. Settings: "Find audio and analyse the library" (the library sync option): runs the audio stage, then analysis, for every record that has no `track_audio` yet; resumable, polite delays, skips cached releases, like the styles backfill. Nothing runs on its own.
**Done when:** an analysed record shows audio status; the Settings run works twice with no repeated network calls.

## Phase 2: review in the app

### Step I4: review without the CLI
1. Endpoints and UI: accept, reject (remembered, so reruns skip the URL), paste a link, assign a file, per track. Each stores in `vinyl.db` and reruns that release.
2. Replace `audioresearch/adapters/local_files.py`'s copy of the matching logic with one shared implementation.
3. The `review` CLI stays as a developer tool.
**Done when:** the whole review cycle works with no CLI.

## Phase 3: bpmkey takes audio

### Step I5: measure from given audio
1. `bpmkey.measure(tracks, audio, readings)`: analyses the given files; readings count as votes with a stated reliability; clips (under 60 s) get lower weight (the benchmark used about 2-minute previews, 30 s clips were never measured).
2. The `analysis` job uses `track_audio` paths first; bpmkey's own search runs only if the flag is on and no audio exists.
3. Proposals carry "audio uncertain" when the audio's status is `review` or its quality is `clip`.
**Done when:** analysis works from `track_audio` rows with the fake `research`.

### Step I6: comparison before switching — GATE
Run old and new on about 30 owned records; write `docs/integration_comparison.md` (BPM and key differences, quality used, time). The owner reads it and approves the switch.

## Phase 4: cleanup

### Step I7
Turn bpmkey's own audio search off by default, then delete it once the owner agrees; update the README (Audio files, Layout, bpmkey sections); link the process viewer from the record page.

## Risks

- **Disk and sync:** about 30 MB of audio per release; hence decision 3.
- **Backfill time:** about 1 minute per release; hence the separate queue and the polite, resumable backfill.
- **Site changes:** page readers break (see architecture section 11); adapter health and the viewer show it.
- **Terms of service:** as in the architecture; personal use at low request rates.
