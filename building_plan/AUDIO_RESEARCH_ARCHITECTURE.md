# Audio Research and Matching: Architecture

The full design of the **audio research and matching** tool, in build order: what it does, how the pipeline works, every adapter, and the shared services. The build steps live in `AUDIO_RESEARCH_BUILD_PLAN.md`.

Items marked **[decided]** were validated by the owner. Items marked **[default]** were not decided yet: they are the proposed choice, so building can start, and they are listed again in section 10.

---

## 1. Purpose

Given a record (a Discogs release), find usable audio for each of its tracks, from your own files or from the web, and say how sure we are that it is the right recording.

- **[decided]** The tool is built first, on its own. It is adapted into `bpmkey` later.
- **[decided]** Its scope is audio in general, not only BPM and key. It finds and verifies audio; it does not decide BPM or key.
- **[decided]** Audio can come from three places: your own files, stripped from a video, or found online.
- **[decided]** A later step changes `bpmkey` so it takes audio directly (the output of this tool) instead of a Discogs link.

What it is not: it does not analyse tempo, key or anything else. It returns audio plus evidence. Analysis stays in `bpmkey`.

## 2. Vocabulary

| Term | Meaning |
| --- | --- |
| **Release** | One Discogs release: label, catalogue number, tracklist, durations. The unit of work. |
| **Track** | One entry of the tracklist, identified by its position (`A1`, `B2`). |
| **Level** | One place to look, ranked by how hard the search is. Higher number = harder case. |
| **Adapter** | The code for one level (or one site inside a level). It only searches and fetches. |
| **Candidate** | Something an adapter found that might be a track or a release: a URL plus its metadata. |
| **Quality** | `full` (whole track), `preview` (long excerpt, roughly a minute or more), `clip` (short excerpt). |
| **Reading** | A BPM or key a site shows (Beatport, deejay.de, decks.de). Kept apart from audio. |
| **Audio research** | Finding audio online (levels 1 to 5). |
| **Audio matching** | Matching your own files to tracks (level 0). |

## 3. Architecture overview [decided]

One pipeline. Levels plug into it as adapters.

```
                 ┌──────────────────────────────┐
 Level adapters  │ 1. Identify release           │   Shared services
 ┌────────────┐  │ 2. Search, level by level  ◄──┼─┐ ┌─────────────────┐
 │0 Your files│─►│ 3. Match release, then tracks │ │ │ Cache           │
 │1 Discogs   │  │ 4. Fetch top candidates       │ │ │ Provenance log  │
 │2 Bandcamp  │  │ 5. Verify recording           │ │ │ Rate limits     │
 │3 SoundCloud│  │ 6. Decide and store ──────────┼─┼►│ Review queue    │
 │4 Beatport  │  └──────────────┬───────────────┘ │ │ Fingerprints    │
 │5 Stores    │                 │                 │ │ Adapter health  │
 └────────────┘      found ◄────┴────► unfound ───┘ └─────────────────┘
                (output contract)    (next level)
```

Principles:
1. **Levels are adapters.** An adapter does two things for its site: `search` and `fetch`. Matching, verifying and deciding are written once and shared. A broken site breaks only its own adapter.
2. **Work per release, not per track.** Identify the release once. When a level finds the release, all its tracks are resolved together; only the missing tracks move to the next level.
3. **Search cheap, download late.** Searching reads metadata only. Audio is downloaded only for the few best candidates, after matching.
4. **Quality ladder.** `full` > `preview` > `clip`. A lower-quality find is kept, and may be beaten by a later level. A clip can serve as a reference fingerprint to confirm a full-length candidate from another source.
5. **Level 0 always wins.** Your own files and a link you paste by hand override everything found online.
6. **Nothing fails silently.** Every candidate tried is logged with its score and the reason it was accepted or rejected.

## 4. The pipeline, stage by stage

### Stage 1: Identify the release
Input: a Discogs release URL (or master URL, resolved to its main release).
Output: a `ReleaseIdentity`:
- `discogs_release_id`, `artist`, `title`, `label`, `catno` (catalogue number), `year`
- `tracks`: position, artist (per-track if different), title, duration in seconds (may be missing)
- `videos`: the YouTube links listed on the release

Reuse `bpmkey/discogs.py` (URL parsing, tracklist parsing, `Name (2)` cleanup). Fetched once per release and cached.

### Stage 2: Search, level by level
For the current level, run all its adapters **in parallel** (each level may have more than one, e.g. level 1 has YouTube and iTunes). Each adapter returns `Candidate`s, metadata only:
- `kind`: `release` (a whole release page: album, set, store item) or `track`
- `url`, `title`, `artist`, `duration`, and for `release` candidates their tracklist (positions, titles, durations)
- `quality_hint`: what the adapter expects to fetch (`full`, `preview`, `clip`)
- `readings`: BPM / key shown by the site, if any

Only the tracks still unfound are searched at each level.

### Stage 3: Match release, then tracks
One shared matcher (built on `bpmkey/matching.py`: `norm`, `similarity`, `token_containment`, `version_penalty`, `bracket_penalty`, `score_candidate`, `dynamic_threshold`).

1. **Release match** for `release` candidates: compare the whole tracklist with Discogs. Score from: catalogue number equal (strong), release title and artist similarity, number of tracks, per-track title similarity, per-track duration agreement. A release candidate is accepted only above a release threshold.
2. **Track match** inside an accepted release: by position (`A1` = `A1`), then title and duration. Version words (remix, live, dub, ...) must agree.
3. **Track match** for `track` candidates: `score_candidate` (title, artist, duration), with the `dynamic_threshold` bar that rises when a release's titles are very alike.

Output: for each track, a short ranked list of matched candidates (default: top 3).

### Stage 4: Fetch top candidates
Download audio only for the top-ranked matched candidates, best first, stopping per track once one verifies (stage 5). The adapter that found the candidate does the fetch. Audio is stored in the audio cache (section 7) as the original stream, no re-encoding.

### Stage 5: Verify the recording
A candidate is accepted only if:
1. **Duration** agrees with Discogs within the tolerance (default 6 s for `full`; previews and clips skip this check). Unknown Discogs duration: reject anything over 15 minutes (DJ mixes, full albums).
2. **Not a mix or medley**: reject audio that is far longer than the track or a label "preview medley" of several tracks.
3. **Fingerprint cross-check** when two sources exist for the same track: their Chromaprint fingerprints must align (a clip or preview is aligned against a segment of the full track). Agreement raises confidence; disagreement flags the track for review.

### Stage 6: Decide and store
Per track, pick the best verified candidate: highest quality first, then highest confidence. Record:
- `confidence` 0 to 1, from the match score, verification results and agreement between sources
- `reason`: one line, e.g. `"Bandcamp release matched on catno; fingerprint agrees with Beatport preview"`

Low-confidence results (default below 0.6) go to the review queue. Tracks still unfound go back to stage 2 at the next level. After the last level they are reported `not_found`.

## 5. The levels and their adapters

Order **[decided]**: 0 Your files, 1 Discogs find, 2 Bandcamp, 3 SoundCloud, 4 Beatport, 5 Record stores.

Every adapter implements the same interface:

```python
class Adapter:
    name: str                 # e.g. "bandcamp"
    level: int                # 0-5
    def search(self, release: ReleaseIdentity, tracks: list[TrackRef]) -> list[Candidate]: ...
    def fetch(self, candidate: Candidate, dest: Path) -> FetchedAudio: ...
```

Rules for every adapter:
- No matching logic inside the adapter beyond basic filtering. Return candidates; the shared matcher decides.
- All HTTP through the shared client (rate limits, user agent, retries, health).
- Tests use saved responses (HTML or JSON fixtures). Tests never touch the network.
- Each site that is read from web pages has a small parser module, so a site change is fixed in one place.

### Level 0: Your files [decided]
Two adapters. Always run first; their results always win.
- **`local_files`** (audio matching): files in `audio/<discogs release id>/`, named like `A1 - Title.wav`. Matched by position first, then title. Unmatched files are listed so they can be assigned by hand. Quality: `full`. Reuse the logic in `backend/app/analysis/matching.py` of Spin Count.
- **`manual_link`**: a URL you paste for one track (any site `yt-dlp` can read, or a direct audio URL). Quality as fetched.

### Level 1: Discogs find [decided]
The audio is already on the Discogs release. Two routes **in parallel**.
- **`discogs_youtube`** (route 1b): the YouTube videos linked on the release. Scored with `score_candidate` and `dynamic_threshold` as in `bpmkey/sources/youtube.py`. Fetched with `yt-dlp` (best audio stream, no re-encoding; skip videos over 20 minutes). Quality: `full`.
  - Fallback **`youtube_music`** when no linked video matches: search YouTube Music by artist and title with `ytmusicapi` (unofficial). Fetch with `yt-dlp`. Quality: `full`. **[default]** The Discogs video is used directly when it matches; YouTube Music is searched only on no match.
- **`itunes`** (route 1a): iTunes Search API, artist and title, as in `bpmkey/sources/itunes.py`. No key needed. Quality: `preview` (about 30 s; treat as `clip` if shorter). Future option, not built now: Apple Music API (needs an Apple developer token).

### Level 2: Bandcamp [decided]
Bandcamp only. No public search API, so the adapter reads Bandcamp's public pages.
- **`bandcamp`**: search by artist and release title, albums first, then single tracks. A release candidate carries the album's tracklist and durations, so the release match (stage 3) runs before any track is trusted. Fetch with `yt-dlp` (supports Bandcamp pages). Quality: `full` when the track streams in full; some tracks are preview-only or not streamable, mark them accordingly.

### Level 3: SoundCloud [default, not yet validated]
Two routes in parallel, fetched with `yt-dlp` (no API key; SoundCloud's API registration has been closed for long periods).
- **`soundcloud_tracks`**: search by artist and track title (as `bpmkey/sources/soundcloud.py` does today), scored like YouTube.
- **`soundcloud_sets`**: search sets (albums, playlists) by artist and release title, matched on the whole tracklist like Bandcamp.
Extra care: fan rips, DJ mixes and label preview medleys are common. The duration and mix/medley checks of stage 5 matter most here. Quality: `full` or `preview` depending on the upload.

### Level 4: Beatport [decided]
Two routes in parallel. Beatport's API is partner-only, so the adapter reads its public pages.
- **`beatport_tracks`**: artist and track title. Beatport names the version ("Original Mix", "Dub Mix"), which feeds the version check.
- **`beatport_releases`**: catalogue number or release title; whole tracklist first.
- **Readings [decided]**: Beatport's BPM and key for the track are stored as a reading, separate from the audio.
Quality: `preview` (Beatport plays excerpts, roughly a couple of minutes). Beatport sells digital releases, so vinyl-only records are often missing.

### Level 5: Record stores [default, not yet validated]
One adapter per store, all searched in parallel. Search by **catalogue number first**, then artist and title. Store pages usually label clips by position (`A1`, `B1`), which the track match uses.
- **`deejay_de`** and **`decks_de`**: clips plus the store's BPM, kept as a reading.
- **`hardwax`**, **`clone`**, **`kalahari_oyster_cult`**: clips only.
Quality: `clip` or `preview`, depending on the store. **[default]** Clips are accepted as results, marked `clip`, and are used as reference fingerprints. **[default]** Build one store at a time, starting with `deejay_de`.

## 6. Data model

```python
@dataclass
class TrackRef:            # from Discogs
    position: str
    artist: str
    title: str
    duration: int | None

@dataclass
class ReleaseIdentity:
    discogs_release_id: int
    artist: str
    title: str
    label: str | None
    catno: str | None
    year: int | None
    tracks: list[TrackRef]
    videos: list[dict]

@dataclass
class Candidate:
    adapter: str
    level: int
    kind: str                  # "release" | "track"
    url: str
    title: str
    artist: str
    duration: int | None
    tracklist: list[TrackRef] | None   # for kind == "release"
    quality_hint: str          # "full" | "preview" | "clip"
    readings: list["Reading"]

@dataclass
class Reading:
    source: str                # "beatport", "deejay_de", ...
    bpm: float | None
    key: str | None
```

## 7. Shared services [decided]

| Service | What it does |
| --- | --- |
| **Cache** | SQLite file `audioresearch.db`. Keyed by release: identity, candidates per adapter, decisions. A rerun of the same release does no network calls unless `--refresh`. `not_found` is cached with a date so it can be retried later. |
| **Audio cache** | Downloaded audio kept in `audio_cache/<release id>/<position>.<source>.<ext>` (git-ignored). **[default]** Kept, not deleted, so `bpmkey` can read it later. |
| **Provenance log** | Every candidate tried: adapter, URL, scores, verification results, accepted or rejected and why. Stored in the cache DB, shown in the report. |
| **Rate limits** | Per site: minimum delay between requests (default 1 s; 2 s for record stores), retry with backoff on 429/5xx, one shared `User-Agent` with a contact email. |
| **Review queue** | Tracks below the confidence threshold, or where sources disagree. Listed in the report and in a `review` CLI command; you can accept, reject or paste a manual link (level 0). |
| **Fingerprints** | Chromaprint (`fpcalc`) fingerprints stored per fetched file; an alignment function compares a clip or preview with a full track. Local comparison only, no AcoustID lookup needed. |
| **Adapter health** | Counts consecutive failures per adapter (network errors, parser errors). After a threshold (default 5) the adapter is switched off for the run and reported. |

## 8. Output contract [decided]

What the tool returns for one release, as JSON (CLI) or Python objects (library). `bpmkey` will read only this.

```json
{
  "discogs_release_id": 12345,
  "tracks": [
    {
      "position": "A1",
      "status": "found",            // found | review | not_found
      "audio_path": "audio_cache/12345/A1.bandcamp.mp3",
      "source": "bandcamp",
      "level": 2,
      "url": "https://...",
      "quality": "full",             // full | preview | clip
      "confidence": 0.92,
      "reason": "Bandcamp release matched on tracklist; fingerprint agrees with Beatport preview",
      "readings": [{"source": "beatport", "bpm": 124.0, "key": "A minor"}],
      "alternatives": [ { "source": "beatport", "quality": "preview", "confidence": 0.8, "audio_path": "..." } ]
    }
  ],
  "adapters_off": [],
  "generated_at": "2026-10-13T12:00:00Z"
}
```

## 9. Interfaces

- **CLI**: `python -m audioresearch <discogs url> [--levels 0-5] [--refresh] [--json out.json]`, `python -m audioresearch review <release id>`, `python -m audioresearch report <release id>`.
- **Library**: `research(url_or_id, levels=..., refresh=False) -> ReleaseResult`.
- Lives in the existing repo as a new package `audioresearch/`, next to `bpmkey/`, reusing `bpmkey.discogs` and `bpmkey.matching` without changing them.
- **Run events**: the pipeline emits an event at every level and stage (start, finish, counts, duration) through an optional callback, stored per run in the cache DB.
- **Process viewer (temporary)**: `python -m audioresearch viewer` serves a local page on `127.0.0.1:8200`. Paste a Discogs link and watch each level and stage run live: candidates found, matches, fetched, verified, rejected with reasons, and how long each step took; plus a track-by-level grid and a final summary. It is a debug tool for understanding the process, not part of Spin Count. See build plan Step 6b.

## 10. Open decisions (defaults in use)

| Decision | Default used until you decide |
| --- | --- |
| Level 3 SoundCloud content | As in section 5 |
| Level 5 record stores content | As in section 5 |
| Clips acceptable as results | Yes, marked `clip` |
| Which store first | `deejay_de`, then one at a time |
| YouTube Music step | Discogs video used directly when it matches; YouTube Music only on no match |
| Keep downloaded audio | Yes, in `audio_cache/` |
| Fingerprint method | Chromaprint (`fpcalc`), local alignment |
| Confidence threshold for review | 0.6 |
| What "beyond BPM and key" will analyse | Out of scope for this tool; decided when adapting `bpmkey` |
| The "audio wins" rule | Stays in `bpmkey`; this tool only supplies audio and readings |

## 11. Risks

- **No official APIs** for Bandcamp, Beatport, SoundCloud search, YouTube Music and the record stores: their page readers and `ytmusicapi` can break when sites change. Mitigation: one parser per site, saved fixtures, adapter health.
- **Terms of service**: downloading audio from YouTube, SoundCloud, Bandcamp, Beatport and the stores is likely outside their terms. Personal use, low request rates.
- **Coverage**: vinyl-only and white-label records may exist only at record stores, and only as clips.
- **Site details** (search URLs, clip lengths, where BPM is shown) are from general knowledge and must be checked against the live sites when each adapter is built.
