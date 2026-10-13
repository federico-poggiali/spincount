from audioresearch.matcher import (RELEASE_THRESHOLD, TRACK_IN_RELEASE_THRESHOLD, match_candidates, match_release,
                                   match_track, match_tracks_in_release, track_threshold)
from audioresearch.models import Candidate, ReleaseIdentity, TrackRef


def identity(tracks=None, catno="ABC001"):
    tracks = tracks or [TrackRef("A1", "Foo", "Night Drive", 360), TrackRef("A2", "Foo", "Morning Light", 400),
                        TrackRef("B1", "Foo", "Deep Water", 380), TrackRef("B2", "Foo", "Last Train", 300)]
    return ReleaseIdentity(1, "Foo", "Night Drive EP", "Label", catno, 2020, tracks)


def release_cand(tracklist, title="Night Drive EP", artist="Foo", catno=None):
    return Candidate("bandcamp", 2, "release", "https://bc/r", title, artist, tracklist=tracklist, catno=catno)


def numbered(tracks, shift=0):
    return [TrackRef(str(i), t.artist, t.title, t.duration + shift if t.duration else None, f"https://bc/t{i}")
            for i, t in enumerate(tracks, 1)]


def test_exact_release():
    i = identity()
    c = release_cand(numbered(i.tracks, 1), catno="abc 001")
    assert match_release(i, c) > 0.95
    assert set(match_tracks_in_release(i, c)) == {"A1", "A2", "B1", "B2"}


def test_release_with_one_bonus_track():
    i = identity()
    tl = numbered(i.tracks) + [TrackRef("5", "Foo", "Bonus Beats", 200, "https://bc/t5")]
    c = release_cand(tl)
    assert match_release(i, c) >= RELEASE_THRESHOLD + 0.2
    assert len(match_tracks_in_release(i, c)) == 4


def test_wrong_release_with_same_title():
    i = identity()
    other = [TrackRef(str(n), "Someone Else", t, 250) for n, t in enumerate(["Alpha", "Bravo", "Charlie", "Delta"], 1)]
    c = release_cand(other, artist="Someone Else", catno="ZZZ999")
    assert match_release(i, c) < RELEASE_THRESHOLD
    assert match_candidates(i, i.tracks, [c]).matches == {}


def test_remix_posing_as_original():
    i = identity()
    t = i.tracks[0]
    remix = Candidate("yt", 1, "track", "u", "Night Drive (Bob Remix)", "Foo", 360)
    original = Candidate("yt", 1, "track", "u2", "Foo - Night Drive", "Foo", 361)
    assert match_track(i, t, remix) < track_threshold(i) <= match_track(i, t, original)
    # and the reverse: Discogs lists the remix, the candidate is the plain song
    j = identity([TrackRef("A1", "Foo", "Night Drive (Bob Remix)", 360), TrackRef("A2", "Foo", "Other", 300)])
    assert match_track(j, j.tracks[0], original) < track_threshold(j)


def test_two_mixes_of_one_song_on_one_release():
    tracks = [TrackRef("A1", "Foo", "Night Drive (Original Mix)", 360), TrackRef("B1", "Foo", "Night Drive (Dub Mix)", 372)]
    i = identity(tracks)
    c = release_cand([TrackRef("1", "Foo", "Night Drive (Dub Mix)", 372, "d"), TrackRef("2", "Foo", "Night Drive (Original Mix)", 360, "o")])
    m = match_tracks_in_release(i, c)
    assert set(m) == {"A1", "B1"} and min(m.values()) >= TRACK_IN_RELEASE_THRESHOLD
    ms = match_candidates(i, i.tracks, [c]).matches
    assert ms["A1"][0].candidate.url == "o" and ms["B1"][0].candidate.url == "d"
    # a release holding only the dub must not satisfy the original
    only_dub = release_cand([TrackRef("1", "Foo", "Night Drive (Dub Mix)", 372, "d")], title="Night Drive")
    assert "A1" not in match_tracks_in_release(i, only_dub)


def test_plain_title_goes_to_the_original_not_the_dub():
    tracks = [TrackRef("A1", "Foo", "Night Drive (Original Mix)", None), TrackRef("B1", "Foo", "Night Drive (Dub Mix)", None)]
    i = identity(tracks)
    plain = Candidate("yt", 1, "track", "u", "Foo - Night Drive", "Foo", None)
    assert list(match_candidates(i, i.tracks, [plain]).matches) == ["A1"]


def test_missing_durations_still_match():
    tracks = [TrackRef("A1", "Foo", "Night Drive", None), TrackRef("A2", "Foo", "Morning Light", None)]
    i = identity(tracks)
    c = release_cand(numbered([TrackRef("", "Foo", "Night Drive", 360), TrackRef("", "Foo", "Morning Light", 400)]))
    assert match_release(i, c) > 0.9 and len(match_tracks_in_release(i, c)) == 2
    long_mix = Candidate("sc", 3, "track", "u", "Foo - Night Drive (DJ mix)", "Foo", 3600)
    assert match_track(i, tracks[0], long_mix) == 0.0  # unknown reference length: over 15 min rejected


def test_dynamic_threshold_rises_for_alike_titles():
    alike = identity([TrackRef("A1", "Foo", "Song (Mix 1)", 300), TrackRef("A2", "Foo", "Song (Mix 2)", 300)])
    assert track_threshold(alike) > track_threshold(identity())
