-- =====================================================================
-- 0032 — A VARIANT CAN BE SUPERSEDED (تقاعد الصف البديل عن المنتج)
--
-- When a connector could not see a product's variations it emitted ONE
-- stand-in row whose variant id IS the product id, priced at whatever
-- the listing showed — for WooCommerce, the price RANGE's low end. The
-- per-variation upgrade then minted the real variants BESIDE that
-- stand-in, and nothing ever retired it: the low end kept posing as a
-- current price forever, on the Data page and in the export (found by
-- the adversarial review, reproduced by execution against a warehouse
-- with v1 data).
--
-- status names the lifecycle: 'active' is the default and the only
-- state read paths show; ingest sets 'superseded' when a run publishes
-- REAL variants for the product and no longer publishes the stand-in,
-- and flips it back to 'active' (with a change event both ways) if the
-- source ever publishes it again — the fallback path does exactly that
-- when every variation fetch fails.
-- =====================================================================

ALTER TABLE source_variant ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'superseded'));

PRAGMA user_version = 32;
