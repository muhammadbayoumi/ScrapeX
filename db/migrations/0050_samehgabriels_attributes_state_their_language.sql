-- =====================================================================
-- 0050 — SAMEH GABRIEL'S ATTRIBUTES STATE THEIR LANGUAGE
--
-- The debt 0039 and 0045 both named and both deferred. 0045 wrote it down
-- plainly: "SAMEHGABRIEL's rows. Woo carries no store/locale evidence, so
-- the same ruling cannot be executed the same honest way there yet."
--
-- 270 rows, 18 products, 10 codes, `lang = ''` on every one and not a
-- single `_ar` marker anywhere. Under 0039 the UNMARKED name is the
-- non-Arabic one — so every one of those codes ASSERTS English over
-- content that is entirely Arabic. `description` is the sharpest: madar
-- files the same fact as `description_ar`, this shop filed Arabic prose
-- under the bare name.
--
-- NOTHING IS BEING DROPPED HERE, and that matters for which rule applies.
-- The captured payload (the whole catalogue, X-WP-Total: 18) publishes no
-- English anywhere: no second field, no wpml/polylang/locale marker. The
-- ONLY Latin strings are the `pa_color` attribute name and the colour term
-- SLUGS — and those slugs are demonstrably not translations («أحمر» = red
-- carries slug "black"), which woocommerce.py already documents and rules
-- must never be reconciled. So this is not a missing-translation defect.
-- The Arabic content is correct; only its MARKING was wrong.
--
-- THE EVIDENCE USED IS THE VALUE'S OWN SCRIPT. Woo gives no store view and
-- no locale header — that absence is exactly why this waited — but «مجدول»
-- is Arabic whatever the headers say. Marking only what is demonstrably
-- Arabic claims nothing extra: a Latin or numeric value keeps its unmarked
-- code, which is already the right one for it.
--
-- LANGUAGE-NEUTRAL FACTS ARE EXCLUDED, the same carve-out 0045 made: a
-- weight's fact is its numeric_value and «كيلوجرام» is only this shop's
-- rendering of it, and a file is a file. Marking `weight` would also
-- silently break its owner promotion in source_attribute_promotion, which
-- keys on the code — so the promotion needs no mirrored update here.
--
-- THE CONNECTOR MOVES IN THE SAME COMMIT, which is 0039's own rule and not
-- a preference: ingest is INSERT ... ON CONFLICT DO UPDATE and never
-- deletes, so a migration alone means the next crawl re-creates all ten old
-- codes BESIDE the ten new ones and every product shows every fact twice.
--
-- No collision risk: this source holds zero `_ar`-suffixed codes today, so
-- UNIQUE (source_product_id, attribute_code, raw_value) cannot be violated.
-- =====================================================================

UPDATE source_product_attribute
   SET attribute_code = attribute_code || '_ar',
       lang = 'ar'
 WHERE source_product_id IN (
         SELECT sp.source_product_id FROM source_product sp
         JOIN source_site ss ON ss.source_id = sp.source_id
         WHERE ss.source_key = 'SAMEHGABRIEL')
   AND COALESCE(lang, '') = ''
   AND attribute_code NOT LIKE '%!_ar' ESCAPE '!'
   -- Language-neutral, as above.
   AND attribute_code != 'weight'
   AND attribute_code NOT LIKE 'image%'
   -- The script IS the evidence. SQLite has no regex, so the Arabic block is
   -- tested by range on the value itself: any row whose text contains a
   -- character between U+0600 and U+06FF. A row that fails this test is not
   -- Arabic and keeps the unmarked code it already correctly has.
   AND EXISTS (
         SELECT 1 FROM (
           SELECT substr(source_product_attribute.raw_value, n, 1) AS ch
           FROM (WITH RECURSIVE seq(n) AS (
                   SELECT 1
                   UNION ALL
                   SELECT n + 1 FROM seq
                    WHERE n < length(source_product_attribute.raw_value))
                 SELECT n FROM seq))
          WHERE unicode(ch) BETWEEN 1536 AND 1791);

PRAGMA user_version = 50;
