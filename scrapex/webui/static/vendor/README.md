# Vendored third-party assets

Files here are **committed on purpose**, not fetched at runtime.

ScrapeX is a local-first tool. It has to work on a machine with no internet, and
a page that quietly loads a library from a CDN would fail exactly when the owner
is offline — the one condition the product promises to survive. It would also
mean a third party could change what runs on the owner's machine without a
commit. So the bytes live in the repository, and updating them is a visible,
reviewable change.

## tabulator-tables 6.5.2

- Source: <https://unpkg.com/tabulator-tables@6.5.2/dist/>
- Licence: MIT — full text in `tabulator.LICENSE.txt`
- Dependencies: **none**
- Vendored: 2026-07-21
- `tabulator.min.js` 435.5 KB, sha256 `04802e757fa41893…`
- `tabulator.min.css` 27.8 KB, sha256 `b55e204b2f968cec…`

Used by **the Datasets page only** (`templates/datasets.html`), which browses the
General database's runtime-discovered schemas. It is deliberately NOT used by the
MarketLens Data page (`templates/source.html`): that page's value is that its URL
is the question — filters, sort and paging live in the query string, so a link
can be shared and still means the same thing a week later, and the whole page
works with scripting off. A grid that holds its state in memory would trade that
away for column resizing.

AG Grid Community was measured against it on 2026-07-21 and rejected: 2,072 KB
against 463 KB, two transitive dependencies against none, and — decisively — its
set filter, master/detail row expansion, row grouping, Excel export and range
clipboard are all Enterprise-gated. Those are precisely the features that would
have justified taking a library at all.

## Updating

1. Download the new files from unpkg at a pinned version.
2. Record the version, date, sizes and hashes above.
3. Run the test suite: `tests/test_vendor.py` fails if a file goes missing, is
   truncated, or loses its licence text.
