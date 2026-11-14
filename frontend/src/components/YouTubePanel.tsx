import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type RecordDetail } from "../api/api";
import { plural } from "../lib";
import { JobChip } from "./JobChip";
import { YouTubeQuota } from "./YouTubeSetup";
import styles from "./YouTubePanel.module.css";

const WATCH = "https://www.youtube.com/watch?v=";

/** Add to YT playlist, on the record page: each track's YouTube video, ticked ones go into the playlist you pick,
 *  in tracklist order. A video already in that playlist is skipped. */
export function YouTubePanel({ record }: { record: RecordDetail }) {
  const client = useQueryClient();
  const key = ["record-youtube", record.id];
  const videos = useQuery({ queryKey: key, queryFn: () => api.recordYouTube(record.id) });
  const status = useQuery({ queryKey: ["youtube-status"], queryFn: api.youtubeStatus });
  const connected = !!status.data?.connected;
  const playlists = useQuery({ queryKey: ["youtube-playlists"], queryFn: api.youtubePlaylists, enabled: connected, retry: false });
  const [playlist, setPlaylist] = useState("");
  const [picked, setPicked] = useState<Set<number> | null>(null);
  const [job, setJob] = useState<number | null>(null);
  const find = useMutation({ mutationFn: (refresh: boolean) => api.findYouTube(record.id, refresh), onSuccess: ({ job_id }) => setJob(job_id) });
  const add = useMutation({
    mutationFn: (ids: number[]) => api.addToPlaylist(playlist, ids),
    onSettled: () => client.invalidateQueries({ queryKey: ["youtube-status"] }), // the quota meter
  });

  const byTrack = new Map((videos.data?.tracks ?? []).map((v) => [v.track_id, v]));
  const withVideo = record.tracks.filter((t) => byTrack.get(t.id)?.video_id);
  const chosen = picked ?? new Set(withVideo.map((t) => t.id)); // every track with a video, until you untick one
  const ticked = record.tracks.filter((t) => chosen.has(t.id) && byTrack.get(t.id)?.video_id).map((t) => t.id);
  const searched = byTrack.size > 0;
  // tracks with no video row yet (the audio search's YouTube links count as found): look up only those
  const missing = record.tracks.some((t) => !byTrack.has(t.id));
  const busy = find.isPending || job != null;

  useEffect(() => {
    if (!playlist && playlists.data?.length) setPlaylist(playlists.data[0].id);
  }, [playlist, playlists.data]);

  const toggle = (id: number) => {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id); else next.add(id);
    setPicked(next);
  };
  const result = add.data;

  return (
    <section className={styles.panel} aria-label="Add to YT playlist">
      <div className={styles.head}>
        <h3>Add to YT playlist</h3>
        <button className="ghost small" onClick={() => find.mutate(!missing)} disabled={busy}>
          {busy ? "Looking up on YouTube…" : !missing ? "Search YouTube again" : searched ? "Find the rest on YouTube" : "Find on YouTube"}
        </button>
      </div>
      {job != null && (
        <JobChip label="Finding on YouTube" jobId={job} onRetry={() => find.mutate(!missing)} retrying={find.isPending}
          onSettled={() => { setJob(null); setPicked(null); client.invalidateQueries({ queryKey: key }); }} />
      )}
      {!searched && !busy && videos.isSuccess && <p className={styles.hint}>Not looked up on YouTube yet.</p>}
      {searched && (
        <ul className={styles.list}>
          {record.tracks.map((t) => {
            const v = byTrack.get(t.id);
            return (
              <li key={t.id} className={styles.row}>
                <input type="checkbox" aria-label={`Add ${t.position} ${t.title}`} checked={!!v?.video_id && chosen.has(t.id)}
                  disabled={!v?.video_id} onChange={() => toggle(t.id)} />
                <span className={styles.position}>{t.position}</span>
                <span className={styles.title}>{t.title}</span>
                {v?.video_id ? (
                  <a href={WATCH + v.video_id} target="_blank" rel="noopener noreferrer" className={styles.video}>
                    {v.source === "audio" ? "Linked on Discogs" : v.title || "YouTube"} ↗
                  </a>
                ) : (
                  <span className={styles.missing}>{v ? "not on YouTube" : "not looked up yet"}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {searched && !connected && status.isSuccess && (
        <p className={styles.hint}><Link to="/settings?section=youtube">Connect YouTube in Settings</Link> to add these to a playlist.</p>
      )}
      {searched && connected && (
        <div className={styles.add}>
          <select className={styles.select} value={playlist} onChange={(e) => setPlaylist(e.target.value)} aria-label="Playlist"
            disabled={!playlists.data?.length}>
            {playlists.isLoading && <option value="">Loading your playlists…</option>}
            {playlists.data?.length === 0 && <option value="">You have no playlists on YouTube yet</option>}
            {playlists.data?.map((p) => <option key={p.id} value={p.id}>{p.title} ({p.count})</option>)}
          </select>
          <button className="primary small" onClick={() => add.mutate(ticked)} disabled={!playlist || ticked.length === 0 || add.isPending}>
            {add.isPending ? "Adding…" : `Add ${plural(ticked.length, "track")}`}
          </button>
        </div>
      )}
      {searched && connected && status.data?.usage && <YouTubeQuota usage={status.data.usage} compact />}
      {playlists.isError && <p className={styles.error} role="alert">{(playlists.error as Error).message}</p>}
      {add.isError && <p className={styles.error} role="alert">{(add.error as Error).message}</p>}
      {result && (
        <p className={styles.hint} role="status">
          {[`${plural(result.added.length, "track")} added`,
            result.already.length > 0 && `${result.already.length} already in the playlist`,
            result.failed.length > 0 && `${result.failed.length} failed`].filter(Boolean).join(" · ")}.
          {result.quota_exceeded && " YouTube's daily quota is used up: try the rest tomorrow."}
          {!result.quota_exceeded && result.failed[0] && ` ${result.failed[0].error}`}
        </p>
      )}
    </section>
  );
}
