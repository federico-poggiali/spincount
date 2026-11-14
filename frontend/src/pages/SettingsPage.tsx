import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/api";
import { DiscogsSync } from "../components/DiscogsSync";
import { JobChip } from "../components/JobChip";
import { KeyFormatToggle } from "../components/KeyFormatToggle";
import { YouTubeCredentialsForm, YouTubeQuota, YouTubeSetupGuide } from "../components/YouTubeSetup";
import { useKeyConfidenceEnabled, useKeyFormat, useKeysEnabled } from "../hooks";
import { plural } from "../lib";
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
  const findLibraryAudio = useMutation({ mutationFn: api.findAudioForLibrary });
  const [keysOn, setKeysOn] = useKeysEnabled();
  const [keyFormat, setKeyFormat] = useKeyFormat();
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
      <div className={styles.toggle}>
        <KeyFormatToggle value={keyFormat} onChange={setKeyFormat} />
        <span>Key notation: Camelot (8A) or musical (Am)</span>
      </div>
      <p className={styles.hint}>Used wherever keys are shown. Needs musical key on.</p>
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
        <button className="primary" onClick={() => findLibraryAudio.mutate()} disabled={findLibraryAudio.isPending}>
          {findLibraryAudio.isPending ? "Queueing…" : "Find audio for the library"}
        </button>
      </div>
      {findLibraryAudio.data && (
        <p className={styles.hint} role="status" data-testid="library-audio-queued">
          {findLibraryAudio.data.queued === 0 ? "Nothing to do: every record has been searched." : `${plural(findLibraryAudio.data.queued, "record")} queued. They run in the background; each record page shows its progress.`}
        </p>
      )}

      <YouTubeSection />

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

      <DiscogsSync />
    </div>
  );
}

/** Add to YT playlist: when on, every track is looked up on YouTube (links only) and each record page can add
 *  the tracks you pick to one of your YouTube playlists. Nothing goes to YouTube by itself. */
function YouTubeSection() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["app-settings"], queryFn: api.getSettings });
  const save = useMutation({ mutationFn: api.patchSettings, onSuccess: (s) => client.setQueryData(["app-settings"], s) });
  const on = settings.data?.youtube_playlist ?? false;
  const status = useQuery({ queryKey: ["youtube-status"], queryFn: api.youtubeStatus, enabled: on });
  const connect = useMutation({ mutationFn: api.connectYouTube, onSuccess: ({ url }) => window.location.assign(url) });
  const disconnect = useMutation({
    mutationFn: api.disconnectYouTube,
    onSuccess: () => client.invalidateQueries({ queryKey: ["youtube-status"] }),
  });
  const findLibrary = useMutation({ mutationFn: api.findYouTubeForLibrary });
  const removeApp = useMutation({
    mutationFn: api.removeYouTubeCredentials,
    onSuccess: () => client.invalidateQueries({ queryKey: ["youtube-status"] }),
  });
  const [changing, setChanging] = useState(false);
  const yt = status.data;
  // Google's sign-in comes back here with ?youtube=connected or ?youtube=error&message=…
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    const back = params.get("youtube");
    if (!back) return;
    if (back === "connected") pushToast("YouTube connected.", "info");
    else pushToast(params.get("message") ?? "YouTube sign-in failed.");
    setParams({}, { replace: true });
  }, [params, setParams]);

  return (
    <>
      <header>
        <span className="micro">youtube</span>
        <h2>Add to YT playlist</h2>
      </header>
      <label className={styles.toggle}>
        <input type="checkbox" checked={on} disabled={!settings.data || save.isPending}
          onChange={(e) => save.mutate({ youtube_playlist: e.target.checked })} />
        <span>Add to YT playlist</span>
      </label>
      <p className={styles.hint}>
        With this on, every track of a record you add is looked up on YouTube, whatever its audio came from: the videos
        linked on Discogs first, then a YouTube search checked on title, artist and length. Nothing is downloaded. Each
        record page then has an Add to YT playlist button: you pick the tracks and one of your playlists. Nothing is added
        to YouTube by itself.
      </p>
      {on && yt && !yt.configured && (
        <>
          <p className={styles.hint} role="note">
            To add tracks to your playlists, Spin Count signs in with your own Google app. It takes about ten minutes, once,
            and gives you your own YouTube quota: 10,000 units a day, about 200 tracks added.
          </p>
          <YouTubeSetupGuide />
          <YouTubeCredentialsForm />
        </>
      )}
      {on && yt?.configured && (changing ? (
        <YouTubeCredentialsForm onDone={() => setChanging(false)} />
      ) : (
        <div className={styles.app}>
          <span className="micro">Your Google app</span>
          <span className={`mono ${styles.clientId}`} title={yt.client_id ?? ""}>{yt.client_id}</span>
          {yt.source === "env" ? (
            <span className={styles.hint}>from .env</span>
          ) : (
            <span className={styles.actions}>
              <button className="ghost small" onClick={() => setChanging(true)}>Change</button>
              <button className="ghost small danger" disabled={removeApp.isPending}
                onClick={() => window.confirm("Remove your Google app from Spin Count? This also disconnects YouTube.") && removeApp.mutate()}>
                Remove
              </button>
            </span>
          )}
        </div>
      ))}
      {on && yt?.usage && <YouTubeQuota usage={yt.usage} />}
      {on && yt?.configured && (
        <div className={styles.actions}>
          {yt.connected ? (
            <>
              <span className={styles.hint} data-testid="youtube-connected">YouTube account connected.</span>
              <button className="ghost" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>Disconnect</button>
            </>
          ) : (
            <button className="primary" onClick={() => connect.mutate()} disabled={connect.isPending}>
              {connect.isPending ? "Opening Google…" : "Connect YouTube"}
            </button>
          )}
        </div>
      )}
      {connect.isError && <p className={styles.error} role="alert">{(connect.error as Error).message}</p>}
      {on && (
        <>
          <p className={styles.hint}>
            Records added before this was on have no YouTube links yet. This looks up every track not searched yet, record
            by record. It is quick and uses none of YouTube&apos;s daily quota; running it again continues where it stopped.
          </p>
          <div className={styles.actions}>
            <button className="ghost" onClick={() => findLibrary.mutate()} disabled={findLibrary.isPending}>
              {findLibrary.isPending ? "Queueing…" : "Find YouTube for the library"}
            </button>
          </div>
          {findLibrary.data && (
            <p className={styles.hint} role="status">
              {findLibrary.data.queued === 0 ? "Nothing to do: every track has been looked up." : `${plural(findLibrary.data.queued, "record")} queued. They run in the background.`}
            </p>
          )}
        </>
      )}
    </>
  );
}
