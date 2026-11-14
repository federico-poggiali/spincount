"""App-wide settings the backend acts on. Display preferences stay in the browser."""
import sqlite3

DEFAULTS: dict[str, bool | int | list] = {
    "auto_collection": True,  # adding an owned record also adds it to the Discogs collection
    "auto_wantlist": False,   # adding a wishlist record also adds it to the Discogs wantlist
    "import_every_min": 0,    # Discogs -> Spin Count on a schedule; 0 = only when asked
    "push_every_min": 0,      # Spin Count -> Discogs on a schedule; 0 = only when asked
    "youtube_playlist": False,  # "Add to YT playlist": every track is looked up on YouTube, for playlists
    "audio_search_lengthy": False,  # the audio search asks every source for every track (slower)
    "audio_sources_off": [],  # audio sources the search skips, by name (see app.audio.sources)
}
# When a scheduled sync last started: kept with the settings, never shown as one.
STATE = ("last_import_at", "last_push_at")


def _decode(key: str, value: str) -> bool | int | list:
    if isinstance(DEFAULTS[key], list):
        return [v for v in value.split(",") if v]
    return value == "on" if isinstance(DEFAULTS[key], bool) else int(value)


def _encode(value: bool | int | list) -> str:
    if isinstance(value, list):
        return ",".join(sorted(set(value)))
    return ("on" if value else "off") if isinstance(value, bool) else str(int(value))


def get_all(conn: sqlite3.Connection) -> dict[str, bool | int | list]:
    stored = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM app_settings")}
    return {k: _decode(k, stored[k]) if k in stored else default for k, default in DEFAULTS.items()}


def get(conn: sqlite3.Connection, key: str) -> bool | int | list:
    return get_all(conn)[key]


def _put(conn: sqlite3.Connection, pairs: list[tuple[str, str]]) -> None:
    conn.executemany(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", pairs)
    conn.commit()


def update(conn: sqlite3.Connection, values: dict[str, bool | int | list]) -> dict[str, bool | int | list]:
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown settings: {sorted(unknown)}")
    _put(conn, [(k, _encode(v)) for k, v in values.items()])
    return get_all(conn)


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    if key not in STATE:
        raise ValueError(f"unknown state: {key}")
    _put(conn, [(key, value)])
