-- =====================================================================
-- 0044 — THE OWNER DECIDES WHICH DETAIL BECOMES A COLUMN
--
-- The owner asked whether the exported tables are not already assembled
-- from the system's own tables, and he was right — more right than the
-- answer he was first given. Measured today:
--
--     MADAR       120 columns = 56 declared + 64 ASSEMBLED
--     SIKAEGSHOP   56 columns = 56 declared +  0 assembled
--
-- Every one of those 64 — `Width (mm)`, `Manufacturer`, «التيار المقنّن
-- (بالأمبير)» — is not a stored column. They are ROWS in
-- source_product_attribute, the details table itself, pivoted into columns
-- at read time. The machine that turns a detail into a column already runs
-- in production.
--
-- So why does sika get none of them? One condition:
--
--     WHERE ss.source_key = ? AND spa.is_site_filter = 1
--
-- Magento publishes its facet list, so madar's rows are flagged and rise.
-- Sika's shop publishes no facets, so nothing of its 18 attribute codes is
-- ever flagged. WHICH DETAIL BECOMES A COLUMN IS DECIDED BY THE SHOP, and
-- the owner has no say in it. That is the whole defect: not a missing
-- mechanism, a missing voice.
--
-- This table is that voice. A promotion is per (source, attribute code),
-- because a fact worth a column on one site is noise on another, and it is
-- REVERSIBLE by deleting the row — the opposite direction (column back to
-- details) already works by hiding the column.
--
-- Deliberately NOT a column on dataset_field. That table registers DISPLAY
-- columns and its field_key is a display key; an attribute code is the
-- SHOP's word for one of its own facts. Storing the promotion beside the
-- layout would make one table answer two questions, and the vocabulary work
-- that just landed exists precisely to stop that.
-- =====================================================================

CREATE TABLE IF NOT EXISTS source_attribute_promotion (
    source_key      TEXT NOT NULL,
    attribute_code  TEXT NOT NULL,
    promoted_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    PRIMARY KEY (source_key, attribute_code)
);

PRAGMA user_version = 44;
