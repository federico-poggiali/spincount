import shutil
import subprocess

import pytest

from audioresearch import fingerprint, verify
from audioresearch.models import Candidate, FetchedAudio, Quality, TrackRef
from audioresearch.tests.audio_utils import SR, make_wav, melody, write_wav

needs_fpcalc = pytest.mark.skipif(not fingerprint.available(), reason="fpcalc not installed")
TRACK = TrackRef("A1", "Foo", "Night Drive", 360)


def fa(dur, q=Quality.FULL, path="x.fake"):
    return FetchedAudio(path, "yt", "u", q, dur)


def check(track=TRACK, f=None, cand=None):
    return verify.verify(track, f, cand, with_fingerprint=False)


def test_duration_tolerance_for_full():
    assert check(f=fa(363)).ok and check(f=fa(363)).duration_ok is True
    v = check(f=fa(375))
    assert not v.ok and "375" in v.reasons[0]


def test_preview_and_clip_skip_the_duration_check():
    assert check(f=fa(90, Quality.PREVIEW)).ok and check(f=fa(30, Quality.CLIP)).duration_ok is None


def test_unknown_discogs_duration_rejects_over_15_minutes():
    t = TrackRef("A1", "Foo", "Night Drive", None)
    assert check(t, fa(14 * 60)).ok
    assert not check(t, fa(16 * 60)).ok


def test_far_longer_audio_is_a_mix_or_medley():
    assert not check(f=fa(900, Quality.PREVIEW)).ok


def test_medley_titles_are_rejected_unless_the_track_is_one():
    c = Candidate("sc", 3, "track", "u", "Foo - EP preview (all tracks)", "Foo", 360)
    assert "medley" in check(f=fa(360), cand=c).reasons[0]
    assert not check(f=fa(360), cand=Candidate("sc", 3, "track", "u", "Foo - Night Drive [DJ Mix]", "Foo", 360)).ok
    assert check(f=fa(360), cand=Candidate("sc", 3, "track", "u", "Foo - Night Drive (Radio Mix)", "Foo", 360)).ok
    assert check(TrackRef("A1", "Foo", "Night Drive (DJ Mix)", 360), fa(360),
                 Candidate("sc", 3, "track", "u", "Night Drive (DJ Mix)", "Foo", 360)).ok


def test_unknown_real_duration_is_a_warning_not_a_rejection():
    v = check(f=fa(None))
    assert v.ok and "unknown" in v.warnings[0]


def test_missing_fpcalc_falls_back_to_duration_only(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(fingerprint, "_warned", False)
    f = fa(360, path=make_wav(tmp_path / "a.wav", 5))
    v = verify.verify(TRACK, f)
    assert v.ok and any("duration only" in w for w in v.warnings)
    assert verify.cross_check(f, fa(360, path=f.path)) is None


@needs_fpcalc
def test_trimmed_clip_aligns_and_different_music_does_not(tmp_path):
    full = melody(1, 60)
    p_full = write_wav(tmp_path / "full.wav", full)
    p_clip = write_wav(tmp_path / "clip.wav", full[20 * SR: 40 * SR])      # 20 s taken from the middle
    p_other = write_wav(tmp_path / "other.wav", melody(2, 60))
    fp_full, fp_clip, fp_other = (fingerprint.compute(p) for p in (p_full, p_clip, p_other))
    hit = fingerprint.align(fp_clip, fp_full)
    assert hit.ratio > 0.9 and hit.offset == pytest.approx(20, abs=1.5)
    assert fingerprint.align(fp_clip, fp_other).ratio < fingerprint.DISAGREE
    assert fingerprint.compare(fp_clip, fp_full) is True and fingerprint.compare(fp_clip, fp_other) is False


@needs_fpcalc
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_other_encoding_of_the_same_audio_still_aligns(tmp_path):
    p = make_wav(tmp_path / "a.wav", 40, seed=5)
    mp3 = tmp_path / "a.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-b:a", "96k", str(mp3)], check=True)
    assert fingerprint.compare(fingerprint.compute(p), fingerprint.compute(mp3)) is True


@needs_fpcalc
def test_cross_check_between_sources(tmp_path):
    a = FetchedAudio(make_wav(tmp_path / "a.wav", 30, 7), "bandcamp", "u1", Quality.FULL, 30)
    b = FetchedAudio(write_wav(tmp_path / "b.wav", melody(7, 30)[5 * SR: 25 * SR]), "beatport", "u2", Quality.PREVIEW, 20)
    c = FetchedAudio(make_wav(tmp_path / "c.wav", 30, 8), "soundcloud", "u3", Quality.FULL, 30)
    assert verify.cross_check(a, b) is True and verify.cross_check(a, c) is False


def test_unreadable_file_gives_no_fingerprint(tmp_path):
    p = tmp_path / "junk.mp3"
    p.write_bytes(b"not audio")
    assert fingerprint.compute(p) is None
