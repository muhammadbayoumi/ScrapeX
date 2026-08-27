-- TWO VERSIONS MAY SHARE A SHAPE ACROSS TIME, AND THE OLD CONSTRAINT SAID THEY COULD NOT.
--
-- `dataset_schema_version` carried `UNIQUE (dataset_definition_id, schema_hash)`, so one
-- field-set shape could exist as at most one version of a dataset, for ever. That is wrong
-- for reasons measured on 2026-08-27 rather than argued:
--
--   * `contractor_profiles` has v2 (27 fields, RETIRED) holding all 17,371 live rows, and
--     v3 (39 fields, APPROVED) holding only the 14 impostor rows `OP-64` disowned. The 12
--     fields v3 adds are `x_*` listing keys, and every one is EMPTY on all 17,371.
--   * `R-53` is his ruling to re-approve those rows onto a clean 27-field v4 — and he
--     explicitly refused the cheaper route of reopening v2, because that says v2's
--     retirement never happened.
--   * A v4 carrying v2's 27 fields carries v2's hash, and this constraint forbade it.
--
-- AND THE CONSTRAINT WAS HIDING A WORSE DEFECT, which is the real reason it goes.
-- `_ensure_schema` looks a version up by `(dataset_definition_id, schema_hash)` with NO
-- filter on status, so a NEW page whose shape matches a retired version is bound to that
-- retired version. Measured: a fresh 27-field profile page today joins v2, which is dead.
-- The constraint guaranteed there was exactly one row to find, which is exactly why nobody
-- noticed the lookup could find a dead one. Lifting it lets the lookup prefer the approved
-- version — and `scrapex/extract/service.py` now does, for every dataset rather than for
-- muqawil alone, on his ruling of 2026-08-27.
--
-- WHAT IS *NOT* RELAXED. `ux_dataset_schema_version_active` still allows exactly one row per
-- dataset with `valid_to IS NULL`, so a dataset can never have two approved versions. That is
-- the invariant that matters, and it is recreated below because it belongs to the table being
-- replaced. `UNIQUE (dataset_definition_id, version_number)` also stays: `version_number` is
-- the version's IDENTITY, and two versions numbered alike make "which v2?" unanswerable.
-- `R-31`'s directional rule in `_retire_or_refuse` is untouched — a subset is still refused
-- on the ordinary approval path, and `R-53`'s repair is a separate named operation that
-- proves its own preconditions.
--
-- THIS IS THE FIRST MIGRATION HERE TO REBUILD A TABLE, and the ordering below is not the
-- obvious one. TWO TRAPS WERE HIT AND MEASURED BEFORE THIS FILE WAS WRITTEN:
--
--   1. With `legacy_alter_table` OFF (the default since 3.25), renaming the OLD table
--      REWRITES the four tables whose foreign keys reference it, so they would end up
--      pointing at `dataset_schema_version_old`. `PRAGMA legacy_alter_table = ON` is what
--      that pragma exists for, and with it the four FK clauses still name
--      `dataset_schema_version` afterwards — verified, four of four.
--   2. The first attempt dropped the old table before renaming the new one into place, and
--      SQLite refused: `error in trigger trg_generic_ingestion_matches_insert: no such
--      table: main.dataset_schema_version`. SIX triggers reference this table from
--      `generic_record`, `generic_record_revision`, `generic_ingestion` and
--      `schema_version_field`, and the schema re-parse rejects a trigger whose table is
--      briefly absent. So the name never disappears: the new table is renamed INTO place
--      before the old one is dropped.
--
-- PROVEN ON A COPY OF THE REAL 1,490 MB WAREHOUSE, not on a fixture: `foreign_key_check`
-- clean, six rows carried across, 31 triggers still valid, all four FK clauses intact,
-- `PRAGMA quick_check` ok, and 17,371 profile rows untouched. The runner adds the rest of
-- the safety — it wraps this file in `BEGIN IMMEDIATE`, suspends `PRAGMA foreign_keys`, and
-- runs `foreign_key_check` INSIDE the transaction, so a rebuild that orphaned a row rolls
-- back instead of being reported after the damage is permanent.

PRAGMA user_version = 13;

PRAGMA legacy_alter_table = ON;

CREATE TABLE dataset_schema_version_rebuilt (
    schema_version_id     INTEGER PRIMARY KEY,
    dataset_definition_id INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    version_number        INTEGER NOT NULL CHECK (version_number >= 1),
    schema_hash           TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'approved'
        CHECK (status IN ('approved','retired')),
    approved_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to              TEXT,
    UNIQUE (dataset_definition_id, version_number)
);

-- Columns are named rather than `SELECT *`, so a column added to the old table by a
-- migration landing before this one cannot be silently dropped by the copy.
INSERT INTO dataset_schema_version_rebuilt
    (schema_version_id, dataset_definition_id, version_number, schema_hash,
     status, approved_at, valid_to)
SELECT schema_version_id, dataset_definition_id, version_number, schema_hash,
       status, approved_at, valid_to
FROM dataset_schema_version;

ALTER TABLE dataset_schema_version RENAME TO dataset_schema_version_old;
ALTER TABLE dataset_schema_version_rebuilt RENAME TO dataset_schema_version;
DROP TABLE dataset_schema_version_old;

CREATE UNIQUE INDEX ux_dataset_schema_version_active
    ON dataset_schema_version(dataset_definition_id)
    WHERE valid_to IS NULL;

PRAGMA legacy_alter_table = OFF;
