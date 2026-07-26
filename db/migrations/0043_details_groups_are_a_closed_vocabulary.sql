-- =====================================================================
-- 0043 — THE DETAILS PANEL HAS FIVE GROUPS, AND ONLY FIVE
--
-- Owner ruling 2026-07-26: a detail belongs to one of
--
--     Description · Specifications · Attachments · More information · Media
--
-- and anything a future site publishes is filed under those. Until now each
-- connector invented its own headings, so one warehouse held ten:
-- Specifications AND Specs on the same source, plus Measurements,
-- Attributes, Classification and Filters. A reader learning where to look
-- had to learn it again per site.
--
-- WHY `Filters` NEEDS A COLUMN, NOT A GROUP. It was doing two jobs at
-- once. As a heading it named nothing a reader recognises; as a MECHANISM
-- it is how the per-source filter columns are found — reports selects
-- `attribute_group = 'Filters'` to build the columns that let the owner
-- slice a table the way the shop slices its own listing. Folding it into
-- Specifications without moving that fact would have silently deleted the
-- feature. So the mechanism becomes what it always was — a property of the
-- row, not a place to file it — and the group is free to be one of five.
--
-- THE MAPPING, and the one judgement in it:
--   Specs, Measurements, Attributes, Filters -> Specifications
--     A measurement, an attribute and a facet are all stated properties of
--     the product. Filters additionally sets is_site_filter.
--   Classification                           -> More information
--     Where the site FILES a product is information about it, not a
--     property of it.
--   Description, Attachments, Media, More information, Specifications
--     already speak the vocabulary and are untouched.
-- =====================================================================

ALTER TABLE source_product_attribute
    ADD COLUMN is_site_filter INTEGER NOT NULL DEFAULT 0;

UPDATE source_product_attribute SET is_site_filter = 1
 WHERE attribute_group = 'Filters';

UPDATE source_product_attribute
   SET attribute_group = 'Specifications'
 WHERE attribute_group IN ('Specs', 'Measurements', 'Attributes', 'Filters');

UPDATE source_product_attribute
   SET attribute_group = 'More information'
 WHERE attribute_group = 'Classification';

-- Anything a connector left blank is information the site stated without
-- saying where it belongs, which is exactly what the catch-all is for.
UPDATE source_product_attribute
   SET attribute_group = 'More information'
 WHERE COALESCE(TRIM(attribute_group), '') = '';

CREATE INDEX IF NOT EXISTS ix_source_product_attribute_site_filter
    ON source_product_attribute (source_product_id, is_site_filter);

PRAGMA user_version = 43;
