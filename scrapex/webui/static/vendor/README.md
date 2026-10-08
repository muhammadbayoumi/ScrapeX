# Vendored third-party assets

Files here are **committed on purpose**, not fetched at runtime.

ScrapeX is a local-first tool. It has to work on a machine with no internet, and
a page that quietly loads a library from a CDN would fail exactly when the owner
is offline — the one condition the product promises to survive. It would also
mean a third party could change what runs on the owner's machine without a
commit. So the bytes live in the repository, and updating them is a visible,
reviewable change.

## TanStack Table and TanStack Virtual (`tanstack/`)

| package | version | npm integrity |
| --- | --- | --- |
| `@tanstack/table-core` | 9.2.5 | `sha512-HCMUpaEBEBS9AkV44sdTDmNgFrAA6H4NAnUgwuoWN7IkPgwXWlf3bfZ0moyxLwZqQXdpNQZdEl7LMW4rqm9zQQ==` |
| `@tanstack/store` | 0.11.2 | `sha512-sJ4mjol8uQsHV0gOJzzjwXfh2Fwm+Sz0+8deqiTm4jGbMdjzNSW+xZCFm0kUa870uhd8yi+DpKnZb5Kc4apa0Q==` |
| `@tanstack/virtual-core` | 3.17.11 | `sha512-+ILjvtHup6Y2hzQ6YzwMgX1Q+oQpxEGOXCEsCNaPoIP0VxMbizIBTmYTDtkerkIQS8/CbP1BRuyt8V/8BCsy1g==` |

- Licence: MIT for all three — each package's `LICENSE` travels in its directory.
- **Nothing loads them yet.** They are for `datagrid.js`, the grid's renderer,
  which replaces Tabulator below (#1342). The extension carries the **second
  copy** in `extension/vendor/tanstack/`; the two copies are held byte-identical
  by `tests/test_vendor.py`.
- Chosen over Tabulator, AG Grid and react-data-grid in #1342: Supabase's
  design system builds its Data Table on TanStack and says its tables are
  converging there, and the owner will not pay for AG Grid's Enterprise licence.

The files are **not** npm's bytes exactly. `tools/vendor_tanstack.py` checks each
tarball against the integrity above, keeps only the modules the grid's entry
points reach, and makes three rewrites, because a browser cannot load the
published files as they are:

1. `"@tanstack/store"` becomes the relative path of the vendored store. A browser
   resolves a bare name only through an import map, and the extension's MV3
   policy refuses an inline one.
2. `process.env.NODE_ENV` becomes `"production"`, as a bundler would write it;
   `process` does not exist in a page.
3. The trailing `//# sourceMappingURL=` line goes, because the maps are not vendored.

## tabulator-tables 6.5.2 — being replaced (#1342)

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

**TanStack:**

1. Change the pinned versions and integrities in `tools/vendor_tanstack.py`.
2. Run `python tools/vendor_tanstack.py`. It writes **both** copies.
3. Update the table above and run the test suite, browser tests included:
   `tests/test_vendor.py` fails if a module is missing, the copies diverge, a bare
   import or a `process` read survives, or a licence is lost.

**Tabulator** is not updated again; it leaves once the grid draws through TanStack.
