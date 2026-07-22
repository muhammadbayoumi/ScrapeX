-- =====================================================================
-- 0029 — PRODUCT CLASSIFICATION, EVERY LEVEL (تصنيف المنتج بكل مستوياته)
--
-- Owner ruling 2026-07-22: classification is part of the MAIN table —
-- in MADAR (several layers deep) and anywhere else — with every level
-- the source publishes available as its own column.
--
-- Stored ON source_product like brand_raw, because it is product
-- IDENTITY the source states, not an open-ended attribute: one ordered
-- path per product ("Cables > Low voltage > Copper"), levels separated
-- by " > ", plus the site's own id for the leaf category when it has
-- one. The PRODUCT_PRICES contract has carried category_path and
-- category_external_id since the 2026-07-20 widening — this is the
-- warehouse finally keeping what connectors were already allowed to
-- say. The display layer splits the path into per-level columns and
-- gates them per source (a flat-set shop keeps its single Category).
-- =====================================================================

ALTER TABLE source_product ADD COLUMN category_path TEXT NOT NULL DEFAULT '';
ALTER TABLE source_product ADD COLUMN category_external_id TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 29;
