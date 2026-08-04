-- =====================================================================
-- 0060 — AN OFFER CAN BE SUPERSEDED TOO (تقاعد العرض الذى حلّ محلّه غيره)
--
-- 0032 gave source_variant this exact column for this exact reason: a
-- stand-in row that a later, better reading replaced, and which nothing
-- ever retired, so it kept posing as current forever. The same thing has
-- now happened one level down.
--
-- MADAR's own option values say «4 كجم/صندوق» — a box you buy and four
-- kilograms you get. Before the unit charter (0058) the warehouse stored
-- the four and threw the word away, so 18 offers read "4 kg". The charter
-- reads both, and the crawl of 2026-08-03 wrote them correctly — BESIDE
-- the old ones rather than over them, because selling_unit_id is part of
-- an offer's identity. That is right and deliberate: "15 per litre" and
-- "15 per gallon" ARE different offers, and ingest says so in writing.
--
-- But these are not two offers. They are two READINGS of one offer: one
-- written by code that could not see the shop's word, one by code that
-- can. The old row already says so about itself — its provenance is
-- 'legacy_unwitnessed', which means nobody can name the field it came
-- from. A value with no witness is not a fact, and leaving it beside a
-- fact makes the table contradict itself: the same product, two rows,
-- two different answers to "what is one of these".
--
-- WHAT THIS DOES NOT DO
--
-- It does not delete. The row stays, its history stays — price_observation
-- is append-only and 19 observations hang off these 18 offers. Retiring
-- is a lifecycle state, exactly as 0032 defined it, and read paths show
-- 'active'.
--
-- It does not retire a legacy reading that nothing has replaced. Measured
-- on the live warehouse 2026-08-03: MADAR carries 92 unwitnessed offers,
-- 18 of which now have a witnessed sibling on the same variant and 74 of
-- which do not. Retiring the 74 would erase a unit and put nothing in its
-- place — the owner would lose an answer to gain a principle. Only a row
-- something else already answers for can go.
--
-- The condition is written into the UPDATE rather than into a list of
-- ids, so it stays true if it runs on a different warehouse: same
-- variant, a different offer, and that other offer's provenance names a
-- witness.
-- =====================================================================

ALTER TABLE source_offer ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'superseded'));

UPDATE source_offer
   SET status = 'superseded'
 WHERE unit_basis_provenance = 'legacy_unwitnessed'
   AND EXISTS (SELECT 1
                 FROM source_offer replacement
                WHERE replacement.source_variant_id = source_offer.source_variant_id
                  AND replacement.offer_id <> source_offer.offer_id
                  AND replacement.unit_basis_provenance IS NOT NULL
                  AND replacement.unit_basis_provenance NOT IN ('', 'legacy_unwitnessed'));

PRAGMA user_version = 60;
