-- =====================================================================
-- 0028 — CURRENCY RATES AGAINST THE DOLLAR (رصد العملات مقابل الدولار)
--
-- The owner wants a computed USD column on the Data page so countries
-- can be RANKED by price across 128 currencies. The rates come free:
-- every GPP country page publishes the local price AND the site's own
-- USD conversion side by side, which IMPLIES the rate the site used —
-- read off the source, never asserted. One row per (currency, day,
-- source): re-crawls upsert the day's figure, history accumulates.
--
-- provenance is in the source column by construction: these are the
-- rates a PUBLISHER used, good for ranking and rough conversion,
-- and the USD column they feed is labelled as derived.
-- =====================================================================

CREATE TABLE currency_rate (
    currency_rate_id INTEGER PRIMARY KEY,
    currency         TEXT NOT NULL,            -- ISO code: EGP, SAR, EUR...
    per_usd          REAL NOT NULL CHECK (per_usd > 0),   -- 1 USD = per_usd currency
    as_of            TEXT NOT NULL,            -- the date the rate speaks for
    source_key       TEXT NOT NULL,            -- who implied it
    recorded_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    UNIQUE (currency, as_of, source_key)
);

CREATE INDEX ix_currency_rate_latest ON currency_rate(currency, as_of DESC);

PRAGMA user_version = 28;
