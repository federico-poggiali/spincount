"""The 8-bit look: a pixel font for headers, glitch slices on the artist, a pixel sprite.

Everything random comes from a seed made of the record's artist and title, so the preview and the
print always match and each record keeps its own glitch."""
import random
import zlib
from functools import lru_cache

from PIL import Image, ImageFont

PIXEL = "Silkscreen-Bold.ttf"

SPRITES = {
    "vinyl": """
        ....####....
        ..########..
        .##########.
        .####..####.
        ####....####
        ###..##..###
        ###..##..###
        ####....####
        .####..####.
        .##########.
        ..########..
        ....####....""",
    "invader": """
        ..#.....#..
        ...#...#...
        ..#######..
        .##.###.##.
        ###########
        #.#######.#
        #.#.....#.#
        ...##.##...""",
    "cassette": """
        ##############
        #............#
        #.##########.#
        #.#.##..##.#.#
        #.#.##..##.#.#
        #.##########.#
        #............#
        #...######...#
        ##############""",
}
SPRITE_SCALE = 4


def rng_for(artist: str, title: str) -> random.Random:
    return random.Random(zlib.crc32(f"{artist}\0{title}".encode()))


def sprite_for(artist: str, title: str) -> list[str]:
    name = sorted(SPRITES)[zlib.crc32(f"{title}\0{artist}".encode()) % len(SPRITES)]
    return SPRITES[name].split()


def sprite_size(rows: list[str]) -> tuple[int, int]:
    return len(rows[0]) * SPRITE_SCALE, len(rows) * SPRITE_SCALE


def draw_sprite(draw, rows: list[str], x: int, y: int) -> None:
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if cell == "#":
                px, py = x + c * SPRITE_SCALE, y + r * SPRITE_SCALE
                draw.rectangle([px, py, px + SPRITE_SCALE - 1, py + SPRITE_SCALE - 1], fill=0)


@lru_cache(maxsize=1)
def _missing_mask(path: str) -> bytes:
    return bytes(ImageFont.truetype(path, 32).getmask("\U0010fffd", mode="1"))


@lru_cache(maxsize=512)
def _has_glyph(path: str, char: str) -> bool:
    mask = bytes(ImageFont.truetype(path, 32).getmask(char, mode="1"))
    return char.isspace() or mask != _missing_mask(path)


def covers(path: str, text: str) -> bool:
    """Whether the pixel font has every character: it only knows Latin, so 'Ryōji' falls back."""
    return all(_has_glyph(path, ch) for ch in text)


def slice_glitch(img: Image.Image, box: tuple[int, int, int, int], unit: int,
                 rng: random.Random) -> None:
    """Shift one of the pixel font's rows sideways, like a CRT losing sync. Slices follow
    the font's own pixel grid (`unit` px), and nothing leaves the box, so it never hits the QR code."""
    x0, y0, x1, y1 = box
    rows = (y1 - y0) // unit
    if rows < 3:
        return
    # one row per line of text (a line is 5 rows of caps plus a gap), so the name stays readable
    for row in rng.sample(range(rows), k=max(1, rows // 6)):
        top = y0 + row * unit
        dx = rng.choice((-1, 1)) * unit
        band = img.crop((x0, top, x1, top + unit))
        shifted = Image.new("L", band.size, 255)
        shifted.paste(band, (dx, 0))
        img.paste(shifted, (x0, top))
