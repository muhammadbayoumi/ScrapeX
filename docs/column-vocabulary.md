# One name per column

Owner-approved 2026-07-25. Until now a column had up to three names: a key in
the payload, a different key in the export, and a display label that matched
neither — `product_name` was headed "Record", `region` was headed "Country"
while the export ALSO had a `country`, and `curation_status` was "Curation".
The reader had to learn a private vocabulary to use their own spreadsheet.

Two rules produce every name below:

1. **The key and the label are the same word.** The label is the key written
   for a person: `price_previous` → "Previous price". No display-only word
   (Record, Status, Source) may stand in for a field's name.
2. **The name states the language of the content.** English is the primary
   display language, so the unmarked name is English and Arabic is marked
   `_ar` — in the table, in the export and in storage. A source that publishes
   only Arabic fills only the `_ar` column and its heading says so, because the
   label describes the content, not the presence of a counterpart.

## The map

| today | key | label |
|---|---|---|
| `product_name` (Arabic, headed "Record (AR)") | `product_name_ar` | Product name (AR) |
| `product_name_en` (headed "Record") | `product_name` | Product name |
| `region` (headed "Country") | `country_code` | Country code |
| `country` (export only) | `country` | Country |
| `brand` | `brand` | Brand |
| `category_en` | `category` | Category |
| `category` (Arabic) | `category_ar` | Category (AR) |
| `category_en_l1`…`_l4` | `category_l1`…`_l4` | Category L1…L4 |
| `category_l1`…`_l4` (Arabic) | `category_l1_ar`… | Category L1 (AR)… |
| `option_label` (headed "Variant") | `variant` | Variant |
| `sku` | `sku` | SKU |
| `product_id` (export only) | `product_id` | Product id |
| `effective_price` (headed "Price") | `price` | Price |
| `regular_price` | `price_before` | Price before |
| `sale_price` | `price_sale` | Sale price |
| `usd_price` | `price_usd` | Price (USD est.) |
| `previous_price` | `price_previous` | Previous price |
| `price_change` | `price_change` | Price change |
| `min_price` / `max_price` | `price_min` / `price_max` | Lowest price / Highest price |
| `discount` (one text cell) | `discount` + `discount_pct` | Discount · Discount % |
| `unit` | `unit` | Unit |
| `currency` | `currency` | Currency |
| `availability` (headed "Status") | `availability` | Availability |
| `tax_label` (headed "Tax") | `tax` | Tax |
| `vat_included` | `tax_included` | Tax included |
| `tax_evidence` | `tax_evidence` | Tax evidence |
| `tax_rate_pct` | `tax_rate_pct` | Tax rate % |
| `tax_statement_url` | `tax_statement` | Tax statement |
| `observations` | `observations` | Observations |
| `price_changed_on` | `price_changed_on` | Price changed on |
| `last_confirmed_on` | `last_confirmed_on` | Last confirmed on |
| `official_source` | `official_source` | Official source |
| `official_source_url` | `official_source_link` | Official source link |
| `curation_status` (headed "Curation") | `curation` | Curation |
| `open` (blank heading) | `product_link` | *(icon only)* |
| `product_url` (export only) | `product_link` | Product link |

The whole price family shares the `price_` prefix, so it reads and sorts
together instead of scattering between `effective_`, `regular_`, `min_` and
`usd_`.

## Per-source columns

Two kinds of column are named by the SITE, not by this table, and appear only
for the sources that publish them:

- **variation axes** — one per axis a source varies by (`Color`,
  «السماكة (مم)»), from the connector's structured axes.
- **site filters** — one per attribute the source itself filters by, from the
  site's own facet list.

Where a source both filters by an attribute and varies by it, the variant's own
value wins: the product-level attribute describes the family.

## What this costs, and it is paid once

- The export header changes, so a Google sheet is rewritten with new headings.
- Saved views and hidden-column choices are stored under the old keys and need
  migrating with the rename.
- The payload contract carries `product_name`, whose CONTENT flips from Arabic
  to English while its NAME stays. Nothing fails loudly on that by itself, so
  the payload version bumps and v1 payloads are refused rather than read wrong.

Which is why this lands as ONE change with the `_ar` inversion, not two
consecutive rewrites of the same contract.
