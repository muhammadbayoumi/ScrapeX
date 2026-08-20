# The Data Page — build document

**Verdict:** build **The Watchboard** (opsroom), with five grafts. Everything below is grounded in files I opened; where a judge's claim was wrong I say so.

---

## 1. What survives, and from where

| Kept | From | Why it survived |
|---|---|---|
| **Metric tile `href` IS the filtered table URL** (`?view=stale`) | Watchboard | All 12 judge-lenses named this best-idea or equivalent. One filtering mechanism, bookmarkable, screen-reader-native because it is an `<a>`. |
| **`form="browse"` form-owner attribute** — one `<form method="get">` before the table, every header filter input carries `form="browse"` | *The Header Is The Control Panel* | Per-column filters with **zero JS** and a shareable URL. Owner-lens and skeptic both called it the only genuine invention in that design. Grafted wholesale. |
| **`FILTERABLE` as the single allow-list, `SORTABLE` derived from it** | *Views First* | One object cannot drift from itself. Today `SORTABLE` (reports.py:201-208) has only 6 keys — `last_confirmed` and `curation_status` are silently unsortable. Deriving fixes that as a side effect. |
| **Answer line: `38 of 721 records` + one removable pill per active filter** | *Views First* | Excel hides filter state behind identical funnel glyphs. Pills are what makes a shared link legible. |
| **`History · 3 prices` — the period count on the row** | *Ledger Grid* | Most offers have no story (`_offers_with_history` exists for exactly that reason, app.py:872). The count answers "which of these 721 moved?" by scanning, not by opening 50 dialogs. |
| **`computed — not filterable` marker on derived columns** | *Ledger Grid* | Honest about Tax/Unit instead of a dead box. |
| **Keep the search box, renamed "Find anything"** | *Ledger Grid* | `_browse_filters` (reports.py:180-196) matches name **OR** region code **OR** the English country name via `region_code()`. No single-column filter can do that. It is not a duplicate. |
| **Never silently repair a stale saved view; a dropped *filter* is escalated above a dropped *column*** | *Views First* | A dropped filter makes the answer **bigger** than the question. That is a lie; a missing column is only a gap. |

---

## 2. The owner's 8, answered by name

**1. Edit toggle on the column heads (X to remove, drag to reorder, drag to resize)**
**As asked, minus resize.** The toggle ships (`<button aria-pressed>Edit columns</button>`), the `<details>` panel at source.html:33-77 is deleted, each `<th>` grows `✕ Hide` + `◀ ▶` + a drag handle. Buttons are the implementation; drag calls the same function.
**Resize is cut from v1** — not taste, mechanics: base.html:59-64 sets `table{width:100%;border-collapse:collapse;overflow:hidden}` and `th{white-space:nowrap}` with **no `table-layout:fixed`**, so `<colgroup>` widths are advisory and will be overridden on exactly the wide columns you'd want to resize. Switching to `table-layout:fixed` reflows every table in the app. Every judge who examined resize named it the worst idea in its design (three separate designs, three separate reasons). `.tablewrap{overflow-x:auto}` already solves the width pain. Revisit as its own change with a rendered proof.

**2. Kill the top filter, filter per column like Excel**
**Better:** per-column filters yes — but **typed**, and the search box stays (renamed *Find anything*). A `<select>` only where the schema bounds the domain (availability, curation_status — CHECK-constrained; region — ISO). Free-text columns get `<input type=search>`. Excel's dropdown is a distinct-value list over the whole column; at 40k a shop's product-name column has ~40k values, and building that list is the unbounded read A8 forbids. Two columns say **`computed — not filterable`**: `unit` (reports.py:251, `price_unit()` in Python) and `tax_label` (reports.py:254, `tax.resolve()` in Python with region→wildcard fallback and `valid_to IS NULL` temporality). Neither exists as a SQL expression and reimplementing `resolve()` in SQL is a correctness trap.

**3. Empty columns must not appear by default**
**Better — and half of it already works, which you may not know.** `column_presence()` (reports.py:283-309) is why GPP_ENERGY shows 8 columns not 11; `option_label`/`sku`/`availability` were swept, with `'unknown'` deliberately counted as absent (reports.py:299-301). What is broken is the **second** case: `ensure_fields` is additive (fields.py:33-35) and app.py:242-247 filters `shown` against `BROWSE_COLUMNS`, **not** against presence — so a column that goes empty later renders em-dashes forever. Fix: intersect presence at render time (`present` is already computed every request at app.py:235 — zero new queries), and state it: *"3 columns are hidden because this source publishes nothing in them: Variant, SKU, Status. Show them."* **Refused:** writing `is_hidden=1` at seed time. `dataset_field` (0008) has no provenance column, so an auto-hide becomes indistinguishable from your decision, permanently — and a source seeded while still empty would hide almost everything.

**4. Obvious pagination + rows-per-page**
**As asked.** `First · Previous · Page 3 of 15 (rows 101–150 of 721) · Next · Last` + `Rows per page [25/50/100/200]`. 200 is not arbitrary — it is the cap `browse_observations` already enforces (reports.py:228). The selector is generated *from* that cap; the route clamps too.

**5. An icon on every row that opens its price history**
**Better:** a **labelled** control `History · 3 prices` (or `No change yet`, not a link) that is a real URL — `/source/{key}/offer/{offer_id}` — server-rendered. JS upgrades it to an inline expanding row over the existing `GET /api/prices/timeline` (app.py:1160). Reason it has never worked: `browse_observations` selects 16 columns (reports.py:234-237) and **`so.offer_id` is not one of them** — the row has no identity to ask history about. One SELECT field unlocks `pricehistory.timeline()` (pricehistory.py:175), live since 0016 with no reader.

**6. Title: English name, site, Arabic beneath**
**As asked, with one honest blocker.** There is no English name anywhere: `source_site.source_name` **is** the Arabic one (schema.sql:96; sources.yaml:198 = `أسعار الطاقة العالمية`). Needs an optional `source_name_en` on `SourceEntry` (config.py, `extra="forbid"` so it must be declared) + migration **0020** (0019 is taken: `0019_price_provenance.sql`). **Fallback is the Arabic name with `dir="auto"`, not the source_key** — a skeptic caught the regression, and source.html:4-5 already prescribes exactly that treatment. `base_url` also needs adding: `source_summary` selects only `source_id, source_name` (reports.py:33).

**7. Summary metrics clickable, drilling into the data**
**Better:** the four metrics you have today cannot drill. This table is one row per **offer**; `Price observations` counts history rows and `Matched (unified)` counts unified-layer matches (reports.py:61-68) — wiring them as filters produces a count that disagrees with the table. Split into **row filters** (each an `<a>` to a filtered URL) and **warehouse facts** (plain text linking to `/changes`, `/review`, labelled as going elsewhere).

**8. Feel like an operations room**
**Better:** lead with *"is what I'm reading current?"*, not *"what changed"*. `last_run`/`last_status` are computed into `SourceSummary` (reports.py:55-59) and rendered **nowhere** on this page — today it shows 721 rows with no hint whether the last crawl succeeded or ran last month. One line of Jinja over data already in hand. Movement tiles are real but grow into prominence as history accumulates; with essentially one crawl, source.html:169 already prints `same day` on every row, so a trend headline would be a flat line dressed as insight.

---

## 3. The design

### Page, top to bottom

1. **Identity block** — `<h1>` English name (LTR) · line 2: `globalpetrolprices.com` link + `<span class="key">GPP_ENERGY</span>` · line 3: Arabic name, muted, `dir="auto"`. Right-aligned: **`Last run 2 hours ago — completed`** / `Last run failed — 3 errors`.
2. **Watch strip** — five tiles, each an `<a href="?view=…">`, ordered by *needs me*. A zero tile renders greyed, count 0, **not a link**, reading `0 stale — all confirmed`. A vanished tile is indistinguishable from one someone forgot to build.
   | Tile | Source | Note |
   |---|---|---|
   | Moved (7 days) | `price_period.first_detected_at >= cutoff AND opened_because='price_change'` (0016:40-59) | **Third state required**: `price_period` is derived and only populated by `POST /api/prices/rebuild`. When it is empty for the source the tile reads **`Price history not built yet — Rebuild`**, never a bare 0. |
   | Not confirmed | `offer_state.last_confirmed_at` vs manifest cadence | `ost` is a **LEFT JOIN** (reports.py:102-103, "an offer whose state has not been derived yet still has a price"). NULL state is **`state not derived`**, counted separately, never folded into "confirmed". Otherwise the staleness signal under-reports staleness. |
   | Missing | open `absence_period` (0016:69-80), served by `ux_absence_period_open` | |
   | Needs curation | `summary.curation['inventoried']` (reports.py:50-54) | already computed, zero new query |
   | Last run | `crawl_run` | links to `/history?source_key=` |
   **Tax-unverified tile: cut.** It needs a `GROUP BY so.region` over `_LATEST_PER_OFFER` crossed with `tax.resolve()`'s fallback in Python, added to a page that already fires the correlated COUNT. Not before the spine is measured.
   Under the strip: one server-generated English sentence. Clean state: *"Nothing needs you. 721 offers, all confirmed by the run that finished 2 hours ago."*
3. **Warehouse facts** — one quiet text line: `Products 721 · Variants 721 · Price observations 5,412 → Changes · Matched 12 → Review queue`.
4. **Toolbar** — Find anything · saved-view `<select>` · Rows per page · `Edit columns` toggle · Apply · Reset.
5. **Answer line** — `38 of 721 records` + `<ul>` of pills, each a link named `Remove filter: Country is Egypt`, then `Clear all`. Present even when empty (`721 records · no filters`) so its absence never means "I forgot to look".
6. **Table** — `.tablewrap > table`. `<thead>` **row 1** = labels + sort links (+ edit-mode controls when the toggle is on). `<thead>` **row 2** = the filter row.
7. **Pager** + rows-per-page echoed.

### The three structural rules

**R1 — One form owns everything.** A single `<form id="browse" method="get" action="/source/{key}">` sits before the table with hidden inputs for `sort/direction/per_page/view`. Every filter control lives in its `<th>` and carries `form="browse"`. Enter anywhere submits all of them. **Filtering involves no JavaScript at all.**

**R2 — No popup, no panel, no second sticky layer inside `<thead>`.** `table{overflow:hidden}` (base.html:60) nested inside `.tablewrap{overflow-x:auto}` (base.html:81) clips any `<details>` opened from a `<th>` — two nested clipping contexts. And `thead th{position:sticky;top:0}` (base.html:74) applies to **both** header rows, so a second row would pin over the first; base.html:65-73 is a comment written about being burned by exactly this. Therefore: the filter row is **inline controls in a second header row, sticky disabled on that row** (`thead tr:nth-child(2) th{position:static}`), verified by rendering before the rest is built.

**R3 — One query-string builder.** `sortlink` (source.html:87-92) hand-concatenates `?q=&availability=&sort=&direction=` and already **drops `page`**; the pager base (source.html:183-184) does the same. With ~15 `f.*` params every sort click would silently discard your filters. **Slice 3 ships `build_query(**overrides)` first**, and the sort links, pager, tiles, chips and Reset all route through it. Nothing else in that slice is written until it exists.

### URL grammar and precedence

```
q=            free search (exists today)
f.<key>=<op>:<value>   one per filtered column
sort= direction=       exists today
per_page= page=
view=<token>           closed allow-list: all|stale|moved|missing|curation|failed
view_id=<n>            a saved view
```
**Operators** are a closed dict of SQL templates; the value is always a bound parameter: `has:` `is:` (comma = IN) `gte:` `lte:` `after:` `before:` `last:<n>d`.

**Precedence, stated once:** `view_id` supplies defaults → `view` token overlays its filter set → an explicit `f.*`/`sort`/`per_page` in the URL always wins. `view` and `view_id` together: `view_id` is the base, `view` narrows it. A `?view=stale` link **bakes the resolved absolute cutoff date into the URL** on first render (`f.last_confirmed=before:2026-07-12`) so a bookmark still means what the pill says a week later. Legacy `availability=` (app.py:220) is accepted and translated to `f.availability=is:` once, then dropped from the emitted URL — never both.

**Stale keys.** A `view_id`'s `config_json` may name a column this source no longer publishes. A dropped **column** is listed: *"2 columns in this view no longer exist here: SKU, Variant."* A dropped **filter** is escalated: *"1 filter was dropped — this shows more rows than the view asks for."* If nothing survives, fall back to the seed and say so. Unknown keys never reach SQL — same guarantee as `SORTABLE`.

### Server changes

1. **`reports.py:234-240`** — append `so.offer_id`; **`:243-256`** — `"offer_id": r[16]`. Two lines. The single blocker for item 5.
2. **`reports.py:201-208`** — `FILTERABLE: dict[key -> (sql_expr, kind)]`, `kind ∈ {text, exact, number, date}`; `SORTABLE = {k: v[0] for k, v in FILTERABLE.items() if v[1] != 'derived'}`. `region` maps to `so.region` **but the value is passed through `region_code()`** (reports.py:160-177) first, so typing "Egypt" — the only string on screen (source.html:116-118 renders `region_name`) — actually matches. `unit` and `tax_label` are marked `derived` and are neither filterable nor sortable.
3. **`reports.py:180-196`** — `_browse_filters(search, availability, columns)` iterates `FILTERABLE.items()`, never the caller's dict. Same `(clause, params)` contract, so the page query and the COUNT (reports.py:229-238) still cannot diverge.
4. **`reports.py`** — `boolean` params `moved_since` / `missing` on `browse_observations`, applied as `EXISTS` subqueries over `price_period` / `absence_period`, to **both** the page and COUNT queries. `?view=moved` and `?view=missing` are not column filters and are not pretended to be.
5. **`reports.py`** — `facet_options(conn, source_key, key, limit=200)` for the three CHECK/ISO-bounded columns only. Called once per request, results memoised into the template context.
6. **`reports.py`** — `watch(conn, source_key)`: **one** query with `SUM(CASE WHEN …)` over the shared join for the offer-scoped tiles, plus one over `price_period` and one over `absence_period`. Not five separate `COUNT(*)`s over the correlated subquery.
7. **`reports.py`** — `history_counts(conn, offer_ids)`: one bounded `GROUP BY offer_id` over `price_period` for the ≤200 offers on the page. This is where `History · 3 prices` comes from; it is not free and it is budgeted here.
8. **`reports.py:33`** — widen `source_summary`'s SELECT to include `base_url` and `source_name_en`.
9. **`app.py:219-261`** — reads `request.query_params` for `f.*` (typed FastAPI args cannot express N filters), clamps `per_page`, resolves `view`/`view_id`, passes `watch`, facets, pager, `present`.
10. **New route `GET /source/{source_key}/offer/{offer_id}`** — server-rendered timeline over `pricehistory.timeline` + `price_on` + `reports.price_extremes`. **Verifies the offer belongs to that `source_key` before rendering**, so the URL cannot be walked into another source's history.
11. **Migration 0020** — `source_site.source_name_en TEXT NULL`. **Migration 0021** — `ix_price_period_detected ON price_period(first_detected_at)` (`ix_price_period_offer` is offer-first and cannot serve the Moved range scan). Two migrations, not one: a schema field and an index have different risk.

### Accessibility (spec 36, CLAUDE.md:1458-1475 — the brief's "section 28" is Apps Script security)

- **Two tab stops per column, maximum**: sort link, then the filter control. Edit-mode controls (`✕`, `◀`, `▶`) exist **only while the toggle is pressed**, so the resting tab path is 2×N, not 4×N. `Skip to results` is the first focusable element.
- **Announcements survive the reload.** Filtering, hiding and reordering are full page loads, which destroy a live region before its content arrives. So: the message is carried in the redirect and rendered into a **status region that exists at parse time** (`<p role="status" tabindex="-1">`), and the route sets `?focus=<field_key>` so focus is explicitly restored to the same control after a reorder. "Focus is restored" is not left to chance.
- **Arabic as data everywhere text and values concatenate** — not just the h1. Filter chips, the status sentence and `<option>` labels wrap the value in FSI/PDI (`&#x2068;…&#x2069;`), which changes.html:16 already does. `source_key`, URLs and ISO codes stay forced LTR.
- **No colour-only status** anywhere: status is a word (already true, source.html:139-142), sort is `▲/▼` + `aria-sort` **moved onto the `<th>`** (today it sits on the `<a>` at source.html:90, where it is meaningless), edit mode is `aria-pressed` plus visible controls, the active tile is the pill above the table.
- **History control**: `<button aria-expanded aria-controls>` with a text label; Escape collapses and returns focus. With JS off it is an `<a>` to a page that actually exists — **not** `/changes?offer=`, which takes no such parameter (app.py:271-272) and renders its timeline only via `fetch` (changes.html:11-26).

### Scale — 721 today, 40k for a shop census

Nothing loads a row set into the browser. Page reads stay ≤200 (reports.py:228). Selects appear only where the schema bounds the domain. Facets are computed once per request. Deep `OFFSET` is accepted, not fixed: keyset needs a unique sort tiebreak and `_order_by` tiebreaks on `(source_name, region)`, which is not unique — and with a 200-row cap the worst case is page 200. Past page 20 the pager says so: *"Deep pages get slower. Filter a column to get there faster."*

**Explicitly deferred: the `_LATEST_PER_OFFER` → `offer_state` spine swap.** `offer_state` is derived and rebuildable (0016:12-15), reports.py:102-103 documents in plain English why it must stay a LEFT JOIN, and it carries **no `business_date`** — which is the "Price changed" column (reports.py:273) and a sortable key. A spine built from it silently drops every ingested-but-not-rebuilt offer from both the page and the count. If the COUNT becomes the bottleneck, the answer is a covering index and a measurement, not a semantics change smuggled into a UI ticket.

---

## 4. Judges' `must_fix` ledger

Every distinct item raised across all four designs and twelve lenses. **F** = fixed above, **R** = refused with reason.

| # | Issue | |
|---|---|---|
| 1 | Ship as sequenced slices, not one slab | **F** §5 |
| 2 | Column width persistence broken / `colgroup` advisory / `table-layout:fixed` regression / widths in `config_json` vs localStorage / debounced `replaceState` | **R** — resize cut from v1 |
| 3 | "Moved 7d" ambiguous when `price_period` unbuilt | **F** third state |
| 4 | `?view=` must be a closed allow-list with stated precedence | **F** |
| 5 | Write the FILTERABLE injection test **before** FILTERABLE (mirror of tests/test_workspace.py:192-197) | **F** slice 3 gate |
| 6 | `sortlink` + pager drop filters → one query-string helper | **F** R3, ships first in slice 3 |
| 7 | Retract "item 3 already works" — `shown` filters against `BROWSE_COLUMNS`, not presence | **F** render-time intersect |
| 8 | Stale saved-view key policy; drop-rule; what the UI says | **F** |
| 9 | Live-region announcements cannot survive a full reload | **F** status region + `?focus=` |
| 10 | Arabic FSI/PDI in chips, options, status text | **F** |
| 11 | Don't add a `GROUP BY` caller to the slow path before measuring | **F** tax tile cut, tiles in one pass |
| 12 | Bake resolved dates into `?view=` URLs or stop claiming bookmarkable | **F** |
| 13 | Tax/Unit not filterable — derived in Python | **F** explicit marker |
| 14 | `?view=moved`/`missing` need EXISTS predicates with COUNT parity | **F** |
| 15 | Don't triplicate the timeline renderer | **F** extracted to `/static/timeline.js`, slice 1 |
| 16 | Focus restoration across the reorder round-trip | **F** `?focus=` |
| 17 | Guard `/source/{key}/offer/{id}` against cross-source walking | **F** |
| 18 | Popup/`<details>` in `<th>` is clipped twice | **F** R2 — no popups in thead |
| 19 | Two-row sticky `<thead>` pins the filter row over the labels | **F** R2 — row 2 static, verified by render |
| 20 | `base_url` is not on `SourceSummary` | **F** widen SELECT |
| 21 | Migration 0019 already taken | **F** 0020 + 0021 |
| 22 | Region filter matches `EG`, screen shows `Egypt` | **F** route through `region_code()` |
| 23 | `offer_state` LEFT JOIN → NULL state under-reports staleness | **F** third bucket |
| 24 | `dataset_field` holds two key vocabularies (EXPORT_HEADER app.py:570-571 vs BROWSE_COLUMNS app.py:236-237) | **F** slice 5 — `GET /api/fields` stops calling `ensure_fields` with the export header; browse is the only seeder |
| 25 | Per-row history count is unbudgeted | **F** `history_counts()`, one aggregate over the page's offer_ids |
| 26 | Facets bound output, not work | **F** three bounded columns, once per request, measured |
| 27 | No-JS history fallback to `/changes` is fiction | **F** real server page |
| 28 | Legacy `availability=` vs `f.availability=` | **F** translate once |
| 29 | `column_presence` per-load cost | **N/A** — it already runs every request (app.py:235); no new query |
| 30 | Title fallback to `source_key` regresses Arabic sources | **F** fallback = Arabic name, `dir="auto"` |
| 31 | Compare mode / `b.` prefix | **R** — nobody asked; doubles every URL builder, template and pane forever; two browser tabs already do it |
| 32 | Answer the datasets.html convergence question | **F** §6 |
| 33 | changes.html: whole timeline block inside `{% block title %}` (verified: line 2 opens the block and markup follows) | **F** slice 1 chore. Correction to one judge: `<title>` is RCDATA, so no duplicate DOM ids and no second script — the symptom is a tab title full of raw markup, not a mis-bound `getElementById` |
| 34 | Frozen first columns (`position:sticky;left:0`) | **R** — `border-collapse:collapse` (base.html:59) drops borders on sticky cells, `td` has no background so rows smear, and it is a fourth interacting sticky layer. Not worth it on 8 columns |
| 35 | "Modified view" detection needs a canonical normal form | **R for v1** — no auto-save at all, so there is nothing to detect. `Save as view` / `Update this view` are explicit buttons |
| 36 | Hidden-seed writes `is_hidden=1` permanently with no provenance | **R** — replaced by render-time presence (item 7) |
| 37 | 44 tab stops | **F** two per column at rest |
| 38 | `_CURRENT_OFFERS` / `offer_state` spine swap | **R/deferred** — see §3 scale |
| 39 | Every new metric tile needs a stated count source | **F** `watch()` |
| 40 | Virtualization / infinite scroll / client-side filtering | **R** — A8; and it destroys Ctrl+F, print, deep links, row counting |

---

## 5. Build order — each slice useful alone

**Slice 1 — Row price history.** *The biggest daily win, touches almost nothing.*
Changes: `reports.py` (+`so.offer_id`, +`history_counts()`), `app.py` (+`/source/{key}/offer/{offer_id}`), new `templates/offer.html`, `templates/source.html` (History cell), new `static/timeline.js` extracted from `changes.html:65-87`, `changes.html` (title-block fix + import the extracted renderer).
Reuses: `pricehistory.timeline` / `price_on`, `/api/prices/timeline` (app.py:1160), `reports.price_extremes`, the `opened_because → sentence` WHY map.
**Check:** a GPP_ENERGY row shows `History · 1 price`; clicking it with JS off loads a page listing the periods; `/source/GPP_ENERGY/offer/<id-from-another-source>` returns 404; the Changes tab's browser title reads `Changes — ScrapeX`.

**Slice 2 — Orientation: status line, identity, pagination.**
Changes: `reports.py:33` (+`base_url`), `app.py` (`per_page` clamp), `source.html` (identity block, `Last run …`, warehouse-facts line, full pager + rows-per-page).
Reuses: `SourceSummary.last_run/last_status`, `BrowsePage.has_prev/has_next/total`, the 200 cap.
**Check:** page reads `Last run … — completed`, `rows 101–150 of 721`, `Page 3 of 15`; `?per_page=40000` returns 200 rows.

**Slice 3 — Filtering. `build_query()` first, then the test, then the feature.**
Changes: `reports.py` (`FILTERABLE`, `SORTABLE` derived, `_browse_filters`, `facet_options`), `app.py` (`f.*` parsing, legacy `availability=` translation), `source.html` (filter row inside `form="browse"`, answer line + pills, all URLs through `build_query`), `tests/test_workspace.py` (+ the crafted-filter-key injection test).
**Check:** `?f.region=is:Egypt` returns Egyptian rows; sorting a filtered view keeps every filter and resets `page`; `?f.effective_price;DROP TABLE x--=1` is ignored and named in the "ignored parameters" line; the whole filter row works with JS disabled; Tax and Unit headers read `computed — not filterable`.

**Slice 4 — Watch strip.**
Changes: `reports.py` (`watch()`, `moved_since`/`missing` EXISTS params), `app.py` (`?view=` token resolution), `source.html` (tiles), migration 0021 (index).
**Check:** tile counts equal the row count of the page they link to, every time; with `price_period` empty the Moved tile reads `Price history not built yet — Rebuild`; a zero tile is not focusable.

**Slice 5 — Edit columns in the header.**
Changes: `source.html` (delete the `<details>`, add the toggle + per-`<th>` `✕ ◀ ▶` + `Show hidden columns` chips + the empty-column disclosure line), `app.py` (`?focus=`, stop `GET /api/fields` seeding EXPORT_HEADER keys), render-time presence intersect.
Reuses: `POST /api/fields/{key}` unchanged — **zero new endpoints**.
**Check:** hide a column by keyboard, hear the status line, restore it from the chip; reorder twice with Enter without losing focus; a column that goes empty disappears and is named in the disclosure line; `GET /api/fields` no longer registers `product_name`.

**Slice 6 — Saved views actually applied.**
Changes: `app.py` (`?view_id=` → defaults), `source.html` (view `<select>` navigates; `Save as view` posts the **full** payload — today source.html:244-248 posts `{columns}` and nothing else into a field documented at `0008_dataset_fields.sql:36` as `{columns, sort, filters}`).
Reuses: `save_view`/`list_views`/`delete_view` and both routes, unchanged. **No schema change.**
**Check:** save "Egyptian diesel", navigate away, reload it, get the same rows and columns; a view naming a now-absent column loads with the notice; `?view_id=N&sort=effective_price` sorts by price.

**Slice 7 — English name.** Migration 0020, `config.SourceEntry.source_name_en`, upsert path, `source_summary`. Last because it is blocked on you authoring names in `sources.yaml`.
**Check:** a source with no `source_name_en` still shows its Arabic name in the h1 with `dir="auto"` — no regression.

---

## 6. Not in this design

- **Compare / two panes.** Not asked for, largest single cost, forces every builder prefix-aware forever. Two tabs.
- **Column resize.** See item 1.
- **Frozen columns.** `border-collapse:collapse` + no cell background + a fourth sticky layer.
- **Tax-unverified tile and a Tax column filter.** `tax.resolve()`'s region→wildcard fallback and `valid_to IS NULL` temporality would have to be reimplemented in SQL and kept in agreement with the Python path across 169 regions.
- **Virtualization, infinite scroll, any client-side sort or filter.**
- **A separate dashboard page.** The ops room is this page; Overview, Changes and History already exist.
- **Auto-refresh.** A room that repaints while you read row 40 is worse than a stale one.
- **Convergence on `datasets.html`.** Asked directly: **no**, and the reasons are structural. It renders client-side from a runtime-discovered, user-authored schema (`datasets.html:443-475`), has no sort, no filters, cursor pagination with no total (`:485`), and lives behind `general_read_conn` (app.py:188-191) — a different database the spec hard-isolates (CLAUDE.md:1801). Converging would trade a bookmarkable, server-rendered, JS-optional page for a JS-only one and put a shared component across a boundary the spec calls hard. It would also destroy the per-column rendering rules that carry this page's meaning: the unit riding on the price when Unit is hidden (source.html:124-132), `same day` (source.html:167-171), the tax short form with the statement URL in the tooltip (source.html:150-159). **What should converge is the CSS** — `.state`, `.toolbar`, `.value` (datasets.html:4-40) move to `base.html` and both pages use them. Share the vocabulary, not the renderer.

---

## 7. The biggest risk

**The COUNT over `_LATEST_PER_OFFER`, and that this design makes it run far more often.**

`_LATEST_PER_OFFER` (reports.py:96-115) picks each offer's newest observation with a **correlated subquery evaluated per candidate row**, and `browse_observations` runs it twice per page load — once for the rows, once for `COUNT(*)` (reports.py:232). At 721 rows this is invisible. At 40,000 offers × ~30 observations it is on the order of a million index probes per request — and per-column filters mean the count is recomputed on **every filter change, every pill removal, every sort click**, which is exactly the interaction pattern this design encourages. Add `watch()` and `history_counts()` on top.

The obvious fix — swap the spine to `offer_state` — is the one thing I refuse to bundle, because it silently drops undecided offers and has no `business_date`. So the honest mitigation is: **measure before slice 3 ships.** Load a 40k-offer fixture, time the current page, and if the count is the bottleneck, land a covering index (or a per-request cached total scoped to the filter clause) as its own change with its own test — before per-column filters make the page ask that question ten times a minute.

Second risk, much smaller but likelier to bite on day one: **R2's sticky/clipping constraints**. `table{overflow:hidden}` inside `.tablewrap{overflow-x:auto}` under a sticky `thead` under a runtime-measured sticky tab bar (base.html:246-269) is four interacting layers that this codebase has already been burned by once, in writing. Render the two-row header on the real GPP_ENERGY table and look at it before building anything else on top of it.