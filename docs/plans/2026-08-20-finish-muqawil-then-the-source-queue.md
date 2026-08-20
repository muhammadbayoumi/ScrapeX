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

## The build order, and why it is this order

### 1 · The listing crawl — closes coverage to a *provable* 100%

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
