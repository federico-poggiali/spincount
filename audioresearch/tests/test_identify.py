import json
from pathlib import Path

from audioresearch.identify import identify, to_url

FIX = Path(__file__).parent / "fixtures" / "discogs"


class FakeDiscogs:
    """Serves the saved Discogs JSON; a master resolves to its main release."""

    def __init__(self, **files):
        self.files = {i: json.loads((FIX / f).read_text()) for i, f in files.items()}
        self.calls = []

    def resolve(self, url):
        self.calls.append(url)
        kind, id_ = url.rstrip("/").split("/")[-2:]
        id_ = int(id_.split("-")[0])
        return self.files[id_]["main_release"] if kind == "master" else id_

    def release(self, rid):
        return self.files[rid]


def _client():
    c = FakeDiscogs()
    for name in ("release_simple", "release_cd", "release_heading"):
        d = json.loads((FIX / f"{name}.json").read_text())
        c.files[d["id"]] = d
    m = json.loads((FIX / "master_137924.json").read_text())
    c.files[137924] = m
    c.files[m["main_release"]] = json.loads((FIX / "release_heading.json").read_text())
    return c


def test_simple_release_identity():
    i = identify(9261843, _client())
    assert (i.artist, i.label, i.catno, i.year) == ("Truncate", "Truncate", "TRUNCATE14", 2016)
    assert [t.position for t in i.tracks] == ["A1", "A2", "B"]
    assert all(t.duration is None for t in i.tracks)
    assert len(i.videos) == 9 and i.tracks[0].artist == "Truncate"


def test_heading_release_skips_headings_and_parses_durations():
    d = json.loads((FIX / "release_heading.json").read_text())
    i = identify(d["id"], _client())
    assert i.catno == "RS 98135 X" and i.label == "R & S Records"
    assert [(t.position, t.duration) for t in i.tracks] == [("A", 420), ("B", 333)]


def test_cd_release_has_no_videos():
    d = json.loads((FIX / "release_cd.json").read_text())
    i = identify(f"https://www.discogs.com/release/{d['id']}-x", _client())
    assert i.videos == [] and i.catno == "LV2311" and len(i.tracks) >= 6


def test_master_resolves_to_main_release():
    c = _client()
    i = identify("https://www.discogs.com/master/137924", c)
    main = json.loads((FIX / "release_heading.json").read_text())
    assert i.discogs_release_id == json.loads((FIX / "master_137924.json").read_text())["main_release"]
    assert i.title == main["title"].strip()


def test_to_url():
    assert to_url(123) == "https://www.discogs.com/release/123"
    assert to_url("https://x/master/1") == "https://x/master/1"
