# Spin Count

A personal vinyl library. Paste a Discogs link and the record, its tracklist, and every track's BPM and key
(Camelot or musical) land in your library; add notes and tags, find records by tempo, key or tag, and read the
whole collection in Obsidian. The BPM and key come from [bpmkey](#bpmkey-the-bpm-and-key-lookup-engine), below.

```
Discogs link ──> intake ──> SQLite (the only place anything is written)
                   │            ├── audio job:    find each track's audio via audioresearch (on add)
                   │            ├── analysis job: BPM + key via bpmkey, proposed for you to validate
                   │            ├── Discogs job:  add to your collection    (owned records only)
                   │            └── vault sync:   generated Obsidian files  (overwritten each sync)
                   └──> web app (React) on the same port as the API (FastAPI)
```

## Run it

You need Python 3.11 (Anaconda is fine) and, once, a [Discogs personal token](https://www.discogs.com/settings/developers)
("Generate new token"). Then, in this folder:

```bash
make run          # first time: creates .env, the Python env (.venv), a Node env (.nodeenv), builds, serves
```

Put your token in `.env` (`DISCOGS_TOKEN=...`, and `CONTACT_EMAIL=...` for polite API headers), run `make run` again,
and open <http://127.0.0.1:8000>. Press `n` to add a record, `/` to search. The server listens on localhost only and
has no login, so do not expose the port.

| Command | What it does |
| --- | --- |
| `make run` | build the app and serve it on port 8000 (`PORT=8100 make run` to change) |
| `make dev` + `make frontend-dev` | API with auto-reload, and the Vite dev server on :5173 with live reload |
| `make test-all` | every Python suite, frontend component tests, browser tests (`make test`, `make test-frontend`, `make e2e`) |
| `make lint`, `make coverage` | ruff and the TypeScript check, and a coverage report |
| `make backup` | copy the database to `backend/backups/` now |
| `make sync-vault` | rebuild the Obsidian files now (the app also does this a couple of seconds after any change) |
| `make backfill-styles` | fetch Discogs styles (and catalogue number, year if missing) for records added before styles existed; calls Discogs once per record |
| `make openapi`, `make types` | re-export `docs/openapi.json`, and regenerate the frontend's API types from it |

The database lives at `DB_PATH` (default `backend/data/vinyl.db`; better outside a synced folder, e.g. Application
Support), and the lookup and audio caches go next to it. Your audio is in `audio/`, the Obsidian files in `vault/`.
Paths and other settings are in `.env` (see `.env.example`).

## Obsidian

Open the `vault/` folder as a vault (Obsidian: *Open folder as vault*) and enable the **Dataview** community plugin.
`Records/` holds one note per record with its BPM range, keys, tags, tracklist and notes in the frontmatter and body;
`Dataview Examples.md` has ready-made queries by BPM, key and tag.

The vault is **generated output**. Edits made in Obsidian are overwritten on the next sync, because the database is the
only place anything is written. Your own notes in `Records/` are never deleted (only files the app generated are).
To keep your own Obsidian notes, put them outside `Records/`, or point `VAULT_DIR` at a folder inside a bigger vault.

## Labels

On a record page, **Make label** opens a preview and editor for two 62 × 40 mm labels (696 × 472 px, 1-bit PNG, ready
for a Brother QL with 62 mm tape): the **main label** (artist, label and cat#, title, a QR code to the Discogs page, year,
country, styles and a one-sentence note) and the **tracks label** (per side a black block, then position, BPM, Camelot
key, tags and the track note; a long tracklist continues on a second label). Every field can be edited or hidden with
its tick, tracks can be skipped, and the preview warns when text had to be cut. Edits are for that print only: the
record is not changed. Country is not stored anywhere, so type it in if you want it. **Download** saves the PNGs;
printing straight to the Brother (`brother_ql`) is not wired in yet.

## Audio

Adding a record starts a search for each track's audio (your own files first, then Discogs videos, iTunes, Bandcamp,
SoundCloud and record stores); the record page plays what was found. BPM and key do not need it: bpmkey looks them
up online and, when the databases disagree, finds and analyses audio itself.

Your own rips win over everything: use **Upload audio** on the record page, or drop them in `audio/<discogs release
id>/` (the number in the Discogs URL), named like `A1 - Title.wav`. They are matched to tracks by position, then by
title (never by guess), and their analysis **overrides** the lookup. Analysis results wait for you to validate them;
a BPM or key you enter by hand is marked *manual* and is never overwritten unless you say so (the x unlocks it).

## Add to YT playlist

Off by default; switch it on in Settings. Every track of a record you add is then looked up on YouTube (the videos
linked on Discogs first, then a yt-dlp search checked by the matcher; links only, no quota). **Find YouTube for the
library** does the records you already have. On a record page, **Add to YT playlist** lets you tick tracks and pick
one of your playlists; videos already in it are skipped. Nothing is added to YouTube by itself.

Connecting your account needs your own Google app (an OAuth client), once. Settings walks you through it, each step
with a button to its Google Cloud page:

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Under *Google Auth Platform*, set up the sign-in screen (External), then **Publish app** so its status is
   **In production** (in *Testing*, Google ends the sign-in every 7 days). You will see an "unverified app" warning
   when you sign in: that is expected for your own client.
3. Create an OAuth client of type **Desktop app**, paste its client ID and secret in Settings (they are checked with
   Google, then kept in `youtube_client.json` next to the database, readable only by you), and **Connect YouTube**.
   `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` in `.env` still work, and win over Settings.

The token is kept in `youtube_token.json` next to the database. Your own project has its own quota: 10,000 units a
day, and adding one video costs 50, so about 200 tracks a day. Google has no API for the quota left, so Spin Count
counts the units it spends (`youtube_usage.json`) and shows them in Settings and on the record panel; the count resets
at midnight Pacific time, like Google's.

## Backups

`make backup` writes a consistent, timestamped copy of the database to `backend/backups/` (safe while the app runs).
For a nightly backup at 03:00 on macOS (runs at wake-up if the Mac was asleep; keeps the newest 14):

```bash
deploy/install-nightly-backup.sh            # install
deploy/install-nightly-backup.sh --remove   # uninstall
```

## Docker (untested)

`Dockerfile` and `docker-compose.yml` are provided for running on a server or NAS. **They have never been built or run**:
Docker was not available where this was developed. `make run` is the supported way.

## Not built yet

- Printing labels straight to the Brother QL (labels can be downloaded as PNG today).
- Two-way Obsidian sync, playlist and set building by Camelot compatibility.
- BPM and key from the audio the app found (today bpmkey still searches audio on its own).

## Layout

| Folder | What |
| --- | --- |
| `backend/` | FastAPI app (`app/`): routes, SQLite schema and migrations, jobs, labels, vault; tests in `tests/` |
| `frontend/` | React app; component tests next to the components, browser tests in `e2e/` |
| `bpmkey/` | BPM and key engine (below); also holds the settings every part shares (`bpmkey/config.py`) |
| `audioresearch/` | Finds each track's audio: your files, Discogs videos, iTunes, Bandcamp, SoundCloud, stores |
| `docs/openapi.json` | The API schema; the frontend's types are generated from it (`make types`) |
| `docs/cleanup-2026-10.md` | What the October 2026 cleanup removed, and next steps to make the app lighter |
| `audio/`, `vault/` | Your audio files, and the generated Obsidian vault |

Temporary, kept only for debugging and to be removed once the app covers them: bpmkey's command line and web page
(`python -m bpmkey`, `python -m bpmkey.server`) and audioresearch's command line and process viewer
(`python -m audioresearch`, `... viewer`).

---

# bpmkey (the BPM and key lookup engine)

A personal tool that takes a [Discogs](https://www.discogs.com) release link and returns the **BPM** and **musical key (Camelot notation)** for every track.

It looks values up online first, compares the sources, and only analyses the audio when the online results are missing or disagree.

## Status

- [x] Discogs release URL → tracklist and YouTube videos
- [x] Audio sources: Discogs videos → YouTube search → SoundCloud → iTunes 30 s preview
- [x] Online BPM/key lookup: GetSongBPM, Deezer, AcousticBrainz
- [x] Audio analysis fallback: yt-dlp + Essentia (BPM, EDM key profile)
- [x] Camelot conversion, reconciliation, SQLite cache, CSV export

## Usage (temporary: the app is the way to use it)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your Discogs token, GetSongBPM key and contact email
python -m bpmkey https://www.discogs.com/release/10296528        # command line
python -m bpmkey.server                                           # local web UI on http://127.0.0.1:8765
```

CLI options: `--no-analyze` (online lookups only), `--refresh` (redo online lookups, keep cached audio analysis), `--reanalyze` (redo everything), `--csv out.csv`, `--tracks-only`, `-v`.
The web UI also accepts `?url=<discogs link>` to start straight away.

Tracks are marked `agreed` when sources agree, `analyzed` when the audio analysis overruled or replaced the online values, `single` when only one source answered, and `conflict`/`none` otherwise.

## How it works

1. Look the track up in GetSongBPM, Deezer and AcousticBrainz. Every hit is checked against the artist and title, because these APIs happily return unrelated songs (and remixes of the right one).
2. If BPM and key are confirmed by at least two sources, stop.
3. Otherwise find the audio (Discogs videos, YouTube search, SoundCloud, iTunes preview as a last resort), matched by title and duration, and analyze it.
4. Audio gives a BPM and a probability for each of the 24 keys. Each database key then counts as a witness that is right about half the time (GetSongBPM 0.5, AcousticBrainz 0.35) and, when wrong, usually lands on a relative, parallel or fifth-neighbour key. A close audio call is easily tipped, a confident one needs two agreeing databases.

## Accuracy

Measured against human-labelled electronic music (Beatport previews; audio not included in this repo):

| | result |
|---|---|
| BPM, within ±4% of the hand-checked BPM (GiantSteps Tempo, 661 clips) | 76.7% (was 62.5%) |
| BPM, within ±4% of Beatport's listed BPM (GiantSteps-MTG, 1104 clips) | 91.2% (was 94.4%) |
| Key, exact match, shipped committee detector (GiantSteps Key, 604 clips, cross-validated) | 63-64% exact; 43% of major keys found |
| Key, exact match, Essentia `edmm` profile alone (same clips) | 65% (weighted MIREX score 0.70); 0% of major keys found |
| Key, exact match, Essentia `bgate` profile (same clips) | 61% (0.68) |
| Key, exact match, Essentia `edma` profile (same clips) | 58% (0.65) |
| Key, exact match, classical Krumhansl profile (same clips) | 49% (0.59) |

Key detection is a small committee (`bpmkey/keydetect.py`): Essentia's `edmm` and `bgate` profiles plus the track's mean chroma vote on all 24 keys, with weights fitted on GiantSteps. It replaced `edmm` alone because `edmm` can only answer minor: on GiantSteps it never produced a major key, so the 15% of clips that are major were always wrong, and a database saying "major" could never overrule it. The committee finds about 4 in 10 of the major keys at the same overall exact accuracy, and its probabilities are better calibrated (log-loss 1.59 to 1.31). Major vs minor stays the hardest call (mode AUC 0.78). `MODE_PRIOR_SHIFT` in `keydetect.py` sets how readily it says major: GiantSteps is 85% minor, so 0 keeps that prior (66% exact, 23% of majors found) and the shipped 1.0 assumes a mixed collection (63-64% exact, 43% of majors). The database reliabilities were estimated from a handful of tracks and the database-combination gains were simulated, so treat both as unverified until measured against labelled tracks from a real collection. The benchmark scripts and report were removed from the repo to keep it light; they are in the git history (before October 2026).

BPM is a vote (`bpmkey/tempo.py`): Essentia's `degara` beat tracker and Percival estimator plus the onset tempogram vote on a tempo, and a log-normal prior over BPM picks between half, single and double. It replaced RhythmExtractor2013 `multifeature` folded into 70-180, and runs in about 3 s per full track instead of 3-5 s. Almost every error is an octave (x2, x1/2) and the two test sets disagree on octaves for some genres (drum & bass is ~174 in GiantSteps Tempo, ~88 in Beatport's listings), so the default prior is a compromise between them; `analyze_file(path, bpm_prior=...)` takes a narrower one, e.g. `tempo.fit_prior` over your own BPMs for the record's style. Beat This! (a neural beat tracker) was tried and dropped: 86% on the Beatport set it had not trained on, and it needs PyTorch.

Key detection by audio alone is the weak spot, so the database votes matter. A 90% exact-key target is not realistic for any current method.

## Known limitations

- Half/double tempo is ambiguous for some genres (e.g. footwork at 80 vs 160 BPM); until a style prior from your own BPMs is passed in, the default prior decides.
- Key detection is unreliable on atonal or heavily percussive music, and on tracks that change key.
- YouTube sometimes blocks downloads (403 or age-gating); the next source is tried automatically.
- Bandcamp is not used: its search is behind a bot challenge, and following artist and label pages found nothing on 7 tracks YouTube had missed, at about 20 s per track, before it was rate-limited.

## Data sources and credits

- BPM and key data provided by [GetSongBPM](https://getsongbpm.com).
- Release metadata from the [Discogs API](https://www.discogs.com/developers).
- Additional BPM data from [Deezer](https://developers.deezer.com) and [AcousticBrainz](https://acousticbrainz.org) via [MusicBrainz](https://musicbrainz.org).

This is a personal project and is not affiliated with any of the services above.
