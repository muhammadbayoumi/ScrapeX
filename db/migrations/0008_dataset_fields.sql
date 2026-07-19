-- ============================================================================
-- Migration 0008 — presentation metadata for dataset columns (spec section 22).
--
-- THE INVARIANT: a presentation change is NEVER a destructive schema change.
--   field_key      immutable — the identity connectors and ingest agree on
--   original_name  preserved forever, so "reset names" always has a target
--   display_name   the only user-editable label
--   is_hidden      hiding removes a column from a VIEW, never the data; a hidden
--                  field keeps receiving every future update
--   display_order  layout only
--
-- Nothing in this table can delete a field or a value. Saved views are layered
-- on top so the owner can keep several arrangements of the same dataset.
-- ============================================================================

CREATE TABLE dataset_field (
    dataset_field_id INTEGER PRIMARY KEY,
    source_key       TEXT NOT NULL,          -- the dataset this column belongs to
    field_key        TEXT NOT NULL,          -- IMMUTABLE identity
    original_name    TEXT NOT NULL,          -- as first discovered; never rewritten
    display_name     TEXT,                   -- NULL = show original_name
    data_type        TEXT NOT NULL DEFAULT 'text'
        CHECK (data_type IN ('text','number','bool','date')),
    is_hidden        INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0,1)),
    display_order    INTEGER NOT NULL DEFAULT 0,
    first_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX ux_dataset_field ON dataset_field(source_key, field_key);
CREATE INDEX ix_dataset_field_order ON dataset_field(source_key, display_order);

CREATE TABLE saved_view (
    saved_view_id INTEGER PRIMARY KEY,
    source_key    TEXT NOT NULL,
    view_name     TEXT NOT NULL,
    config_json   TEXT NOT NULL,             -- {columns:[...], sort:..., filters:{...}}
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX ux_saved_view_name ON saved_view(source_key, view_name);

PRAGMA user_version = 8;
