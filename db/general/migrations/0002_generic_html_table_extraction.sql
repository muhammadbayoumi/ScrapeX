-- General migration 0002: owner-approved HTML table extraction storage.
-- Detection candidates remain transient. Only saved evidence and approved
-- datasets, schemas, records, and revisions are persisted in General.

CREATE TABLE generic_page_snapshot (
    page_snapshot_id INTEGER PRIMARY KEY,
    source_url       TEXT NOT NULL,
    content_type     TEXT NOT NULL DEFAULT 'text/html'
        CHECK (content_type = 'text/html'),
    html_content     TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    captured_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX ix_generic_page_snapshot_page
    ON generic_page_snapshot(page_snapshot_id, captured_at);
CREATE INDEX ix_generic_page_snapshot_hash
    ON generic_page_snapshot(content_hash, page_snapshot_id);

CREATE TRIGGER trg_generic_page_snapshot_immutable_update
BEFORE UPDATE ON generic_page_snapshot
BEGIN
    SELECT RAISE(ABORT, 'saved HTML snapshots are immutable');
END;

CREATE TRIGGER trg_generic_page_snapshot_immutable_delete
BEFORE DELETE ON generic_page_snapshot
BEGIN
    SELECT RAISE(ABORT, 'saved HTML snapshots are immutable');
END;

CREATE TABLE dataset_schema_version (
    schema_version_id     INTEGER PRIMARY KEY,
    dataset_definition_id INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    version_number        INTEGER NOT NULL CHECK (version_number >= 1),
    schema_hash           TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'approved'
        CHECK (status IN ('approved','retired')),
    approved_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to              TEXT,
    UNIQUE (dataset_definition_id, version_number),
    UNIQUE (dataset_definition_id, schema_hash)
);

CREATE UNIQUE INDEX ux_dataset_schema_version_active
    ON dataset_schema_version(dataset_definition_id)
    WHERE valid_to IS NULL;

CREATE TABLE schema_version_field (
    schema_version_id   INTEGER NOT NULL
        REFERENCES dataset_schema_version(schema_version_id),
    field_definition_id INTEGER NOT NULL
        REFERENCES field_definition(field_definition_id),
    field_order         INTEGER NOT NULL CHECK (field_order >= 0),
    PRIMARY KEY (schema_version_id, field_definition_id),
    UNIQUE (schema_version_id, field_order)
);

CREATE INDEX ix_schema_version_field_order
    ON schema_version_field(schema_version_id, field_order);

CREATE TABLE generic_record (
    generic_record_id     INTEGER PRIMARY KEY,
    dataset_definition_id INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    record_key            TEXT NOT NULL,
    schema_version_id     INTEGER NOT NULL
        REFERENCES dataset_schema_version(schema_version_id),
    data_json             TEXT NOT NULL
        CHECK (json_valid(data_json) AND json_type(data_json) = 'object'),
    source_snapshot_id    INTEGER NOT NULL
        REFERENCES generic_page_snapshot(page_snapshot_id),
    source_locator        TEXT NOT NULL,
    content_hash          TEXT NOT NULL,
    first_seen_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    status                TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','unavailable','retired')),
    UNIQUE (dataset_definition_id, record_key)
);

CREATE INDEX ix_generic_record_page
    ON generic_record(dataset_definition_id, generic_record_id);
CREATE INDEX ix_generic_record_snapshot
    ON generic_record(source_snapshot_id, generic_record_id);

CREATE TABLE generic_record_revision (
    record_revision_id INTEGER PRIMARY KEY,
    generic_record_id  INTEGER NOT NULL REFERENCES generic_record(generic_record_id),
    schema_version_id  INTEGER NOT NULL
        REFERENCES dataset_schema_version(schema_version_id),
    source_snapshot_id INTEGER NOT NULL
        REFERENCES generic_page_snapshot(page_snapshot_id),
    data_json          TEXT NOT NULL
        CHECK (json_valid(data_json) AND json_type(data_json) = 'object'),
    content_hash       TEXT NOT NULL,
    observed_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (generic_record_id, source_snapshot_id, content_hash)
);

CREATE INDEX ix_generic_record_revision_record
    ON generic_record_revision(generic_record_id, record_revision_id);

CREATE TRIGGER trg_generic_record_revision_append_only_update
BEFORE UPDATE ON generic_record_revision
BEGIN
    SELECT RAISE(ABORT, 'generic record revisions are append-only');
END;

CREATE TRIGGER trg_generic_record_revision_append_only_delete
BEFORE DELETE ON generic_record_revision
BEGIN
    SELECT RAISE(ABORT, 'generic record revisions are append-only');
END;

CREATE TABLE generic_ingestion (
    generic_ingestion_id  INTEGER PRIMARY KEY,
    dataset_definition_id INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    schema_version_id     INTEGER NOT NULL
        REFERENCES dataset_schema_version(schema_version_id),
    source_snapshot_id    INTEGER NOT NULL
        REFERENCES generic_page_snapshot(page_snapshot_id),
    source_locator        TEXT NOT NULL,
    record_count          INTEGER NOT NULL CHECK (record_count >= 0),
    status                TEXT NOT NULL DEFAULT 'success'
        CHECK (status = 'success'),
    ingested_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (source_snapshot_id, source_locator)
);

CREATE INDEX ix_generic_ingestion_dataset
    ON generic_ingestion(dataset_definition_id, generic_ingestion_id);

CREATE TRIGGER trg_generic_ingestion_append_only_update
BEFORE UPDATE ON generic_ingestion
BEGIN
    SELECT RAISE(ABORT, 'generic ingestions are append-only');
END;

CREATE TRIGGER trg_generic_ingestion_append_only_delete
BEFORE DELETE ON generic_ingestion
BEGIN
    SELECT RAISE(ABORT, 'generic ingestions are append-only');
END;

-- Cross-table guards keep approved schema state inside one General dataset.
CREATE TRIGGER trg_schema_version_field_matches_insert
BEFORE INSERT ON schema_version_field
FOR EACH ROW
WHEN (SELECT dataset_definition_id FROM field_definition
      WHERE field_definition_id = NEW.field_definition_id LIMIT 1) <>
     (SELECT dataset_definition_id FROM dataset_schema_version
      WHERE schema_version_id = NEW.schema_version_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'schema fields must belong to the schema dataset');
END;

CREATE TRIGGER trg_schema_version_field_matches_update
BEFORE UPDATE OF schema_version_id, field_definition_id ON schema_version_field
FOR EACH ROW
WHEN (SELECT dataset_definition_id FROM field_definition
      WHERE field_definition_id = NEW.field_definition_id LIMIT 1) <>
     (SELECT dataset_definition_id FROM dataset_schema_version
      WHERE schema_version_id = NEW.schema_version_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'schema fields must belong to the schema dataset');
END;

CREATE TRIGGER trg_generic_record_schema_matches_insert
BEFORE INSERT ON generic_record
FOR EACH ROW
WHEN NEW.dataset_definition_id <>
     (SELECT dataset_definition_id FROM dataset_schema_version
      WHERE schema_version_id = NEW.schema_version_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'generic record schema must belong to its dataset');
END;

CREATE TRIGGER trg_generic_record_schema_matches_update
BEFORE UPDATE OF dataset_definition_id, schema_version_id ON generic_record
FOR EACH ROW
WHEN NEW.dataset_definition_id <>
     (SELECT dataset_definition_id FROM dataset_schema_version
      WHERE schema_version_id = NEW.schema_version_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'generic record schema must belong to its dataset');
END;

CREATE TRIGGER trg_generic_record_revision_matches_insert
BEFORE INSERT ON generic_record_revision
FOR EACH ROW
WHEN (SELECT dataset_definition_id FROM dataset_schema_version
      WHERE schema_version_id = NEW.schema_version_id LIMIT 1) <>
     (SELECT dataset_definition_id FROM generic_record
      WHERE generic_record_id = NEW.generic_record_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'generic record revision schema must belong to its dataset');
END;

CREATE TRIGGER trg_generic_ingestion_matches_insert
BEFORE INSERT ON generic_ingestion
FOR EACH ROW
WHEN NEW.dataset_definition_id <>
     (SELECT dataset_definition_id FROM dataset_schema_version
      WHERE schema_version_id = NEW.schema_version_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'generic ingestion schema must belong to its dataset');
END;

PRAGMA user_version = 2;
