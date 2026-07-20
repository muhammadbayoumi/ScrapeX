# REFUTER independent connector-output capture - 2026-07-20

Real rows produced by running the SHIPPED connector classes against LIVE bytes.
Not fixtures. Not replayed. Network fetch, honest UA, 2s interval.

## ADVANCEDCASTLE (ZidConnector, scrapex/connectors/zid.py)
sitemap https://advancedcastle.com/sitemap.xml -> 200, 4 sub-sitemaps
sitemap_products.xml -> 200, 167 product <loc>
First 8 product URLs fetched -> 8 of 8 rows produced (100% yield)
Every row: price, currency SAR, availability in_stock, sku, name populated.
brand_raw EMPTY on all 8 - live Zid Product nodes have NO brand key.
Sample: external_product_id=a4ba0102-P6 regular_price=160.00 currency=SAR availability=in_stock

## ALSWEED (SallaConnector, scrapex/connectors/salla.py)
https://alsweed.sa/ar/sitemap.xml -> 200, 3 sub-sitemaps
2466 product URLs matching /p{5,} -- but only 1233 UNIQUE product ids.
The /ar/ sitemap index also lists every /en/ URL: 1233 ar + 1233 en, factor exactly 2.0.
First 8 URLs fetched -> 6 rows (2 skipped, price key absent = variant-priced).
Those 6 rows are 3 DISTINCT products emitted TWICE each, with IDENTICAL
external_product_id AND external_variant_id, differing only in product_url.
e.g. id 1754450923 appears as .../ar/.../p1754450923 and .../en/.../p1754450923

## Fixture falsification evidence (tests/fixtures/zid_*)
- zid_sitemap.xml declares https://advancedcastle.com/sitemap-products.xml (hyphen) -> LIVE HTTP 400
  Real name is sitemap_products.xml (underscore).
- zid_subsitemap.xml declares /products/cement-bag and /products/rebar-12 -> LIVE HTTP 404 both.
  Neither slug appears anywhere in the live sitemap. Live catalogue is safety equipment.
- Fixture Product nodes carry brand (dict form and string form); ZERO live Zid products have brand.
- zid_product_variant.html uses an @graph wrapper and an AggregateOffer/lowPrice;
  live pages have neither - 3 standalone ld+json blocks, always {"@type":"Offer"}.
- git log: single commit ff21042 2026-07-19, never refreshed.
