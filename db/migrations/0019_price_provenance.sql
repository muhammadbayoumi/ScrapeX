-- =====================================================================
-- 0019 — WHERE A PRICE CAME FROM (مصدر السعر)
--
-- Until now every row in price_observation meant the same thing: "we read
-- this price ourselves, on this date". That was true, because we only ever
-- recorded what a live crawl saw.
--
-- globalpetrolprices publishes, free on each country page, what the price
-- WAS one month, three months and one year ago. Taking those turns one
-- initial crawl into a year of history instead of waiting fifty-two weeks
-- to learn a trend — but they are not our observations. We did not see the
-- Egyptian diesel price on 2025-07-21; the publisher states today that it
-- was 15.50 then.
--
-- Storing both under one meaning would make the warehouse claim an
-- observation it never made. So each row now says which it is:
--
--   'observed'  we fetched the page and this was the price on it
--   'reported'  the source stated, at fetch time, that this was the price
--               on an earlier date
--
-- Existing rows are 'observed', which is what they are. The column is NOT
-- NULL with that default, so a writer cannot forget to say.
--
-- A reported price is still an append-only fact and still carries the
-- run that recorded it, so it can always be traced back. What it must
-- never do is silently pass for something we watched happen.
-- =====================================================================

ALTER TABLE price_observation
    ADD COLUMN provenance TEXT NOT NULL DEFAULT 'observed'
    CHECK (provenance IN ('observed','reported'));

-- Reading "what did this offer cost over time" now has to be able to ask
-- for one kind or both, cheaply.
CREATE INDEX ix_price_obs_provenance
    ON price_observation (offer_id, provenance, business_date DESC);
