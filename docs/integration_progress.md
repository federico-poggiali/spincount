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
