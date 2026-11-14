"""The audio sources the search can use, grouped the way Settings shows them.

Your own files are not listed: they always come first and cannot be switched off."""

GROUPS = [
    ("youtube", "YouTube", ("discogs_youtube", "youtube_music")),
    ("itunes", "iTunes", ("itunes",)),
    ("bandcamp", "Bandcamp", ("bandcamp", "bandcamp_tracks")),
    ("soundcloud", "SoundCloud", ("soundcloud_tracks", "soundcloud_sets")),
    ("beatport", "Beatport", ("beatport_tracks", "beatport_releases")),
]
LABELS = {
    "discogs_youtube": "Videos linked on Discogs", "youtube_music": "YouTube Music",
    "itunes": "iTunes previews", "bandcamp": "Bandcamp releases", "bandcamp_tracks": "Bandcamp tracks",
    "soundcloud_tracks": "SoundCloud tracks", "soundcloud_sets": "SoundCloud sets",
    "beatport_tracks": "Beatport tracks", "beatport_releases": "Beatport releases",
    "deejay_de": "deejay.de", "hardwax": "Hard Wax", "redeye": "Redeye", "decks_de": "Decks",
    "clone": "Clone", "soundmetaphors": "Sound Metaphors", "one_eye_witness": "One Eye Witness",
    "smallblackdots": "Small Black Dots", "runas": "Runas", "orbitwax": "Orbit Wax",
}


def groups() -> list[dict]:
    """Only the sources this install can use, in the order the search asks them."""
    from audioresearch.adapters import default_registry

    online = [a for a in default_registry().all() if a.level > 0]
    names = {a.name for a in online}
    source = lambda name: {"name": name, "label": LABELS.get(name, name)}  # noqa: E731
    out = [{"key": key, "label": label, "sources": [source(n) for n in members if n in names]}
           for key, label, members in GROUPS]
    grouped = {n for _, _, members in GROUPS for n in members}
    out.append({"key": "shops", "label": "Record shops",
                "sources": [source(a.name) for a in online if a.name not in grouped]})
    return [g for g in out if g["sources"]]
