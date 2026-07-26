-- =====================================================================
-- 0042 — `region` IS A COUNTRY CODE, SO IT SAYS SO
--
-- Rule 1: the key and the label are the same word. `region` was headed
-- "Country" in the table while the export ALSO had a `country` column
-- holding the spelled-out name, so one concept wore two names and one name
-- covered two concepts. It holds an ISO 3166-1 alpha-2 code, and now it is
-- called that.
--
-- WHY THIS COSTS NOTHING, contrary to the deferral note it replaces.
-- The concern was that `region` is inside pricekey.IDENTITY_FIELDS and is
-- hashed BY NAME, so renaming it would drop every stored row's entry on
-- read, make comparable() false, and open a fresh price period on every
-- affected offer. That is true of pricekey's OWN field name — and this
-- migration does not touch it. `pricekey.build()` is keyword-only and has
-- exactly one call site; the column feeds its `region=` parameter and the
-- hash vocabulary stays frozen, exactly as record_hash's does. No
-- PRICE_KEY_VERSION bump, no re-baseline, no price period disturbed.
--
-- DELIBERATELY NOT RENAMED, because they are a different concept: the
-- manifest's `default_region` and `extract.regions`, and `tax_rule.region`.
-- Those SCOPE a source or a rule ("produce rows for these countries",
-- "this evidence covers that country"); they are not a column of data
-- describing one row. Renaming them would be churn that helps no reader.
--
-- The view is dropped first for the same reason as 0038: SQLite rewrites a
-- view's body around a renamed column and keeps the alias, silently.
-- =====================================================================

DROP VIEW IF EXISTS v_material_price_tracking;

ALTER TABLE source_offer RENAME COLUMN region TO country_code_alpha2;

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
    so.country_code_alpha2          AS country_code_alpha2,
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

-- The saved column layouts follow, same as 0040.
UPDATE dataset_field SET field_key = 'country_code_alpha2' WHERE field_key = 'region';
UPDATE dataset_field SET original_name = field_key WHERE original_name <> field_key;

PRAGMA user_version = 42;
