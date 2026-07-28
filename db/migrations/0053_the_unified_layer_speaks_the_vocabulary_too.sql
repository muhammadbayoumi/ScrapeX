-- =====================================================================
-- 0053 — THE UNIFIED LAYER SPEAKS THE VOCABULARY TOO (E4, E5)
--
-- Three columns in the not-yet-populated unified layer break rules the
-- source-local layer has now finished obeying. Every one of these tables
-- holds ZERO rows today, which is the whole reason to do it now: the same
-- change costs a data migration, a re-verification and an owner's
-- re-arrangement once they fill.
--
-- E4 — THE NAME STATES ITS LANGUAGE (0039's rule, unapplied here):
--   classification_scheme.scheme_name -> scheme_name_ar
--   classification_node.node_name     -> node_name_ar
-- and each gains its unmarked English twin. These will hold the SAME kind of
-- content as source_product.category_path / category_path_ar, which already
-- carries the mark — so leaving them unmarked would put two spellings of one
-- idea in one warehouse, and the unified layer is precisely where the two
-- meet.
--
-- E5 — ONE WORD, ONE MEANING:
--   material_variant.variant_name -> variant_label
-- `variant` now means the source-local variation of a product
-- (source_variant.variant, 0038), and material_variant.variant_name is a
-- different thing entirely: the CURATED name of a variant of a material in
-- the owner's own catalogue. Two meanings behind one word is how a join gets
-- written between columns that do not correspond, and the reader who makes
-- that mistake will be reading a query, not this comment.
--
-- v_material_price_tracking DOES select mv.variant_name, so the view is
-- dropped first and rebuilt from 0051's body with only that line changed.
-- SQLite silently rewrites a view around a renamed column and keeps the old
-- alias, which is the trap 0038 documented and 0047 had to respect.
-- =====================================================================

DROP VIEW IF EXISTS v_material_price_tracking;

ALTER TABLE classification_scheme RENAME COLUMN scheme_name TO scheme_name_ar;
ALTER TABLE classification_scheme ADD COLUMN scheme_name TEXT;

ALTER TABLE classification_node RENAME COLUMN node_name TO node_name_ar;
ALTER TABLE classification_node ADD COLUMN node_name TEXT;

ALTER TABLE material_variant RENAME COLUMN variant_name TO variant_label;

CREATE VIEW v_material_price_tracking AS
SELECT
    po.business_date                AS observation_date,
    ss.source_name                  AS source_name,
    ss.source_name_ar               AS source_name_ar,
    m.material_id                   AS material_id,
    COALESCE(m.material_name, m.material_name_ar) AS material_name,
    mv.variant_id                   AS variant_id,
    mv.variant_label                AS variant_label,
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

PRAGMA user_version = 53;
