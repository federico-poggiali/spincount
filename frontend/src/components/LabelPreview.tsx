import { useState } from "react";
import type { LabelData, LabelImage } from "../api/api";
import styles from "../pages/LabelPage.module.css";

export const fileStem = (label: LabelData) => `${label.artist} - ${label.title}`.replace(/[\\/:*?"<>|]/g, "");

function download(image: LabelImage, stem: string) {
  const link = document.createElement("a");
  link.href = `data:image/png;base64,${image.png_base64}`;
  link.download = `${stem} (${image.name}).png`;
  link.click();
}

const imageTitle = (image: LabelImage) =>
  image.kind === "main" ? "Main label" : image.name === "tracks" ? "Tracks label" : `Tracks label ${image.name.split("-")[1]}`;

type Props = { images: LabelImage[]; warnings: string[]; stem: string; onReset: () => void; canReset: boolean; hint: string };

export function LabelPreview({ images, warnings, stem, onReset, canReset, hint }: Props) {
  // Labels left out of the print, by name. Kept across re-renders, so an edit doesn't bring them back.
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const isSkipped = (name: string) => images.length > 1 && skipped.has(name);  // a lone label has no tick to undo
  const chosen = images.filter((image) => !isSkipped(image.name));
  const choose = (name: string, on: boolean) => setSkipped((prev) => {
    const next = new Set(prev);
    if (on) next.delete(name); else next.add(name);
    return next;
  });
  const downloadAll = () => chosen.forEach((image, i) => setTimeout(() => download(image, stem), i * 250));
  return (
    <aside className={styles.preview} aria-label="Preview">
      <div className={styles.actions}>
        <button className="primary" onClick={downloadAll} disabled={chosen.length === 0}>
          Download {chosen.length > 1 ? `${chosen.length} labels` : "label"} (PNG)
        </button>
        <button className="ghost" onClick={onReset} disabled={!canReset}>Reset edits</button>
      </div>
      {warnings.length > 0 && (
        <ul className={styles.warnings} aria-label="Warnings">
          {warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
      <div className={styles.figures}>
      {images.map((image) => (
        <figure key={image.name} className={styles.figure} data-skipped={isSkipped(image.name) || undefined}>
          <img src={`data:image/png;base64,${image.png_base64}`} alt={`${imageTitle(image)} preview`} width={image.width} height={image.height} />
          <figcaption>
            <label className={styles.choose}>
              {images.length > 1 && (
                <input type="checkbox" checked={!isSkipped(image.name)} aria-label={`Print ${imageTitle(image).toLowerCase()}`}
                  onChange={(e) => choose(image.name, e.target.checked)} />
              )}
              <span className="micro">{imageTitle(image)} · 62 × 40 mm</span>
            </label>
            <button className="ghost small" onClick={() => download(image, stem)}>Download</button>
          </figcaption>
        </figure>
      ))}
      </div>
      <p className={styles.hint}>{hint}</p>
    </aside>
  );
}
