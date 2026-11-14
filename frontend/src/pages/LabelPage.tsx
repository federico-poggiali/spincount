import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type LabelData } from "../api/api";
import { LabelEditor, withSavedLook } from "../components/LabelEditor";
import { fileStem, LabelPreview } from "../components/LabelPreview";
import { Skeleton } from "../components/Skeleton";
import { useDebounced, useLabelPresets } from "../hooks";
import styles from "./LabelPage.module.css";

export default function LabelPage() {
  const id = Number(useParams().id);
  const base = useQuery({
    queryKey: ["label", id], queryFn: () => api.getLabel(id), refetchOnWindowFocus: false,
  });
  const [edited, setEdited] = useState<LabelData | null>(null);
  // the database's label in the look last chosen in Customize; read again on reset, so a reset keeps it
  const label = useMemo(() => edited ?? (base.data ? withSavedLook(base.data) : null), [edited, base.data]);
  const settled = useDebounced(label, 250);
  const presets = useLabelPresets();
  const preview = useQuery({
    queryKey: ["label-render", id, settled],
    queryFn: () => api.renderLabel(id, settled!),
    enabled: settled != null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });

  if (base.isError) {
    const status = base.error instanceof ApiError ? base.error.status : null;
    const message = status === 404 ? "That record doesn't exist, so there is no label to make."
      : status === 409 ? "That record is on your wishlist. Labels are only for records you own."
      : "Couldn't load this label.";
    return (
      <div className={styles.missing}>
        <span className="micro">{status ?? "error"}</span>
        <h1>{message}</h1>
        <Link className="ghost" to="/">Back to the library</Link>
      </div>
    );
  }
  if (!label) return <Skeleton rows={6} />;

  const images = preview.data?.images ?? [];
  const warnings = preview.data?.warnings ?? [];

  return (
    <article className={styles.page}>
      <header className={styles.head}>
        <div>
          <span className="micro">label</span>
          <h1>{label.title}</h1>
          <p className={styles.sub}>{label.artist}</p>
        </div>
        <Link className="ghost" to={`/records/${id}`}>Back to the record</Link>
      </header>

      <div className={styles.layout}>
        <LabelEditor value={label} onChange={setEdited} presets={presets} />

        <LabelPreview images={images} warnings={warnings} stem={fileStem(label)} onReset={() => setEdited(null)} canReset={edited != null}
          hint="Edits are for this print only; the record is not changed. Black and white, 696 px wide: ready for a Brother QL with 62 mm tape." />
      </div>
    </article>
  );
}
