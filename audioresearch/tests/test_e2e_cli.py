import json
from pathlib import Path

import jsonschema

from audioresearch import cli, config, pipeline
from audioresearch.adapters import Registry
from audioresearch.adapters.fake import FakeAdapter
from audioresearch.models import Candidate, Quality, ReleaseIdentity, TrackRef

SCHEMA = json.loads((Path(__file__).parent.parent / "output_schema.json").read_text())


def ident():
    return ReleaseIdentity(88, "Foo", "EP", "L", "C1", 2020, [TrackRef("A1", "Foo", "Night Drive", 360), TrackRef("B1", "Foo", "Deep Water", 380)])


def setup(monkeypatch, tmp_path):
    reg = Registry([FakeAdapter("yt", 1, [Candidate("yt", 1, "track", "https://yt/1", "Night Drive", "Foo", 360, position="A1")])], disabled=set())
    monkeypatch.setattr(pipeline, "default_registry", lambda: reg)
    monkeypatch.setattr(pipeline, "identify", lambda *a, **k: ident())
    monkeypatch.setattr(config, "AUDIORESEARCH_DB", tmp_path / "cli.db")
    monkeypatch.setattr(config, "AUDIO_CACHE_DIR", tmp_path / "audio")


def test_fake_end_to_end_prints_a_table_and_valid_json(monkeypatch, tmp_path, capsys):
    setup(monkeypatch, tmp_path)
    out = tmp_path / "out.json"
    assert cli.main(["research", "88", "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "pos" in text and "A1" in text and "found" in text and "not_found" in text and "1 found, 0 review, 1 not found" in text
    data = json.loads(out.read_text())
    jsonschema.validate(data, SCHEMA)
    assert data["tracks"][0]["source"] == "yt" and data["tracks"][1]["status"] == "not_found"


def test_bare_url_means_research_and_report_shows_provenance(monkeypatch, tmp_path, capsys):
    setup(monkeypatch, tmp_path)
    assert cli.main(["https://www.discogs.com/release/88-x"]) == 0
    capsys.readouterr()
    assert cli.main(["report", "88"]) == 0
    text = capsys.readouterr().out
    assert "Provenance" in text and "accepted" in text and "https://yt/1" in text


def test_review_reject_and_accept(monkeypatch, tmp_path, capsys):
    from audioresearch.store import Store
    from audioresearch.models import Status
    setup(monkeypatch, tmp_path)
    cli.main(["research", "88"])
    store = Store(tmp_path / "cli.db")
    res, levels, _ = store.get_result(88)
    res.track("A1").status = Status.REVIEW
    store.save_result(res, levels)
    answers = iter(["a", "s"])  # accept A1, skip B1
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli.main(["review", "88"]) == 0
    assert store.get_result(88)[0].track("A1").status == Status.FOUND
    assert store.overrides(88)["A1"]["action"] == "accept"
