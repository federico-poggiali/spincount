import pytest

from audioresearch.decide import Accepted, confidence, decide_track
from audioresearch.matcher import Match
from audioresearch.models import Candidate, FetchedAudio, Quality, Status
from audioresearch.verify import Verification


def acc(adapter, score=0.9, q=Quality.FULL, level=2, agreement=None, duration_ok=True, via="track", **extra):
    c = Candidate(adapter, level, "track", f"https://{adapter}", "T", "A", 360, extra=extra)
    f = FetchedAudio(f"/tmp/{adapter}.mp3", adapter, c.url, q, 360.0)
    return Accepted(Match("A1", c, score, via), f, Verification(True, ["duration 360s agrees with Discogs 360s"], duration_ok=duration_ok),
                    level, agreement)


def test_clear_match_is_found_with_a_readable_reason():
    r = decide_track("A1", [acc("bandcamp", 0.95, via="release")], [])
    assert r.status == Status.FOUND and r.confidence == pytest.approx(0.6 * 0.95 + 0.15 + 0.125)
    assert "release matched on tracklist" in r.reason


def test_agreement_raises_confidence():
    base = confidence(acc("a"))
    assert confidence(acc("a", agreement=True)) > base > confidence(acc("a", agreement=False))


def test_disagreement_sends_the_track_to_review_whatever_the_score():
    r = decide_track("A1", [acc("a", 0.99, agreement=False), acc("b", 0.99, agreement=False)], [])
    assert r.status == Status.REVIEW and r.confidence < 0.6 and "DISAGREES" in r.reason


def test_review_threshold():
    weak = acc("a", 0.45, duration_ok=None)
    assert decide_track("A1", [weak], []).status == Status.REVIEW
    assert decide_track("A1", [weak], [], review_threshold=0.5).status == Status.FOUND
    assert decide_track("A1", [acc("a", 0.9)], []).status == Status.FOUND


def test_quality_beats_confidence_and_alternatives_remain():
    clip = acc("deejay_de", 0.99, Quality.CLIP, level=5, agreement=True)
    full = acc("youtube", 0.7, Quality.FULL, level=1)
    r = decide_track("A1", [clip, full], [])
    assert r.source == "youtube" and r.quality == Quality.FULL


def test_level_0_always_wins_with_full_confidence():
    local = acc("local_files", 1.0, level=0, via="trusted", how="matched by position")
    r = decide_track("A1", [acc("bandcamp", 0.99, agreement=True), local], [])
    assert (r.source, r.level, r.confidence, r.status) == ("local_files", 0, 1.0, Status.FOUND)
    assert "your own file" in r.reason
    manual = acc("manual_link", 1.0, level=0, via="trusted", manual=True)
    assert confidence(manual) == 0.95 and "pasted link" in decide_track("A1", [manual], []).reason


def test_nothing_accepted_is_not_found_but_keeps_readings():
    from audioresearch.models import Reading
    r = decide_track("A1", [], [Reading("beatport", 124.0, "A minor")])
    assert r.status == Status.NOT_FOUND and r.readings[0].bpm == 124.0
