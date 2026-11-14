"""Label presets: a named look (design, sizes, hidden fields). Saving under an existing name replaces it."""
import json
import sqlite3
from datetime import UTC, datetime


def list_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, name, look FROM label_presets ORDER BY name COLLATE NOCASE")
    return [{"id": r["id"], "name": r["name"], "look": json.loads(r["look"])} for r in rows]


def save(conn: sqlite3.Connection, name: str, look: dict) -> int:
    name = " ".join(name.split())
    if not name:
        raise ValueError("preset name is empty")
    now = datetime.now(UTC).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO label_presets(name, look, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET name = excluded.name, look = excluded.look, "
        "updated_at = excluded.updated_at",
        (name, json.dumps(look), now))
    conn.commit()
    return conn.execute("SELECT id FROM label_presets WHERE name = ?", (name,)).fetchone()["id"]


def delete(conn: sqlite3.Connection, preset_id: int) -> None:
    if conn.execute("DELETE FROM label_presets WHERE id = ?", (preset_id,)).rowcount == 0:
        raise LookupError("preset not found")
    conn.commit()
