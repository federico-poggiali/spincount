import { useQuery } from "@tanstack/react-query";
import { api, type RecordDetail } from "../api/api";
import styles from "./AudioFoundPanel.module.css";

const QUALITY: Record<string, string> = { full: "full track", preview: "preview", clip: "short clip" };
const WORD: Record<string, string> = { found: "found", review: "needs a look", not_found: "not found" };

/** What audioresearch found for each track: where, how good, how sure. It runs as the first step of analysis. */
export function AudioFoundPanel({ record, busy, onSearchAgain }: { record: RecordDetail; busy: boolean; onSearchAgain: () => void }) {
  const found = useQuery({ queryKey: ["record-audio", record.id], queryFn: () => api.recordAudio(record.id), meta: { quiet: true } });
  const byTrack = new Map((found.data ?? []).map((a) => [a.track_id, a]));
  const searched = byTrack.size > 0;
  const counts = { found: 0, review: 0, not_found: 0 };
  byTrack.forEach((a) => { counts[a.status] += 1; });

  return (
    <section className={styles.panel} aria-label="Found audio" data-testid="found-audio">
      <div className={styles.head}>
        <span className="micro">found audio</span>
        <span className={styles.count}>
          {searched ? `${counts.found} found · ${counts.review} need a look · ${counts.not_found} not found` : "not searched yet"}
        </span>
      </div>
      {!searched && (
        <p className={styles.note}>
          Audio is searched for as the first step of analysis (your own files, YouTube, Bandcamp, SoundCloud, record stores). Analyse
          this record and the result appears here.
        </p>
      )}
      {searched && (
        <ul className={styles.list}>
          {record.tracks.map((t) => {
            const a = byTrack.get(t.id);
            if (!a) return null;
            const bpm = a.readings.find((r) => typeof r.bpm === "number")?.bpm as number | undefined;
            return (
              <li key={t.id} data-testid={`found-audio-${t.position}`}>
                <span className={styles.pos}>{t.position}</span>
                <span className={styles.what}>
                  <b>{t.title}</b>
                  <small>{a.reason || WORD[a.status]}</small>
                </span>
                <span className={styles.meta}>
                  <span className={styles[a.status]}>{WORD[a.status]}</span>
                  {a.source && <small>{a.source.replace(/_/g, " ")}{a.quality ? ` · ${QUALITY[a.quality]}` : ""}{a.confidence != null ? ` · ${Math.round(a.confidence * 100)}%` : ""}{bpm ? ` · shop BPM ${bpm}` : ""}</small>}
                </span>
                {(a.page || a.url) ? <a className="ghost" href={(a.page || a.url)!} target="_blank" rel="noreferrer">Open</a> : <span />}
              </li>
            );
          })}
        </ul>
      )}
      <div>
        <button className="ghost" onClick={onSearchAgain} disabled={busy}>{busy ? "Working…" : "Search for audio again and analyse"}</button>
      </div>
    </section>
  );
}
