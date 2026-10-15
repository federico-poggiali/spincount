"""Command line: python -m audioresearch <discogs link> (or research / review / report / viewer).

TEMPORARY (kept for debugging only; remove once the app covers it, see README)."""
from __future__ import annotations

import argparse
import sys

COMMANDS = {"research", "review", "report", "viewer"}


def _levels(text: str) -> list[int]:
    """'0-5' -> [0..5]; '1,3' -> [1, 3]."""
    out: list[int] = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return sorted(set(out))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audioresearch", description="Find audio for every track of a Discogs release.")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("research", help="research one release (a bare Discogs URL also works)")
    r.add_argument("url", help="Discogs release/master URL or release id")
    r.add_argument("--levels", type=_levels, default=list(range(6)), help="e.g. 0-5 or 1,3")
    r.add_argument("--refresh", action="store_true", help="ignore the cache")
    r.add_argument("--search-all", action="store_true", help="test mode: search every level for every track, never stop early")
    r.add_argument("--json", metavar="FILE", help="also write the result as JSON")
    rv = sub.add_parser("review", help="accept, reject or paste a link for tracks that need review")
    rv.add_argument("release_id", type=int)
    rp = sub.add_parser("report", help="show the provenance log of a release")
    rp.add_argument("release_id", type=int)
    v = sub.add_parser("viewer", help="local process viewer (temporary debug page)")
    v.add_argument("--fake", action="store_true", help="use fake adapters")
    v.add_argument("--port", type=int, default=8200)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "research")  # `python -m audioresearch <url>`
    args = build_parser().parse_args(argv)
    from . import commands

    return getattr(commands, args.command)(args)
