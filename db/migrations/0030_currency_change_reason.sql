-- =====================================================================
-- 0030 — A CURRENCY FLIP IS NOT A PRICE MOVE (تغيّر العملة ليس تغيّر سعر)
--
-- Currency sits inside the price key, so when a source flips the
-- currency it publishes in (GPP country pages can publish USD one week
-- and the local currency the next), the observation correctly opens a
-- new period — but the only reason the vocabulary could give it was
-- 'price_change'. 20.50 EGP after 0.40 USD is NOT a −98% crash; the
-- numbers are not comparable at all, and telling the owner the price
-- moved is the exact corruption the currency-in-key rule exists to
-- prevent. 'currency_change' names what actually happened.
--
-- SQLite cannot widen a CHECK in place, so price_period is rebuilt —
-- same recipe as 0020: ids preserved, enforcement suspended for the
-- swap. The table is DERIVED (rebuilt from observations on demand), so
-- the copy is cheap and nothing references its rows by id.
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
    -- or the source switching the CURRENCY it publishes in.
    opened_because     TEXT NOT NULL DEFAULT 'price_change'
        CHECK (opened_because IN ('first_seen','price_change','returned',
                                  'fields_changed','currency_change'))
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

PRAGMA foreign_keys = ON;

PRAGMA user_version = 30;
