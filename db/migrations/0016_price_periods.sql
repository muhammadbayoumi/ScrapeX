-- =====================================================================
-- migration 0016: the derived price layers (spec: price-history storage
-- semantics).
--
-- The owner-facing history is a timeline of REAL price changes. That needs
-- three things the append-only evidence cannot express on its own:
--
--   offer_state     the latest price and availability, for fast reads
--   price_period    one row per continuous confirmed price
--   absence_period  when an offer stopped being seen, and when it returned
--
-- All three are DERIVED and REBUILDABLE from price_observation plus
-- crawl_run. That is what makes them safe to make mutable while the
-- evidence beneath them stays append-only: nothing here is a source of
-- truth, and pricehistory.rebuild() can reconstruct every row.
--
-- Purely additive. No existing table is altered and no observation is
-- touched, so the append-only triggers have nothing to object to.
-- =====================================================================

-- One row per offer: what it costs and whether it can be bought, right now.
CREATE TABLE offer_state (
    offer_id            INTEGER PRIMARY KEY REFERENCES source_offer(offer_id),
    effective_price     REAL,
    currency            TEXT,
    availability        TEXT NOT NULL DEFAULT 'unknown',
    stock_quantity      REAL,
    price_hash          TEXT,
    price_fields        TEXT,
    -- Advanced by every successful refresh that saw this offer, whether or
    -- not the price moved. A failed or partial run must NOT advance it.
    last_confirmed_at   TEXT,
    last_seen_at        TEXT,
    first_seen_at       TEXT,
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- One row per continuous stretch during which the price did not change.
-- closed_at IS NULL means the period is still open.
CREATE TABLE price_period (
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
    -- return after an absence, or the source changing which fields it publishes.
    opened_because     TEXT NOT NULL DEFAULT 'price_change'
        CHECK (opened_because IN ('first_seen','price_change','returned','fields_changed'))
);

CREATE INDEX ix_price_period_offer ON price_period (offer_id, first_detected_at DESC);
-- At most one open period per offer: two would mean two current prices.
CREATE UNIQUE INDEX ux_price_period_open ON price_period (offer_id)
    WHERE closed_at IS NULL;

-- Created only when a successfully completed run did not see an offer it
-- expected. A failed or partial run proves nothing about absence.
CREATE TABLE absence_period (
    absence_period_id  INTEGER PRIMARY KEY,
    offer_id           INTEGER NOT NULL REFERENCES source_offer(offer_id),
    missing_since      TEXT NOT NULL,
    returned_at        TEXT,
    -- The run that established the absence, so the claim is auditable.
    detected_by_run_id INTEGER REFERENCES crawl_run(run_id)
);

CREATE INDEX ix_absence_period_offer ON absence_period (offer_id, missing_since DESC);
CREATE UNIQUE INDEX ux_absence_period_open ON absence_period (offer_id)
    WHERE returned_at IS NULL;

PRAGMA user_version = 16;
