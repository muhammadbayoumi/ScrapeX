# What the Data page shows, and where

The owner asked to review the schema of the Data page: what belongs in the
table at the top, what belongs in the container that opens underneath when a
row is selected, and what a language switch governs. This file is the ruling,
so the answer stops being re-decided per screen.

## The split

**The table answers "how do these compare?"** It holds what you scan across
many rows at once and sort, filter or group by:

| | |
|---|---|
| identity | Record (name), Record (AR), SKU, product id, Brand, Country |
| classification | Category and every level the source publishes (L1–L4) |
| the offer | Price, Unit, Discount, Status, Tax |
| the variation | Variant, and one column per AXIS the source varies by |
| the site's own facets | one column per attribute the source FILTERS by |
| provenance | Price changed, Last confirmed, Curation |

**The container answers "what is this one thing?"** It holds what describes a
single record and would be noise repeated eighty-seven times:

| | |
|---|---|
| pictures | every image the source publishes, the gallery leading |
| description | the short one and the long one, as the source's own paragraphs |
| specifications | the site's own "technical specifications" card |
| attachments | datasheets and other files, with their real size |
| measurements | weight, stock, thresholds |
| the price story | the change timeline, the change feed, every observation |

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
   zones; hiding a field moves it into the container rather than losing it.
6. **Nothing is computed into a price.** Every figure is what the source
   published; the Tax column states, per row, whether that figure includes tax.

## What an export carries

The Excel download is not the view — it is the whole record: a `prices` sheet,
a `details` sheet, a `history` sheet and an `about` sheet naming the source,
the export time, the counts and what each sheet is. CSV and JSON stay the view
you are looking at, filters and column order included.
