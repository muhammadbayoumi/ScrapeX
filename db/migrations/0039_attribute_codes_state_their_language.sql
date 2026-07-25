-- =====================================================================
-- 0039 — AN ATTRIBUTE CODE STATES ITS LANGUAGE TOO
--
-- source_product_attribute.attribute_code is row DATA, so 0038's RENAME
-- COLUMN could not reach it. sika stores every spec, description and
-- keyword twice — `description` in Arabic and `description_en` in English —
-- which is the same inversion 0038 just deleted from the columns, in the
-- one place a column rename cannot go.
--
-- THE RULE IS THE DATA'S OWN, NOT A SUFFIX HEURISTIC. Two rules were
-- available and both are wrong:
--   * "the row has an _en twin" leaves the inversion in place: all nine of
--     sika's _en codes DO have their base present, so a rule looking for
--     that finds every row and decides nothing.
--   * "anything unsuffixed is Arabic" stamps a language claim on 1,129
--     madar/samehgabriel rows the warehouse never made a claim about.
--
-- `lang` is declared on PRECISELY the rows that should move and on no
-- others — 1,092 rows, 18 codes, one source — so the rule is WHERE lang IN
-- ('ar','en'). No source list to maintain and no assertion about a language
-- nobody stated.
--
-- ARABIC FIRST, then English, for the same reason as 0038: the Arabic row
-- vacates `description` before the English row claims it. The collision
-- check against UNIQUE(source_product_id, attribute_code, raw_value) was
-- run on a copy of the live warehouse and returns 0.
--
-- THE CONNECTOR MOVES IN THE SAME COMMIT OR THIS IS UNDONE AND DOUBLED.
-- ingest's attribute write is INSERT ... ON CONFLICT DO UPDATE and never
-- deletes, so migrating the rows without changing custom_json would have
-- the next sika crawl re-create all nine old codes BESIDE the nine new
-- ones: 87 products showing every description, spec and keyword twice,
-- under two vocabularies, in the record panel.
--
-- DELIBERATELY NOT DONE: madar's 534 `description` + 577 `short_description`
-- rows and samehgabriel's 18 keep their unmarked codes, and under the new
-- rule an unmarked name asserts English while ~486 and ~499 of madar's
-- respectively contain Arabic script. That is a STATED, ACCEPTED debt. The
-- warehouse holds no evidence to decide them — lang is '' on every one,
-- they have no _en twin, and most are MIXED — so guessing would commit the
-- exact error this rule exists to prevent, in the rule's own name. Closing
-- it is a madar connector change (fill lang per row) followed by a second,
-- identical lang-driven re-code. Its own task.
-- =====================================================================

UPDATE source_product_attribute
   SET attribute_code = attribute_code || '_ar'
 WHERE lang = 'ar' AND attribute_code NOT LIKE '%\_ar' ESCAPE '\';

UPDATE source_product_attribute
   SET attribute_code = substr(attribute_code, 1, length(attribute_code) - 3)
 WHERE lang = 'en' AND attribute_code LIKE '%\_en' ESCAPE '\';

PRAGMA user_version = 39;
