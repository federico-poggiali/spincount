# Cleanup of October 2026, and how to make the app lighter

What the deep cleanup of 2026-10-14 removed, changed and fixed, and a list of next steps for deploying and
selling Spin Count. Start with "Making it lighter" if you come back to this later.

## Making it lighter: next steps

Ordered by size of the win. Sizes are measured in the current `.venv`.

1. **Drop librosa (about 300 MB).** It is only used in `bpmkey/keychroma.py` to compute one chroma vector
   for key detection (`chroma_cqt`). It pulls in llvmlite (125 MB), scipy (97 MB), scikit-learn (49 MB),
   numba (31 MB) and librosa itself (5 MB). Essentia is already installed and has chroma/HPCP. Plan:
   compute the same input with Essentia, check that key accuracy holds on the bpmkey benchmark, then drop
   librosa, numba, llvmlite, scikit-learn and scipy from `requirements.txt` and regenerate the lock.
2. **Rebuild the local venv (about 750 MB).** The current `.venv` still holds torch (587 MB), sympy,
   networkx and pandas from the removed semantic search and benchmark. They are not in
   `requirements.lock.txt` any more, so a fresh `python -m venv .venv && make install` gets rid of them.
   Docker images already install only the lock.
3. **Let bpmkey analyse the audio audioresearch finds.** This was planned in the old integration plan.
   Then bpmkey's own audio search (`bpmkey/analyze.py` downloading, `bpmkey/lookup/`) can go.
4. **Remove the temporary tools.** bpmkey's CLI and web page (:8765), and audioresearch's CLI and viewer
   (:8200), are marked TEMPORARY. Delete them once the app covers debugging; that also removes their
   dependencies from the runtime.
5. **Use one HTTP library.** The engines use `requests` (`bpmkey/discogs.py`, `bpmkey/lookup/base.py`,
   `audioresearch/http.py`); the app uses `httpx` (`backend/app/discogs.py`). Pick one, probably httpx.
6. **Consider making yt-dlp optional (25 MB).** It is only needed for the YouTube audio source.
7. **Before deploying anywhere:** add a login (the app has none), and actually run the Docker files
   (never done; the image was missing `audioresearch/` until this cleanup).
8. **Small leftover:** the `records.status` CHECK constraint still allows `'considering'`. Removing it
   needs a table rebuild; do it in the next migration that rebuilds `records` anyway.

## Tests before and after

| Suite | Before | After |
|---|---|---|
| Backend | 177 passed | 160 passed |
| audioresearch + bpmkey | 130 + 32 passed | 163 passed (1 test added) |
| Frontend unit | 34 passed | 29 passed |
| Playwright e2e (incl. accessibility) | 35 passed | 35 passed |
| Lint / TypeScript | 4 ruff errors | clean |

The missing tests covered removed features. `make test-all` runs everything.

Size of the change: 129 files, about 9,200 lines removed and 900 added. 6,800 of the removed lines are
research leftovers, about 600 net are app code (backend/app 4,664 → 4,344 lines, frontend/src 5,220 →
4,942), and 760 are the generated API schema.

## Removed

Decided by the owner:

- **Research leftovers:** `benchmark/` scripts, `building_plan/`, and the progress/report notes in `docs/`
  (`audioresearch_decisions`, `audioresearch_live_report`, `audioresearch_progress`,
  `integration_progress`, `progress`). bpmkey code that only served the benchmark (legacy key profiles)
  went too. Git history keeps all of it; the local `benchmark/` data folder is now git-ignored.
- **Search by meaning:** `backend/app/embeddings/`, sqlite-vec, the `note_embeddings` table,
  `/api/search/semantic`, `/api/admin/reembed` and the search-mode toggle. Search is exact words only
  (`/api/search/exact`).
- **Status "considering":** merged into wantlist. Statuses are `owned` and `wantlist`; adding a record
  still defaults to wantlist.
- **Side tools:** kept, but marked TEMPORARY (see step 4 above).

Dead code nobody used:

- Endpoints from the removed manual-assign panel: `/api/records/{id}/audio-match`,
  `POST/DELETE /api/tracks/{id}/audio`.
- The backend's copy of the audio-file matcher (`analysis/matching.py`); audioresearch's matcher is used
  through `app/audio/files.py`.
- `analysis/camelot.py` (now `app/keys.py`, built on bpmkey).
- The note `type` column and everything around it (always prose since migration 0008).
- Frontend: `NoteEditor`, QuickNote's hero variant, JobChip's idle/Start state, stale query keys, a
  Settings hint to a non-existent "Audio tab".
- `discogs.remove_from_collection`, `records.list_all`, `tracks.delete`, `crate.cube_label`, duplicate
  request models.

## Restructured

- One `.env` loader and `DATA_DIR` in `bpmkey/config.py`, used by bpmkey, audioresearch and the app.
  bpmkey's cache moved next to the database (Application Support); the old one was copied there.
- `app/deps.py`: shared `require_record`, `library_filters`, `parse_key` and `discogs_errors()`
  (typed `DiscogsBadUrl` instead of matching on error text).
- `app/keys.py`: key name, Camelot conversion and wheel order in one place; `db/_util.now()` for
  timestamps.
- All API models in `schemas.py`; `routes/label_maker.py` merged into `routes/labels.py`.
- Frontend: `useStoredSetting`/`useStoredToggle` and `useDismiss` in `hooks.ts`; `parseBpm` and `plural`
  in `lib.ts`.
- bpmkey tests moved from root `tests/` to `bpmkey/tests/`.
- Packaging: `requirements.txt` (runtime), `requirements.lock.txt` (56 runtime packages),
  `requirements-dev.lock.txt` (tests and lint); `backend/pyproject.toml` no longer duplicates deps.

## Bugs fixed

- Docker image did not copy `audioresearch/`, so the app would crash inside it.
- The runtime lock lacked beautifulsoup4, lxml, mutagen and jsonschema (fresh installs broke) and
  included pandas, mir-eval, tabulate and sqlite-vec for nothing.
- Every Label Maker preview triggered an Obsidian vault rebuild (`READ_ONLY_POSTS` in `main.py`).
- Changing the key notation did not update parts of the page already open.
- The library's two "Clear filters" buttons did different things.

## Database migration

`backend/app/db/migrations/0011_lighter.sql` runs on the next app start: drops the vector table (without
needing sqlite-vec), drops `notes.type`, and turns `considering` records into `wantlist`. Tested on a
copy of the real database: 47 records (42 owned, 5 wantlist) and 7 notes kept, integrity and foreign-key
checks pass. Backup taken first: `backend/backups/vinyl-20261014-235842.db`.

## Left on disk (not in git, safe to delete)

- `benchmark/`: 1.7 GB of local research audio.
- `audio_cache/` (118 MB), `audioresearch.db`, `cache.sqlite` in the repo folder: old caches; the
  databases have copies next to `vinyl.db`.
