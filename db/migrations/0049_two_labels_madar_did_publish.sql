-- =====================================================================
-- 0049 — THE TWO LABELS MADAR DID PUBLISH
--
-- 422 madar attribute rows carry their bare CODE where the panel should
-- print the shop's word. Reading them apart splits into two unrelated
-- problems, and only one of them is a defect on our side:
--
--   420 rows / 20 codes (voltage, wattage, cct, amperage, gangs...) are
--   unlabelled SYMMETRICALLY -- both store views, in exactly equal
--   numbers. madar publishes no human word for them at all: neither
--   customAttributeMetadataV2 nor the facet aggregations answer, in
--   either language. This migration does NOT touch them. Inventing a
--   label would put text on the page the site never wrote, which is the
--   owner's standing rule, and his ruling here was to accept the code and
--   make the CRAWL say so instead -- done in the connector, which now
--   names the codes a store declined to label rather than staying silent
--   (the silence is why this survived two "fixed" crawls unnoticed).
--
--   2 rows are a genuine defect, and are all this migration repairs.
--   `length_mm_ar` and `thickness_mm_ar` on source_product_id 127
--   (SKU 1604040030, "SANDWICH PANEL 4 MTR * 3 CM") are frozen at
--   2026-07-26 while every other row was rewritten on 2026-07-28. The
--   product has not appeared in the census since, so no crawl can reach
--   them, and _retire_superseded_attributes only touches (product, code)
--   pairs a run RESTATED -- so nothing reaches them either.
--
-- NOTHING IS INVENTED HERE. madar publishes «الطول (ملم)» for
-- length_mm_ar on 84 other rows and «السماكة (مم)» for thickness_mm_ar
-- on 71. This copies the shop's own word onto the two rows a stalled
-- product left behind -- restoring what the site says, not authoring it.
--
-- Scoped by the defect, not by the code: WHERE the label still equals the
-- code. If a later crawl repairs them first, this updates nothing.
-- =====================================================================

UPDATE source_product_attribute
   SET attribute_label = 'الطول (ملم)'
 WHERE attribute_code = 'length_mm_ar'
   AND attribute_label = 'length_mm';

UPDATE source_product_attribute
   SET attribute_label = 'السماكة (مم)'
 WHERE attribute_code = 'thickness_mm_ar'
   AND attribute_label = 'thickness_mm';

PRAGMA user_version = 49;
