-- What audioresearch found for each track (one row per track; a new run replaces it).
CREATE TABLE track_audio (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('found', 'review', 'not_found')),
    source TEXT,
    level INTEGER,
    quality TEXT CHECK (quality IS NULL OR quality IN ('full', 'preview', 'clip')),
    confidence REAL,
    reason TEXT,
    url TEXT,
    page TEXT,
    audio_path TEXT,
    readings TEXT CHECK (readings IS NULL OR json_valid(readings)),
    alternatives TEXT CHECK (alternatives IS NULL OR json_valid(alternatives)),
    found_at TEXT NOT NULL
);
