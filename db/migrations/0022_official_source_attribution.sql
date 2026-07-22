-- =====================================================================
-- 0022 — WHO STATES THIS PRICE (المصدر الرسمي)
--
-- globalpetrolprices names, on many country pages, the official body its
-- figure comes from — "Source: Ministry of Petroleum and Mineral
-- Resources" with a link for Egypt, Saudi Aramco for Saudi Arabia — and
-- the warehouse had no home for it, so the strongest provenance signal
-- on the whole page was thrown away at parse time.
--
-- It rides the OBSERVATION, denormalized, because the observation table
-- is append-only: an attribution that changes on the site simply arrives
-- on the next row, and history keeps what each row said at its time.
-- Both columns default to '' — Germany's page names no source, and an
-- absent attribution must read as "not stated", never be invented.
-- =====================================================================

ALTER TABLE price_observation ADD COLUMN official_source_name TEXT NOT NULL DEFAULT '';
ALTER TABLE price_observation ADD COLUMN official_source_url  TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 22;
