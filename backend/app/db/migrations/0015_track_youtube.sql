-- Each track's YouTube video, for adding it to a YouTube playlist (one row per track searched; a new search
-- replaces it). video_id NULL: searched, YouTube does not have it.
CREATE TABLE track_youtube (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    video_id TEXT,
    source TEXT CHECK (source IS NULL OR source IN ('audio', 'search')),
    title TEXT,
    channel TEXT,
    duration INTEGER,
    confidence REAL,
    found_at TEXT NOT NULL
);
