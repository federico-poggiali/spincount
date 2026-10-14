# Audio research: decisions (Step 0)

Confirmed by the owner on 2026-10-13: "all defaults".

| # | Question | Answer | Default? |
|---|----------|--------|----------|
| 1 | Level 3 SoundCloud content | `scsearch` by track + set search; DJ mixes and preview medleys rejected | yes |
| 2 | Level 5 record stores content | As in architecture section 5 | yes |
| 3 | Clips count as results | Yes, marked `clip`, used as reference fingerprints | yes |
| 4 | First store | `deejay_de`, then one store at a time | yes |
| 6 | Keep downloaded audio | Yes, in `audio_cache/` | yes |
| 7 | Fingerprint method | Chromaprint (`fpcalc`), local alignment | yes |
| 8 | Review threshold | 0.6 | yes |
| 9 | "Beyond BPM and key" | Out of scope for this tool | yes |
| 10 | "Audio wins" rule | Stays in `bpmkey` | yes |
| 11 | Tool setup (`fpcalc`, `ffmpeg`, `yt-dlp`, Python 3.11) | Not answered explicitly; none installed at Step 0. Assumed: install via Homebrew when a step needs them | assumed |
| 12 | Plan files in `building_plan/` | Copied there | yes |

## Integration with Spin Count (2026-10-14)
Decisions are in `building_plan/INTEGRATION_BUILD_PLAN.md`: audio research only as the first stage of analysis (on add-then-analyse or Analyze; never alone on add), plus a Settings option to run it for the whole library, audio shown directly, cache in Application Support, bpmkey CLI and web page kept for now.
