-- Every source carries its own crawl scope, because 14 minutes and 34 hours are
-- two products and not two settings of one (owner, 2026-08-05).
--
-- Measured on muqawil.org: the listing is 860 pages; every detail page is
-- 121,157 requests. Change-tracking repeats whichever was chosen, so the
-- difference is not paid once.
--
-- DEFAULTS TO THE CHEAPEST ON PURPOSE. A default that costs thirty-four hours
-- is a default that runs before anyone has understood what they asked for, and
-- existing rows have never been asked.
--
-- `crawl_slice` is the city or grade that makes listing_plus_slice affordable.
-- NULL is correct for the other two scopes and scrapex/crawlscope.py refuses
-- listing_plus_slice without it, rather than quietly meaning "everything".

ALTER TABLE site_profile ADD COLUMN crawl_scope TEXT NOT NULL DEFAULT 'listing_only';
ALTER TABLE site_profile ADD COLUMN crawl_slice TEXT;

PRAGMA user_version = 3;
