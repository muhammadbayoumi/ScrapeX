-- =====================================================================
-- 0040 — THE SAVED COLUMN LAYOUTS SPEAK THE NEW VOCABULARY
--
-- dataset_field.field_key is row DATA holding a DISPLAY column name, so no
-- rename reached it. ensure_fields is additive by design and apply_schema
-- registers the export header on the first export after the sweep, so
-- skipping this would leave every source's saved layout pointing at keys
-- the code no longer emits — and it fails SILENTLY in both directions:
-- app.py excludes stale keys from absent_columns (they are no longer in
-- BROWSE_COLUMNS) so the page never mentions them, while grid.js renders
-- every registered field with no cross-check, so the orphan appears in
-- Choose Columns as "Product Name En" (the humanising fallback) and
-- toggling it POSTs 200 with rowcount 1 and changes nothing on screen.
--
-- THIS IS NOT A PURE RENAME. MADAR and ARAMCO_FUEL_SA each hold a
-- `variant_ar` row seeded from the EXPORT header, and MADAR also holds an
-- `option_label` row seeded from the BROWSE list — two rows, one fact, two
-- names, on a source that both browses and exports it. So the first
-- statement is a MERGE, not a chain: the browse row is the one the owner
-- arranged, so it keeps its position and the export-seeded duplicate goes.
--
-- Everything else is the same chain order as 0038 and for the same reason:
-- Arabic to _ar first (target free), then English to the base.
-- ux_dataset_field(source_key, field_key) is UNIQUE, and four sources hold
-- both sides of the name pair, four both sides of category, and MADAR both
-- sides of levels 1-3.
--
-- WHAT IS NOT TOUCHED: MADAR's ~60 site-named rows — `Width (mm)`,
-- `Manufacturer`, «التيار المقنّن (بالأمبير)». Those are the SITE's own
-- vocabulary, not ours, and are outside this sweep by the same rule that
-- leaves tests/fixtures byte-faithful.
-- =====================================================================

DELETE FROM dataset_field
 WHERE field_key = 'variant_ar'
   AND EXISTS (SELECT 1 FROM dataset_field o
                WHERE o.source_key = dataset_field.source_key
                  AND o.field_key  = 'option_label');
UPDATE dataset_field SET field_key = 'variant_ar' WHERE field_key = 'option_label';

UPDATE dataset_field SET field_key = 'product_name_ar' WHERE field_key = 'product_name';
UPDATE dataset_field SET field_key = 'product_name'    WHERE field_key = 'product_name_en';
UPDATE dataset_field SET field_key = 'category_ar'     WHERE field_key = 'category';
UPDATE dataset_field SET field_key = 'category'        WHERE field_key = 'category_en';

UPDATE dataset_field SET field_key = 'category_l1_ar'  WHERE field_key = 'category_l1';
UPDATE dataset_field SET field_key = 'category_l1'     WHERE field_key = 'category_en_l1';
UPDATE dataset_field SET field_key = 'category_l2_ar'  WHERE field_key = 'category_l2';
UPDATE dataset_field SET field_key = 'category_l2'     WHERE field_key = 'category_en_l2';
UPDATE dataset_field SET field_key = 'category_l3_ar'  WHERE field_key = 'category_l3';
UPDATE dataset_field SET field_key = 'category_l3'     WHERE field_key = 'category_en_l3';
UPDATE dataset_field SET field_key = 'category_l4_ar'  WHERE field_key = 'category_l4';
UPDATE dataset_field SET field_key = 'category_l4'     WHERE field_key = 'category_en_l4';
UPDATE dataset_field SET field_key = 'category_l5_ar'  WHERE field_key = 'category_l5';
UPDATE dataset_field SET field_key = 'category_l5'     WHERE field_key = 'category_en_l5';
UPDATE dataset_field SET field_key = 'category_l6_ar'  WHERE field_key = 'category_l6';
UPDATE dataset_field SET field_key = 'category_l6'     WHERE field_key = 'category_en_l6';
UPDATE dataset_field SET field_key = 'category_l7_ar'  WHERE field_key = 'category_l7';
UPDATE dataset_field SET field_key = 'category_l7'     WHERE field_key = 'category_en_l7';
UPDATE dataset_field SET field_key = 'category_l8_ar'  WHERE field_key = 'category_l8';
UPDATE dataset_field SET field_key = 'category_l8'     WHERE field_key = 'category_en_l8';
UPDATE dataset_field SET field_key = 'category_l9_ar'  WHERE field_key = 'category_l9';
UPDATE dataset_field SET field_key = 'category_l9'     WHERE field_key = 'category_en_l9';
UPDATE dataset_field SET field_key = 'category_l10_ar' WHERE field_key = 'category_l10';
UPDATE dataset_field SET field_key = 'category_l10'    WHERE field_key = 'category_en_l10';

-- original_name is the label fallback and 0008 documents it as "as first
-- discovered; never rewritten" — just as it documents field_key as an
-- IMMUTABLE identity. This migration is the one event that rewrites both,
-- because the name a column was discovered under no longer exists anywhere
-- in the product, and leaving it stale would relabel every column in Choose
-- Columns with the retired word. Suspending a declared invariant silently is
-- what turns a schema comment into a lie, so it is said here in full.
UPDATE dataset_field SET original_name = field_key WHERE original_name <> field_key;

PRAGMA user_version = 40;
