-- ============================================================================
-- Migration 0010 — expose the offer's region in the flat publish view.
--
-- The view joined source_offer but selected only basis_quantity from it, so the
-- country never reached the published table. For a commodity source that is the
-- row's identity: ~180 countries share one material, so without region every row
-- reads identically except for the price.
--
-- The schema comment on source_offer.region already stated the intent — "TEXT by
-- design so it joins feed_assignment.region directly" — the view just never
-- surfaced it.
-- ============================================================================

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
    so.region                       AS region,          -- NEW: the country/market
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
    ORDER BY po2.observed_at DESC, po2.price_observation_id DESC LIMIT 1
);

PRAGMA user_version = 10;
