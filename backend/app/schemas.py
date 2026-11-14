"""Pydantic models for the JSON API (the frontend generates its types from these)."""
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from app.labels.data import LabelLook

T = TypeVar("T")
Status = Literal["owned", "wantlist"]  # owned = the library; wantlist = everything else


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class NoteOut(BaseModel):
    id: int
    body: str
    record_id: int | None
    track_id: int | None
    created_at: str
    updated_at: str


class ProposalOut(BaseModel):
    """An analysis result waiting to be validated onto its track."""
    bpm: float | None
    key: str | None
    camelot_key: str | None
    confidence: float | None
    analysis_raw: dict | None
    audio_path: str | None
    proposed_at: str


class TrackAudioOut(BaseModel):
    """What audioresearch found for one track."""
    track_id: int
    status: Literal["found", "review", "not_found"]
    source: str | None
    level: int | None
    quality: Literal["full", "preview", "clip"] | None
    confidence: float | None
    reason: str | None
    url: str | None
    page: str | None  # the page the audio came from (a store's record page, a Bandcamp album ...)
    readings: list[dict] = []  # BPM / key a store shows, kept apart from the audio
    alternatives: list[dict] = []
    found_at: str


class TrackOut(BaseModel):
    id: int
    record_id: int
    position: str
    artist: str | None
    title: str
    duration_sec: int | None
    bpm: float | None
    key: str | None
    camelot_key: str | None
    confidence: float | None
    analysis_raw: dict | None
    audio_path: str | None
    analyzed_at: str | None
    bpm_manual: bool
    key_manual: bool
    year: int | None = None  # inherited from the record, like styles
    styles: list[str] = []  # inherited from the record
    tags: list[str] = []
    notes: list[NoteOut] = []
    proposal: ProposalOut | None = None  # set on a record's tracks while analysis awaits validation


class RecordOut(BaseModel):
    id: int
    discogs_release_id: int | None
    artist: str
    title: str
    label: str | None
    catno: str | None
    year: int | None
    format: str | None
    cover_url: str | None
    status: Status
    added_at: str
    discogs_collection_synced: bool
    styles: list[str] = []  # Discogs styles; hand-edited when styles_manual is set
    styles_manual: bool
    tags: list[str] = []
    traded_at: str | None = None  # when it moved from the wishlist to owned


class RecordSummary(RecordOut):
    track_count: int
    has_note: bool = False  # a record-level note exists (the one that prints on the label)
    bpm_min: float | None = None
    bpm_max: float | None = None
    camelot_keys: list[str] = []
    matched_track_ids: list[int] | None = None  # set when a BPM/key filter was used


class RecordDetail(RecordOut):
    tracks: list[TrackOut]
    notes: list[NoteOut]  # record-level notes; track notes are on each track


class ValidateRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1)
    overwrite_manual: bool = Field(
        default=False, description="Replace hand-entered BPM/key too (and release their lock)")


class AnalyzeRequest(BaseModel):
    track_ids: list[int] | None = None  # omitted: the whole record
    refresh_audio: bool = False  # search for audio again even if some was already found


class DiscardRequest(BaseModel):
    track_ids: list[int] | None = None  # omitted: every proposal on the record


class IntakeRequest(BaseModel):
    discogs_url: str
    status: Status = "owned"


class IntakeResponse(RecordDetail):
    resolved_from_master: int | None
    jobs: dict[str, int | None] | None


class RecordRef(BaseModel):
    id: int
    artist: str
    title: str
    status: Status
    cover_url: str | None


class TrackHit(TrackOut):
    record: RecordRef


class RecordPatch(BaseModel):
    artist: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    label: str | None = None
    catno: str | None = None
    year: int | None = Field(default=None, ge=1850, le=2100)
    format: str | None = None
    cover_url: str | None = None
    status: Status | None = None
    styles: list[str] | None = Field(
        default=None, description="Replaces the whole list and locks it against Discogs re-fetches")
    reset_styles: bool = Field(
        default=False, description="Release the lock and re-fetch the styles from Discogs")


class TrackPatch(BaseModel):
    """Setting bpm or key locks that field against re-analysis; list it in `unlock` to release it."""
    bpm: float | None = Field(default=None, gt=0, le=400)
    key: str | None = Field(default=None, description="Musical ('F# minor', 'Am') or Camelot ('11A')")
    unlock: list[Literal["bpm", "key"]] = []


class NoteCreate(BaseModel):
    body: str
    record_id: int | None = None
    track_id: int | None = None


class NotePatch(BaseModel):
    body: str


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class TagCount(BaseModel):
    name: str
    group: str
    record_count: int
    track_count: int


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class TagDefUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    group_id: int | None = None


class TagDef(BaseModel):
    id: int
    name: str
    record_count: int
    track_count: int


class TagGroup(BaseModel):
    id: int
    name: str
    fixed: bool
    tags: list[TagDef]


class GroupList(BaseModel):
    items: list[TagGroup]


class JobOut(BaseModel):
    id: int
    type: str
    status: Literal["queued", "running", "done", "failed"]
    record_id: int | None
    error: str | None
    result: dict | None
    created_at: str
    updated_at: str


class JobStarted(BaseModel):
    job_id: int
    status: str


class StyleCount(BaseModel):
    name: str
    record_count: int


class StyleList(BaseModel):
    items: list[StyleCount]


class TagList(BaseModel):
    items: list[TagCount]


class FromDiscogs(BaseModel):
    discogs_url: str


class LabelPresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    look: LabelLook


class LabelPreset(LabelPresetIn):
    id: int


class LabelPresetList(BaseModel):
    items: list[LabelPreset]


class ExactNoteHit(BaseModel):
    snippet: str  # matches wrapped in \x02 ... \x03
    note: NoteOut
    record: RecordRef
    track: TrackOut | None = None


class ExactResults(BaseModel):
    notes: list[ExactNoteHit]
    records: list[RecordRef]


# --- Audio -------------------------------------------------------------------------------------

class RecordAudioOut(BaseModel):
    tracks: list[TrackAudioOut]  # tracks never searched are left out
    previews: dict  # audioresearch's plan: {tracks: {position: option | null}, families, stores}


class FindAudioRequest(BaseModel):
    refresh: bool = False  # search again even where audio was already found
    everything: bool = False  # search every level for every track, for more sources (slower)


class Uploaded(BaseModel):
    file: str


class BandcampEmbed(BaseModel):
    kind: str  # "track" | "album"
    id: int


# --- Admin -------------------------------------------------------------------------------------

class VaultSyncOut(BaseModel):
    written: int
    skipped: int
    deleted: int
    synced_at: str


class VaultStatus(BaseModel):
    vault_dir: str
    last_sync: VaultSyncOut | None
    last_error: str | None


class LibraryAudioStarted(BaseModel):
    queued: int
    job_ids: list[int]


class OpenedPath(BaseModel):
    opened: bool
    path: str


# --- Crate: the physical shelf -----------------------------------------------------------------

class CrateRecord(BaseModel):
    id: int
    copy_number: int = 1        # which copy of the record sits here
    copy_id: int | None = None  # set for copy 2 and up
    artist: str
    title: str
    year: int | None
    cover_url: str | None
    styles: list[str] = []
    tags: list[str] = []


class CrateSuggestion(BaseModel):
    section_id: int
    score: int
    reasons: list[str]  # the tags/styles (or artist letter range) that matched


class UnsortedRecord(CrateRecord):
    suggestion: CrateSuggestion | None


class SectionOut(BaseModel):
    id: int
    position: int
    name: str
    records: list[CrateRecord]


class CubeOut(BaseModel):
    id: int
    row: int
    col: int
    name: str
    description: str
    sections: list[SectionOut]


class UnitOut(BaseModel):
    id: int
    name: str
    rows: int
    cols: int
    x: int  # wall position, in cubes from the left
    y: int  # wall position, in cubes from the top
    cubes: list[CubeOut]


class CrateOut(BaseModel):
    units: list[UnitOut]
    unsorted: list[UnsortedRecord]  # owned records not on the shelf yet


class UnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    rows: int = Field(ge=1, le=8)
    cols: int = Field(ge=1, le=8)
    x: int = Field(default=0, ge=0, le=60)
    y: int = Field(default=0, ge=0, le=30)


class UnitPatch(BaseModel):
    """Shrinking a unit drops the cubes outside it; their records go back to unsorted."""
    name: str | None = Field(default=None, min_length=1, max_length=60)
    rows: int | None = Field(default=None, ge=1, le=8)
    cols: int | None = Field(default=None, ge=1, le=8)
    x: int | None = Field(default=None, ge=0, le=60)
    y: int | None = Field(default=None, ge=0, le=30)


class CubePatch(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=300)


class SectionIn(BaseModel):
    name: str = Field(default="", max_length=60)


class PlaceIn(BaseModel):
    record_ids: list[int] = Field(min_length=1, max_length=500)
    section_id: int | None  # null puts the records back in unsorted


# ---- syncing with Discogs ----

class AppSettings(BaseModel):
    auto_collection: bool  # adding an owned record also adds it to the Discogs collection
    auto_wantlist: bool    # adding a wishlist record also adds it to the Discogs wantlist
    import_every_min: int  # Discogs -> Spin Count on a schedule; 0 = only when asked
    push_every_min: int    # Spin Count -> Discogs on a schedule; 0 = only when asked
    youtube_playlist: bool  # "Add to YT playlist": every track is looked up on YouTube, for playlists


MAX_EVERY = 7 * 24 * 60  # a week, in minutes


class AppSettingsPatch(BaseModel):
    auto_collection: bool | None = None
    auto_wantlist: bool | None = None
    import_every_min: int | None = Field(default=None, ge=0, le=MAX_EVERY)
    push_every_min: int | None = Field(default=None, ge=0, le=MAX_EVERY)
    youtube_playlist: bool | None = None


class SyncItem(BaseModel):
    id: int | None  # the Spin Count record; null for a release not imported yet
    discogs_release_id: int
    artist: str
    title: str
    year: int | None
    cover_url: str | None
    copies: int = 1          # copies in the Discogs collection
    here: int | None = None  # copies in Spin Count, when they differ


class ResetCounts(BaseModel):
    records: int
    notes: int
    analysed_tracks: int


class SyncCompare(BaseModel):
    discogs_count: int
    owned_count: int
    to_discogs: list[SyncItem]  # owned here, missing from the Discogs collection
    to_import: list[SyncItem]   # in the Discogs collection, missing here
    to_trade: list[SyncItem]    # in the Discogs collection, on the wishlist here
    to_copy: list[SyncItem]     # more copies on Discogs than here
    kept: list[SyncItem]        # deleted here but kept on Discogs: imports skip them
    to_wantlist: list[SyncItem]   # on the wishlist here, not on the Discogs wantlist
    owned_wanted: list[SyncItem]  # owned here, still on the Discogs wantlist
    reset: ResetCounts          # what a reset would erase


class PushRequest(BaseModel):
    record_ids: list[int] = Field(min_length=1, max_length=2000)


class CopyOut(BaseModel):
    number: int           # 1 is the record itself
    copy_id: int | None   # None for copy 1
    section_id: int | None  # its shelf place; None = unsorted


class CopyPlace(BaseModel):
    section_id: int | None


class ResetRequest(BaseModel):
    confirm: str = Field(description='Must be "RESET"')


class TrackYouTubeOut(BaseModel):
    """A track's YouTube video, for "Add to YT playlist": a stored lookup, or the YouTube link the audio
    search already found. Tracks with neither are left out."""
    track_id: int
    video_id: str | None  # null: searched, YouTube does not have it
    source: Literal["audio", "search"] | None  # the audio search's link (from Discogs), or a YouTube search
    title: str | None     # the video's title (search only)
    channel: str | None
    duration: int | None
    confidence: float | None
    found_at: str


class RecordYouTubeOut(BaseModel):
    tracks: list[TrackYouTubeOut]


class FindYouTubeRequest(BaseModel):
    refresh: bool = False  # search again even for tracks already searched


class YouTubeUsage(BaseModel):
    """Quota units this app spent today, counted here (Google has no API for it); resets at Pacific
    midnight."""
    used: int
    limit: int      # 10,000: a Google Cloud project's default
    resets_at: str  # UTC, ISO 8601


class YouTubeStatus(BaseModel):
    configured: bool  # your Google app's client ID and secret are set (Settings or .env)
    connected: bool   # signed in to a YouTube account
    source: Literal["env", "settings"] | None = None  # where the client ID and secret come from
    client_id: str | None = None  # not secret; shown so you know which Google app is used
    usage: YouTubeUsage | None = None  # only once configured


class YouTubeCredentials(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    client_secret: str = Field(min_length=1, max_length=200)


class YouTubeCredentialsSaved(BaseModel):
    checked: bool  # false: Google could not be reached, so the ID and secret were saved unchecked


class YouTubeConnect(BaseModel):
    url: str  # Google's sign-in page; it comes back to /api/youtube/callback


class YouTubePlaylist(BaseModel):
    id: str
    title: str
    count: int


class AddToPlaylist(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=200)  # added in this order


class TrackError(BaseModel):
    track_id: int
    error: str


class AddedToPlaylist(BaseModel):
    added: list[int]     # track ids
    already: list[int]   # their video was in the playlist already
    no_video: list[int]  # not on YouTube, or not searched yet
    failed: list[TrackError]
    quota_exceeded: bool  # YouTube stopped it for today; the rest of the tracks were not tried
