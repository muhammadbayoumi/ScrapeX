-- =====================================================================
-- 0052 — THE TRADE TIER IS A PRICE, NOT A DETAIL
--
-- Owner ruling 2026-07-28: «عمود سعر فى الجدول لا تفصيلة».
--
-- sikaegshop publishes `specail_price`: the amount the storefront charges a
-- logged-in customer whose customerTypeId is 2. It is settled fact, proven
-- from the shop's own bundle and a live browser — not a dated discount and
-- not something ScrapeX can ever be quoted, because it crawls anonymously.
-- It was stored as an attribute (filed under Store by 0046, as a holding
-- place the test said so out loud). A price belongs beside the prices.
--
-- 78 rows move from the details bag into a real column.
--
-- IT IS NOT IN THE PRICE KEY, and that is deliberate twice over. It is not
-- what makes two prices incomparable — it is a DIFFERENT customer's price,
-- so hashing it would split one product's timeline on a number the owner
-- is never charged. And record_hash is the frozen cross-engine dedupe key
-- (ingest._observation_values says so); changing its composition would
-- silently re-key every observation in the warehouse.
--
-- THE LIMITATION THAT FOLLOWS, written down rather than discovered later:
-- because it is outside record_hash, a run where ONLY the trade price moved
-- appends no observation, so the new value is not recorded until something
-- else about the price changes. That is acceptable on the evidence — this
-- shop's specail_price is a standing B2B price that has not moved across
-- every capture — but it IS a limitation, and if the shop starts moving it
-- independently the honest fix is to widen record_hash behind a
-- PRICE_KEY_VERSION-style re-baseline, not to pretend it was never true.
--
-- The attribute rows are DELETED rather than left beside the column: unlike
-- madar's manufacturer, this fact is not something the shop prints in a
-- panel we would be hiding. It is a number the API returns, and keeping it
-- in two places is the same fact filed twice under two names.
-- =====================================================================

ALTER TABLE price_observation ADD COLUMN price_trade REAL;

-- NO BACKFILL, and the reason is a rule this project already made:
-- price_observation is APPEND-ONLY, enforced by trg_price_obs_no_update. The
-- first draft of this migration tried to fill the latest observation per offer
-- and the trigger refused it — correctly. Writing a trade price onto an
-- observation made before this column existed would be stating that the shop
-- quoted that number on that date, which nothing here knows.
--
-- The values are not lost: they are re-fetched from the shop on the next
-- sikaegshop crawl, which is what a scraper is for. Until that crawl runs the
-- column is empty and its per-source gate keeps it off the table entirely,
-- rather than showing 87 blanks.

DELETE FROM source_product_attribute WHERE attribute_code = 'trade_tier_price';

PRAGMA user_version = 52;
