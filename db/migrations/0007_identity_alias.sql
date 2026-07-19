-- ============================================================================
-- Migration 0007 — identity aliases (spec section 14).
--
-- A record's INTERNAL identity (material / material_variant) is permanent; its
-- SOURCE identity is not. Sites re-slug URLs, re-issue SKUs, and migrate ids.
-- Without a memory of the old values, a re-crawl sees a stranger and mints a
-- duplicate entity, silently splitting the price history in two.
--
-- Every superseded identity value is kept here, so matching can still recognise
-- the record by what it USED to be called.
-- ============================================================================

CREATE TABLE identity_alias (
    identity_alias_id INTEGER PRIMARY KEY,
    source_product_id INTEGER NOT NULL REFERENCES source_product(source_product_id),
    alias_type        TEXT NOT NULL
        CHECK (alias_type IN ('external_product_id','external_sku','product_url')),
    alias_value       TEXT NOT NULL,
    first_seen_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    retired_at        TEXT     -- when this value stopped being the current one
);

CREATE UNIQUE INDEX ux_identity_alias
    ON identity_alias(source_product_id, alias_type, alias_value);
-- The lookup that matters: "has anyone ever been known by this value?"
CREATE INDEX ix_identity_alias_value ON identity_alias(alias_type, alias_value);

PRAGMA user_version = 7;
