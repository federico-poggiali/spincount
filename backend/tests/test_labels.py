import base64
import io

import pytest
from PIL import Image

from app.db import connect, notes, queries, records, tags, tracks
from app.labels import data as label_data
from app.labels import render as label_render
from app.labels.data import LabelData, LabelTrack


@pytest.fixture
def conn(db_path):
    c = connect(db_path)
    yield c
    c.close()


@pytest.fixture
def record_id(conn):
    rid = records.create(conn, artist="Jeff Mills (2)", title="The Bells", label="Purpose Maker",
                         catno="PM-01", year=1994, discogs_release_id=4242, styles=["Techno", "Minimal"])
    t1 = tracks.create(conn, rid, position="A", title="The Bells", bpm=135.04, key="F minor",
                       camelot_key="4A")
    tracks.create(conn, rid, position="B", title="Other", bpm=None, key="A minor")
    tags.create_tag(conn, 1, "peak")
    tags.add(conn, "track", t1, "peak")
    notes.create(conn, body="Relentless and hypnotic. Great after midnight.", record_id=rid)
    notes.create(conn, body="Drop at two minutes", track_id=t1)
    return rid


def pixels(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png))


def sample(tracks_: list[LabelTrack] | None = None, **kw) -> LabelData:
    base = dict(artist="Jeff Mills", title="The Bells", label="Axis", catno="AX-1", year="1994",
                styles=["Techno"], note="A short note.", qr_url="https://www.discogs.com/release/1",
                tracks=tracks_ or [LabelTrack(position="A1", bpm="130", key="8A")])
    return LabelData(**{**base, **kw})


def warnings_of(data: LabelData) -> list[str]:
    return label_render.render(data)[1]


# ---- builder ----

def test_build_merges_record_tracks_tags_and_notes(conn, record_id):
    data = label_data.build(queries.record_detail(conn, record_id))
    assert data.artist == "Jeff Mills"  # the Discogs "(2)" is not for print
    assert (data.label, data.catno, data.year) == ("Purpose Maker", "PM-01", "1994")
    assert data.styles == ["Techno", "Minimal"]
    assert data.note == "Relentless and hypnotic."  # prose note, first sentence only
    assert data.qr_url == "https://www.discogs.com/release/4242"
    assert data.country is None  # not stored
    first, second = data.tracks
    assert (first.position, first.bpm, first.key, first.tags) == ("A", "135", "4A", ["peak"])
    assert first.note == "Drop at two minutes"
    assert (second.bpm, second.key, second.note) == (None, "A minor", None)  # falls back to the musical key


def test_clean_artist_only_drops_discogs_numbers():
    assert label_data.clean_artist("Aphex Twin") == "Aphex Twin"
    assert label_data.clean_artist("Jeff Mills (2) & DJ Rush (3)") == "Jeff Mills & DJ Rush"
    assert label_data.clean_artist("Blink (182)") == "Blink"
    assert label_data.clean_artist("(Not) A Number") == "(Not) A Number"


def test_a_record_without_a_discogs_id_has_no_qr(conn):
    rid = records.create(conn, artist="A", title="B")
    assert label_data.build(queries.record_detail(conn, rid)).qr_url is None


# ---- renderer ----

def test_labels_are_62_by_40_mm_one_bit_images():
    images, warnings = label_render.render(sample())
    assert [i.name for i in images] == ["main", "tracks"] and warnings == []
    for image in images:
        img = pixels(image.png)
        assert img.size == (696, 472) and img.mode == "1"  # 62 x 40 mm at 300 dpi, black or white only
        assert round(img.info["dpi"][0]) == 300
        assert img.histogram()[0] > 0  # something was drawn (black pixels)


def test_hiding_a_field_changes_the_label():
    full = label_render.render(sample())[0][0].png
    for field in ("label", "catno", "year", "styles", "note", "qr"):
        assert label_render.render(sample(hidden=[field]))[0][0].png != full, field


def test_editing_a_value_changes_the_label():
    assert (label_render.render(sample(country="UK"))[0][0].png
            != label_render.render(sample())[0][0].png)


def test_main_label_without_a_qr_url_just_has_no_qr():
    assert label_render.render(sample(qr_url=None))[0][0].png == label_render.render(sample(hidden=["qr"]))[0][0].png


def test_long_text_is_cut_and_reported():
    assert warnings_of(sample()) == []
    assert any("title" in w for w in warnings_of(sample(title="Word " * 60)))
    assert any("artist" in w for w in warnings_of(sample(artist="Artist " * 40)))


def test_a_note_that_does_not_fit_is_reported():
    assert any("note" in w for w in warnings_of(sample(note="Very long note. " * 40)))


def test_tracks_are_left_off_when_skipped_or_absent():
    skipped = [LabelTrack(position="A1", skip=True)]
    assert [i.kind for i in label_render.render(sample(skipped))[0]] == ["main"]
    assert [i.kind for i in label_render.render(LabelData(artist="A", title="B", tracks=[]))[0]] == ["main"]


def test_many_tracks_need_several_labels():
    many = [LabelTrack(position=f"{side}{n}", bpm="128", key="8A", tags=["a", "b"], note="note")
            for side in "AB" for n in range(1, 6)]
    images, warnings = label_render.render(sample(many))
    assert [i.name for i in images] == ["main", "tracks-1", "tracks-2"]
    assert warnings == ["Tracks label: The tracks need 2 labels"]


def test_sides_group_tracks_and_sides_are_read_from_positions():
    assert [label_render.side_of(p) for p in ("A1", "B", "AA2", "1-3", "2.1", "")] == [
        "A", "B", "AA", "1", "2", "·"]
    pages = label_render._paginate([LabelTrack(position=p) for p in ("A1", "A2", "B1")])
    assert [[(s, len(t)) for s, t in page] for page in pages] == [[("A", 2), ("B", 1)]]


def test_hidden_track_fields_are_not_drawn():
    base = LabelTrack(position="A1", bpm="130", key="8A", tags=["x"], note="n")
    full = label_render.render(sample([base]))[0][1].png
    for field in ("bpm", "key", "tags", "note"):
        hidden = base.model_copy(update={"hidden": [field]})
        assert label_render.render(sample([hidden]))[0][1].png != full, field


# ---- API ----

def test_get_label_defaults_come_from_the_database(client, record_id):
    body = client.get(f"/api/records/{record_id}/label").json()
    assert body["artist"] == "Jeff Mills" and body["tracks"][0]["key"] == "4A"


def test_label_is_only_for_records_in_the_library(client):
    assert client.get("/api/records/999/label").status_code == 404
    assert client.post("/api/records/999/label/render", json=sample().model_dump()).status_code == 404


def test_wishlist_records_get_no_label(client, conn):
    rid = records.create(conn, artist="A", title="Wanted", status="wantlist")
    assert client.get(f"/api/records/{rid}/label").status_code == 409
    assert client.post(f"/api/records/{rid}/label/render", json=sample().model_dump()).status_code == 409


def test_render_returns_pngs_and_changes_nothing(client, record_id, conn):
    edited = client.get(f"/api/records/{record_id}/label").json()
    edited["artist"] = "Someone Else"
    edited["country"] = "UK"
    response = client.post(f"/api/records/{record_id}/label/render", json=edited)
    assert response.status_code == 200
    body = response.json()
    assert [i["name"] for i in body["images"]] == ["main", "tracks"] and body["warnings"] == []
    for image in body["images"]:
        assert (image["width"], image["height"]) == (696, 472)
        assert pixels(base64.b64decode(image["png_base64"])).size == (696, 472)
    assert records.get(conn, record_id)["artist"] == "Jeff Mills (2)"  # edits are for this print only


def test_render_rejects_malformed_edits(client, record_id):
    assert client.post(f"/api/records/{record_id}/label/render", json={"artist": "A"}).status_code == 422
    bad = sample().model_dump() | {"hidden": ["nonsense"]}
    assert client.post(f"/api/records/{record_id}/label/render", json=bad).status_code == 422


# ---- labels for records you do not own yet ----

def test_loose_label_renders_without_a_record(client):
    body = sample().model_dump()
    out = client.post("/api/labels/render", json=body)
    assert out.status_code == 200 and out.json()["images"]


def test_label_from_discogs_link_stores_nothing(client):
    out = client.post("/api/labels/from-discogs", json={"discogs_url": "https://www.discogs.com/release/9261843"})
    assert out.status_code == 200
    data = out.json()
    assert data["title"] and data["tracks"] and data["qr_url"].endswith("/9261843")
    assert client.get("/api/records").json()["total"] == 0


def test_label_from_bad_link_is_a_clear_error(client):
    out = client.post("/api/labels/from-discogs", json={"discogs_url": "https://example.com/x"})
    assert out.status_code == 400


def test_the_doodle_is_the_same_on_every_render_and_differs_per_record():
    first = label_render.render(sample())[0][0].png
    assert label_render.render(sample())[0][0].png == first
    assert label_render.render(sample(title="Something else"))[0][0].png != first


def test_names_the_pixel_font_cannot_spell_fall_back_to_the_plain_font():
    assert label_render._header_font("JEFF MILLS") == label_render.PIXEL
    assert label_render._header_font("RYŌJI IKEDA") == label_render.SANS


def test_a_label_holds_two_sides_so_a_double_lp_needs_three_labels():
    tracks = [LabelTrack(position=f"{side}{n}", bpm="128") for side in "ABCD" for n in (1, 2)]
    assert [i.name for i in label_render.render(sample(tracks))[0]] == ["main", "tracks-1", "tracks-2"]
    pages = label_render._paginate(tracks)
    assert [[s for s, _ in page] for page in pages] == [["A", "B"], ["C", "D"]]


def test_tracks_labels_are_filled_to_the_bottom_with_sides_in_proportion():
    tracks = [LabelTrack(position=p, bpm="128") for p in ("A1", "A2", "A3", "B1")]
    img = Image.open(io.BytesIO(label_render.render(sample(tracks))[0][1].png)).convert("L")
    column = [img.getpixel((label_render.MARGIN + 8, y)) for y in range(label_render.H)]
    blocks, prev = [], 255
    for y, v in enumerate(column):
        if v == 0 and prev != 0:
            blocks.append([y, y])
        if v == 0:
            blocks[-1][1] = y
        prev = v
    heights = [b - a for a, b in blocks]
    assert blocks[-1][1] >= label_render.H - label_render.MARGIN - 8
    assert 2.5 < heights[0] / heights[1] < 3.5


def test_track_artist_is_kept_only_when_it_differs_from_the_record():
    from app.labels.data import build
    track = lambda artist: {"position": "A1", "artist": artist, "bpm": None, "camelot_key": None,  # noqa: E731
                            "key": None, "tags": [], "notes": []}
    record = {"discogs_release_id": None, "artist": "Various", "label": None, "catno": None, "title": "T",
              "year": None, "styles": [], "notes": [], "tracks": [track("Jeff Mills (2)"), track("Various")]}
    assert [t.artist for t in build(record).tracks] == ["Jeff Mills", None]


def test_tracks_label_prints_the_artist_line():
    plain = [LabelTrack(position="A1", bpm="130")]
    with_artist = [LabelTrack(position="A1", bpm="130", artist="Jeff Mills")]
    assert label_render._row_height(with_artist[0]) > label_render._row_height(plain[0])
    assert label_render.render_tracks(sample(with_artist), lambda m: None)


def test_a_doodle_goes_on_the_rim_only_where_there_is_room():
    from app.labels import doodles
    W, H, M = label_render.W, label_render.H, label_render.MARGIN
    area = (M, M, W - M, H - M)
    for seed in "abcdefgh":
        img = Image.new("L", (W, H), 255)
        img.paste(0, (0, 0, W, H // 2))  # the top half is "text"
        assert doodles.place(img, doodles.rng_for(seed), area) in doodles.DOODLES
        x0, y0, x1, y1 = _ink_below(img, H // 2 + 1)
        assert y0 > H // 2 + doodles.CLEARANCE - 2  # clear of the text
        assert x0 == M or x1 == W - M or y1 == H - M  # touching the rim, not floating in the middle
    full = Image.new("L", (W, H), 0)
    assert doodles.place(full, doodles.rng_for("a"), area) is None  # no room, no doodle


def _ink_below(img: Image.Image, top: int) -> tuple[int, int, int, int]:
    from PIL import ImageOps
    x0, y0, x1, y1 = ImageOps.invert(img.crop((0, top, img.width, img.height))).getbbox()
    return x0, y0 + top, x1, y1 + top


# ---- text sizes ----

def black(png: bytes) -> int:
    return pixels(png).histogram()[0]


def test_a_short_note_grows_to_fill_the_empty_space():
    short = label_render.render_main(sample(note="Peak time."), lambda _: None)
    long_ = label_render.render_main(sample(note="Peak time. " * 12), lambda _: None)
    lone = label_render.render_main(sample(note=None), lambda _: None)
    # the two words alone take more ink than the info at the usual note size would
    assert black(short) - black(lone) > 3 * (black(label_render.render_main(
        sample(note="Peak time.", sizes={"note": 0.6}), lambda _: None)) - black(lone)) / 2
    assert not warnings_of(sample(note="Peak time.")) and black(long_) > black(lone)


def test_size_sliders_make_text_bigger_or_smaller():
    def ink(**sizes) -> int:  # short texts, so none has to shrink to fit
        return black(label_render.render_main(sample(artist="Moby", title="Go", note=None, sizes=sizes),
                                              lambda _: None))
    usual = ink()
    for field in ("artist", "title", "details", "info"):
        big, small = ink(**{field: 1.4}), ink(**{field: 0.7})
        assert small < usual < big, field


def test_bigger_track_text_needs_more_labels():
    many = [LabelTrack(position=f"A{i}", bpm="128", key="8A", note="Long build") for i in range(1, 6)]
    assert len(label_render.render_tracks(sample(many), lambda _: None)) == 1
    assert len(label_render.render_tracks(sample(many, sizes={"tracks": 1.6}), lambda _: None)) > 1


def test_sizes_are_bounded():
    with pytest.raises(ValueError):
        sample(sizes={"note": 3})


# ---- designs ----

DESIGNS = ["glitchy", "corrupted", "penguin", "republic", "factory"]


@pytest.mark.parametrize("design", DESIGNS)
def test_every_design_draws_both_labels_at_print_size(design):
    data = sample([LabelTrack(position=p, bpm="128", key="8A", note="Build") for p in ("A1", "A2", "B1")],
                  design=design, note="Relentless and hypnotic, best after midnight.")
    images, warnings = label_render.render(data)
    assert [i.kind for i in images] == ["main", "tracks"]
    for image in images:
        img = pixels(image.png)
        assert img.size == (696, 472) and img.mode == "1"
    assert warnings == []


@pytest.mark.parametrize("design", DESIGNS)
def test_every_design_honours_hidden_fields_and_sizes(design):
    base = black(label_render.render(sample(design=design))[0][0].png)
    hidden = sample(design=design, hidden=["label", "catno", "year", "country", "styles", "note", "qr"])
    assert black(label_render.render(hidden)[0][0].png) != base  # (penguin swaps its white QR panel for the oval)
    bigger = sample(design=design, sizes={"title": 1.5}, title="Go")
    assert black(label_render.render(bigger)[0][0].png) != black(label_render.render(sample(design=design, title="Go"))[0][0].png)


@pytest.mark.parametrize("design", DESIGNS)
def test_every_design_survives_names_its_font_cannot_spell(design):
    images, _ = label_render.render(sample(design=design, artist="坂本龍一", title="音楽図鑑", label="School"))
    assert pixels(images[0].png).histogram()[0] > 0


def test_only_the_glitchy_designs_carry_doodles(monkeypatch):
    placed = []
    monkeypatch.setattr("app.labels.doodles.place", lambda *a, **k: placed.append(1))
    for design in DESIGNS:
        placed.clear()
        label_render.render(sample(design=design))
        assert bool(placed) == (design in ("glitchy", "corrupted")), design


def test_a_very_long_note_is_cut_with_a_warning_in_every_design():
    for design in DESIGNS:
        assert any("note" in w for w in warnings_of(sample(design=design, note="Peak time. " * 60))), design


# ---- presets ----

def test_presets_save_replace_by_name_and_delete(client):
    look = {"design": "penguin", "sizes": {"title": 1.2}, "hidden": ["country"], "track_hidden": ["tags"]}
    items = client.post("/api/label-presets", json={"name": "Shelf", "look": look}).json()["items"]
    assert [(p["name"], p["look"]["design"], p["look"]["sizes"]["title"]) for p in items] == [("Shelf", "penguin", 1.2)]
    items = client.post("/api/label-presets", json={"name": "shelf", "look": {**look, "design": "factory"}}).json()["items"]
    assert len(items) == 1 and items[0]["look"]["design"] == "factory"  # same name, any case: replaced
    client.post("/api/label-presets", json={"name": "Gig", "look": {}})
    assert [p["name"] for p in client.get("/api/label-presets").json()["items"]] == ["Gig", "shelf"]
    assert client.delete(f"/api/label-presets/{items[0]['id']}").json()["items"][0]["name"] == "Gig"
    assert client.delete("/api/label-presets/999").status_code == 404


def test_presets_reject_unknown_designs_and_blank_names(client):
    assert client.post("/api/label-presets", json={"name": "x", "look": {"design": "comic sans"}}).status_code == 422
    assert client.post("/api/label-presets", json={"name": "   ", "look": {}}).status_code == 422
