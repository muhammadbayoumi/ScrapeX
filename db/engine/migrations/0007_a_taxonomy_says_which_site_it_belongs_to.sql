-- =====================================================================
-- 0007 — A TAXONOMY SAYS WHICH SITE IT BELONGS TO, A REFERENCE IS A REAL
--        COLUMN, AND A CHANGED FIELD SAYS WHICH FIELD IT WAS
--
-- His rulings, 2026-08-21: R-30 «نفذ ب» settles that R-19 is built as
-- child DATASETS whose value references a `classification_node`; R-31
-- «نعم وسع النطاق ونفذ الأفضل» widens it after he asked whether a field
-- change could be WRITTEN rather than derived, and what happens when the
-- site adds a field. Two of his four questions measured as "not today".
--
-- `classification_node` and `classification_scheme` have existed since the
-- schema was derived and hold ZERO rows. Nothing has ever written them:
-- `grep "INSERT INTO classification"` returns nothing in the repository,
-- and `reports.py` only names them in a glossary. This is the first
-- tenant, and five things were missing for it.
--
-- ---------------------------------------------------------------------
-- 1 · A SOURCE SCHEME COULD NOT NAME ITS SOURCE
--
-- `classification_scheme.source_id` references `source_site(source_id)` —
-- the PRICE side of the warehouse. muqawil is not there: `source_site`
-- holds four price sources, and muqawil is registered in `site_profile` as
-- `muqawil_org`. So a scheme with `scheme_type = 'source'` describing
-- muqawil's own taxonomy would have to leave `source_id` NULL: a source
-- scheme with no source, a row contradicting itself. The generic side gets
-- its own pointer and `source_id` is left exactly as the price side needs.
--
-- ---------------------------------------------------------------------
-- 2 · A NODE COULD NOT BE FOUND AGAIN BY NAME
--
-- The only uniqueness was `(scheme_id, external_id) WHERE external_id IS
-- NOT NULL`. muqawil publishes activities as NAMES with no identifier at
-- all — the cell reads `التشغيل والصيانة - مكافحة الآفات والتطهير البيئي
-- Operations and Maintenance Activities - Pest Control & Environmental
-- Disinfection`. With `external_id` NULL that index constrains nothing, so
-- a second extraction pass would insert the whole taxonomy again and the
-- integer references would fan out across duplicates. When the site gives
-- no id, a node's identity is its name under its parent.
--
-- `ifnull(parent_node_id, 0)` IS LOAD-BEARING. NULLs are DISTINCT in a
-- SQLite unique index, so a plain `(scheme_id, parent_node_id,
-- node_name_ar)` would let two ROOT nodes share a name — and the roots are
-- exactly the nodes whose parent is NULL. Folding NULL to 0 constrains the
-- root level like every other. Verified against a real database before
-- this was written: the duplicate root is refused.
--
-- ---------------------------------------------------------------------
-- 3 · THE REFERENCE WAS UNTYPED TEXT INSIDE JSON
--
-- A child row carries its node in `data_json`, and `json_extract` is not a
-- column: measured on 2026-08-21, a row storing `{"node_id": "143"}` did
-- NOT match `json_extract(...) = 143` — one of two rows that both mean 143
-- — a nonexistent node id was accepted with nothing to stop it, and a typo
-- in the JSON path returned NULL instead of an error.
--
-- A VIRTUAL GENERATED COLUMN FIXES ALL THREE, AND THAT WAS NOT ASSUMED.
-- Measured on SQLite 3.45.1: `ALTER TABLE ... ADD COLUMN ... GENERATED
-- ALWAYS AS (...) VIRTUAL REFERENCES ...` is accepted on an existing
-- table; the column is indexable (`SEARCH ... USING INDEX (node_id=?)`);
-- INTEGER affinity makes `"143"` match `143`, so it found 2 of 2; a
-- mistyped column name raises; and the FOREIGN KEY IS ENFORCED — a
-- nonexistent node id raises `IntegrityError`.
--
-- VIRTUAL, NOT STORED, for two reasons. `ALTER TABLE` cannot add a STORED
-- generated column at all, and VIRTUAL costs no bytes — the value is
-- computed on read and materialised only in the index, which is precisely
-- where it is needed.
--
-- `parent_record_key` IS GENERIC ON PURPOSE. A child row names its parent
-- by the parent's `record_key`, never by a site-specific field like
-- `contractor_id`, because `dataset_relationship` and
-- `relationship_field_pair` express the join as field pairs and this index
-- has to serve whatever source arrives next.
--
-- BOTH ARE NULL FOR A PARENT ROW, and that is correct rather than
-- tolerated: the 1,172 contractor rows carry neither key, a NULL foreign
-- key is always satisfied, and the partial indexes exclude them entirely.
--
-- ---------------------------------------------------------------------
-- 4 · A CHANGED FIELD DID NOT SAY WHICH FIELD
--
-- `generic_record_revision.data_json` holds the WHOLE object, so "when did
-- this contractor's readiness change" is answerable only by diffing two
-- revisions, and is written down nowhere. That is what he asked for.
--
-- IT IS LIGHTER THAN WHAT IT SUPPLEMENTS. A revision copies all 21 fields
-- — roughly 2.5 KB — to record one field moving. A row here is on the
-- order of 100 bytes. AND IT DOES NOT REPLACE THE REVISION: the revision
-- is the row as it stood, which is what an audit needs; this is the
-- question anyone actually asks.
--
-- EVERY ROW CARRIES ITS EVIDENCE. `source_snapshot_id NOT NULL`, the same
-- rule as `generic_record` and for the same reason — a recorded change
-- with no provenance is a change nobody can check.
--
-- ---------------------------------------------------------------------
-- 5 · A NEW FIELD WAS REFUSED, AND COULD NEVER BECOME A VERSION
--
-- No DDL is needed for this one — `version_number`, `status` and
-- `valid_to` already exist — and it is recorded here because the schema is
-- where the reason belongs. Measured: all five references to `valid_to` in
-- the code are READS (`WHERE valid_to IS NULL`). Nothing has ever written
-- it, so v2 was unreachable by construction and `ExtractionConflict` was
-- the only outcome. The behaviour change lives in `extract/service.py`,
-- and it is DIRECTIONAL: a superset retires the active version and opens
-- v2; a subset, a rename or a retype is still refused. #234 is why —
-- `region_id=0`'s pages carried 21 of the declared 22 fields and were
-- correctly refused, and auto-versioning any drift would have accepted a
-- parser that silently lost a column.
-- =====================================================================

-- 1 · the generic side's own owner pointer. Nullable: a scheme that is not
--     a site's own has nothing to point at.
ALTER TABLE classification_scheme ADD COLUMN site_profile_id INTEGER
    REFERENCES site_profile(site_profile_id);

-- 2 · a node's identity when the site publishes no id of its own.
CREATE UNIQUE INDEX IF NOT EXISTS ux_classification_node_name
    ON classification_node(scheme_id, ifnull(parent_node_id, 0), node_name_ar);

-- 3 · the reference as a real, typed, foreign-keyed column.
ALTER TABLE generic_record ADD COLUMN node_id INTEGER
    GENERATED ALWAYS AS (json_extract(data_json, '$.node_id')) VIRTUAL
    REFERENCES classification_node(node_id);

ALTER TABLE generic_record ADD COLUMN parent_record_key TEXT
    GENERATED ALWAYS AS (json_extract(data_json, '$.parent_record_key')) VIRTUAL;

CREATE INDEX IF NOT EXISTS ix_generic_record_node
    ON generic_record(node_id) WHERE node_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_generic_record_parent_key
    ON generic_record(parent_record_key) WHERE parent_record_key IS NOT NULL;

-- 4 · which field changed, from what, to what, and on whose evidence.
CREATE TABLE IF NOT EXISTS generic_record_field_change (
    field_change_id     INTEGER PRIMARY KEY,
    generic_record_id   INTEGER NOT NULL
        REFERENCES generic_record(generic_record_id),
    field_definition_id INTEGER NOT NULL
        REFERENCES field_definition(field_definition_id),
    -- NULL means the field did not exist on the row before this change,
    -- which is what a schema moving to v2 looks like from a row's side.
    -- Distinguished from an empty string on purpose: "" is a value the
    -- site published, NULL is the absence of the field itself.
    value_before        TEXT,
    value_after         TEXT,
    source_snapshot_id  INTEGER NOT NULL
        REFERENCES generic_page_snapshot(page_snapshot_id),
    observed_at         TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    -- The same idempotency the revision has: re-running an extraction over
    -- stored pages must not write the same change twice. Per DEC-10 a
    -- corrected parser re-run is expected to be cheap and repeatable.
    UNIQUE (generic_record_id, field_definition_id, source_snapshot_id)
);

-- "What changed for this row, newest first" — the profile screen's question.
CREATE INDEX IF NOT EXISTS ix_field_change_record
    ON generic_record_field_change(generic_record_id, observed_at);

-- "What changed in this field across every row" — the analytic one, and the
-- reason a field-level log beats diffing revisions: there is no way to ask
-- this of a whole-row revision without reading every one of them.
CREATE INDEX IF NOT EXISTS ix_field_change_field
    ON generic_record_field_change(field_definition_id, observed_at);
