# A7 dormant-source audit — live captures, 2026-07-23

Every fixture below was fetched from the public, unauthenticated endpoint named
against it, with `User-Agent: ScrapeX/0.1 (+contact: owner)` (advancedcastle
with the Chrome UA its manifest entry declares), ~1.5 s apart. Values, key
names and nesting are byte-faithful; only whole sub-objects were dropped to
keep the files readable, and each drop is listed here.

## Files

- `salla_alsweed_product_node_outofstock_2026-07-23.json`
  The schema.org Product node from
  `https://alsweed.sa/ar/لي-سخان-اسباني-مجدول/p1754450923` (HTTP 200).
  Trimmed: the `review` array. Kept because it is the case no hand-authored
  fixture contained — a priced product whose `offers.availability` is
  `https://schema.org/OutOfStock`, which both SSR connectors recorded as
  `unknown`.

- `zid_advancedcastle_product_node_category_2026-07-23.json`
  The Product node from `https://advancedcastle.com/products/grabs` (HTTP 200),
  untrimmed. It states `category: "قفل عجلات > مخفض"` — already in the
  separator `category_path` uses — from the same node the price is read out of.

- `masdar_hybris_occ_search_ar_2026-07-23.json` /
  `masdar_hybris_occ_search_en_2026-07-23.json`
  `https://api.masdaronline.com/rest/v2/masdar/products/search?fields=FULL&pageSize=3&currentPage=0&query=:relevance&lang={ar|en}`
  (HTTP 200). The SAME three products in both languages. Trimmed: `facets`,
  `sorts`, and per product `description`, `images`, `gtmProductData`,
  `paymentModesMedia`. `pagination` is untouched and reports the live catalogue:
  **1353 products**.

- `elsewedyshop_products_en_page1_2026-07-23.json`
  `https://elsewedyshop.com/en/products.json?limit=250&page=1` (HTTP 200),
  filtered to the four product ids already captured in
  `elsewedyshop_products_page1_live.json` (2026-07-20) so the pair joins by id.
  The shop declares `ar` + `en` in its own homepage `hreflang` links.

## Cross-checks run at capture time (not stored, stated here)

- masdar storefront URL shape: the composed
  `/{lang}/{currency}/{salesUnit}/…` URL was compared against every entry of
  `https://api.masdaronline.com/rest/v2/masdar/sitemap/Product-ar-SAR.xml`
  (13,652 locs) — **639 of 639 priced products matched exactly, 0 mismatches**.
  The 714 products the API prices as `null` are absent from that sitemap too,
  i.e. they are genuinely off the storefront.
- masdar bilingual coverage: an `ar` pass and an `en` pass over all 14 search
  pages returned **1331 codes with a different English name, 0 identical**.
- alsweed's `/en/…` locale serves the **Arabic** name (checked on
  p698258674) — so no English exists to capture there; elburoj's `/en/…`
  serves a real English name.
