import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { type CrateOut, type CrateRecord, type CubeOut } from "../../api/api";
import { Cover } from "../../components/Cover";
import { ShelfSelect } from "../../components/ShelfSelect";
import type { Place } from "../../crate";
import styles from "./crate.module.css";

export const MAX_X = 60; // the wall's size limit, in cubes
export const MAX_Y = 30;
export const DRAG_TYPE = "application/x-spincount-record";

export type Mode = "dig" | "build";
export type Selection = { kind: "cube" | "unit"; id: number } | null;
export type Rect = { x: number; y: number; rows: number; cols: number };
export type Act = (fn: () => Promise<CrateOut | void>) => void;
/** copyId is set when a second (or later) copy moves; copy 1 moves the record itself. */
export type PlaceRecord = (recordId: number, sectionId: number | null, copyId?: number | null) => void;

/** A list key that tells two copies of one record apart. */
export const rowKey = (r: CrateRecord) => `${r.id}-${r.copy_number ?? 1}`;

export const cubeCount = (cube: CubeOut) => cube.sections.reduce((n, s) => n + s.records.length, 0);

export function overlaps(a: Rect, b: Rect) {
  return a.x < b.x + b.cols && b.x < a.x + a.cols && a.y < b.y + b.rows && b.y < a.y + a.rows;
}

export const matches = (r: CrateRecord, q: string) => `${r.artist} ${r.title}`.toLowerCase().includes(q);

export function RecordRow({ record, sectionId, places, onPlace, children }: {
  record: CrateRecord; sectionId: number | null; places: Map<number, Place>; onPlace: PlaceRecord; children?: ReactNode;
}) {
  return (
    <li className={styles.row} draggable={record.copy_id == null}
      onDragStart={(e) => { e.dataTransfer.setData(DRAG_TYPE, String(record.id)); e.dataTransfer.effectAllowed = "move"; }}>
      <span className={styles.grip} aria-hidden="true">{record.copy_id == null ? "⋮⋮" : ""}</span>
      <Cover url={record.cover_url} size={40} />
      <div className={styles.rowText}>
        <Link to={`/records/${record.id}`}><b>{record.title}</b>{record.copy_id != null && <span className={styles.copyTag}> copy {record.copy_number}</span>}</Link>
        <span>{record.artist}{record.year ? ` · ${record.year}` : ""}</span>
        {children}
      </div>
      <ShelfSelect className={styles.move} value={sectionId} places={places} label={`Move ${record.title}`} onChange={(id) => onPlace(record.id, id, record.copy_id)} />
    </li>
  );
}

/** A text field that saves when you leave it or press Enter. */
export function Inline({ value, onSave, label, placeholder, multiline }: { value: string; onSave: (v: string) => void; label: string; placeholder?: string; multiline?: boolean }) {
  const [text, setText] = useState(value);
  const commit = () => text.trim() !== value && onSave(text.trim());
  const props = {
    className: "field-input", "aria-label": label, placeholder, value: text,
    onChange: (e: { target: { value: string } }) => setText(e.target.value), onBlur: commit,
  };
  return multiline ? <textarea {...props} rows={2} /> : <input {...props} onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()} />;
}
