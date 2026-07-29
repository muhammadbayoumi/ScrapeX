-- =====================================================================
-- 0056 — HOW THE SITE SHOWS IT, AND WHAT ONE UNIT BUYS
--
-- Two questions were being answered by one column, and badly.
--
-- THE DEFECT. A MADAR row could not be read. The prices themselves were
-- never wrong — all 3,410 live prices matched the warehouse exactly on
-- 2026-07-29, 0 mismatches — but every fact SURROUNDING the number was
-- missing, and without them the number is unreadable:
--
--   the Ø8mm rebar member costs 4,830 and the Ø32mm costs 4,045
--
-- Per piece that is impossible: a 12 m Ø32 bar carries ~16x the steel of
-- a Ø8 bar. Per TONNE it is exactly right — thin bars cost more per tonne
-- to roll. The site says so in numbers: weight 1000, is_qty_decimal true,
-- min_sale_qty 0.25, qty_increments 0.05. ScrapeX stored basis_quantity
-- 1.0, no unit, no minimum — "the price of one thing".
--
-- WHAT THIS MIGRATION DOES NOT DO: it does not write «طن» anywhere. The
-- shop never prints that word. Verified exhaustively 2026-07-29 against
-- the live site — member attributes, parent attributes, description,
-- short_description, every meta field, both category descriptions, both
-- store views, and the full 932KB rendered page: «طن» 0 times, «الوحدة»
-- 0 times, and the quantity box is labelled «الكمية» and nothing else.
-- The owner ruled on it directly: «الحقائق الخام فقط» — raw facts only.
-- So the site's NUMBERS are stored and the display layer renders "per
-- 1,000 kg". An inferred unit would be a word the shop never said, which
-- is the one thing this warehouse does not do.
--
-- THE KEY STRUCTURAL FINDING, and the reason this is TWO columns and not
-- one: "sold by a bulk unit" is NOT a fourth Magento shape. It appears
-- inside GroupedProduct (96 leaves) AND inside ConfigurableProduct (13 —
-- the steel mesh, whose children carry per-child weights of 6.74..66.02
-- kg, not a uniform 1000). Any design that models presentation as a
-- single enum over __typename misses it. So:
--
--   source_product.display_method  — HOW THE SITE PRESENTS THE PRODUCT.
--                                    A property of the PRODUCT, constant
--                                    across every row it emits.
--   source_offer.<quantity facts>  — WHAT ONE UNIT OF THE PRICE BUYS.
--                                    A property of the OFFER, differing
--                                    per member.
--
-- WHY NOT REUSE has_variants: it reads 1 for 763 of 763 MADAR products,
-- and for every product of sources 1,2,3,4,7,8,9. ingest emitted
-- `1 if external_variant_id or option_fingerprint`, and a simple product
-- is emitted as row(uid, uid), so external_variant_id is never empty. The
-- one column that looked like it answered "how is this product presented"
-- answered 1 for everything. Its meaning is spent; a new column is
-- cheaper than a re-interpretation nobody can see.
--
-- display_method's vocabulary is closed (scrapex.vocab.DisplayMethod) and
-- deliberately has NO catch-all value. '' means "a shape nobody has
-- studied", never "the nearest thing" — a BundleProduct arriving tomorrow
-- files blank rather than wrong. Counted live 2026-07-29: 400 single, 36
-- options_one_price, 292 options_priced, 33 member_list (161 leaves).
--
-- minimum_quantity already EXISTED and was never wired: it appeared
-- exactly once in the whole repo, in db/schema.sql, with nothing reading
-- or writing it and no column for it on the PRODUCT_PRICES contract, so
-- no connector could have sent one. riyadh-cement child 70504010
-- publishes min_sale_qty 450 with qty_increments 450 at 50 kg a bag —
-- the price is only obtainable at 450 bags = 22.5 t per order, and the
-- warehouse said NULL for all 3,417 MADAR offers.
--
-- NO BACKFILL IS POSSIBLE, and none is attempted: raw_snapshot holds 0
-- rows, so there is nothing to re-read. Values arrive on the next crawl.
-- Every default below ('' and 0 and NULL) reads as "the site did not
-- say", which is precisely the truthful state of every existing row.
--
-- All three changes are ALTER TABLE ADD COLUMN with defaults: no table
-- rebuild, no index touched, no view rewritten, no data loss. The offer
-- identity index (ux_source_offer_identity) does NOT include any of these
-- columns, so no existing offer changes identity and no offer is split.
-- =====================================================================

-- HOW THE SITE PRESENTS IT — one of vocab.DisplayMethod, or '' for a
-- shape not yet studied. No CHECK constraint: the vocabulary lives in
-- scrapex/vocab.py and test_schema.py asserts the two never drift, which
-- is this repo's standing pattern for an enum that connectors extend.
ALTER TABLE source_product ADD COLUMN display_method TEXT NOT NULL DEFAULT '';

-- WHAT ONE UNIT OF THE PRICE BUYS. minimum_quantity is already on the
-- table (schema.sql:177) and only needed wiring, so it is absent here.
ALTER TABLE source_offer ADD COLUMN quantity_increment REAL;
ALTER TABLE source_offer ADD COLUMN quantity_is_decimal INTEGER NOT NULL DEFAULT 0
    CHECK (quantity_is_decimal IN (0,1));

-- has_variants, CORRECTED IN PLACE — the one thing in this migration that is a
-- backfill, and the only one that CAN be. The other columns describe facts the
-- site publishes and we never asked for, so they must wait for a crawl. This
-- one is derivable from rows the warehouse already holds: a product has
-- variations when some variant of it is not simply ITSELF.
--
-- Without this the fix would be half a fix. ingest only ever wrote has_variants
-- at INSERT, so correcting the rule there fixes products discovered from now
-- on and leaves every existing one — all 763 MADAR products and every product
-- of sources 1,2,3,4,7,8,9 — still reading 1. A column that is right for new
-- rows and wrong for old ones is worse than one that is uniformly wrong,
-- because nothing on screen says which kind of row you are looking at.
--
-- The rule is exactly the row-level one, aggregated: a variant whose
-- external_variant_id differs from its product's external_product_id is a real
-- variation, and so is any variant carrying an option fingerprint. A simple
-- product is stored as one variant wearing the product's own id, which is
-- precisely the case the old test could not see.
UPDATE source_product SET has_variants = (
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM source_variant v
        WHERE v.source_product_id = source_product.source_product_id
          AND (COALESCE(v.option_fingerprint, '') <> ''
               OR COALESCE(v.external_variant_id, '')
                  NOT IN ('', source_product.external_product_id))
    ) THEN 1 ELSE 0 END
);

PRAGMA user_version = 56;
