-- =====================================================================
-- 0021 — THE VIEW'S "CURRENT PRICE" MUST BE WHAT WE SAW, NOT WHAT WAS
-- LAST INSERTED
--
-- v_material_price_tracking picked each offer's row by
-- ORDER BY observed_at DESC, price_observation_id DESC. observed_at is
-- the CRAWL timestamp, identical for every row one crawl lands — today's
-- observed price and the source's backfilled year-ago anchors alike — so
-- the id tiebreak crowned the LAST INSERT. For GPP that was the oldest
-- reported anchor: Egypt diesel published 15.5 EGP dated 2025 while the
-- source said 20.5 today.
--
-- The honest order, same as reports.py uses live: an OBSERVED row always
-- outranks a reported claim; among candidates the newest business_date
-- wins; the id only breaks genuine same-day ties toward the newest row.
-- A reported row may speak only for an offer that has no observation at
-- all — a pure --history backfill — and then the newest-dated claim is
-- truthfully the best known price.
-- =====================================================================

DROP VIEW IF EXISTS v_material_price_tracking;

CREATE VIEW v_material_price_tracking AS
SELECT
    po.business_date                AS observation_date,
    ss.source_name                  AS source_name,
    m.material_id                   AS material_id,
    COALESCE(m.material_name_en, m.material_name_ar) AS material_name,
    mv.variant_id                   AS variant_id,
    mv.variant_name                 AS variant_description,
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
WHERE po.price_observation_id = (
    SELECT po2.price_observation_id FROM price_observation po2
    WHERE po2.offer_id = po.offer_id
    ORDER BY (po2.provenance = 'observed') DESC, po2.business_date DESC,
             po2.price_observation_id DESC LIMIT 1
);

PRAGMA user_version = 21;
