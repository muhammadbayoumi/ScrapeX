# Where the migration stands, and where to pick it up

*Written 2026-08-15. Read this before touching Phase B.*

## The plan is `docs/MIGRATION-PLAN.md`

"ScrapeX — the Console, the migration, and the debt", drafted 2026-08-12 and
moved into this repository on 2026-08-15.

**It was written into `~/.claude/plans/`, and that was wrong twice over.** It
cost a session's opening — nothing under `docs/` matched, and it was found only
by searching the home directory for files touched on the right day. And the owner
works from two machines, morning and night: a plan on one of them does not exist
on the other. Anything this work depends on goes in the repository.

That file is the reasoning. **This one is the state**, and it is the one to keep
current when a phase lands.

## What measurement changed in the plan — read this before trusting it

Two of its statements were wrong, and both were caught by measuring rather than
by reading:

| the plan says | what is true |
|---|---|
| T1's remedy: "restore `crawl_honour_delay`" | It would have done nothing. `alsweed.sa/robots.txt` declares no `Crawl-delay`, and `honour_crawl_delay` only acts when a site declares one. Fixed as `crawl_pace_s` instead (#190). |
| B2: "`/api/records` already exists for it" | It does not. `/api/records` is the PANEL's card endpoint — compact, paginated at 100, *"the panel shows cards, never a table"*. The Data page runs on `/api/table/{key}` plus four more. Building on the card endpoint would have shipped cards and called it the migration. |

One statement checked and **upheld**: `DELETE /api/views/{id}` really has no caller
anywhere, as B1 claims. See the conflict below, though — finishing B2 revives it.

## Done

| | |
|---|---|
| **Step 0** | #182, #183 merged; the three working-tree files committed |
| **A0** | The blind settings guard — `_with_includes` expands Jinja includes; the nine Storage/Retention controls recorded in `MIGRATING_TO_THE_PANEL`, a list that may only shrink |
| **A1–A4** | **Phase A complete.** The Console reads and edits all six sheets (#185, #186, #187, #188, #189, #192) |
| **T1** | `crawl_pace_s` (#190) |
| — | samehgabriel alive after 12 days dead; the `SourceUriValidator` mirror re-derived after mbiXaddin's own repair; the contract-drift guard given something real to watch (#191) |
| **B2 · foundation** | `backend.js` extracted; Tabulator vendored into the extension; `data.html`/`data.js`/`datatable.js` (#193) |

## In flight

**PR #194** — the Data page's first load aborted itself and never painted; the
fix is an ordering, plus `tools/tabpage_harness.py` and
`tests/test_tab_page_dom.py` so a tab page is now RENDERED in tests. Also
generalises CI's "must RUN, not skip" step: seven suites depend on playwright,
and it named one.

## Resume here — the rest of B2

The Data page today draws the table, the columns, the fold switch and the bound.
Four capabilities of the engine's page are not in it yet. Build them in this
order, and the order is reasoned:

1. **The details drawer — `GET /api/offer/{key}/{id}`.** Least entangled, and it
   touches nothing the panel uses, so it proves the pattern on a second endpoint
   at no risk. The endpoint was BUILT for this: its docstring says *"for the
   panel the Data page opens INLINE"*. Note its ownership rule — an offer that
   is not this source's answers 404 **without confirming the id exists at all**.

2. **Choose-Columns — `GET`/`POST /api/fields/{key}`.** **Do not write a second
   one.** The panel already has the whole thing: `loadSourceColumns`
   (`extension/app.js:1579`) and `saveSourceColumns` (`:1618`), speaking the same
   bodies — `{field_key, hidden}`, `{order}`, `{reset: true}`. EXTRACT it into a
   shared module the way `backend.js` was extracted, or the two surfaces will
   disagree about how a column is saved. It touches the panel, which is why it
   comes after the drawer and not before.

3. **Saved views — `POST /api/views/{key}`, `DELETE /api/views/{id}`.**

4. **Promotion — `GET`/`POST /api/promotable/{key}`.** Its contract was not read;
   read it first.

**And when all four are in, remove the workbook link from the source card.** It
sits beside the new action deliberately: the engine's page still has these four,
and taking them away before the replacement carries them would be a downgrade
wearing the word "migration".

### A decision the owner owes on (3)

B1 lists `DELETE /api/views/{id}` among nine dead routes to delete. Building saved
views **revives it**. So either B1 loses that line, or the new page cannot delete
a saved view. A saved view that cannot be deleted is a defect, not a feature — but
it is the owner's call, and B1's list should be edited rather than quietly
contradicted.

## Named gaps, not forgotten

- **No DOM test for the Console.** `tools/tabpage_harness.py` was written for the
  Data page and would extend to `console.html` cheaply. Until then the Console's
  only proof is static plus one manual browser pass (#186).
- **`behaviourVersion` is ScrapeX's own bookkeeping, not a signal.** mbiXaddin has
  no such field; both numbers live here and one commit raises both. The real fix
  is `docs/HANDOFF-mbiXaddin-contract-producer.md`. What DOES look upstream is
  `test_no_cited_addin_file_has_moved_since_the_reading`, which watches the `.cs`
  files the reading cites and found three already moved.
- **`scrapex/version.py` has not moved** through any of this. The capability gate
  is green either way, and #190 set the precedent by not moving it. But *"the
  crawl falls back to product pages when the Store API refuses"* is exactly the
  kind of thing the owner asks *"does my build do that?"* about — which is the
  failure `tests/test_version.py`'s own docstring says the ledger exists to
  prevent. **Open question, owner's call.**

## Phases not started

**B1** (delete pure duplication and the dead routes) · **B3** (Storage and
Retention — the destructive half; every safety interlock moves WITH its control,
not after it) · **B4** (the rest, cheapest first) · **B5** (one navigation source
instead of three) · **B6** (the engine's new face: tray icon and a log window).

**Phase C** stays deferred: `127.0.0.1` cannot go until the extension can read
SQLite itself (**DEC-1**, wa-sqlite + OPFS), and jobs cannot move while the
heartbeat is broken under load (**T2**).
