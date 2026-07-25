-- =====================================================================
-- 0037 — THE VARIATION'S OWN ADDRESS, AND THE PRODUCT'S OWN SKU
--
-- Two identity faults, both of them "the last row wins" over a column
-- that was never meant to be shared.
--
-- 1. THE LINK. A variation has its own page — WooCommerce publishes
--    /product/…/?attribute_pa_color=black per variation — and there was
--    nowhere to put it, so ingest wrote it onto source_product.product_url
--    and every variation of a product overwrote the one before. Live on
--    samehgabriel: all 108 variants carry ONE url, so five of every six
--    links open the wrong colour.
--
--    A note for whoever reads that url next and thinks it is wrong: this
--    shop's colour SLUGS do not match its colour NAMES. «أحمر» is slug
--    `black`, «أخضر» is `beige`, «أسود» is `blue` — they renamed the terms
--    and kept the slugs. WooCommerce selects by slug, so the link is
--    correct and the label is correct and they disagree on purpose. Do not
--    "fix" the link to match the label; that would break selection.
--
-- 2. THE SKU. source_product.external_sku held the sku of whichever
--    VARIATION was ingested last (76ec8c8572f0-6), not the product's own
--    (76ec8c8572f0) — which the shop publishes plainly on the parent.
--    Same shape of bug: one column, many writers, no owner.
--
-- Both columns are additive and empty by default: a source that publishes
-- one product per row fills neither, and nothing downstream may assume
-- they are populated.
-- =====================================================================

ALTER TABLE source_variant ADD COLUMN variant_url TEXT NOT NULL DEFAULT '';
ALTER TABLE source_product ADD COLUMN parent_sku TEXT NOT NULL DEFAULT '';

PRAGMA user_version = 37;
