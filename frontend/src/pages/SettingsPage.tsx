import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/api";
import { JobChip } from "../components/JobChip";
import { useKeyConfidenceEnabled, useKeysEnabled } from "../hooks";
import { pushToast } from "../toast";
import styles from "./SettingsPage.module.css";

export default function SettingsPage() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["vault-status"], queryFn: api.vaultStatus });
  const sync = useMutation({
    mutationFn: api.syncVault,
    onSuccess: () => client.invalidateQueries({ queryKey: ["vault-status"] }),
  });
  const reveal = useMutation({
    mutationFn: api.openVault,
    onSuccess: (r) => pushToast(r.opened ? "Revealed in Finder." : `Not generated yet. It will be at ${r.path}`, "info"),
  });
  const [stylesJob, setStylesJob] = useState<number | null>(null);
  const fetchStyles = useMutation({ mutationFn: api.backfillStyles, onSuccess: ({ job_id }) => setStylesJob(job_id) });
  const [libraryJobs, setLibraryJobs] = useState<number[]>([]);
  const analyseLibrary = useMutation({ mutationFn: api.findAudioForLibrary, onSuccess: ({ job_ids }) => setLibraryJobs(job_ids) });
  const [keysOn, setKeysOn] = useKeysEnabled();
  const [confidenceOn, setConfidenceOn] = useKeyConfidenceEnabled();
  const last = sync.data ?? status.data?.last_sync ?? null;

  return (
    <div className={styles.page}>
      <header>
        <span className="micro">settings</span>
        <h1>Obsidian vault</h1>
      </header>

      <p className={styles.warning} role="note">
        <b>Edits made inside Obsidian are overwritten.</b> The vault is rebuilt from this app on every sync. Change a record, note
        or tag here and it appears in Obsidian; the other way round never happens.
      </p>

      <dl className={styles.facts}>
        <div>
          <dt className="micro">vault folder</dt>
          <dd className="mono" data-testid="vault-dir">{status.data?.vault_dir ?? "…"}</dd>
        </div>
        <div>
          <dt className="micro">last sync</dt>
          <dd data-testid="last-sync">{last ? last.synced_at.replace("T", " ").replace("Z", " UTC") : "not yet"}</dd>
        </div>
        <div>
          <dt className="micro">last result</dt>
          <dd data-testid="last-result">{last ? `${last.written} written · ${last.skipped} unchanged · ${last.deleted} deleted` : "·"}</dd>
        </div>
      </dl>
      {status.data?.last_error && <p className={styles.error} role="alert">The last automatic sync failed: {status.data.last_error}</p>}

      <div className={styles.actions}>
        <button className="primary" onClick={() => sync.mutate()} disabled={sync.isPending}>{sync.isPending ? "Syncing…" : "Sync vault now"}</button>
        <button className="ghost" onClick={() => reveal.mutate()} disabled={reveal.isPending}>Show Dataview examples in Finder</button>
      </div>
      <p className={styles.hint}>The vault also syncs by itself a couple of seconds after any change. The Dataview examples file shows ready-made queries by BPM, key and tag.</p>

      <header>
        <span className="micro">analysis</span>
        <h2>Musical key</h2>
      </header>
      <label className={styles.toggle}>
        <input type="checkbox" checked={keysOn} onChange={(e) => setKeysOn(e.target.checked)} />
        <span>Analyse and show musical key</span>
      </label>
      <p className={styles.hint}>
        BPM is always analysed and shown. With this on, analysis also proposes a key for each track, and the tracklist, library
        filters and track list show keys (Camelot or musical). Off, every key column, filter and picker is hidden.
      </p>
      <label className={styles.toggle}>
        <input type="checkbox" checked={confidenceOn} disabled={!keysOn} onChange={(e) => setConfidenceOn(e.target.checked)} />
        <span>Show how sure the key analysis is</span>
      </label>
      <p className={styles.hint}>
        Adds the confidence percentage and the low-confidence warnings next to proposed and analysed keys. Needs musical key on.
      </p>

      <header>
        <span className="micro">audio</span>
        <h2>Find audio for the library</h2>
      </header>
      <p className={styles.hint}>
        New records find their audio by themselves when you add them. This does it for every record that has not been searched
        yet, one after the other: your own files, YouTube, Bandcamp, SoundCloud and record stores. It is slow (about a minute a
        record) and downloads audio. Records already searched are skipped, so running it again only continues where it stopped.
        BPM and key are not touched: analysing a record later reuses the audio found.
      </p>
      <div className={styles.actions}>
        <button className="primary" onClick={() => analyseLibrary.mutate()} disabled={analyseLibrary.isPending}>
          {analyseLibrary.isPending ? "Queueing…" : "Find audio for the library"}
        </button>
      </div>
      {analyseLibrary.data && (
        <p className={styles.hint} role="status" data-testid="library-audio-queued">
          {analyseLibrary.data.queued === 0 ? "Nothing to do: every record has been searched." : `${analyseLibrary.data.queued} ${analyseLibrary.data.queued === 1 ? "record" : "records"} queued. You can leave this page; they run in the background.`}
        </p>
      )}
      {libraryJobs.length > 0 && <p className={styles.hint}>Progress is on each record page (Audio tab).</p>}

      <header>
        <span className="micro">discogs</span>
        <h2>Styles</h2>
      </header>
      <p className={styles.hint}>
        Records added before styles were imported have none. This asks Discogs once per record (about one a second) and fills in
        the style and catalogue number. Records whose styles you edited are never touched.
      </p>
      <div className={styles.actions}>
        <button className="primary" onClick={() => fetchStyles.mutate()} disabled={fetchStyles.isPending}>Fetch styles for existing records</button>
      </div>
      {stylesJob != null && (
        <JobChip label="Styles" jobId={stylesJob} onRetry={() => fetchStyles.mutate()} retrying={fetchStyles.isPending}
          onSettled={() => { client.invalidateQueries({ queryKey: ["styles"] }); client.invalidateQueries({ queryKey: ["records"] }); }} />
      )}
    </div>
  );
}
