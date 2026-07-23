-- =====================================================================
-- 0035 — THE SITE'S OWN NAME IN BOTH LANGUAGES (اسم الموقع باللغتين)
--
-- The bilingual rule reached the products (0033) and their classification
-- (0034), and stopped at the site itself: source_site carries one name,
-- the Arabic one, so every dataset list and every page heading read
-- Arabic-only while the table underneath them flipped AR|EN on demand.
--
-- The name lives in the manifest — it is a fact about the source, not a
-- scraped value — so this column is what ingest writes from sources.yaml.
-- Stored beside source_name, never merged: the display layer picks the
-- language, the warehouse remembers both.
-- =====================================================================

ALTER TABLE source_site ADD COLUMN source_name_en TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 35;
