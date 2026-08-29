-- ONE SOURCE REGISTRY. `site_profile` merges into `source_site` and stops existing.
--
-- `R-62`, his ruling of 2026-08-27: «ادمج `site_profile` فى `source_site` — سجلٌّ واحد». He
-- was offered the cheaper route -- teach `POST /api/jobs` to resolve the other registries --
-- and took the migration instead.
--
-- WHAT TWO REGISTRIES COST, measured rather than argued. `POST /api/jobs` answers
-- `404 unknown source_key 'contractors'` while `/api/table/contractors` serves 17,304 rows
-- from the same warehouse, because the route validates against one registry and the data
-- lives in the other. Every READ route already resolves both -- `/api/table`, `/api/fields`,
-- and `/api/dry/{source_key}` since #274 -- so the split survives only on the write path.
--
-- AND THE RULING PRICED IT AT TWO TABLES. Measured on his warehouse on 2026-08-29 it is
-- FOUR, because `0011`/`0012` added a fifth referencing table after `R-62` was written:
--
--     dataset_definition.site_profile_id                  3 rows
--     dataset_relationship.site_profile_id                2 rows
--     classification_scheme.site_profile_id               2 rows   <- not in the ruling
--     organization_enrichment_definition.site_profile_id  1 row    <- added by 0011/0012
--
-- All eight point at `site_profile_id = 2` (`muqawil_org`). `site_profile_id = 1`
-- (`muqawil`) is referenced by NOTHING -- it is `Q-24`'s duplicate, and it is carried across
-- and closed with `valid_to` rather than deleted, because a deletion nobody can see is how
-- the next session re-derives the same duplicate and believes it.
--
-- THREE DECISIONS THE MERGE FORCED, and all three are his:
--
--   * `source_site.source_name_ar` is NOT NULL and neither muqawil row has an Arabic name
--     stored anywhere. He gave it: «الهيئة السعودية للمقاولين».
--   * The two tables carry two ideas of state -- `source_site.active` (0/1) and
--     `site_profile.lifecycle` (draft/active/paused). **`lifecycle` survives alone**, because
--     `active = 0` cannot tell "never configured" from "you switched it off", and both
--     muqawil rows are `draft` today. The twelve price sources migrate `1 -> 'active'` and
--     `0 -> 'paused'`, and `source_site.active` has exactly TWO readers in the codebase
--     (`scrapex/storage.py`), both updated in the same change.
--   * `authority` is NOT NULL and CHECKed. muqawil.org is the Saudi Contractors Authority's
--     own register, so `'official'` -- the value that column exists to carry.
--
-- WHAT THIS MIGRATION DOES NOT DO, said out loud because the ruling implies otherwise.
-- **It does not open the crawl button on its own.** `POST /api/jobs` validates against
-- `app.state.manifest`, which is `load_manifest(sources.yaml)` -- a FILE, not this database.
-- `R-62` says the merge "is what unblocks `REQ-45`"; measured, it is necessary and not
-- sufficient, and the route change ships in the same pull request for exactly that reason.
--
-- THE TWO TRAPS `0013` MEASURED, AND THEY APPLY FIVE TIMES OVER HERE:
--   1. Renaming a table aside REWRITES the foreign-key clauses of every table referencing it
--      unless `legacy_alter_table` is ON. `source_site` is referenced by `crawl_run`,
--      `source_product` (9,270 rows), `feed_assignment` and `classification_scheme`;
--      `dataset_definition` by `generic_record`, `dataset_schema_version`, `field_definition`
--      and more. None of them may be touched.
--   2. A table's NAME may never disappear, even briefly, or the schema re-parse rejects any
--      trigger that references it. So every rebuild renames the old aside FIRST and the new
--      one into place SECOND, and the drop comes last.
--
-- The site-scoping triggers are dropped before the rebuilds and recreated after, because they
-- name the column being renamed.

PRAGMA user_version = 14;
PRAGMA legacy_alter_table = ON;

DROP TRIGGER IF EXISTS trg_dataset_relationship_same_site_insert;
DROP TRIGGER IF EXISTS trg_dataset_relationship_same_site_update;
DROP TRIGGER IF EXISTS trg_enrichment_definition_same_site_insert;
DROP TRIGGER IF EXISTS trg_enrichment_definition_same_site_update;

-- ---------------------------------------------------------------- 1 · source_site itself
-- Rebuilt rather than ALTERed because `active` carries its own CHECK, and SQLite refuses
-- `DROP COLUMN` on a column named in one.

CREATE TABLE source_site_rebuilt (
    source_id        INTEGER PRIMARY KEY,
    source_key       TEXT NOT NULL UNIQUE,   -- join key with sources.yaml (the Harvest Manifest)
    -- `DEFAULT ''` IS NEW AND DELIBERATE. The column was `NOT NULL` with no default, so
    -- every INSERT had to name it -- and a registration carries no Arabic name, so what
    -- it named was an empty string or, worse, a copy of the English. `SPARK_ESHOP`
    -- already stores '' here, so the column's own history says empty is how "not known"
    -- is spelled; the default makes that the answer instead of each caller's guess.
    source_name_ar   TEXT NOT NULL DEFAULT '', -- 'المدار', 'السويد', ...
    source_name      TEXT NOT NULL DEFAULT '',
    -- `NOT NULL DEFAULT ''`, AND BOTH HALVES WERE MEASURED. `source_site.base_url` was
    -- nullable and `site_profile.base_url` was not; a merge has to take one, and on his
    -- warehouse **zero rows of either table hold a NULL** -- 0 of 12 and 0 of 2 -- so the
    -- stronger constraint costs nothing. The DEFAULT is the second half: without it every
    -- INSERT has to name the column, and a price source is registered from `sources.yaml`
    -- before anyone has said where it lives. Empty is how this table already spells "not
    -- known" in `source_name` and `source_name_ar`; a third column doing it differently
    -- would be the inconsistency, not the rule.
    base_url         TEXT NOT NULL DEFAULT '',
    platform         TEXT,                   -- 'Magento2' | 'Salla' | 'Zid' | 'Shopify' | ... | 'Unknown'
    currency         TEXT,                   -- 'SAR' | 'EGP' | 'USD'
    timezone         TEXT,                   -- 'Asia/Riyadh'
    default_tax_mode TEXT NOT NULL DEFAULT 'incl' CHECK (default_tax_mode IN ('incl','excl')),
    authority        TEXT NOT NULL DEFAULT 'shop' CHECK (authority IN ('official','aggregator','shop')),
    -- FROM `site_profile`, and `lifecycle` replaces `active` on his ruling.
    lifecycle        TEXT NOT NULL DEFAULT 'draft'
        CHECK (lifecycle IN ('draft','active','paused')),
    price_source_key TEXT,
    crawl_scope      TEXT NOT NULL DEFAULT 'listing_only',
    crawl_slice      TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to         TEXT
);

INSERT INTO source_site_rebuilt (
    source_id, source_key, source_name_ar, source_name, base_url, platform, currency,
    timezone, default_tax_mode, authority, lifecycle)
SELECT source_id, source_key, source_name_ar, source_name, base_url, platform, currency,
       timezone, default_tax_mode, authority,
       CASE WHEN active = 1 THEN 'active' ELSE 'paused' END
  FROM source_site;

ALTER TABLE source_site RENAME TO source_site_old;
ALTER TABLE source_site_rebuilt RENAME TO source_site;
DROP TABLE source_site_old;

-- ------------------------------------------------- 2 · the map, built before anything moves
-- `MAX(source_id)` has to be read ONCE, before the inserts that change it, and the new ids
-- have to be the same ones the four repointings use. A table makes that explicit; a subquery
-- repeated in five statements would be five chances to disagree.
--
-- ROW_NUMBER over `site_profile_id` keeps the relative order, so a warehouse with a different
-- number of price sources still gets a deterministic, collision-free answer.

CREATE TABLE _site_profile_to_source (
    site_profile_id INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL UNIQUE
);

INSERT INTO _site_profile_to_source (site_profile_id, source_id)
SELECT p.site_profile_id,
       (SELECT COALESCE(MAX(s.source_id), 0) FROM source_site s)
           + ROW_NUMBER() OVER (ORDER BY p.site_profile_id)
  FROM site_profile p;

INSERT INTO source_site (
    source_id, source_key, source_name_ar, source_name, base_url, authority,
    lifecycle, price_source_key, crawl_scope, crawl_slice, created_at, updated_at, valid_to)
SELECT m.source_id,
       p.site_key,
       -- HIS ANSWER, 2026-08-29. Nothing in either registry held an Arabic name for these.
       'الهيئة السعودية للمقاولين',
       p.display_name,
       p.base_url,
       -- The Saudi Contractors Authority's own register, which is what 'official' is for.
       'official',
       -- `Q-24`: id 1 (`muqawil`) closes, id 2 (`muqawil_org`) survives and is the one with
       -- the data -- 34,675 active rows against zero. A closed row is `paused` and carries a
       -- `valid_to`; the survivor is `active`, because it is being crawled.
       CASE WHEN p.site_key = 'muqawil' THEN 'paused' ELSE 'active' END,
       p.price_source_key,
       p.crawl_scope,
       p.crawl_slice,
       p.created_at,
       strftime('%Y-%m-%dT%H:%M:%SZ','now'),
       CASE WHEN p.site_key = 'muqawil'
            THEN strftime('%Y-%m-%dT%H:%M:%SZ','now') ELSE p.valid_to END
  FROM site_profile p
  JOIN _site_profile_to_source m ON m.site_profile_id = p.site_profile_id;

-- ------------------------------------------------------------- 3 · dataset_definition

CREATE TABLE dataset_definition_rebuilt (
    dataset_definition_id INTEGER PRIMARY KEY,
    source_id             INTEGER NOT NULL REFERENCES source_site(source_id),
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
    UNIQUE (source_id, dataset_key)
);

INSERT INTO dataset_definition_rebuilt (
    dataset_definition_id, source_id, dataset_key, original_name, display_name,
    dataset_kind, discovery_method, locator_json, first_seen_at, last_seen_at, valid_to)
SELECT d.dataset_definition_id, m.source_id, d.dataset_key, d.original_name,
       d.display_name, d.dataset_kind, d.discovery_method, d.locator_json,
       d.first_seen_at, d.last_seen_at, d.valid_to
  FROM dataset_definition d
  JOIN _site_profile_to_source m ON m.site_profile_id = d.site_profile_id;

ALTER TABLE dataset_definition RENAME TO dataset_definition_old;
ALTER TABLE dataset_definition_rebuilt RENAME TO dataset_definition;
DROP TABLE dataset_definition_old;

CREATE INDEX ix_dataset_definition_site
    ON dataset_definition(source_id, dataset_definition_id, valid_to);

-- ----------------------------------------------------------- 4 · dataset_relationship

CREATE TABLE dataset_relationship_rebuilt (
    dataset_relationship_id INTEGER PRIMARY KEY,
    source_id               INTEGER NOT NULL REFERENCES source_site(source_id),
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
    UNIQUE (source_id, relationship_key)
);

INSERT INTO dataset_relationship_rebuilt (
    dataset_relationship_id, source_id, relationship_key, parent_dataset_id,
    child_dataset_id, cardinality, review_status, confidence, evidence_json,
    created_at, updated_at, valid_to)
SELECT r.dataset_relationship_id, m.source_id, r.relationship_key, r.parent_dataset_id,
       r.child_dataset_id, r.cardinality, r.review_status, r.confidence, r.evidence_json,
       r.created_at, r.updated_at, r.valid_to
  FROM dataset_relationship r
  JOIN _site_profile_to_source m ON m.site_profile_id = r.site_profile_id;

ALTER TABLE dataset_relationship RENAME TO dataset_relationship_old;
ALTER TABLE dataset_relationship_rebuilt RENAME TO dataset_relationship;
DROP TABLE dataset_relationship_old;

CREATE INDEX ix_dataset_relationship_site
    ON dataset_relationship(source_id, dataset_relationship_id, valid_to);

-- ---------------------------------------------------------- 5 · classification_scheme
-- The one table that already carried BOTH keys. Measured before writing this: its two rows
-- hold `source_id IS NULL` and `site_profile_id = 2`, so the two columns collapse into one
-- with nothing to reconcile. `COALESCE` is written the way round that keeps a price source's
-- existing `source_id` if one ever holds both.

CREATE TABLE classification_scheme_rebuilt (
    scheme_id      INTEGER PRIMARY KEY,
    scheme_name_ar TEXT NOT NULL UNIQUE,
    scheme_name    TEXT,
    scheme_type    TEXT NOT NULL CHECK (scheme_type IN ('source','internal','standard')),
    source_id      INTEGER REFERENCES source_site(source_id)  -- set when scheme_type='source'
);

INSERT INTO classification_scheme_rebuilt (
    scheme_id, scheme_name_ar, scheme_name, scheme_type, source_id)
SELECT c.scheme_id, c.scheme_name_ar, c.scheme_name, c.scheme_type,
       COALESCE(c.source_id, m.source_id)
  FROM classification_scheme c
  LEFT JOIN _site_profile_to_source m ON m.site_profile_id = c.site_profile_id;

ALTER TABLE classification_scheme RENAME TO classification_scheme_old;
ALTER TABLE classification_scheme_rebuilt RENAME TO classification_scheme;
DROP TABLE classification_scheme_old;

-- ------------------------------------------- 6 · organization_enrichment_definition

CREATE TABLE organization_enrichment_definition_rebuilt (
    enrichment_definition_id INTEGER PRIMARY KEY,
    source_id                 INTEGER NOT NULL
        REFERENCES source_site(source_id),
    source_dataset_id         INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    detail_dataset_id         INTEGER
        REFERENCES dataset_definition(dataset_definition_id),
    output_dataset_id         INTEGER NOT NULL UNIQUE
        REFERENCES dataset_definition(dataset_definition_id),
    entity_key_field          TEXT NOT NULL,
    detail_key_field          TEXT,
    field_mapping_json        TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(field_mapping_json)
               AND json_type(field_mapping_json) = 'object'),
    providers_json            TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(providers_json)
               AND json_type(providers_json) = 'array'),
    status                    TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'retired')),
    created_at                TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at                TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_run_at               TEXT,
    configuration_version     INTEGER NOT NULL DEFAULT 1
        CHECK (configuration_version >= 1),
    UNIQUE (source_dataset_id)
);

INSERT INTO organization_enrichment_definition_rebuilt (
    enrichment_definition_id, source_id, source_dataset_id, detail_dataset_id,
    output_dataset_id, entity_key_field, detail_key_field, field_mapping_json,
    providers_json, status, created_at, updated_at, last_run_at, configuration_version)
SELECT e.enrichment_definition_id, m.source_id, e.source_dataset_id, e.detail_dataset_id,
       e.output_dataset_id, e.entity_key_field, e.detail_key_field, e.field_mapping_json,
       e.providers_json, e.status, e.created_at, e.updated_at, e.last_run_at,
       e.configuration_version
  FROM organization_enrichment_definition e
  JOIN _site_profile_to_source m ON m.site_profile_id = e.site_profile_id;

ALTER TABLE organization_enrichment_definition
    RENAME TO organization_enrichment_definition_old;
ALTER TABLE organization_enrichment_definition_rebuilt
    RENAME TO organization_enrichment_definition;
DROP TABLE organization_enrichment_definition_old;

-- --------------------------------------------------- 7 · the triggers, against source_id
-- Same rules, same messages, one column renamed.
--
-- AND `0012`'s TWO `datasets_differ` TRIGGERS ARE RECREATED HERE TOO, which the first draft
-- of this file did not do. It carried a comment claiming they were "untouched: they never
-- named the registry, so the rebuild above kept them". **Measured on a copy of his warehouse:
-- 31 triggers before, 29 after.** Rebuilding a table drops EVERY trigger on it, whether or
-- not the trigger mentions the column being changed -- and one of the two lost was
-- `RAISE(ABORT, 'the enrichment output must be a new dataset')`, the guard that keeps an
-- enrichment run from writing back over the dataset it read (`R-45`).
--
-- The count is the only reason this was caught. A comment asserting a trigger survived is
-- not evidence that it did.

CREATE TRIGGER trg_dataset_relationship_same_site_insert
BEFORE INSERT ON dataset_relationship
FOR EACH ROW
WHEN (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.parent_dataset_id LIMIT 1) <> NEW.source_id
  OR (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.child_dataset_id LIMIT 1) <> NEW.source_id
BEGIN
    SELECT RAISE(ABORT, 'relationship datasets must belong to the same source');
END;

CREATE TRIGGER trg_dataset_relationship_same_site_update
BEFORE UPDATE OF source_id, parent_dataset_id, child_dataset_id
ON dataset_relationship
FOR EACH ROW
WHEN (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.parent_dataset_id LIMIT 1) <> NEW.source_id
  OR (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.child_dataset_id LIMIT 1) <> NEW.source_id
BEGIN
    SELECT RAISE(ABORT, 'relationship datasets must belong to the same source');
END;

CREATE TRIGGER trg_enrichment_definition_same_site_insert
BEFORE INSERT ON organization_enrichment_definition
FOR EACH ROW
WHEN (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.source_dataset_id LIMIT 1) <> NEW.source_id
  OR (NEW.detail_dataset_id IS NOT NULL AND
      (SELECT source_id FROM dataset_definition
       WHERE dataset_definition_id = NEW.detail_dataset_id LIMIT 1) <> NEW.source_id)
  OR (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.output_dataset_id LIMIT 1) <> NEW.source_id
BEGIN
    SELECT RAISE(ABORT, 'enrichment datasets must belong to the same source');
END;

CREATE TRIGGER trg_enrichment_definition_same_site_update
BEFORE UPDATE OF source_id, source_dataset_id, detail_dataset_id,
                 output_dataset_id ON organization_enrichment_definition
FOR EACH ROW
WHEN (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.source_dataset_id LIMIT 1) <> NEW.source_id
  OR (NEW.detail_dataset_id IS NOT NULL AND
      (SELECT source_id FROM dataset_definition
       WHERE dataset_definition_id = NEW.detail_dataset_id LIMIT 1) <> NEW.source_id)
  OR (SELECT source_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.output_dataset_id LIMIT 1) <> NEW.source_id
BEGIN
    SELECT RAISE(ABORT, 'enrichment datasets must belong to the same source');
END;

CREATE TRIGGER trg_enrichment_definition_datasets_differ_insert
BEFORE INSERT ON organization_enrichment_definition
FOR EACH ROW
WHEN NEW.source_dataset_id = NEW.output_dataset_id
  OR NEW.detail_dataset_id = NEW.source_dataset_id
  OR NEW.detail_dataset_id = NEW.output_dataset_id
BEGIN
    SELECT RAISE(ABORT, 'the enrichment output must be a new dataset');
END;

CREATE TRIGGER trg_enrichment_definition_datasets_differ_update
BEFORE UPDATE OF source_dataset_id, detail_dataset_id, output_dataset_id
ON organization_enrichment_definition
FOR EACH ROW
WHEN NEW.source_dataset_id = NEW.output_dataset_id
  OR NEW.detail_dataset_id = NEW.source_dataset_id
  OR NEW.detail_dataset_id = NEW.output_dataset_id
BEGIN
    SELECT RAISE(ABORT, 'the enrichment output must be a new dataset');
END;

-- ------------------------------------------------------------------ 8 · the split is gone

DROP INDEX IF EXISTS ix_site_profile_page;
DROP TABLE site_profile;
DROP TABLE _site_profile_to_source;

PRAGMA legacy_alter_table = OFF;
