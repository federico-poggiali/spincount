import { Fragment, useEffect, useRef, useState } from "react";
import { formatBpm, formatDuration, keyLabel, LOW_CONFIDENCE, WHEEL_KEYS, type KeyFormat } from "../lib";
import type { RecordDetail, TrackOut } from "../api/api";
import { useKeyConfidenceEnabled, usePatchTrack, useTagMutations, useTags } from "../hooks";
import { ClampedNote } from "./ClampedNote";
import { STORES, type RecordAudioState, type TrackAudioView } from "./useRecordAudio";
import { QuickNote } from "./QuickNote";
import { TagEditor } from "./TagEditor";
import styles from "./TrackTable.module.css";

type Selection = { ids: Set<number>; onChange: (ids: Set<number>) => void };
type Props = {
  record: RecordDetail; audio?: RecordAudioState; editable: boolean; keyFormat: KeyFormat; showKeys: boolean; busyIds?: Set<number>; selection?: Selection;
  /** Decide on a track's waiting analysis from its pop-up: take it, or pass on it. */
  onUse?: (track: TrackOut) => void;
  onPass?: (track: TrackOut) => void;
};

const SORTED_KEYS = [...WHEEL_KEYS].sort((a, b) => parseInt(a.camelot) - parseInt(b.camelot) || a.camelot.localeCompare(b.camelot));

export function TrackTable({ record, audio, editable, keyFormat, showKeys, busyIds, selection, onUse, onPass }: Props) {
  const [open, setOpen] = useState<number | null>(null);
  const all = record.tracks.length > 0 && record.tracks.every((t) => selection?.ids.has(t.id));
  const showLength = record.tracks.some((t) => t.duration_sec != null);
  const colSpan = (selection ? 6 : 5) + (showKeys ? 1 : 0) - (showLength ? 0 : 1) + (audio?.searched ? 1 : 0);
  return (
    <table className={styles.table}>
      <caption className="sr">Tracklist</caption>
      <thead>
        <tr>
          {selection && (
            <th scope="col" className={styles.pick}>
              <input type="checkbox" aria-label="Select all tracks" checked={all}
                onChange={() => selection.onChange(all ? new Set() : new Set(record.tracks.map((t) => t.id)))} />
            </th>
          )}
          {audio?.searched && <th scope="col" aria-label="Play" />}
          <th scope="col">Pos</th>
          <th scope="col">Title</th>
          {showLength && <th scope="col" className={styles.num}>Length</th>}
          <th scope="col" className={styles.num}>BPM</th>
          {showKeys && <th scope="col">Key</th>}
          <th scope="col">Tags</th>
        </tr>
      </thead>
      <tbody>
        {record.tracks.map((track) => (
          <TrackRow
            key={track.id}
            track={track}
            record={record}
            editable={editable}
            keyFormat={keyFormat}
            showKeys={showKeys}
            open={open === track.id}
            working={busyIds?.has(track.id) ?? false}
            colSpan={colSpan}
            showLength={showLength}
            audio={audio?.view(track.position, track.id) ?? null}
            onUse={onUse}
            onPass={onPass}
            picked={selection ? selection.ids.has(track.id) : undefined}
            onPick={selection ? () => {
              const next = new Set(selection.ids);
              if (!next.delete(track.id)) next.add(track.id);
              selection.onChange(next);
            } : undefined}
            onToggle={() => setOpen(open === track.id ? null : track.id)}
          />
        ))}
      </tbody>
    </table>
  );
}

type RowProps = {
  track: TrackOut;
  record: RecordDetail;
  editable: boolean;
  keyFormat: KeyFormat;
  showKeys: boolean;
  open: boolean;
  working: boolean;
  colSpan: number;
  showLength: boolean;
  audio: TrackAudioView | null;
  onUse?: (track: TrackOut) => void;
  onPass?: (track: TrackOut) => void;
  picked?: boolean;
  onPick?: () => void;
  onToggle: () => void;
};

function TrackRow({ track, record, editable, keyFormat, showKeys, open, working, colSpan, showLength, audio, onUse, onPass, picked, onPick, onToggle }: RowProps) {
  const [confidenceOn] = useKeyConfidenceEnabled();
  const patch = usePatchTrack(record.id);
  const onEdit = (v: { bpm?: number; key?: string }) => patch.mutate({ trackId: track.id, patch: v });
  const trackNote = track.notes.map((n) => n.body.trim()).filter(Boolean).join(" · ");
  const raw = (track.analysis_raw ?? {}) as { status?: string; note?: string; measurements?: { origin: string; bpm?: number; camelot?: string }[] };
  const hasDetail = Boolean(raw.status || raw.measurements?.length || track.audio_path || track.analyzed_at
    || (showKeys && confidenceOn && track.confidence != null && !track.key_manual));
  const hasData = track.bpm != null || (showKeys && track.camelot_key != null) || track.proposal != null;

  return (
    <Fragment>
      <tr className={`${styles.row} ${open ? styles.open : ""} ${!hasData ? styles.none : ""} ${working ? styles.working : ""}`}>
        {picked !== undefined && (
          <td className={styles.pick}>
            <input type="checkbox" aria-label={`Select ${track.title}`} checked={picked} onChange={onPick} />
          </td>
        )}
        {audio && (
          <td className={styles.playCell}>
            {audio.playable && (
              <button type="button" className={`${styles.play} ${audio.playing ? styles.playing : ""}`} onClick={audio.toggle}
                aria-label={`${audio.playing ? "Pause" : "Play"} ${track.position || track.title}`}>{audio.playing ? "❚❚" : "▶"}</button>
            )}
          </td>
        )}
        <td className={styles.pos}>{track.position || "·"}</td>
        <th scope="row" className={styles.name}>
          <div className={styles.nameWrap}>
            <button type="button" className={styles.titleBtn} aria-expanded={hasDetail ? open : undefined} onClick={hasDetail ? onToggle : undefined}
              style={hasDetail ? undefined : { cursor: "default" }}>
              <b>{track.title}</b>
              {track.artist && track.artist.toLowerCase() !== record.artist.toLowerCase() && <span>{track.artist}</span>}
            </button>
            <QuickNote recordId={record.id} title={track.title} track={track} filled={track.notes.some((n) => n.body.trim() !== "")} />
          </div>
          {audio && (audio.review || !audio.playable) && (
            <div className={styles.audioLine} data-testid={`found-audio-${track.position}`}>
              {audio.playable ? <span className={styles.review}>needs a look</span> : <span>{audio.missing}</span>}
              {!audio.playable && audio.stores.map((st) => <a key={st.source} href={st.page} target="_blank" rel="noopener noreferrer">Find at {STORES[st.source] ?? st.source} ↗</a>)}
            </div>
          )}
          {trackNote && <ClampedNote as="em" text={trackNote} className={styles.noteLine} />}
        </th>
        {showLength && <td className={`${styles.num} ${styles.length}`}>{track.duration_sec != null ? formatDuration(track.duration_sec) : ""}</td>}
        <td className={styles.num}>
          <BpmCell track={track} editable={editable} keyFormat={keyFormat} showKeys={showKeys}
            onUse={onUse} onPass={onPass} onEdit={onEdit}
            onSave={(bpm) => patch.mutate({ trackId: track.id, patch: { bpm } })}
            onUnlock={() => patch.mutate({ trackId: track.id, patch: { unlock: ["bpm"] } })} />
        </td>
        {showKeys && (
          <td>
            <KeyCell track={track} keyFormat={keyFormat} editable={editable} showKeys={showKeys}
              onUse={onUse} onPass={onPass} onEdit={onEdit}
              onSave={(key) => patch.mutate({ trackId: track.id, patch: { key } })}
              onUnlock={() => patch.mutate({ trackId: track.id, patch: { unlock: ["key"] } })} />
          </td>
        )}
        <td className={styles.tagCell}>
          <div className={styles.tagWrap}>
            {(track.tags ?? []).map((t) => <i key={t} className={styles.tagChip}>{t}</i>)}
            {editable && <TrackTagButton track={track} label={`track ${track.position || track.title}`} />}
          </div>
        </td>
      </tr>
      {open && hasDetail && (
        <tr className={styles.detailRow}>
          <td colSpan={colSpan}>
            <dl className={styles.detail}>
              {raw.status && (<><dt>Result</dt><dd>{raw.status}{raw.note ? `: ${raw.note}` : ""}</dd></>)}
              {raw.measurements?.map((m, i) => (
                <Fragment key={i}>
                  <dt>{m.origin}</dt>
                  <dd>{[m.bpm ? `${formatBpm(m.bpm)} BPM` : "", showKeys ? m.camelot ?? "" : ""].filter(Boolean).join(" · ") || "no value"}</dd>
                </Fragment>
              ))}
              {showKeys && confidenceOn && track.confidence != null && !track.key_manual && (<><dt>Key confidence</dt><dd>{Math.round(track.confidence * 100)}%{track.confidence < LOW_CONFIDENCE ? ", low: check it by ear" : ""}</dd></>)}
              {track.audio_path && (<><dt>Audio file</dt><dd>{track.audio_path.split("/").pop()}</dd></>)}
              {track.analyzed_at && (<><dt>Analysed</dt><dd>{track.analyzed_at.replace("T", " ").replace("Z", "")}</dd></>)}
            </dl>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** A tag doodle on every track: opens a small pad to add or remove its tags. */
function TrackTagButton({ track, label }: { track: TrackOut; label: string }) {
  const [open, setOpen] = useState(false);
  const mutations = useTagMutations(track.record_id);
  const allTags = useTags();
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  const has = (track.tags ?? []).length > 0;
  return (
    <span className={styles.tagPop} ref={root} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <button type="button" className={styles.tagAdd} aria-expanded={open}
        aria-label={`${has ? "Edit tags" : "Add a tag"} for ${track.title}`} title={has ? "Edit tags" : "Add a tag"} onClick={() => setOpen(!open)}>
        {has ? "edit" : "+ tag"}
      </button>
      {open && (
        <div className={styles.pop} role="dialog" aria-label={`Tags for ${track.title}`}>
          <TagEditor label={label} tags={track.tags ?? []} options={allTags.data ?? []}
            onAdd={(name) => mutations.add.mutate({ kind: "track", id: track.id, name })}
            onRemove={(name) => mutations.remove.mutate({ kind: "track", id: track.id, name })} />
        </div>
      )}
    </span>
  );
}

/** The analysis waiting on a track, shown in its BPM and Key columns. Opens a small panel where the proposed values can be
 *  corrected before using them, with how sure the analysis was (when switched on), and the choice to use it or pass on it. */
type EditValues = { bpm?: number; key?: string };
type PopProps = {
  track: TrackOut; keyFormat: KeyFormat; showKeys: boolean; label: string; low?: boolean;
  onUse?: (t: TrackOut) => void; onPass?: (t: TrackOut) => void; onEdit: (v: EditValues) => void;
};

function ProposalPop({ track, keyFormat, showKeys, label, onUse, onPass, onEdit }: PopProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const p = track.proposal!;
  const [bpmDraft, setBpmDraft] = useState("");
  const [keyDraft, setKeyDraft] = useState("");
  useEffect(() => {
    if (!open) return;
    setBpmDraft(p.bpm != null ? String(p.bpm) : "");
    setKeyDraft(p.camelot_key ?? "");
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, p.bpm, p.camelot_key]);
  const [confidenceOn] = useKeyConfidenceEnabled();
  const low = showKeys && confidenceOn && p.confidence != null && p.confidence < LOW_CONFIDENCE;
  const use = () => {
    setOpen(false);
    const bpm = parseFloat(bpmDraft.replace(",", "."));
    const edit: EditValues = {};
    if (Number.isFinite(bpm) && bpm > 0 && bpm <= 400 && bpm !== p.bpm) edit.bpm = bpm;
    if (showKeys && keyDraft && keyDraft !== p.camelot_key) edit.key = keyDraft;
    if (edit.bpm == null && edit.key == null) { onUse?.(track); return; }
    // Corrected by hand: save the corrected values (marked manual) and let the rest of the proposal go.
    const keep: EditValues = { ...edit };
    if (keep.bpm == null && p.bpm != null) keep.bpm = p.bpm;
    if (showKeys && keep.key == null && p.camelot_key) keep.key = p.camelot_key;
    onEdit(keep);
    onPass?.(track);
  };
  return (
    <span className={styles.tagPop} ref={root} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <button type="button" className={styles.proposed} aria-expanded={open} aria-label={`Review the analysis for ${track.title}`}
        title="New analysis, waiting for you. Click to check or change it" onClick={() => setOpen(!open)}>→ {label}{low && label !== formatBpm(p.bpm) ? " · low" : ""}</button>
      {open && (
        <div className={styles.pop} role="dialog" aria-label={`Analysis for ${track.title}`}>
          <dl className={styles.popFacts}>
            {p.bpm != null && (<><dt>BPM</dt><dd>
              <input className={`field-input ${styles.bpmInput}`} type="number" step="0.1" min="1" max="400" aria-label={`Proposed BPM for ${track.title}`}
                value={bpmDraft} onChange={(e) => setBpmDraft(e.target.value)} />
            </dd></>)}
            {showKeys && p.camelot_key != null && (<><dt>Key</dt><dd>
              <select className="field-input" aria-label={`Proposed key for ${track.title}`} value={keyDraft} onChange={(e) => setKeyDraft(e.target.value)}>
                {SORTED_KEYS.map((k) => <option key={k.camelot} value={k.camelot}>{keyLabel(k.camelot, keyFormat)}</option>)}
              </select>
            </dd></>)}
            {showKeys && confidenceOn && p.confidence != null && (<><dt>Confidence</dt><dd>{Math.round(p.confidence * 100)}%</dd></>)}
          </dl>
          {low && <p className={styles.popWarn}>The analysis was unsure about this key. Check it by ear.</p>}
          <div className={styles.popActions}>
            {onUse && <button type="button" className="primary small" onClick={use}>Use</button>}
            {onPass && <button type="button" className="ghost small" onClick={() => { setOpen(false); onPass(track); }}>Pass</button>}
          </div>
        </div>
      )}
    </span>
  );
}

function KeyCell({ track, keyFormat, editable, showKeys, onSave, onUnlock, onUse, onPass, onEdit }: {
  track: TrackOut; keyFormat: KeyFormat; editable: boolean; showKeys: boolean; onSave: (key: string) => void; onUnlock: () => void;
  onUse?: (t: TrackOut) => void; onPass?: (t: TrackOut) => void; onEdit: (v: EditValues) => void;
}) {
  const label = keyLabel(track.camelot_key, keyFormat);
  const p = track.proposal;
  const proposed = p?.camelot_key != null && p.camelot_key !== track.camelot_key ? keyLabel(p.camelot_key, keyFormat) : "";
  return (
    <span className={`${styles.keyWrap} ${proposed ? styles.stack : ""}`}>
      {!label && proposed ? null : editable ? (
        <span className={styles.keyPick}>
          <span className={`${styles.key} ${!label ? styles.empty : ""}`} aria-hidden="true">{label || "set"}</span>
          <select
            className={styles.keySelect}
            aria-label={`Key for ${track.title}`}
            value={track.camelot_key ?? ""}
            onChange={(e) => e.target.value && onSave(e.target.value)}
          >
            <option value="">{label ? `${label} (current)` : "Not set"}</option>
            {SORTED_KEYS.map((k) => (
              <option key={k.camelot} value={k.camelot}>{k.camelot} · {k.name}</option>
            ))}
          </select>
        </span>
      ) : (
        <span className={`${styles.key} ${!label ? styles.empty : ""}`}>{label || "·"}</span>
      )}
      {track.key_manual && (
        <span className={styles.manual}>manual{editable && (
          <button type="button" aria-label={`Hand key for ${track.title} back to analysis`} title="Hand back to analysis" onClick={onUnlock}>×</button>
        )}</span>
      )}
      {proposed && (
        <ProposalPop track={track} keyFormat={keyFormat} showKeys={showKeys} label={proposed} onUse={onUse} onPass={onPass} onEdit={onEdit} />
      )}
    </span>
  );
}

function BpmCell({ track, editable, keyFormat, showKeys, onSave, onUnlock, onUse, onPass, onEdit }: {
  track: TrackOut; editable: boolean; keyFormat: KeyFormat; showKeys: boolean;
  onSave: (bpm: number) => void; onUnlock: () => void; onUse?: (t: TrackOut) => void; onPass?: (t: TrackOut) => void; onEdit: (v: EditValues) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const commit = () => {
    setEditing(false);
    const value = parseFloat(draft.replace(",", "."));
    if (Number.isFinite(value) && value > 0 && value <= 400 && value !== track.bpm) onSave(value);
  };

  if (editing) {
    return (
      <input
        className={`field-input ${styles.bpmInput}`}
        type="number" step="0.1" min="1" max="400" autoFocus
        aria-label={`BPM for ${track.title}`}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setEditing(false);
        }}
      />
    );
  }
  const value = track.bpm != null ? formatBpm(track.bpm) : "";
  const p = track.proposal;
  const newBpm = p?.bpm != null && p.bpm !== track.bpm;
  const proposalLabel = newBpm ? formatBpm(p!.bpm) : "";
  return (
    <span className={`${styles.bpmWrap} ${proposalLabel ? styles.stack : ""}`}>
      {!value && proposalLabel ? null : editable ? (
        <button type="button" className={styles.bpm} aria-label={`Edit BPM for ${track.title}`}
          onClick={() => { setDraft(value); setEditing(true); }}>
          {value || <span className={styles.dash}>set</span>}
        </button>
      ) : (
        <span className={styles.bpm}>{value || <span className={styles.dash}>·</span>}</span>
      )}
      {track.bpm_manual && (
        <span className={styles.manual}>manual{editable && (
          <button type="button" aria-label={`Hand BPM for ${track.title} back to analysis`} title="Hand back to analysis" onClick={onUnlock}>×</button>
        )}</span>
      )}
      {proposalLabel && (
        <ProposalPop track={track} keyFormat={keyFormat} showKeys={showKeys} label={proposalLabel} onUse={onUse} onPass={onPass} onEdit={onEdit} />
      )}
    </span>
  );
}
