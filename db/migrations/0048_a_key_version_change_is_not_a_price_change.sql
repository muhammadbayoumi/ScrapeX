-- =====================================================================
-- 0048 — CHANGING WHAT A KEY MEANS IS NOT A PRICE CHANGE
--
-- pricekey.PRICE_KEY_VERSION exists so the MEANING of a hashed field can
-- change (a different normalizer, a renamed key). Its own docstring
-- promises that bumping it "re-baselines every offer instead of reporting
-- a price change, because nothing about the price actually moved", and
-- docs/column-vocabulary.md leans on that promise when it argues a column
-- rename is safe.
--
-- The promise was never implemented. Proven by running it: after a bump the
-- field set is identical and the currency is identical, so _same_price fell
-- through to `return False, "price_change"` — for EVERY offer in the
-- warehouse, on the next crawl. The one escape hatch the design provides
-- was a warehouse-wide false alarm, which is why nobody could ever take it.
--
-- Two things were missing and both are added here:
--   * the version was hashed INTO the digest but never recorded beside it,
--     so a reader could not tell a v1 key from a v2 one. It now rides at the
--     front of price_fields as "v2,effective,...". parse_fields already
--     ignores tokens outside its vocabulary (there is a test), so old rows
--     with no prefix read as v1 — which is what they are — and nothing that
--     compares field SETS changes behaviour.
--   * the vocabulary had no honest word for it. 'key_version_changed' says
--     what happened: we changed how prices are compared, the source did
--     nothing. reports.py counts only 'price_change' when it reports price
--     movement, so this is excluded from that count by construction.
--
-- SQLite cannot widen a CHECK in place, so price_period is rebuilt — the
-- same recipe 0030 used to add 'currency_change'. The table is DERIVED
-- (rebuilt from observations on demand), so the copy is cheap and nothing
-- references its rows by id.
-- =====================================================================

PRAGMA foreign_keys = OFF;

CREATE TABLE price_period_new (
    price_period_id    INTEGER PRIMARY KEY,
    offer_id           INTEGER NOT NULL REFERENCES source_offer(offer_id),
    price_hash         TEXT NOT NULL,
    -- The fields the hash covered. Two periods whose field sets differ are not
    -- comparable, and the boundary between them is the source publishing more
    -- (or less) rather than a price moving.
    price_fields       TEXT NOT NULL DEFAULT '',
    effective_price    REAL,
    regular_price      REAL,
    sale_price         REAL,
    currency           TEXT,
    vat_included       INTEGER,
    first_detected_at  TEXT NOT NULL,
    last_confirmed_at  TEXT NOT NULL,
    closed_at          TEXT,
    -- Why this period began: the first price ever seen, a real price change, a
    -- return after an absence, the source changing which fields it publishes,
    -- the source switching the CURRENCY it publishes in, or US changing what a
    -- key MEANS (PRICE_KEY_VERSION) — the last of which is not an event at the
    -- source at all.
    opened_because     TEXT NOT NULL DEFAULT 'price_change'
        CHECK (opened_because IN ('first_seen','price_change','returned',
                                  'fields_changed','currency_change',
                                  'key_version_changed'))
);

INSERT INTO price_period_new (
    price_period_id, offer_id, price_hash, price_fields, effective_price,
    regular_price, sale_price, currency, vat_included, first_detected_at,
    last_confirmed_at, closed_at, opened_because)
SELECT
    price_period_id, offer_id, price_hash, price_fields, effective_price,
    regular_price, sale_price, currency, vat_included, first_detected_at,
    last_confirmed_at, closed_at, opened_because
FROM price_period;

DROP TABLE price_period;
ALTER TABLE price_period_new RENAME TO price_period;

CREATE INDEX ix_price_period_offer ON price_period (offer_id, first_detected_at DESC);

-- BOTH indexes, not one. 0030 rebuilt this table and recreated only
-- ix_price_period_offer, silently dropping the partial UNIQUE that IS the
-- invariant "at most one open period per offer" — 0031 exists solely to put it
-- back. This migration reuses 0030's recipe, so it inherited the same omission
-- and the regression test 0031 left behind caught it. Copying a migration
-- copies its bugs.
CREATE UNIQUE INDEX ux_price_period_open
    ON price_period (offer_id) WHERE closed_at IS NULL;

PRAGMA foreign_keys = ON;

PRAGMA user_version = 48;
