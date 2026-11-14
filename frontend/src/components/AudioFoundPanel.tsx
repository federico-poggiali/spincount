import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type RecordAudio, type RecordDetail, type TrackAudio } from "../api/api";
import styles from "./AudioFoundPanel.module.css";

/** One playable link of a track, as chosen by audioresearch's preview plan (same rules as its viewer). */
type Option = { source: string; url: string | null; quality: string | null; confidence: number; review: boolean; family: string; kind: "youtube" | "bandcamp" | "soundcloud" | "audio" | "file"; embed_id?: string };
type Plan = { tracks: Record<string, Option | null>; families: { family: string; tracks: string[] }[]; stores: Record<string, { source: string; page: string }[]> };

const FAMILY: Record<string, string> = { youtube: "YouTube", bandcamp: "Bandcamp", soundcloud: "SoundCloud", itunes: "iTunes", "your files": "Your files" };
const STORES: Record<string, string> = { deejay_de: "deejay.de", hardwax: "Hard Wax", redeye: "Redeye", decks_de: "Decks", clone: "Clone", soundmetaphors: "Sound Metaphors", one_eye_witness: "One Eye Witness", smallblackdots: "Small Black Dots", runas: "Runas", orbitwax: "Orbit Wax" };
const familyName = (f: string) => FAMILY[f] ?? STORES[f] ?? f;
const WORD: Record<TrackAudio["status"], string> = { found: "found", review: "needs a look", not_found: "not found" };

type Now = { pos: string; kind: Option["kind"]; playing: boolean; dock: string | null; label: string };

/** What audioresearch found for each track, playable in the page: one play button per track, the record's
    sources picked so it sounds like one source. Audio is searched for when a record is added. */
export function AudioFoundPanel({ record, busy, onSearchAgain }: { record: RecordDetail; busy: boolean; onSearchAgain: () => void }) {
  const found = useQuery({ queryKey: ["record-audio", record.id], queryFn: () => api.recordAudio(record.id), meta: { quiet: true } });
  const data = found.data as RecordAudio | undefined;
  const plan = (data?.previews ?? { tracks: {}, families: [], stores: {} }) as Plan;
  const byTrack = new Map((data?.tracks ?? []).map((a) => [a.track_id, a]));
  const order = record.tracks.map((t) => t.position).filter((p) => plan.tracks[p]);
  const idOf = (pos: string) => record.tracks.find((t) => t.position === pos)?.id;

  const audio = useRef<HTMLAudioElement | null>(null);
  const frame = useRef<HTMLIFrameElement | null>(null);
  const [now, setNow] = useState<Now | null>(null);

  const stop = useCallback(() => { audio.current?.pause(); audio.current?.removeAttribute("src"); setNow(null); }, []);
  useEffect(() => stop, [stop, record.id]);

  const command = (play: boolean) => {   // YouTube and SoundCloud players take commands by postMessage
    if (!frame.current?.contentWindow || !now) return;
    const msg = now.kind === "youtube" ? { event: "command", func: play ? "playVideo" : "pauseVideo", args: [] } : { method: play ? "play" : "pause" };
    frame.current.contentWindow.postMessage(JSON.stringify(msg), "*");
  };

  const play = async (pos: string) => {
    const o = plan.tracks[pos];
    if (!o) return;
    if (now?.pos === pos) {   // same track: pause / resume
      const playing = !now.playing;
      if (now.kind === "audio" || now.kind === "file") { if (playing) audio.current?.play(); else audio.current?.pause(); }
      else if (now.kind === "bandcamp") { if (!playing) return stop(); }   // no API: closing stops it
      else command(playing);
      return setNow({ ...now, playing });
    }
    stop();
    const label = `${pos} · ${familyName(o.family)}${o.review ? " · needs a look" : ""}`;
    if (o.kind === "audio" || o.kind === "file") {
      const el = audio.current!;
      el.src = o.kind === "file" ? api.audioFileUrl(idOf(pos)!) : o.url!;
      setNow({ pos, kind: o.kind, playing: true, dock: null, label });
      el.play().catch(() => setNow((n) => (n && n.pos === pos ? { ...n, playing: false } : n)));
    } else if (o.kind === "youtube") {
      setNow({ pos, kind: o.kind, playing: true, label, dock: `https://www.youtube-nocookie.com/embed/${encodeURIComponent(o.embed_id ?? "")}?autoplay=1&enablejsapi=1&rel=0` });
    } else if (o.kind === "soundcloud") {
      setNow({ pos, kind: o.kind, playing: true, label, dock: `https://w.soundcloud.com/player/?url=${encodeURIComponent(o.url ?? "")}&auto_play=true&visual=false&show_artwork=false&show_comments=false&hide_related=true` });
    } else if (o.kind === "bandcamp") {
      setNow({ pos, kind: o.kind, playing: true, label, dock: "" });
      try {
        const b = await api.bandcampEmbed(o.url!);
        setNow((n) => (n?.pos === pos ? { ...n, dock: `https://bandcamp.com/EmbeddedPlayer/${b.kind}=${b.id}/size=small/transparent=true/` } : n));
      } catch {
        setNow((n) => (n?.pos === pos ? { ...n, dock: null, label: `${label} · player unavailable` } : n));
      }
    }
  };

  const onEnded = () => {   // clips roll on to the next track that has a preview
    const next = now ? order[order.indexOf(now.pos) + 1] : undefined;
    if (next) void play(next); else setNow((n) => (n ? { ...n, playing: false } : n));
  };

  const searched = byTrack.size > 0;
  const counts = { found: 0, review: 0, not_found: 0 };
  byTrack.forEach((a) => { counts[a.status] += 1; });
  const height = now?.kind === "youtube" ? 200 : now?.kind === "bandcamp" ? 42 : 20;

  return (
    <section className={styles.panel} aria-label="Found audio" data-testid="found-audio">
      <div className={styles.head}>
        <div>
          <span className="micro">found audio</span>
          <p className={styles.count} data-testid="found-audio-counts">
            {searched ? `${counts.found} found · ${counts.review} need a look · ${counts.not_found} not found · ${order.length} of ${record.tracks.length} playable` : busy ? "searching…" : "not searched yet"}
          </p>
        </div>
        <div className={styles.actions}>
          {order.length > 0 && <button className="primary" onClick={() => play(order[0])}>▶ Play record</button>}
          <button className="ghost" onClick={onSearchAgain} disabled={busy}>{busy ? "Searching…" : searched ? "Search again" : "Find audio"}</button>
        </div>
      </div>

      {!searched && !busy && (
        <p className={styles.note}>Audio is searched for when a record is added: your own files, YouTube, Bandcamp, SoundCloud and record stores.</p>
      )}

      {searched && (
        <>
          <table className={styles.table}>
            <thead><tr><th aria-label="Play" /><th>Pos</th><th>Title</th><th>Preview</th><th aria-label="Link" /></tr></thead>
            <tbody>
              {record.tracks.map((t) => {
                const a = byTrack.get(t.id);
                const o = plan.tracks[t.position];
                const stores = plan.stores[t.position] ?? [];
                const on = now?.pos === t.position;
                const link = a?.page || a?.url;
                return (
                  <tr key={t.id} className={`${o ? "" : styles.none} ${on ? styles.now : ""}`} data-testid={`found-audio-${t.position}`}>
                    <td>{o && <button className={`${styles.play} ${on && now?.playing ? styles.on : ""}`} onClick={() => play(t.position)} aria-label={`${on && now?.playing ? "Pause" : "Play"} ${t.position}`}>{on && now?.playing ? "❚❚" : "▶"}</button>}</td>
                    <td className={styles.pos}>{t.position}</td>
                    <td className={styles.title}>
                      <b>{t.title}</b>
                      {a && <small>{a.reason || WORD[a.status]}</small>}
                      {stores.length > 0 && <span className={styles.stores}>{stores.map((s) => <a key={s.source} href={s.page} target="_blank" rel="noopener noreferrer">Find at {STORES[s.source] ?? s.source} ↗</a>)}</span>}
                    </td>
                    <td>
                      {o ? (
                        <span className={o.review ? styles.review : styles.src}>
                          {familyName(o.family)}{o.quality && o.quality !== "full" ? ` · ${o.quality}` : ""}{o.review ? " · needs a look" : ""}
                          <small>{Math.round(o.confidence * 100)}% sure</small>
                        </span>
                      ) : <span className={styles.noSrc}>{a ? (a.status === "not_found" ? "not found" : "no preview") : "not searched"}</span>}
                    </td>
                    <td>{link ? <a className={styles.open} href={link} target="_blank" rel="noopener noreferrer">Open ↗</a> : null}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {plan.families.length > 0 && (
            <p className={styles.note}>
              Each track plays from the source that covers most of the record; the rest come from the next best one.{" "}
              {plan.families.map((f) => `${familyName(f.family)}: ${f.tracks.join(" ")}`).join(" · ")}
            </p>
          )}
        </>
      )}

      <audio ref={audio} onEnded={onEnded} onPause={() => setNow((n) => (n && (n.kind === "audio" || n.kind === "file") ? { ...n, playing: false } : n))} onPlay={() => setNow((n) => (n ? { ...n, playing: true } : n))} hidden />
      {now && now.kind !== "audio" && now.kind !== "file" && (
        <div className={styles.dock} role="region" aria-label="Player">
          <div className={styles.dockHead}><span>{now.label}</span><button className="ghost small" onClick={stop} aria-label="Close player">✕</button></div>
          {now.dock ? <iframe ref={frame} src={now.dock} height={height} title={`${familyName(now.kind)} player`} allow="autoplay; encrypted-media" />
            : now.dock === "" ? <span className={styles.note}>loading Bandcamp…</span>
            : <span className={styles.note}>The player could not load. Use “Open ↗” on the track.</span>}
        </div>
      )}
    </section>
  );
}
