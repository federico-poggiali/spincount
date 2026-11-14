import { useEffect, useRef, useState, type RefObject } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type LabelLook, type NoteCreate, type NotePatch, type RecordDetail, type RecordPatch, type TrackPatch } from "./api/api";
import { keyByCamelot, type KeyFormat } from "./lib";

export function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

export const recordKey = (id: number) => ["record", id] as const;

export function useRecord(id: number, refetchWhileBusy = false) {
  return useQuery({
    queryKey: recordKey(id),
    queryFn: () => api.getRecord(id),
    enabled: id > 0,
    refetchInterval: refetchWhileBusy ? 2500 : false,
  });
}

export function useTags() {
  return useQuery({ queryKey: ["tags"], queryFn: () => api.listTags().then((r) => r.items) });
}

export function useStyles() {
  return useQuery({ queryKey: ["styles"], queryFn: () => api.listStyles().then((r) => r.items) });
}

/** A mutation that patches the cached record immediately and rolls back if the server refuses. */
function useRecordMutation<V, R = unknown>(
  id: number,
  mutationFn: (v: V) => Promise<R>,
  optimistic: (record: RecordDetail, v: V) => RecordDetail,
  alsoInvalidate: string[] = [],
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onMutate: async (v: V) => {
      await client.cancelQueries({ queryKey: recordKey(id) });
      const previous = client.getQueryData<RecordDetail>(recordKey(id));
      if (previous) client.setQueryData(recordKey(id), optimistic(previous, v));
      return { previous };
    },
    onError: (_error, _v, context) => {
      if (context?.previous) client.setQueryData(recordKey(id), context.previous);
    },
    onSettled: () => {
      client.invalidateQueries({ queryKey: recordKey(id) });
      alsoInvalidate.forEach((key) => client.invalidateQueries({ queryKey: [key] }));
    },
  });
}

const mapTrack = (record: RecordDetail, trackId: number, fn: (t: RecordDetail["tracks"][number]) => RecordDetail["tracks"][number]) => ({
  ...record,
  tracks: record.tracks.map((t) => (t.id === trackId ? fn(t) : t)),
});

export function usePatchTrack(recordId: number) {
  return useRecordMutation(
    recordId,
    ({ trackId, patch }: { trackId: number; patch: TrackPatch }) => api.patchTrack(trackId, patch),
    (record, { trackId, patch }) =>
      mapTrack(record, trackId, (t) => {
        const key = patch.key ? keyByCamelot(patch.key.toUpperCase()) : undefined;
        return {
          ...t,
          ...(patch.bpm != null ? { bpm: patch.bpm, bpm_manual: true } : {}),
          ...(patch.key ? { key: key?.name ?? patch.key, camelot_key: key?.camelot ?? t.camelot_key, key_manual: true } : {}),
          ...(patch.unlock?.includes("bpm") ? { bpm_manual: false } : {}),
          ...(patch.unlock?.includes("key") ? { key_manual: false } : {}),
        };
      }),
  );
}

export function usePatchRecord(recordId: number) {
  return useRecordMutation(
    recordId,
    (patch: RecordPatch) => api.patchRecord(recordId, patch),
    (record, patch) => ({ ...record, ...(patch as Partial<RecordDetail>) }),
    ["records"],
  );
}

/** Edit a record's styles (locks them against Discogs) or reset them to Discogs' own list. */
export function useStyleMutations(recordId: number) {
  const set = useRecordMutation(
    recordId,
    (styles: string[]) => api.patchRecord(recordId, { styles }),
    (record, styles) => ({ ...record, styles, styles_manual: true, tracks: record.tracks.map((t) => ({ ...t, styles })) }),
    ["records", "styles"],
  );
  const reset = useRecordMutation(recordId, () => api.patchRecord(recordId, { reset_styles: true }), (record) => record, ["records", "styles"]);
  return { set, reset };
}

export function useNoteMutations(recordId: number) {
  const create = useRecordMutation(recordId, (body: NoteCreate) => api.createNote(body), (r) => r, ["records"]);
  const patch = useRecordMutation(
    recordId,
    ({ id, body }: { id: number; body: NotePatch }) => api.patchNote(id, body),
    (record, { id, body }) => {
      const update = (n: RecordDetail["notes"][number]) => (n.id === id ? { ...n, ...(body as object) } : n);
      return { ...record, notes: record.notes.map(update), tracks: record.tracks.map((t) => ({ ...t, notes: t.notes.map(update) })) };
    },
  );
  const remove = useRecordMutation(
    recordId,
    (id: number) => api.deleteNote(id),
    (record, id) => ({
      ...record,
      notes: record.notes.filter((n) => n.id !== id),
      tracks: record.tracks.map((t) => ({ ...t, notes: t.notes.filter((n) => n.id !== id) })),
    }),
    ["records"],
  );
  return { create, patch, remove };
}

export function useTagGroups() {
  return useQuery({ queryKey: ["tag-groups"], queryFn: api.listTagGroups });
}

export function useTagMutations(recordId: number) {
  const add = useRecordMutation(
    recordId,
    ({ kind, id, name }: { kind: "record" | "track"; id: number; name: string }) => api.addTag(kind, id, name),
    (record, { kind, id, name }) => {
      const tag = name.trim().toLowerCase();
      const withTag = (tags: string[]) => (tags.includes(tag) ? tags : [...tags, tag].sort());
      return kind === "record"
        ? { ...record, tags: withTag(record.tags ?? []) }
        : mapTrack(record, id, (t) => ({ ...t, tags: withTag(t.tags ?? []) }));
    },
    ["tags"],
  );
  const remove = useRecordMutation(
    recordId,
    ({ kind, id, name }: { kind: "record" | "track"; id: number; name: string }) => api.removeTag(kind, id, name),
    (record, { kind, id, name }) => {
      const without = (tags: string[]) => tags.filter((t) => t !== name);
      return kind === "record"
        ? { ...record, tags: without(record.tags ?? []) }
        : mapTrack(record, id, (t) => ({ ...t, tags: without(t.tags ?? []) }));
    },
    ["tags"],
  );
  return { add, remove };
}

/** A setting remembered per browser (localStorage) and kept in step across every component that reads it. */
function useStoredSetting<T extends string>(key: string, fallback: T, valid: readonly T[]): [T, (value: T) => void] {
  const read = (): T => {
    try {
      const stored = localStorage.getItem(key) as T | null;
      return stored !== null && valid.includes(stored) ? stored : fallback;
    } catch {
      return fallback; // private mode: the choice just is not remembered
    }
  };
  const [value, setValue] = useState(read);
  useEffect(() => {
    const sync = () => setValue(read());
    window.addEventListener(SETTINGS_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(SETTINGS_EVENT, sync); window.removeEventListener("storage", sync); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (next: T) => {
    setValue(next);
    try {
      localStorage.setItem(key, next);
    } catch {
      /* not remembered */
    }
    window.dispatchEvent(new Event(SETTINGS_EVENT));
  };
  return [value, set];
}

const SETTINGS_EVENT = "spincount-settings";
const ON_OFF = ["on", "off"] as const;

function useStoredToggle(key: string): [boolean, (on: boolean) => void] {
  const [value, set] = useStoredSetting(key, "off", ON_OFF);
  return [value === "on", (on) => set(on ? "on" : "off")];
}

/** Camelot or musical key labels. */
export const useKeyFormat = () => useStoredSetting<KeyFormat>("spincount.keyformat", "camelot", ["camelot", "musical"]);

/** Whether musical keys are analysed and shown anywhere (off unless switched on in Settings). BPM is always shown. */
export const useKeysEnabled = () => useStoredToggle("spincount.keys");

/** Whether a key's confidence is shown (percentage and low-confidence warnings); only matters while keys are shown. */
export const useKeyConfidenceEnabled = () => useStoredToggle("spincount.key-confidence");

/** Close a popover when the pointer goes down anywhere outside `root`. */
export function useDismiss(root: RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  const latest = useRef(close);
  latest.current = close;
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) latest.current(); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, root]);
}

/** Label presets (named looks, kept in the database) for the label editor's Customize panel. */
export function useLabelPresets() {
  const client = useQueryClient();
  const key = ["label-presets"];
  const presets = useQuery({ queryKey: key, queryFn: api.listLabelPresets, staleTime: Infinity });
  const settle = { onSuccess: (items: Awaited<ReturnType<typeof api.listLabelPresets>>) => client.setQueryData(key, items) };
  const save = useMutation({ mutationFn: ({ name, look }: { name: string; look: LabelLook }) => api.saveLabelPreset(name, look), ...settle });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteLabelPreset(id), ...settle });
  return {
    items: presets.data ?? [],
    save: (name: string, look: LabelLook) => save.mutate({ name, look }),
    remove: (id: number) => remove.mutate(id),
  };
}
