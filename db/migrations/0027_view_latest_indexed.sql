-- =====================================================================
-- 0027 — THE VIEW'S LATEST-PICK GAINS AN INDEX-SERVABLE SHAPE
--
-- Same meaning as 0021 (observed outranks reported, then newest
-- business_date), different mechanics: ORDER BY (provenance='observed')
-- DESC is an EXPRESSION no index can serve, and the ten-year backfill
-- made that lethal — 136k observations x a ~500-row sort each froze
-- every consumer of this view for seconds (measured live on the Data
-- page's twin query: 6.3s -> 0.06s, identical results). Two probes on
-- ix_price_obs_provenance (offer_id, provenance, business_date DESC)
-- replace the sort; COALESCE keeps the reported fallback for offers
-- with no observation at all.
-- =====================================================================

-- The probe's full ORDER BY is (business_date DESC, price_observation_id
-- DESC); without the id in the index, every probe still builds a temp
-- b-tree for the last term. Rebuilt under the same name with the
-- tiebreak column so the pick is a pure index seek.
DROP INDEX IF EXISTS ix_price_obs_provenance;
CREATE INDEX ix_price_obs_provenance
    ON price_observation (offer_id, provenance, business_date DESC,
                          price_observation_id DESC);

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
WHERE po.price_observation_id = COALESCE(
    (SELECT p2.price_observation_id FROM price_observation p2
     WHERE p2.offer_id = po.offer_id AND p2.provenance = 'observed'
     ORDER BY p2.business_date DESC, p2.price_observation_id DESC LIMIT 1),
    (SELECT p3.price_observation_id FROM price_observation p3
     WHERE p3.offer_id = po.offer_id AND p3.provenance = 'reported'
     ORDER BY p3.business_date DESC, p3.price_observation_id DESC LIMIT 1)
);

PRAGMA user_version = 27;
