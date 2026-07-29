# Live capture — HEIDELBERG_EG (heidelberg-price-matrix), 2026-07-29

Every file below was fetched from `https://onlinestoreapi.heidelbergmaterials.eg`,
anonymously, with `User-Agent: ScrapeX/0.1 (+contact: owner)`, 2.5 s apart,
through ScrapeX's own `HttpFetcher`. All three answered **HTTP 200** and all
three arrived `Content-Encoding: gzip` — httpx negotiates that by default,
which is what makes the 19 MB price table a 5.4 MB download. Neither host
serves `robots.txt` (both 404), so no Crawl-delay applies.

Values, key names and nesting are byte-faithful. One sub-object was dropped,
and it is listed below.

## Files

- `heidelberg_products_2026-07-29.json` — `GET /api/Products`, **untrimmed**.
  All 9 products, 78,138 bytes decoded. Every product is `isActive: true` and
  `productTypes.productTypeNameEn == "Bagged"`; a `Bulk` («سائب») type exists in
  `/api/ProductTypes` and no product uses it.

- `heidelberg_plants_2026-07-29.json` — `GET /api/Plants`, **untrimmed**.
  3 rows: Y210 Suez/السويس, Y220 Katameya/القطامية, Y410 Helwan/حلوان, each with
  its company. This is the only place **Y220's name exists**: no product in the
  catalogue is assigned to Y220 (all 9 sit on Y210 or Y410) and the storefront
  still quotes it to every multi-plant product, so without this lookup the
  plant axis of 22 published rows could only be blank or transliterated by us.

- `heidelberg_products_prices_2026-07-29.json` — `GET /api/ProductsPrices`.
  The live table is **2,070 rows / 19,038,623 bytes**; 46 cities × 9 products ×
  5 segments, and every (product, city, segment) triple appears exactly once.
  **Trimmed two ways**, both stated so the file can be reasoned about:

  1. **Rows.** Kept: all 414 `Y6` rows (the segment the anonymous storefront
     hard-codes) plus all 45 remaining rows for **Dahab**, the only city whose
     non-Y6 rows hold a real price. 450 rows of 2,070. The dropped 1,620 hold
     **zero** real prices, so the fixture reproduces the published set exactly:
     108 rows out, the same number the full table gives.
  2. **The embedded `products` object.** Every price row carries a FULL copy of
     its product — which is the whole reason the response is 19 MB — and that
     copy is **identical to the `/api/Products` entry except that its `plants`
     is `null`**, on all 2,070 rows, checked field by field at capture time.
     The copy is therefore both redundant and *insufficient*: a connector that
     read it instead of joining on `productId` would see no `plantCode` and
     would emit nothing at all for the 6 non-multi-plant products. Dropping it
     from the fixture makes that mistake fail the tests instead of shipping.

## The census, run at capture time (not stored, stated here)

Over the **full** 2,070-row table, not the trimmed fixture:

| | |
|---|---|
| price slots (`salePrice*` / `salePrice30*`, 6 per row) | **12,420** |
| …holding a real number (`> 0.1`) | **211** |
| …sentinel | 4,523 × `0.02`, 7,686 × `0.0` |
| distinct fractional part of every real price | `.02`, and only `.02` |
| `fakePrice*` slots | 12,420 |
| …holding a real number | **0** |
| price rows with `isOnSale: true` | **0** of 2,070 |
| PRODUCTS with `isOnSale: true` | 5 of 9 — with no `fakePrice` behind any of them |

Real prices by segment: **Y6 201**, YT 5, YM 5, YO 0, YR 0. Every one of the 10
non-Y6 prices is for **Dahab**, which the API flags `isActive: false` on the
city itself and on the row.

The three filters, applied in the order the storefront applies them:

```
211 real prices
 -10  segment: not Y6, the segment an anonymous visitor is quoted
 - 5  isActive: false on the price row (the storefront's own endpoint filters these)
 -88  plant: a column the product's page never renders
= 108 published
```

108 rows over **8 products** (the ninth publishes no price anywhere) and
**9 cities** — 6 October, Al Dakahleya, Al Gharbeya, Al Monoufeya, Al Sharkeya,
Cairo, Ismaileya, Qalyoubeya, Suez. 90 of them are the ≥30 t bracket and 18 the
1–29 t one; 44 Y410, 42 Y210, 22 Y220. All 108 `(external_product_id,
external_variant_id)` pairs are distinct — 0 collisions — so each is its own
offer with its own timeline.

## The storefront's own rules, read from `main-4XHUPALI.js` (719,821 bytes)

Fetched the same day from `https://onlinestore.heidelbergmaterials.eg/`. The
bundle escapes every non-ASCII character, so these were counted after decoding
`\uXXXX`:

- `segment="Y6"` — 1 occurrence, beside `plant="Y210"`, in the products
  component's own field list. This is the anonymous quote.
- `t.salePrice30Y410>.1?5:-1` / `t.salePrice30Y410<=.1?6:-1` — the price/«غير
  متاح» branch, 14 occurrences of the sentinel branch across the six columns.
- `w(t.products.isMultiPlant?-1:1)` / `?2:-1` — the two-branch plant rule; the
  multi-plant branch is a `<select>` whose only options are «مصنع السويس» and
  «مصنع القطامية». There is **no Y410 option in it**.
- `" السعر لأقل من 30 طن"` (5×) / `" السعر لأكثر من 30 طن"` (5×), `" / للطن "`
  (13×), `"ج م"` (47×) — the two brackets, the unit and the currency.
- `" قد تختلف الأسعار حسب كمية الأسمنت المطلوبة أو المصنع المنتِج - السعر من 1 الى 29 طن يختلف عن السعر من 30 طن فأكثر "`
  — the sentence the quantity axis's Arabic values are lifted from, verbatim.
- `" شامل النقل و ضريبة القيمة المضافة (14%) "` — 3 occurrences, each rendered
  directly beneath `t.order.total` in the cart, checkout and order-details
  components. This is the source's whole VAT statement.
- `maxPrice` — **0 occurrences**. `exWorkMaxPrice` — **0**. `salePrice` — 65.
  The two fields that look like the price are referenced by nothing.
- `c.onAddCart(o.productId,s,o.salePriceY410,o.salePrice30Y410,"Y410")` — the
  site's live cart defect: a non-multi-plant Y210/Y220 product adds to cart at
  the Y410 column's ≥30 t price. The DISPLAY branches are correct, and the
  display is what this connector records.

Routes checked the same day, all **404** at IIS because there is no SPA
fallback rewrite: `/cart`, `/cart/`, `/checkout/`,
`/productinfo/1000007e-32a9-4324-8ed9-117b0c47389f`. A product link is a
client-side route to be opened in a browser, never fetched.
