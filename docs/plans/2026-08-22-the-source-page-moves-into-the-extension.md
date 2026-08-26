# The engine's source page moves into the extension

**LIVE. Written 2026-08-22. Step 0 is DONE on this branch.**

He asked for the plan itself, and he asked for it to survive:

> «ضع خطة لتنفيذها كلها وتتبع التنفيذ حتى لا نفقده»

*Write a plan to execute all of it, and track the execution so we do not lose it.*
The second half is the operative half. He refused the framing of the question he was
asked — products **or** contractors — and answered *all of it, tracked*. So the order
below is an order, not a choice.

**«حتى لا نفقده» is `C7`'s reason restated.** `REQ-07` was captured **2026-08-12**,
answered by measurement in `DEC-8` on **08-16**, and nothing had been built by 08-22.
`REQ-04` sat ruled and unbuilt for sixteen days after dropping out of view. This
repository has a documented habit of plans «توضع ولا تستكمل الى النهاية» — put down and
not carried to the end. **The status table is the answer to that**, and it is the first
thing in this file so it cannot be missed.

Lives here per [R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository).

---

## Status of the seven steps

**`who` says which category a step actually serves.** His stated reason for
[R-45](../RULINGS.md#r-45--the-site-is-the-only-source-of-truth-and-a-field-the-table-does-not-need-goes-in-the-rows-card)
was contractors — «لان المقاولون سيكون هناك عدة مصادر له فى المستقبل» — while
`REQ-07`'s four capabilities are all products-shaped. This column is so he can see, at
any moment, how much of what is built serves the category he asked about.

| step | who | state |
|---|---|---|
| 0 · the truth repair — the chooser stops lying on a dataset table | **both** | **DONE** — this branch. Eleven price-path keys were reaching `contractors`; hiding a column was a silent no-op. Both mutation-tested |
| 1 · AR \| EN in the panel | **both** | **not started.** The smallest real port, ~98 lines, and the payload already carries `bilingual`. `DEC-8`'s own example of a feature carried in NAME and left in FACT |
| 2 · Choose-Columns in the panel | **both** | **not started.** EXTRACT the panel's existing pair into a shared module — do not write a second one |
| 3 · the record card | **contractors** first, then products | **not started, and it is `REQ-32`.** The engine has this for products already; the port and the dataset build are one shell with two bodies. **UNGATED 2026-08-26** by `R-50`: the read is SQL over a file the panel does not hold, so the engine keeps the endpoint and the panel owns the surface |
| 4 · filters, column menus, export | **both** | **not started.** The bulk of the chrome — ~1,400 lines and the least inventive |
| 5 · promotion | **products** | **not started, and worth the least.** `source_attribute_promotion` has never carried a row on any source. **UNGATED 2026-08-26** by `R-48`: a write that decides which fields are columns is control, and control is the extension's with the engine executing. Still last — `source_attribute_promotion` has never carried a row |
| 6 · the workbook link comes off the source card | — | **terminal gate.** Only when 1–5 are in |
| — · saved views | products | **BLOCKED on [O-5](../RULINGS.md#open--awaiting-the-owners-ruling).** Do not start |

---

## ✅ ANSWERED 2026-08-26 — the gate below is LIFTED, and one of its two premises was wrong

**This section said steps 3 and 5 must not start until a boundary study answered. It
answered on 2026-08-23 and this gate stayed shut for three days.** That is a `C2` defect
with a measurable cost — two steps marked DO-NOT-START against a question the owner had
already ruled on twice — and it was found by another session reading the plan, not by its
author.

**What he ruled**, both on `main`:

- **[R-50](../RULINGS.md#r-50--the-engine-is-a-helper-to-the-extension-and-any-task-the-extension-can-do-moves-to-it)**
  — *the engine is a helper to the extension, and any task the extension CAN perform moves
  to it.* **The test is capability, not category.**
- **[R-48](../RULINGS.md#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports)**
  — the extension is the control room; the engine executes and reports.

**So «fetch only» was never the answer, and the table below was asking the wrong question.**
The narrowest formulation the record supports is **fetch *and write SQLite*** — every
statement of it attaches storage, including his own: *"leave the engine only fetch +
SQLite"* (`MIGRATION-PLAN.md:43-45`). A step that needs the engine to read `generic_record`
was never outside the boundary.

**Both steps are UNGATED, and each for its own reason:**

- **Step 3 · the record card.** Under `R-50` the question is not *"is this fetch?"* but
  *"can the extension do it?"* A read of `generic_record` plus its revisions is SQL over a
  SQLite file the panel does not hold, so **the engine keeps it for `R-50`'s only permitted
  reason** — and the panel owns the surface. Build it.
- **Step 5 · promotion.** A write that changes which fields are columns is a *control*
  decision, and `R-48` puts control in the extension with the engine executing. So it is
  not blocked either — but it is still **worth the least**: `source_attribute_promotion` has
  never carried a row on any source, which is why it stays last rather than becoming urgent.

**The dependency map below is kept rather than deleted, per `C4`**, because it was correct
reasoning from a premise that turned out to be false, and the shape of the error is more
useful than its absence: **it split the steps by "does this ask the engine to do more than
fetch", and the boundary is not drawn there.**

**Why it lands on this plan at all.** The two remaining capabilities are not symmetrical
with steps 1, 2 and 4:

| step | what it would add to the engine | exposed if the answer is "fetch only" |
|---|---|---|
| 1 · AR \| EN | nothing — the payload already carries `bilingual` | **no** |
| 2 · Choose-Columns | nothing — `/api/fields` exists and step 0 made it truthful | **no** |
| 4 · filters, menus, export | nothing — all client-side over a payload it already gets | **no**, except Excel, which is already server-built |
| **3 · the record card** | **a NEW endpoint** reading `generic_record` + its revisions for one row | **yes** |
| **5 · promotion** | **a WRITE** that changes which fields are columns | **yes** |

So the plan splits cleanly: **steps 1, 2 and 4 are pure client ports and are safe under
either answer.** Steps 3 and 5 are the two that ask the engine to do more than fetch.

**What I am NOT claiming.** I did not derive this boundary; it is his, and the workflow
measuring it is not mine. What this plan contributes is only the dependency map above —
which steps stop if the answer is "fetch only", and which do not. **If the answer is
fetch-only, step 3's endpoint has to live somewhere else, and that changes the shape of
the record card rather than merely delaying it.**

**And note what step 0 did NOT do**, deliberately: it added no endpoint and no new write.
It gave an existing endpoint a branch it was missing and made an existing payload read a
table it already owned. That is why it was safe to build before this question resolves.

## What `DEC-8` got right, re-verified at `4522158`

Every load-bearing number in
[`DEC-8`](../BACKLOG.md#dec-8--the-engines-data-page-is-a-port-not-a-rebuild--measured-2026-08-16)
still holds, which is why this is a plan to port rather than a plan to design:

| claim | re-measured |
|---|---|
| `grid.js` is 3,212 lines | **3,212** — exact |
| `extension/datatable.js` is 100 lines | **100** — exact |
| both run the same Tabulator | **byte-identical**: `tabulator.min.js` 445,987 and `tabulator.min.css` 28,497 in both `vendor/` directories |
| `source.html` carries 105 Jinja lines / 118 expressions | **105 lines, 61 `{{ }}` + 57 `{% %}` = 118** — exact |
| MV3 forbids nothing `grid.js` does | `eval(` **0**, `new Function` **0**, inline `on*=` **0** |
| the migration carried the WORD `bilingual` and left the feature | still true at `datatable.js:55` |

**And `grid.js` is 100% ours.** Tabulator lives in `static/vendor/`, so the 3,212 lines
are all ScrapeX. Only ~40 of them are data work — nine `fetch` calls against five
endpoints. **The rest is presentation and interaction**, which is exactly why it copies.

### Where the 3,212 lines actually are

Priced from `grid.js`'s own section markers, because "3,100 lines of difference" is not
a plan:

| section | lines | share |
|---|---|---|
| the record panel | 742 | 23.1% |
| the three-dot column menu | 634 | 19.7% |
| cell rendering | 631 | 19.6% |
| active filters + the filter popup | 414 | 12.9% |
| the History panel | 116 | 3.6% |
| multi-row selection cards | 109 | 3.4% |
| export | 98 | 3.1% |
| AR \| EN | 98 | 3.1% |
| ordering + what a column reads | 168 | 5.2% |
| fold, popup management, header buttons | 167 | 5.2% |

The record-panel cluster — 742 + 116 + 109 = **967 lines, 30%** — is one step, and it is
step 3.

---

## The correction this plan is built on

**`R-45` and `REQ-32` both state that a per-row card exists on neither surface. It has
existed on the engine since 2026-07-22.**

The measurement searched for `rowFormatter`, `row-detail`, `expandRow` and
`detailsDrawer` and found nothing. All four are the wrong symbol: the card is opened by
row **selection**, through `rowSelectionChanged` → `openOfferPanel` →
`GET /api/offer/{key}/{id}` → `renderOfferPanel`, into `#offer-panel`. First landed
`6f99a93`, redesigned `bac9c94`. `grid.js`'s own comment records the ruling: *"ONE
container under the table, opened by SELECTING a row (the owner's ruling)"*.

It already includes the thing `R-45` asks for. `reports.py` builds `moved_to_details`
and says in its own words: *"hiding a column is 'move it to the details' and showing it
is 'move it back' — the owner's ask, using the mechanism that already exists."*

**So he was not misremembering.** `REQ-32` says he *"remembers this as built. It is half
built, and not the half he needs."* The truth is that it is **fully built for products
on the engine**, and his complaint is that contractors lack it — which is precisely what
he said: «نفس الشى اريده فى كاتوجرى المقاولون».

The `C4`/`C5` correction to both registers is the primary session's to land.

---

## The structural fact that decides the order

**There are three surfaces, not two.** The engine page serves datasets too — `/source/contractors`
renders through the `is_dataset` branch — and **it is itself incomplete for contractors**.
A port of a page cannot deliver a feature the page does not have.

Four of the five endpoints the engine's data page consumes run on `read_conn()`, the
price warehouse, and are structurally products-only.

**CORRECTED 2026-08-26 — and this plan's own step 0 is what falsified it.** This paragraph
said *"only `/api/table` uses `general_read_conn()` and resolves the catalogue first."*
**`GET /api/fields` does too**, at `scrapex/webui/app.py:2269` — which is precisely what
step 0 changed when it made that endpoint truthful for a dataset. So the sentence was
already false in the commit that shipped beside it. Kept and corrected rather than
rewritten, per `C4`: **a plan contradicted by its own delivered step is a `C2` bug, not a
footnote**, and it was found by a session reviewing the plan rather than by its author.

| capability | engine · products | engine · contractors | panel |
|---|---|---|---|
| the table, sort, filters, column menus, group, nest, export, AR\|EN | ✅ | ✅ | partial |
| Choose-Columns | ✅ | **repaired in step 0** | ❌ |
| the record card | ✅ | ❌ — rows carry no `offer_id`, and there is no `/api/offer` for a dataset | ❌ |
| promotion | ✅ (never used) | ❌ | ❌ |
| saved views | thin | ❌ — `views=[]` | ❌ |

**`REQ-32` is therefore new engine work, not a migration.** That is the one place this
plan departs from `DEC-8`: `DEC-8` is right that `REQ-07` is a port, and `REQ-32` is not
in `DEC-8` at all.

One happy exception: `saved_view.source_key` is plain `TEXT` with **no foreign key**, so
saved views is the only one of the four already dataset-agnostic in storage — and it is
the one he has blocked.

---

## The steps, each with the gate that proves it done

A gate is a property that can be checked, not a description of the work.

### Step 0 · the truth repair — **DONE**

*Serves both categories. It is a prerequisite for every measurement after it.*

`/api/fields/{key}` had no catalogue branch, so a dataset key fell through to the price
path and asked `column_presence` about a contractor directory. `ensure_fields` is
additive, so merely OPENING the chooser wrote eleven price-path keys against
`contractors`. And `dataset_table_payload` never read `dataset_field`, so hiding a column
saved a row and changed nothing on screen.

**Gate — met.** Ten guards. `/api/fields/contractors` offers only keys the dataset's own
schema carries; none of the eleven is listed even when present on disk; hiding a column
removes it from `columns` and puts it in `moved_to_details`; showing it moves it back; a
rename reaches the heading; an untouched table keeps schema order; `MADAR` still takes
the price path. Both defects mutation-tested — the missing branch turns six red, ignoring
`dataset_field` turns three red, control returns to ten green.

**The eleven rows are made inert, not deleted.** `COMPATIBILITY.md` puts a destructive
migration behind a review gate that is **his**. Whether to delete them is `OP-58` and it
needs his word.

### Step 1 · AR | EN in the panel

*Serves both categories.* Contractors already gets bilingual pairs — `dataset_table_payload`
derives them from any `_ar` suffix rather than a hand-written list.

The engine's toggle swaps column **visibility** between the two name columns rather than
rewriting one column's contents, so sort, filter and export each keep working on the
column they name. It governs the record card as well, by his ruling.

**Why first:** ~98 lines, the payload already carries everything, and it is `DEC-8`'s own
example of the migration carrying a word and dropping a feature. Smallest possible proof
that the port pattern works on a second capability.

**Gate.** In `tools/tabpage_harness.py`, with a payload whose `bilingual` is non-empty:
pressing the toggle changes which column is visible and leaves row order and the active
sort untouched; with `bilingual` empty the control is **absent**, not disabled-and-lying.
And `summarise` stops printing the word for an empty object — see `OP-56`.

### Step 2 · Choose-Columns in the panel

*Serves both categories, now that step 0 makes it truthful for datasets.*

**Do not write a second one.** The panel already speaks these exact bodies —
`{field_key, hidden}`, `{order}`, `{reset: true}` — in `loadSourceColumns` and
`saveSourceColumns`. **Extract them into a shared module the way `backend.js` was**, or
the two surfaces will disagree about how a column is saved.

> `HANDOFF-resume-the-migration.md` puts those two symbols at lines 1579 and 1618 of
> `extension/app.js`. **Both are stale** — they are at 1594 and 1633 at `4522158`, and
> `STATE.md` has them right. That handoff sits outside the citation guard's `DOCUMENTS`,
> which is `OP-59`. **Re-derive before you touch either**, and note these are written
> without the `path:line` form on purpose. `#258` has since merged and rewrote parts
> of that file; **both symbols survived at 1594 and 1633**, which is luck rather than
> stability — re-derive anyway.

**Gate.** One module, imported by both surfaces; a grep finds no second copy of any of
the three bodies. Hiding a column in the panel and reloading the engine page shows it
hidden there too, and the reverse — proving one store, not two.

### Step 3 · the record card — `REQ-32`

*Serves contractors first, then products.* **This is the step he actually asked for.**

One shell, two bodies. The shell is the engine's: open on row selection, one container
under the table, deselect closes it, and a **"Moved out of the table"** section fed by
`payload.moved_to_details` — which step 0 populates for datasets for the first time.

The bodies differ because the data does. The products body is heavily price-coupled —
`periods`, `observations`, `changes`, `money()`, `basisOf()`. A contractor has none of
that; its extras are already on disk in `generic_record.data_json`, so **nothing needs
re-crawling**.

**This needs a new engine endpoint**, and that is the honest cost. `/api/offer` is
products-only on every axis: `read_conn()`, `offer_identity`, `pricehistory.timeline`.
The dataset equivalent keys on `generic_record_id`.

**Order inside the step:** the dataset card first, because its server half does not exist
and building it proves the shape; then the products card, which is a port of 967 lines
onto an endpoint that already answers.

**Gate.** Selecting a contractor row opens a card listing every field the row carries
that is not a visible column, including the readiness level on the rows that have it —
which is what closes `Q-17` without a schema change. Selecting a second row replaces the
card rather than stacking. Deselecting closes it. Driven in the DOM harness, not asserted
against source text.

**Do not skip the harness.** The Data page has already shipped BROKEN once with 2,460
engine and 398 extension tests green on it: every first load aborted itself, and it was
found by opening it in a browser. Three thousand ported lines with nothing rendering them
is that failure with more surface.

### Step 4 · filters, column menus, export

*Serves both.* The bulk: ~414 lines of filter machinery, ~634 of column menu, ~98 of
export. Least inventive, largest diff.

**Carry the working half only.** Several server-side capabilities on the engine page are
already unreachable — a global search parameter with no input bound to it, an availability
filter, a `sortlink` macro with no caller, and server pagination the grid replaced. A port
that copies them ports dead code. That census is `OP-55`.

**Gate.** For one products source and one dataset: every filter chip the engine page can
produce, the panel produces; CSV and JSON export byte-identical for the same payload;
Excel still served by the engine, since the browser-side xlsx writer needs a SheetJS this
project has never vendored.

### Step 5 · promotion

*Serves products only, and it is worth the least of the five.*

**`source_attribute_promotion` has never carried a row — zero, on every source, in his
live warehouse.** That is not an argument to skip it; it is an argument for its position
in the order, and it belongs in this plan rather than only in a `BACKLOG` entry because
it changes what the step is worth.

Its contract was never read. Read it first: the row **is** the promotion, so demoting
deletes it and nothing has to remember a previous shape.

**Gate.** Promoting an attribute in the panel makes it a column on both surfaces;
demoting removes it from both; a demote-then-promote returns the same column, proving
reversibility.

### Step 6 · the workbook link comes off the source card

**The terminal gate, and it is a gate rather than a task.** The link lives in the
*panel's* source card, not on the engine page. It sits beside the new action deliberately:
the engine's page still has these capabilities, and taking the link away before the
replacement carries them would be a downgrade wearing the word "migration".

**Gate.** Steps 1–5 green, and the entry is removed in the same pull request that proves
the last of them.

### Blocked · saved views

**`O-5`, and it is his.** B1 lists `DELETE /api/views/{id}` among nine dead routes to
delete; building saved views revives it. He has comments on B1 itself and will raise them
first.

Two things worth knowing before he rules, because they change what he is ruling on:

- **The feature is thinner than it sounds.** A saved view captures only URL state —
  filter parameters, a search term, sort, direction, page size. It captures **no grid
  state at all**: not a column arrangement, not a group, not a pin.
- **The engine page has no delete UI**, so the route B1 calls dead is dead because nothing
  ever offered it, not because the feature was dropped.

---

## The measurement he asked for: «قِسْ أوّلاً ثمّ قُل لى»

Measured 2026-08-22 read-only against the live warehouse, at
`~/.scrapex/engine/scrapex-engine.db` — 1,125 MB with a 4 MB WAL.

**Populations today are not the ones in the code's own docstring.** It said 11,059; the
profile crawl has been adding all day.

```
contractors           17,304 records      contractor_profiles   704 records
```

> **THE POPULATION AT THE MOMENT OF MEASUREMENT, because a bare figure here is what went
> stale last time.** Every timing below was taken with `contractors` at **17,304** and
> `contractor_profiles` at **704**, before the power cut. The profile crawl has since been
> resumed and was at **20,352 of 34,834 pages (58.4%)**, so `contractor_profiles` is
> climbing and the 704 is already historical.
>
> **This does not move the verdict, and the reason is the shape of the cost rather than
> its size.** The server side is **linear at ~28 µs/row**, so even a `contractor_profiles`
> grown to the full 34,834 lands near 1.0 s server-side — still inside a 5,000 ms
> deadline. What would change the answer is not more rows but more BYTES PER ROW: a
> profile carries 21 fields against the listing's 28 but far longer values, and nobody has
> measured a full-population profile payload. **Re-measure before step 3 rather than
> scaling this number**, since step 3 is the one that opens a profile row.

**`/api/table/contractors`, 17,304 rows × 34 columns = 24.26 MB:**

| stage | cost |
|---|---|
| SQL query + row shaping | 373 ms |
| JSON serialisation | 110 ms |
| **server total** | **483 ms** |
| transfer over `127.0.0.1` | 133 ms |
| **the request, against a 5,000 ms deadline** | **616 ms — 12.3% of budget, 88% headroom** |
| then `JSON.parse` at 360 px | 78 ms |
| Tabulator build | 384 ms |
| two frames to paint | 23 ms |
| **browser total** | **485 ms** |
| **end to end** | **~1.1 s** |

**The answer is that it is not close, and my own risk flag was wrong.** I reported the
5,000 ms deadline against a ~21 MB payload as the same shape as the `/api/health` defect
— 3.8 s against a 2,500 ms budget, which made the panel call a healthy engine absent.
Measured, it is an eighth of its budget rather than 150% of it. **The guess was wrong in
the safe direction and the measurement is why we know.**

**Pagination is what saves the render:** 80 rows reach the DOM out of 17,304, 5,793 nodes,
57 MB of JS heap. Without `paginationSize: 100` this would be a different answer.

**Honest limits of this measurement**, so nobody treats it as more than it is:

- Server timings are in-process against a read-only connection. FastAPI's own encoder is
  not `json.dumps` and will add something.
- **The crawl was not running** — the WAL was 4 MB. Under a live crawl the query will be
  slower, and 88% headroom is what absorbs that.
- One machine. A slower one scales all of it.
- Growth is linear in rows at ~28 µs/row server-side, so the full 17,403-contractor
  population moves the total by single-digit milliseconds.

**What this does not measure, and it is the number that would actually bite:** the panel
holds the whole 24 MB payload in memory per open data tab. Two tabs is 48 MB before
Tabulator's own structures. Nobody has measured several open at once.

---

## Findings this plan rests on

Seven, `OP-53`…`OP-59`, assigned by the primary session. Recorded in
[BACKLOG.md](../BACKLOG.md) — where they came from *us*, not from him.

| # | finding |
|---|---|
| `OP-53` | eleven price-path keys written against `contractors` in the live warehouse |
| `OP-54` | Choose-Columns was a silent no-op for datasets — `dataset_table_payload` never read `dataset_field` |
| `OP-55` | server capabilities on the engine page that nothing reaches; a port must not carry them |
| `OP-56` | `summarise` prints "bilingual" for `{}`, because an empty object is truthy — and the test asserts booleans the server never sends |
| `OP-57` | `data.js` pins `index: "offer_id"`, which no dataset row has |
| `OP-58` | whether to delete the eleven rows on disk — a destructive migration, so **his** gate |
| `OP-59` | `HANDOFF-resume-the-migration.md` sits outside the citation guard and two of its `app.js` citations are stale |

---

## Coordination

- **`#258` was a dependency and it has LANDED** (`d10e974`), so the entry point this plan
  needs now exists. `sourceMenu` used to return `""` for `kind === "dataset"`, hiding the
  only route into `data.html` for exactly the datasets this plan serves — `OP-42`, now
  CLOSED. A dataset card draws the actions whose proof is `RESOLVES_A_DATASET`, so
  "Open the data table" is reachable. **Verified at `4522158`, not assumed.**
- **`data.html` does not load `app.js` or `app.css`.** Steps 1–4 land in `data.*` and
  `datatable.js`. Only step 2's extraction touches `app.js`, which `#258` has now
  finished with — but it stays a hot file, so cite symbols there and not lines.
- **Migration numbers are a shared register** and nobody had listed them: `main` is at
  `0009`, another branch holds `0010` and bumps `contracts/contract-baseline.json` to
  0.3.1. Step 3 needs a migration and must take the next free number by asking, not by
  counting. Going into `ORCHESTRATION.md` §3.
- **All five endpoints are contract-guarded** — every route/method pair appears in
  `contracts/contract-baseline.json`'s `endpoints`. Step 3's new endpoint edits that file,
  so it must be sequenced with whoever holds it.
- **Do not pin a line into `extension/app.js` or `extension/app.css`.** Cite the symbol
  and say the commit.
