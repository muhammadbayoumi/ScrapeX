-- The tender history keeps each release as SQLite JSONB, not as JSON text.
--
-- HIS DECISION ON #1733, 2026-10-20: "the best, not the cheapest, with a reference". The
-- references are ES-6 (`docs/ENGINEERING-SOURCES.md`): Supabase recommends jsonb "for
-- almost all cases"; PostgreSQL prefers it unless the exact text matters, and the exact
-- text is kept already, compressed, in `fetched_responses`; SQLite's own documentation says
-- its JSONB "is smaller and faster than text JSON". Measured on the six real World Bank
-- releases, 100,000 rows: 1,462 bytes a release against 1,643, `json_extract` 2.2 to 2.4
-- times faster on four paths, and the compile's own read unchanged.
--
-- WHAT DOES NOT CHANGE. `payload_sha256` is still the sha256 of the release's canonical
-- text, taken in Python before the write (`tenderstore._canonical`), so the same release
-- read twice is stored once as before. The CHECK still holds the column to one JSON object:
-- `json_valid(payload, 8)` is "strictly conforming JSONB", and JSON text is refused. Every
-- other column, the UNIQUE key, both indexes and both append-only triggers are as `0025`
-- declared them.
--
-- WHY A REBUILD: SQLite cannot change a column's type or its CHECK in place. The table is
-- empty on every installation until part 3b's first crawl, so this costs nothing; any row
-- it does hold is carried over, converted by `jsonb()`.
--
-- SQLITE 3.45.0 OR NEWER, or this stops here. `jsonb()` and the two-argument `json_valid`
-- arrived in 3.45.0 (2024-01-15). On an older SQLite the copy below cannot be prepared
-- ("no such function: jsonb"), so the migration fails before it changes anything, by the
-- name of the function it lacks. The engine's interpreter bundles its SQLite, and the
-- pinned Python (`.python-version`) ships 3.50.
--
-- `legacy_alter_table = ON` IS REQUIRED, for `0023`'s reason: three tables carry
-- `REFERENCES tender_releases` (`tenders`, `tender_contact_points`,
-- `tender_beneficial_owners`).
-- Without the pragma the RENAME rewrites them to point at `tender_releases_old`, which is
-- then dropped. The triggers and indexes go with the old table and are created again.

PRAGMA user_version = 26;
PRAGMA legacy_alter_table = ON;

-- One release as read: the history. Append-only. Its payload is JSONB (ES-6).
CREATE TABLE tender_releases_rebuilt (
    id                  INTEGER PRIMARY KEY,
    tender_process_id   INTEGER NOT NULL REFERENCES tender_processes(id),
    -- OCDS release id: the source's own notice id.
    release_ref         TEXT NOT NULL,
    -- OCDS date: when the source published it (valid time).
    released_at         TEXT NOT NULL,
    -- The source's own change stamp, when it gives one (#1616 D10).
    source_modified_at  TEXT,
    -- OCDS tag: a JSON array of releaseTag codes.
    tags                TEXT NOT NULL CHECK (json_valid(tags) AND json_type(tags) = 'array'),
    -- The language the source states for it, as a BCP 47 tag (#1616 D10).
    language            TEXT,
    -- The release as OCDS JSON, without persons, stored as SQLite JSONB (ES-6).
    payload             BLOB NOT NULL CHECK (json_valid(payload, 8) AND json_type(payload) = 'object'),
    -- sha256 of the payload's canonical text, hex: the same release read twice is stored once.
    payload_sha256      TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    -- The response it was read from.
    fetched_response_id INTEGER REFERENCES fetched_responses(id),
    -- When it was stored here (system time).
    recorded_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (tender_process_id, release_ref, payload_sha256)
) STRICT;

INSERT INTO tender_releases_rebuilt (
    id, tender_process_id, release_ref, released_at, source_modified_at, tags, language,
    payload, payload_sha256, fetched_response_id, recorded_at)
SELECT
    id, tender_process_id, release_ref, released_at, source_modified_at, tags, language,
    jsonb(payload), payload_sha256, fetched_response_id, recorded_at
FROM tender_releases;

ALTER TABLE tender_releases RENAME TO tender_releases_old;
ALTER TABLE tender_releases_rebuilt RENAME TO tender_releases;
DROP TABLE tender_releases_old;

CREATE INDEX tender_releases_tender_process_id_idx ON tender_releases (tender_process_id);
CREATE INDEX tender_releases_fetched_response_id_idx ON tender_releases (fetched_response_id);

CREATE TRIGGER tender_releases_append_only_update
BEFORE UPDATE ON tender_releases
BEGIN
    SELECT RAISE(ABORT, 'tender releases are append-only');
END;

CREATE TRIGGER tender_releases_append_only_delete
BEFORE DELETE ON tender_releases
BEGIN
    SELECT RAISE(ABORT, 'tender releases are append-only');
END;

PRAGMA legacy_alter_table = OFF;
