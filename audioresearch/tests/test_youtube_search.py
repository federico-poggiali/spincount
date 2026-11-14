"""YouTube search for "Add to YT playlist": the matcher keeps the right video and leaves wrong ones out."""
from audioresearch.models import ReleaseIdentity, TrackRef
from audioresearch.youtube_search import find_track

TRACK = TrackRef("A1", "Moodymann", "Shades Of Jae", 420)
IDENTITY = ReleaseIdentity(1, "Moodymann", "Silentintroduction", None, None, None,
                           [TRACK, TrackRef("A2", "Moodymann", "Tribute", 300)])

# Real rows from yt-dlp's flat search for "Moodymann Shades Of Jae" (Topic channel second, a cover third).
ROWS = [
    {"id": "0YCgkz_yK1w", "title": "Moodymann - Shades of Jae", "duration": 417.0, "channel": "vinylandry"},
    {"id": "fNXyJooVVk4", "title": "Shades of Jae", "duration": 416, "channel": "moodymann - Topic"},
    {"id": "UxD0f4XhTMM", "title": "Moodymann ''shade of jae'' by SHAN S.", "duration": 370, "channel": "Shan S."},
]


def test_best_hit_is_kept_with_its_details():
    queries = []
    hit = find_track(IDENTITY, TRACK, lambda q: queries.append(q) or ROWS)
    assert queries == ["Moodymann Shades Of Jae"]
    assert hit["video_id"] in {"0YCgkz_yK1w", "fNXyJooVVk4"}
    assert hit["confidence"] >= 0.7 and isinstance(hit["duration"], int)


def test_topic_channel_counts_as_the_artist():
    hit = find_track(IDENTITY, TRACK, lambda q: ROWS[1:2])
    assert hit["video_id"] == "fNXyJooVVk4" and hit["channel"] == "moodymann - Topic"


def test_wrong_songs_are_left_out():
    other = [{"id": "x" * 11, "title": "Moodymann - Tribute", "duration": 300, "channel": "x"}]
    assert find_track(IDENTITY, TRACK, lambda q: ROWS[2:] + other) is None
    assert find_track(IDENTITY, TRACK, lambda q: []) is None
