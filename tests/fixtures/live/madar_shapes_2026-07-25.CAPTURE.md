# Live capture — MADAR (magento-graphql), the PRODUCT SHAPES

- File: `madar_shapes_2026-07-25.json`
- URL: `https://www.madar.com/graphql` (POST)
- Captured: 2026-07-25, HTTP 200
- Query: the connector's own `_QUERY_TEMPLATE`, with the census filter swapped
  from `price:{from:"0"}` to `sku:{in:$skus}` so the capture stays small. Every
  field is the one the census really asks for.
- Trimmed: `11535-SRW` really has 28 members; the first 4 are kept. Nothing
  else is modified — the numbers, the `__typename`s and the `price_range`s are
  the bytes the API returned.

## Why these four

Study B1 enumerated the whole live census (8 pages, 760 products) on
2026-07-25 and found exactly three shapes:

| `__typename`          | count |
|-----------------------|-------|
| `SimpleProduct`       |   399 |
| `ConfigurableProduct` |   328 |
| `GroupedProduct`      |    33 |

No `BundleProduct`, `VirtualProduct` or `DownloadableProduct` anywhere.

The four captured products are one of each shape plus a second grouped one,
chosen because each pins a fact the connector now depends on:

- **`11535-SRW`** «الخشب الأحمر السويدي» — a `GroupedProduct` whose members
  really span **1,449.00 .. 2,233.88**, while the group's own `price_range`
  answers `maximum_price == minimum_price == 1449`. The group figure is the
  CHEAPEST MEMBER wearing the group's name. Verified on the storefront the
  same day: the page prints no product price at all, only
  «المقاسات/الأنواع المتوفرة» followed by one price per member — and those 28
  printed prices equal the API's 28 member prices exactly.
- **`10128-TSS`** «حديد تسليح تعمير» — a `GroupedProduct` whose 3 members all
  cost 3,139.50, so the group figure happens to be right. Kept so the fix is
  tested where the old behaviour was accidentally correct too.
- **`12512-TSP`** "Tigercore Shuttering Plywood" — a `ConfigurableProduct`.
  GraphQL answers 50.4; the page prints «يبدأ من: 57.96». This is not a ratio
  guess: the same HTML declares
  `finalPriceExclTaxKey = 'basePrice'` / `finalPriceInclTaxKey = 'finalPrice'`
  and then publishes `{"basePrice":{"amount":50.4},"finalPrice":{"amount":57.96}}`.
  The API lands on the EXCLUSIVE field; the visitor is shown the inclusive one.
- **`71102002`** `putty-1-kg-sab` — the `SimpleProduct` commit 53b2407 checked
  by hand. GraphQL 4.23, page `initialFinalPrice` 4.232, page excl 3.68. For
  this shape the API figure IS the visitor's, which is why the source-wide
  uplift had to go.

Six further products of each shape were sampled at random and agreed 6/6 both
ways (simple: API == printed; configurable: API == the page's own `basePrice`).
