import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type RecordAudio, type RecordDetail, type TrackAudio } from "../api/api";
import styles from "./RecordAudio.module.css";

/** One playable link of a track, as chosen by audioresearch's preview plan (same rules as its viewer). */
type Option = { source: string; url: string | null; quality: string | null; confidence: number; review: boolean; family: string; kind: "youtube" | "bandcamp" | "soundcloud" | "audio" | "file"; embed_id?: string };
type Plan = { tracks: Record<string, Option | null>; families: { family: string; tracks: string[] }[]; stores: Record<string, { source: string; page: string }[]> };

const FAMILY: Record<string, string> = { youtube: "YouTube", bandcamp: "Bandcamp", soundcloud: "SoundCloud", itunes: "iTunes", "your files": "Your files" };
export const STORES: Record<string, string> = { deejay_de: "deejay.de", hardwax: "Hard Wax", redeye: "Redeye", decks_de: "Decks", clone: "Clone", soundmetaphors: "Sound Metaphors", one_eye_witness: "One Eye Witness", smallblackdots: "Small Black Dots", runas: "Runas", orbitwax: "Orbit Wax" };
const familyName = (f: string) => FAMILY[f] ?? STORES[f] ?? f;
const WORD: Record<TrackAudio["status"], string> = { found: "found", review: "needs a look", not_found: "not found" };

type Now = { pos: string; kind: Option["kind"]; playing: boolean; dock: string | null; label: string };

/** What a track row shows about its audio. */
export type TrackAudioView = {
  playable: boolean;
  playing: boolean;
  review: boolean;
  /** why nothing plays: "not found", "no preview" */
  missing: string | null;
  stores: { source: string; page: string }[];
  toggle: () => void;
};

/** Every link found for a track other than the one it plays, for the "Other audio sources" panel. */
export type OtherSources = { position: string; title: string; links: { label: string; url: string; detail: string }[] }[];

export type RecordAudioState = {
  others: OtherSources;
  /** Null until audio has been searched for. */
  view: (position: string, trackId: number) => TrackAudioView | null;
  searched: boolean;
  playFirst: (() => void) | null;
  /** The hidden <audio> element and the docked embedded player; render once, anywhere. */
  player: ReactNode;
};

/** What audioresearch found for each track, playable on the record page: one play button per track,
 *  the record's sources picked so it sounds like one source. */
export function useRecordAudio(record: RecordDetail | undefined): RecordAudioState {
  const recordId = record?.id ?? 0;
  const tracks = record?.tracks ?? [];
  const found = useQuery({ queryKey: ["record-audio", recordId], queryFn: () => api.recordAudio(recordId), enabled: recordId > 0, meta: { quiet: true } });
  const data = found.data as RecordAudio | undefined;
  const plan = (data?.previews ?? { tracks: {}, families: [], stores: {} }) as Plan;
  const byTrack = new Map((data?.tracks ?? []).map((a) => [a.track_id, a]));
  const order = tracks.map((t) => t.position).filter((p) => plan.tracks[p]);
  const idOf = (pos: string) => tracks.find((t) => t.position === pos)?.id;

  const audio = useRef<HTMLAudioElement | null>(null);
  const frame = useRef<HTMLIFrameElement | null>(null);
  const [now, setNow] = useState<Now | null>(null);

  const stop = useCallback(() => { audio.current?.pause(); audio.current?.removeAttribute("src"); setNow(null); }, []);
  useEffect(() => stop, [stop, recordId]);

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
  const height = now?.kind === "youtube" ? 200 : now?.kind === "bandcamp" ? 42 : 20;

  const others: OtherSources = tracks.flatMap((t) => {
    const a = byTrack.get(t.id);
    if (!a) return [];
    const chosen = plan.tracks[t.position]?.url;
    const seen = new Set<string>(chosen ? [chosen] : []);
    const links = [...(a.status === "not_found" ? [] : [a]), ...a.alternatives].flatMap((c) => {
      const x = c as { source?: string; url?: string | null; page?: string | null; quality?: string | null; confidence?: number };
      const detail = [x.quality && x.quality !== "full" ? x.quality : null, x.confidence ? `${Math.round(x.confidence * 100)}% sure` : null].filter(Boolean).join(" · ");
      return [x.url, x.page].flatMap((url, i) => {
        if (!url || !/^https?:/.test(url) || seen.has(url)) return [];
        seen.add(url);
        return [{ label: `${familyName(x.source ?? "link")}${i === 1 ? " page" : ""}`, url, detail: i === 1 ? "" : detail }];
      });
    });
    return links.length ? [{ position: t.position, title: t.title, links }] : [];
  });

  const view = (position: string, trackId: number): TrackAudioView | null => {
    if (!searched) return null;
    const a = byTrack.get(trackId);
    const o = plan.tracks[position];
    return {
      playable: Boolean(o),
      playing: now?.pos === position && now.playing,
      review: Boolean(o?.review),
      missing: o ? null : a ? (a.status === "not_found" ? "not found" : a.reason || WORD[a.status]) : null,
      stores: plan.stores[position] ?? [],
      toggle: () => void play(position),
    };
  };

  const player = (
    <>
      <audio ref={audio} onEnded={onEnded} onPause={() => setNow((n) => (n && (n.kind === "audio" || n.kind === "file") ? { ...n, playing: false } : n))} onPlay={() => setNow((n) => (n ? { ...n, playing: true } : n))} hidden />
      {now && now.kind !== "audio" && now.kind !== "file" && (
        <div className={styles.dock} role="region" aria-label="Player">
          <div className={styles.dockHead}><span>{now.label}</span><button className="ghost small" onClick={stop} aria-label="Close player">✕</button></div>
          {now.dock ? <iframe ref={frame} src={now.dock} height={height} title={`${familyName(now.kind)} player`} allow="autoplay; encrypted-media" />
            : now.dock === "" ? <span className={styles.note}>loading Bandcamp…</span>
            : <span className={styles.note}>The player could not load. Use “Open ↗” on the track.</span>}
        </div>
      )}
    </>
  );

  return {
    view, searched, player, others,
    playFirst: order.length > 0 ? () => void play(order[0]) : null,
  };
}
