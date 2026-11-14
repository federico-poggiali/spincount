-- Syncing the library with Discogs: app-wide settings the backend acts on, whether a wishlist record
-- is on the Discogs wantlist, and when a wishlist record became owned ("recently traded").
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO app_settings (key, value) VALUES ('auto_collection', 'on'), ('auto_wantlist', 'off');

ALTER TABLE records ADD COLUMN traded_at TEXT;
ALTER TABLE records ADD COLUMN discogs_wantlist_synced INTEGER NOT NULL DEFAULT 0
    CHECK (discogs_wantlist_synced IN (0, 1));
CREATE INDEX idx_records_traded ON records(traded_at);
