from audioresearch.models import Quality, ReleaseResult, Status, TrackResult
from audioresearch.parsers.bandcamp import parse_item_id
from audioresearch.previews import classify, plan, youtube_id

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
BC = "https://artist.bandcamp.com/track/song-{}"
CLIP = "https://www.deejay.de/streamit/{}.mp3"


def track(pos, source=None, url=None, quality="full", conf=0.8, alts=()):
    t = TrackResult(pos, Status.FOUND if source else Status.NOT_FOUND, None, source, None, url,
                    Quality(quality) if source else None, conf if source else 0.0)
    t.alternatives = [{"source": s, "url": u, "quality": q, "confidence": c, "audio_path": ""} for s, u, q, c in alts]
    return t


def test_classify_links():
    assert youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert classify("discogs_youtube", YT) == ("youtube", "youtube")
    assert classify("bandcamp", BC.format(1)) == ("bandcamp", "bandcamp")
    assert classify("soundcloud_tracks", "https://soundcloud.com/a/b") == ("soundcloud", "soundcloud")
    assert classify("deejay_de", CLIP.format(1)) == ("deejay_de", "audio")
    assert classify("local_files", "/x/a.wav") == ("your files", "file")
    assert classify("hardwax", "https://hardwax.com/12345/") is None   # a page, not audio


def test_majority_source_takes_its_tracks_rest_from_next():
    """5 tracks: YouTube has 4, Bandcamp 3 -> YouTube plays A1-B1, Bandcamp only B2."""
    yt = lambda i: ("discogs_youtube", f"https://youtu.be/aaaaaaaaaa{i}", "full", 0.7)
    bc = lambda i: ("bandcamp", BC.format(i), "full", 0.9)
    r = ReleaseResult(1, [
        track("A1", *bc(1)[:2], alts=[yt(1)]),
        track("A2", *bc(2)[:2], alts=[yt(2)]),
        track("A3", *yt(3)[:2]),
        track("B1", *yt(4)[:2]),
        track("B2", *bc(5)[:2]),
    ])
    p = plan(r)
    assert [(f["family"], f["tracks"]) for f in p["families"]] == [("youtube", ["A1", "A2", "A3", "B1"]), ("bandcamp", ["B2"])]
    assert p["tracks"]["A1"]["embed_id"] == "aaaaaaaaaa1"
    assert p["tracks"]["B2"]["kind"] == "bandcamp"


def test_store_clip_plays_directly_and_unfound_is_none():
    r = ReleaseResult(1, [track("A1", "deejay_de", CLIP.format(1), "clip"), track("A2")])
    p = plan(r)
    assert p["tracks"]["A1"]["kind"] == "audio" and p["tracks"]["A1"]["url"] == CLIP.format(1)
    assert p["tracks"]["A2"] is None


def test_your_files_go_first():
    r = ReleaseResult(1, [track("A1", "local_files", "/a.wav", alts=[("discogs_youtube", YT, "full", 0.9)]),
                          track("A2", "discogs_youtube", YT), track("A3", "discogs_youtube", YT)])
    assert plan(r)["families"][0] == {"family": "your files", "tracks": ["A1"]}


def test_bandcamp_item_id():
    page = '<div data-tralbum="{&quot;id&quot;: 42, &quot;item_type&quot;: &quot;track&quot;}"></div>'
    assert parse_item_id(page) == ("track", 42)
    assert parse_item_id("<html></html>") is None


def test_find_at_store_buttons():
    page = "https://www.deejay.de/Artist_Title_AX084DC_Vinyl__1234"
    t = track("A1", "deejay_de", CLIP.format(1), "clip")
    t.level, t.page = 5, page
    t.alternatives = [{"source": "hardwax", "url": "x", "quality": "clip", "confidence": 0.5, "audio_path": "",
                       "level": 5, "page": "https://hardwax.com/1/"},
                      {"source": "bandcamp", "url": BC.format(1), "quality": "full", "confidence": 0.9, "audio_path": "",
                       "level": 2, "page": "https://a.bandcamp.com/album/x"}]
    stores = plan(ReleaseResult(1, [t, track("A2")]))["stores"]
    assert stores["A1"] == [{"source": "deejay_de", "page": page}, {"source": "hardwax", "page": "https://hardwax.com/1/"}]
    assert stores["A2"] == []
