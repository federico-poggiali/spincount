"""The 8-bit touch: a pixel font for headers and one pixel doodle per label, dropped at random into
whatever space the text leaves free.

Everything random comes from a seed made of the record's artist and title (and which label it is),
so the preview and the print always match and each record keeps its own doodles."""
import random
import zlib
from functools import lru_cache

from PIL import Image, ImageFont

PIXEL = "Silkscreen-Bold.ttf"

DOODLES = {
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
    "headphones": """
        ....####....
        ..##....##..
        .#........#.
        #..........#
        #..........#
        #..........#
        ###......###
        ###......###
        ###......###
        .##......##.""",
    "note": """
        ....####.
        ....#####
        ....#..##
        ....#...#
        ....#....
        ....#....
        .####....
        #####....
        #####....
        .###.....""",
    "heart": """
        .###...###.
        #####.#####
        ###########
        ###########
        .#########.
        ..#######..
        ...#####...
        ....###....
        .....#.....""",
    "star": """
        .....#.....
        ....###....
        ....###....
        ###########
        .#########.
        ..#######..
        ..#######..
        .####.####.
        .###...###.
        .##.....##.""",
    "bolt": """
        ...#####
        ..#####.
        ..####..
        .####...
        .#######
        ....###.
        ...###..
        ..###...
        .##.....
        #.......""",
    "smiley": """
        ..######..
        .#......#.
        #........#
        #..#..#..#
        #........#
        #.#....#.#
        #..####..#
        .#......#.
        ..######..""",
    "ghost": """
        ...#####...
        .#########.
        ###########
        ##..###..##
        ##..###..##
        ###########
        ###########
        ###########
        ###.###.###
        .#...#...#.""",
    "mic": """
        ..###..
        .#####.
        .#####.
        .#####.
        #.###.#
        #.....#
        .#...#.
        ..###..
        ...#...
        ...#...
        .#####.""",
    "speaker": """
        ##########
        #...##...#
        #..####..#
        #...##...#
        #........#
        #..####..#
        #.##..##.#
        #.#.##.#.#
        #.##..##.#
        #..####..#
        #........#
        ##########""",
    "sun": """
        .....#.....
        .#...#...#.
        ..#.....#..
        ....###....
        ...#####...
        ##.#####.##
        ...#####...
        ....###....
        ..#.....#..
        .#...#...#.
        .....#.....""",
}
SCALES = (5, 6, 7)  # px per doodle pixel
CLEARANCE = 14  # white space kept around a doodle, so it never touches text
STEP = 8  # candidate spots are this far apart


def rng_for(*parts: str) -> random.Random:
    return random.Random(zlib.crc32("\0".join(parts).encode()))


def place(img: Image.Image, rng: random.Random, area: tuple[int, int, int, int]) -> str | None:
    """Draw one doodle at a random spot inside `area` where the label is still blank. Nothing is
    drawn when the label is too full. Returns the doodle's name."""
    name = rng.choice(sorted(DOODLES))
    rows = DOODLES[name].split()
    scale = rng.choice(SCALES)
    w, h = len(rows[0]) * scale, len(rows) * scale
    x0, y0, x1, y1 = area
    spots = [(x, y) for x in range(x0, x1 - w + 1, STEP) for y in range(y0, y1 - h + 1, STEP)]
    rng.shuffle(spots)
    for x, y in spots:
        box = (max(0, x - CLEARANCE), max(0, y - CLEARANCE),
               min(img.width, x + w + CLEARANCE), min(img.height, y + h + CLEARANCE))
        if img.crop(box).getextrema()[0] == 255:  # all white
            _draw(img, rows, scale, x, y)
            return name
    return None


def _draw(img: Image.Image, rows: list[str], scale: int, x: int, y: int) -> None:
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if cell == "#":
                img.paste(0, (x + c * scale, y + r * scale, x + (c + 1) * scale, y + (r + 1) * scale))


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
