-- Copies: one record per release, but you can own it more than once. The record's own section_id is
-- the first copy's shelf place; every further copy is a row here with its own place (NULL = unsorted).
CREATE TABLE record_copies (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES cube_sections(id) ON DELETE SET NULL,
    added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_record_copies_record ON record_copies(record_id);
CREATE INDEX idx_record_copies_section ON record_copies(section_id);

-- Releases you deleted here but chose to keep in the Discogs collection: imports skip them.
CREATE TABLE discogs_kept (
    discogs_release_id INTEGER PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    kept_at TEXT NOT NULL
);

-- Scheduled syncs, in minutes (0 = only when you ask).
INSERT INTO app_settings (key, value) VALUES ('import_every_min', '0'), ('push_every_min', '0');
