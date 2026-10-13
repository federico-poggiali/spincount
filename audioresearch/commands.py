"""CLI command implementations (filled in as the pipeline is built)."""
from __future__ import annotations


def _todo(name: str) -> int:
    print(f"`{name}` is not implemented yet")
    return 2


def research(args) -> int:
    return _todo("research")


def review(args) -> int:
    return _todo("review")


def report(args) -> int:
    return _todo("report")


def viewer(args) -> int:
    return _todo("viewer")
