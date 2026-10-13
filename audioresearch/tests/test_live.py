"""Live checks: real networks and real sites. Skipped unless `--live` is passed.

    .venv/bin/python -m pytest audioresearch/tests/test_live.py --live -q -s
Set AUDIORESEARCH_LIVE_RELEASE=<discogs release id> to pick the release (default: Rick Astley, 249504).
"""
import os

import pytest

from audioresearch import config
from audioresearch.models import Status
from audioresearch.pipeline import research
from audioresearch.store import Store

RELEASE = os.environ.get("AUDIORESEARCH_LIVE_RELEASE", "249504")
pytestmark = pytest.mark.live


def run_levels(tmp_path, levels):
    return research(RELEASE, levels, store=Store(tmp_path / "live.db"), audio_dir=tmp_path / "audio")


def test_level_1_returns_audio_for_at_least_one_track(tmp_path):
    res = run_levels(tmp_path, [1])
    print(res.to_json())
    got = [t for t in res.tracks if t.status != Status.NOT_FOUND]
    assert got and all(os.path.exists(t.audio_path) for t in got)
