# Gallery order — live capture 2026-08-01 (issue #35)

`elsewedyshop_gallery_order_2026-08-01.json` — three products, taken verbatim
out of `https://elsewedyshop.com/products.json?limit=250&page={1,2,3}`.
User-Agent `ScrapeX/0.1 (+contact: owner)`, requests spaced 1.3 s, HTTP 200 on
all three, nothing else was asked for. **No image file was downloaded** — the
URL is the record. No crawl was running (`/api/jobs`: last job finished
2026-07-30 13:35Z) and the engine was not touched.

## Why a new fixture instead of an existing one

`elsewedyshop_products_images_2026-07-30.json` exists and would nearly do. It
was captured to prove the pictures were *captured at all*, and it happens to
contain one gallery whose order disagrees with the alphabet. Issue #35 is about
the order specifically, and a fixture whose two orders agree passes with the
defect fully in place — which is how six connectors could each carefully rank
their pictures and nobody noticed the ranking never arrived. So the
disagreement here is chosen, stated, and asserted by the test itself
(`test_the_fixture_actually_disagrees_or_this_whole_file_proves_nothing`)
rather than left to luck.

## What the three products are for

| id | pictures | why |
|---|---|---|
| 8931923394860 | 7 | The shop leads with `FHSDK47-6.jpg`, which sorts **7th of 7** alphabetically — the shop's first is the alphabetically **last**. A filename sort cannot hide in this product. |
| 9718091219244 | 3 | The two orders **agree** (`212620-1/-2/-3.png`). Guards the opposite mistake: the fix must restore the shop's order, not reverse or shuffle. |
| 10157311557932 | 1 | The common case. No ordering question exists, and it must come out untouched. |

The demonstrator's gallery, in the order the shop publishes it:

```
1. FHSDK47-6.jpg     <-- the shop's own first; sorted alphabetically it is 7th
2. FHSDK47-15.jpg    <-- what the card showed instead
3. FHSDK47-23.jpg
4. FHSDK47-24.jpg
5. FHSDK47-1_2.jpg
6. FHSDK47-2_2.jpg
7. FHSDK47-3_2.jpg
```

## The census the choice was made from

Pages 1–3 of the catalogue, 750 products:

| | count |
|---|---|
| products read | 750 |
| publish more than one picture | 53 (page 1 alone) |
| of those, first picture **not** the alphabetically first | **31 of 53 on page 1** |
| publish exactly one picture | 475 |
| galleries already in alphabetical order | 37 |

So on this shop the read-side defect changed the displayed picture for roughly
three in five multi-picture products, and could not affect the 475 with one.

## Not captured, deliberately

Shopify's `products.json` states no alt text at all on this shop (1,442 of
1,442 null, measured 2026-07-30), so there is no caption to pair and nothing
was translated or invented — the file name stands in as the label, exactly as
`shopify.py:212` already does.
