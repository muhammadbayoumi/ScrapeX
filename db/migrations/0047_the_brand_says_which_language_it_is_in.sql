-- =====================================================================
-- 0047 — THE BRAND SAYS WHICH LANGUAGE IT IS IN
--
-- brand_raw held one string with no language, and three different things
-- were living in it:
--
--   ALSWEED       both names glued together, Arabic first, in one field:
--                 «لوكسيفاي LUXIFY», «الخزف السعودي Saudi Ceramics». The
--                 site publishes both, so the standing bilingual rule says
--                 both are captured -- and half of every one of them was
--                 unreachable behind the other.
--   MASDAR/SIKA   Latin only.
--   SAMEHGABRIEL  Arabic only («السويدي اليكتريك»).
--
-- The pair follows the project's naming convention (0039 / B10): the
-- UNMARKED name is the non-Arabic one, `_ar` marks Arabic.
--
-- SPLIT BY SCRIPT, PER WORD, ORDER PRESERVED — normalize.split_brand. Not
-- by position: «الخزف السعودي Saudi Ceramics» is two Arabic words then two
-- Latin ones, and a cut at a fixed index would maul it.
--
-- NOTHING IS EDITED, ONLY MOVED. Rejoining the pair Arabic-first reproduces
-- the published string byte for byte -- verified on all 261 distinct brand
-- strings in the warehouse, and the generator below REFUSES to emit a row
-- that does not round-trip. That property is load-bearing twice over:
--   * the owner's rule that the site's text is the record, never edited;
--   * the price key. ingest feeds it the rejoined string, so every existing
--     offer keeps its exact hash. 0 of 261 digests change, so not one
--     phantom "price change" is reported and no price period closes.
--
-- MADAR: 536 of its 763 products state a manufacturer, already bilingual
-- under `manufacturer` / `manufacturer_ar`, while brand_raw was empty on
-- every one. Copied ACROSS VERBATIM, on the owner's ruling (2026-07-28)
-- that what the site publishes is the record even where it is plainly a
-- human error -- so `Brazil`, `India` and `Malaysia` (a country typed into
-- the brand field), «مصنع حديد» ("steel factory", a description), «حديد
-- محلي», and `Gaint` (the shop's own misspelling of Giant) all travel
-- unchanged. They will be right when the shop fixes them, and a cleaning
-- rule here would hide the day it did. The detail rows STAY: the shop
-- prints them under "More information", and deleting them would remove
-- something the page says.
--
-- The view is dropped FIRST and rebuilt from 0042's body with only the
-- brand line changed. SQLite silently rewrites a view around a changed
-- column and keeps the old alias, which is how 0038 learned this.
-- =====================================================================

DROP VIEW IF EXISTS v_material_price_tracking;

ALTER TABLE source_product ADD COLUMN brand TEXT;
ALTER TABLE source_product ADD COLUMN brand_ar TEXT;

-- One statement per distinct stored brand, generated from the warehouse
-- itself rather than hand-typed, so no value here was invented.
UPDATE source_product SET brand_ar = '', brand = 'ABRO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ABRO';
UPDATE source_product SET brand_ar = '', brand = 'AGM'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'AGM';
UPDATE source_product SET brand_ar = '', brand = 'AL-SAFWA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'AL-SAFWA';
UPDATE source_product SET brand_ar = '', brand = 'ALAYED'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALAYED';
UPDATE source_product SET brand_ar = '', brand = 'ALFANAR'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALFANAR';
UPDATE source_product SET brand_ar = '', brand = 'ALJAZEERA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALJAZEERA';
UPDATE source_product SET brand_ar = '', brand = 'ALMONA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALMONA';
UPDATE source_product SET brand_ar = '', brand = 'ALROUF'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALROUF';
UPDATE source_product SET brand_ar = '', brand = 'ALSALEH'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALSALEH';
UPDATE source_product SET brand_ar = '', brand = 'ALTAYAR'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ALTAYAR';
UPDATE source_product SET brand_ar = '', brand = 'APLACO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'APLACO';
UPDATE source_product SET brand_ar = '', brand = 'AQUATIC'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'AQUATIC';
UPDATE source_product SET brand_ar = '', brand = 'AREB'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'AREB';
UPDATE source_product SET brand_ar = '', brand = 'ARISTON'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ARISTON';
UPDATE source_product SET brand_ar = '', brand = 'BAHRAIN PIPES'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'BAHRAIN PIPES';
UPDATE source_product SET brand_ar = '', brand = 'BEOROL'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'BEOROL';
UPDATE source_product SET brand_ar = '', brand = 'BOSCH'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'BOSCH';
UPDATE source_product SET brand_ar = '', brand = 'Blue W.D'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Blue W.D';
UPDATE source_product SET brand_ar = '', brand = 'Blue by el sewedy'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Blue by el sewedy';
UPDATE source_product SET brand_ar = '', brand = 'CANYON'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'CANYON';
UPDATE source_product SET brand_ar = '', brand = 'DABG'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'DABG';
UPDATE source_product SET brand_ar = '', brand = 'DADCO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'DADCO';
UPDATE source_product SET brand_ar = '', brand = 'DIME'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'DIME';
UPDATE source_product SET brand_ar = '', brand = 'DOLPHY'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'DOLPHY';
UPDATE source_product SET brand_ar = '', brand = 'EGLO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'EGLO';
UPDATE source_product SET brand_ar = '', brand = 'EL-KHAYAT'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'EL-KHAYAT';
UPDATE source_product SET brand_ar = '', brand = 'EMY'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'EMY';
UPDATE source_product SET brand_ar = '', brand = 'ENOLGAS'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ENOLGAS';
UPDATE source_product SET brand_ar = '', brand = 'EURODOCCIA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'EURODOCCIA';
UPDATE source_product SET brand_ar = '', brand = 'Egylux'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Egylux';
UPDATE source_product SET brand_ar = '', brand = 'El Sewedy Cables'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'El Sewedy Cables';
UPDATE source_product SET brand_ar = '', brand = 'El-Sewedy'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'El-Sewedy';
UPDATE source_product SET brand_ar = '', brand = 'Elsewedy'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Elsewedy';
UPDATE source_product SET brand_ar = '', brand = 'FIX-IT'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'FIX-IT';
UPDATE source_product SET brand_ar = '', brand = 'FOREMANN'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'FOREMANN';
UPDATE source_product SET brand_ar = '', brand = 'FixTec'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'FixTec';
UPDATE source_product SET brand_ar = '', brand = 'Flory'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Flory';
UPDATE source_product SET brand_ar = '', brand = 'GENOX'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'GENOX';
UPDATE source_product SET brand_ar = '', brand = 'GRUNDFOS'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'GRUNDFOS';
UPDATE source_product SET brand_ar = '', brand = 'Himel'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Himel';
UPDATE source_product SET brand_ar = '', brand = 'Home Light'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Home Light';
UPDATE source_product SET brand_ar = '', brand = 'Huntkey'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Huntkey';
UPDATE source_product SET brand_ar = '', brand = 'JCC'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'JCC';
UPDATE source_product SET brand_ar = '', brand = 'KARIBA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'KARIBA';
UPDATE source_product SET brand_ar = '', brand = 'KISTENMACHER'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'KISTENMACHER';
UPDATE source_product SET brand_ar = '', brand = 'KNIPEX'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'KNIPEX';
UPDATE source_product SET brand_ar = '', brand = 'Kenier'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Kenier';
UPDATE source_product SET brand_ar = '', brand = 'LATICRETE'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'LATICRETE';
UPDATE source_product SET brand_ar = '', brand = 'LUMA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'LUMA';
UPDATE source_product SET brand_ar = '', brand = 'Luma'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Luma';
UPDATE source_product SET brand_ar = '', brand = 'MINLI'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'MINLI';
UPDATE source_product SET brand_ar = '', brand = 'MUSTANG'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'MUSTANG';
UPDATE source_product SET brand_ar = '', brand = 'Moustafa Mahmoud'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Moustafa Mahmoud';
UPDATE source_product SET brand_ar = '', brand = 'Orange'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Orange';
UPDATE source_product SET brand_ar = '', brand = 'PETA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'PETA';
UPDATE source_product SET brand_ar = '', brand = 'PHILIPS'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'PHILIPS';
UPDATE source_product SET brand_ar = '', brand = 'PKCELL'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'PKCELL';
UPDATE source_product SET brand_ar = '', brand = 'Panasonic'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Panasonic';
UPDATE source_product SET brand_ar = '', brand = 'Pkcell'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Pkcell';
UPDATE source_product SET brand_ar = '', brand = 'RAM BOARD'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'RAM BOARD';
UPDATE source_product SET brand_ar = '', brand = 'RIO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'RIO';
UPDATE source_product SET brand_ar = '', brand = 'RIYADH CEMENT'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'RIYADH CEMENT';
UPDATE source_product SET brand_ar = '', brand = 'SAAF'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SAAF';
UPDATE source_product SET brand_ar = '', brand = 'SAMNAN'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SAMNAN';
UPDATE source_product SET brand_ar = '', brand = 'SAUDI'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SAUDI';
UPDATE source_product SET brand_ar = '', brand = 'SAVETO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SAVETO';
UPDATE source_product SET brand_ar = '', brand = 'SCHNIEDER'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SCHNIEDER';
UPDATE source_product SET brand_ar = '', brand = 'SIEFCO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SIEFCO';
UPDATE source_product SET brand_ar = '', brand = 'SIKA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SIKA';
UPDATE source_product SET brand_ar = '', brand = 'SILENT POWER'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'SILENT POWER';
UPDATE source_product SET brand_ar = '', brand = 'Shall'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Shall';
UPDATE source_product SET brand_ar = '', brand = 'Siemens'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Siemens';
UPDATE source_product SET brand_ar = '', brand = 'TAHWEEL'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'TAHWEEL';
UPDATE source_product SET brand_ar = '', brand = 'TCONTROLS'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'TCONTROLS';
UPDATE source_product SET brand_ar = '', brand = 'TESA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'TESA';
UPDATE source_product SET brand_ar = '', brand = 'TRAMONTINA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'TRAMONTINA';
UPDATE source_product SET brand_ar = '', brand = 'TREVITECH'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'TREVITECH';
UPDATE source_product SET brand_ar = '', brand = 'Tango'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Tango';
UPDATE source_product SET brand_ar = '', brand = 'TopDon'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'TopDon';
UPDATE source_product SET brand_ar = '', brand = 'UNITED'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'UNITED';
UPDATE source_product SET brand_ar = '', brand = 'USAMS'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'USAMS';
UPDATE source_product SET brand_ar = '', brand = 'UYUS tools'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'UYUS tools';
UPDATE source_product SET brand_ar = '', brand = 'Weidasi'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Weidasi';
UPDATE source_product SET brand_ar = '', brand = 'Wokin'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Wokin';
UPDATE source_product SET brand_ar = '', brand = 'Worksite'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'Worksite';
UPDATE source_product SET brand_ar = '', brand = 'X-BOARD'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'X-BOARD';
UPDATE source_product SET brand_ar = '', brand = 'YAMAMAH'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'YAMAMAH';
UPDATE source_product SET brand_ar = '', brand = 'YinduTools'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'YinduTools';
UPDATE source_product SET brand_ar = '', brand = 'gardenia'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'gardenia';
UPDATE source_product SET brand_ar = '', brand = 'modern light'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'modern light';
UPDATE source_product SET brand_ar = '', brand = 'mp illumination'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'mp illumination';
UPDATE source_product SET brand_ar = '', brand = 'sphinx'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'sphinx';
UPDATE source_product SET brand_ar = 'أليماتيك', brand = 'ALEMATEK'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'أليماتيك ALEMATEK';
UPDATE source_product SET brand_ar = 'أوريانت ستاندرد', brand = ''
 WHERE TRIM(COALESCE(brand_raw,'')) = 'أوريانت ستاندرد';
UPDATE source_product SET brand_ar = 'اريستون', brand = 'ARISTON'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'اريستون ARISTON';
UPDATE source_product SET brand_ar = 'اكواهت', brand = 'Aquahot'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'اكواهت Aquahot';
UPDATE source_product SET brand_ar = 'الخزف السعودي', brand = 'Saudi Ceramics'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'الخزف السعودي Saudi Ceramics';
UPDATE source_product SET brand_ar = 'الرائد العربي', brand = 'ALRAED'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'الرائد العربي ALRAED';
UPDATE source_product SET brand_ar = 'الزامل', brand = 'AL ZAMIL'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'الزامل AL ZAMIL';
UPDATE source_product SET brand_ar = 'السويدي اليكتريك', brand = ''
 WHERE TRIM(COALESCE(brand_raw,'')) = 'السويدي اليكتريك';
UPDATE source_product SET brand_ar = 'العايد', brand = 'ALAYED'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'العايد ALAYED';
UPDATE source_product SET brand_ar = 'الوسائل', brand = 'ALWSAIL'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'الوسائل ALWSAIL';
UPDATE source_product SET brand_ar = 'ايمي', brand = 'EMI'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ايمي EMI';
UPDATE source_product SET brand_ar = 'بورسلينا', brand = 'Porsalina'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'بورسلينا Porsalina';
UPDATE source_product SET brand_ar = 'بوسيني', brand = 'BOSSINI'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'بوسيني BOSSINI';
UPDATE source_product SET brand_ar = 'تات', brand = 'TAT'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'تات TAT';
UPDATE source_product SET brand_ar = 'تاتو', brand = 'TATO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'تاتو TATO';
UPDATE source_product SET brand_ar = 'تريدكس', brand = 'TREDEX'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'تريدكس TREDEX';
UPDATE source_product SET brand_ar = 'تيلو', brand = 'tillo'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'تيلو tillo';
UPDATE source_product SET brand_ar = 'جروهي', brand = 'GROHE'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'جروهي GROHE';
UPDATE source_product SET brand_ar = 'جيبرت', brand = 'GEBERIT'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'جيبرت GEBERIT';
UPDATE source_product SET brand_ar = 'ديوجي', brand = 'DueGi'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ديوجي DueGi';
UPDATE source_product SET brand_ar = 'ركيزة', brand = ''
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ركيزة';
UPDATE source_product SET brand_ar = 'سافيتو', brand = 'SAVETO'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'سافيتو SAVETO';
UPDATE source_product SET brand_ar = 'ستامينا', brand = 'Stamina'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ستامينا Stamina';
UPDATE source_product SET brand_ar = 'سمنان', brand = 'SAMNAN'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'سمنان SAMNAN';
UPDATE source_product SET brand_ar = 'شركة الوطني للبولي اثيلين', brand = ''
 WHERE TRIM(COALESCE(brand_raw,'')) = 'شركة الوطني للبولي اثيلين';
UPDATE source_product SET brand_ar = 'فيتا', brand = 'VITTA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'فيتا VITTA';
UPDATE source_product SET brand_ar = 'كولين', brand = 'KOOLEN'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'كولين KOOLEN';
UPDATE source_product SET brand_ar = 'لوتز', brand = 'LUTZ'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'لوتز LUTZ';
UPDATE source_product SET brand_ar = 'لوكسيفاي', brand = 'LUXIFY'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'لوكسيفاي LUXIFY';
UPDATE source_product SET brand_ar = 'ليما', brand = 'LIMA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ليما LIMA';
UPDATE source_product SET brand_ar = 'مورس', brand = 'Maurice'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'مورس Maurice';
UPDATE source_product SET brand_ar = 'ميديا', brand = 'MIDEA'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ميديا MIDEA';
UPDATE source_product SET brand_ar = 'هانزجروهي', brand = 'hansgrohe'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'هانزجروهي hansgrohe';
UPDATE source_product SET brand_ar = 'هزنت', brand = 'HESANIT'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'هزنت HESANIT';
UPDATE source_product SET brand_ar = 'هنتر', brand = 'HUNTER'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'هنتر HUNTER';
UPDATE source_product SET brand_ar = 'هوفمان', brand = 'HOFFMANN'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'هوفمان HOFFMANN';
UPDATE source_product SET brand_ar = 'ون', brand = 'One'
 WHERE TRIM(COALESCE(brand_raw,'')) = 'ون One';

-- MADAR's brand, promoted from the detail the shop already publishes.
UPDATE source_product
   SET brand = COALESCE((SELECT spa.raw_value FROM source_product_attribute spa
                          WHERE spa.source_product_id = source_product.source_product_id
                            AND spa.attribute_code = 'manufacturer'), ''),
       brand_ar = COALESCE((SELECT spa.raw_value FROM source_product_attribute spa
                             WHERE spa.source_product_id = source_product.source_product_id
                               AND spa.attribute_code = 'manufacturer_ar'), '')
 WHERE source_id IN (SELECT source_id FROM source_site WHERE source_key = 'MADAR')
   AND EXISTS (SELECT 1 FROM source_product_attribute spa
                WHERE spa.source_product_id = source_product.source_product_id
                  AND spa.attribute_code IN ('manufacturer', 'manufacturer_ar'));

-- COVERAGE GUARD, and the reason it exists: the split statements above are
-- generated from a SNAPSHOT of the warehouse, so a brand first crawled between
-- generating this file and running it would match none of them and be thrown
-- away the moment brand_raw is dropped. That is exactly the silent data loss
-- the owner's rule forbids, so it fails the migration instead.
--
-- The CHECK can never be satisfied and the column is NOT NULL, so ANY row the
-- SELECT finds raises and the runner rolls the whole migration back. An empty
-- SELECT inserts nothing and costs nothing.
CREATE TEMP TABLE _brand_split_coverage (
    uncovered TEXT NOT NULL CHECK (uncovered IS NULL)
);
INSERT INTO _brand_split_coverage (uncovered)
SELECT DISTINCT brand_raw FROM source_product
 WHERE TRIM(COALESCE(brand_raw, '')) <> '' AND brand IS NULL AND brand_ar IS NULL;
DROP TABLE _brand_split_coverage;

ALTER TABLE source_product DROP COLUMN brand_raw;

CREATE VIEW v_material_price_tracking AS
SELECT
    po.business_date                AS observation_date,
    ss.source_name                  AS source_name,
    ss.source_name_ar               AS source_name_ar,
    m.material_id                   AS material_id,
    COALESCE(m.material_name, m.material_name_ar) AS material_name,
    mv.variant_id                   AS variant_id,
    mv.variant_name                 AS variant_name,
    sv.external_sku                 AS external_sku,
    sp.source_product_id            AS source_product_id,
    sv.source_variant_id            AS source_variant_id,
    COALESCE(b.brand_name, sp.brand)    AS brand,
    sp.brand_ar                     AS brand_ar,
    mv.spec_fingerprint             AS specification_summary,
    so.country_code_alpha2          AS country_code_alpha2,
    po.regular_price                AS regular_price,
    po.sale_price                   AS sale_price,
    po.effective_price              AS effective_price,
    po.currency                     AS currency,
    su.unit_code                    AS selling_unit,
    so.basis_quantity               AS basis_quantity,
    po.vat_included                 AS vat_included,
    po.availability                 AS availability,
    po.stock_quantity               AS stock_quantity,
    sp.product_url                  AS product_url,
    po.snapshot_id                  AS snapshot_id
FROM price_observation po
JOIN source_offer so        ON so.offer_id = po.offer_id
JOIN source_variant sv      ON sv.source_variant_id = so.source_variant_id
JOIN source_product sp      ON sp.source_product_id = sv.source_product_id
JOIN source_site ss         ON ss.source_id = sp.source_id
JOIN source_variant_match svm ON svm.source_variant_id = sv.source_variant_id
                             AND svm.review_status = 'approved' AND svm.valid_to IS NULL
JOIN material_variant mv    ON mv.variant_id = svm.variant_id
JOIN material m             ON m.material_id = mv.material_id
LEFT JOIN brand b           ON b.brand_id = m.brand_id
LEFT JOIN selling_unit su   ON su.selling_unit_id = so.selling_unit_id
WHERE po.price_observation_id = COALESCE(
    (SELECT p2.price_observation_id FROM price_observation p2
     WHERE p2.offer_id = po.offer_id AND p2.provenance = 'observed'
     ORDER BY p2.business_date DESC, p2.price_observation_id DESC LIMIT 1),
    (SELECT p3.price_observation_id FROM price_observation p3
     WHERE p3.offer_id = po.offer_id AND p3.provenance = 'reported'
     ORDER BY p3.business_date DESC, p3.price_observation_id DESC LIMIT 1)
);

PRAGMA user_version = 47;
