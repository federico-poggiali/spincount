"""The label designs besides glitchy. Each is a main-label renderer plus a TrackLook for the tracks label.

- corrupted: glitchy, torn: the pixel wordmark sliced and displaced, a scanline divider, a terminal note.
- penguin: Jan Tschichold's Penguin grid: black top and foot bands, the title centred in the white band.
- republic: The Designers Republic (Warp, Wipeout): extended black wordmark, micro spec line, hazard
  stripes, a genre tag and a barcode made from the catalogue number.
- factory: Peter Saville's FAC sleeves: the catalogue number is the object, a code strip encodes it,
  everything else is small, tracked and quiet.

Only the glitchy designs carry doodles. Every design honours the hidden fields and the size sliders,
warns when it has to cut, and lets the note grow into whatever room is left."""

import hashlib

import qrcode
from PIL import Image, ImageDraw

from app.labels import doodles
from app.labels import render as R
from app.labels.data import LabelData

W, H, FLOOR, ELLIPSIS = R.W, R.H, R.FLOOR, R.ELLIPSIS
INK, PAPER = 0, 255
SERIF, DISPLAY = "PTSerif-Bold.ttf", "AbrilFatface-Regular.ttf"


def ARCH(wght: int, wdth: int = 100) -> str:  # noqa: N802 - reads like the font's name
    return f"Archivo.ttf:wght={wght},wdth={wdth}"


def JBM(wght: int = 800) -> str:  # noqa: N802
    return f"JetBrainsMono.ttf:wght={wght}"


# ---- type helpers: tracking, cap-top alignment, fallbacks ----


def _covers(name: str, text: str) -> bool:
    return doodles.covers(str(R.FONTS / name.partition(":")[0]), text.replace(" ", ""))


def pick(name: str, text: str, fallback: str = R.SANS) -> str:
    """The design's font when it can spell the text (a Japanese name, say), otherwise a plain one."""
    return name if _covers(name, text) else fallback


def cap(name: str, size: int) -> tuple[int, int]:
    """Space above the capitals, and the cap height: type is placed by its cap top so it sits on a grid."""
    top, bottom = R._font(name, size).getbbox("H")[1::2]
    return top, bottom - top


def width(c: R.Canvas, text: str, name: str, size: int, track: int = 0) -> float:
    font = R._font(name, size)
    if not track:
        return font.getlength(text)
    return sum(font.getlength(ch) for ch in text) + track * max(0, len(text) - 1)


def put(
    c: R.Canvas, x: float, y: int, text: str, name: str, size: int, track: int = 0, fill: int = INK
) -> int:
    """Draw with the cap top at y. Returns the cap height."""
    font = R._font(name, size)
    top, height = cap(name, size)
    if not track:
        c.draw.text((x, y - top), text, font=font, fill=fill)
    else:
        for ch in text:
            c.draw.text((x, y - top), ch, font=font, fill=fill)
            x += font.getlength(ch) + track
    return height


def put_right(c, xr, y, text, name, size, track=0, fill=INK) -> int:
    return put(c, xr - width(c, text, name, size, track), y, text, name, size, track, fill)


def put_center(c, x0, x1, y, text, name, size, track=0, fill=INK) -> int:
    return put(c, x0 + (x1 - x0 - width(c, text, name, size, track)) / 2, y, text, name, size, track, fill)


def scaled(sizes, scale: float) -> list[int]:
    out: list[int] = []
    for s in sizes:
        v = max(FLOOR, round(s * scale))
        if v not in out:
            out.append(v)
    return out


def fit(c, text, name, room, sizes, warn, what, track=0) -> tuple[str, int]:
    """The largest size at which `text` fits on one line; at the smallest, cut with an ellipsis.
    Tracked text gives up its letter-spacing before it gets cut."""
    for size in sizes:
        if width(c, text, name, size, track) <= room:
            return text, size
    if track > 1:
        return fit(c, text, name, room, sizes[-1:], warn, what, track=1)
    size = sizes[-1]
    while text and width(c, text + ELLIPSIS, name, size, track) > room:
        text = text[:-1]
    warn(f"{what} was too long and has been cut")
    return text.rstrip() + ELLIPSIS, size


def fill(c, text, name, room_w, room_h, top, floor, warn, what, lead=1.25) -> tuple[list[str], int, int]:
    """Lines, size and line height for `text` at the largest size from `top` down that fits the box:
    a short note fills the empty space instead of leaving it white."""
    for size in range(top, floor - 1, -2):
        lh = round(size * lead)
        lines = c.wrap(text, name, size, room_w)
        if len(lines) * lh - (lh - size) <= room_h:
            return lines, size, lh
    size, lh = floor, round(floor * lead)
    most = max(0, (room_h + lh - size) // lh)
    if most == 0:
        warn(f"{what} does not fit on the label")
        return [], size, lh
    lines = c.wrap(text, name, size, room_w)
    warn(f"{what} was too long and has been cut")
    return lines[: most - 1] + [c.ellipsize(" ".join(lines[most - 1 :]), name, size, room_w)], size, lh


def _shown(d: LabelData):
    def shown(field: str) -> bool:
        value = d.qr_url if field == "qr" else getattr(d, field)
        return field not in d.hidden and bool(value)

    return shown


def qr_square(c, url: str, x: int, y: int, size: int) -> int:
    """A bare QR code (no frame) with its top-left at (x, y). Returns its side."""
    q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_L)
    q.add_data(url)
    q.make(fit=True)
    matrix = q.get_matrix()
    scale = max(3, size // len(matrix))
    for r, row in enumerate(matrix):
        for col, dark in enumerate(row):
            if dark:
                c.draw.rectangle(
                    [x + col * scale, y + r * scale, x + (col + 1) * scale - 1, y + (r + 1) * scale - 1],
                    fill=INK,
                )
    return len(matrix) * scale


# =============================== corrupted ===============================


def corrupted(d: LabelData, warn) -> bytes:
    c = R.Canvas()
    m, sz, shown = R.MARGIN, d.sizes, _shown(d)
    right = W - m
    qr = R._qr(c, d.qr_url, right, m, 120) if shown("qr") else 0
    text_w = right - m - (qr + 16 if qr else 0)

    # the wordmark, drawn off-canvas and pasted back in torn, displaced slices
    art = d.artist.upper()
    name = R._header_font(art)
    step = 8 if name == R.PIXEL else 2
    options = [max(FLOOR, round(s * sz.artist / step) * step) for s in (80, 72, 64, 56, 48, 40, 32)]
    art, s = fit(c, art, name, text_w - 20, list(dict.fromkeys(options)), warn, "The artist")
    top, height = cap(name, s)
    tmp = Image.new("L", (W, height + 4), PAPER)
    ImageDraw.Draw(tmp).text((0, 2 - top), art, font=R._font(name, s), fill=INK)
    rng = doodles.rng_for(d.artist, "glitch")
    yy = 0
    while yy < tmp.height:
        band = max(2, round(rng.choice((8, 10, 14, 18)) * s / 80))
        dx = round(rng.choice((0, 0, 0, 0, -6, 6, 10)) * s / 80)  # the tear scales with the type
        c.img.paste(tmp.crop((0, yy, text_w, min(yy + band, tmp.height))), (m + dx, m + yy))
        yy += band
    y = m + tmp.height + 16

    # title, printed twice slightly out of register
    title_fit = R._scaled([(34, 1), (32, 1), (30, 1), (28, 1), (26, 1), (30, 2), (26, 2)], sz.title)
    lines, ts, _ = c.fit(d.title, R.SANS, text_w - 4, title_fit)
    for line in lines:
        c.text((m + 3, y + 3), line, R.SANS, ts)
        c.text((m, y), line, R.SANS, ts)
        y += R._line_height(ts)
    details = " · ".join(
        p
        for p in (
            (d.label or "").upper() if shown("label") else "",
            f"CAT# {d.catno}" if shown("catno") else "",
        )
        if p
    )
    if details:
        y = c.block(
            y + 4,
            details,
            R.MONO,
            text_w,
            R._scaled([(26, 1), (24, 1), (22, 1)], sz.details),
            warn,
            "The label line",
        )
    y = max(y + 10, m + qr + 10)

    # a scanline gradient as the divider: the lines thicken left to right
    for i in range(0, 24, 3):
        c.draw.rectangle([m + (21 - i) * 20, y + i, right, y + i + (1 if i < 12 else 2)], fill=INK)
    y += 34
    info = " · ".join(
        p
        for p in (
            d.year if shown("year") else None,
            d.country if shown("country") else None,
            ", ".join(d.styles) if shown("styles") else None,
        )
        if p
    )
    if info:
        y = (
            c.block(
                y,
                info,
                R.SANS,
                right - m,
                R._scaled([(28, 1), (26, 1), (24, 2)], sz.info),
                warn,
                "The info line",
            )
            + 8
        )
    if shown("note"):
        lines, ns, lh = fill(
            c,
            "> " + d.note + " █",
            R.MONO,
            right - m,
            H - m - y,
            round(40 * sz.note),
            max(FLOOR, round(24 * min(1, sz.note))),
            warn,
            "The note",
        )
        for line in lines:
            c.text((m, y), line, R.MONO, ns)
            y += lh
    doodles.place(c.img, doodles.rng_for(d.artist, d.title), (m, m, W - m, H - m))
    return c.png()


def corrupted_side(c: R.Canvas, top: int, height: int, side: str) -> None:
    """The glitchy block, with scanlines cut through it."""
    R.pixel_side(c, top, height, side)
    for yy in range(top + 58, top + height - 8, 6):
        c.draw.rectangle([R.MARGIN + 6, yy, R.MARGIN + R.SIDE_W - 7, yy + 1], fill=PAPER)


# =============================== penguin ===============================

BAND = 118


def penguin(d: LabelData, warn) -> bytes:
    c = R.Canvas()
    sz, shown = d.sizes, _shown(d)
    c.draw.rectangle([0, 0, W - 1, BAND - 1], fill=INK)
    c.draw.rectangle([0, H - BAND, W - 1, H - 1], fill=INK)
    c.draw.rectangle([0, BAND + 8, W - 1, BAND + 10], fill=INK)
    c.draw.rectangle([0, H - BAND - 11, W - 1, H - BAND - 9], fill=INK)

    # top band: the label in tracked capitals over the artist, set in a display serif, white
    art_font = pick(DISPLAY, d.artist)
    if shown("label"):
        lab, ls = fit(
            c,
            d.label.upper(),
            pick(SERIF, d.label),
            W - 80,
            scaled([22, 20, 18], sz.details),
            warn,
            "The label",
            track=8,
        )
        put_center(c, 0, W, 26, lab, pick(SERIF, d.label), ls, track=8, fill=PAPER)
        art_top, art_room = 60, BAND - 60 - 16
    else:
        art_top, art_room = 0, BAND
    art, s = fit(c, d.artist, art_font, W - 80, scaled(range(58, 27, -2), sz.artist), warn, "The artist")
    s = min(s, max(FLOOR, art_room - 4) if shown("label") else s)
    ah = cap(art_font, s)[1]
    put_center(
        c,
        0,
        W,
        art_top + (art_room - ah) // 2 if not shown("label") else art_top + max(0, (art_room - ah) // 2),
        art,
        art_font,
        s,
        fill=PAPER,
    )

    # centre band: title, then the note, centred as one block
    mid_top, mid_h = BAND + 11, H - 2 * BAND - 22
    tf = pick(SERIF, d.title)
    title_fit = R._scaled([(44, 1), (40, 1), (36, 1), (34, 2), (30, 2), (26, 2)], sz.title)
    tlines, ts, _ = c.fit(d.title, tf, W - 120, title_fit)
    t_lh = cap(tf, ts)[1] + round(ts * 0.42)
    block = len(tlines) * t_lh - round(ts * 0.42)
    note_lines, ns, nlh = [], 0, 0
    if shown("note"):
        nf = pick(SERIF, d.note)
        room = mid_h - block - 24 - 16
        note_lines, ns, nlh = fill(
            c,
            d.note,
            nf,
            W - 160,
            room,
            round(30 * sz.note),
            max(FLOOR, round(20 * min(1, sz.note))),
            warn,
            "The note",
            lead=1.3,
        )
        if note_lines:
            block += 22 + len(note_lines) * nlh - (nlh - cap(nf, ns)[1])
    y = mid_top + (mid_h - block) // 2
    for line in tlines:
        put_center(c, 0, W, y, line, tf, ts)
        y += t_lh
    y += 22 - round(ts * 0.42)
    for line in note_lines:
        put_center(c, 0, W, y, line, pick(SERIF, d.note), ns)
        y += nlh

    # foot band: the cartouche (QR code, or the label's initial), cat# left, year and style right
    cy = H - BAND // 2
    if shown("qr"):
        side = 92
        c.draw.rounded_rectangle(
            [W // 2 - side // 2 - 10, cy - side // 2 - 10, W // 2 + side // 2 + 9, cy + side // 2 + 9],
            radius=18,
            fill=PAPER,
        )
        qr_square(c, d.qr_url, W // 2 - side // 2, cy - side // 2, side)
        gap = side // 2 + 30
    else:
        c.draw.ellipse([W // 2 - 52, cy - 32, W // 2 + 52, cy + 32], fill=PAPER)
        c.draw.ellipse([W // 2 - 46, cy - 26, W // 2 + 46, cy + 26], outline=INK, width=2)
        initial = ((d.label if shown("label") else None) or d.artist or "·")[0].upper()
        f = pick(DISPLAY, initial, R.SANS)
        put_center(c, W // 2 - 50, W // 2 + 50, cy - cap(f, 36)[1] // 2, initial, f, 36)
        gap = 82
    meta = scaled([20, 18], sz.info)
    room = W // 2 - gap - 34
    if shown("catno"):
        cat, s = fit(
            c,
            d.catno.upper(),
            pick(SERIF, d.catno),
            room,
            scaled([20, 18], sz.details),
            warn,
            "The cat#",
            track=3,
        )
        put(c, 34, cy - cap(SERIF, s)[1] // 2, cat, pick(SERIF, d.catno), s, track=3, fill=PAPER)
    when = " ".join(
        p for p in (d.year if shown("year") else None, d.country if shown("country") else None) if p
    ).upper()
    style = (d.styles[0] if shown("styles") else "").upper()
    one = " ".join(p for p in (when, style) if p)
    if one and width(c, one, pick(SERIF, one), meta[0], 3) <= room:
        put_right(
            c, W - 34, cy - cap(SERIF, meta[0])[1] // 2, one, pick(SERIF, one), meta[0], track=3, fill=PAPER
        )
    elif one:  # two lines: year and country over the style
        lines = [x for x in (when, style) if x]
        size = meta[-1]
        y = cy - (len(lines) * (cap(SERIF, size)[1] + 12) - 12) // 2
        for line in lines:
            txt, size = fit(c, line, pick(SERIF, line), room, [size], warn, "The year and style", track=3)
            put_right(c, W - 34, y, txt, pick(SERIF, line), size, track=3, fill=PAPER)
            y += cap(SERIF, size)[1] + 12
    return c.png()


def penguin_side(c: R.Canvas, top: int, height: int, side: str) -> None:
    """A plain black band, square, with the side letter in the display serif."""
    c.draw.rectangle([R.MARGIN, top, R.MARGIN + R.SIDE_W - 1, top + height - 1], fill=INK)
    f = pick(DISPLAY, side)
    s = 44 if len(side) == 1 else 30
    put_center(c, R.MARGIN, R.MARGIN + R.SIDE_W, top + 12, side, f, s, fill=PAPER)


# =============================== republic ===============================


def _stripes(c, x0, y0, x1, y1, step=14, t=7) -> None:
    tile = Image.new("L", (x1 - x0, y1 - y0), PAPER)
    td = ImageDraw.Draw(tile)
    h = y1 - y0
    for k in range(-h, x1 - x0, step):
        td.polygon([(k, h), (k + t, h), (k + t + h, 0), (k + h, 0)], fill=INK)
    c.img.paste(tile, (x0, y0))


def _barcode(c, x, y, w, h, seed: str) -> None:
    """Decorative bars from the cat# (not a scannable code: the QR is for scanning)."""
    bits = "".join(f"{b:08b}" for b in hashlib.sha1(seed.encode()).digest())
    xx, i = x, 0
    while xx < x + w:
        bw = 2 + int(bits[i % len(bits)]) * 2 + int(bits[(i + 7) % len(bits)])
        if i % 2 == 0:
            c.draw.rectangle([xx, y, min(xx + bw, x + w) - 1, y + h - 1], fill=INK)
        xx += bw
        i += 1


def republic(d: LabelData, warn) -> bytes:
    c = R.Canvas()
    m, sz, shown = 22, d.sizes, _shown(d)
    micro = JBM(800)

    # the spec line, with registration dots on the right
    spec = [
        f"{d.label.upper()}™" if shown("label") else "",
        d.catno.upper() if shown("catno") else "",
        d.year if shown("year") else "",
        f"MADE IN {d.country.upper()}" if shown("country") else "",
    ]
    spec_text = "  ▲  ".join(p for p in spec if p)
    if spec_text:
        # a micro line, so it may go below the usual floor: it is set in a heavy mono
        spec_sizes = list(dict.fromkeys(max(14, round(v * sz.details)) for v in (18, 16, 15, 14)))
        txt, s = fit(
            c,
            spec_text,
            pick(micro, spec_text, R.MONO),
            W - 2 * m - 80,
            spec_sizes,
            warn,
            "The spec line",
            track=1,
        )
        put(c, m, m, txt, pick(micro, spec_text, R.MONO), s, track=1)
    for k in range(3):
        cx = W - m - 6 - k * 20
        c.draw.ellipse([cx - 6, m - 1, cx + 6, m + 11], fill=INK if k != 1 else PAPER, outline=INK, width=2)

    # the wordmark: extended black, set tight
    art = d.artist.upper()
    af = pick(ARCH(900, 125), art)
    art, s = fit(
        c, art, af, W - 2 * m + 4, scaled(range(110, 37, -2), sz.artist), warn, "The artist", track=-3
    )
    y = m + 30
    y += put(c, m - 3, y, art, af, s, track=-3) + 14

    # hazard stripes and the title
    title = d.title.upper()
    tf = pick(ARCH(800, 110), title)
    t, ts = fit(c, title, tf, W - 2 * m - 110, scaled(range(30, 17, -1), sz.title), warn, "The title")
    bar = max(34, cap(tf, ts)[1] + 12)
    _stripes(c, m, y, m + 92, y + bar)
    put(c, m + 108, y + (bar - cap(tf, ts)[1]) // 2, t, tf, ts)
    y += bar + 18

    if shown("styles"):
        tag = "→ " + " / ".join(s.upper() for s in d.styles)
        gf = pick(ARCH(900, 125), tag)
        tag, gs = fit(c, tag, gf, W - 2 * m - 24, scaled([22, 20, 18], sz.info), warn, "The styles", track=1)
        gh = cap(gf, gs)[1]
        c.draw.rectangle([m, y, m + width(c, tag, gf, gs, 1) + 24, y + gh + 18], fill=INK)
        put(c, m + 12, y + 9, tag, gf, gs, track=1, fill=PAPER)
        y += gh + 18 + 16

    # the bottom row: QR and barcode cluster on the right, catalogue line on the left
    foot = H - m - 15
    cluster_x = W - m
    if shown("qr"):
        side = 84
        qr_square(c, d.qr_url, W - m - side, foot - side - 8, side)
        cluster_x = W - m - side - 14
    if shown("catno"):
        _barcode(c, cluster_x - 180, foot - 72, 180, 64, d.catno)
        put(
            c,
            cluster_x - 180,
            foot + 2,
            d.catno.upper()[:18],
            R.MONO if not _covers(micro, d.catno) else micro,
            15,
            track=2,
        )
    put(c, m, foot + 2, "SIDE A / SIDE B  ▸▸  33 RPM", micro, 15, track=1)

    if shown("note"):
        nf = pick(JBM(700), d.note, R.MONO)
        room_w = (cluster_x - 200 if shown("catno") or shown("qr") else W - m) - m
        lines, ns, lh = fill(
            c,
            d.note.upper(),
            nf,
            room_w,
            foot - 16 - y,
            round(28 * sz.note),
            max(FLOOR, round(18 * min(1, sz.note))),
            warn,
            "The note",
            lead=1.35,
        )
        for line in lines:
            put(c, m, y, line, nf, ns)
            y += lh
    return c.png()


def republic_side(c: R.Canvas, top: int, height: int, side: str) -> None:
    """Hazard stripes down the side, the letter knocked out in a white box at the top."""
    x0, x1 = R.MARGIN, R.MARGIN + R.SIDE_W
    _stripes(c, x0, top, x1, top + height, step=12, t=6)
    f = pick(ARCH(900, 125), side)
    s = 34 if len(side) == 1 else 22
    c.draw.rectangle([x0, top, x1 - 1, top + 56], fill=INK)
    put_center(c, x0, x1, top + 12, side, f, s, fill=PAPER)


# =============================== factory ===============================


def _code_strip(c, x, y, text, sq=14, gap=4) -> int:
    """Each character as a column of five squares, filled for 1 and outlined for 0: a private code."""
    xx = x
    for ch in text.upper():
        if ch == " ":
            xx += sq
            continue
        v = ord(ch) % 32
        for b in range(5):
            box = [xx, y + b * (sq + gap), xx + sq - 1, y + b * (sq + gap) + sq - 1]
            if v >> (4 - b) & 1:
                c.draw.rectangle(box, fill=INK)
            else:
                c.draw.rectangle(box, outline=INK, width=2)
        xx += sq + gap
    return xx - x


def factory(d: LabelData, warn) -> bytes:
    c = R.Canvas()
    m, sz, shown = 34, d.sizes, _shown(d)
    hero = (d.catno if shown("catno") else d.artist).upper()
    hf = pick(ARCH(300), hero)
    hero, hs = fit(
        c,
        hero,
        hf,
        W - 2 * m + 6,
        scaled(range(104, 39, -2), sz.details if shown("catno") else sz.artist),
        warn,
        "The cat#",
        track=-3,
    )
    y = m + 6
    y += put(c, m - 4, y, hero, hf, hs, track=-3) + 26

    if shown("catno"):  # the artist is the hero when there is no cat#
        af = pick(ARCH(650), d.artist)
        art, s = fit(
            c, d.artist.upper(), af, W - 2 * m, scaled([20, 18], sz.artist), warn, "The artist", track=4
        )
        y += put(c, m, y, art, af, s, track=4) + 12
    tf = pick(ARCH(420), d.title)
    title, s = fit(c, d.title.upper(), tf, W - 2 * m, scaled([20, 18], sz.title), warn, "The title", track=4)
    y += put(c, m, y, title, tf, s, track=4) + 24

    # bottom: code strip left, metadata right (left of the QR when it shows)
    strip_top = H - m - 86
    if shown("catno"):
        _code_strip(c, m, strip_top, d.catno.replace(" ", "")[:12])
    right = W - m
    if shown("qr"):
        side = 86
        qr_square(c, d.qr_url, W - m - side, H - m - side, side)
        right = W - m - side - 20
    meta = [
        d.label if shown("label") else "",
        " ".join(
            p for p in (d.year if shown("year") else None, d.country if shown("country") else None) if p
        ),
        ", ".join(d.styles) if shown("styles") else "",
    ]
    mf = ARCH(520)
    yy = strip_top
    room = right - (m + 12 * 18 + 30)
    for line in meta:
        if line:
            f = pick(mf, line)
            txt, s = fit(c, line.upper(), f, room, scaled([18], sz.info), warn, "The details", track=3)
            put_right(c, right, yy, txt, f, s, track=3)
            yy += 28

    if shown("note"):
        nf = pick(ARCH(420), d.note)
        lines, ns, lh = fill(
            c,
            d.note,
            nf,
            W - 2 * m,
            strip_top - 22 - y,
            round(32 * sz.note),
            max(FLOOR, round(20 * min(1, sz.note))),
            warn,
            "The note",
            lead=1.3,
        )
        for line in lines:
            put(c, m, y, line, nf, ns)
            y += lh
    return c.png()


def factory_side(c: R.Canvas, top: int, height: int, side: str) -> None:
    """No block: a light letter and a code column for it, hung from a hairline."""
    x0 = R.MARGIN
    c.draw.rectangle([x0, top, x0 + R.SIDE_W - 8, top + 2], fill=INK)
    f = pick(ARCH(300), side)
    put(c, x0, top + 12, side, f, 48 if len(side) == 1 else 30)
    v = ord(side[0]) % 32
    for b in range(5):
        y = top + 74 + b * 18
        if y + 14 > top + height:
            break
        box = [x0, y, x0 + 13, y + 13]
        if v >> (4 - b) & 1:
            c.draw.rectangle(box, fill=INK)
        else:
            c.draw.rectangle(box, outline=INK, width=2)


DESIGNS = {
    "glitchy": (R.render_main, R.GLITCHY_TRACKS),
    "corrupted": (corrupted, R.TrackLook(side=corrupted_side)),
    "penguin": (penguin, R.TrackLook(big=SERIF, small=SERIF, side=penguin_side, doodle=False)),
    "republic": (republic, R.TrackLook(big=JBM(800), small=ARCH(700, 110), side=republic_side, doodle=False)),
    "factory": (factory, R.TrackLook(big=ARCH(520), small=ARCH(420), side=factory_side, doodle=False)),
}
