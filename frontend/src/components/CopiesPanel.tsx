import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CopyOut } from "../api/api";
import { placesOf } from "../crate";
import { ShelfSelect } from "./ShelfSelect";
import styles from "./CopiesPanel.module.css";

/** Each copy of an owned record and where it sits on the shelf. Copy 1 is the record itself, so
 *  moving it is the same as moving the record in the crate. */
export function CopiesPanel({ recordId }: { recordId: number }) {
  const client = useQueryClient();
  const key = ["copies", recordId];
  const copies = useQuery({ queryKey: key, queryFn: () => api.listCopies(recordId) });
  const crate = useQuery({ queryKey: ["crate"], queryFn: api.getCrate });
  const places = useMemo(() => placesOf(crate.data?.units ?? []), [crate.data]);
  const done = (list: CopyOut[]) => { client.setQueryData(key, list); client.invalidateQueries({ queryKey: ["crate"] }); };
  const move = useMutation({
    mutationFn: async ({ copy, section }: { copy: CopyOut; section: number | null }) => {
      if (copy.copy_id == null) { await api.place([recordId], section); return api.listCopies(recordId); }
      return api.placeCopy(copy.copy_id, section);
    },
    onSuccess: done,
  });
  const add = useMutation({ mutationFn: () => api.addCopy(recordId), onSuccess: done });
  const drop = useMutation({ mutationFn: (copyId: number) => api.deleteCopy(copyId), onSuccess: done });

  const list = copies.data ?? [];
  if (!copies.data) return null;
  return (
    <section className={styles.panel} aria-labelledby={`copies-${recordId}`}>
      <h3 id={`copies-${recordId}`}>{list.length === 1 ? "Copy" : `${list.length} copies`}</h3>
      <ul className={styles.list}>
        {list.map((c) => (
          <li key={c.copy_id ?? "first"} className={styles.row}>
            <span className={styles.number}>#{c.number}</span>
            <ShelfSelect className={styles.select} value={c.section_id} places={places} label={`Shelf place of copy ${c.number}`}
              onChange={(section) => move.mutate({ copy: c, section })} />
            {c.copy_id != null && (
              <button className="ghost small" onClick={() => drop.mutate(c.copy_id!)} disabled={drop.isPending} aria-label={`Remove copy ${c.number}`}>Remove</button>
            )}
          </li>
        ))}
      </ul>
      <button className={styles.link} onClick={() => add.mutate()} disabled={add.isPending}>I have another copy</button>
      {places.size === 0 && <p className={styles.hint}>Draw your shelf on the Crate page to give each copy a place.</p>}
    </section>
  );
}
