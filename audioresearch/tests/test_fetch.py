from pathlib import Path
from types import SimpleNamespace

import pytest

from audioresearch import fetch
from audioresearch.adapters.base import AdapterError
from audioresearch.models import FetchedAudio, Quality, ReleaseIdentity
from audioresearch.tests.audio_utils import make_wav


def test_dest_path_layout(tmp_path):
    i = ReleaseIdentity(12345, "A", "T", None, None, None, [])
    assert fetch.dest_for(tmp_path, i, "A1", "bandcamp") == tmp_path / "12345" / "A1.bandcamp"
    assert fetch.dest_for(tmp_path, i, "1/2", "x").name == "1_2.x"


def test_probe_real_duration(tmp_path):
    p = make_wav(tmp_path / "a.wav", 3.0)
    assert fetch.probe_duration(p) == pytest.approx(3.0, abs=0.1)
    assert fetch.probe_duration(tmp_path / "missing.wav") is None


@pytest.mark.parametrize("real,discogs,hint,expected", [
    (30, 360, Quality.FULL, Quality.CLIP),            # under 60 s is a clip whatever the site said
    (120, 360, Quality.FULL, Quality.PREVIEW),        # clearly shorter than the Discogs duration
    (355, 360, Quality.PREVIEW, Quality.FULL),        # the site said preview, the file is the whole track
    (300, None, Quality.PREVIEW, Quality.PREVIEW),    # no reference length: trust the hint
    (300, None, Quality.FULL, Quality.FULL),
    (150, None, Quality.CLIP, Quality.PREVIEW),       # a 150 s store clip with no reference length
    (None, 360, Quality.CLIP, Quality.CLIP),          # could not measure: keep the hint
])
def test_quality_ladder(real, discogs, hint, expected):
    assert fetch.classify(real, discogs, hint) == expected


def test_finalize_measures_the_file(tmp_path):
    p = make_wav(tmp_path / "a.wav", 5.0)
    f = fetch.finalize(FetchedAudio(p, "x", "u", Quality.FULL, 999.0), 360)
    assert f.quality == Quality.CLIP and f.duration == pytest.approx(5.0, abs=0.1)
    f = fetch.finalize(FetchedAudio(tmp_path / "unreadable.fake", "x", "u", Quality.FULL, 355.0), 360)
    assert f.quality == Quality.FULL and f.duration == 355.0


class FakeHttp:
    def __init__(self, body=b"abc" * 100, ctype="audio/mpeg"):
        self.body, self.ctype, self.urls = body, ctype, []

    def get(self, url, **kw):
        self.urls.append(url)
        return SimpleNamespace(headers={"Content-Type": self.ctype}, iter_content=lambda n: iter([self.body]))


def test_http_download_lands_in_the_right_place(tmp_path):
    http = FakeHttp()
    p = fetch.http_download("https://x/preview?id=1", tmp_path / "77" / "A1.itunes", site="itunes", adapter="itunes", http=http)
    assert p == tmp_path / "77" / "A1.itunes.mp3" and p.read_bytes() == b"abc" * 100
    p = fetch.http_download("https://x/p.m4a", tmp_path / "77" / "A2.itunes", site="itunes", adapter="itunes", http=http)
    assert p.name == "A2.itunes.m4a"
    with pytest.raises(AdapterError):
        fetch.http_download("https://x/p.mp3", tmp_path / "B1.itunes", site="i", adapter="i", http=FakeHttp(body=b""))


def test_ytdlp_download_with_yt_dlp_mocked(tmp_path, monkeypatch):
    import yt_dlp

    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            self.out = tmp_path / "77" / "A1.yt.webm"
            self.out.parent.mkdir(parents=True, exist_ok=True)
            self.out.write_bytes(b"x")
            return {"id": "1"}

        def prepare_filename(self, info):
            return str(self.out)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    p = fetch.ytdlp_download("https://youtu.be/1", tmp_path / "77" / "A1.yt")
    assert p.name == "A1.yt.webm" and seen["outtmpl"].endswith("A1.yt.%(ext)s") and seen["format"].startswith("bestaudio")
