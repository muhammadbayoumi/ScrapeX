# Live capture — MADAR (magento-graphql), the REMAINING-STOCK COUNTS

- File: `madar_stock_counts_2026-07-30.json`
- URL: `https://www.madar.com/graphql` (POST)
- Captured: 2026-07-30, HTTP 200
- Query: the connector's own `_QUERY_TEMPLATE` fields, with the census filter
  swapped from `price:{from:"0"}` to `sku:{in:[...]}` so the capture stays to
  three products. `only_x_left_in_stock` is asked for exactly where the census
  asks for it — on `SimpleProduct` at the top level and on the `SimpleProduct`
  inside a `GroupedProduct` member.
- Trimmed: nothing. The counts, the `null`s, the names (including the leading
  whitespace madar puts in `71205003`'s name) and the prices are the bytes the
  API returned.

## Why these three

They are the two products named in the defect report plus one grouped product,
and between them they hold both halves of the rule under test.

| sku          | `__typename`      | `only_x_left_in_stock` |
|--------------|-------------------|------------------------|
| `530458705`  | `SimpleProduct`   | **1**                  |
| `71205003`   | `SimpleProduct`   | **8**                  |
| `10115-HSS`  | `GroupedProduct`  | `null` on all 9 members |

- **`530458705`** "PEGASO P52 STEEL BAR BENDING MACHIN", 27,772.50 — a count of
  **1**. The smallest non-zero count the site publishes, and the one that is
  destroyed by a falsy guard rather than a null check. It is the reason
  `_still_the_same_price` tests `is not None` and not truthiness.
- **`71205003`** "DADCO POLYESTER-DP200 -4MM", 150.94 — a count of **8**, the
  second example from the report.
- **`10115-HSS`** «حديد تسليح ابوكسي من حديد» — the epoxy rebar. All **nine**
  members answer `null`: the site publishes no remaining count for any of them.
  This is the half of the contract that has no other witness — these nine must
  stay NULL and must never be written as 0. "We do not know how many are left"
  and "none are left" are different facts, and on a price-tracking warehouse the
  second one is a claim about the shop's ability to sell.

Note this is a `sku:{in:...}` capture, so `categories` answers `[]` for all
three — madar only fills breadcrumbs on a category listing. The test supplies
the category context separately; nothing here depends on it.
