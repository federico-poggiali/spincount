from audioresearch.models import Candidate, ReleaseIdentity, TrackRef
from audioresearch.scope import RELEASE, TRACK, UNKNOWN, classify
from audioresearch.tests.test_level1 import bells


def cand(duration=None, description=""):
    return Candidate("discogs_youtube", 1, "track", "https://youtu.be/x", "t", "", duration, extra={"description": description})


def ident(*durs):
    i = bells()
    i.tracks = [TrackRef(f"A{n}", "Jeff Mills", f"T{n}", d) for n, d in enumerate(durs, 1)]
    return i


def test_timestamps_mean_whole_record():
    assert classify(ident(300, 300), cand(60, "0:00 One\n5:00 Two\n10:00 Three"))[0] == RELEASE


def test_duration_decides_when_known():
    i = ident(300, 280, 320)
    assert classify(i, cand(1000))[0] == RELEASE
    assert classify(i, cand(305))[0] == TRACK


def test_no_data_means_unknown():
    assert classify(ident(None, None), cand(300))[0] == UNKNOWN
    assert classify(ident(300, 300), cand(None))[0] == UNKNOWN
