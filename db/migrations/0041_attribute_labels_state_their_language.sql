-- =====================================================================
-- 0041 — THE ATTRIBUTE LABEL STATES ITS LANGUAGE TOO
--
-- 0039 moved every attribute CODE onto the new vocabulary and left the
-- LABEL behind, so the record panel and the details export ended up saying
-- the exact opposite of what they hold. Owner-reported, from a sika export:
--
--     code=description     lang=en   label='Description (EN)'
--     code=description_ar  lang=ar   label='Description'
--
-- The code is right and the label is inverted: the row that holds ENGLISH
-- is marked "(EN)" — a marker the vocabulary retired, because the unmarked
-- name IS English — while the row that holds ARABIC reads plainly
-- "Description". A reader trusts the label, which is the one part of the
-- pair that is written for a person.
--
-- Scoped by `lang`, the same evidence 0039 used, and narrowed further for
-- the Arabic side: only the labels WE author are marked. attr_1..attr_6
-- carry the SHOP's own words («اللون», 'color') and are named by the site,
-- not by this vocabulary — appending "(AR)" to «اللون» would be our
-- vocabulary talking over someone else's.
-- =====================================================================

UPDATE source_product_attribute
   SET attribute_label = TRIM(REPLACE(attribute_label, '(EN)', ''))
 WHERE lang = 'en' AND attribute_label LIKE '%(EN)%';

UPDATE source_product_attribute
   SET attribute_label = attribute_label || ' (AR)'
 WHERE lang = 'ar'
   AND attribute_code IN ('description_ar', 'keywords_ar', 'full_description_ar')
   AND attribute_label NOT LIKE '%(AR)%';

PRAGMA user_version = 41;
