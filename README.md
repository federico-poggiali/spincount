# Spin Count

A personal vinyl library for DJs and collectors. Paste a Discogs link: the record and its tracklist land in your
library, the app finds each track's audio, and one button analyses BPM and key (Camelot or musical). Then find
records by tempo, key, tag or style, file them on your real shelf, print sleeve labels, build YouTube playlists,
and keep your Discogs collection in step.

It runs on your own computer: a web app on `localhost`, one SQLite database, no account and no login.

> **Where it is going.** A desktop app for me and a few friends, on macOS and Windows. The plan, in phases:
> tidy the code into one package, move background jobs to their own process, use one audio search for
> everything, replace Essentia (which has no Windows build), then package it as an app.

## Contents

- [Quick start](#quick-start)
- [Where your data lives](#where-your-data-lives)
- [How a record flows](#how-a-record-flows)
- [What it does](#what-it-does)
- [Commands](#commands)
- [Settings](#settings)
- [Project layout](#project-layout)
- [The BPM and key engine](#the-bpm-and-key-engine)
- [Not built yet](#not-built-yet)
- [Credits](#credits)

## Quick start

You need **Python 3.11** (Anaconda is fine) and **conda** or Node 22. You also need a
[Discogs personal token](https://www.discogs.com/settings/developers): click "Generate new token".

```bash
git clone https://github.com/federico-poggiali/spincount.git ~/Code/spincount
cd ~/Code/spincount
make run       # first run: creates .env, .venv (Python) and .nodeenv (Node), builds the web app, starts it
```

Put your token in `.env` (`DISCOGS_TOKEN=...`, and `CONTACT_EMAIL=...` for polite API headers), run `make run`
again, and open <http://127.0.0.1:8000>. Press `n` to add a record and `/` to search.

> **Keep the project out of OneDrive, iCloud Drive or Dropbox.** Sync tools fight with `.git`, `.venv` and the
> SQLite files: they restore deleted files, make "conflict" copies and leave files online-only. On a Mac
> `~/Documents` and `~/Desktop` are often synced, so use a plain folder such as `~/Code`.

## Where your data lives

| What | Where | Notes |
| --- | --- | --- |
| Database (`vinyl.db`) | `DB_PATH` in `.env`, e.g. `~/Library/Application Support/vinyl-second-brain/` | The only place anything is written |
| Caches (`audioresearch.db`, `cache.sqlite`) | Next to the database | Safe to delete; they rebuild |
| Downloaded audio (`audio_cache/`) | Next to the database | Temporary: see [Audio](#audio-and-analysis) |
| Your own rips | `audio/<discogs release id>/` in the project | Never deleted or moved by the app |
| Obsidian vault | `vault/` in the project | Generated, overwritten on every sync |
| YouTube sign-in | `youtube_client.json`, `youtube_token.json`, `youtube_usage.json` next to the database | Private files (0600) |
| Backups | `backend/backups/` | `make backup`, or nightly (see [Commands](#commands)) |

Without `DB_PATH`, the database goes to `backend/data/vinyl.db` in the project.

## How a record flows

```text
 Discogs link
     │
     ▼
 intake ──► record + tracklist in SQLite
     │
     ├─► audio job (runs by itself)    your files ▸ Discogs videos ▸ YouTube ▸ Bandcamp ▸ SoundCloud ▸ iTunes ▸ shops
     │                                 → a player per track; downloads go to audio_cache/
     ├─► Analyse (button)              BPM + key from that audio → proposals
     │        └─► you validate or discard → saved on the tracks; the download is deleted
     ├─► Discogs sync                  owned → your collection, wishlist → wantlist (preview + confirm)
     ├─► YouTube links (if on)         a link per track; you add them to your playlists by hand
     └─► vault sync                    one Obsidian note per record
```

Jobs run one at a time in the background, and each record page shows its progress.

## What it does

### Library and search

The library has two parts: records you **own**, and a **wishlist** for the rest. You can filter by BPM range,
key (musical or Camelot), tags, styles and free text, and a BPM and a key filter must match on the same track.
The **Tracks** view lists every track instead of every record. A BPM or key you type in is marked *manual* and
analysis never overwrites it unless you say so.

### Audio and analysis

Adding a record starts a search for each track's audio. It tries your own files first, then the videos linked
on Discogs, YouTube, Bandcamp, SoundCloud, iTunes and record stores. The record page plays what was found with
the official players or the shop's clip. **Search again** starts the search from scratch.

**Analyse** works out BPM and key from that audio and shows them as proposals; nothing changes until you
**validate** them. Your own rips always win. Upload them on the record page, or drop them in
`audio/<release id>/` named like `A1 - Title.wav`. They are matched to tracks by position, then by title, never
by guess.

**Downloaded audio is temporary.** It is only needed for the analysis, so it is deleted as soon as you validate
or discard that track's result. Analysing the track again downloads it again. Settings → Audio shows how much
is kept and has a **Clear downloaded audio** button, which keeps only the files a track still needs.

### Crate

Draw your real shelf as units of cubes (a 1×4 or 4×4 Kallax, for example), name the cubes, and split them with
dividers. Place records on the Crate page, where the app suggests a spot by style. Each copy of a record can
have its own spot.

### Labels

**Make label** on a record page, or **Make a label** for any Discogs link, produces two 62 × 40 mm labels
(696 × 472 px, 1-bit PNG) for a Brother QL:
- the **main label**: artist, label, cat#, title, a QR code to Discogs, year and styles;
- the **tracks label**: position, BPM, key and tags per track.

Several designs are available. Any field can be edited or hidden for that print only. **Download** saves the
PNGs.

### Discogs sync

Settings → Discogs keeps Spin Count and your Discogs account in step.
- **Import** pulls your collection in as owned records, with no audio search.
- **Adding to Discogs** always shows a preview first, and only the records you confirm are sent.
- Owned records can go to your collection automatically, and wishlist records to your wantlist (both optional).
- A record moved from the wishlist to owned shows under **Recently traded**.
- Nothing is ever removed from Discogs unless you choose it when deleting.
- **Reset** backs up the database first and keeps your wishlist.

### YouTube playlists

This is off by default; switch it on in Settings. Every track then gets a YouTube link: the Discogs video first,
otherwise a yt-dlp search checked by the matcher. **Add to YT playlist** on a record page lets you tick tracks and
pick one of your playlists. Nothing is ever added by itself.

It needs your own Google app, once; Settings walks you through it:
1. Create a project in the [Google Cloud console](https://console.cloud.google.com/) and enable
   **YouTube Data API v3**.
2. Set up the sign-in screen (External) and **Publish app**, so sign-ins don't expire after 7 days. An
   "unverified app" warning when you sign in is expected.
3. Create an OAuth client of type **Desktop app**, paste its ID and secret in Settings, and **Connect YouTube**.

Your project gets 10,000 quota units a day, and adding a video costs 50, so about 200 tracks a day. The app
counts what it spends and shows it in Settings.

### Obsidian vault

Open `vault/` in Obsidian as a vault and enable the **Dataview** plugin. `Records/` has one note per record, and
`Dataview Examples.md` has ready-made queries by BPM, key and tag. The vault is generated output: edits made in
Obsidian are overwritten. Keep your own notes outside `Records/`, or point `VAULT_DIR` into a bigger vault.

## Commands

| Command | What it does |
| --- | --- |
| `make run` | Build and serve on port 8000 (`PORT=8100 make run` for another port) |
| `make run-test` | The same, plus a panel showing background jobs live and how long each search step takes |
| `make dev` + `make frontend-dev` | API with auto-reload, and the Vite dev server on :5173 |
| `make test-all` | Every test: backend, engines, frontend components, browser (`make test`, `test-frontend`, `e2e`) |
| `make lint`, `make coverage` | Ruff and the TypeScript check; a coverage report |
| `make backup` | Copy the database to `backend/backups/` now (safe while the app runs) |
| `deploy/install-nightly-backup.sh` | Back up every night at 03:00 on macOS and keep the newest 14 (`--remove` to undo) |
| `make sync-vault` | Rebuild the Obsidian files now (the app also does it after every change) |
| `make backfill-styles` | Fetch Discogs styles for records added before styles existed |
| `make openapi`, `make types` | Export `docs/openapi.json`, and regenerate the frontend's API types from it |

## Settings

Most settings are in the app (Settings page). `.env` holds the rest (see `.env.example`):

| Key | What |
| --- | --- |
| `DISCOGS_TOKEN` | Your Discogs personal token (required) |
| `CONTACT_EMAIL` | Sent in the User-Agent header to Discogs and the BPM databases |
| `GETSONGBPM_KEY` | Optional key for the GetSongBPM lookup |
| `DB_PATH` | Database file; caches and downloads go next to it |
| `AUDIO_DIR`, `VAULT_DIR` | Your rips and the Obsidian vault (default `audio/` and `vault/`) |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Optional; override the Google app pasted in Settings |

## Project layout

| Folder | What |
| --- | --- |
| `backend/app/` | FastAPI app: routes, SQLite schema and migrations, jobs, labels, Discogs sync, YouTube, vault |
| `backend/tests/` | Backend tests (pytest) |
| `frontend/` | React app; component tests next to the components, browser tests (Playwright) in `e2e/` |
| `audioresearch/` | Finds each track's audio: your files, Discogs videos, YouTube, Bandcamp, SoundCloud, iTunes, shops |
| `bpmkey/` | BPM and key engine; also holds the settings every part shares (`bpmkey/config.py`) |
| `docs/` | `openapi.json` (the frontend's types come from it) and notes such as `cleanup-2026-10.md` |
| `deploy/` | The nightly backup installer |

`Dockerfile` and `docker-compose.yml` exist but **have never been built or run**. `make run` is the supported
way. bpmkey's command line and web page (`python -m bpmkey`, `python -m bpmkey.server`) and audioresearch's
command line and viewer are temporary debugging tools and will be removed.

## The BPM and key engine

`bpmkey/` works out BPM and key from audio.
- **BPM** is a vote between Essentia's `degara` beat tracker, the Percival estimator and an onset tempogram. A
  prior over BPM then picks between half, single and double tempo. It takes about 3 s per track.
- **Key** comes from a small committee: Essentia's `edmm` and `bgate` profiles plus the track's mean chroma vote
  on all 24 keys. It finds major keys, which `edmm` alone never did.

Measured in October 2026 on human-labelled electronic music (GiantSteps datasets). The benchmark data and scripts
have since been deleted:

| | Result |
| --- | --- |
| BPM within ±4% of the hand-checked BPM (GiantSteps Tempo, 661 clips) | 76.7% |
| BPM within ±4% of Beatport's listed BPM (GiantSteps-MTG, 1104 clips) | 91.2% |
| Key, exact match (GiantSteps Key, 604 clips, cross-validated) | 63–64%, with 43% of major keys found |

Almost every BPM error is an octave (×2 or ×½). Key detection from audio alone is the weak spot, and it is
unreliable on atonal or very percussive tracks and on tracks that change key.

Essentia has no Windows build, so it will be replaced with librosa and numpy. The switch is accepted only if the
results on the library's own hand-checked tracks hold up.

## Not built yet

- Printing labels straight to the Brother QL (download the PNGs for now).
- Building sets and playlists by Camelot compatibility.
- Two-way Obsidian sync.
- A login: the app trusts anyone who can reach its port, so keep it on `localhost`.

## Credits

- Release data from the [Discogs API](https://www.discogs.com/developers).
- BPM and key data from [GetSongBPM](https://getsongbpm.com), [Deezer](https://developers.deezer.com) and
  [AcousticBrainz](https://acousticbrainz.org) via [MusicBrainz](https://musicbrainz.org).
- Audio analysis with [Essentia](https://essentia.upf.edu) (AGPL-3.0) and [librosa](https://librosa.org).

A personal project, not affiliated with any of the services above.
