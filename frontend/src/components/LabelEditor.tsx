import { useEffect, useId, useState, type CSSProperties, type FormEvent } from "react";
import type { Design, LabelData, LabelLook, LabelPreset, LabelSizes, LabelTrack } from "../api/api";
import styles from "./LabelEditor.module.css";

type MainHidden = NonNullable<LabelData["hidden"]>[number];
type TrackHidden = NonNullable<LabelTrack["hidden"]>[number];

export const parseList = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);
const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((v, i) => v === b[i]);

function toggled<T>(list: T[] | undefined, item: T, on: boolean): T[] {
  const rest = (list ?? []).filter((x) => x !== item);
  return on ? rest : [...rest, item];
}

type FieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  hint?: string;
  /** Accessible name when the visible label is not unique (one per track). */
  name?: string;
  /** Takes the whole row of the grid. */
  wide?: boolean;
  /** A few characters (BPM, key): a narrow box. */
  narrow?: boolean;
};

function Field({ label, value, onChange, multiline, hint, name = label, wide, narrow }: FieldProps) {
  const id = useId();
  const Control = multiline ? "textarea" : "input";
  return (
    <div className={styles.field} data-wide={wide || undefined} data-narrow={narrow || undefined}>
      <label htmlFor={id} className="micro">{label}</label>
      <Control
        id={id} className="field-input" value={value} placeholder={hint} aria-label={name}
        onChange={(e) => onChange(e.target.value)}
        {...(multiline ? { rows: 2 } : {})}
      />
    </div>
  );
}

/** A comma-separated list. Keeps what is being typed (a trailing comma) until it is a real item. */
function ListField({ value, onChange, ...rest }: Omit<FieldProps, "value" | "onChange"> & { value: string[]; onChange: (v: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => {
    if (!sameList(parseList(text), value)) setText(value.join(", "));
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  return <Field {...rest} value={text} onChange={(t) => { setText(t); onChange(parseList(t)); }} />;
}

// ---- Customize: the design, what is printed and how big. The look last used is remembered per browser,
// so every label starts from it; presets are named looks kept in the database.

export const DEFAULT_SIZES: LabelSizes = { artist: 1, details: 1, title: 1, info: 1, note: 1, tracks: 1 };
const LOOK_KEY = "spincount.labellook";
const MAIN_FIELDS: MainHidden[] = ["label", "catno", "year", "country", "styles", "note", "qr"];
const TRACK_FIELDS: TrackHidden[] = ["artist", "bpm", "key", "tags", "note"];

const DESIGN_FAMILIES: { family: string; designs: { design: Design; label: string }[] }[] = [
  { family: "Glitchy", designs: [{ design: "glitchy", label: "Current" }, { design: "corrupted", label: "Corrupted" }] },
  { family: "Classic", designs: [{ design: "penguin", label: "Penguin" }] },
  { family: "90s", designs: [{ design: "republic", label: "Republic" }, { design: "factory", label: "Factory" }] },
];
const DESIGNS = DESIGN_FAMILIES.flatMap((f) => f.designs);
const designName = (design: Design) => DESIGNS.find((d) => d.design === design)?.label ?? design;

const USUAL_LOOK: LabelLook = { design: "glitchy", sizes: DEFAULT_SIZES, hidden: [], track_hidden: [] };

/** A look from anywhere (storage, a preset), with anything unknown or out of range dropped. */
function cleanLook(raw: Partial<LabelLook> & { trackHidden?: unknown }): LabelLook {
  const sizes = { ...DEFAULT_SIZES };
  for (const key of Object.keys(sizes) as (keyof LabelSizes)[]) {
    const v = raw.sizes?.[key];
    if (typeof v === "number" && v >= 0.6 && v <= 1.6) sizes[key] = v;
  }
  const trackHidden = raw.track_hidden ?? raw.trackHidden;  // trackHidden: how the first version stored it
  return {
    design: DESIGNS.some((d) => d.design === raw.design) ? raw.design! : "glitchy",
    sizes,
    hidden: Array.isArray(raw.hidden) ? MAIN_FIELDS.filter((f) => raw.hidden!.includes(f)) : [],
    track_hidden: Array.isArray(trackHidden) ? TRACK_FIELDS.filter((f) => (trackHidden as string[]).includes(f)) : [],
  };
}

/** The look last chosen in Customize. */
export function savedLook(): LabelLook {
  try {
    return cleanLook(JSON.parse(localStorage.getItem(LOOK_KEY) ?? "{}"));
  } catch {
    return { ...USUAL_LOOK }; // private mode, or something unreadable
  }
}

function rememberLook(look: LabelLook) {
  try {
    localStorage.setItem(LOOK_KEY, JSON.stringify(look));
  } catch {
    /* not remembered */
  }
}

/** The look a label is in. With no tracks to carry the track choices, they come from the remembered look. */
export function lookOf(label: LabelData): LabelLook {
  const tracks = label.tracks ?? [];
  return cleanLook({
    design: label.design, sizes: label.sizes, hidden: label.hidden,
    track_hidden: tracks.length ? tracks[0].hidden ?? [] : savedLook().track_hidden,
  });
}

export function applyLook(label: LabelData, look: LabelLook): LabelData {
  return {
    ...label, design: look.design, sizes: { ...look.sizes }, hidden: [...look.hidden],
    tracks: (label.tracks ?? []).map((t) => ({ ...t, hidden: [...look.track_hidden] })),
  };
}

/** `label` in the look last chosen. */
export const withSavedLook = (label: LabelData) => applyLook(label, savedLook());

const sameLook = (a: LabelLook, b: LabelLook) => JSON.stringify(cleanLook(a)) === JSON.stringify(cleanLook(b));

/** Saved presets and what to do with them; the page supplies them (they live in the database). */
export type PresetControls = {
  items: LabelPreset[];
  save: (name: string, look: LabelLook) => void;
  remove: (id: number) => void;
};

const MAIN_TOGGLES: { field: MainHidden; label: string }[] = [
  { field: "label", label: "Label" }, { field: "catno", label: "Cat#" }, { field: "year", label: "Year" },
  { field: "country", label: "Country" }, { field: "styles", label: "Styles" }, { field: "note", label: "Note" },
  { field: "qr", label: "QR code" },
];
const TRACK_TOGGLES: { field: TrackHidden; label: string }[] = [
  { field: "artist", label: "Artist" }, { field: "bpm", label: "BPM" }, { field: "key", label: "Key" },
  { field: "tags", label: "Tags" }, { field: "note", label: "Note" },
];
const SIZE_ROWS: { key: keyof LabelSizes; label: string; hint?: string }[] = [
  { key: "artist", label: "Artist" },
  { key: "details", label: "Label · Cat#" },
  { key: "title", label: "Title" },
  { key: "info", label: "Year · styles" },
  { key: "note", label: "Note", hint: "The largest it gets: a short note grows to fill the label" },
  { key: "tracks", label: "Tracks label" },
];

function Toggle({ label, name, on, onChange }: { label: string; name: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className={styles.chip}>
      <input type="checkbox" checked={on} aria-label={name} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function Presets({ look, presets, onApply }: { look: LabelLook; presets: PresetControls; onApply: (look: LabelLook) => void }) {
  const [name, setName] = useState("");
  const existing = presets.items.find((p) => p.name.toLowerCase() === name.trim().toLowerCase());
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    presets.save(name.trim(), look);
    setName("");
  };
  return (
    <div className={styles.toggleGroup}>
      <span className="micro">Presets</span>
      {presets.items.length > 0 && (
        <div className={styles.chips}>
          {presets.items.map((p) => (
            <span key={p.id} className={styles.preset} data-active={sameLook(p.look, look) || undefined}>
              <button type="button" aria-pressed={sameLook(p.look, look)} onClick={() => onApply(cleanLook(p.look))}
                title={`${designName(cleanLook(p.look).design)} · apply to this label`}>{p.name}</button>
              <button type="button" className={styles.presetDelete} aria-label={`Delete preset ${p.name}`}
                onClick={() => presets.remove(p.id)}>×</button>
            </span>
          ))}
        </div>
      )}
      <form className={styles.presetForm} onSubmit={submit}>
        <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
          placeholder="Name this look to reuse it" aria-label="Preset name" />
        <button type="submit" className="ghost small" disabled={!name.trim()}>{existing ? "Replace" : "Save preset"}</button>
      </form>
    </div>
  );
}

function Customize({ value, onChange, presets }: { value: LabelData; onChange: (next: LabelData) => void; presets?: PresetControls }) {
  const [open, setOpen] = useState(false);
  const look = lookOf(value);
  const setLook = (next: LabelLook) => { rememberLook(next); onChange(applyLook(value, next)); };
  const sizes = look.sizes;
  const hiddenCount = look.hidden.length + look.track_hidden.length;
  const resized = SIZE_ROWS.some(({ key }) => sizes[key] !== 1);
  const preset = presets?.items.find((p) => sameLook(p.look, look));
  const summary = [preset ? `${preset.name} (${designName(look.design)})` : designName(look.design),
    hiddenCount > 0 && `${hiddenCount} hidden`, resized && "resized"].filter(Boolean).join(" · ");
  return (
    <section aria-label="Customize" className={styles.customize} data-open={open || undefined}>
      <button type="button" className={styles.customizeToggle} aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>Customize</span>
        <span className={styles.customizeState}>{summary}</span>
        <span aria-hidden className={styles.chevron}>▾</span>
      </button>
      {open && (
        <div className={styles.customizeBody}>
          <div className={styles.toggleGroup}>
            <span className="micro">Design</span>
            <div className={styles.families}>
              {DESIGN_FAMILIES.map(({ family, designs }) => (
                <div key={family} className={styles.family} role="group" aria-label={family}
                  style={{ "--n": designs.length } as CSSProperties}>
                  <span className={styles.familyName}>{family}</span>
                  <div className={styles.segments}>
                    {designs.map(({ design, label }) => (
                      <button key={design} type="button" aria-pressed={look.design === design}
                        aria-label={`${family} ${label}`} onClick={() => setLook({ ...look, design })}>{label}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
          {presets && <Presets look={look} presets={presets} onApply={setLook} />}
          <div className={styles.toggleGroup}>
            <span className="micro">Main label shows</span>
            <div className={styles.chips}>
              {MAIN_TOGGLES.filter(({ field }) => field !== "qr" || value.qr_url).map(({ field, label }) => (
                <Toggle key={field} label={label} name={`Print ${label.toLowerCase()}`} on={!look.hidden.includes(field)}
                  onChange={(on) => setLook({ ...look, hidden: toggled(look.hidden, field, on) })} />
              ))}
            </div>
          </div>
          <div className={styles.toggleGroup}>
            <span className="micro">Tracks label shows</span>
            <div className={styles.chips}>
              {TRACK_TOGGLES.map(({ field, label }) => (
                <Toggle key={field} label={label} name={`Print track ${label.toLowerCase()}`} on={!look.track_hidden.includes(field)}
                  onChange={(on) => setLook({ ...look, track_hidden: toggled(look.track_hidden, field, on) })} />
              ))}
            </div>
          </div>
          <div className={styles.toggleGroup}>
            <span className="micro">Text size</span>
            <div className={styles.sizes}>
              {SIZE_ROWS.map(({ key, label, hint }) => (
                <div key={key} className={styles.size} title={hint}>
                  <span>{label}</span>
                  <input type="range" min={0.6} max={1.6} step={0.05} value={sizes[key]} aria-label={`${label} size`}
                    onChange={(e) => setLook({ ...look, sizes: { ...sizes, [key]: Number(e.target.value) } })} />
                  <output className="mono">{Math.round(sizes[key] * 100)}%</output>
                </div>
              ))}
            </div>
          </div>
          <div className={styles.customizeFoot}>
            <p className={styles.empty}>Text still shrinks when it would not fit. Your last look is kept for the next label.</p>
            <button type="button" className="ghost small" disabled={sameLook(look, USUAL_LOOK)} onClick={() => setLook({ ...USUAL_LOOK })}>
              Reset
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

type Props = {
  value: LabelData;
  onChange: (next: LabelData) => void;
  /** A label with no record behind it: tracks can be added, renamed and removed. */
  loose?: boolean;
  presets?: PresetControls;
};

export function LabelEditor({ value, onChange, loose, presets }: Props) {
  const set = <K extends keyof LabelData>(key: K, v: LabelData[K]) => onChange({ ...value, [key]: v });
  const text = (key: "label" | "catno" | "year" | "country" | "note") => (v: string) => set(key, v === "" ? null : v);
  // a field left off the label (in Customize) is left out of the form too
  const shown = (field: MainHidden) => !(value.hidden ?? []).includes(field);
  const setTrack = (i: number, patch: Partial<LabelTrack>) =>
    set("tracks", (value.tracks ?? []).map((t, n) => (n === i ? { ...t, ...patch } : t)));

  return (
    <div className={styles.editor}>
      <Customize value={value} onChange={onChange} presets={presets} />

      <section aria-label="Main label" className={styles.group}>
        <h2>Main label</h2>
        <div className={styles.grid}>
        <Field label="Artist" value={value.artist} onChange={(v) => set("artist", v)} wide />
        <Field label="Title" value={value.title} onChange={(v) => set("title", v)} wide />
        {shown("label") && <Field label="Label" value={value.label ?? ""} onChange={text("label")} />}
        {shown("catno") && <Field label="Cat#" value={value.catno ?? ""} onChange={text("catno")} />}
        {shown("year") && <Field label="Year" value={value.year ?? ""} onChange={text("year")} />}
        {shown("country") && <Field label="Country" value={value.country ?? ""} onChange={text("country")} hint="Not stored: type it in" />}
        {shown("styles") && <ListField label="Styles" value={value.styles ?? []} onChange={(v) => set("styles", v)} hint="Comma separated" />}
        {shown("note") && <Field label="Note" value={value.note ?? ""} onChange={text("note")} multiline hint="One sentence" wide />}
        </div>
      </section>

      <section aria-label="Tracks label" className={styles.group}>
        <div className={styles.head}>
          <h2>Tracks label</h2>
          {(value.tracks ?? []).length > 1 && (
            <div className={styles.bulk}>
              <button type="button" className="ghost small" onClick={() => set("tracks", (value.tracks ?? []).map((t) => ({ ...t, skip: false })))}>All</button>
              <button type="button" className="ghost small" onClick={() => set("tracks", (value.tracks ?? []).map((t) => ({ ...t, skip: true })))}>None</button>
            </div>
          )}
        </div>
        {(value.tracks ?? []).length === 0 && <p className={styles.empty}>{loose ? "No tracks yet." : "This record has no tracks."}</p>}
        {(value.tracks ?? []).map((t, i) => {
          const trackShown = (f: TrackHidden) => !(t.hidden ?? []).includes(f);
          return (
            <div key={i} role="group" aria-label={`Track ${t.position}`} className={styles.track} data-skipped={t.skip || undefined}>
              <div className={styles.trackHead}>
                <label className={styles.include}>
                  <input type="checkbox" checked={!t.skip} onChange={(e) => setTrack(i, { skip: !e.target.checked })}
                    aria-label={`Include track ${t.position}`} />
                  {loose ? null : <span className="mono">{t.position}</span>}
                </label>
                {loose && (
                  <>
                    <input className="field-input" aria-label={`Position of track ${i + 1}`} value={t.position} size={4}
                      onChange={(e) => setTrack(i, { position: e.target.value })} />
                    <button type="button" className="ghost small" aria-label={`Remove track ${t.position}`}
                      onClick={() => set("tracks", (value.tracks ?? []).filter((_, n) => n !== i))}>Remove</button>
                  </>
                )}
              </div>
              <div className={styles.trackFields}>
                {t.artist && trackShown("artist") && <Field label="Artist" name={`Artist ${t.position}`} value={t.artist} onChange={(v) => setTrack(i, { artist: v || null })} wide />}
                {trackShown("bpm") && <Field label="BPM" name={`BPM ${t.position}`} value={t.bpm ?? ""} onChange={(v) => setTrack(i, { bpm: v || null })} narrow />}
                {trackShown("key") && <Field label="Key" name={`Key ${t.position}`} value={t.key ?? ""} onChange={(v) => setTrack(i, { key: v || null })} narrow />}
                {trackShown("tags") && <ListField label="Tags" name={`Tags ${t.position}`} value={t.tags ?? []} onChange={(v) => setTrack(i, { tags: v })} />}
                {trackShown("note") && <Field label="Note" name={`Note ${t.position}`} value={t.note ?? ""} onChange={(v) => setTrack(i, { note: v || null })} />}
              </div>
            </div>
          );
        })}
        {loose && (
          <button type="button" className="ghost" onClick={() => set("tracks", [...(value.tracks ?? []), { position: nextPosition(value.tracks ?? []), skip: false, tags: [], hidden: lookOf(value).track_hidden }])}>
            Add track
          </button>
        )}
      </section>
    </div>
  );
}

/** A1, A2, ... then B1: carries on from the last track's side. */
function nextPosition(tracks: LabelTrack[]) {
  const last = tracks[tracks.length - 1]?.position ?? "";
  const m = /^([A-Za-z]*)(\d*)$/.exec(last);
  if (!m || !m[1]) return tracks.length === 0 ? "A1" : String(tracks.length + 1);
  return `${m[1]}${(Number(m[2]) || 0) + 1}`;
}
