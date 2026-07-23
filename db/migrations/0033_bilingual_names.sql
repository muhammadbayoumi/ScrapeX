-- =====================================================================
-- 0033 — BOTH LANGUAGES, EXTRACTED ONCE (الاسمان معًا، استخراج واحد)
--
-- Owner ruling: a bilingual site is extracted in BOTH languages in one
-- crawl, and the table lets the reader flip AR/EN without re-extracting.
-- The contract has carried product_name_en and lang since the 2026-07-20
-- widening; madar's en_SA store view answers English names for the same
-- uids (verified live: "اسمنت الرياض" -> "Riyadh Cement"). This stores
-- them: the English name beside the primary one, and which language the
-- primary is in, when the connector states it. Kept SEPARATE, never
-- merged — the display layer chooses, the warehouse remembers both.
-- =====================================================================

ALTER TABLE source_product ADD COLUMN source_name_en TEXT NOT NULL DEFAULT '';
ALTER TABLE source_product ADD COLUMN name_lang TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 33;
