import json
from pathlib import Path

import jsonschema

from audioresearch.models import Candidate, Quality, Reading, ReleaseIdentity, ReleaseResult, Status, TrackRef, TrackResult

SCHEMA = json.loads((Path(__file__).parent.parent / "output_schema.json").read_text())


def sample() -> ReleaseResult:
    return ReleaseResult(12345, [
        TrackResult("A1", Status.FOUND, "audio_cache/12345/A1.bandcamp.mp3", "bandcamp", 2, "https://x", Quality.FULL, 0.92,
                    "Bandcamp release matched on tracklist", [Reading("beatport", 124.0, "A minor")],
                    [{"source": "beatport", "quality": "preview", "confidence": 0.8, "audio_path": "p"}]),
        TrackResult("B1"),
    ], ["clone"], "2026-10-13T12:00:00Z")


def test_round_trip():
    r = sample()
    assert ReleaseResult.from_json(r.to_json()).to_dict() == r.to_dict()
    assert ReleaseResult.from_json(r.to_json()).track("A1").quality is Quality.FULL


def test_schema_accepts_sample_and_rejects_bad():
    jsonschema.validate(sample().to_dict(), SCHEMA)
    bad = sample().to_dict()
    bad["tracks"][0]["status"] = "maybe"
    try:
        jsonschema.validate(bad, SCHEMA)
        raise AssertionError("schema accepted a bad status")
    except jsonschema.ValidationError:
        pass


def test_identity_round_trip_and_for_track():
    i = ReleaseIdentity(1, "A", "T", "L", "C1", 2020, [TrackRef("A1", "A", "One", 200)], [{"uri": "u"}])
    assert ReleaseIdentity.from_dict(i.to_dict()).to_dict() == i.to_dict()
    c = Candidate("bandcamp", 2, "release", "https://r", "T", "A", tracklist=[TrackRef("1", "A", "One", 200, "https://t1")])
    tc = c.for_track(c.tracklist[0], "A1")
    assert (tc.kind, tc.url, tc.position, tc.extra["release_url"]) == ("track", "https://t1", "A1", "https://r")
