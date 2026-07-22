-- =====================================================================
-- 0023 — TAX EVIDENCE IS PER COMMODITY, NOT ONLY PER COUNTRY
--
-- The owner's report from the live Data page: every row's tax link led
-- to the DIESEL list page — gasoline, electricity and natural-gas rows
-- included — because tax_rule could only say "this source, this region".
-- The site states its evidence per ENERGY-TYPE page, in different words:
-- the diesel/gasoline/LPG pages each carry their own taxes-and-subsidies
-- sentence, the electricity page says plainly "Final retail prices with
-- all taxes and fees included", and the natural-gas page says nothing —
-- which must resolve to Unverified, not borrow diesel's link.
--
-- material_key '*' is the source-wide rule (every existing row keeps its
-- meaning unchanged); a specific key scopes a rule to one commodity.
-- Product sources never set it and keep resolving through '*'.
-- =====================================================================

ALTER TABLE tax_rule ADD COLUMN material_key TEXT NOT NULL DEFAULT '*';

-- One CURRENT rule per (source, region, material); superseded rules stay.
DROP INDEX ux_tax_rule_current;
CREATE UNIQUE INDEX ux_tax_rule_current
    ON tax_rule (source_key, region, material_key) WHERE valid_to IS NULL;

DROP INDEX ix_tax_rule_lookup;
CREATE INDEX ix_tax_rule_lookup
    ON tax_rule (source_key, region, material_key, valid_from DESC);

PRAGMA user_version = 23;
