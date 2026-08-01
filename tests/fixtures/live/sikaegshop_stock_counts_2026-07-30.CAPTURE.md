# SIKAEGSHOP stock counts — live capture 2026-07-30

Captured while diagnosing why `price_observation.stock_quantity` is NULL for
every SIKAEGSHOP row although the API publishes a count for every product.
`https://www.sikaegshop.com/api/products?page=1..8`, User-Agent
`ScrapeX/0.1 (+contact: owner)`, requests spaced ≥1.3 s, HTTP 200 on all 8,
read-only GETs against the same open endpoint the connector already crawls.

## The census — all 87 products, one pass

| fact | count |
|---|---|
| products returned (8 pages of 12, last page 3) | **87**, 87 distinct ids |
| publish the `stock_quantity` key | **87 / 87** |
| publish a non-null value | **87 / 87** |
| value type | `int` on all 87 — never a string, never a float |
| **publish `0`** | **16 / 87** |
| range | 0 … 4000 |

Distribution: `0`×16, `1`×2, `5`×4, `7`, `8`, `9`×4, `10`×18, `11`, `14`,
`15`×7, `16`, `18`×4, `19`, `20`×2, `23`, `24`, `25`×2, `26`, `48`, `57`, `82`,
`83`, `99`, `100`×4, `108`, `110`, `119`, `130`, `198`, `240`, `500`, `1196`,
`3000`, `4000`.

## What the 16 zeros settle

**All 16 zero-stock products carry `is_active: true`.** The shop lists them and
says none are left, at the same time. That is the whole argument for two rules
this fixture exists to hold in place:

1. **A published 0 must land.** It is not missing data — it is the single most
   decision-changing thing the shop says about a count, on 18% of the catalogue
   today. Storing NULL there would erase it.
2. **A count nobody published must stay NULL.** The inverse error is worse: a
   defaulted `0` reads as "sold out" for a product the shop never discussed.

So the price row uses an explicit `is not None` test, never truthiness. The
enrichment bag keeps its opposite, falsy guard — deliberately, with its own
recorded reason (a `Stock quantity: 0` row would sit next to `Maximum stock
level: 0` on 85 of 87 products, which is the field left unset, not a limit).
Prose and measurement want different rules; only the measurement column is
being fixed here.

`is_active: true` on all 16 also re-confirms `_availability`'s ordering: the
listing flag is not a stock level, and reading it first would report 16
out-of-stock products as `in_stock`.

## The fixture — `sikaegshop_stock_counts_2026-07-30.json`

Three products, **whole and byte-faithful** — no key was dropped and no value
edited. These records are ~1.3 KB each, so the trimming the larger captures in
this directory need does not apply.

| id | page | `stock_quantity` | `price` | why it is here |
|---|---|---|---|---|
| 213 | 1 | **0** | 2280 | the published zero, `is_active: true` |
| 252 | 2 | 198 | 10 | a healthy count; the same product `sikaegshop_page2.json` already carries at 198 |
| 288 | 8 | 4000 | 650 | the top of the range, four digits |

The envelope is the real `{success, data, pagination}` shape. Only two
`pagination` values were adjusted so the fixture stands alone as a single page:
`totalPages` 8 → 1 and `hasMore` true → false. `total: 87`, `page: 1` and
`limit: 12` are as captured — 87 is the true catalogue size, and the file is
three of those 87, not a claim that the shop sells three things.

No detail (`/api/products/{id}`) request was made for this capture: the count is
published by the LIST endpoint, which is what the price row is built from, so a
prices-only crawl already has it in hand.

## What the warehouse looked like before the fix (read-only, 2026-07-30)

Joined `price_observation` → `source_offer` → `source_variant` →
`source_product` → `source_site`:

| source | observations | carrying a count |
|---|---|---|
| **SIKAEGSHOP** | **252** | **0** |
| MADAR | 6,146 | 0 |
| MASDAR | 617 | 617 |
| GPP_ENERGY | 64,514 | 0 |

and `offer_state`: SIKAEGSHOP **0 of 87** rows carry one, MASDAR 617 of 617.

MASDAR is the proof the column works end to end — `hybris.py` has passed
`stock_quantity=` since it was written. sika read the same number twice (once in
`_availability`, once as an enrichment row) and put it on neither price row.
