-- =====================================================================
-- 0055 — THE TAX TABLE SPEAKS THE TAX VOCABULARY
--
-- Owner ruling 2026-07-28, from the column-vocabulary audit:
-- «توحيد التخزين على tax_*».
--
-- THE DEFECT. One fact wears two words depending on which side of the
-- storage boundary you stand on:
--
--     stored in tax_rule        on the wire / in the export / on screen
--     ------------------        ------------------------------------
--     vat_mode                  tax_mode
--     rate_pct                  tax_rate_pct
--     evidence                  tax_evidence
--     statement_url             tax_statement
--     statement_text            (nothing — it has no wire name at all)
--     statement_lang            (nothing)
--
-- 0051 moved the whole system onto `tax` — price_observation.vat_included,
-- price_period and source_offer all became tax_included — and this table was
-- the one place the sweep did not reach. So the same tax position is `tax_*`
-- in three tables and `vat`/bare words in this one, and every reader has to
-- learn two dictionaries for one idea.
--
-- WHAT THIS IS NOT: it is not a change to what any of these columns MEAN, and
-- not a change to a single value. Eight rules exist across four sources, all
-- of them keep exactly the position they state today.
--
-- statement_text gains a name for the first time. It is populated on all eight
-- live rules and no consumer has ever been able to ask for it, because it had
-- no wire spelling — 0051's rename collided `tax_statement_url -> tax_statement`
-- on top of it and Python kept the last of the two duplicate dict keys. Naming
-- it tax_statement_text does not export it; it makes exporting it possible.
--
-- source_site.default_vat_mode moves with them. It is the same fact — this
-- source's default tax position — stored one table over, and leaving it behind
-- would keep the word `vat` alive in the warehouse for one column.
--
-- SQLite renames columns in place and rewrites the views that select them, so
-- no view is dropped here: `SELECT vat_mode` appears in no view (checked
-- against sqlite_master), and the two live views name only tax_included, which
-- 0051 already renamed.
-- =====================================================================

ALTER TABLE tax_rule RENAME COLUMN vat_mode       TO tax_mode;
ALTER TABLE tax_rule RENAME COLUMN rate_pct       TO tax_rate_pct;
ALTER TABLE tax_rule RENAME COLUMN evidence       TO tax_evidence;
ALTER TABLE tax_rule RENAME COLUMN statement_url  TO tax_statement;
ALTER TABLE tax_rule RENAME COLUMN statement_text TO tax_statement_text;
ALTER TABLE tax_rule RENAME COLUMN statement_lang TO tax_statement_lang;

ALTER TABLE source_site RENAME COLUMN default_vat_mode TO default_tax_mode;

-- The guard: every rule must still state a position after the rename. A
-- renamed-away column would leave these NULL, and a tax position that quietly
-- became unknown is the one outcome this table exists to prevent.
CREATE TEMP TABLE _tax_rename_complete (
    unstated INTEGER NOT NULL CHECK (unstated = 0)
);
INSERT INTO _tax_rename_complete (unstated)
SELECT COUNT(*) FROM tax_rule
 WHERE tax_mode IS NULL OR TRIM(tax_mode) = ''
    OR tax_evidence IS NULL OR TRIM(tax_evidence) = '';
DROP TABLE _tax_rename_complete;

PRAGMA user_version = 55;
