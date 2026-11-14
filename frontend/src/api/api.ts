import type { components } from "./schema";

type S = components["schemas"];
export type RecordDetail = S["RecordDetail"];
export type RecordSummary = S["RecordSummary"];
export type RecordPatch = Partial<S["RecordPatch"]>;
export type TrackOut = S["TrackOut"];
export type TrackHit = S["TrackHit"];
export type TrackPatch = Partial<S["TrackPatch"]>;
export type NoteOut = S["NoteOut"];
export type NoteCreate = S["NoteCreate"];
export type NotePatch = S["NotePatch"];
export type IntakeResponse = S["IntakeResponse"];
export type JobOut = S["JobOut"];
export type TrackAudio = S["TrackAudioOut"];
export type RecordAudio = S["RecordAudioOut"];
export type ExactResults = S["ExactResults"];
export type TagCount = S["TagCount"];
export type TagGroup = S["TagGroup"];
export type StyleCount = S["StyleCount"];
export type VaultStatus = S["VaultStatus"];
export type VaultSyncOut = S["VaultSyncOut"];
export type LabelData = S["LabelData"];
export type LabelTrack = S["LabelTrack"];
export type LabelRender = S["LabelRender"];
export type LabelImage = S["LabelImage"];
export type LabelSizes = S["LabelSizes"];
export type LabelLook = S["LabelLook"];
export type LabelPreset = S["LabelPreset"];
export type Design = NonNullable<LabelData["design"]>;
export type CrateOut = S["CrateOut"];
export type UnitOut = S["UnitOut"];
export type CubeOut = S["CubeOut"];
export type SectionOut = S["SectionOut"];
export type CrateRecord = S["CrateRecord"];
export type UnsortedRecord = S["UnsortedRecord"];
export type UnitCreate = S["UnitCreate"];
export type UnitPatch = Partial<S["UnitPatch"]>;
export type CubePatch = Partial<S["CubePatch"]>;
export type RecordOut = S["RecordOut"];
export type AppSettings = S["AppSettings"];
export type SyncCompare = S["SyncCompare"];
export type SyncItem = S["SyncItem"];
export type CopyOut = S["CopyOut"];
export type TrackYouTube = S["TrackYouTubeOut"];
export type YouTubeStatus = S["YouTubeStatus"];
export type YouTubePlaylist = S["YouTubePlaylist"];
export type AddedToPlaylist = S["AddedToPlaylist"];
export type Status = RecordSummary["status"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

function toSearch(query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.append(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export async function request<T>(
  method: string,
  path: string,
  opts: { query?: Query; body?: unknown; file?: File; signal?: AbortSignal } = {},
): Promise<{ data: T; status: number }> {
  let response: Response;
  try {
    response = await fetch(path + toSearch(opts.query), {
      method,
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.file ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
      signal: opts.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Can't reach the server. Is the backend running?");
  }
  if (!response.ok) {
    let code = "error";
    let message = `Request failed (${response.status})`;
    let details: unknown;
    try {
      const body = await response.json();
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
      details = body.error?.details;
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, code, message, details);
  }
  const data = response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  return { data, status: response.status };
}

const get = async <T>(path: string, query?: Query, signal?: AbortSignal) =>
  (await request<T>("GET", path, { query, signal })).data;
const send = async <T>(method: string, path: string, body?: unknown) =>
  (await request<T>(method, path, { body })).data;

export type LibraryQuery = {
  q?: string;
  bpm_min?: number;
  bpm_max?: number;
  key?: string;
  tag?: string[];
  style?: string[];
  status?: Status;
  limit?: number;
  offset?: number;
};

export const api = {
  health: (signal?: AbortSignal) => get<{ status: string }>("/health", undefined, signal),

  listRecords: (query: LibraryQuery, signal?: AbortSignal) =>
    get<Page<RecordSummary>>("/api/records", query, signal),
  listTracks: (query: LibraryQuery, signal?: AbortSignal) =>
    get<Page<TrackHit>>("/api/tracks", query, signal),
  getRecord: (id: number) => get<RecordDetail>(`/api/records/${id}`),
  patchRecord: (id: number, body: RecordPatch) => send<RecordDetail>("PATCH", `/api/records/${id}`, body),
  deleteRecord: (id: number, fromDiscogs = false) => send<void>("DELETE", `/api/records/${id}${fromDiscogs ? "?from_discogs=true" : ""}`),
  listCopies: (id: number) => get<CopyOut[]>(`/api/records/${id}/copies`),
  addCopy: (id: number) => send<CopyOut[]>("POST", `/api/records/${id}/copies`),
  placeCopy: (copyId: number, section_id: number | null) => send<CopyOut[]>("PATCH", `/api/copies/${copyId}`, { section_id }),
  deleteCopy: (copyId: number) => send<CopyOut[]>("DELETE", `/api/copies/${copyId}`),
  intake: (body: { discogs_url: string; status: Status }) =>
    request<IntakeResponse>("POST", "/api/records/intake", { body }),
  analyze: (id: number, trackIds?: number[], refreshAudio = false) =>
    send<{ job_id: number }>("POST", `/api/records/${id}/analyze`,
      trackIds || refreshAudio ? { track_ids: trackIds, refresh_audio: refreshAudio } : undefined),
  recordAudio: (id: number) => get<RecordAudio>(`/api/records/${id}/audio`),
  /** `everything` searches every level for every track, for more sources (slower). */
  findAudio: (id: number, refresh = false, everything = false) =>
    send<{ job_id: number }>("POST", `/api/records/${id}/find-audio`,
      refresh || everything ? { refresh, everything } : undefined),
  uploadAudio: (id: number, file: File) =>
    request<{ file: string }>("POST", `/api/records/${id}/upload-audio`, { query: { filename: file.name }, file }).then((r) => r.data),
  audioFileUrl: (trackId: number) => `/api/tracks/${trackId}/audio-file`,
  recordYouTube: (id: number) => get<{ tracks: TrackYouTube[] }>(`/api/records/${id}/youtube`),
  findYouTube: (id: number, refresh = false) =>
    send<{ job_id: number }>("POST", `/api/records/${id}/find-youtube`, refresh ? { refresh } : undefined),
  bandcampEmbed: (url: string) => get<{ kind: string; id: number }>("/api/audio/bandcamp-embed", { url }),
  validate: (id: number, trackIds: number[], overwriteManual = false) =>
    send<RecordDetail>("POST", `/api/records/${id}/validate`, { track_ids: trackIds, overwrite_manual: overwriteManual }),
  discard: (id: number, trackIds?: number[]) =>
    send<RecordDetail>("POST", `/api/records/${id}/discard`, trackIds ? { track_ids: trackIds } : undefined),
  syncDiscogs: (id: number) => send<{ job_id: number }>("POST", `/api/records/${id}/sync-discogs`),
  getJob: (id: number) => get<JobOut>(`/api/jobs/${id}`),

  patchTrack: (id: number, body: TrackPatch) => send<TrackOut>("PATCH", `/api/tracks/${id}`, body),

  createNote: (body: NoteCreate) => send<NoteOut>("POST", "/api/notes", body),
  patchNote: (id: number, body: NotePatch) => send<NoteOut>("PATCH", `/api/notes/${id}`, body),
  deleteNote: (id: number) => send<void>("DELETE", `/api/notes/${id}`),

  listTags: () => get<{ items: TagCount[] }>("/api/tags"),
  listTagGroups: () => get<{ items: TagGroup[] }>("/api/tag-groups").then((r) => r.items),
  createTagGroup: (name: string) => send<{ items: TagGroup[] }>("POST", "/api/tag-groups", { name }),
  renameTagGroup: (id: number, name: string) => send<{ items: TagGroup[] }>("PATCH", `/api/tag-groups/${id}`, { name }),
  deleteTagGroup: (id: number) => send<{ items: TagGroup[] }>("DELETE", `/api/tag-groups/${id}`),
  createTagDef: (groupId: number, name: string) => send<{ items: TagGroup[] }>("POST", `/api/tag-groups/${groupId}/tags`, { name }),
  updateTagDef: (id: number, body: { name?: string; group_id?: number }) => send<{ items: TagGroup[] }>("PATCH", `/api/tag-defs/${id}`, body),
  deleteTagDef: (id: number) => send<{ items: TagGroup[] }>("DELETE", `/api/tag-defs/${id}`),
  addTag: (kind: "record" | "track", id: number, name: string) =>
    send<string[]>("POST", `/api/${kind}s/${id}/tags`, { name }),
  removeTag: (kind: "record" | "track", id: number, name: string) =>
    send<string[]>("DELETE", `/api/${kind}s/${id}/tags/${encodeURIComponent(name)}`),

  labelFromDiscogs: (discogs_url: string) => send<LabelData>("POST", "/api/labels/from-discogs", { discogs_url }),
  renderLooseLabel: (body: LabelData) => send<LabelRender>("POST", "/api/labels/render", body),
  getLabel: (id: number) => get<LabelData>(`/api/records/${id}/label`),
  renderLabel: (id: number, body: LabelData) => send<LabelRender>("POST", `/api/records/${id}/label/render`, body),
  listLabelPresets: () => get<{ items: LabelPreset[] }>("/api/label-presets").then((r) => r.items),
  saveLabelPreset: (name: string, look: LabelLook) => send<{ items: LabelPreset[] }>("POST", "/api/label-presets", { name, look }).then((r) => r.items),
  deleteLabelPreset: (id: number) => send<{ items: LabelPreset[] }>("DELETE", `/api/label-presets/${id}`).then((r) => r.items),

  listStyles: () => get<{ items: StyleCount[] }>("/api/styles"),

  search: (q: string, signal?: AbortSignal) => get<ExactResults>("/api/search/exact", { q }, signal),

  getCrate: () => get<CrateOut>("/api/crate"),
  createUnit: (body: UnitCreate) => send<CrateOut>("POST", "/api/crate/units", body),
  patchUnit: (id: number, body: UnitPatch) => send<CrateOut>("PATCH", `/api/crate/units/${id}`, body),
  deleteUnit: (id: number) => send<void>("DELETE", `/api/crate/units/${id}`),
  patchCube: (id: number, body: CubePatch) => send<CrateOut>("PATCH", `/api/crate/cubes/${id}`, body),
  addSection: (cubeId: number, name = "") => send<CrateOut>("POST", `/api/crate/cubes/${cubeId}/sections`, { name }),
  renameSection: (id: number, name: string) => send<CrateOut>("PATCH", `/api/crate/sections/${id}`, { name }),
  deleteSection: (id: number) => send<CrateOut>("DELETE", `/api/crate/sections/${id}`),
  place: (record_ids: number[], section_id: number | null) => send<CrateOut>("PUT", "/api/crate/place", { record_ids, section_id }),

  vaultStatus: () => get<VaultStatus>("/api/admin/vault-status"),
  syncVault: () => send<VaultSyncOut>("POST", "/api/admin/sync-vault"),
  findAudioForLibrary: () => send<{ queued: number; job_ids: number[] }>("POST", "/api/admin/find-audio"),
  findYouTubeForLibrary: () => send<{ queued: number; job_ids: number[] }>("POST", "/api/admin/find-youtube"),
  youtubeStatus: () => get<YouTubeStatus>("/api/youtube/status"),
  saveYouTubeCredentials: (client_id: string, client_secret: string) =>
    send<{ checked: boolean }>("PUT", "/api/youtube/credentials", { client_id, client_secret }),
  removeYouTubeCredentials: () => send<void>("DELETE", "/api/youtube/credentials"),
  connectYouTube: () => send<{ url: string }>("POST", "/api/youtube/connect"),
  disconnectYouTube: () => send<void>("DELETE", "/api/youtube/connection"),
  youtubePlaylists: () => get<YouTubePlaylist[]>("/api/youtube/playlists"),
  addToPlaylist: (playlistId: string, track_ids: number[]) =>
    send<AddedToPlaylist>("POST", `/api/youtube/playlists/${encodeURIComponent(playlistId)}/tracks`, { track_ids }),
  backfillStyles: () => send<{ job_id: number }>("POST", "/api/admin/backfill-styles"),
  getSettings: () => get<AppSettings>("/api/settings"),
  patchSettings: (patch: Partial<AppSettings>) => send<AppSettings>("PATCH", "/api/settings", patch),
  compareDiscogs: () => get<SyncCompare>("/api/discogs-sync/compare"),
  pushToDiscogs: (record_ids: number[]) => send<{ job_id: number }>("POST", "/api/discogs-sync/push", { record_ids }),
  pullFromDiscogs: () => send<{ job_id: number }>("POST", "/api/discogs-sync/pull"),
  resetFromDiscogs: (confirm: string) => send<{ job_id: number }>("POST", "/api/discogs-sync/reset", { confirm }),
  recentlyTraded: () => get<RecordOut[]>("/api/records/recently-traded"),
  wantlistPush: (record_ids: number[]) => send<{ job_id: number }>("POST", "/api/discogs-sync/wantlist", { record_ids }),
  wantlistTidy: (record_ids: number[]) => send<{ job_id: number }>("POST", "/api/discogs-sync/wantlist-tidy", { record_ids }),
  refreshFromDiscogs: () => send<{ job_id: number }>("POST", "/api/discogs-sync/refresh"),
  forgetKept: (releaseId: number) => send<void>("DELETE", `/api/discogs-sync/kept/${releaseId}`),
  openVault: () => send<{ opened: boolean; path: string }>("POST", "/api/admin/open-vault"),
};
