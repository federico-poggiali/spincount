"""What goes on a record's labels: built from the database, editable before it is rendered.

Every printed value is a plain string so the editor can change it freely. Nothing here writes to
the database: edits apply to the print only."""
import re
from typing import Literal

from pydantic import BaseModel, Field

MainField = Literal["label", "catno", "year", "country", "styles", "note", "qr"]
# glitchy: the pixel original · corrupted: glitchy, torn · penguin: Tschichold's Penguin grid ·
# republic: The Designers Republic · factory: Saville's catalogue-number sleeves
Design = Literal["glitchy", "corrupted", "penguin", "republic", "factory"]
TrackField = Literal["artist", "bpm", "key", "tags", "note"]


class LabelTrack(BaseModel):
    position: str
    artist: str | None = Field(default=None, description="Only set when it is not the record's artist")
    bpm: str | None = None
    key: str | None = None
    tags: list[str] = []
    note: str | None = None
    skip: bool = Field(default=False, description="Leave this track off the tracks label")
    hidden: list[TrackField] = []


def _scale(description: str | None = None):
    return Field(default=1.0, ge=0.6, le=1.6, description=description)


class LabelSizes(BaseModel):
    """How big each text is, as a factor of its usual size. Text still shrinks to fit from there."""
    artist: float = _scale()
    details: float = _scale("The label and Cat# line")
    title: float = _scale()
    info: float = _scale("Year, country and styles")
    note: float = _scale("The largest the note may grow to fill the label")
    tracks: float = _scale("All the text on the tracks label")


class LabelData(BaseModel):
    artist: str
    label: str | None = None
    catno: str | None = None
    title: str
    year: str | None = None
    country: str | None = Field(default=None, description="Not stored: type it in if you want it printed")
    styles: list[str] = []
    note: str | None = None
    qr_url: str | None = Field(default=None, description="The Discogs page the QR code opens")
    hidden: list[MainField] = []
    tracks: list[LabelTrack] = []
    sizes: LabelSizes = LabelSizes()
    design: Design = "glitchy"


class LabelLook(BaseModel):
    """Everything Customize sets, apart from the text: what a saved preset holds."""
    design: Design = "glitchy"
    sizes: LabelSizes = LabelSizes()
    hidden: list[MainField] = []
    track_hidden: list[TrackField] = []


_DISCOGS_SUFFIX = re.compile(r"\s*\(\d+\)(?=\s*(?:[&,/]|$))")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def clean_artist(name: str) -> str:
    """Discogs tells namesakes apart with a number: 'Jeff Mills (2)'. Not for print."""
    return _DISCOGS_SUFFIX.sub("", name).strip()


def first_sentence(notes: list[dict]) -> str | None:
    """One sentence for the label: the first non-empty note, cut at the first full stop."""
    for note in notes:
        text = " ".join(note["body"].split())
        if text:
            return _SENTENCE_END.split(text, maxsplit=1)[0]
    return None


def _bpm(value: float | None) -> str | None:
    return None if value is None else f"{round(value, 1):g}"


def _track_artist(track: dict, record_artist: str) -> str | None:
    """A track's own artist, only where it adds something: a compilation, or a guest on a record."""
    artist = clean_artist(track["artist"] or "")
    return artist if artist and artist.casefold() != record_artist.casefold() else None


def build(record: dict) -> LabelData:
    """`record` is queries.record_detail(): the record with its tracks, tags and notes."""
    release_id = record["discogs_release_id"]
    record_artist = clean_artist(record["artist"])
    return LabelData(
        artist=record_artist,
        label=record["label"], catno=record["catno"], title=record["title"],
        year=str(record["year"]) if record["year"] else None,
        styles=record["styles"] or [],
        note=first_sentence(record["notes"]),
        qr_url=f"https://www.discogs.com/release/{release_id}" if release_id else None,
        tracks=[LabelTrack(position=t["position"], artist=_track_artist(t, record_artist), bpm=_bpm(t["bpm"]),
                           key=t["camelot_key"] or t["key"], tags=t["tags"],
                           note=first_sentence(t["notes"]))
                for t in record["tracks"]],
    )
