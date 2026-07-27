-- =====================================================================
-- 0045 — MADAR'S ATTRIBUTES STATE THEIR LANGUAGE, BY PROVENANCE
--
-- 0039 closed the attribute vocabulary for rows whose `lang` was declared,
-- and deliberately left 1,129 madar/samehgabriel rows with lang='' alone:
-- "the warehouse holds no evidence to decide them". The owner has now ruled
-- the closure path — fill lang from the CONNECTOR, then re-code — and for
-- madar the evidence exists, and it was there all along. It is not in the
-- content; it is in the PROVENANCE.
--
-- Every attribute row madar has ever stored was extracted by the one pass
-- that fetches custom_attributesV2 and the descriptions: the DEFAULT store
-- pass, which serves ar_SA. The en_SA pass fetched uid+name only — it has
-- never written an attribute row. So "which language is this row's edition"
-- is not a guess about mixed text («ASTM A775 Grade 60» is what the ARABIC
-- page prints too); it is a fact about which store answered, and the answer
-- is: all of them, Arabic.
--
-- The connector moves in the same commit (the 0039 rule): it now emits
-- `code_ar` + lang='ar' from the default pass and bare `code` + lang='en'
-- from the en_SA pass, with the site's own labels per store — «المصنع»
-- beside "Manufacturer" where the panel printed `manufacturer`. Migrate
-- without it and the next crawl doubles every fact; move the connector
-- without this and the panel shows every fact twice until the codes align.
--
-- Left OUT, deliberately:
--   * image% and weight rows — language-neutral by construction (a file is
--     a file, a number is a number). The connector marks weight's label
--     language going forward; there is nothing to re-code.
--   * SAMEHGABRIEL's rows. Woo carries no store/locale evidence, so the
--     same ruling cannot be executed the same honest way there yet. Its 18
--     description rows and 216 specification rows remain the stated debt.
-- =====================================================================

UPDATE source_product_attribute
   SET attribute_code = attribute_code || '_ar',
       lang = 'ar'
 WHERE lang = ''
   AND attribute_code NOT LIKE '%!_ar' ESCAPE '!'
   AND attribute_code NOT LIKE 'image%'
   AND attribute_code != 'weight'
   AND source_product_id IN (
       SELECT sp.source_product_id FROM source_product sp
       JOIN source_site ss ON ss.source_id = sp.source_id
       WHERE ss.source_key = 'MADAR');

-- A promoted code follows its fact (0044), or the owner's choice silently
-- stops matching anything.
UPDATE source_attribute_promotion
   SET attribute_code = attribute_code || '_ar'
 WHERE source_key = 'MADAR'
   AND attribute_code NOT LIKE '%!_ar' ESCAPE '!'
   AND attribute_code NOT LIKE 'image%'
   AND attribute_code != 'weight';

PRAGMA user_version = 45;
