-- ============================================================================
-- Migration 0006 — field-level change events (spec section 15).
--
-- price_observation already keeps full PRICE history (append-only), but every
-- other field was invisible: _get_product only INSERTed, so a product renamed at
-- the source kept its original name forever — the change was neither recorded
-- NOR applied. This table is the missing "what changed, when, and in which job"
-- layer, and it is what the panel's "34 changed · 15 new · 3 unavailable"
-- summary reads.
--
-- Current state stays in source_product / source_variant / price_observation;
-- this table is the CHANGE layer over them, never a replacement.
-- ============================================================================

CREATE TABLE change_event (
    change_event_id   INTEGER PRIMARY KEY,
    source_product_id INTEGER REFERENCES source_product(source_product_id),
    source_variant_id INTEGER REFERENCES source_variant(source_variant_id),
    offer_id          INTEGER REFERENCES source_offer(offer_id),
    field_key         TEXT NOT NULL,        -- 'effective_price' | 'source_name' | 'availability' | ...
    previous_value    TEXT,                 -- NULL for a 'new' event
    new_value         TEXT,
    change_type       TEXT NOT NULL CHECK (change_type IN (
                          'new','field_updated','price_increase','price_decrease',
                          'unavailable','returned','removed')),
    detected_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    run_id            INTEGER REFERENCES crawl_run(run_id),
    job_id            INTEGER REFERENCES crawl_job(job_id)
);

CREATE INDEX ix_change_event_time ON change_event(change_event_id DESC);
CREATE INDEX ix_change_event_product ON change_event(source_product_id, change_event_id DESC);
CREATE INDEX ix_change_event_run ON change_event(run_id);

PRAGMA user_version = 6;
