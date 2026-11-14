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

const SECTIONS = [
  { key: "discogs", label: "Discogs" },
  { key: "audio", label: "Audio" },
  { key: "analysis", label: "Analysis" },
  { key: "youtube", label: "YouTube" },
  { key: "vault", label: "Obsidian vault" },
] as const;
type SectionKey = (typeof SECTIONS)[number]["key"];

/** Settings, one section at a time, picked from the menu on the right. The section lives in ?section= so
 *  other pages can link straight to it; Google's sign-in comes back with ?youtube=…, which opens YouTube. */
export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("section");
  const section: SectionKey = SECTIONS.some((s) => s.key === asked)
    ? (asked as SectionKey)
    : params.has("youtube") ? "youtube" : "discogs";
  const label = SECTIONS.find((s) => s.key === section)!.label;

  return (
    <div className={styles.layout}>
      <div className={styles.page}>
        <header>
          <span className="micro">settings</span>
          <h1>{label}</h1>
        </header>
        {section === "discogs" && <DiscogsSection />}
        {section === "audio" && <><AudioSearchSection /><LibraryAudioSection /></>}
        {section === "analysis" && <KeySection />}
        {section === "youtube" && <YouTubeSection />}
        {section === "vault" && <VaultSection />}
      </div>
      <nav className={styles.menu} aria-label="Settings sections">
        <ul>
          {SECTIONS.map((s) => (
            <li key={s.key}>
              <button type="button" className={s.key === section ? styles.current : ""}
                aria-current={s.key === section ? "page" : undefined}
                onClick={() => setParams({ section: s.key }, { replace: true })}>
                {s.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

function VaultSection() {
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
  const last = sync.data ?? status.data?.last_sync ?? null;

  return (
    <>
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
    </>
  );
}

function KeySection() {
  const [keysOn, setKeysOn] = useKeysEnabled();
  const [keyFormat, setKeyFormat] = useKeyFormat();
  const [confidenceOn, setConfidenceOn] = useKeyConfidenceEnabled();

  return (
    <>
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
    </>
  );
}

function LibraryAudioSection() {
  const findLibraryAudio = useMutation({ mutationFn: api.findAudioForLibrary });

  return (
    <>
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
      <DownloadedAudio />
    </>
  );
}

const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;

/** Audio the app downloaded is only kept until the track's analysis is validated or discarded. */
function DownloadedAudio() {
  const client = useQueryClient();
  const usage = useQuery({ queryKey: ["downloads"], queryFn: api.downloads });
  const clear = useMutation({
    mutationFn: api.clearDownloads,
    onSuccess: (out) => {
      client.setQueryData(["downloads"], { files: out.files, bytes: out.bytes });
      pushToast(out.deleted === 0 ? "Nothing to clear" : `Cleared ${plural(out.deleted, "file")}, ${megabytes(out.freed_bytes)}`, "info");
    },
  });

  return (
    <>
      <header>
        <span className="micro">audio</span>
        <h2>Downloaded audio</h2>
      </header>
      <p className={styles.hint}>
        Audio the app downloads (YouTube, shop clips) is only needed to analyse a track, so it is deleted once you validate or
        discard that analysis. Analysing the track again downloads it again. Your own files are never touched.
      </p>
      <p className={styles.hint} data-testid="downloads-usage">
        {usage.data ? `${plural(usage.data.files, "file")} kept, ${megabytes(usage.data.bytes)}.` : "…"}
      </p>
      <div className={styles.actions}>
        <button onClick={() => clear.mutate()} disabled={clear.isPending || usage.data?.files === 0}>
          {clear.isPending ? "Clearing…" : "Clear downloaded audio"}
        </button>
      </div>
      <p className={styles.hint}>Keeps only the files a track still needs: an analysis waiting for you, or one not run yet.</p>
    </>
  );
}

function DiscogsSection() {
  const client = useQueryClient();
  const [stylesJob, setStylesJob] = useState<number | null>(null);
  const fetchStyles = useMutation({ mutationFn: api.backfillStyles, onSuccess: ({ job_id }) => setStylesJob(job_id) });

  return (
    <>
      <DiscogsSync />

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
    </>
  );
}

/** How "Search audio" works everywhere: fast or lengthy, and which sources it asks. Record shops can be
 *  switched one by one. Your own files are not listed: they always come first. */
function AudioSearchSection() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["app-settings"], queryFn: api.getSettings });
  const groups = useQuery({ queryKey: ["audio-sources"], queryFn: api.audioSources, staleTime: Infinity });
  const save = useMutation({ mutationFn: api.patchSettings, onSuccess: (s) => client.setQueryData(["app-settings"], s) });
  const lengthy = settings.data?.audio_search_lengthy ?? false;
  const off = new Set(settings.data?.audio_sources_off ?? []);
  const locked = !settings.data || save.isPending;
  const set = (names: string[], on: boolean) => {
    const next = new Set(off);
    names.forEach((n) => (on ? next.delete(n) : next.add(n)));
    save.mutate({ audio_sources_off: [...next] });
  };

  return (
    <>
      <header>
        <span className="micro">audio</span>
        <h2>Audio search</h2>
      </header>
      <div className={styles.choices} role="radiogroup" aria-label="Search mode">
        <label className={styles.toggle}>
          <input type="radio" name="audio-mode" checked={!lengthy} disabled={locked} onChange={() => save.mutate({ audio_search_lengthy: false })} />
          <span>Fast</span>
        </label>
        <label className={styles.toggle}>
          <input type="radio" name="audio-mode" checked={lengthy} disabled={locked} onChange={() => save.mutate({ audio_search_lengthy: true })} />
          <span>Lengthy</span>
        </label>
      </div>
      <p className={styles.hint}>
        {lengthy
          ? "Lengthy asks every source below for every track, so each track also gets its other sources. It is much slower."
          : "Fast asks the sources below one after the other and stops as soon as every track has audio."}
        {" "}Search audio on a record always starts from scratch. Tracks with a file you uploaded are never searched.
      </p>
      <ul className={styles.sources} aria-label="Sources the search uses">
        {(groups.data ?? []).map((g) => {
          const names = g.sources.map((s) => s.name);
          const onCount = names.filter((n) => !off.has(n)).length;
          const box = (
            <label className={styles.toggle}>
              <input type="checkbox" checked={onCount > 0} disabled={locked}
                ref={(el) => { if (el) el.indeterminate = onCount > 0 && onCount < names.length; }}
                onChange={(e) => set(names, e.target.checked)} />
              <span>{g.label}</span>
            </label>
          );
          return g.key !== "shops" ? <li key={g.key}>{box}</li> : (
            <li key={g.key}>
              {box}
              <details>
                <summary>Choose shops ({onCount} of {names.length} on)</summary>
                <ul>
                  {g.sources.map((s) => (
                    <li key={s.name}>
                      <label className={styles.toggle}>
                        <input type="checkbox" checked={!off.has(s.name)} disabled={locked} onChange={(e) => set([s.name], e.target.checked)} />
                        <span>{s.label}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          );
        })}
      </ul>
    </>
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
    setParams({ section: "youtube" }, { replace: true });
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
