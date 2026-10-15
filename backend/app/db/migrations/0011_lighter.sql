-- Search by meaning is gone: drop the note_embeddings vec0 table without needing sqlite-vec loaded.
-- A virtual table has no storage of its own, so removing its schema row and dropping its shadow tables
-- is the whole of it. Databases created after 0001 lost its CREATE have none of these, which is fine.
PRAGMA writable_schema = ON;
DELETE FROM sqlite_master WHERE type = 'table' AND name = 'note_embeddings';
PRAGMA writable_schema = OFF;
DROP TABLE IF EXISTS note_embeddings_info;
DROP TABLE IF EXISTS note_embeddings_chunks;
DROP TABLE IF EXISTS note_embeddings_rowids;
DROP TABLE IF EXISTS note_embeddings_vector_chunks00;

-- Every note is prose since 0008, so the type column says nothing.
ALTER TABLE notes DROP COLUMN type;

-- Two statuses: owned (the library) and wantlist (everything else). The CHECK still allows the old
-- 'considering' value because changing it means rebuilding the table; the API no longer accepts it.
UPDATE records SET status = 'wantlist' WHERE status = 'considering';
