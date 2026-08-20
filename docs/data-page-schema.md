# What the Data page shows, and where

The column tables below are GENERATED from `scrapex/reports.py` by
`python -m scrapex.cli export-version`. Do not hand-edit them: the code is the
truth and this is its readable form. The prose is hand-written, because those
are the owner's rulings and nothing derives them.

The owner asked to review the schema of the Data page: what belongs in the
table at the top, what belongs in the container that opens underneath when a
row is selected, and what a language switch governs. This file is the ruling,
so the answer stops being re-decided per screen.

## The table, in reading order

**The table answers "how do these compare?"** — what you scan across many
rows at once and sort, filter or group by. Identity, then the offer, then the
filing: the price is the reason the table exists, so nothing files in front
of it.

**Identity** — which thing this row is

| column | what it means |
|---|---|
| Product name | The product's name in English, where the source publishes one. |
| Product name (AR) | The same name in Arabic, where the source publishes one. |
| Country code | The country the price applies to, as an ISO 3166-1 alpha-2 code. |
| Variant | Which variation this row is, in English. |
| Variant (AR) | The same variation in the site's own Arabic words. |
| SKU | The source's own code for this item. |
| Display method | How the site itself presents this product, in its own terms: `single` for one product with one price, `options_priced` where each option carries it… |

**The offer** — what it costs and on what terms

| column | what it means |
|---|---|
| Price | What a visitor actually pays today. |
| Trade price | The price for trade or wholesale buyers, where the source publishes a second one beside the retail price. |
| Price (USD est.) | An approximate US-dollar figure, so many currencies can be ranked in one column. UNDER REVIEW — the owner has flagged this column for a decision: t… |
| Previous price | The price that held immediately before the current one. |
| Price change | The move from that previous price to this one. |
| Lowest price | The lowest price ever recorded for this record. |
| Highest price | The highest price ever recorded for this record. |
| Discount | How much the listing takes off, as an amount. |
| Discount % | The same discount as a percentage. |
| Unit | What one price BUYS: a litre, a 50 kg bag, a 100 m roll. Empty when the source states no unit — never guessed. |
| Minimum quantity | The smallest amount the shop will sell at this price. Cement is 450 bags: below that the price on the row is not obtainable at all. Blank means the… |
| Quantity step | The step the shop sells in. Rebar moves in 0.05 of its basis and cement in whole pallets of 450, so a quantity between two steps cannot be ordered.… |
| Stock count | The shop's own count of what is left, where it publishes one. A published 0 is a fact and is shown as 0; a blank means the shop said nothing, and t… |
| Availability | In stock or out, as the source states it. |
| Tax | Whether THIS figure includes tax, and at what rate. |

**The filing** — where the shop files it

| column | what it means |
|---|---|
| Brand | The brand, as the source publishes it — never inferred from the name. |
| Brand (AR) | The same brand in Arabic, where the source publishes one. |
| Category | The full classification path the source files this product under, in English where it publishes one. |
| Category (AR) | The same path in Arabic, where the source publishes one. |
| Category leaf | — |
| Category leaf (AR) | — |
| Category L1 | — |
| Category L1 (AR) | — |
| Category L2 | — |
| Category L2 (AR) | — |
| Category L3 | — |
| Category L3 (AR) | — |
| Category L4 | — |
| Category L4 (AR) | — |
| Category L5 | — |
| Category L5 (AR) | — |
| Category L6 | — |
| Category L6 (AR) | — |
| Category L7 | — |
| Category L7 (AR) | — |
| Category L8 | — |
| Category L8 (AR) | — |
| Category L9 | — |
| Category L9 (AR) | — |
| Category L10 | — |
| Category L10 (AR) | — |

**Provenance** — where the row came from, and when it was last true

| column | what it means |
|---|---|
| Observations | How many times this price has been recorded. |
| Price changed on | When the price last MOVED. |
| Last confirmed on | When a completed run last saw it still true. |
| Official source | The body the source attributes its figure to. |
| Curation | Your own review state for this product. |
| product_link | The product's page on the site — the arrow opens it, and the export carries the full address. |

Category levels are generated: `CATEGORY_LEVELS = 10`,
so raising the ceiling is one line and this table follows it.

## The container, and what is filed where

**The container answers "what is this one thing?"** — what describes a single
record and would be noise repeated eighty-seven times.

| group | |
|---|---|
| Description | |
| Specifications | |
| More information | |
| Store | |
| Site metadata | |
| Attachments | |
| Media | |

Selecting two or more rows turns the same container into a **comparison** of
them, marking the fields that differ.

## The rules behind it

1. **A column's name states the language of its content — in display and in
   storage.** English is the primary display language, so an unmarked column is
   English and Arabic lives in one marked `ar`. A source that publishes only
   Arabic fills only the marked column, and its single visible column reads
   `Record (AR)`, because the label describes the content, not the presence of
   a counterpart.
2. **One language at a time.** The AR|EN switch governs the table AND the
   container. Printing both languages side by side in the cards under the table
   is the same fact twice, not more detail.
3. **A missing translation shows the fact, never a blank.** Where a source
   published only one side of a pair, that side is shown under a heading that
   names its language.
4. **Presence is per source.** A column appears only where that source's own
   rows fill it — no global gate. A shop with no geography shows no Country
   column; a source with no variations gains no axis columns.
5. **The owner moves fields between the two places.** Choose Columns has two
   zones; hiding a field moves it into the container rather than losing it. It
   is reachable from the side panel and from the web page, and both write the
   same order — the panel is the control room, and nothing it cannot do may
   live on the page.
6. **An order you arranged is yours.** Until you move a column, the table shows
   the agreed order above and we may improve it. The moment you do, that
   arrangement wins on every surface and no update replaces it. Each screen
   says which of the two you are looking at.
7. **Nothing is computed into a price.** Every figure is what the source
   published; the Tax column states, per row, whether that figure includes tax.
   Where a shop names a container and what is in it — «4 كجم/صندوق» — both are
   stored, and a price per kilogram is arithmetic over two stated facts rather
   than a rewrite of one.

## What an export carries

The Excel download is not the view — it is the whole record: a `prices` sheet,
a `details` sheet, a `history` sheet and an `about` sheet naming the source,
the export time, the counts and what each sheet is. CSV and JSON stay the view
you are looking at, filters and column order included.

