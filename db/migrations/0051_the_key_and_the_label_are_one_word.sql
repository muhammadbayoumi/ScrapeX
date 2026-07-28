-- =====================================================================
-- 0051 — THE KEY AND THE LABEL ARE ONE WORD (batch D)
--
-- docs/column-vocabulary.md states two rules. The second — the name states
-- its language — landed across 0038-0050. This is the first: the key and
-- the heading are the same word, and no display-only word (Record, Status,
-- Source) may stand in for a field's name.
--
-- The whole remaining batch, in ONE migration, because a rename that lands
-- in pieces means the vocabulary is wrong in a different way each week.
--
-- THE PRICE FAMILY reads as a family: price, price_before, price_sale, and
-- (derived, in reports only) price_usd / price_previous / price_min /
-- price_max. `effective_price` was the odd one: the column headed "Price".
--
-- THE TAX FAMILY the same: vat_included -> tax_included, since a VAT-less
-- jurisdiction still has the column, and tax_statement_url -> tax_statement
-- (derived).
--
-- `curation_status` -> `curation`: the heading is "Curation". Its index
-- ix_source_product_curation travels with the column automatically —
-- SQLite rewrites index definitions on RENAME COLUMN — and its CHECK
-- constraint travels too, so the vocabulary of VALUES (inventoried /
-- selected / ignored) is untouched.
--
-- WHAT THIS MIGRATION DOES *NOT* MOVE, deliberately: `region` in
-- tax_rule, the manifest's default_region/extract.regions, and pricekey's
-- own `region` field — they SCOPE a row rather than describe it (0042).
-- And pricekey's parameter names are the HASH's private field names, not
-- column names: build() is keyword-only with one call site, so ingest
-- simply reads a differently-named dict key on the left of each `=`.
-- No digest moves, no PRICE_KEY_VERSION bump, no price period opens.
--
-- =====================================================================
-- THE product_link COLLISION, and the decision taken
-- =====================================================================
-- Two columns target the same name and both are real: `open` is the narrow
-- arrow the Data page puts last, `product_url` is the full URL the export
-- puts beside the official source link. They are one fact — the link to
-- the record on the site — arriving from two seeding paths that never
-- reconciled.
--
-- dataset_field is UNIQUE(source_key, field_key), so after the rename only
-- ONE row per source can survive. Three sources hold both: MADAR,
-- SAMEHGABRIEL, SIKAEGSHOP.
--
-- DECIDED on 0040's precedent, which faced the identical merge for
-- variant_ar/option_label: "the browse row is the one the owner arranged,
-- so it keeps its position and the export-seeded duplicate goes". The
-- `open` row survives; the `product_url` row is deleted. Nothing
-- owner-authored is lost — all eleven rows carry display_name NULL and
-- is_hidden 0, and saved_view is empty.
--
-- ONE CONSEQUENCE, stated because it is a real loss of control: the two
-- rows could be hidden independently, so the arrow could be taken off the
-- table while the URL stayed in the exported sheet. After the merge one
-- row governs both, so hiding Product link hides the arrow AND drops the
-- URL from the Current-View sheet.
-- =====================================================================

DROP VIEW IF EXISTS v_material_price_tracking;

-- ---- the price family --------------------------------------------------
ALTER TABLE price_observation RENAME COLUMN effective_price TO price;
ALTER TABLE price_observation RENAME COLUMN regular_price   TO price_before;
ALTER TABLE price_observation RENAME COLUMN sale_price      TO price_sale;
ALTER TABLE price_period      RENAME COLUMN effective_price TO price;
ALTER TABLE price_period      RENAME COLUMN regular_price   TO price_before;
ALTER TABLE price_period      RENAME COLUMN sale_price      TO price_sale;
ALTER TABLE offer_state       RENAME COLUMN effective_price TO price;

-- ---- the tax family ----------------------------------------------------
ALTER TABLE price_observation RENAME COLUMN vat_included TO tax_included;
ALTER TABLE price_period      RENAME COLUMN vat_included TO tax_included;
ALTER TABLE source_offer      RENAME COLUMN vat_included TO tax_included;

-- ---- the rest ----------------------------------------------------------
ALTER TABLE price_observation RENAME COLUMN official_source_url TO official_source_link;
ALTER TABLE source_product    RENAME COLUMN product_url     TO product_link;
ALTER TABLE source_product    RENAME COLUMN curation_status TO curation;

-- ---- identity_alias: the CHECK names the retired column ----------------
-- The single most dangerous item in this batch. alias_type is a
-- CHECK-constrained enum containing the literal 'product_url', and 108 live
-- rows hold that value. SQLite cannot widen a CHECK in place, so the table
-- is rebuilt — and it MUST be, because changes.ALIAS_FIELDS now writes
-- 'product_link': an alias write that raises is a re-crawl minting a
-- duplicate product and splitting its price history, which is the exact
-- failure 0007 exists to prevent.
PRAGMA foreign_keys = OFF;

-- Copied column-for-column from the live DDL, not retyped from memory:
-- first_seen_at is NOT NULL with a default and retired_at is NULLABLE (it is
-- "when this value stopped being current"), and getting either backwards would
-- rewrite 3,212 rows of identity history.
CREATE TABLE identity_alias_new (
    identity_alias_id INTEGER PRIMARY KEY,
    source_product_id INTEGER NOT NULL REFERENCES source_product(source_product_id),
    alias_type        TEXT NOT NULL
        CHECK (alias_type IN ('external_product_id','external_sku','product_link')),
    alias_value       TEXT NOT NULL,
    first_seen_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    retired_at        TEXT     -- when this value stopped being the current one
);

INSERT INTO identity_alias_new (identity_alias_id, source_product_id, alias_type,
                                alias_value, first_seen_at, retired_at)
SELECT identity_alias_id, source_product_id,
       CASE alias_type WHEN 'product_url' THEN 'product_link' ELSE alias_type END,
       alias_value, first_seen_at, retired_at
FROM identity_alias;

DROP TABLE identity_alias;
ALTER TABLE identity_alias_new RENAME TO identity_alias;

-- BOTH indexes. 0030 rebuilt a table and recreated only one of two, which is
-- the whole reason 0031 had to exist; 0048 inherited that omission by copying
-- the recipe and a regression test caught it. Twice is a pattern, so both are
-- named here explicitly.
CREATE UNIQUE INDEX ux_identity_alias
    ON identity_alias (source_product_id, alias_type, alias_value);
CREATE INDEX ix_identity_alias_value
    ON identity_alias (alias_type, alias_value);

PRAGMA foreign_keys = ON;

-- ---- the saved column layout -------------------------------------------
-- MERGE, not a chain: delete the export-seeded duplicate first, so the
-- surviving browse row can take the name without violating the UNIQUE.
DELETE FROM dataset_field
 WHERE field_key = 'product_url'
   AND source_key IN (SELECT source_key FROM dataset_field WHERE field_key = 'open');

UPDATE dataset_field SET field_key = 'product_link'
 WHERE field_key IN ('open', 'product_url');

UPDATE dataset_field SET field_key = 'price'        WHERE field_key = 'effective_price';
UPDATE dataset_field SET field_key = 'price_before' WHERE field_key = 'regular_price';
UPDATE dataset_field SET field_key = 'price_sale'   WHERE field_key = 'sale_price';
UPDATE dataset_field SET field_key = 'price_usd'      WHERE field_key = 'usd_price';
UPDATE dataset_field SET field_key = 'price_previous' WHERE field_key = 'previous_price';
UPDATE dataset_field SET field_key = 'price_min'      WHERE field_key = 'min_price';
UPDATE dataset_field SET field_key = 'price_max'      WHERE field_key = 'max_price';
UPDATE dataset_field SET field_key = 'tax'            WHERE field_key = 'tax_label';
UPDATE dataset_field SET field_key = 'tax_included'   WHERE field_key = 'vat_included';
UPDATE dataset_field SET field_key = 'tax_statement'  WHERE field_key = 'tax_statement_url';
UPDATE dataset_field SET field_key = 'official_source_link'
 WHERE field_key = 'official_source_url';
UPDATE dataset_field SET field_key = 'curation'       WHERE field_key = 'curation_status';

-- 0008 declared original_name "as first discovered; never rewritten". 0040
-- suspended that for exactly this reason and said so: the column it names no
-- longer exists, so leaving it would preserve a pointer to nothing.
UPDATE dataset_field SET original_name = field_key WHERE original_name <> field_key;

-- ---- the change history -------------------------------------------------
-- 0038 rewrote these; 0047 did not, which is why 87 rows still say the
-- retired `brand_raw`. The Changes feed reads field_key by name
-- (changes._FIELD_LABELS, falling back to the key with underscores turned to
-- spaces), so leaving history unrewritten makes old rows render under one
-- vocabulary beside new rows rendering under another. 0038's rule wins, and
-- brand_raw is swept up with them rather than left as a third vocabulary.
UPDATE change_event SET field_key = 'product_link' WHERE field_key = 'product_url';
UPDATE change_event SET field_key = 'price'        WHERE field_key = 'effective_price';
UPDATE change_event SET field_key = 'price_before' WHERE field_key = 'regular_price';
UPDATE change_event SET field_key = 'price_sale'   WHERE field_key = 'sale_price';
UPDATE change_event SET field_key = 'tax_included' WHERE field_key = 'vat_included';
UPDATE change_event SET field_key = 'curation'     WHERE field_key = 'curation_status';
UPDATE change_event SET field_key = 'brand'        WHERE field_key = 'brand_raw';

-- ---- the view, rebuilt on the new vocabulary ----------------------------
CREATE VIEW v_material_price_tracking AS
SELECT
    po.business_date                AS observation_date,
    ss.source_name                  AS source_name,
    ss.source_name_ar               AS source_name_ar,
    m.material_id                   AS material_id,
    COALESCE(m.material_name, m.material_name_ar) AS material_name,
    mv.variant_id                   AS variant_id,
    mv.variant_name                 AS variant_name,
    sv.external_sku                 AS external_sku,
    sp.source_product_id            AS source_product_id,
    sv.source_variant_id            AS source_variant_id,
    COALESCE(b.brand_name, sp.brand)    AS brand,
    sp.brand_ar                     AS brand_ar,
    mv.spec_fingerprint             AS specification_summary,
    so.country_code_alpha2          AS country_code_alpha2,
    po.price_before                 AS price_before,
    po.price_sale                   AS price_sale,
    po.price                        AS price,
    po.currency                     AS currency,
    su.unit_code                    AS selling_unit,
    so.basis_quantity               AS basis_quantity,
    po.tax_included                 AS tax_included,
    po.availability                 AS availability,
    po.stock_quantity               AS stock_quantity,
    sp.product_link                 AS product_link,
    po.snapshot_id                  AS snapshot_id
FROM price_observation po
JOIN source_offer so        ON so.offer_id = po.offer_id
JOIN source_variant sv      ON sv.source_variant_id = so.source_variant_id
JOIN source_product sp      ON sp.source_product_id = sv.source_product_id
JOIN source_site ss         ON ss.source_id = sp.source_id
JOIN source_variant_match svm ON svm.source_variant_id = sv.source_variant_id
                             AND svm.review_status = 'approved' AND svm.valid_to IS NULL
JOIN material_variant mv    ON mv.variant_id = svm.variant_id
JOIN material m             ON m.material_id = mv.material_id
LEFT JOIN brand b           ON b.brand_id = m.brand_id
LEFT JOIN selling_unit su   ON su.selling_unit_id = so.selling_unit_id
WHERE po.price_observation_id = COALESCE(
    (SELECT p2.price_observation_id FROM price_observation p2
     WHERE p2.offer_id = po.offer_id AND p2.provenance = 'observed'
     ORDER BY p2.business_date DESC, p2.price_observation_id DESC LIMIT 1),
    po.price_observation_id);

PRAGMA user_version = 51;
