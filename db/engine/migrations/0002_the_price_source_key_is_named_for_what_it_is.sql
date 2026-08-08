-- The column that pointed a generic site at its price counterpart was called
-- `marketlens_source_key`, after a database that no longer exists.
--
-- It is not a rename for tidiness. The name told a reader to go looking for a
-- MarketLens database to understand what the column meant, and there is nothing
-- by that name to find — so the name had stopped describing anything and had
-- started describing a thing that was deleted.
--
-- `price_source_key` says what it holds: the key of the price source this site
-- corresponds to. That was always what it held.
--
-- THE COLUMN IS NULL ON EVERY ROW THAT EXISTS. Checked read-only against the
-- owner's own database before this was written: one site_profile row, muqawil,
-- with this column NULL. So there is no data movement here at all — this is a
-- name changing, and RENAME COLUMN carries the index and the constraints with
-- it rather than rebuilding the table around them.

ALTER TABLE site_profile RENAME COLUMN marketlens_source_key TO price_source_key;

PRAGMA user_version = 2;
