-- =====================================================================
-- 0054 — A RATE SAYS WHETHER A PROVIDER OR A SHOP PUBLISHED IT
--
-- Owner ruling 2026-07-28, after the column-vocabulary audit found it:
-- «عمود صريح لنوع المصدر».
--
-- THE DEFECT. currency_rate.source_key holds two different KINDS of thing
-- under one name, and the live data proves it:
--
--     google_finance   93 rows   2024-06-18T01:01:00Z .. 2026-07-28T13:17:00Z
--     GPP_ENERGY       81 rows   2026-07-20 .. 2026-07-20
--
-- 'google_finance' is a RATE PROVIDER. 'GPP_ENERGY' is a SHOP — one of the
-- nine rows in source_site — that happens to publish local/USD pairs the
-- crawl can read an implied rate off. So any query that joins
-- currency_rate.source_key to source_site.source_key silently matches 81 rows
-- and drops 93, and nothing in the schema says that is wrong.
--
-- The two namespaces even format their dates differently — the provider
-- writes ISO timestamps, the shop writes bare dates — which is a symptom of
-- the same split, not a second problem.
--
-- THE FIX is a column that states which one a row is, so the distinction is
-- in the schema rather than in the head of whoever writes the next query.
--
-- WHY A TABLE REBUILD RATHER THAN ALTER TABLE ADD COLUMN: SQLite cannot add a
-- NOT NULL column without a DEFAULT, and a default here is the exact bug this
-- migration exists to prevent — a future INSERT that forgets the kind would
-- silently be filed as whatever the default says. The table holds 174 rows,
-- so a rebuild costs nothing and buys a constraint that cannot be forgotten.
--
-- THE BACKFILL IS DERIVED, NOT LISTED: a row is a shop's if its source_key
-- names a row in source_site, and a provider's otherwise. Hard-coding
-- 'google_finance' would be right today and wrong the first time a second
-- provider is added.
--
-- ADVANCEDCASTLE is why this lands now rather than later: it publishes its own
-- SAR->EGP rate, so it is about to become the SECOND shop writing into this
-- table (owner ruling, same day: store the published rate, never the converted
-- price). Without this column that would have doubled the ambiguity.
-- =====================================================================

CREATE TABLE currency_rate_new (
    currency_rate_id INTEGER PRIMARY KEY,
    currency         TEXT NOT NULL,            -- ISO code: EGP, SAR, EUR...
    per_usd          REAL NOT NULL CHECK (per_usd > 0),   -- 1 USD = per_usd currency
    as_of            TEXT NOT NULL,            -- the date the rate speaks for
    source_key       TEXT NOT NULL,            -- who published it
    -- WHAT KIND of publisher that is. 'provider' is a rate service whose
    -- business IS the rate; 'shop' is a storefront we read an implied rate off
    -- its own printed prices. A shop's rate is evidence about that shop, and
    -- must never be mistaken for a market rate.
    source_kind      TEXT NOT NULL CHECK (source_kind IN ('provider', 'shop')),
    recorded_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (currency, as_of, source_key)
);

INSERT INTO currency_rate_new
    (currency_rate_id, currency, per_usd, as_of, source_key, source_kind, recorded_at)
SELECT cr.currency_rate_id, cr.currency, cr.per_usd, cr.as_of, cr.source_key,
       CASE WHEN EXISTS (SELECT 1 FROM source_site ss
                          WHERE ss.source_key = cr.source_key)
            THEN 'shop' ELSE 'provider' END,
       cr.recorded_at
  FROM currency_rate cr;

-- The guard: every row must have been classified. An unclassified row would
-- have violated the CHECK above and rolled this back already, but a count
-- mismatch would not, and a partial copy is the worse failure.
CREATE TEMP TABLE _rate_copy_complete (
    lost INTEGER NOT NULL CHECK (lost = 0)
);
INSERT INTO _rate_copy_complete (lost)
SELECT (SELECT COUNT(*) FROM currency_rate)
     - (SELECT COUNT(*) FROM currency_rate_new);
DROP TABLE _rate_copy_complete;

DROP TABLE currency_rate;
ALTER TABLE currency_rate_new RENAME TO currency_rate;

CREATE INDEX ix_currency_rate_latest ON currency_rate(currency, as_of DESC);
-- Reading a rate now asks the provider first, so this is the index that answers.
CREATE INDEX ix_currency_rate_kind ON currency_rate(currency, source_kind, as_of DESC);

PRAGMA user_version = 54;
