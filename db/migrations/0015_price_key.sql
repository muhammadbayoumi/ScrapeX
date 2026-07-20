-- =====================================================================
-- migration 0015: record WHAT made each price comparable.
--
-- record_hash mixed the money with availability and stock, so a stock
-- movement produced a new hash, a new observation, and a change event
-- that read as a price change. The owner wants the latest stock state,
-- never its history.
--
-- price_hash covers everything that makes two prices non-comparable —
-- money, denomination (unit, region) and what is priced (manufacturer,
-- origin, specification) — and NOT availability or stock.
--
-- price_fields records which of those the source actually supplied.
-- Stores differ: most give no manufacturer, almost none give an origin.
-- Without this list, the day a store starts publishing a manufacturer
-- every one of its offers would appear to change price at once.
--
-- Purely additive. price_observation stays append-only: these columns
-- are added, never back-filled, because back-filling would mean
-- UPDATE-ing rows the schema triggers forbid touching. Rows written
-- before this migration keep NULL and readers treat that as "unknown",
-- which is what it is.
-- =====================================================================

ALTER TABLE price_observation ADD COLUMN price_hash TEXT;
ALTER TABLE price_observation ADD COLUMN price_fields TEXT;

-- The price timeline is read per offer, newest first.
CREATE INDEX ix_price_obs_offer_pricehash
    ON price_observation (offer_id, observed_at DESC, price_hash);

PRAGMA user_version = 15;
