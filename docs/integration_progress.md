# Integration: progress

## Steps I1 to I3 (first testable slice)
Built:
- **Contract v1**: `contract_version: 1` in `ReleaseResult` JSON and `output_schema.json`; the backend refuses any other version.
- **One storage setting**: with `DB_PATH` in `.env`, audioresearch's database and `audio_cache/` default to the same folder as `vinyl.db` (Application Support), and its level 0 folder defaults to `AUDIO_DIR`. Without `DB_PATH` nothing changes. The old `audio_cache/` (93 MB) and `audioresearch.db` in the repo were not moved: they are only a cache, and new runs write to the new place.
- **`track_audio` table** (migration 0010) and `backend/app/audio/stage.py`: the audio stage calls `audioresearch.research()` and stores each track's result (status, source, level, quality, confidence, reason, link, page, readings, alternatives). It never raises: a failed search is reported in the job result and the analysis goes on.
- **Audio is the first stage of the analysis job** (`analysis/job.py`), so it runs when you press Analyze and nowhere else. Analysing again reuses the audio found; `refresh_audio` searches again. `GET /api/records/{id}/audio`.
- **Settings**: "Find audio and analyse the library" queues an analysis job for every record with tracks and no audio search yet (`POST /api/admin/find-audio-and-analyse`); running it again only continues where it stopped.
- **Record page, Audio tab**: a "found audio" panel (per track: found / needs a look / not found, source, quality, confidence, link to the page it came from, the shop's BPM when there is one) and "Search for audio again and analyse".
- Tests: 7 new backend tests (`test_audio.py`, the research function is injected), one new browser flow (the e2e server fakes the research with a saved-shape contract), the whole browser suite and the accessibility checks pass. Checked once for real: release 249504, 18 s, track A found (full, 0.875).

Differences from the plan:
- Audio is a **stage inside the analysis job**, not a second job on its own queue. A library run therefore blocks the one job worker (and Discogs syncs queued behind it) until it finishes. A separate queue is still to do before running it on a big library.
- **Analysis does not use the audio yet.** BPM and key still come from bpmkey exactly as before (its own online lookup and audio search). That is Phase 3 (steps I5 and I6); until then the found audio is only shown, not analysed.
- Not built yet: playing the audio in the app, accept / reject / paste a link / assign a file (Phase 2, step I4). Your own files in `audio/<release id>/` are found by level 0 as before.
- Step I1's two open questions were settled by default: the 0.62 confidence (no Discogs durations) is kept as it is, and the old cache stays where it is.

## Audio on add, and the viewer's results in the app
The owner changed rule 1: audio is found **by itself when a record is added**; analysis stays a button.
- **`audio` job** (`backend/app/audio/job.py`): finds audio only, never BPM or key. Intake queues it for every new record (`jobs: {"audio": id}`); the record page shows a "Finding audio" chip. A failure fails the job (Retry), unlike inside analysis where it is only reported. The analysis job still searches first, but only when no audio was found yet.
- **Results like the viewer**: `GET /api/records/{id}/audio` now returns `{tracks, previews}`, where `previews` is audioresearch's own plan (`audioresearch/previews.py`, built from the stored rows, so the app and the viewer pick the same links). The Audio tab shows a play button per track, the source family (YouTube, Bandcamp, SoundCloud, iTunes, a store, your files), quality, "needs a look", how sure, "Find at <store>" links, "Open" to the source page, "Play record", and a docked player (official YouTube / SoundCloud / Bandcamp embeds; store clips and iTunes previews in an audio element; clips roll on to the next track).
- **Playback helpers**: `GET /api/tracks/{id}/audio-file` plays your own files (only files level 0 matched, and only inside `AUDIO_DIR`); `GET /api/audio/bandcamp-embed?url=` gives the id Bandcamp's player needs (bandcamp.com links only).
- **Search again**: `POST /api/records/{id}/find-audio` (`refresh`), the "Search again" button.
- **Settings**: "Find audio for the library" (`POST /api/admin/find-audio`) queues `audio` jobs, not analysis.
- Tests: 172 backend (new: audio job, reuse by analysis, preview plan, store pages, file serving limited to the audio folder, Bandcamp link check), 35 browser (the audio flow now adds a record, waits for the automatic search, checks the rows and plays a YouTube track in the docked player).
- Not checked in a real browser with real embeds: the e2e test only checks the player's iframe address. The Bandcamp embed endpoint is the viewer's code, not run against a live page here.
- Still true: one job worker, so a new record's audio search (about a minute) delays anything queued after it, including an "Analyse" pressed straight away (which then reuses the audio).
