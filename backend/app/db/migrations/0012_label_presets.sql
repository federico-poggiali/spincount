-- Saved label looks (design, text sizes, hidden fields) that any label can start from.
CREATE TABLE label_presets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    look TEXT NOT NULL,  -- JSON: app.labels.data.LabelLook
    updated_at TEXT NOT NULL
);
