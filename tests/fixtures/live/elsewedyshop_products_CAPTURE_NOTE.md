# ELSEWEDYSHOP live capture — 2026-07-20

Source: `https://elsewedyshop.com` (sources.yaml `ELSEWEDYSHOP`, family `shopify-json`)

## URLs fetched (HTTP 200, public, unauthenticated)

- `https://elsewedyshop.com/products.json?limit=250&page=1` — 250 products / 260 variants
- `https://elsewedyshop.com/products.json?limit=250&page=2` — 250 products
- `https://elsewedyshop.com/products.json?limit=250&page=3` — 250 products
- `https://elsewedyshop.com/products.json?limit=250&page=4` — 184 products (< 250 -> pagination ends)

Catalogue total on this date: **934 products / 1034 variants**.
Page id sets are disjoint (p1&p2 overlap = 0, p2&p3 overlap = 0), so the
`?page=` parameter genuinely paginates on this shop.

## Files

- `elsewedyshop_products_page1_live.json` — 4 products trimmed from page 1, byte-faithful
  (values, key names and nesting untouched; only the product list was shortened).
  Chosen to cover the real branch space: single `Default Title` variant, a 6-variant
  product with a real `color` option, a product carrying `compare_at_price`, and an
  out-of-stock variant.
- `elsewedyshop_products_page4_live.json` — first 3 products of the last page.

User-Agent sent: `ScrapeX/1.0 (+price research; contact madastore1899@gmail.com)`.
Requests spaced ~1.5–2 s apart.
