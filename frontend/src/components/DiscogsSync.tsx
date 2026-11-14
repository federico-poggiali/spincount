import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AppSettings, type JobOut, type SyncItem } from "../api/api";
import { plural } from "../lib";
import { pushToast } from "../toast";
import { JobChip } from "./JobChip";
import styles from "./DiscogsSync.module.css";

type Kind = "push" | "pull" | "reset" | "wantlist" | "tidy" | "refresh";
const LABEL: Record<Kind, string> = {
  push: "To Discogs", pull: "From Discogs", reset: "Reset", wantlist: "Wantlist", tidy: "Wantlist tidy", refresh: "Refresh details",
};

/** Settings: keep the library and Discogs in step. Anything that writes to Discogs shows the records
 *  first and asks; importing runs on a click; a reset needs the word RESET and a last alert. */
export function DiscogsSync() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["app-settings"], queryFn: api.getSettings });
  const save = useMutation({ mutationFn: api.patchSettings, onSuccess: (s) => client.setQueryData(["app-settings"], s) });
  const compare = useQuery({ queryKey: ["discogs-compare"], queryFn: api.compareDiscogs, enabled: false, retry: false });
  const [job, setJob] = useState<{ kind: Kind; id: number; running: boolean } | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [word, setWord] = useState("");

  const started = (kind: Kind) => ({ job_id }: { job_id: number }) => setJob({ kind, id: job_id, running: true });
  const push = useMutation({ mutationFn: api.pushToDiscogs, onSuccess: started("push") });
  const pull = useMutation({ mutationFn: api.pullFromDiscogs, onSuccess: started("pull") });
  const wantlist = useMutation({ mutationFn: api.wantlistPush, onSuccess: started("wantlist") });
  const tidy = useMutation({ mutationFn: api.wantlistTidy, onSuccess: started("tidy") });
  const refresh = useMutation({ mutationFn: api.refreshFromDiscogs, onSuccess: started("refresh") });
  const reset = useMutation({ mutationFn: api.resetFromDiscogs, onSuccess: (r) => { setResetOpen(false); setWord(""); started("reset")(r); } });
  const forget = useMutation({ mutationFn: api.forgetKept, onSuccess: () => compare.refetch() });
  const busy = [push, pull, wantlist, tidy, refresh, reset].some((m) => m.isPending) || !!job?.running;

  const data = compare.data;
  const incoming = (data?.to_import.length ?? 0) + (data?.to_trade.length ?? 0) + (data?.to_copy.length ?? 0);

  const confirmReset = () => {
    const n = data?.reset;
    if (window.confirm(`Last check. This deletes ${plural(n?.records ?? 0, "owned record")}, with their BPM/key, notes, tags and shelf places, `
      + "then imports your Discogs collection. A backup of the database is made first. Continue?"))
      reset.mutate(word);
  };
  const settled = (done: JobOut) => {
    setJob((j) => (j && j.id === done.id ? { ...j, running: false } : j));
    if (done.status === "done") pushToast(summary(done), "info");
    client.invalidateQueries({ queryKey: ["records"] });
    client.invalidateQueries({ queryKey: ["crate"] });
    if (data) compare.refetch();
  };
  const retry = () => {
    if (job?.kind === "pull") pull.mutate();
    else if (job?.kind === "refresh") refresh.mutate();
    else if (job?.kind === "reset") setResetOpen(true);
    else setJob(null); // a Discogs write is redone from its list, with its confirmation
  };

  return (
    <section className={styles.sync} aria-labelledby="discogs-sync">
      <header>
        <span className="micro">discogs</span>
        <h2 id="discogs-sync">Sync with Discogs</h2>
      </header>

      <label className={styles.toggle}>
        <input type="checkbox" checked={settings.data?.auto_collection ?? true} disabled={!settings.data || save.isPending}
          onChange={(e) => save.mutate({ auto_collection: e.target.checked })} />
        <span>Add records I own to my Discogs collection automatically</span>
      </label>
      <label className={styles.toggle}>
        <input type="checkbox" checked={settings.data?.auto_wantlist ?? false} disabled={!settings.data || save.isPending}
          onChange={(e) => save.mutate({ auto_wantlist: e.target.checked })} />
        <span>Add wishlist records to my Discogs wantlist automatically</span>
      </label>
      <p className={styles.hint}>For records you add from now on, and records you move between the wishlist and the library.</p>

      <div className={styles.schedule}>
        <Every label="Import from Discogs" settingsKey="import_every_min" settings={settings.data} onSave={(v) => save.mutate(v)} />
        <Every label="Add to Discogs" settingsKey="push_every_min" settings={settings.data} onSave={(v) => save.mutate(v)} />
      </div>
      <p className={styles.hint}>
        On a schedule, import brings in records added on Discogs, and add puts every owned record Discogs lacks into your collection.
        Removing and resetting never run on their own. Leave both on "when I ask" to sync only from the lists below.
      </p>

      <div className={styles.actions}>
        <button className="ghost" onClick={() => compare.refetch()} disabled={compare.isFetching}>
          {compare.isFetching ? "Comparing…" : data ? "Compare again" : "Compare with Discogs"}
        </button>
        <button className="ghost" onClick={() => refresh.mutate()} disabled={busy}>Refresh details from Discogs</button>
        {data && <span className={styles.hint}>{plural(data.owned_count, "owned record")} here · {plural(data.discogs_count, "release")} on Discogs</span>}
      </div>
      <p className={styles.hint}>Refresh fetches titles, covers, labels and tracklists again. Your BPM, key, notes, tags, shelf places and edited styles stay; tracks are never deleted.</p>
      {compare.isError && <p className={styles.error} role="alert">Couldn't reach Discogs: {(compare.error as Error).message}</p>}
      {job && <JobChip label={LABEL[job.kind]} jobId={job.id} onSettled={settled} retrying={busy} onRetry={retry} />}

      {data && (
        <div className={styles.cards}>
          <PickCard title="Spin Count → Discogs collection" items={data.to_discogs} busy={busy} empty="Nothing to add."
            hint="Owned here, missing from your Discogs collection. Untick any you don't want to add."
            action={(n) => `Add ${plural(n, "record")} to Discogs…`}
            confirm={(n) => `Add ${plural(n, "record")} to your Discogs collection? This changes your Discogs account.`}
            onConfirm={(ids) => push.mutate(ids)} />

          <article className={styles.card}>
            <h3>Discogs collection → Spin Count</h3>
            <p className={styles.hint}>In your Discogs collection, missing here. Imported as owned, without the audio search. Wishlist ones move to the library and show under Recently traded.</p>
            {incoming === 0 ? <p className={styles.same}>Nothing to import.</p> : (
              <>
                <ul className={styles.list}>
                  {data.to_import.map((r) => <li key={r.discogs_release_id}><Item r={r} tag="new" /></li>)}
                  {data.to_trade.map((r) => <li key={r.discogs_release_id}><Item r={r} tag="from wishlist" /></li>)}
                  {data.to_copy.map((r) => <li key={r.discogs_release_id}><Item r={r} tag={`${r.copies} copies on Discogs, ${r.here} here`} /></li>)}
                </ul>
                <button className="primary" onClick={() => pull.mutate()} disabled={busy}>Import {plural(incoming, "change")}</button>
              </>
            )}
            {data.kept.length > 0 && (
              <>
                <p className={styles.hint}>Deleted here but kept on Discogs, so imports skip them:</p>
                <ul className={styles.list}>
                  {data.kept.map((r) => (
                    <li key={r.discogs_release_id}>
                      <span className={styles.item}>
                        <span className={styles.name}><b>{r.artist}</b> · {r.title}</span>
                        <button className={`ghost small ${styles.tag}`} onClick={() => forget.mutate(r.discogs_release_id)} disabled={forget.isPending}>Import again</button>
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </article>

          <PickCard title="Wishlist → Discogs wantlist" items={data.to_wantlist} busy={busy} empty="Your wishlist is all on the Discogs wantlist."
            hint="On your wishlist here, not on your Discogs wantlist. This only goes one way: the Discogs wantlist is never imported."
            action={(n) => `Add ${plural(n, "record")} to the wantlist…`}
            confirm={(n) => `Add ${plural(n, "record")} to your Discogs wantlist? This changes your Discogs account.`}
            onConfirm={(ids) => wantlist.mutate(ids)} />

          <PickCard title="Owned, still on your Discogs wantlist" items={data.owned_wanted} busy={busy} empty="No owned record is on your wantlist."
            hint="Records you own that your Discogs wantlist still asks for. Untick any you want to keep wanting."
            action={(n) => `Remove ${plural(n, "record")} from the wantlist…`}
            confirm={(n) => `Remove ${plural(n, "record")} from your Discogs wantlist? This changes your Discogs account.`}
            onConfirm={(ids) => tidy.mutate(ids)} />

          <article className={`${styles.card} ${styles.danger}`}>
            <h3>Reset from Discogs</h3>
            <p className={styles.hint}>
              Deletes every owned record here ({plural(data.reset.records, "record")}, {plural(data.reset.analysed_tracks, "analysed track")},
              {" "}{plural(data.reset.notes, "note")}, tags and shelf places), then imports your whole Discogs collection, including
              records you once deleted here. The wishlist is kept. A database backup is made first.
            </p>
            {!resetOpen ? (
              <button className="ghost" onClick={() => setResetOpen(true)} disabled={busy}>Reset library from Discogs…</button>
            ) : (
              <div className={styles.confirm}>
                <label htmlFor="reset-word">Type <b className="mono">RESET</b> to confirm</label>
                <input id="reset-word" className="mono" value={word} autoComplete="off" spellCheck={false} onChange={(e) => setWord(e.target.value)} />
                <div className={styles.actions}>
                  <button className={styles.destroy} onClick={confirmReset} disabled={word !== "RESET" || busy}>Erase and import</button>
                  <button className="ghost" onClick={() => { setResetOpen(false); setWord(""); }}>Cancel</button>
                </div>
              </div>
            )}
          </article>
        </div>
      )}
    </section>
  );
}

/** A list that writes to Discogs: every record ticked by default, untick to leave one out, then a
 *  confirmation names the count before anything is sent. */
function PickCard({ title, hint, empty, items, busy, action, confirm, onConfirm }: {
  title: string; hint: string; empty: string; items: SyncItem[]; busy: boolean;
  action: (n: number) => string; confirm: (n: number) => string; onConfirm: (ids: number[]) => void;
}) {
  const [unpicked, setUnpicked] = useState<Set<number>>(new Set());
  useEffect(() => setUnpicked(new Set()), [items]);
  const picked = items.filter((r) => !unpicked.has(r.id!));
  return (
    <article className={styles.card}>
      <h3>{title}</h3>
      <p className={styles.hint}>{hint}</p>
      {items.length === 0 ? <p className={styles.same}>{empty}</p> : (
        <>
          <ul className={styles.list}>
            {items.map((r) => (
              <li key={r.discogs_release_id}>
                <label>
                  <input type="checkbox" checked={!unpicked.has(r.id!)} onChange={(e) => setUnpicked((s) => toggle(s, r.id!, !e.target.checked))} />
                  <Item r={r} />
                </label>
              </li>
            ))}
          </ul>
          <button className="primary" disabled={busy || picked.length === 0}
            onClick={() => window.confirm(confirm(picked.length)) && onConfirm(picked.map((r) => r.id!))}>
            {action(picked.length)}
          </button>
        </>
      )}
    </article>
  );
}

type EveryKey = "import_every_min" | "push_every_min";

/** Off ("when I ask"), or every N minutes or hours. Saved as minutes. */
function Every({ label, settingsKey, settings, onSave }: {
  label: string; settingsKey: EveryKey; settings?: AppSettings; onSave: (patch: Partial<AppSettings>) => void;
}) {
  const minutes = settings?.[settingsKey] ?? 0;
  const inHours = minutes > 0 && minutes % 60 === 0;
  const [unit, setUnit] = useState<"min" | "h">(inHours ? "h" : "min");
  const [count, setCount] = useState(String(minutes === 0 ? "" : inHours ? minutes / 60 : minutes));
  useEffect(() => {
    if (!settings) return;
    const m = settings[settingsKey];
    const h = m > 0 && m % 60 === 0;
    setUnit(h ? "h" : "min");
    setCount(m === 0 ? "" : String(h ? m / 60 : m));
  }, [settings, settingsKey]);
  const on = minutes > 0;
  const commit = (nextCount = count, nextUnit = unit) => {
    const n = Math.round(Number(nextCount));
    if (!Number.isFinite(n) || n <= 0) return;
    const value = Math.min(n * (nextUnit === "h" ? 60 : 1), 7 * 24 * 60);
    if (value !== minutes) onSave({ [settingsKey]: value });
  };
  return (
    <div className={styles.every} role="group" aria-label={label}>
      <span className={styles.everyLabel}>{label}</span>
      <select value={on ? "every" : "ask"} disabled={!settings} aria-label={`${label}: when`}
        onChange={(e) => (e.target.value === "ask" ? onSave({ [settingsKey]: 0 }) : commit(count || "1", unit))}>
        <option value="ask">when I ask</option>
        <option value="every">every…</option>
      </select>
      {on && (
        <>
          <input type="number" min={1} inputMode="numeric" value={count} aria-label={`${label}: how often`}
            onChange={(e) => setCount(e.target.value)} onBlur={() => commit()} onKeyDown={(e) => e.key === "Enter" && commit()} />
          <select value={unit} aria-label={`${label}: unit`} onChange={(e) => { const u = e.target.value as "min" | "h"; setUnit(u); commit(count, u); }}>
            <option value="min">minutes</option>
            <option value="h">hours</option>
          </select>
        </>
      )}
    </div>
  );
}

function Item({ r, tag }: { r: SyncItem; tag?: string }) {
  return (
    <span className={styles.item}>
      <span className={styles.name}><b>{r.artist}</b> · {r.title}{r.year ? <span className={styles.year}> {r.year}</span> : null}</span>
      {tag && <span className={styles.tag}>{tag}</span>}
    </span>
  );
}

function toggle(set: Set<number>, id: number, on: boolean): Set<number> {
  const next = new Set(set);
  if (on) next.add(id); else next.delete(id);
  return next;
}

function summary(job: JobOut): string {
  const r = (job.result ?? {}) as {
    added?: number[]; already_there?: number[]; imported?: number[]; traded?: number[]; copies_added?: number; failed?: unknown[];
    deleted?: number; wanted?: number[]; unwanted?: number[]; updated?: number; tracks_added?: number;
  };
  const parts: string[] = [];
  if (r.deleted != null) parts.push(`${plural(r.deleted, "record")} deleted`);
  if (r.added) parts.push(`${plural(r.added.length, "record")} added to Discogs`);
  if (r.already_there?.length) parts.push(`${r.already_there.length} already there`);
  if (r.imported) parts.push(`${plural(r.imported.length, "record")} imported`);
  if (r.traded?.length) parts.push(`${r.traded.length} moved from the wishlist`);
  if (r.copies_added) parts.push(`${plural(r.copies_added, "copy", "copies")} added`);
  if (r.wanted) parts.push(`${plural(r.wanted.length, "record")} added to the wantlist`);
  if (r.unwanted) parts.push(`${plural(r.unwanted.length, "record")} removed from the wantlist`);
  if (r.updated != null) parts.push(`${plural(r.updated, "record")} refreshed`);
  if (r.tracks_added) parts.push(`${plural(r.tracks_added, "track")} added`);
  if (r.failed?.length) parts.push(`${r.failed.length} failed`);
  return `Sync done: ${parts.join(", ") || "nothing changed"}.`;
}
