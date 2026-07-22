-- =====================================================================
-- 0024 — A HOME FOR THE DETAILS (تفاصيل المنتج من المصدر)
--
-- The WooCommerce connector has emitted enrichment rows since 2026-07-20
-- — colours, cable type, length, brand, warranty, categories, weights,
-- all arriving in the SAME response the price comes from — and ingest
-- rejected every one with "kind enrichment not yet ingestable (Phase 1)".
-- The connector did the work; the warehouse threw it away. Worse, since
-- completed_with_errors landed, those rejections DEGRADE a healthy job.
--
-- This is the SOURCE-LOCAL layer, deliberately: raw per-source details,
-- exactly as the shop printed them. The unified material_attribute_value
-- fills only after the owner curates — same two-layer rule as products.
--
-- UNIQUE (product, code, value): re-crawling refreshes last_seen_at
-- instead of duplicating; a value the shop removes simply stops being
-- refreshed, and nothing is deleted.
-- =====================================================================

CREATE TABLE source_product_attribute (
    source_product_attribute_id INTEGER PRIMARY KEY,
    source_product_id INTEGER NOT NULL
        REFERENCES source_product(source_product_id),
    attribute_code   TEXT NOT NULL,             -- stable key: pa_color, category
    attribute_label  TEXT NOT NULL DEFAULT '',  -- as printed; renames are cosmetic
    raw_value        TEXT NOT NULL,             -- as printed: "100 meters"
    numeric_value    TEXT NOT NULL DEFAULT '',  -- "100" when measurable
    unit_raw         TEXT NOT NULL DEFAULT '',  -- the unit AS WRITTEN
    value_url        TEXT NOT NULL DEFAULT '',
    attribute_group  TEXT NOT NULL DEFAULT '',  -- Attributes | Classification | ...
    lang             TEXT NOT NULL DEFAULT '',
    first_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (source_product_id, attribute_code, raw_value)
);

CREATE INDEX ix_spa_product ON source_product_attribute(source_product_id);

PRAGMA user_version = 24;
