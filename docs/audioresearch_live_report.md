# Audio research: live report (Step 17)

Run on 2026-10-13, all levels (0 to 5), 16 releases taken from your Spin Count library (read-only), chosen to cover: a mainstream album, vinyl-only 12"s, a white label, compilations, a test pressing, a 4xLP, 2025 releases, and records with several mixes of one song. You can replace this sample with your own list of links and rerun: `python -m audioresearch research <link> --json out.json`.
Whole run: about 15 minutes, 494 MB of audio downloaded (kept in `audio_cache/`; the report run used a scratch folder).

## Result

87 tracks: **73 found, 3 review, 11 not found.**

| Level / source | Tracks resolved | Quality |
| --- | --- | --- |
| 1 Discogs video | 41 | full |
| 1 YouTube Music | 13 | full |
| 1 iTunes | 3 | clip (30 s) |
| 2 Bandcamp album | 10 | full |
| 2 Bandcamp track | 6 | 5 full, 1 preview |
| 3 SoundCloud set | 3 | clip (30 s snippets) |
| 4 Beatport | 0 | off (no token) |
| 5 Record stores | 0 | not needed: everything the stores could have given was found earlier, or not in the stores |

Level 5 never got to resolve a track in this sample. It is also untested end to end on a real record (its parsers are tested on real pages, and a live catalogue-number search works).

## Per release

| Release | Found | Review | Not found | Notes |
| --- | --- | --- | --- | --- |
| Beach House, Teen Dream (2168824) | 18 | 2 | 0 | 9 album tracks via the Bandcamp album match (full, durations agree). The DVD tracks (DVD-n) came from YouTube Music and Bandcamp tracks: they are the album recordings, not necessarily the DVD versions. 2 DVD tracks flagged because the fingerprints of two sources disagree. |
| Cabaret Voltaire, The Conversation (144347) | 9 | 0 | 4 | "Project 80.1/80.2/80.3/80.4" (sides E to H) not found anywhere. |
| Lucky People Center, Interspecies Communication (511533) | 9 | 0 | 0 | 3 tracks are only 30 s SoundCloud snippets (clip). |
| Cyrus, Enforcement (1074215) | 1 | 0 | 2 | A found as a Bandcamp preview; the two mixes (Mills Mix, Recall) not found. |
| Surefoot, Slippery Mitts (12952) | 0 | 0 | 2 | Original Version / Ian Void Rework not found. |
| Levon Vincent, WKO (white label) (15687920) | 2 | 0 | 0 | |
| Various, Modes Of Communication 2 (84153) | 6 | 1 | 0 | Tantalus (C1) in review: the two sources disagree. |
| Various Artists, Elektropia EP (11736205) | 4 | 0 | 0 | |
| Neurø, Guidance / Paradigm / Synaesthesia (215083) | 3 | 0 | 0 | Found at low confidence (0.62): no Discogs durations. |
| Ricardo Villalobos, Salvador Part II/III (35041163) | 2 | 0 | 0 | |
| Driven By Attraction, Tadan (29060320) | 6 | 0 | 0 | |
| Barker, Stochastic Drift (33743922) | 8 | 0 | 0 | All via the linked videos at 0.62 (no Discogs durations: nothing to check the length against). |
| Maurizio, M4.5 (1074062) | 0 | 0 | 2 | Both tracks are titled "Untitled": nothing to search for. |
| Problematic, Electrify Me (test pressing) (33239529) | 1 | 0 | 1 | B side not found. |
| Shkedul, Natural Goofy, Uxementale EP (36268936) | 2 | 0 | 0 | |
| Barcellona 2000, Guitara Del Cielo (549217) | 2 | 0 | 0 | |

## Not found, with the reason

- Maurizio M4.5 (A, B): titles are just "Untitled"; the search has nothing to go on. Would need the catalogue number or a manual link.
- Surefoot (A, B), Cyrus B1/B2, Cabaret Voltaire E to H, Problematic B: no candidate matched at any level. Typical for old vinyl-only mixes; the stores (level 5) were searched only when level 1 to 4 had not found the track, and did not have them either, but see "what to check" below.

## Tracks in review

Beach House DVD-5 (10 Mile Stereo) and DVD-7 (Lover Of Mine), Modes Of Communication C1 (Tantalus): the fingerprint of one source disagrees with another (for example Bandcamp full track against an iTunes clip or a YouTube Music upload). This is the cross-check working; open them with `python -m audioresearch review <release id>`.

## Adapters that failed or need a fix

1. **Beatport (level 4): off in every run** (8 of 16 runs reached it). beatport.com is behind a Cloudflare challenge and the API needs a token. Needs your decision: supply `BEATPORT_TOKEN`, or drop level 4 (see Step 15 in the progress notes).
2. **decks_de and clone (level 5): off by default**, Cloudflare. **kalahari_oyster_cult: not built**, no address found.
3. **YouTube 403 errors:** 8 downloads failed with `HTTP Error 403: Forbidden` (6 on the linked videos, 2 on YouTube Music), in the Beach House run. The next candidate was used each time, so no track was lost, but if the 403s become frequent yt-dlp needs updating or a cookie setup. Failures are counted per adapter and 5 in a row would switch it off.
4. **Missing Discogs durations** are the main weakness: 20 of the found tracks have no duration to check the audio length against, so their confidence tops out around 0.62 to 0.65 and a wrong video of a similar title could pass. A later step could take the duration from Bandcamp/stores instead.
5. **Bandcamp track search found a "preview"** for Cyrus A with no duration to confirm; worth listening to.

## What to check by ear

- Cyrus A (Bandcamp preview) and the 0.62-confidence tracks (Barker, Neurø, Villalobos B).
- Beach House DVD-n tracks: are album recordings acceptable for DVD tracks?
- That the fingerprint thresholds (agree 0.70, disagree 0.63) flag the right pairs; the 3 review cases are good test material.

## Possible next steps (new steps, not done)

1. Decide Beatport (token or drop) and the missing store addresses.
2. Use durations from found sources to verify tracks with none in Discogs.
3. Move `audio_cache/` outside OneDrive (set `AUDIO_CACHE_DIR`): downloads are large and the repo folder is synced.
4. Allow assigning an unmatched local file to a track by hand.
