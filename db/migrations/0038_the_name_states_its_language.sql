-- =====================================================================
-- 0038 — THE NAME STATES ITS LANGUAGE
--
-- Owner's rule, approved 2026-07-25: "column names should always reflect
-- their content in both display and storage." English is the primary
-- display language, so the UNMARKED name is English and Arabic is marked
-- `_ar`. A source that publishes only Arabic fills only the `_ar` column
-- and its heading says so, because the label describes the content, not
-- the presence of a counterpart.
--
-- The warehouse said the opposite. `source_product.source_name` held the
-- site's Arabic name and `source_name_en` the English one, so the unmarked
-- column — the one a reader assumes needs no explanation — was the Arabic
-- one. Every page, export and Google sheet inherited that.
--
-- This migration renames ONLY. No value moves, no row is touched, nothing
-- the owner sees changes: the wire still says `product_name` and still
-- means Arabic, and ingest now routes it to a column CALLED product_name_ar.
-- The meaning flips later, in its own commit, behind a payload version bump.
--
-- WHY THE VIEW IS DROPPED FIRST. SQLite does not fail when a RENAME COLUMN
-- reaches a column a view selects — it REWRITES the view body and keeps the
-- alias, so `ss.source_name AS source_name` silently becomes
-- `ss.source_name_ar AS source_name` and the view goes on publishing Arabic
-- under an English name, with no error. The view returns 0 rows today
-- (source_variant_match is empty), so nothing would ever have caught it.
--
-- WHY THE ORDER IS FORCED. Every pair is a chain: Arabic to `_ar` first
-- (the target is free), then English to the base (now vacated). Reversed,
-- SQLite raises `duplicate column name` — which is the loud failure you
-- want if someone reorders this. There is no cycle, so no parking name.
--
-- WHAT RENAME COLUMN DOES NOT MOVE. It moves the values, so
-- source_name_ar='السويد' / source_name='Alsweed' without touching a row.
-- It moves NOTHING for anything that stores a column name AS DATA:
-- change_event.field_key (handled below), dataset_field.field_key (0040),
-- source_product_attribute.attribute_code (0039), and the export's _about
-- tab labels (code). Each is handled explicitly or deliberately left.
--
-- WHAT THE CONSTRAINTS DO. RENAME COLUMN carries NOT NULL with the column,
-- so source_site's NOT NULL now sits on source_name_ar — the warehouse still
-- demands an ARABIC site name, which is the opposite of where the manifest is
-- heading (English required, Arabic optional). It is not corrected here
-- because dropping NOT NULL needs a full table rebuild, and ingest writes ''
-- rather than NULL for an absent name, so nothing breaks. Left as a stated
-- inheritance, to be settled when the manifest's requiredness inverts.
--
-- NOT TOUCHED, AND EACH WOULD BE A LIE IF IT WERE:
--   * option_fingerprint — the variant identity fallback, Arabic-derived by
--     construction (`color=أحمر`) and frozen by CONTRACT_VERSION 1.
--     Re-deriving it from the English axes re-keys every variant, mints
--     duplicates and splits every price history, while the contract version
--     stays at 1 and nothing complains.
--   * The General database's original_name / display_name. Those hold the
--     CRAWLED SITE's own field names as first discovered. Marking them with
--     our vocabulary would be an assertion about someone else's data.
--   * db/schema.sql and 0033-0037 — the checksum ledger. A fresh database
--     reaches this shape by applying 0001 -> 0038 in order; editing an
--     applied file raises "checksum changed" on every existing install.
-- =====================================================================

DROP VIEW IF EXISTS v_material_price_tracking;   -- FIRST. See the header.

ALTER TABLE source_site    RENAME COLUMN source_name      TO source_name_ar;
ALTER TABLE source_site    RENAME COLUMN source_name_en   TO source_name;

ALTER TABLE source_product RENAME COLUMN source_name      TO product_name_ar;
ALTER TABLE source_product RENAME COLUMN source_name_en   TO product_name;
ALTER TABLE source_product RENAME COLUMN category_path    TO category_path_ar;
ALTER TABLE source_product RENAME COLUMN category_path_en TO category_path;

-- Kept, not dropped, and renamed to say whose claim it is: this is the
-- CONNECTOR's own statement about which language its extraction ran in. It
-- is what 0039's attribute rule leans on, and changes.py tracks it.
ALTER TABLE source_product RENAME COLUMN name_lang        TO product_name_lang;

ALTER TABLE source_variant RENAME COLUMN option_label     TO variant_ar;
ALTER TABLE source_variant RENAME COLUMN raw_options_json TO variant_axes_ar;

-- The unified layer is unpopulated (0 rows each). Free now, expensive after
-- the matching layer is used — and the view is rebuilt once instead of twice.
ALTER TABLE material             RENAME COLUMN material_name_en TO material_name;
ALTER TABLE selling_unit         RENAME COLUMN name_en TO name;
ALTER TABLE attribute_definition RENAME COLUMN name_en TO name;

-- The view, recreated over the new names. Three edits from 0027:
--   * source_name now reads the ENGLISH column, and the Arabic one is
--     published beside it under a name that says so. Deliberately NO
--     COALESCE: falling back to Arabic under an English alias is the exact
--     violation this migration exists to delete.
--   * material_name_en -> material_name (mechanical; the table is empty).
--   * variant_description -> variant_name. "description" was a display-only
--     word standing in for a field name.
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
    COALESCE(b.brand_name, sp.brand_raw) AS brand,
    mv.spec_fingerprint             AS specification_summary,
    so.region                       AS region,
    po.regular_price                AS regular_price,
    po.sale_price                   AS sale_price,
    po.effective_price              AS effective_price,
    po.currency                     AS currency,
    su.unit_code                    AS selling_unit,
    so.basis_quantity               AS basis_quantity,
    po.vat_included                 AS vat_included,
    po.availability                 AS availability,
    po.stock_quantity               AS stock_quantity,
    sp.product_url                  AS product_url,
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
    (SELECT p3.price_observation_id FROM price_observation p3
     WHERE p3.offer_id = po.offer_id AND p3.provenance = 'reported'
     ORDER BY p3.business_date DESC, p3.price_observation_id DESC LIMIT 1)
);

-- change_event.field_key stores the STORED COLUMN name, written by ingest's
-- product_field_diffs. Zero rows name one of these today, so this is free —
-- but only until a source renames a product, after which the change feed
-- would read in two vocabularies with nothing to separate them.
UPDATE change_event SET field_key = 'product_name_ar'   WHERE field_key = 'source_name';
UPDATE change_event SET field_key = 'product_name'      WHERE field_key = 'source_name_en';
UPDATE change_event SET field_key = 'category_path_ar'  WHERE field_key = 'category_path';
UPDATE change_event SET field_key = 'category_path'     WHERE field_key = 'category_path_en';
UPDATE change_event SET field_key = 'product_name_lang' WHERE field_key = 'name_lang';

PRAGMA user_version = 38;
