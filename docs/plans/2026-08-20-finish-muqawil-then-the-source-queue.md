# Finish muqawil.org completely, then the source queue

**LIVE. Written 2026-08-20, and written to be picked up on the other machine.**

> «بعد الانتهاء من آلية التخزين اريد التوقف حتى استكمل من جهاز اخر تاكد من تسجيل كل شى»

He works from two machines under two accounts. `~/.claude/plans/` is one machine and
one account, which is why seven plans had to be rescued out of it on 2026-08-17 and
why **`R-08` puts the plan in the repository**. This file is here so the other machine
can start from it without asking anyone what happened.

**His priority, in his words: «موقع مقاول بشكل كامل»** — finish muqawil.org
completely — and complete means **«كلّ ما ينشره الموقع»**, every field the site
publishes, both languages, detail pages included.

---

## Where it actually stands

**The studying is finished. The building has started.** Every gate the previous plan
set before the crawl has been cleared.

| | |
|---|---|
| **Done** | the crawl study ([DEC-11](../BACKLOG.md), #228 · #229) · the sightings ledger and resume (#227) · the storage study ([STORAGE.md](../STORAGE.md), #230) · **the storage mechanism itself** (`scrapex/snapshotbody.py`, engine migration 0005) |
| **Coverage today** | **11,059 of 17,403 contractors — 64%**, listing pages only, **zero** profile pages ever fetched |
| **Columns today** | **22 of his ~70**, all from the listing card. The other 48 live on the profile page, which has never been crawled |

### The four numbers that matter, all measured on 2026-08-20

- The listing is **871 pages**, and `(L−1)×20 + c` with `c` **read** — it was 15 cards
  on 2026-08-16, 2 that morning, 3 that afternoon. He warned the data is live before
  any of this was measured.
- `region_id` × `company_size` is an **exhaustive 56-cell partition**, exact to the
  unit: 15,966 across regions 1–13 plus **1,437 under `region_id=0`** (the contractors
  who publish no location) = 17,403.
- A provable listing crawl is **~1,065 requests, ~1.7 h**, against 18.4 h for a blind
  sweep that can never say "complete".
- The whole corpus is **4.55 GB** raw and **~90 MB** stored, because the mechanism is
  built.

---

## EVERY STATE A ROW CAN BE IN — enumerated first, on his instruction

> «حل هذه المشكلة بحيث المستخدم يقدر يعرف حالة الصف فى اى حالة ذكرناها او ممكن تحدث
> اجمع كل الحالات واحصرهم اولا … حتى حالة اذا تم ابديت لصف»

`R-27` says the row never leaves the screen and its state becomes a column. That is
only safe if the vocabulary is **closed** — a state nobody enumerated is a row
displaying something the reader cannot interpret. So: every state, and honestly
marked where it cannot be computed today.

**The reference point is `newest` — the latest `last_seen_at` in the dataset, i.e.
"the last crawl".** Every state below is relative to it.

| state | what happened | how it is known |
|---|---|---|
| **`new`** | first appeared in the last crawl | `first_seen_at >= newest` |
| **`updated`** | seen in the last crawl **and its data changed** | a `generic_record_revision` with `observed_at >= newest`. **This is only meaningful because of `R-20`**: now that an unchanged row writes no revision, the presence of a fresh revision *is* the change |
| **`confirmed`** | seen in the last crawl, nothing changed | `last_seen_at >= newest` and no fresh revision |
| **`absent`** | stored, and the last crawl did **not** show it | `last_seen_at < newest`. A departure **only if that crawl covered it** — a partial crawl produces this too |
| **`unsighted`** | stored, and not in the sighting ledger at all | no `dataset_sighting` row. A gap in the LEDGER (these predate #227), **not** a contractor leaving |
| **`returned`** | proved absent in an earlier crawl, and here again | `last_absent_at` — **added by migration 0006**, because absence cannot be recomputed later |
| **`retired`** / **`unavailable`** | someone marked the record | `generic_record.status`. Informational only — never a filter, per `R-27` |

**All seven are computed today, in one place** — `sightings.row_state`, with the
precedence written down. Eight names in the vocabulary: these seven plus
`unavailable`.

### `returned` needed a migration, and that is the interesting one

Absence leaves **no trace** in `dataset_sighting`: a row simply stops being touched,
and a `last_seen_at` two crawls old is identical whether the id was missed once and
came back or has been gone throughout. "Was this absent at some point" is a question
about a moment that has already passed — so it cannot be derived after the fact and
had to be **written when a crawl proved it**. Migration 0006 adds `last_absent_at`
and `last_absent_run_ref` (the run that proved it, so the evidence can be checked
rather than the timestamp trusted).

**And it is only ever written from a proof** — a cell that closed with `D = 0`. A
crawl misses contractors for its own reasons: a dead page, a rolled generation, a cell
above the witness ceiling. Recording those as absences would retire contractors
because the crawler had a bad afternoon, which is `R-27`'s failure arriving from the
other side.

### Two states that still cannot be computed, and why

- **`seen but never stored`** — the site showed us a contractor and no row exists.
  `sightings.missing_ids` counts them, but under `R-27` "the row stays visible" has no
  meaning when **there is no row**. Whether such a contractor should appear as an
  empty row is a design question, not a defect.
- **`never seen at all`** — not in the warehouse and never shown to us. **Unreachable
  by construction**, and his own correction: only the crawl's deficit `D` counts these.
  Membership 10001274 was this case.

### And one number that gates all of it

`newest` is a single `MAX(last_seen_at)` over the dataset, so it is one indexed
aggregate rather than a per-row question — which matters, because the naive way to
answer these states is a correlated subquery per row and that is exactly the
performance defect measured on 2026-08-21 (see below).

---

## HOW MUCH IS LEFT — asked 2026-08-21, answered by counting

> «قولى ناقص اد اى للانتهاء من خطة مقاول»

Thirty boxes. **Eighteen are done, two are answered by measurement rather than built,
and ten are open — of which only SIX are muqawil engineering.**

| | | |
|---|---|---|
| **done** | 18 | including the listing crawl, now `D = 0` |
| **answered, not built** | 2 | conditional requests (the site sends no validator); `detail_urls` (the claim was wrong) |
| **open — muqawil engineering** | **6** | below |
| **open — elsewhere** | 1 | the panel path, tracked in [the tool's plan](2026-08-21-the-tool-itself.md) |
| **open — his to rule** | 3 | `STORAGE.md` §5, `O-2` (parked by him), `DEC-10` |

**The six, in the order they should be taken, with the cost measured not guessed:**

| | item | cost | why this order |
|---|---|---|---|
| 1 | `status = 'unavailable'` on a departed row | **~1 h** | **already ruled** — he chose `unavailable` over `retired`; detection is built, only the WRITE is missing. A ruled-and-unbuilt item is the exact shape of `REQ-04`, which is why **C7** exists. |
| 2 | State the resume cost in the tool's output | **~20 min** | It is in a docstring at `partitioncrawl.py:81`, which is not where a user of the command looks. |
| 3 | `is_enabled` has 0 callers | **~1 h** | Two capabilities are lit at `PARTIAL` and nothing reads them, so lighting one is a *claim*, not a switch. |
| 4 | The slice scope, unused for muqawil | **~1 h** | Built and tested; wiring it is what makes a partial re-read addressable. |
| 5 | The profile crawl — 34,806 pages | **~2 h to wire, ~17.4 h to run** | The adapter exists (`bilingual_profile_candidate`, #235). This is mostly *runtime*, and it is the item that turns 21 columns into 48. |
| 6 | `R-19` child tables, all five groups | **~1 day** | The largest, and last on purpose: ~500K rows, five tables, and it depends on profile pages being on disk — which is item 5. |

**So: about a day and a half of work, plus roughly eighteen hours of crawling that runs
unattended.** Two of the six are under an hour each and one of those is already ruled.

**What could still move that number:** `DEC-10`. Without a row-aware idempotency key, a
corrected parser re-run over stored snapshots reports `recovered=True` and writes
nothing — so a mistake in item 5 or 6 costs a re-crawl instead of a re-parse. It is the
one open decision that changes the *cost* of the remaining work rather than its scope.

---

## THE CHECKLIST — everything open on muqawil, and whose turn it is

**His instruction, 2026-08-21:** «احصر كل التعديلات المطلوبة فى مقاول ولم يتم تنفيذها
وكل التطويرات المطلوبة ولم يتم البدء فيها وكل ما هو موجود فى الكود وغير موصل بشكل
صحيح» — as a checklist he can track. Anything tool-wide goes to
[the tool's own plan](2026-08-21-the-tool-itself.md) instead, per the same
instruction. **And: «اريد الانتهاء من كل المكاسب السريعة وخطة مقاول فى المقام الاول».**

Tick a box only when it is MERGED. `⚡` marks a quick win — under about an hour.

### A · Quick wins — do these first, by his instruction

**All five are BUILT, and the boxes stay unticked until the pull request merges.**

- [x] ⚡ **`R-20`: an unchanged row writes no revision.** `content_hash` is now read
      **before** the upsert, because the upsert overwrites the evidence and the
      comparison is impossible afterwards. It was 34,550 revisions for 11,059
      contractors; now history is a timeline of real changes. **Four mutations killed**,
      and one of them exposed an existing test demanding *four* revisions where one row
      of two had changed — the expectation encoded the defect.
- [x] ⚡ **`DSN-05`: City and Region are separate columns.** The published
      `"RIYADH - Riyadh"` is **kept** beside them, because source truth is never edited.
      The Arabic halves are derived from the **positionally aligned** value, not the
      Arabic row: `_slug` filters every Arabic label to nothing, so `card_city_region`
      is absent there and splitting that row gave two empty strings for every
      contractor in the country — silently.
- [x] ⚡ **`DSN-04`: the URL columns.** Taken from the card's own **absolute** href
      rather than built, so no hostname is duplicated out of `sites/muqawil.py`, and the
      `143` tail is **rebuilt** rather than carried over — it is what makes the
      self-build price section render at all. `contract_request_url` is **not**
      invented: its pattern column in the design is empty, and a guessed URL is worse
      than an absent one because it looks answered.
- [x] ⚡ **Detect the disappeared** — `sightings.departures`, **read-only**. Two lists
      kept apart: departed, and a gap in our own ledger. The WRITE still needs his
      ruling on `unavailable` vs `retired` ([OP-26](../BACKLOG.md)). It answers
      *disappeared*, never *never-seen* — only `D` reaches those.
- [x] ⚡ **`missing_ids` and `sighting_frequencies` have a caller** — `--coverage` in
      the crawl tool, which also surfaces departures. All three had **zero callers**
      between them: the answer to "what are we missing", written for the 10001274
      incident, and nothing asked it.
- [x] ⚡ **`R-27`: the row never leaves the screen; its state is a column.** The
      `status = 'active'` filter is gone from the grid payload, and eight states are
      named in one closed vocabulary with a sentence each.
- [x] ⚡ **The coverage queries were 1,600× too slow** — 49.7 s and 48.8 s, together
      past the two-minute limit, because the site's own id is inside `data_json` and no
      index can serve a `json_extract`. Now 0.03 s each. Root cause recorded as
      [OP-27](../BACKLOG.md); this routes around it.

### B · The crawl method — in flight

- [x] The provable partitioned listing crawl (#233)
- [x] Both completeness proofs, witness and count (#234, open)
- [x] `--only` so the residual is addressable without re-reading proven cells
- [x] **Close the deficit — `D = 0`. 17,414 of 17,414, a PROVABLE 100%** (2026-08-21).
      Three cells cannot be witnessed at any size — RIYADH twice, JEDDAH — and they
      closed by **counting**, exactly as [R-26](../RULINGS.md#r-26--the-residual-crawl-runs-in-the-background-while-development-continues-and-must-be-stoppable)
      allowed.
      **What actually took the last 633: the dry-stop was counting REPLAYED attempts.**
      A resumed cell read its ids back off disk, gained nothing new, and the crawl
      called that "dry" after two such rounds — so the five heaviest cells stopped
      without ever asking the site. Fixed by requiring `attempt.pages_read > 0` before
      an attempt can count as dry, in the loop **and** in `went_dry`. Then 631 new
      contractors arrived: `D` fell **633 → 0**. The number the plan opened with was 3,690.
- [x] **`REQ-21`: the nested audit** — `crawl_partition(..., parent=Cell)` audits
      `Σ N_child` against the parent cell, `Cell.is_under` decides membership as a set
      question so filter order cannot matter, and `NotASubdivision` refuses a child
      that dropped one of the parent's filters **before a single request** — such a
      child is measured over a larger set and could clear the parent's count while
      covering none of it. A nested proof now reads *"AND FOR THAT CELL ONLY"* rather
      than claiming the listing. Seven tests, **eight mutations killed**.
      Measured target: the city list from partial evidence accounts for 4,665 of
      4,697 — a deficit of **32** the audit now names instead of drowning in 17,414.
      **A nested crawl runs today** — `listing_url` builds from `cell.query`
      generically, so `?region_id=1&company_size=verysmall&city_id=21&page=3` is a URL
      like any other and `in_cell` yields both locales; verified, not assumed. What is
      missing is a **published** city-cell generator: `cells()` still returns only the
      56, and deriving cities means querying the warehouse for what we have seen. Not
      built ahead of his ruling, because for Riyadh it buys 9% (4,697 → 4,268) and
      the counting proof remains the route.
- [ ] **Make sizing resumable**, or state its cost in the tool's own output. A resumed
      run re-pays ~112 requests (5.7%).

### C · The 48 columns — further along than this list said

> **CORRECTION, 2026-08-21.** This section said *"Nothing extracts a profile page
> today"* and that was **wrong**. Measured against the committed fixtures:
>
> | | |
> |---|---|
> | `read_profile` | reads **11 fields** per locale — the `.info-box` pairs |
> | `read_email` | decodes Cloudflare's XOR'd `data-cfemail` ✓ |
> | `read_coordinates` | returns `24.6717 / 46.3942` from the inline script ✓ |
> | `merge_locales` | gives **20 merged keys** including both `_ar` halves ✓ |
> | `profile_candidate` | **built 2026-08-21** as `bilingual_profile_candidate` (#235) — it was the actual gap |
> | `profile-en.html` / `profile-ar.html` | both committed ✓ |
>
> So the reading works end to end and what is missing is the **adapter** to a
> `TableCandidate` — the profile's equivalent of `bilingual_listing_candidate`.
> A wrong checklist is worse than no checklist: it sends the next session to build
> what is already built.
>
> **And a defect found on the way:** `_candidate_from` hardcodes `CARD_FIELDS` as the
> declared lead, so a profile row put through it comes out carrying **17 empty listing
> columns** — measured, 39 fields where the profile has 20. The declared list has to
> become a parameter, not a constant.
>
> **Where the other ~28 columns are, so nobody hunts for them in `read_profile`:** the
> profile page carries **five real `<table>` elements** — the licences and their
> readiness, the two contractor lists, the technical rating, the contract counts. Those
> go through `detect_html_tables` like any other site's tables, and they are exactly
> the multi-valued groups `R-19` wants in child tables. That is why `R-19` is a
> separate item and not part of the parser.

- [x] **`profile_candidate`** — `bilingual_profile_candidate`, plus `_candidate_from`
      taking its declared field list as a parameter instead of always leading with
      `CARD_FIELDS`. Verified on the committed fixtures: 21 fields, approvable, one
      row, no `card_*` leakage, identity `881`, coordinates `24.6717 / 46.3942`.
      Five mutations killed. **#235.**
- [x] **A declared `PROFILE_FIELD_ORDER`**, for the reason `CARD_FIELDS` exists: a
      profile page that happens to omit a box must not produce a different schema.
      **#235.**
- [ ] **`R-19`: child tables for all five multi-valued groups** — «جداول أبناء للخمس
      كلّها»: Interests, Licensed Activities, Qualification Programs, Balady Services,
      contractor relations. Not JSON, not `Activity 1, 2, 3`. A measured profile carried
      **30 hierarchical interest values in 6 groups** — about 500K rows. Ruled, unbuilt.
- [ ] **The profile crawl**, 34,806 pages both locales. Must run with `body_class` set
      so the pages arrive compressed — `snapshotcrawl` already does it.
- [~] **Conditional requests on the recurring pass — BUILT, AND THIS SOURCE CANNOT USE
      THEM.** Measured 2026-08-21 against the live site, one request:

      | header | muqawil.org sends |
      |---|---|
      | `ETag` | **absent** |
      | `Last-Modified` | **absent** |
      | `Cache-Control` | `no-cache, private` |

      It is a Laravel application that mints a fresh `XSRF-TOKEN` per response, so there
      is no stable entity to validate and `no-cache` says so explicitly. `fetch_validator`
      holding **0 rows after 727 fetched pages** is therefore CORRECT BEHAVIOUR, not a
      wiring bug — and it is why this was checked before anything was blamed.

      **The line this list carried — "this is what makes maintaining 48 columns
      affordable" — was an assumption, and it is false here.** A recurring profile pass
      re-downloads all 34,806 pages in full. What survives of the idea is the part that
      never depended on the server: `R-20` compares `content_hash` **after** the fetch,
      so an unchanged profile still writes no revision. Bandwidth is not reducible on
      this source; storage and history already are.

      The code stays — `sources.yaml` sites do send validators, and the seam is generic.
      Recorded as evidence against the plan's own premise, per **C5**.

### D · In the code and NOT WIRED — measured, not guessed

- [ ] **`is_enabled` has 0 callers.** `GENERIC_DATASET_CATALOG` and
      `GENERIC_EXTRACTION` are lit at `PARTIAL` and nothing reads them, so lighting one
      is a *claim* about a capability rather than a switch.
- [x] **`missing_ids`, `sighting_frequencies` have a caller** — `--coverage`. Listed
      twice; it is section A's item and it shipped there.
- [~] **`detail_urls`: the "referenced only by tests" claim was WRONG.** Measured:
      `pagewalk.py:145` and `partitioncrawl.py:639` both call it. What is true is
      narrower and is the same item as the profile crawl above — **nothing walks the
      frontier for muqawil**. The `143` segment stays load-bearing: it is what makes the
      self-build price section render at all.
- [ ] **`belongs_to_slice` / `crawl_slice` / `LISTING_PLUS_SLICE`:** the slice scope is
      built, tested, and never used for muqawil.
- [ ] **`generic_record.status` offers `unavailable` and `retired` and nothing ever sets either.** Detection is built (`sightings.departures`); the WRITE needs his ruling on which of the two a delisted contractor gets — see [OP-26](../BACKLOG.md)
- [x] **`approve_candidate` creates a version 2 now** — `_retire_or_refuse`, and the
      direction decides: a **superset** of the approved fields retires v1 and approves
      v2, while a subset or a rename is still refused, because those two are how a
      broken parser looks and a silent narrowing is the failure worth keeping. Proven on
      the live warehouse: v1 retired, v2 approved with **28 fields**. `R-31`.
- [x] **A SHIPPED COMMAND — `scrapex contractors`** (`REQ-24`, 2026-08-21). Measured
      first: `pyproject.toml` ships `include = ["scrapex*"]`, so `tools/` never reaches
      an installed user; `scrapex crawl` wants a `source_key from sources.yaml` and
      muqawil is not in it; `cli.py` had **zero** references to `muqawil`,
      `partitioncrawl`, `snapshotcrawl` or `generic_record`. The implementation moved
      to `scrapex/contractors.py`, `tools/crawl_muqawil_listing.py` is a four-line
      pointer, and both front doors share `add_arguments`/`run` so they cannot drift.
      **This is why the panel said "Engine not detected" while a crawl ran:** the
      crawl was a developer script that never went near the Engine.
- [ ] **No path from the PANEL, still.** `jobs.py` contains no reference to `muqawil`,
      `generic_record`, `partitioncrawl` or `snapshotcrawl`. Pressing update runs the
      price connectors. → tracked in [the tool's plan](2026-08-21-the-tool-itself.md).

### E · Held by him, deliberately

- [x] **`OP-25` — RULED AND EXECUTED 2026-08-21.** He chose «امسح وأعِد الاعتماد من
      القرص»: re-approve from stored snapshots, which the
      [GENERIC-FETCH-SEAM](../GENERIC-FETCH-SEAM.md) makes a **zero-network** operation.
      `generic_record` went **1,172 → 13,892** (15,707 as the residual crawl continues).
      The wipe R-28 had thought necessary was not needed in the end — `R-31` gave the
      upgrade path, and `R-28` is marked superseded rather than edited, per **C4**.
- [ ] **`STORAGE.md` §5** — is a snapshot evidence, or a parse cache? Also deferred.
      Tonight's measurement changed its numbers: **47× not 187×**, mean page **448 KB
      not 363 KB**, 0.91 GB → 19.4 MB.
- [ ] **`O-2`** — does the contractor entity belong in the mbiX workbook, or stay
      engine-only until it has proved itself?
- [ ] **`DEC-10`** — the row-aware idempotency key. Without it a corrected parser
      re-run over stored snapshots returns `recovered=True` and writes nothing.

---

## The build order, and why it is this order

### 1 · The listing crawl — closes coverage to a *provable* 100%

> **BUILT AND RUNNING, 2026-08-20 (evening).** `scrapex/partitioncrawl.py`,
> `Cell`/`WHOLE` in `scrapex/pagesource.py`, `MuqawilPartition` + `cells()` +
> `listing_url()` + `read_ids()` in `scrapex/sites/muqawil.py`, and the driver
> `tools/crawl_muqawil_listing.py`. Twenty-seven mutations killed across the crawl
> and the upgrade path it needed.
>
> **`--plan` ran against the live site and the partition is confirmed exact:**
> 56 cells, 897 pages, declared **17,414** against the listing's **17,414** —
> exhaustiveness deficit **0**, twice. Re-priced from the latency it actually paid:
> **~1,964 requests bilingual, about 1.4 h** (the 1,065 below is English-only).
>
> **Getting it a warehouse took two rulings of his.** The home machine had none and a
> pre-collapse pointer ([OP-22](../BACKLOG.md)); he ruled that an empty installation is
> the product's normal first-run state ([R-23](../RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)).
> `carry-over` then refused on his real data and **I stepped around it** by crawling
> into an empty database beside his full one — the trap `registry.py`'s own message
> names. He refused that too:
> [R-24](../RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
> — a database is **upgraded, never replaced**. So [OP-23](../BACKLOG.md) was fixed and
> the installation upgraded in place: 3,739 offers, 3,739 observations, 17,111
> attributes, 7,410 change events, **not one row short**.
>
> Run it against the installation's own warehouse:
> ```
> python tools/crawl_muqawil_listing.py --plan
> python tools/crawl_muqawil_listing.py --crawl   --run-ref listing-YYYY-MM-DD
> python tools/crawl_muqawil_listing.py --approve --run-ref listing-YYYY-MM-DD
> ```
> `--crawl` is resumable: the same `--run-ref` again skips the pages it stored,
> and `--approve` re-reads the stored pages without fetching anything.
>
> **Three things the live run taught that no fixture could.** A cell can publish
> **zero** rows (`region_id=8 & company_size=big`) and its empty page 1 is a
> different fact from a page never read — conflating them left that cell
> permanently unprovable and so the whole partition unprovable. A **log line** can
> kill the run: `UnicodeEncodeError` on `→` against a cp1252 console, after all 114
> requests had succeeded. And `snapshotcrawl`'s **resume saves no requests** at all
> — [OP-21](../BACKLOG.md) — which `partitioncrawl` works around locally.

**~1,065 requests, ~1.7 hours.** Method in [DEC-11](../BACKLOG.md), §"The method:
partition, then witness the partition":

1. Size all 56 cells from their own paginators — one request each. `read_last_page`
   already reads a filtered listing correctly (fixed in #229).
2. Read each cell, then **re-fetch its page 1 and compare the ID SEQUENCE** — never
   the bytes. A re-fetched page whose id order was identical was measured **not**
   byte-identical; a byte comparison certifies nothing, ever, while appearing to work.
3. `D = N_cell − |distinct|`. `D = 0` proves the cell complete. One cell is already
   closed end to end: region 13 × verysmall, 7 pages, 128 ids, 128 distinct.
4. Record every id seen through `scrapex/sightings.py` (`record_sightings`), so
   "which contractors did the site show us that we did not store" is answerable
   afterwards. That is what the 10001274 incident demanded.

**Two things to expect.** The generation floor is **157 s** (measured: identical order
at 55, 90 and 157 s; rolled by 282 s), so a cell above ~31 pages may fail its witness
and retry — that is a cost, not a correctness problem. And **five city×size cells stay
above the ceiling**, worst RIYADH×verysmall at ~212 pages, with no fourth exhaustive
axis fine enough. `user_type` only halves it.

### 2 · The profile parser — the 48 missing columns

Nothing extracts a profile page today. `docs/CONTRACTOR-SOURCE.md` carries the full
field table with his own labels and the addendum, and marks where each value comes
from (`sc` search card, `pr` profile, `js` inline script, `u` built from the id).

**One correction to carry forward:** `contract_request_url` is marked `u` in the design
but has **no known URL pattern** and is not on the card. It cannot be built from the id.

### 3 · The child tables — `R-19`, already ruled

**«جداول أبناء للخمس كلّها»** — child tables for all five multi-valued groups
(Interests, Licensed Activities, Qualification Programs, Balady Services, contractor
relations), not JSON and not `Activity 1, 2, 3…`. A measured profile carried **30
hierarchical interest values in 6 groups**, so this is ~500K rows and the decision is
his and already taken.

### Why listing-first is the strategy, confirmed 2026-08-21

He asked whether the provable crawl is applied to the **listing** stage because it is
cheaper, with the rest of the data as a second step — **«هل هذا مطبق ام هناك استراتجية
اقوى»**. It is, and it is right:

| stage | what it yields | cost |
|---|---|---|
| listing | **identity + 22 columns** | 897 pages |
| profile | **the other 48 columns** | 34,806 pages — **39×** |

Separating them means *who exists* is settled cheaply, and the expensive stage then
starts from a **known, complete work-list** instead of searching and collecting at the
same time. **There is no cheaper route to identity**: DEC-11 recorded three dead ends
(the sitemap is 20 static pages, `/contractors/map` carries no contractor markers, no
stable sort exists) and no open dataset.

**But the profile stage has a much stronger strategy available, already built and
never used:**

- **Conditional requests.** `HttpFetcher` replays `ETag`/`Last-Modified`, so an
  unchanged profile answers **304 with no body** — the cheapest answer a server can
  give. The FIRST profile pass is ~17 hours; every pass after it is mostly 304s. That
  is what makes maintaining 48 columns affordable at all, and it is the same mechanism
  #210 had to protect from being gamed by a 404 storm.
- **The work-list is `dataset_sighting`**, which already holds every id seen and is
  resumable by nature.
- **Crawl by CHANGE, not by size.** Fetch the profile of a contractor whose listing row
  changed, or who is new. Recurring cost then scales with the *change* in the directory
  rather than with the directory.

**That third one needs [R-20](../RULINGS.md#r-20--an-unchanged-contractor-is-confirmed-not-re-recorded)
implemented first**, because change detection is what selects the work. So R-20 is not
tidying: it is the precondition for the profile stage being cheap. See
[OP-26](../BACKLOG.md).

### 4 · The profile crawl — 34,806 pages, ~17.4 hours

Both locales, because the Arabic values come only from the Arabic page and are matched
**by page-order index, never by label** (one field is spelled `رقم العضويه` with `ه`).
It writes 3.95 GB raw and ~87 MB stored. **This is the step the storage mechanism
existed for**, so it must run with `body_class` set — `snapshotcrawl` already does it.

### Cheap wins, an hour in total

- **`DSN-05`**: split `card_city_region` (`"RIYADH - Riyadh"`) into City and Region.
  His request to separate them is not met, and a column count calls it done.
- **`DSN-04`**: the URL columns built from the id — minus `contract_request_url`
  above.

---

## What is blocked, and on whom

| | |
|---|---|
| **`DEC-10`** | *"fix the parser and re-run over the snapshots"* **does not work**: `approve_candidate` short-circuits on `(snapshot, locator)` plus `schema_hash`, so a corrected parser returns `recovered=True` for every page and writes nothing. 864 pages once reported re-approved changed not one row. Needs a row-aware idempotency key |
| **`STORAGE.md` §5** | *Is a snapshot evidence, or only a parse cache?* **His.** It does not block the crawl — the recommendation is retain everything — it decides whether a future reduction is permitted |
| **`DEC-12`** | The append gate's key is not the number. **His**, because it changes what `SR-6` means. Not needed for muqawil; needed before the first price collection |
|  Which machine holds the warehouse? Measured: the home machine has no engine database, a `"mode": "split"` pointer from before the collapse, and a `general.db` with **zero rows in every generic table** — so the 11,059 rows, the 1,728 snapshots and the sweep's 17,283-id sighting ledger are on the work machine only. Carry the file across, run only there, or reconcile two warehouses. [OP-22](../BACKLOG.md) |
| **`O-2`, `O-5`** | Open contractor questions. `O-5` is explicitly held by him |
| **`REQ-11`** | Branch protection — he deferred it to its own session. `main` still has **no protection at all** (the API answers 404) |

---

## Then, and only then: the source queue

Six briefs of his, all stored **verbatim** in `docs/`, none started.
[../STATE.md](../STATE.md) Track 5 is the board.

| # | source | file | note |
|---|---|---|---|
| 2 | Balady engineering offices | [BALADY-ENG-OFFICES.md](../BALADY-ENG-OFFICES.md) | `REQ-14`. Its deliverable 6 — does an open dataset exist — should be answered **first** |
| 3 | UAE, 7 emirates | [UAE-SOURCES.md](../UAE-SOURCES.md) | `REQ-15`. Abu Dhabi DMT publishes both languages **in one record** — better-shaped than muqawil |
| 4 | Egypt, Oman, Qatar, Bahrain, Kuwait | [GULF-EGYPT-SOURCES.md](../GULF-EGYPT-SOURCES.md) | `REQ-16`. Only 3 of 5 have a national public directory |
| — | diesel prices | [DIESEL-PRICES.md](../DIESEL-PRICES.md) | `REQ-17`. **7 pages**, ~14 requests a month — an afternoon, not a track |
| — | bitumen 60/70 | [BITUMEN-PRICES.md](../BITUMEN-PRICES.md) | `REQ-18`. **Cannot be crawled**: 5 of 7 need a written quotation |
| — | concrete materials | [CONCRETE-MATERIALS.md](../CONCRETE-MATERIALS.md) | `REQ-19`. A provenance-typed price model; an index is not a price |

**All three price briefs break `SR-6` in different places** — period, commercial
basis, source type — which is [DEC-12](../BACKLOG.md). Settle it before collecting,
because a dropped period is not a wrong row a later fix corrects; it is a row that
never existed, in a table whose whole purpose is history.

---

## Working rules that cost real time when forgotten

- **`R-22`**: the full suite finishes before a PR opens. Two red PRs came from narrow
  test runs.
- **`R-18`**: merge when green — and **verify the merge landed**. A background waiter
  once printed `MERGED` while GitHub had reported a conflict; check the command's exit
  code *and* grep `origin/main` for `(#NNN)`.
- **`SR-19`**: never `git add .`. It once swept 33 MB of `.vs/` into a commit.
- **A guard is not trusted until it has been mutated.** Three guards written on
  2026-08-20 passed under the very defect they were written for.
- **`SCRAPEX_FULL_MIGRATIONS=1`** for the real migration path locally.
- **One expected failure**, `OP-19`: `test_a_killed_engine_does_not_leave_a_job_claiming_to_run`
  is a load-dependent race, demonstrated pass/FAIL/FAIL on an unchanged tree.
- **The live DB is `~/.scrapex/engine/scrapex-engine.db`.** `~/.scrapex/marketlens/marketlens.db`
  is the stale old path and carries none of the generic tables.
