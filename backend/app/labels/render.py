"""Draw the labels for a Brother QL, 62 mm roll at 300 dpi: 696 px wide, 1 px = 1 dot.

Pure black on white, no grey (thermal printers dither it), thick rules, smallest text 26 px
(18 px when a size slider asks for it).
Text is drawn without anti-aliasing, so what the preview shows is exactly what gets printed.
Each label has a design (glitchy, corrupted, penguin, republic, factory). Glitchy is drawn here, the
others in designs.py; all of them share this canvas, the fitting rules and the tracks layout.
The 8-bit touch (pixel headers, one doodle per label) lives in doodles.py: only the glitchy designs use it."""
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from app.labels import doodles
from app.labels.data import LabelData, LabelTrack

W, H = 696, 472  # 62 x 40 mm at 300 dpi
MARGIN = 20
RULE = 6
MIN_SIZE = 26  # about 2.2 mm
FLOOR = 18  # the smallest a size slider can take text
NOTE_MAX = 64  # the note grows up to this to fill an empty label
FONTS = Path(__file__).parent / "fonts"
SANS, MONO = "DejaVuSans-Bold.ttf", "DejaVuSansMono-Bold.ttf"
PIXEL = doodles.PIXEL
ELLIPSIS = "…"

# (font size, most lines) to try in order; the first that fits wins, the last gets cut with "…".
Fit = list[tuple[int, int]]


@dataclass
class Rendered:
    kind: str  # "main" or "tracks"
    name: str  # file name stem, e.g. "tracks-1"
    png: bytes


@lru_cache(maxsize=256)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """`name` is a font file, or a variable font with its axes: "Archivo.ttf:wght=900,wdth=125"."""
    file, _, axes = name.partition(":")
    font = ImageFont.truetype(str(FONTS / file), size)
    if axes:
        wanted = dict(a.split("=") for a in axes.split(","))
        font.set_variation_by_axes([float(wanted.get(_AXIS_TAGS.get(a["name"], ""), a["default"]))
                                    for a in font.get_variation_axes()])
    return font


_AXIS_TAGS = {b"Weight": "wght", b"Width": "wdth", b"Optical size": "opsz", "Weight": "wght", "Width": "wdth"}


def _line_height(size: int) -> int:
    return round(size * 1.2)


def _scaled(options: Fit, scale: float, step: int = 1) -> Fit:
    """`options` at `scale` times their size, kept on multiples of `step` (the pixel font needs 8)."""
    out: Fit = []
    for size, lines in options:
        option = (max(FLOOR, round(size * scale / step) * step), lines)
        if option not in out:
            out.append(option)
    return out


def _header_font(text: str) -> str:
    """The pixel font when it can spell the text, otherwise the plain one."""
    return PIXEL if doodles.covers(str(FONTS / PIXEL), text) else SANS


class Canvas:
    def __init__(self) -> None:
        self.img = Image.new("L", (W, H), 255)
        self.draw = ImageDraw.Draw(self.img)
        self.draw.fontmode = "1"  # no anti-aliasing: every pixel is black or white

    def width(self, text: str, name: str, size: int) -> float:
        return self.draw.textlength(text, font=_font(name, size))

    def text(self, xy: tuple[int, int], text: str, name: str, size: int, fill: int = 0) -> None:
        self.draw.text(xy, text, font=_font(name, size), fill=fill)

    def rule(self, y: int) -> int:
        self.draw.rectangle([MARGIN, y, W - MARGIN - 1, y + RULE - 1], fill=0)
        return y + RULE

    def wrap(self, text: str, name: str, size: int, width: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if self.width(trial, name, size) <= width:
                current = trial
                continue
            if current:
                lines.append(current)
            current = word
            while self.width(current, name, size) > width and len(current) > 1:  # one huge word
                cut = len(current) - 1
                while cut > 1 and self.width(current[:cut], name, size) > width:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        if current:
            lines.append(current)
        return lines

    def ellipsize(self, text: str, name: str, size: int, width: int) -> str:
        if self.width(text, name, size) <= width:
            return text
        while text and self.width(text + ELLIPSIS, name, size) > width:
            text = text[:-1]
        return text.rstrip() + ELLIPSIS

    def fit(self, text: str, name: str, width: int, options: Fit) -> tuple[list[str], int, bool]:
        """Lines and font size for `text`, and whether it had to be cut to fit."""
        for size, max_lines in options:
            lines = self.wrap(text, name, size, width)
            if len(lines) <= max_lines:
                return lines, size, False
        size, max_lines = options[-1]
        full = self.wrap(text, name, size, width)
        # the last line carries the cut: keep everything that did not fit in it, then trim
        lines = full[:max_lines - 1] + [self.ellipsize(" ".join(full[max_lines - 1:]), name, size, width)]
        return lines, size, True

    def block(self, y: int, text: str, name: str, width: int, options: Fit, warn, what: str,
              x: int = MARGIN) -> int:
        lines, size, cut = self.fit(text, name, width, options)
        if cut:
            warn(f"{what} was too long and has been cut")
        for line in lines:
            if name == PIXEL:  # tight lines: the pixel font has a lot of room above its caps
                top, bottom = _font(name, size).getbbox("ÀJ")[1::2]
                self.text((x, y - top), line, name, size)
                y += bottom - top + size // 8
            else:
                self.text((x, y), line, name, size)
                y += _line_height(size)
        return y

    def png(self) -> bytes:
        out = io.BytesIO()
        self.img.convert("1", dither=Image.Dither.NONE).save(out, format="PNG", dpi=(300, 300))
        return out.getvalue()


def _qr(canvas: Canvas, url: str, x: int, y: int, size: int = 144) -> int:
    """Draw a QR code in a rounded frame with its top-right corner at (x, y). Returns the frame size."""
    qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    scale = max(3, size // len(matrix))
    side = len(matrix) * scale
    pad, frame = 5, 4
    total = side + 2 * (pad + frame)
    left = x - total
    canvas.draw.rounded_rectangle([left, y, x - 1, y + total - 1], radius=14, outline=0, width=frame)
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                px, py = left + frame + pad + c * scale, y + frame + pad + r * scale
                canvas.draw.rectangle([px, py, px + scale - 1, py + scale - 1], fill=0)
    return total


def render_main(d: LabelData, warn) -> bytes:
    canvas = Canvas()
    sizes = d.sizes

    def shown(field: str) -> bool:
        value = d.qr_url if field == "qr" else getattr(d, field)
        return field not in d.hidden and bool(value)

    right = W - MARGIN
    qr_size = 0
    if shown("qr"):
        qr_size = _qr(canvas, d.qr_url, right, MARGIN)
    text_w = right - MARGIN - (qr_size + 16 if qr_size else 0)

    y = MARGIN
    artist = d.artist.upper()
    artist_font = _header_font(artist)
    if artist_font == PIXEL:  # the pixel font is only crisp at multiples of 8 px
        artist_fit = _scaled([(s, 1) for s in (80, 72, 64, 56, 48, 40)] + [(s, 2) for s in (48, 40, 32)],
                             sizes.artist, step=8)
    else:
        artist_fit = _scaled([(s, 1) for s in range(64, 43, -4)] + [(s, 2) for s in range(52, 35, -4)],
                             sizes.artist)
    y = canvas.block(y, artist, artist_font, text_w, artist_fit, warn, "The artist") + 6
    label_line = " · ".join(
        p for p in ((d.label or "").upper() if shown("label") else "",
                    f"Cat# {d.catno}" if shown("catno") else "") if p)
    if label_line:
        details_fit = _scaled([(s, 1) for s in (30, 28, 26)], sizes.details)
        y = canvas.block(y + 4, label_line, MONO, text_w, details_fit, warn, "The label line")
    title_fit = _scaled([(s, 1) for s in range(40, 31, -2)] + [(s, 2) for s in range(32, 25, -2)],
                        sizes.title)
    y = canvas.block(y + 4, d.title, SANS, text_w, title_fit, warn, "The title")
    y = max(y, MARGIN + qr_size) + 10

    parts = [d.year if shown("year") else None, d.country if shown("country") else None,
             ", ".join(d.styles) if shown("styles") else None]
    info = " · ".join(p for p in parts if p)
    if info:
        y = canvas.rule(y) + 10
        info_fit = _scaled([(s, 1) for s in (32, 30, 28, 26)] + [(26, 2)], sizes.info)
        y = canvas.block(y, info, SANS, W - 2 * MARGIN, info_fit, warn, "The info line") + 6
    if shown("note") and d.note:
        y = canvas.rule(y) + 10
        room = H - MARGIN - y
        # as big as the room allows: a short note fills the empty space instead of leaving it white
        smallest = max(FLOOR, round(MIN_SIZE * min(1.0, sizes.note)))
        note_fit: Fit = [(s, room // _line_height(s))
                         for s in range(round(NOTE_MAX * sizes.note), smallest - 1, -2)
                         if room >= _line_height(s)]
        if not note_fit:
            warn("The note does not fit on the label")
        else:
            canvas.block(y, d.note, SANS, W - 2 * MARGIN, note_fit, warn, "The note")
    elif y > H - MARGIN:
        warn("The label is too full: hide a field")
    doodles.place(canvas.img, doodles.rng_for(d.artist, d.title), (MARGIN, MARGIN, W - MARGIN, H - MARGIN))
    return canvas.png()


# ---- tracks label ----
SIDE_W = 64  # the black block that carries the side letter
GAP = 16


def side_of(position: str) -> str:
    letters = re.match(r"[A-Za-z]+", position)
    if letters:
        return letters.group(0).upper()
    return re.split(r"[-./]", position)[0] or "·"


def _shows(t: LabelTrack, field: str) -> bool:
    return field not in t.hidden and bool(getattr(t, field))


@dataclass(frozen=True)
class TrackType:
    """The tracks label's two text sizes, from its size slider."""
    big: int  # position, BPM, key
    small: int  # tags, artist, note

    @classmethod
    def at(cls, scale: float) -> "TrackType":
        return cls(max(FLOOR, round(30 * scale)), max(FLOOR, round(26 * scale)))


USUAL = TrackType.at(1.0)


def _row_height(t: LabelTrack, tt: TrackType = USUAL) -> int:
    return _line_height(tt.big) + sum(_line_height(tt.small) for f in ("artist", "note") if _shows(t, f)) + 10


def _group_height(tracks: list[LabelTrack], tt: TrackType = USUAL) -> int:
    return max(sum(_row_height(t, tt) for t in tracks), 62)  # room for the side letter


def _page_height(groups: list[tuple[str, list[LabelTrack]]], tt: TrackType = USUAL) -> int:
    return sum(_group_height(tracks, tt) for _, tracks in groups) + 12 * (len(groups) - 1)


def _paginate(entries: list[LabelTrack], tt: TrackType = USUAL) -> list[list[tuple[str, list[LabelTrack]]]]:
    """Pages of (side, tracks), two sides to a label (a double LP is A+B, C+D…). A side that runs
    over continues, with its block, on the next label."""
    limit = H - 2 * MARGIN
    pages: list[list[tuple[str, list[LabelTrack]]]] = [[]]
    for t in entries:
        side = side_of(t.position)
        if len(pages[-1]) >= 2 and pages[-1][-1][0] != side:  # a label holds two sides: A+B, C+D…
            pages.append([])
        page = pages[-1]
        if page and page[-1][0] == side:
            page[-1][1].append(t)
        else:
            page.append((side, [t]))
        if len(page) > 1 or len(page[0][1]) > 1:  # a lone track always fits
            if _page_height(page, tt) > limit:
                page[-1][1].pop()
                if not page[-1][1]:
                    page.pop()
                pages.append([(side, [t])])
    return pages


def pixel_side(canvas: "Canvas", top: int, height: int, side: str) -> None:
    """The glitchy side marker: a black block with stepped pixel corners and the letter in white."""
    canvas.draw.rectangle([MARGIN, top, MARGIN + SIDE_W - 1, top + height - 1], fill=0)
    for cx, cy in ((MARGIN, top), (MARGIN + SIDE_W - 6, top), (MARGIN, top + height - 6),
                   (MARGIN + SIDE_W - 6, top + height - 6)):  # stepped pixel corners
        canvas.draw.rectangle([cx, cy, cx + 5, cy + 5], fill=255)
    font = _header_font(side)
    size = 40 if len(side) == 1 else 32 if len(side) == 2 else 24
    if font == SANS:
        size = 44 if len(side) == 1 else 34 if len(side) == 2 else 26
    label_w = canvas.width(side, font, size)
    canvas.text((MARGIN + int((SIDE_W - label_w) / 2), top + 8), side, font, size, fill=255)


@dataclass(frozen=True)
class TrackLook:
    """What a design changes on the tracks label: its fonts, the side marker, and the doodle."""
    big: str = MONO  # position, BPM, key
    small: str = SANS  # tags, artist, note
    side: Callable[["Canvas", int, int, str], None] = pixel_side  # (canvas, top, height, side letter)
    doodle: bool = True


GLITCHY_TRACKS = TrackLook()


def _render_tracks_page(groups: list[tuple[str, list[LabelTrack]]], tt: TrackType, warn, seed: str,
                        look: TrackLook = GLITCHY_TRACKS) -> bytes:
    """One label per pair of sides: the sides share the label's height in proportion to their
    tracks, and each side's rows are spread evenly over its block, so the label is always full."""
    canvas = Canvas()
    big, small = look.big, look.small
    x = MARGIN + SIDE_W + GAP
    width = W - MARGIN - x
    all_tracks = [t for _, tracks in groups for t in tracks]
    pos_w = int(max(canvas.width(t.position, big, tt.big) for t in all_tracks)) + 16
    show_bpm = any(_shows(t, "bpm") for t in all_tracks)
    show_key = any(_shows(t, "key") for t in all_tracks)
    bpm_w = int(max(canvas.width(t.bpm or "", big, tt.big) for t in all_tracks)) + 22 if show_bpm else 0
    key_w = int(max(canvas.width(t.key or "", big, tt.big) for t in all_tracks)) + 22 if show_key else 0

    natural = [_group_height(tracks, tt) for _, tracks in groups]
    gaps = 12 * (len(groups) - 1)
    # the last block loses its 6 px of trailing space, so it ends exactly at the bottom margin
    room = H - 2 * MARGIN + 6 - gaps
    weights = [sum(_row_height(t, tt) for t in tracks) for _, tracks in groups]
    y = MARGIN
    for (side, tracks), nat, weight in zip(groups, natural, weights, strict=True):
        top = y
        block = max(nat, round(room * weight / sum(weights)))  # share the height by tracks
        block_h = block - 6
        rows = [_row_height(t, tt) for t in tracks]
        slack = max(0, block - sum(rows)) / len(tracks)  # extra space per row
        row_top = float(top)
        for t, row_h in zip(tracks, rows, strict=True):
            ty = int(row_top + slack / 2)
            canvas.text((x, ty), t.position, big, tt.big)
            col = x + pos_w
            if _shows(t, "bpm"):
                canvas.text((col, ty), t.bpm, big, tt.big)
            col += bpm_w
            if _shows(t, "key"):
                canvas.text((col, ty), t.key, big, tt.big)
            col += key_w
            if _shows(t, "tags") and t.tags:
                text = ", ".join(t.tags)
                shown = canvas.ellipsize(text, small, tt.small, x + width - col)
                if shown != text:
                    warn(f"Tags of {t.position} were too long and have been cut")
                canvas.text((col, ty + (tt.big - tt.small) * 3 // 4), shown, small, tt.small)
            line = ty + _line_height(tt.big)
            if _shows(t, "artist"):
                shown = canvas.ellipsize(t.artist, small, tt.small, width)
                if shown != t.artist:
                    warn(f"The artist of {t.position} was too long and has been cut")
                canvas.text((x, line), shown, small, tt.small)
                line += _line_height(tt.small)
            if _shows(t, "note"):
                shown = canvas.ellipsize(t.note, small, tt.small, width)
                if shown != t.note:
                    warn(f"The note of {t.position} was too long and has been cut")
                canvas.text((x, line), shown, small, tt.small)
            row_top += row_h + slack
        look.side(canvas, top, block_h, side)
        y = top + block + 12
    if look.doodle:
        doodles.place(canvas.img, doodles.rng_for(seed), (x, MARGIN, W - MARGIN, H - MARGIN))
    return canvas.png()


def render_tracks(d: LabelData, warn, look: TrackLook = GLITCHY_TRACKS) -> list[bytes]:
    entries = [t for t in d.tracks if not t.skip]
    if not entries:
        return []
    tt = TrackType.at(d.sizes.tracks)
    pages = _paginate(entries, tt)
    if len(pages) > 1:
        warn(f"The tracks need {len(pages)} labels")
    return [_render_tracks_page(groups, tt, warn, f"{d.artist}\0{d.title}\0tracks-{i}", look)
            for i, groups in enumerate(pages, start=1)]


def render(d: LabelData) -> tuple[list[Rendered], list[str]]:
    """Both labels as PNGs, plus anything the person should look at before printing."""
    warnings: list[str] = []

    def warn_in(prefix: str):
        def warn(message: str) -> None:
            text = f"{prefix}: {message}"
            if text not in warnings:
                warnings.append(text)
        return warn

    from app.labels import designs  # the other designs build on this module

    main, look = designs.DESIGNS[d.design]
    out = [Rendered("main", "main", main(d, warn_in("Main label")))]
    pages = render_tracks(d, warn_in("Tracks label"), look)
    for i, png in enumerate(pages, start=1):
        out.append(Rendered("tracks", f"tracks-{i}" if len(pages) > 1 else "tracks", png))
    return out, warnings
