-- =====================================================================
-- 0036 — THE VARIATION IN BOTH LANGUAGES (التنويع باللغتين)
--
-- The owner: madar publishes its variations in Arabic AND English, and we
-- kept one of them. source_variant has held exactly one label
-- (option_label, «السماكة (مم): 2.2») and one axes bag
-- (raw_options_json) since the first schema, so the standing bilingual
-- rule — a translation the site publishes and we drop is a defect —
-- stopped at the variation.
--
-- THE NAMES ARE THE NEW VOCABULARY, DELIBERATELY. docs/column-vocabulary.md
-- (owner-approved) settles that the unmarked name is ENGLISH and Arabic is
-- marked `_ar`, and that the display name for this field is `variant`. The
-- Arabic columns are not renamed here: option_label and raw_options_json
-- are renamed to variant_ar and variant_axes_ar by the one sweep that
-- inverts every bilingual name at once. Naming the NEW columns correctly
-- now means that sweep renames only what already existed, instead of
-- renaming these two again a day after inventing them.
--
-- So, until that sweep lands, this table reads:
--     option_label      Arabic label      -> becomes variant_ar
--     variant           English label     (this migration)
--     raw_options_json  Arabic axes JSON  -> becomes variant_axes_ar
--     variant_axes      English axes JSON (this migration)
--
-- Empty is the honest default: a source that publishes one language fills
-- one column, and the display layer falls back to whichever side exists
-- rather than showing a blank.
-- =====================================================================

ALTER TABLE source_variant ADD COLUMN variant TEXT NOT NULL DEFAULT '';
ALTER TABLE source_variant ADD COLUMN variant_axes TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 36;
