-- =====================================================================
-- 0034 — THE CLASSIFICATION IN BOTH LANGUAGES (التصنيف باللغتين)
--
-- The owner's standing rule (2026-07-23): any content a site publishes in
-- Arabic AND English is captured in BOTH — not names alone. madar's
-- category tree answers in en_SA as readily as in ar_SA, and sika states
-- category_arname beside category_enname on every product; we stored one
-- and dropped the other, so the whole classification read Arabic-only.
--
-- Stored beside the primary path, never merged: the display layer picks
-- the language, the warehouse remembers both. Same shape source_name_en
-- established in 0033, so one rule covers every bilingual field.
-- =====================================================================

ALTER TABLE source_product ADD COLUMN category_path_en TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 34;
