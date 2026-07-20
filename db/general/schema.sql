-- General database baseline 0001: generic catalogue definitions only.
-- Generic snapshots, jobs, schedules and records arrive in their owning slices.

PRAGMA foreign_keys = ON;
PRAGMA application_id = 1398294350;

CREATE TABLE scrapex_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO scrapex_meta (key, value) VALUES
    ('database_kind', 'general'),
    ('migration_stream', 'general');

CREATE TABLE database_migration (
    migration_number INTEGER PRIMARY KEY,
    migration_name   TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    applied_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE site_profile (
    site_profile_id      INTEGER PRIMARY KEY,
    site_key             TEXT NOT NULL UNIQUE,
    display_name         TEXT NOT NULL,
    base_url             TEXT NOT NULL,
    marketlens_source_key TEXT,
    lifecycle            TEXT NOT NULL DEFAULT 'draft'
        CHECK (lifecycle IN ('draft','active','paused')),
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to             TEXT
);

CREATE INDEX ix_site_profile_page ON site_profile(valid_to, site_profile_id);

CREATE TABLE dataset_definition (
    dataset_definition_id INTEGER PRIMARY KEY,
    site_profile_id       INTEGER NOT NULL REFERENCES site_profile(site_profile_id),
    dataset_key           TEXT NOT NULL,
    original_name         TEXT NOT NULL,
    display_name          TEXT,
    dataset_kind          TEXT NOT NULL DEFAULT 'unknown'
        CHECK (dataset_kind IN ('table','list','detail','tree','stream','unknown')),
    discovery_method      TEXT NOT NULL
        CHECK (discovery_method IN (
            'manual','html_table','repeating_dom','json','api','inferred')),
    locator_json          TEXT NOT NULL DEFAULT '{}',
    first_seen_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to              TEXT,
    UNIQUE (site_profile_id, dataset_key)
);

CREATE INDEX ix_dataset_definition_site
    ON dataset_definition(site_profile_id, dataset_definition_id, valid_to);

CREATE TABLE field_definition (
    field_definition_id   INTEGER PRIMARY KEY,
    dataset_definition_id INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    field_key             TEXT NOT NULL,
    original_name         TEXT NOT NULL,
    display_name          TEXT,
    data_type             TEXT NOT NULL DEFAULT 'unknown'
        CHECK (data_type IN (
            'text','integer','decimal','boolean','date','datetime','url','json','unknown')),
    is_nullable           INTEGER NOT NULL DEFAULT 1 CHECK (is_nullable IN (0,1)),
    identity_role         TEXT NOT NULL DEFAULT 'none'
        CHECK (identity_role IN ('none','candidate','key_part')),
    display_order         INTEGER NOT NULL DEFAULT 0 CHECK (display_order >= 0),
    first_seen_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to              TEXT,
    UNIQUE (dataset_definition_id, field_key)
);

CREATE INDEX ix_field_definition_dataset
    ON field_definition(dataset_definition_id, display_order, field_definition_id);

CREATE TABLE dataset_relationship (
    dataset_relationship_id INTEGER PRIMARY KEY,
    site_profile_id         INTEGER NOT NULL REFERENCES site_profile(site_profile_id),
    relationship_key        TEXT NOT NULL,
    parent_dataset_id       INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    child_dataset_id        INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    cardinality             TEXT NOT NULL DEFAULT 'unknown'
        CHECK (cardinality IN (
            'one_to_one','one_to_many','many_to_one','many_to_many','unknown')),
    review_status           TEXT NOT NULL DEFAULT 'suggested'
        CHECK (review_status IN ('suggested','confirmed','rejected')),
    confidence              REAL NOT NULL DEFAULT 0.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence_json           TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to                TEXT,
    CHECK (parent_dataset_id <> child_dataset_id),
    UNIQUE (site_profile_id, relationship_key)
);

CREATE INDEX ix_dataset_relationship_site
    ON dataset_relationship(site_profile_id, dataset_relationship_id, valid_to);

CREATE TABLE relationship_field_pair (
    relationship_field_pair_id INTEGER PRIMARY KEY,
    dataset_relationship_id    INTEGER NOT NULL
        REFERENCES dataset_relationship(dataset_relationship_id),
    parent_field_id             INTEGER NOT NULL REFERENCES field_definition(field_definition_id),
    child_field_id              INTEGER NOT NULL REFERENCES field_definition(field_definition_id),
    pair_order                  INTEGER NOT NULL DEFAULT 0 CHECK (pair_order >= 0),
    UNIQUE (dataset_relationship_id, parent_field_id, child_field_id),
    UNIQUE (dataset_relationship_id, pair_order)
);

CREATE INDEX ix_relationship_field_pair_relationship
    ON relationship_field_pair(dataset_relationship_id, pair_order);

CREATE TRIGGER trg_dataset_relationship_same_site_insert
BEFORE INSERT ON dataset_relationship
FOR EACH ROW
WHEN (SELECT site_profile_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.parent_dataset_id LIMIT 1) <> NEW.site_profile_id
  OR (SELECT site_profile_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.child_dataset_id LIMIT 1) <> NEW.site_profile_id
BEGIN
    SELECT RAISE(ABORT, 'relationship datasets must belong to the same site profile');
END;

CREATE TRIGGER trg_dataset_relationship_same_site_update
BEFORE UPDATE OF site_profile_id, parent_dataset_id, child_dataset_id
ON dataset_relationship
FOR EACH ROW
WHEN (SELECT site_profile_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.parent_dataset_id LIMIT 1) <> NEW.site_profile_id
  OR (SELECT site_profile_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.child_dataset_id LIMIT 1) <> NEW.site_profile_id
BEGIN
    SELECT RAISE(ABORT, 'relationship datasets must belong to the same site profile');
END;

CREATE TRIGGER trg_relationship_field_pair_matches_insert
BEFORE INSERT ON relationship_field_pair
FOR EACH ROW
WHEN (SELECT dataset_definition_id FROM field_definition
      WHERE field_definition_id = NEW.parent_field_id LIMIT 1) <>
     (SELECT parent_dataset_id FROM dataset_relationship
      WHERE dataset_relationship_id = NEW.dataset_relationship_id LIMIT 1)
  OR (SELECT dataset_definition_id FROM field_definition
      WHERE field_definition_id = NEW.child_field_id LIMIT 1) <>
     (SELECT child_dataset_id FROM dataset_relationship
      WHERE dataset_relationship_id = NEW.dataset_relationship_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'relationship fields must belong to their mapped datasets');
END;

CREATE TRIGGER trg_relationship_field_pair_matches_update
BEFORE UPDATE OF dataset_relationship_id, parent_field_id, child_field_id
ON relationship_field_pair
FOR EACH ROW
WHEN (SELECT dataset_definition_id FROM field_definition
      WHERE field_definition_id = NEW.parent_field_id LIMIT 1) <>
     (SELECT parent_dataset_id FROM dataset_relationship
      WHERE dataset_relationship_id = NEW.dataset_relationship_id LIMIT 1)
  OR (SELECT dataset_definition_id FROM field_definition
      WHERE field_definition_id = NEW.child_field_id LIMIT 1) <>
     (SELECT child_dataset_id FROM dataset_relationship
      WHERE dataset_relationship_id = NEW.dataset_relationship_id LIMIT 1)
BEGIN
    SELECT RAISE(ABORT, 'relationship fields must belong to their mapped datasets');
END;

PRAGMA user_version = 1;
