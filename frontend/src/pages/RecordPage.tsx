import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/api";
import { ClampedNote } from "../components/ClampedNote";
import { Cover } from "../components/Cover";
import { Icon } from "../components/Icon";
import { JobChip } from "../components/JobChip";
import { useRecordAudio } from "../components/useRecordAudio";
import { QuickNote } from "../components/QuickNote";
import { SaveIndicator } from "../components/SaveIndicator";
import { ShelfPrompt } from "../components/ShelfPrompt";
import { Skeleton } from "../components/Skeleton";
import { StyleEditor } from "../components/StyleEditor";
import { TagEditor } from "../components/TagEditor";
import { TrackTable } from "../components/TrackTable";
import { recordKey, usePatchRecord, useKeyFormat, useKeyConfidenceEnabled, useKeysEnabled, useRecord, useStyleMutations, useStyles, useTagMutations, useTags } from "../hooks";
import { LOW_CONFIDENCE } from "../lib";
import styles from "./RecordPage.module.css";

/** Passed in router state by the add-record page, so the record can say what happened.
    askShelf: it was added as owned, so ask where it goes on the shelf. */
export type Arrival = { existed: boolean; fromMaster: boolean; askShelf?: boolean; audioJob?: number };

export default function RecordPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const { state } = useLocation();
  const arrival = state as Arrival | null;
  const client = useQueryClient();
  const [analysisJob, setAnalysisJob] = useState<number | null>(null);
  const [syncJob, setSyncJob] = useState<number | null>(null);
  const [audioJob, setAudioJob] = useState<number | null>(arrival?.audioJob ?? null);
  const [findingAudio, setFindingAudio] = useState(arrival?.audioJob != null);
  const [analysing, setAnalysing] = useState(false);
  const record = useRecord(id, analysing);
  const patch = usePatchRecord(id);
  const tags = useTagMutations(id);
  const allTags = useTags();
  const styleMutations = useStyleMutations(id);
  const allStyles = useStyles();
  const [keyFormat] = useKeyFormat();
  const [keysOn] = useKeysEnabled();
  const [confidenceOn] = useKeyConfidenceEnabled();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [askShelf, setAskShelf] = useState(!!arrival?.askShelf);

  const audio = useRecordAudio(record.data);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [analysisIds, setAnalysisIds] = useState<number[] | null>(null); // tracks of the running analysis; null = whole record
  const analyze = useMutation({
    mutationFn: (trackIds?: number[]) => api.analyze(id, trackIds),
    onSuccess: ({ job_id }, trackIds) => { setAnalysisIds(trackIds ?? null); setAnalysisJob(job_id); setAnalysing(true); },
  });
  const searchAgain = useMutation({
    mutationFn: (everything: boolean = false) => api.findAudio(id, !everything, everything),
    onSuccess: ({ job_id }) => { setAudioJob(job_id); setFindingAudio(true); },
  });
  // Your own files go into the record's audio folder; searching afterwards matches them to their tracks first.
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadAudio(id, file);
      return api.findAudio(id, true);
    },
    onSuccess: ({ job_id }) => { setAudioJob(job_id); setFindingAudio(true); },
  });
  const pickFiles = useRef<HTMLInputElement>(null);
  // Analysis results wait as proposals until validated; `conflict` holds tracks whose hand-set values they'd replace.
  const [conflict, setConflict] = useState<{ ids: number[]; manual: string[] } | null>(null);
  const validate = useMutation({
    mutationFn: ({ ids, overwrite }: { ids: number[]; overwrite: boolean }) => api.validate(id, ids, overwrite),
    onSuccess: (detail) => { setConflict(null); client.setQueryData(recordKey(id), detail); refresh(); },
  });
  const discard = useMutation({
    mutationFn: (ids?: number[]) => api.discard(id, ids),
    onSuccess: (detail) => { setConflict(null); client.setQueryData(recordKey(id), detail); },
  });
  const [syncRunning, setSyncRunning] = useState(false);
  const sync = useMutation({ mutationFn: () => api.syncDiscogs(id), onSuccess: ({ job_id }) => { setSyncJob(job_id); setSyncRunning(true); } });
  const del = useMutation({
    mutationFn: () => api.deleteRecord(id),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["records"] }); navigate("/"); },
  });
  const refresh = useCallback(() => {
    client.invalidateQueries({ queryKey: ["records"] });
    client.invalidateQueries({ queryKey: recordKey(id) });
    client.invalidateQueries({ queryKey: ["record-audio", id] });
  }, [client, id]);

  if (record.isError) {
    const missing = record.error instanceof ApiError && record.error.status === 404;
    return (
      <div className={styles.missing}>
        <span className="micro">{missing ? "404" : "error"}</span>
        <h1>{missing ? "That record isn't in your library." : "Couldn't load this record."}</h1>
        <Link className="ghost" to="/">Back to the library</Link>
      </div>
    );
  }
  if (!record.data) return <Skeleton rows={6} />;

  const r = record.data;
  const analysisBusy = analyze.isPending || analysing;
  const busyIds = analysing ? new Set(analysisIds ?? r.tracks.map((t) => t.id)) : undefined;
  const recordNote = r.notes.map((n) => n.body.trim()).find(Boolean);
  const pending = r.tracks.filter((t) => t.proposal);
  const lowCount = !keysOn || !confidenceOn ? 0 : pending.filter((t) => t.proposal!.confidence != null && t.proposal!.confidence < LOW_CONFIDENCE).length;
  const pickedPending = pending.filter((t) => selected.has(t.id));
  const startValidate = (tracks: typeof pending) => {
    const manual = tracks.filter((t) => {
      const p = t.proposal!;
      return (t.bpm_manual && p.bpm != null && p.bpm !== t.bpm)
        || (keysOn && t.key_manual && p.camelot_key != null && p.camelot_key !== t.camelot_key);
    });
    const ids = tracks.map((t) => t.id);
    if (manual.length) setConflict({ ids, manual: manual.map((t) => t.position || t.title) });
    else validate.mutate({ ids, overwrite: false });
  };

  const facts = [
    ["Label", r.label], ["Catalogue", r.catno], ["Year", r.year], ["Format", r.format],
  ].filter(([, v]) => v != null && v !== "") as [string, string | number][];

  return (
    <article className={styles.page}>
      {arrival?.existed && <p className={styles.notice} role="status"><b>Already in your library.</b> It was not added twice.</p>}
      {arrival?.fromMaster && <p className={styles.notice}>Master link: using its main release.</p>}
      {askShelf && r.status === "owned" && <ShelfPrompt recordId={r.id} onDone={() => setAskShelf(false)} />}
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <Link to={r.status === "owned" ? "/" : "/wantlist"}>{r.status === "owned" ? "Library" : "Wishlist"}</Link>
        <Icon name="chevron" size={12} />
        <span aria-current="page">{r.title}</span>
        <SaveIndicator />
      </nav>
      <header className={styles.head}>
        <div className={styles.cover}><Cover url={r.cover_url} alt={`${r.artist} - ${r.title}`} /></div>
        <div className={styles.meta}>
          <h1>{r.title}</h1>
          <p className={styles.artist}>{r.artist}{r.year ? <span> · {r.year}</span> : null}</p>
          {pending.length > 0 && (
            <span className={styles.pendingBadge}>{pending.length} {pending.length === 1 ? "track" : "tracks"} to validate</span>
          )}
          {recordNote && <ClampedNote text={recordNote} className={styles.noteLine} />}
        </div>
        <div className={styles.actions}>
          <QuickNote recordId={r.id} title={r.title} filled={r.notes.some((n) => n.body.trim() !== "")} />
          {r.discogs_release_id != null && (
            <a className="ghost small" href={`https://www.discogs.com/release/${r.discogs_release_id}`} target="_blank" rel="noreferrer">Discogs <Icon name="external" size={12} /></a>
          )}
          <Link className="ghost small" to={`/records/${id}/label`}>Make label</Link>
        </div>
      </header>

      <div className={styles.body}>
        <div className={styles.main}>
      <section aria-label="Tracks">
          <div className={styles.toolbar}>
            <div className={styles.toolbarActions}>
              <button className="primary" onClick={() => analyze.mutate(selected.size ? [...selected] : undefined)}
                disabled={analysisBusy || r.discogs_release_id == null}>
                {selected.size === 0 ? "Analyse all tracks" : `Analyse ${selected.size} ${selected.size === 1 ? "track" : "tracks"}`}
              </button>
              {selected.size > 0 && <button className="ghost" onClick={() => setSelected(new Set())}>Clear selection</button>}
              <button className="ghost" onClick={() => searchAgain.mutate(false)} disabled={findingAudio || searchAgain.isPending || upload.isPending || r.discogs_release_id == null}>
                {findingAudio || searchAgain.isPending ? "Searching audio…" : audio.searched ? "Search audio again" : "Find audio"}
              </button>
              <button className="ghost" onClick={() => pickFiles.current?.click()} disabled={upload.isPending || findingAudio || r.discogs_release_id == null}>
                {upload.isPending ? "Uploading…" : "Upload audio"}
              </button>
              <input ref={pickFiles} type="file" accept="audio/*,.flac,.aif,.aiff" multiple hidden aria-label="Audio files to upload"
                onChange={(e) => { const files = [...(e.target.files ?? [])]; e.target.value = ""; if (files.length) upload.mutate(files); }} />
              {audio.playFirst && <button className="ghost" onClick={audio.playFirst}>▶ Play record</button>}
              <span className={styles.spacer} />
            </div>
            {(analysisJob != null || syncJob != null || audioJob != null) && (
              <div className={styles.jobs}>
                {audioJob != null && <JobChip label="Finding audio" jobId={audioJob} onSettled={() => { setFindingAudio(false); refresh(); }} onRetry={() => searchAgain.mutate(searchAgain.variables ?? false)} retrying={searchAgain.isPending} />}
                {analysisJob != null && <JobChip label="Analysis" jobId={analysisJob} onSettled={() => { setAnalysing(false); refresh(); }} onRetry={() => analyze.mutate(analysisIds ?? undefined)} />}
                {syncJob != null && <JobChip label="Discogs sync" jobId={syncJob} onSettled={() => { setSyncRunning(false); refresh(); }} onRetry={() => sync.mutate()} />}
              </div>
            )}
            {pending.length > 0 && (
              <div className={styles.validateBar} role="region" aria-label="Analysis to validate">
                {conflict ? (
                  <>
                    <p><b>{conflict.manual.join(", ")}</b> {conflict.manual.length === 1 ? "has" : "have"} a {keysOn ? "BPM or key" : "BPM"} you set by hand. Replace {conflict.manual.length === 1 ? "it" : "them"} with the new analysis?</p>
                    <div className={styles.toolbarActions}>
                      <button className="primary small" disabled={validate.isPending} onClick={() => validate.mutate({ ids: conflict.ids, overwrite: true })}>Replace mine</button>
                      <button className="ghost small" disabled={validate.isPending} onClick={() => validate.mutate({ ids: conflict.ids, overwrite: false })}>Keep mine</button>
                      <button className="ghost small" onClick={() => setConflict(null)}>Cancel</button>
                    </div>
                  </>
                ) : r.status === "owned" ? (
                  <>
                    <p>New analysis is ready for {pending.length} {pending.length === 1 ? "track" : "tracks"}. Nothing is saved until you validate it.{lowCount > 0 && ` ${lowCount} ${lowCount === 1 ? "has" : "have"} a key the analysis was unsure about. Open the arrow next to it to see how sure.`}</p>
                    <div className={styles.toolbarActions}>
                      <button className="primary small" disabled={validate.isPending || pickedPending.length === 0} onClick={() => startValidate(pickedPending)}>
                        Validate selected{pickedPending.length ? ` (${pickedPending.length})` : ""}
                      </button>
                      <button className="ghost small" disabled={validate.isPending} onClick={() => startValidate(pending)}>Validate all</button>
                      <button className="ghost small danger" disabled={discard.isPending} onClick={() => discard.mutate()}>Discard</button>
                    </div>
                  </>
                ) : (
                  <>
                    <p>New analysis is ready for {pending.length} {pending.length === 1 ? "track" : "tracks"}. Add the record to your library to validate it.</p>
                    <div className={styles.toolbarActions}>
                      <button className="ghost small danger" disabled={discard.isPending} onClick={() => discard.mutate()}>Discard</button>
                    </div>
                  </>
                )}
              </div>
            )}
            {selected.size > 0 && <p className={styles.hint}>Only the ticked tracks will be analysed.</p>}
          </div>
          <TrackTable record={r} audio={audio} editable keyFormat={keyFormat} showKeys={keysOn} busyIds={busyIds} selection={{ ids: selected, onChange: setSelected }}
            onUse={r.status === "owned" ? (t) => startValidate([t]) : undefined} onPass={(t) => discard.mutate([t.id])} />
          {audio.player}
          {audio.searched && (
            <details className={styles.others} data-testid="other-audio">
              <summary>Other audio sources{audio.others.length > 0 && <span>{audio.others.reduce((n, o) => n + o.links.length, 0)}</span>}</summary>
              <div className={styles.othersHead}>
                <p className={styles.hint}>{audio.others.length > 0 ? "Everything else the search found for each track." : "No other sources yet."} Finding more searches every source for every track, so it is slower.</p>
                <button className="ghost small" onClick={() => searchAgain.mutate(true)} disabled={findingAudio || searchAgain.isPending || upload.isPending}>
                  {findingAudio && searchAgain.variables ? "Finding more sources…" : "Find more sources"}
                </button>
              </div>
              {audio.others.length > 0 && <ul>
                {audio.others.map((o) => (
                  <li key={o.position}>
                    <b>{o.position} {o.title}</b>
                    <span>{o.links.map((l) => (
                      <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer">{l.label} ↗{l.detail ? <small> {l.detail}</small> : null}</a>
                    ))}</span>
                  </li>
                ))}
              </ul>}
            </details>
          )}
          {upload.isError && <p className={styles.hint} role="alert">Upload failed: {(upload.error as Error).message}</p>}
          <p className={styles.hint}>Click a {keysOn ? "BPM or key" : "BPM"} to set it yourself. A value you set is marked manual; validating new analysis asks before replacing it.</p>
        </section>

        </div>

        <aside className={styles.attrs} aria-label="Attributes">
          <dl>
            <div className={styles.attr}>
              <dt>Status</dt>
              <dd>
                {r.status === "owned" ? (
                  <span className={styles.owned}>Owned</span>
                ) : (
                  <div className={styles.statusActions}>
                    <span className={styles.statusText}>Wishlist</span>
                    <button className="primary small" onClick={() => patch.mutate({ status: "owned" }, { onSuccess: () => { client.invalidateQueries({ queryKey: ["crate"] }); setAskShelf(true); } })}>Add to library</button>
                  </div>
                )}
              </dd>
            </div>
            {facts.map(([k, v]) => (
              <div key={k} className={styles.attr}><dt>{k}</dt><dd>{v}</dd></div>
            ))}
            {r.status === "owned" && (
              <div className={styles.attr}>
                <dt>Collection</dt>
                <dd>
                  <button className={styles.link} onClick={() => sync.mutate()} disabled={sync.isPending || syncRunning}>
                    {r.discogs_collection_synced ? "In Discogs collection · sync again" : "Add to Discogs collection"}
                  </button>
                </dd>
              </div>
            )}
          </dl>
          <div className={styles.attrBlock}>
            <StyleEditor
              styles={r.styles ?? []} manual={r.styles_manual} suggestions={(allStyles.data ?? []).map((s) => s.name)}
              readOnly={arrival != null}
              onChange={(next) => styleMutations.set.mutate(next)}
              onReset={r.discogs_release_id != null ? () => styleMutations.reset.mutate() : undefined}
            />
          </div>
          <div className={styles.attrBlock}>
            <TagEditor
              label="this record" tags={r.tags ?? []} options={allTags.data ?? []}
              onAdd={(name) => tags.add.mutate({ kind: "record", id, name })}
              onRemove={(name) => tags.remove.mutate({ kind: "record", id, name })}
            />
          </div>
          <div className={styles.danger}>
            {confirmDelete ? (
              <>
                <button className="ghost small danger" onClick={() => del.mutate()} disabled={del.isPending}>Confirm delete</button>
                <button className="ghost small" onClick={() => setConfirmDelete(false)}>Keep</button>
              </>
            ) : (
              <button className="ghost small danger" onClick={() => setConfirmDelete(true)}>Delete record</button>
            )}
          </div>
        </aside>
      </div>
    </article>
  );
}
