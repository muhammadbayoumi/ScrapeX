# ScrapeX — what we found: open problems, debt, and decisions not yet built

Written **2026-07-29**. This file exists because decisions kept getting lost between
sessions. It is the single place where the project's *state* lives: what is settled, what
is broken, what was approved and never built, what shipped but nobody has confirmed, what
we deferred on purpose, and what is waiting on the owner.

It is **not** an architecture guide. It does not explain how the code works. Every entry
carries its evidence — a commit hash, a `file:line`, a number measured against the live
warehouse, or the owner's own words. Anything I inferred rather than verified is marked
**(inferred)**.

> ### ⚠ It is no longer the ONLY tracking document — read this before adding an entry
>
> A documentation system was built on **2026-08-17** ([R-09](RULINGS.md#r-09--one-documentation-system-in-the-repository-all-english)),
> and it starts at [../CLAUDE.md](../CLAUDE.md). Three registers now exist, and the
> test for where a thing belongs is **where it came from**:
>
> | it came from | it belongs in |
> |---|---|
> | **the owner asked for it** | [REQUESTS.md](REQUESTS.md) — `REQ-nn` |
> | **we found it** — a bug, a debt, a duplication | **this file** — `OP-`, `DEC-`, `DEBT-` |
> | **a decision was taken** | [RULINGS.md](RULINGS.md) — `R-nn` |
>
> **The overlap that stood here is resolved.** §1's `SR-1..SR-23` and
> `RULINGS.md`'s `R-nn` were both registers of his rulings, because `RULINGS.md`
> was written without reading this file. He ruled on **2026-08-19**
> ([R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file),
> [REQ-09](REQUESTS.md#req-09--one-home-for-rulings-not-two)): the `SR-` rules moved
> to `RULINGS.md` keeping every number, and **a new standing rule goes there, never
> here.**
>
> Also note the live state of the work has moved to [STATE.md](STATE.md), which is
> kept current per **C2**; the "Repository state" block below was last re-measured
> on 2026-08-12 and its own warning about drifting numbers applies to it again.

**Repository state — re-measured 2026-08-12**

| | |
|---|---|
| `origin/main` | `4fcc14f` — *Check the chooser owners are actually sent to, every day (#179)* |
| working tree | clean |
| suite | 1,830 engine · 570 extension · 181 node · 2 skipped · 1 xfailed · ruff and eslint clean |
| branches | **148 local / 128 remote** — see **DEC-7**, and note the number keeps being quoted stale |
| live warehouse | `~/.scrapex/engine/scrapex-engine.db`, **119.2 MB** · **90,013** price observations · **17,471** offers · **12** sources, 7 active · **59** migrations applied · 122 crawl jobs |

> **The numbers above were wrong for two weeks.** This block described 2026-07-29
> until today: a branch that no longer exists, a 75 MB warehouse that is now 119,
> nine sources that are twelve. Every figure in this file was re-measured on
> 2026-08-12 by six agents reading the code and the live database rather than
> reading this file; what they found is in **§6d**. Where an entry's own numbers
> were wrong they are corrected in place and the old figure is kept beside them,
> because a number that drifted once will drift again and the drift is the
> evidence.

**How to read an entry.** Every entry has a stable ID (`SR-`, `OP-`, `DEC-`, `BV-`,
`DEBT-`, `Q-`). IDs are never reused; when something is finished, move it to §7 and keep
the ID. Sections are ordered by consequence, not by category — data-correctness sits above
cosmetics everywhere.

---

## 1. Standing rules — MOVED to docs/RULINGS.md

**`SR-1`–`SR-23` left this file on 2026-08-19** for
[RULINGS.md](RULINGS.md#standing-rules--the-data-product-and-process-policy-sr-1sr-23),
on the owner's ruling
[R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file).
**Every number is unchanged** — an `SR-` cited in this file, in another document, or
in a test still means what it meant.

They moved because his rulings were in two registers at once: this §1 since
2026-07-29, and `RULINGS.md` since 2026-08-17, which was written without reading
this file. `RULINGS.md` is where **C1** sends every session before it designs
anything, and this document is too long to be read before every decision.

**This file keeps what it is best at** — what *we* found rather than what he ruled:
`OP-` (open problems), `DEC-` (decided, not built), `BV-` (built, not verified),
`DEBT-` (deferred on purpose) and `Q-` (questions for him). A new standing rule goes
to `RULINGS.md`; a thing we discovered goes here.

---

## 2. Open problems — known broken or wrong

Ordered by consequence.

### OP-1 · The engine on the owner's machine ran unmerged, half-written code
**Status: CLOSED, re-measured 2026-08-09.** `_host_lanes` is on `origin/main` in
`scrapex/jobs.py`; the PR was opened and merged. The account below is kept because
it is the only end-to-end description of the fault, and because it is the class of
failure **OP-13** exists to catch and still does not.
Three crawl jobs failed on 2026-07-29 between 15:23 and 15:25 with
`worker error: name '_host_lanes' is not defined` (`crawl_job` rows `job_aebc47261d01`,
`job_50a7783ad32a`, `job_b094a0510dce` — measured). The engine restarted while `jobs.py`
had the call and not yet the helpers; the commit `1deff23` says so itself. The file is
whole now, but `1deff23` is **not on `main`** and no PR exists for it (`gh pr list` tops
out at #15).
**Next action:** none. What remains is **BV-1** — it has still never been run at
width > 1 on the owner's machine.

### OP-2 · Three different answers to "which sources are active"
**Status: open.** Measured 2026-07-29:

| source | `main` | working tree | live `source_site.active` |
|---|---|---|---|
| MADAR | false | **true** | 1 |
| ALSWEED | true | **false** | 1 |
| ELBUROJ | false | false | *(no site row)* |
| ADVANCEDCASTLE | true | true | 1 |
| ELSEWEDYSHOP | true | **false** | 1 |
| MASDAR | true | **false** | 1 |
| SIKAEGSHOP | false | false | 1 |
| SAMEHGABRIEL | true | **false** | 1 |
| GPP_ENERGY | true | **false** | 1 |
| ARAMCO_FUEL_SA | true | true | 1 |

The manifest edit is uncommitted, so it exists on exactly one machine and dies with the
next `git checkout`. And the warehouse says every source is active, which contradicts both
files — either `source_site.active` is never re-synced from the manifest, or it means
something else entirely.
**RE-MEASURED 2026-08-09 — the uncommitted edit is gone, exactly as the paragraph
above predicted it would be.** `sources.yaml` in the working tree is now
byte-identical to `main`: six sources active of twelve. Nobody decided that; a
`git checkout` did, and no one noticed for eleven days. So there are **two**
answers now rather than three, and the warehouse is still the one that disagrees —
which makes the second half of this entry the whole of it.

**RE-MEASURED 2026-08-12 — the three answers are now ONE, and the disagreement
this entry exists for is gone.** Measured, not inferred:

| | |
|---|---|
| manifest (`sources.yaml` at the repo **root**, not `config/`) | 12 sources, **7 active** — ALSWEED, ADVANCEDCASTLE, ELSEWEDYSHOP, MASDAR, SAMEHGABRIEL, GPP_ENERGY, ARAMCO_FUEL_SA |
| `main` vs working tree | byte-identical (`50ff470`), nothing uncommitted |
| live `source_site.active` | the **same seven**, set for set |

So "six of twelve" (2026-08-09) is stale too: it is **seven**. What fixed it is
`80c7258` (#177) — `reconcile_active` already existed and was already correct;
the commit gave it a caller at startup and on every manifest-reload route.

**But the fix is not guarded, and that is my own failure to record.** The two
tests that cover what the commit actually CHANGED are **string greps over
`app.py`'s source text** — `source.count("_follow_the_manifest()") >= 6`. Neither
builds an app, hits a route, or reads a row. The five behavioural tests call
`reconcile_active(conn)` directly — the function that was already correct. Seven
tests pass, and they pass for the wrong reason. The route's new
`warehouse_updated` field is read by nothing: one occurrence repo-wide, its own
definition.

**Next action:** a test that drives a reload route through `TestClient` and
asserts a warehouse row changed. Then this entry can close. The remaining
question — whether **seven of twelve** is the set the owner *intends* — is
**Q-11**, and it is a decision, not a discrepancy.

### OP-3 · ~~Five currencies have no exchange rate~~ — CLOSED 2026-08-11, and it was never five

> Measured: 123 currencies in use, 119 with a rate, four without — and three of
> those four were not gaps. `UNKNOWN` is a placeholder belonging entirely to the
> deleted SPARK_ESHOP, `USD` is the base, and `SLL`/`ZWD` retired in 2022 and
> 2009. Named in `UNQUOTABLE` (#156). The original text below is kept because its
> premise — a page-shape change — was wrong, and that is worth knowing.

**Status: open.** Live `scrapex_meta.runtime_rates_note`, 2026-07-29T12:18:32Z: 116 rates
stored, five refused —

> `PEN`, `SLL`, `SYP`, `VEF`, `ZWD`: *no rate found on the page (neither `data-last-price`
> nor the display figure) — the page shape has changed*

The message blames the page shape, but four of the five are currencies that have been
redenominated or withdrawn (SYP, VEF, ZWD, SLL), which suggests Google Finance simply does
not quote them any more — a different problem with a different fix. GPP prices in 100+
currencies, so those countries' converted column is blank.
**Next action:** open one of those quote URLs by hand. If the pair is gone, drop it from
the fetch list with the reason recorded; if the pair is there, the parser is what broke.

### OP-4 · `scrapex/webui/app.py` is 3,347 lines / 95 routes, and the extraction it started stopped
**Status: open. Re-measured 2026-08-12.**

| when | lines | routes |
|---|---|---|
| `REVIEW-2026-07-28` | 1,820 | 82 |
| 2026-07-29 | 2,480 | 89 |
| 2026-08-09 | 2,955 | 95 |
| 2026-08-11 | 3,246 | 98 |
| 2026-08-12 (*Sheets moves into the panel*) | 3,198 | 93 |
| **2026-08-12 `4fcc14f`** | **3,347** | **95** |

**Two things this entry said are wrong, and both make the work easier, not harder.**

*"It has grown at every measurement"* — it has not. One PR reduced it by 48 lines
and 5 routes. The trend is still upward, but the sentence was rhetoric, and
rhetoric in a measurement file is how a number stops being checked.

*"The router-factory pattern is already applied inside the same file to four
fragments"* — it is not inside the file. `grep -nE 'def [a-z_]*(router|_api)\w*\(' scrapex/webui/app.py`
returns nothing. All four factories live in **sibling modules** and are imported
(`app.py:47`, `:161`, `:162`):

| module | lines | routes |
|---|---|---|
| `scrapex/webui/catalog_api.py:21` `create_catalog_router` | 122 | 8 |
| `scrapex/webui/database_api.py:11` `create_database_router` | 82 | 3 |
| `scrapex/webui/database_api.py:65` `create_domain_health_router` | *(same file)* | |
| `scrapex/extract/api.py:42` `create_extraction_router` | 134 | 6 |

338 lines and 17 routes are out; 3,347 lines and 95 routes are still in. The
pattern is *extraction to a module*, already proven three times — so the next
action is smaller than the entry implied. `catalog_api.py` and `database_api.py`
are byte-for-byte the same size as on 2026-08-09: no extraction has happened in
three days.

The regex-scraping test is real and still there: `tests/test_ui_manifest.py:25`.

**Next action:** continue the extraction. The alternative branch — declare the
size acceptable and delete the pattern — is contradicted by the file itself,
which added 392 lines in three days. *"Keep extracting when there is time" is not
a third option; that is what has been happening.*

### OP-5 · `reports.py` computes the six history statistics twice, and the price has already been paid once
**Status: open. Line numbers corrected 2026-08-12.** `export_source_table`
(`scrapex/reports.py:1214`, was cited as `:982`) and `table_payload` (`:1997`, was
`:1664`) each carry their own copy; the file is now 2,795 lines. This was a
maintenance argument until the review found the owner's own comment in the code
recording that adding one column shifted `observations` / `min` / `max` /
`previous` by one during the brand work.

The duplication is between the `_EXPORT_SELECT` dict (`:1016`, entries at
`:1064-1078`) and `table_payload`'s own restated subqueries.
**Next action:** one expression source read by both — and have `table_payload`
read its results **by alias** rather than by `r[19]..r[22]`, so the shift-by-one
class of defect dies with the duplication instead of merely moving.

### OP-6 · Four review findings were never refuted, and one of them is about test coverage
**Status: partly closed, partly unknown.** `REVIEW-2026-07-28` §5 warns that the
refutation stage for eight findings (ت1–ت8) died on a session limit, and that at the
observed rate (6 of 18 fell under refutation) **2–3 of the eight should be wrong**. Do not
treat them as facts.

| claim | status now |
|---|---|
| ت4 `matching.py` rescans the material table per product per name | **fixed** `0a2209c` |
| ت5 `LocalSink` reloads the whole workbook per tab | **fixed** `0a2209c` |
| ت6 the panel rebuilds the log every 1.5s and steals the selection | **fixed** `f901638` |
| ت7 the whole 45-test panel suite silently skipped in CI | **fixed** `48ec48b` + the ≥40 collection floor in `ci.yml` |
| ت1 restore / start-fresh always broken while the worker thread runs | **HALF closed, re-measured 2026-08-12** — *start-fresh* is guarded and tested; `/api/storage/restore` has **no** active-job 409. Refusing is the correct behaviour, and only one of the two routes does it |
| ت2 the heartbeat is written between jobs only, so the engine declares itself dead mid-crawl | **OPEN — and its stated cause is now wrong.** See below |
| ت3 every run rebuilds the full derived timeline of every touched offer | **open** — the entry pointed at DEBT-4; it means **DEBT-3** |
| ت8 the `grid.js` XSS guard scopes itself by splitting on two comments and leaves a gap | **changed** — that guard is gone. Its replacement scopes by line-suffix and by a 14-word `_TEXT_BEARING_FIELDS` allowlist, which leaves two nested markup builders unchecked |

**ت2, measured rather than read (2026-08-12).** Two probes driving a real
`JobRunner`:

- The docstring's stated root cause — *"the loop hands its whole pass to
  `run_job_once`"* — **is stale**. Jobs run on their own threads
  (`jobs.py:1450`) and `touch_runtime_heartbeat` fires every poll
  (`jobs.py:1334`): 6 distinct heartbeats in 12 s.
- The real cause: when a job **holds an open write transaction** — which a long
  ingest does — `touch_runtime_heartbeat` raises
  `sqlite3.OperationalError: database is locked` from `jobs.py:1035` and the
  runtime heartbeat **freezes** (1 distinct value across 45 s).

And only one of the **two** `worker_alive` computations was fixed:

| where | what it calls | verdict |
|---|---|---|
| `scrapex/webui/app.py:1450` — `/api/health` | the new two-heartbeat `worker` verdict | correct; the panel reads this one (`extension/engine.js:38`) |
| `scrapex/webui/app.py:2438` — `_about` | `worker_is_alive(conn)`, single heartbeat | **the function the fix superseded** |

`_about` renders the engine's own `/settings` page
(`scrapex/webui/templates/settings.html:162-167`), so **the engine still shows
"Not running" while it is crawling**, and advises the owner to check whether the
engine is started at all.

**Next action:** three separate things — the second `worker_alive` at
`app.py:2438`; the heartbeat's behaviour under a held write lock; and the 409 on
`/api/storage/restore` with a mirror of
`test_start_fresh_is_refused_while_a_crawl_runs`.

### OP-7 · `/api/native-host/register` takes no authentication and REPLACES the allowlist
**Status: open, needs an owner decision (**Q-8**).** `REVIEW-2026-07-28` §2 #2. Since the
origin lock (`3d7d1a9`) no web page can reach it, but this route is the *deliberate*
exemption from the guard — any extension reaches it, and `install()` overwrites the list so
registering one id evicts the one that was working. It writes an HKCU registry key.

### OP-8 · The Apps Script funnel is frozen on v1 payloads and the block is on the owner's desk
**Status: open, blocked on the owner.** Live `scrapex_meta.setting:apps_script_last`,
2026-07-26T13:40:49Z:

> *"Delivered 87 rows in 19 chunk(s). The sheet did not confirm writing — update the pasted
> script (Copy Script) to get write confirmations, or run Rebuild tables from the sheet's
> ScrapeX menu."*

The vocabulary sweep changed `product_name`'s meaning, so the old pasted script acks each
chunk, throws inside `reassemble_`, and keeps republishing the last v1 batch — alive,
openable, and frozen for three days.
**Next action:** owner opens Settings → Copy Script and re-pastes it. Nothing else unblocks
it.

### OP-9 · 154 rows hold a name with no Arabic character in the Arabic column
**Status: open, small, and it is stale data rather than a code defect.** Measured today
across 3,799 products: **MADAR 147, GPP_ENERGY 6, MASDAR 1** carry a `product_name_ar`
containing not one Arabic character. The GPP six are the material keys (`DIESEL`,
`GASOLINE`, …) folded there before the sweep. A re-crawl of each source moves them.
Memory recorded 148; the measured figure is 154.
**Next action:** re-crawl MADAR and GPP, then re-measure. Tax survives regardless — the
material key is read through `COALESCE(NULLIF(product_name,''), product_name_ar)`.

### OP-10 · MASDAR is missing nine English names, and MASDAR is a bilingual source
**Status: open (new — found while writing this file).** Measured: 9 of 617 MASDAR products
have an empty `product_name`. ALSWEED (1203/1203) and SAMEHGABRIEL (18/18) are *correct* —
salla and woo are monolingual and the empty English column is the pinned rule (SR-15). But
hybris publishes both, so under **SR-2** nine missing English names are a defect.
**Next action:** find out whether those nine products genuinely have no English name on the
site (then it is data) or the English pass dropped them (then it is a bug).

### OP-11 · 2,385 attribute rows carry no language mark
**Status: open, deferred once already.** The vocabulary sweep deferred MADAR /
SAMEHGABRIEL's `lang=''` attribute rows; memory recorded 1,129. Measured today:
**2,385**. It has more than doubled, so whatever produces them is still producing them.
**Next action:** find the connector path that emits an attribute with no `lang` before
back-filling, or the backfill will be undone by the next crawl.

### OP-12 · ~~No linter, formatter or type checker~~ — PARTLY CLOSED 2026-08-11

> ruff gates `scrapex/` and caught three of my own mistakes in one day. `mypy
> --strict` was RUN over the price files and reported 72 findings — 14
> correctness-shaped, of which 10 were false and 2 real, both fixed (#157). The
> GATE is deliberately not added: 60 of the 72 are annotations and that churn
> buys no defect. Widening ruff to `tests/` and `tools/` is still open.

**Status: open, but NOT as the line below said.** ~~No `ruff`, no `mypy`, no
`eslint` anywhere~~ — that sentence was false when it was written down and is kept
struck through rather than deleted, because it is the clearest example in this
file of a status line surviving the thing it described.

Measured 2026-08-12 from `.github/workflows/ci.yml`:

| gate | what it covers |
|---|---|
| `ruff==0.16.2` (`ci.yml:30`) | `scrapex/` **only** |
| `eslint@9.39.0` (`ci.yml:38`) | `extension`, `scrapex/webui/static`, `contract`, `apps_script` |
| mypy | **nowhere.** No CI step, no `pyproject` section, no `mypy.ini`, no pre-commit |

`python -m ruff check tests/ tools/` → **395 errors, 233 auto-fixable** (378 of
them in `tests/` alone). mypy 2.3.0 is already installed on the owner's machine,
so nothing but a missing CI step stands between here and a gate.

**Next action:** widen ruff to `tests/` and `tools/` (fix the 233, decide the
rest), and either add the mypy gate or move it to §5 as a declared debt with its
reason — the current state is neither.

### OP-13 · ~~There are no end-to-end or chaos tests~~ — CLOSED 2026-08-11
Killing the engine mid-job, corrupting a checkpoint, force-closing the browser
were all named in ENGINEERING T7 and none was implemented. They exist now:
`tests/test_the_engine_survives_being_killed.py` and the end-to-end test added in
the same PR. **The chaos test's own reliability is the live problem — see OP-19.**

### OP-14 · The Native Messaging size ceiling — the backwards sentence is already gone
**Status: changed, minutes of work left.** `scrapex/native.py` no longer carries
the reversed claim the entry describes, so the thing to settle is settled. What
remains is that the comment still does not state the two limits plainly.

**Next action:** one comment edit — a host→extension message is capped at 1 MB;
extension→host is 64 MiB — and drop the "decides whether a large record set can
be returned at all" clause, which was the reason for urgency and no longer holds.

---

### OP-15 · The panel talks about the engine in the wrong places, and says it twice differently

Reported by the owner on 2026-08-11 with the engine at 0.2.2 and the unpacked
extension at 0.2.1, so all of it is visible on a real installation right now.
Recorded in full as issue #160; the four parts are:

- The version-mismatch banner follows the reader onto **all eleven views**. It
  sits outside every view deliberately — its comment argues that a warning you
  have to hunt for arrives after the owner has already asked why a feature is
  missing. That reasoning was sound before the Engine page existed. Moving it is
  a **reversal of a documented decision**, so whoever does it must answer the
  original problem rather than delete the note.
- The Engine card reads `Installed version 0.2.2 / Latest released 0.2.1` while
  the banner above it reads `Installed extension 0.2.1 / Engine 0.2.2`. Each is
  correct alone. **The word "installed" means two different things two inches
  apart.**
- Engine controls stay enabled when there is no engine to control.
- The About page carries three version numbers and eight capability entries with
  their own commit hashes. That is a changelog, on the page a person opens to
  find out what the thing is.

The owner's own rule decides most of it without arguing case by case: *leave what
belongs to the extension where it is, and tie everything else to the engine.*

### OP-16 · "Closing the panel never stops a run" is asserted in a comment and checked by nothing

`extension/app.js` opens by stating that the panel is a remote control, that
closing it never stops a run, and that reopening reconnects to whatever is in
flight. **No test exercised any of it** — every panel test opened the panel, drove
it, and ended. Issue #161.

**Half of this is now closed. Re-measured 2026-08-12.** *Reopening reconnects* was
the fragile half and it was also **false**: a reopened panel showed a live crawl
as idle. `reattachToRunningJob` and the panel-visibility handling fixed it and
tests drive it.

*Closing never stops a run* is **still asserted and still checked by nothing.**
It is probably true — the engine owns execution — but the panel holds a poll loop
and, since #152, work that begins on `load`; if the close path aborts a request
the engine reads as a cancel, a long crawl dies because the owner closed a side
panel to read a page, and they would never connect the two.

**Next action:** restate this item as the first half only, and pin it with a test
that fires `pagehide` on a panel with a job in flight and asserts the job row is
still queued or running afterwards.

### OP-17 · `carry_over` cannot merge a table that lives in both old databases

Found by running the carry-over for real on 2026-08-11. Both old files number
their rows from 1, so any table present in BOTH collides on its primary key and
`INSERT OR IGNORE` drops the second file's rows without a word. It did not bite
the owner only because no table of theirs lives in both.

**Refusing is the correct behaviour and the row-count guard already produces it**
— 45 read, 40 written, pointer not moved. Recorded rather than fixed, because a
merge would have to invent new keys and rewrite every foreign key that points at
them. Worth doing only if a real installation ever needs it.

A second thing that run taught, worth keeping beyond this item: **`INSERT OR
IGNORE` swallows a CONSTRAINT failure exactly as quietly as it swallows a
duplicate.** A row violating a NOT NULL in the new schema vanishes with no error;
the row count is the only thing that notices. `PRAGMA table_info` does not show
CHECK constraints at all, which is why the test fixture was wrong three times
before it was built from the shipped schema instead of from memory.

### OP-21 · `snapshotcrawl`'s resume saves the write and none of the requests

**MEASURED 2026-08-20**, by resuming a nine-page crawl and counting: the second run
made exactly as many requests as the first.

The module's own docstring gives the reason it exists in requests —
*"a second attempt re-fetched every one of them — on a full pass, hours of requests
to re-learn what was already on disk. Keeping the evidence and re-fetching it
anyway is not a resume."* The implementation checks the resume in the wrong place:

```
scrapex/snapshotcrawl.py:154   def store(page: FetchedPage) -> None:
scrapex/snapshotcrawl.py:156       if page.url in seen:
```

`store` is the walker's `on_page`, and `PageWalker.walk` calls it **after**
`self._get(url, …)` has already fetched. So a resumed run re-fetches every page and
then declines to store it. It saves the INSERT and the compression, which is real,
and none of the hours, which is what was claimed.

**Not fixed here, per [R-01](RULINGS.md#r-01--diagnose-confirm-then-fix--one-step-at-a-time)**
— where the skip belongs is that module's own decision, and the honest fix moves
the check into the walk rather than adding a second one. `scrapex/partitioncrawl.py`
needs a resume that actually saves requests because it is a ~2,000-request crawl, so
it filters the already-stored URLs out of the `PageSource` before the walk sees them
(`_Unstored`) and reads those pages' ids back off the stored snapshot instead of off
the wire. That is a local answer, and it leaves this defect standing for every other
caller.

**Why it matters beyond the tidiness:** the resume is the reason a crawl can be
interrupted. An eight-hour profile crawl (step 4 of the muqawil plan, 34,806 pages)
interrupted at hour six would, today, re-fetch six hours of pages to store nothing.

### OP-22 · The warehouse exists on ONE of the two machines, and the pointer on the other is pre-collapse

**MEASURED 2026-08-20 on the home machine**, before anything was run:

| | |
|---|---|
| `~/.scrapex/engine/scrapex-engine.db` | **does not exist** |
| `~/.scrapex/databases.json` | `"mode": "split"` — the layout from before the two databases were collapsed into one, so `DatabaseRegistry.defaults()` **raises** |
| `~/.scrapex/general/general.db` | 192 KB, has the generic tables and **0 rows in every one of them**; no `dataset_sighting`, no `snapshot_dictionary` |
| `~/.scrapex/marketlens/marketlens.db` | 21 MB, and carries none of the generic tables |

So the 11,059 contractors, the 1,728 page snapshots and — the part that cannot be
re-derived — the `dataset_sighting` ledger from the six-pass sweep, with its 17,283
ids and their frequency distribution, are on the work machine only. The home machine
can read every document describing them and open none of them.

> **THE FRAMING BELOW WAS MINE AND HE OVERTURNED IT THE SAME DAY. Kept per C4/C5.**
> I wrote that this is *"`CLAUDE.md`'s founding failure in the one place the
> repository cannot follow it"*. It is not a failure at all:
> [R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)
> — ScrapeX is a tool **many people install**, so an installation with no warehouse
> is the product's **normal first-run state**, and a warehouse is per installation.
> The repository rule is about decisions and knowledge, which do travel; a user's
> collected data was never meant to.
>
> **What survives as a real finding** is the second half: a *coverage number is a
> fact about one installation*, so "11,059 of 17,403" must never be written as a
> project-wide truth — and any session must check which warehouse it is looking at
> before trusting one. That part stands, and it is why this entry is not deleted.

~~**This is `CLAUDE.md`'s founding failure in the one place the repository cannot
follow it.** A document is committed and travels; a 796 MB database is not and does
not.~~

**The question it raised was the owner's** and was recorded as `O-6`: carry the file
across, run only where the data is, or let each machine hold a warehouse and
reconcile them. **He chose none of them** — see the note above. It never blocked the
*build*; the crawl was written, tested and priced without it.

### OP-23 · ~~`carry_over` cannot carry a pre-0058 installation~~ — FIXED 2026-08-20, and the fix was a ruling first

> **CLOSED THE SAME EVENING IT WAS FOUND, because the owner ruled that it was not a
> backlog item.** I had recorded it here and stepped around it by creating a second
> warehouse. He refused that:
> [R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
> — a database is upgraded, never replaced, and a migration that refuses on real data
> is a release blocker rather than debt. The diagnosis below stands as written; what
> changed is who it was for.
>
> **Fixed and verified on the real installation:** `Backfill` in
> `scrapex/databases/carry_over.py` supplies the columns the engine schema requires
> and the split-era schema never had, reusing migration 0058's own
> `legacy_unwitnessed` rather than minting a second literal, conditional exactly as
> 0058 is. The carry-over then ran: **3,739 offers, 3,739 observations, 3,739 periods,
> 17,111 attributes, 7,410 change events, 966 products — not one row short**, 261
> offers marked legacy, 3,478 without a unit untouched, old files read-only and still
> in place. Guarded by
> `tests/test_a_carry_over_upgrades_rather_than_starting_over.py`; six mutations killed.
>
> **Two things it had to be at the INSERT rather than after it**, both measured:
> the trigger fires on INSERT so a later `UPDATE` never runs; and copy-then-migrate —
> the elegant design, which would have got every migration's backfill for free — is
> architecturally closed, because the engine schema is DERIVED and starts a new stream
> at v1. A copy of `marketlens.db` is refused on `application_id` (1398295884) before
> its `user_version` of 55 is even read. That measurement is why the row-copy design
> in `carry_over` is correct by necessity and not by oversight.

### The diagnosis, kept because it is where the fix came from

**MEASURED 2026-08-20, by running it for real on the home machine** while creating the
warehouse [R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)
calls for. `scrapex carry-over` refused:

```
error: a selling unit must carry its provenance and its witness
```

**It refused correctly and moved nothing** — the pointer is still `"mode": "split"`,
which is the safety design in `carry_over`'s own docstring working exactly as written.
But the documented upgrade path for this installation is now closed.

**The cause, exactly.** Migration 0058 added `unit_basis_provenance` and
`unit_basis_witness` to `source_offer` plus two triggers that refuse a row carrying a
`selling_unit_id` without both. `carry_over` INSERTs the old rows into an
already-migrated database, so the triggers see them — and the old schema has **no such
columns at all**:

| | |
|---|---|
| `source_offer` rows in `marketlens.db` | **3,739** |
| of those, carrying a `selling_unit_id` | **261** |
| `unit_basis_provenance` / `unit_basis_witness` in the old schema | **the columns do not exist** |

**And the fix needs no decision about evidence, which is why this is a defect and not
a question.** 0058 already faced the same rows in the in-place upgrade path and answered
it — [db/migrations/0058_a_unit_that_can_name_who_said_it.sql:89-90](../db/migrations/0058_a_unit_that_can_name_who_said_it.sql)
sets `unit_basis_provenance = 'legacy_unwitnessed'` with a witness that says in words
that nobody can say where the value came from. So the honest value exists, is named,
and counts as unresolved under the resolution metric. `carry_over` simply never applies
it, because it copies rows rather than migrating a file.

~~**Not fixed here, per R-01.**~~ **Struck 2026-08-20:** R-01 governs a fix landing before the CAUSE is agreed, and the cause was agreed the moment it was measured. What I actually did was defer a release blocker, which is what R-24 refuses.
It touches the path that carries the owner's 3,739 price observations, which is the
highest-consequence surface in the project, and it is unrelated to the muqawil crawl
this pull request is about. The shape of the fix is one `UPDATE` after the copy, reusing
0058's own literal rather than inventing a second one — and it needs a test that the
carried rows come out marked `legacy_unwitnessed` rather than merely arriving.

**A sibling of [OP-17](#op-17--carry_over-cannot-merge-a-table-that-lives-in-both-old-databases)**,
and the same lesson from a different direction: that entry recorded that
`INSERT OR IGNORE` swallows a CONSTRAINT failure as quietly as a duplicate. Here the
constraint is a TRIGGER, so it aborted loudly instead — which is better, and is why
this was found in one command rather than by counting rows afterwards.

### OP-24 · The marketlens → engine rename is a MANUAL command, so a shipped user gets a dead engine

**HIS QUESTION, 2026-08-20, on the board as [REQ-20](REQUESTS.md#req-20--the-database-rename-must-reach-every-user-not-just-this-machine):** «قاعدة بيانات marketlens تم تغيير اسمها — هل تم تغيير
اسمها عند كل المستخدمين؟» The answer is no, and it was measured rather than reasoned.

**The mechanism exists and the product does not reach it.** `carry_over` has exactly
**one** production caller — the manual subcommand `scrapex carry-over`
(`scrapex/cli.py:993`). Nothing automatic calls it: not `ui`, not autostart, not the
native host, not the panel.

**What a split-era user actually gets**, simulated end to end against a fake split
installation:

| path | result |
|---|---|
| any CLI command | clean message naming `scrapex carry-over` — `main()` catches everything (`scrapex/cli.py:1127`) |
| `native.startup_check()` — how the PANEL starts the engine | `ok: false`, `action: "check_storage"`, detail = *"Run 'scrapex carry-over'"* |
| `native.upgrade_database()` — **the panel's own repair action** | `ok: false`. **It cannot fix this**: `DatabaseRegistry.defaults()` refuses before `initialize()` is ever reached |

So the one button the product offers for a database problem is unable to fix the one
transition every existing installation must make — and it reports the failure as
`check_storage`, which is the wrong action: nothing is wrong with the storage.

**THE PROJECT HAS ALREADY RULED ON THIS EXACT SITUATION, and the ruling was not applied
here.** `cli._upgrade_what_is_only_behind` exists because of his instruction of
2026-08-05, and its docstring is this entry's whole argument:

> Migration 0061 merged and was never applied here, so the next time the engine started
> it refused — correctly, and with the exact command to run — and the owner saw only a
> dead engine. The rule protected the data and cost him the product, because **the one
> person the refusal speaks to is the one who does not read a log.**

That reasoning was applied to *migrations* and never to *carry-over*, which is the
bigger of the two transitions.

**And the automatic version is SAFER than the one already shipped**, which is the part
that makes this cheap. `_upgrade_what_is_only_behind` advances the user's file in place
and therefore has to take a backup first. `carry_over` opens both old files
**read-only**, writes a new one, verifies every table's row count, and moves the
pointer **last** — so the old files are the backup, by construction, and a failure
leaves an installation that refuses to start rather than one that starts on half its
data.

**Shape of the fix**, for whoever picks it up: call `carry_over` from the same place
`_upgrade_what_is_only_behind` is called (`scrapex/cli.py:761`) when the pointer is
split, say so on stdout and in the log naming both source files, and give
`native.upgrade_database()` the same path so the panel's button works. Then a test
that a split installation **starts**, which is the test nobody has written — every
carry-over test to date has called `carry_over` directly, so the gap was invisible.

**Not built here.** It is a different concern from the muqawil crawl in flight, and
under [R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
it is a **release blocker** rather than debt — so it is his call whether it goes in its
own session now or immediately after the crawl lands.

### OP-25 · The partition made the crawl provable and broke the approval, for the SAME reason

**MEASURED 2026-08-21 on the first partitioned crawl.** 897 stored page-pairs went
through `--approve`. **74 approved, 823 refused** with
`ExtractionConflict: This dataset already has a different approved schema.`

**74 is not a round number and it is not random.** `region_id=0`'s four cells are
`1 + 4 + 10 + 59 = 74` pages, and `region_id=0` **is** the 1,438 contractors who
publish no location at all. Their cards carry no location box, so:

| page | fields |
|---|---|
| `region_id=0 & company_size=big` | **21** — no `card_city_region` |
| `region_id=1 & company_size=big` | **22** |

Those 74 pages taught the dataset a 21-field schema, and every located contractor's
page after them presented 22 and was refused.

**The cause is the partition itself, which is what makes this worth writing down.**
`_candidate_from` derives the field list from the union of THAT PAGE's cards. The old
unfiltered crawl mixed every kind of contractor onto every page, so
`card_city_region` was always in the union and the schema was stable — 864 pages
approved into 11,059 records. The partition deliberately **groups like with like**, so
the first cell is systematically unrepresentative. The same property that makes a cell
provably complete makes its schema a bad sample.

**The full card field set, measured across page 1 of every cell:** 15 fields, of which
14 appear on every page that has any cards, and only `card_city_region` varies (58 of
64 pages). The intersection reads 0 because one cell — `region_id=8 &
company_size=big` — publishes **no contractors at all**, so its page contributes an
empty set.

**The fix is already written in the same file, for the same reason, applied to only
half the problem.** `extract/muqawil.py` declares `BILINGUAL_CARD_FIELDS` and says why:

> Emitting `_ar` only where an Arabic value happened to be found made the column list
> depend on which contractors that page's Arabic half showed — and the listing
> reorders, so 118 pages in 119 were refused as a different schema. Which fields the
> SITE translates is a fact about the site, so it is declared here … and an absent
> value is a NULL in a column that is always there.

That argument is identical and covers the `_ar` half only. **The base card fields need
the same declaration**: which boxes a card can carry is a fact about the site, not
about which twenty contractors a page happened to show.

**AND IT NEEDS A DECISION, because the 74 pages already landed.** A parser that always
emits 22 fields produces a different `schema_hash`, so those 74 are refused too. Three
ways out, and the choice has data consequences:

- **(a) Wipe the `contractors` dataset and re-approve all 897 pages from disk.** ~20
  minutes, **no re-fetching** — the snapshots are stored, which is the whole economics
  of the seam. Cleanest, and destroys 1,172 rows that would be immediately rebuilt.
- **(b) A new dataset key.** Keeps the 74 pages' dataset, and leaves two datasets
  describing one directory — which `R-11` would not thank anyone for.
- **(c) Schema-drift review support**, which the error message itself points at and
  which does not exist. The largest option and the one that would help every future
  source.

*Recommended: (a), and it is only cheap because nothing has to be re-fetched.*

### OP-26 · The contractor directory can be COLLECTED but not MAINTAINED

**MEASURED 2026-08-21**, answering [REQ-22](REQUESTS.md#req-22--what-happens-on-a-new-contractor-a-vanished-one-a-changed-one-and-on-update).
Collection is in good order after this session — provable, evidence-stored,
resumable, and every id seen is recorded. **Everything that happens after the first
crawl is missing**, and these are four separate defects that share one cause: nothing
has ever run a SECOND crawl of this source through to rows.

> **FIRST, A DISTINCTION HE HAD TO CORRECT ME ON, 2026-08-21.** I wrote this entry as
> though "missing" and "disappeared" were one problem. They are two, and only one of
> them is detectable:
>
> > «لو تقصد المقاول الذى سالت عنه برقم العضوية فهذا لانى اعرف هذا المقاول بالتحديد
> > وبعد اول زحفة لم اجده ضمن المقاولين ولكن هذا لا يعنى بالضرورة انى اعرف باقى
> > المختفيين»
>
> | | what it is | can it be detected? |
> |---|---|---|
> | **never seen** | no pass has ever shown this contractor. **10001274's case** | **no — not who, only how many.** That number is the deficit `D`, which is why closing `D` is the only thing that addresses it |
> | **disappeared** | seen and STORED, then absent from a pass that proved it read every row of that contractor's cell | yes, by query — and nothing does it |
>
> **He found 10001274 because he happened to know that company.** That is exactly what
> does not scale: the rest have nobody to ask after them. So the sighting ledger and
> `missing_ids` answer "stored vs sighted" — a real question — and neither of them
> reaches a contractor the site has never shown us at all. Only `D` does.

**1 · A contractor that disappears is invisible** — **DETECTION BUILT 2026-08-21, the
write still open.** No production code moves a `generic_record` out of `'active'`, so
a delisted contractor keeps `status='active'` with a frozen `last_seen_at` and is
**indistinguishable from one this run did not crawl**. That matters more than it
looks: the listing SHRANK by 25 rows on the night of 2026-08-20, so departures are
routine.

> **A CORRECTION TO THIS ENTRY, and it changes what has to be decided.** It said no
> code sets `status = 'superseded'`. **`generic_record` does not accept that value at
> all** — its CHECK is `status IN ('active','unavailable','retired')`
> ([db/engine/schema.sql:303](../db/engine/schema.sql)). `'superseded'` belongs to
> `source_offer` and `source_variant`, which is where I read it from. Found by a test
> raising `IntegrityError` on the value this entry recommended.
>
> **So the schema anticipated departure and offered TWO words for it**, and choosing
> between them is a decision rather than a detail:
>
> | | |
> |---|---|
> | `unavailable` | the site is not showing this contractor **right now** — reversible, and the row comes back on the next crawl that sees it |
> | `retired` | it is gone, and the row is history |
>
> A directory that reorders and churns by 25 rows a night will produce both, and
> reading one as the other either loses a real delisting or retires a contractor over
> a page the crawl happened to miss. **His call.**

**`sightings.departures` is the detection**, and it is read-only on purpose: a cell
closed with `D=0` proves the crawl saw every row it publishes, so a stored row of
that cell missing from the run **has left**. A query, not a re-crawl — and it keeps
two lists apart, because a row with no sighting at all is a gap in the LEDGER (it
predates #227) and not a contractor leaving. It reaches only rows we already HOLD; a
contractor never shown to us is in neither list, which is the distinction he had to
correct me on above.

**2 · An unchanged contractor still writes history**, contrary to
[R-20](RULINGS.md#r-20--an-unchanged-contractor-is-confirmed-not-re-recorded). The
ruling says a second crawl finding no change updates `last_seen_at` and writes no
revision; `content_hash` is on the table and **is not consulted on ingest**. 34,550
revisions for 11,059 contractors, from two crawls of a directory that barely moved.
R-20 records this as a change to the write path rather than a description of it, and
it is still unwritten.

**3 · There is no path from the product's own interface.** `scrapex/jobs.py` — what
the panel drives through `POST /api/jobs` — contains **no reference to** `muqawil`,
`generic_record`, `partitioncrawl` or `snapshotcrawl`. Pressing the panel's update
button runs the price connectors and does nothing whatever to the contractors. They
can be crawled only by `tools/crawl_muqawil_listing.py` from a terminal. Same family
as [REQ-20](REQUESTS.md#req-20--the-database-rename-must-reach-every-user-not-just-this-machine):
a capability that exists and that the product cannot reach.

**4 · And the schema question gates the rows**, [OP-25](#op-25--the-partition-made-the-crawl-provable-and-broke-the-approval-for-the-same-reason),
deferred by [R-25](RULINGS.md#r-25--the-crawl-method-is-settled-first-the-schema-and-retention-questions-come-last).

**Why all four were invisible until tonight.** Every test of this path approves a
page or two into an empty database. The defects are all in the SECOND pass — what
happens to a row that already exists, or that should stop existing — and
`LESSONS.md` already says it in those words: *"test the second crawl, never the first
ingest."* This source had never had a second crawl reach rows at all.

### OP-27 · A site's own id has no indexed column, so every coverage question is a table scan

**MEASURED 2026-08-21 on the live warehouse**, and the numbers are not marginal:

| | before | after |
|---|---|---|
| `coverage` | **49.74 s** | 0.03 s |
| `missing_ids` | **48.81 s** | 0.03 s |

The two together exceeded the two-minute limit, so `--coverage` simply never
returned. **~1,600×**, for the same answers.

**The cause is that the warehouse has nowhere to put a site's own identifier.**

- `generic_record.record_key` is `_digest(_canonical(identity))` — a **SHA-256**.
  Measured: it equals the contractor id on **0 of 1,172 rows** (`'ff88670d…'` against
  `'20044482'`).
- The id itself lives **inside `data_json`**, reachable only as
  `json_extract(data_json, '$.contractor_id')`, and **no index can serve that**.

So every question of the form "do we hold the row for this id" was a correlated
`EXISTS` scanning `generic_record` once per sighting: 14,180 × 1,172 = **16.6M**
comparisons.

**What was done, and what it is not.** `sightings.stored_ids` reads each side once and
intersects in Python — O(n+m). That is a route around the problem and it scales to the
17,403 contractors, **not** to `R-19`'s child tables, which are projected at ~500K
rows across five groups. At that size the set fits in memory but the full scan of
`generic_record` per call does not stay cheap.

**The structural fix is an indexed `external_id` on `generic_record`**, written at
approval time from the dataset's declared identity field. It is a migration plus a
write-path change, it would make every one of these an index seek, and it benefits
every future source — which is why it is here and not folded into a performance patch.

**And it hid a correctness defect, which is the part worth remembering.** Because
`record_key` looks like it should be the id, the first draft of `departures` joined on
it and would have reported **every stored row as unsighted**. The tests passed: the
fixture wrote `record_key = contractor_id`, which production never does. The fixture
is fixed (it now hashes exactly as the write path does) and reverting the join fails
four tests — but a column named for what it actually holds would have made the mistake
unavailable in the first place.

---

### OP-28 · The muqawil crawl driver has 306 lines and no tests at all

Found 2026-08-21 while scoping what a Windows-only failure could hide.
`tools/crawl_muqawil_listing.py` — the driver for `--plan`, `--crawl`, `--approve`,
`--coverage`, `--only`, `--heavy-attempts`, `--not-seen-since` — is referenced by
**zero tests**:

```
grep -rln "crawl_muqawil_listing" tests/   ->   no matches
```

It is also the file where the one Windows-only defect of this whole track lived: a
`UnicodeEncodeError` on `→` in `say()` killed a run **after all 114 requests had
succeeded**, because the console codepage is cp1252 and the arrow is not in it. The
fix (a `say` that cannot raise) is guarded by nothing, and CI cannot catch a
regression: CI is **ubuntu-only**, and `tools/` is not even in the linted path
(`ruff check scrapex/`).

So the exposure is specific rather than theoretical: **argument handling, resume
selection and console output in the one file whose failure mode is invisible to CI.**
Not urgent — it is a developer tool, not shipped code — but it is the cheapest test
debt on the board, and `say()` in particular is one parametrised test.

---

### OP-29 · ~~An invalid escape sequence in a test docstring is a future `SyntaxError`~~ — FIXED 2026-08-21

> **CLOSED THE DAY AFTER IT WAS FILED, and the one character is a guard now rather
> than a memory.** `tests/test_relaunch_log.py:85` opens `r"""`, so the Windows path
> the docstring quotes is text rather than three escape sequences. Measured before
> and after with one command:
>
> ```
> PYTHONPATH=. python -m pytest tests/test_relaunch_log.py \
>   tests/test_the_extension_gate_is_complete.py \
>   tests/test_the_docs_gate_is_complete.py -p no:randomly -q -rw
> ```
>
> **Before:** two entries in pytest's warnings summary — one against
> `tests/test_relaunch_log.py:85` from importing the module, and one `<unknown>:85`
> attributed to *both* gate tests at once, which is exactly the shape the diagnosis
> below predicted. **After:** no warnings summary at all, 16 passed, exit 0.
> The docstring's own text did not change — an invalid escape was already kept
> verbatim, so nothing but the warning ever differed.
>
> **The sweep found nothing else, and that is a measurement rather than a glance.**
> All **273** tracked `.py` files were compiled and every string literal classified:
> **zero** invalid escapes remain; the only three non-raw literals holding a
> valid-but-silent escape are deliberate byte constants (a UTF-8 BOM, a length
> prefix, the PNG magic); and all **171** regex patterns in the repository are
> already raw — so none of them holds a `\b` that would mean *backspace* where a
> word boundary was meant, which is this defect's silent twin and would never warn.
> `tests/test_gpp.py:496` reads like a fourth finding and is not: it is a `"""\`
> line continuation, and it looked like backslash-CR only because the checkout is
> CRLF — trap 2 of [../CLAUDE.md](../CLAUDE.md) biting the scan that was hunting
> trap-shaped bugs.
>
> **Guarded, so a revert is loud.** The `r"""` is pinned in `PINNED` in
> `tests/test_the_documents_cite_what_they_claim.py`, so deleting the `r` now fails
> tier 2 of the citation guard instead of printing a warning nobody reads.

**The diagnosis, kept as it was written on 2026-08-21 — the present tense below
is that morning's, not today's.**

Every full suite prints `<unknown>:85: SyntaxWarning: invalid escape sequence '\.'`,
raised by both gate tests because they compile the suite's own sources to count it.
Traced 2026-08-21 to a **non-raw** docstring at `tests/test_relaunch_log.py:84`, which
quotes a Windows path verbatim:

    ...\.scrapex\engine.log

`\.` and `\e` are not escape sequences. Python 3.12 warns; **a future Python makes
this a `SyntaxError`**, and then the file stops importing. The fix is one character —
`r"""` — and it is filed rather than folded into an unrelated pull request because a
warning that has been printing for a while is not an emergency, and because a
docstring quoting a path is exactly the case that will recur.

## 3. Decided, not yet built

### DEC-1 · Topology A — the TypeScript extension as the public product
**Approved 2026-07-18. Zero commits since.** This is the largest gap between what was
decided and what exists.

The owner chose Topology **A** over the study's recommendation of B — *"A, but leave the
current engine running until the new engine is finished"* — with the Python engine kept as
the golden reference oracle (`docs/MASTER-PLAN.md:9-44`). The plan records Spike 1
(fingerprint parity) as **PASSED** and names `spikes/fingerprint-parity/` as the artefact.

What I can verify: `git log --all -- spikes` returns nothing — that directory has never
existed in this repository. The surviving descendant is `contract/parity/`, which every
commit reports as "contract parity 3/3". Spike 2 (wa-sqlite + OPFS running `db/schema.sql`
verbatim inside an MV3 worker) has never been attempted, and Phases 1–3 of the A roadmap
(port connectors + normalize + rowspec + ingest to TS) have not started. Every one of the
last 130 commits is Python, and the extension has remained a thin panel over the Python
engine's JSON API.

That may well be the right outcome — the Python product got very good in the meantime — but
nobody ever said so out loud, and `docs/MASTER-PLAN.md` still reads as the live plan. Its
own §8 asks the owner to "Confirm Topology B", a question its own header already answers
with A. It is the most-wrong document in `docs/`.
**Next action:** **Q-6**. Whatever he answers, correct MASTER-PLAN.md in the same session.

### DEC-2 · shopify cannot resume per page as it stands
`fd2b6d9` states it plainly: the English-title pass runs *after* paging and back-fills
`product_name` into rows already built (`scrapex/connectors/shopify.py:57-63`), so a page
yielded during the loop would go out without its English name. Fixing it means fetching
English first or accepting two passes over the catalogue — a redesign, deliberately not
smuggled into a mechanical change.

### DEC-3 · custom_json's interruption rescue cannot survive an interruption
`fd2b6d9`: it accumulates pages into one list, and its `CrawlBlocked` rescue table carries
no page token — so `clear_untokenized` deletes the rescue on resume. The rescue is destroyed
by exactly the event it exists for.

### DEC-4 · The rest of the vocabulary sweep
`docs/column-vocabulary.md` §Status. The language half landed (0038–0042). Still to move:
the `price_*` family, `tax`, `curation`, and `open`/`product_url` → `product_link`. The last
one is blocked on **Q-7** (a `dataset_field` UNIQUE collision — one of the two names has to
lose).

### DEC-5 · Sources that are proven and unfinished
- **ELBUROJ** needs a second pass for English names, on a 10s-delay crawl
  (`plan-closing-the-gaps` §5.2). Measured in `2253308`: 3,874 products at `Crawl-delay: 10`
  ≈ **eleven hours**.
- **SIKA datasheets** want their own connector (§5.3). The site is Sika Egypt's *corporate*
  AEM instance (`egy.sika.com`), not the shop: ~310 products and ~1,050 TDS PDFs behind
  stable DMS GUIDs, with sitemap `lastmod` driving an incremental re-scrape. It publishes
  **no prices** — it would feed `material_attribute_value` only, never `price_observation`.
  `datasheet-enrichment` is in `vocab.ConnectorFamily` with **no builder** in
  `connectors/factory.py`, so the connector is the whole of the work and a manifest entry
  cannot come first: `test_no_manifest_entry_declares_a_family_nothing_can_build` refuses a
  family nothing can build. That is why `SIKA_EGYPT_DATASHEETS` was removed in `256cd27`,
  which also records the two things that make this bigger than it looks — SIKAEGSHOP already
  stores 154 datasheet PDFs as `Attachment` rows, so the only new gain is reading *inside*
  the PDFs, and `pyproject.toml` declares no PDF library at all.
- **TABLER** has never been probed (§5.4). Now tracked with the rest of the unprobed
  queue in `docs/CANDIDATE-SOURCES.md`, whose row also records that its URL was never
  written down anywhere.

### DEC-6 · Authenticated capture for prices an anonymous crawl can never reach
Decided in principle, unbuilt: ALSWEED's variant prices (`offers.price=0` in JSON-LD),
sikaegshop's trade tier for `customerTypeId 2`, MADAR's business-segment prices and
per-branch availability. All three need an extension session capture, not a connector
change. `sources.yaml:131`, `:112`, memory `sika-trade-tier-price.md`.

### DEC-7 · Branch cleanup, which the owner asked to be reminded of
**RE-MEASURED 2026-08-20, with the right test this time: 172 local, 125 remote.**

Run over all 172 local refs with `git merge-tree --write-tree origin/main <branch>`
compared against `git rev-parse origin/main^{tree}` — the test this entry itself
prescribes, on `main` at `72f93a8` (#218):

| | |
|---|---|
| fully contained in `main` — merging changes **nothing** | **60** |
| merging would **conflict** | **110** |
| merges cleanly and **adds** something | **2** |

The shape has held across three measurements over eleven days: 47/68/1, then this.
Local grew 148 → 172 while remote SHRANK 128 → 125, so someone is deleting remote
branches and nothing is deleting local ones.

**And both members of the `adds` bucket are instructive rather than a backlog.**

- `docs/branch-protection-is-its-own-session` — in flight; this entry's own commit.
- `feat/the-warehouse-travels-through-drive` — **THE TRAP, and it must not be
  merged.** It reads as "adds something" because its content is genuinely absent
  from `main`. But its commit *did* land, as `8ebb1f5` (#123), and
  `scrapex/drive.py` was then **deliberately deleted** by `59d5910` (#164), "Drive
  moves into the panel, and the engine stops holding a token it never needed".
  Verified: `git cat-file -e origin/main:scrapex/drive.py` fails. Merging it
  resurrects a module the owner had removed on purpose.

  **So `adds` is not a synonym for `wanted`.** The bucket test answers *would
  merging change main*, never *should it*. Any branch whose files `main` later
  deleted lands in `adds` for ever, and this is the second time this entry has
  had to warn about a bucket being read as an instruction.

**A branch rots between measurements, which is the case for acting rather than
re-measuring.** `claude/jolly-borg-a826ba` — the one branch the 2026-08-20 morning
inventory found holding live work that merged **cleanly** — is now in the
**conflict** bucket. #217 and #218 moved `extension/app.css`, `extension/console.css`
and the three parallel `tokens.css` / `appearance.js` copies, which is exactly the
surface it touches. It was mergeable in the morning and is not by the afternoon,
and nothing about the branch changed.

**Previous measurement, 2026-08-12: 148 local branches, 128 remote.** It has GROWN by 31
local and 22 remote in three days — every session that opens a branch adds one,
and nothing removes any. The 2026-08-09 figures (117 / 106) are kept below with
the analysis that was done against them, because the *method* is the valuable
part and it does not need re-running to stay true.

Three `.codex` worktrees now, not two: `git worktree remove` still comes first.

**Previous measurement, 2026-08-09: 117 local, 106 remote, 21 worktrees.**

And the measurement below was made the wrong way, which matters more than the count.
`git branch --merged` reports 11, and it is **meaningless here**: this repository
squash-merges, so a squash-merged branch reads as unmerged for ever. `git diff
origin/main...branch` is no better — for a diff, three dots means *merge-base to
branch*, which answers "what did this branch add when it forked", not "is it in main
now". It reported 105 branches holding work. That number is wrong.

**The test that actually settles it is `git merge-tree --write-tree origin/main
<branch>`: if the tree it writes equals main's tree, merging that branch changes
nothing.** Run over all 117:

| | |
|---|---|
| fully contained in main — merging changes **nothing** | **47** |
| merging would **conflict** | 68 |
| merges cleanly and **adds** something | **1** *(and it is the branch open in PR #141)* |

Of the 68 conflicting, **31 carry a subject line that is already on `main`**, so they
are squash-merged and their conflict is just main having moved on. The remaining 37
are the only ones that need a human to look, and several of those are review scaffolding
(`review-6x`, `refute-6x`, `t64`, `t65`, `merge43`, `ranktest`) rather than work.

The 2026-07-28 note listed three stale branches. It read: `codex/selected-card-layout`,
`codex/source-card-display-review` and `codex/unified-record-inspector-scroll` each carry the
same four unmerged commits (`dd786b9`, `9e4c1c4`, `d25b166`, `465bfd2`) whose *titles* are
already on `main` under different hashes — so they are almost certainly superseded rather
than missing **(inferred from the titles; the check is a diff, not a title match)**.
`codex/workspace-overview-ui` still holds the one genuine orphan `c88961a`, already ruled
**superseded, do not merge**. Two branches live in `~/.codex/worktrees/`, so
`git worktree remove` comes before any deletion.

### DEC-12 · The append gate's key is not the number, and three of his briefs prove it separately

**FOUND 2026-08-20**, not from the code but from reading three price briefs he sent
within an hour of each other. Each describes a different product, each was written
independently, and **each breaks `SR-6` in a different place.** One case would be a
quirk; three from three directions is a defect in the key.

`SR-6` is right about what it was written for: a scraped shelf price where an
unchanged number carries no new information, so the observation is **confirmed rather
than appended**. That is what `_still_the_same_price` implements, and it is why the
warehouse is not full of identical rows.

**It is wrong about what "the same" means for an official published price.**

| the brief | what carries the new fact | what `SR-6` sees |
|---|---|---|
| [DIESEL-PRICES.md](DIESEL-PRICES.md) §3 — *"never overwrite a previous price when a new month or quarter begins"* | **the period.** Oman published `0.258 OMR/litre` for August. If July was also `0.258`, the ministry setting it again for a named month **is** the fact | no change → writes nothing → **the August period never exists** |
| [BITUMEN-PRICES.md](BITUMEN-PRICES.md) | **the commercial basis.** Two observations can be ex-refinery and delivered, taxed and untaxed, 25-tonne truck and sea — different facts at equal values | no change → collapses them → destroys the only thing that made either usable |
| [CONCRETE-MATERIALS.md](CONCRETE-MATERIALS.md) §3 | **the source type.** Its table has a column headed *"Can it populate `price_amount`?"* and the answer is **No** for `official_price_index`, `official_approved_source` and `official_specification`. An index point and an absolute price are not comparable quantities | no change → treats an index value and a price as the same observation |

> **So the key is not `(product, price)`. It is at least
> `(product identity, period, commercial basis, source type)`** — and the concrete
> brief goes further than a key: an index must not enter the price column **at all**,
> which is a schema boundary rather than a gate condition. It gives
> `price_index_observations` and `water_tariffs` their own tables for exactly that
> reason.

#### Why this is recorded now, before any of it is collected

Because the failure is **silent and unrecoverable**. A dropped month is not a wrong
row that a later fix corrects — it is a row that never existed, in a table whose whole
purpose is history. By the time anyone notices August is missing, August is not
re-fetchable: these are dated bulletins and expiring quotations, and the Qatar bitumen
figure had **already expired** when he sent it.

**And this shape has already happened here once.** A new `price_observation` column
stayed NULL because the append gate never learned to notice it — the gate decides what
history exists, and it only ever knew about the price. That is the same defect at a
smaller scale, and it is the reason to believe this one.

#### Water is the sharpest single example, and it is his

The concrete brief §2.2 refuses to store one water price at all. The official network
tariff is **one component** of the site cost, beside meter charges, wastewater
charges, tanker filling, transport, storage and testing — and *"a potable-water tariff
alone does not prove technical suitability"* for concrete mixing. **One number here
would be false in both directions**: too low as a delivered cost, and not evidence of
fitness for purpose. So the tariff and the delivered quotation are two tables, which
is the same argument as the three rows above with the volume turned up.

#### What this does NOT say

It does not say `SR-6` should be removed. `SR-6` earned itself on the price sources
this project already runs, and removing it would fill the warehouse with identical
rows. **It says the gate needs to be told what "new" means per product class**, and
that the three product classes he has now queued each answer differently.

**Not built, and deliberately not designed here.** The evidence is recorded while it
is fresh; the mechanism is a decision for when the first of these collections is
actually scheduled, and it will need his ruling because it changes what `SR-6` means.

---

### DEC-11 · How to crawl muqawil without missing anyone, and what it costs

**STUDIED 2026-08-20 on his instruction** — «ازاى نزحف صح بدون ان نغفل شى» and «اريد
منك فحص كل الحلول والحالات» — because the warehouse had told him a real company did
not exist. Fifteen agents over five angles, each proposed method then attacked to find
the contractor it misses.

#### First, four numbers in this repository are wrong, including one of mine

| stated | measured 2026-08-20 |
|---|---|
| 865 listing pages | **871** |
| ~17,300 / "at least 17,283" contractors | **17,402** = `(L−1)×20 + c`, where the last page now carries **2** cards, not 15 |
| a 2026-08-17 pass ran at 5.4 requests/second *(mine, in conversation)* | **FALSE.** `captured_at` is the INSERT time, not the fetch time. The "160 seconds" was a database copy. The real rate is **5.84 s PER REQUEST** — 34× slower |
| 121,157 detail requests | superseded, and still written down |

**So speed IS a problem, contrary to what I told him.** The correction matters because
every cost below is priced at 5.84 s and would be nonsense at 5.4/s.

#### The mechanism, and it is the whole answer

The listing order is **not** randomised per request. It is a randomised ordering held
in a cache whose generation lasts **more than 66 s and at most 268 s**. Measured.

- **Inside one generation, pagination is an exact partition** — pages disjoint,
  together covering every published row once.
- **Across generations it is independent resampling**, which is why 864 pages read
  over hours yielded 11,059 of 17,275 slots and why six passes never converged.

> **Therefore any page set read entirely inside one generation is provably complete
> for that set.** That sentence is the difference between hoping and knowing.

#### The method: partition, then witness the partition

| step | what it does | cost |
|---|---|---|
| **0 · ceiling** | page 1 → `L` and cards-per-page `S`; page `L` → `c`; `N = (L−1)·S + c`. **`S` is READ, never assumed** — he warned it may change, and it did change on the last page | **2 requests, ~12 s** — replaces an 8h54m six-pass sweep |
| **1 · partition** | slices small enough to read inside one generation. **`region_id` × `company_size`, 56 cells, exhaustive and verified to the unit** — see the measurement below. Slice sizes are read from each cell's own paginator, never assumed | 1 request a cell |
| **2 · witness** | after reading a slice, **re-fetch its page 1 and compare THE ID SEQUENCE** — never the bytes; see the correction below. Same sequence ⇒ the generation never rolled ⇒ the pages were one true partition ⇒ if `distinct == N_s` the slice is **provably complete**. Different ⇒ the ids still count, and the slice retries | `L_s + 1` |
| **3 · exhaustiveness audit** | `Σ N_s == N_total`? If short, **the deficit is exactly the count of contractors whose facet value is null** — the "contractor in no partition" case, detected and counted instead of silently dropped | 2 per slice |
| **4 · global deficit** | `D = N − |distinct|`. `D > 0` **proves** incompleteness and names its size; `D == 0` proves every published row position was read. Re-read `L` at the end: if it moved, say "complete as of the start, with N arrivals deferred" | free |

**Cost: ~1,670 requests ≈ 2.7 h serial, ~58 min at concurrency 4** — against **18.4 h**
for a blind 13-pass sweep that can still only ever say *"expected unseen 0.04"*. Seven
times cheaper **and provable instead of probabilistic**.

**Concurrency buys wall-clock, not coverage.** Closing an 871-page pass inside a 66 s
generation would need ~34 in flight, and `pacegovernor.py` already measured the price
of four (latency 6.6 s → 9.2 s, *"a server saying it is hurting"*). Coverage comes from
slice size, not from parallelism.

#### What this method still cannot see, and it is the most important paragraph here

It proves it read every row the paginated listing **publishes**. It cannot prove the
listing publishes every contractor the site knows:

> **The site's own header counts 123,842 "Saudi Contractor" against 17,402 published
> rows — a factor of 7.1.**

So the only honest warehouse claim is *"every contractor findable in the muqawil.org
contractor listing as of «timestamp»"*, never *"every Saudi contractor"*. And
membership **10001274** is therefore **explained but not closed**: `q` reaches it
(tested — it returned exactly id 1301), and whether it appears in the unfiltered
listing is unknown until one crawl closes with `D == 0`.

#### The blind fallback, priced honestly

Expected unseen after `k` passes = `N·e^(−k)`, and the model is validated: it predicted
42.9 unseen after 6 passes; the sweep observed 38. `k=10` for expected unseen below 1,
`k=13` for 95% confidence of missing nobody, `k=15` for 99%. Reserve it for the
residual, never as the primary method — it cannot say "complete".

#### And one cost correction that changes the plan

`sites/muqawil.py:118` computes `listing_requests = last_page × len(locales)`. Correct
about requests, **but it must not be read as coverage**: Arabic page N returns the SAME
20 ids as English page N — 20 of 20 identical on 845 of 864 stored pages. The Arabic
half buys **129 new ids for 865 requests**. Count passes in ONE locale for completeness
planning and treat Arabic as a data-pairing cost, not a coverage cost.

#### The partition, measured 2026-08-20 — and it is exhaustive to the unit

**MEASURED, 152 requests** — 43 sizing the regions, 61 the region×size cells, 13 the
cities endpoint, 10 probing whether a null facet is addressable, 10 sizing
`region_id=0`, 14 witnessing, 1 diagnosing.

The three unknowns this study left open were the ones the method stood on. Two are now
closed and the third is closed as a defect.

**The page count never needed a sweep.** The paginator publishes its own last page:

```html
<li class="page-item"><a href="…?region_id=1&amp;page=322">»</a></li>
```

So **one request sizes any slice**, filtered or not. `read_last_page` already did this
and nobody had noticed it answers the filtered case too.

**Every filter the listing offers, because a `<select>`-only search had missed most of
them.** This study previously recorded that `company_size`, `rating_stars` and
`user_type` "have no `<select>` in the listing at all". True, and misleading: **they are
radio inputs**, and their values were in the page the whole time.

| parameter | values | exhaustive? |
|---|---|---|
| `region_id` | `1`…`13`, **and `0`** | **yes, with `0`** — see below |
| `city_id` | 3,953 ids, AJAX only | no — same null class as region |
| `company_size` | `big` `medium` `small` `verysmall` | **yes** |
| `user_type` | `SC` `NSC` | **yes** (783 + 88 = 871 pages, the whole listing) |
| `rating_stars` | `1`…`5` | no — **17 contractors in total** carry any rating |
| `lc_program_list_id` | 13 programme ids | no |
| `interest_id` | `jstree`, hierarchical | no, and multi-valued |
| `q` | free text | **matches the membership number exactly** |
| `my_contractors` | `1` `2` | no — a logged-in user's own list |

**`city_id` comes from an endpoint, and it was in the stored HTML all along**, in the
listing's own jQuery rather than in any `<option>` — which is exactly why a search of
the `<select>` found an empty one:

```js
var citiesUrl = "https://muqawil.org/en/contractors/cities";
```

`GET /{lang}/contractors/cities?region_id=<n>` → `[{"id":…,"name":…}, …]`. Thirteen
requests give **3,953 cities**. `city_id` also works **without** `region_id`
(`?city_id=3` alone → 296 pages, which is RIYADH — the warehouse projects 5,896 for
that city and the paginator says 5,920).

**`region_id=0` is the whole answer to the exhaustiveness question.** `Σ N_r` over
regions 1–13 came to **15,966** against a whole of **17,403** — 1,437 short, the
contractors whose card publishes no location at all. `region_id=0` (and
`region_id=null`) returns **exactly those 1,437**, every card blank:

| | |
|---|---|
| Σ regions 1…13 | **15,966** |
| `region_id=0` | **1,437** — and its own four `company_size` cells sum to 1,437 |
| whole listing | **17,403** = 15,966 + 1,437, exact |

Corroborated independently: 960 of the 11,059 stored records (**8.7%**) have a null
`card_city_region`, and 1,437 of 17,403 is **8.3%**. Two measurements, different
instruments, same class of contractor. **This is the "contractor in no partition" case
the study warned about, and it turns out to have a URL.**

`company_size` is a second exhaustive axis: its four values sum to **17,405** against
17,403 — a drift of two arrivals in the minutes between the two measurements — and
`card_company_size` is filled for **all 11,059** stored records with no empties, ratios
matching the live page counts to a tenth of a percent (76.6 / 14.4 / 6.1 / 3.1).

**So the partition is `region_id` × `company_size` — 56 cells, exhaustive, exact.**

| | |
|---|---|
| cells | **56** |
| Σ pages over cells | **897** against 871 unfiltered — **3% overhead**, the per-cell rounding |
| cells over 31 pages | **6**: Riyadh×verysmall 235, Makkah×verysmall 156, Eastern×verysmall 93, no-region×verysmall 59, Riyadh×small 51, Madinah×verysmall 32 |
| those 6, split again by `city_id` | **405 of 410** city×size cells fall under 31 pages. The five that do not: RIYADH×verysmall ~212, JEDDAH×verysmall ~92, RIYADH×small ~48, MAKKAH×verysmall ~39, DAMMAM×verysmall ~32 |

**Re-priced: ~1,065 requests, ~1.7 h serial** (56 to size + 897 to read + 56 to
witness + 56 tail counts) against this study's earlier estimate of 1,670 and 2.7 h, and
against **18.4 h** for the blind sweep. And it is now provable rather than hoped-for,
because the partition is exhaustive rather than assumed to be.

#### Two corrections the measurement forced, and one would have broken everything

**1 · The witness must compare the ID SEQUENCE, not the bytes.** Step 2 said
"byte-identical". Measured: a re-fetched page 1 whose id order was **identical** was
**not** byte-identical — the body carries per-response noise. A byte comparison would
have failed every witness, so the method would have certified **nothing**, ever, while
looking like it was working.

**2 · A filtered listing hid its page count behind an entity, and that is a defect in
this repository rather than a quirk of the site.** `read_last_page` matched
`[?&]page=(\d+)`. Unfiltered, the paginator writes `?page=2` and it matched. Filtered,
it writes `&amp;page=322`, where the character before `page=` is a **semicolon** — so
nothing matched, the function raised, and a caller that guarded the raise read Riyadh's
**322 pages as one page of twenty**. It is fixed, read only from inside an `href`
(unescaping alone would let prose containing `page=` count as pagination), and both
halves are mutation-proven.

#### Proven once, end to end

`region_id=13` × `company_size=verysmall`, 7 pages: **128 ids read, 128 distinct**, and
the witness page 1 came back in the same order. `D = 0`. **That slice is complete, and
the claim is a proof rather than a hope** — the first time anything in this project has
been able to say that about muqawil.

And the generation lasts longer than the study assumed. Page 1 of a filtered slice held
its exact order at **55 s, 90 s and 157 s**, and had rolled by **282 s** (10 of 20 ids
in common). So the working floor is **157 s**, not 66 s — which is what makes 31-page
cells comfortable and the six heavy cells worth attempting at all.

#### Unknowns that remain

1. **Is 10001274 in the unfiltered listing?** Still unknown until a crawl closes with
   `D = 0`. But it is now **reachable on demand**: `?q=10001274` returns exactly one
   card. That is the reconciliation primitive `dataset_sighting` needed — one request
   per missing id, not a re-crawl.
2. **The five city×size cells over 31 pages**, worst RIYADH×verysmall at ~212. No
   fourth exhaustive axis is fine enough — `user_type` only halves it to ~190. The
   witness makes attempting them **safe rather than risky**, since a failed witness
   still contributes its ids and retries, so this is a cost question and not a
   correctness one.
3. **Whether `q` can cover the residue.** `q=zzz` → 0 results and `q=a` → 856 pages, so
   it is a substring match and a cover built from it would overlap. Unmeasured whether
   every published name contains an ASCII letter.

#### Dead ends, so nobody spends the requests twice

Recorded because a negative result stated firmly is worth as much as a positive one,
and each of these looked promising enough to chase:

- **The sitemap does not enumerate contractors.** `/sitemap.xml` → `/ar/sitemap.xml` →
  a sitemapindex of `sitemap-ar.xml` and `sitemap-en.xml`, and the English one holds
  **20 static pages**. Settled; do not re-check.
- **`/en/contractors/map` carries no contractor markers.** The page is 406 KB and
  holds 263 distinct latitude-shaped numbers, which is what made it look like a feed.
  It is not: the one coordinate in the map's own script is the map CENTRE — Riyadh,
  `{lat: 24.70372261387751, lng: 46.683}` — sitting under a comment copied straight
  from a Google Maps tutorial, `// The location of Uluru`. **Zero contractor profile
  links on the page.** Its only endpoints are `/api/js` (Google Maps) and
  `/api/rating-api` (the rating widget). So the map gives neither an enumeration nor
  the coordinates the owner asked for — `latitude`/`longitude` remain a profile-page
  field, exactly as `CONTRACTOR-SOURCE.md` already marks them (`js`, inline script
  only).
- **No stable sort exists.** `sort`, `order`, `order_by`, `orderby`, `sort_by`,
  `direction` and `sort_field` were each tried against the live listing and **not one
  changed the order** — measured before this study, and recorded in
  `scrapex/sweep.py`'s header. There is nothing to build.
- **Id-space enumeration is not viable.** Contractor ids span 720 … 20,217,024 in two
  series the site publishes, far too sparse to probe.

---

### DEC-9 · Snapshots are stored uncompressed, and the full crawl is 6.4 GB of it

> **SUPERSEDED 2026-08-20 by [STORAGE.md](STORAGE.md), and kept in full per C4.**
> It asked *how to store 6.4 GB more cheaply* and answered that well. The owner
> asked *why we are storing 6.4 GB at all*, and five of the numbers below do not
> survive being measured properly: a listing page is **17.8%** cards, not 21%; a
> profile is **119 KB** across 13 samples, not 168 KB from one; the corpus is
> **4.55 GB**, not 6.4; a profile compresses **7.7×** with zlib, not 9.4×; and the
> compressed projection is **~90 MB**, not 660.
>
> The one that mattered is not a number but a cause: its 15.6× is **entirely
> intra-page**. zlib's 32 KB window never sees across a 121 KB page, so the
> cross-page redundancy this entry credits for the ratio was left on the table.
> `zstd` with one real page as a raw dictionary gets **187×** on listings and
> **46×** on profiles — **254×** re-measured through the `zstandard` wheel,
> which is what shipped — and keeps every row independently decompressible. Its *rule* — keep the snapshots — is upheld and
> strengthened. Its *encoding* is not.

**MEASURED 2026-08-20, on the live database.** The contractors cost 342 MB, of which
**320 MB is HTML and 22 MB is data** — 94% of the price is the pages, not the rows.

| | |
|---|---|
| the file on disk | 483 MB *(now 835 MB, with the Arabic half merged)* |
| 864 snapshots | 320 MB, averaging **362 KB a page** |
| 11,059 records | 8.7 MB |
| 17,275 revisions | 13.6 MB |

**Only 21% of a listing page is its contractor cards.** The other 291 KB is nav,
footer, scripts and the city dropdown — a near-identical skeleton repeated 864
times, which is exactly why it compresses so well:

| | | |
|---|---|---|
| 25 pages raw | 9.3 MB | |
| gzip level 6 | 0.6 MB | **15.1x** |
| zlib level 9 | 0.6 MB | **15.6x** |
| lzma | 0.5 MB | 19.1x |

**320 MB would be 21 MB.** And the projection that makes it a decision — one real
profile page was fetched and measured at **168 KB raw, 18 KB compressed (9.4x)**:

| Stage B, 17,402 contractors x 2 languages = 34,804 pages | |
|---|---|
| raw | **~6.4 GB** |
| compressed | **~660 MB** |

**The recommendation is that the rule is right and the encoding is wrong.** "One page
in, one snapshot out" earned itself on 2026-08-20: a defect in the bilingual merge was
repaired from disk with **nothing re-fetched**, where a re-crawl is 2.8 hours — and
[DEC-11](#dec-11--how-to-crawl-muqawil-without-missing-anyone-and-what-it-costs) prices
a *provable* one at 2.7 hours serial or 58 minutes at concurrency 4. So the
snapshots stay. They should be stored compressed — `zlib` is in the standard library
and needs no new dependency.

What was considered and is worse:
- **Trimming to the cards (21%)** saves 4.8x where compression saves 15.6x — three
  times worse, and it spends the ability to re-parse. The defect repaired that day was
  *inside* the card; the next one may not be.
- **Deleting snapshots after approval** spends exactly what saved the day.
- **Keeping a hash and re-fetching on demand** cannot work: the listing reorders every
  thirty seconds, so a page is not reproducible. What is not kept now is not gettable
  later.
- **A shared-dictionary compressor (trained zstd)** would beat 15.6x, since the
  skeleton repeats 864 times — but it adds a dependency for a margin we do not need.

**The cost, and why it is the owner's call:** `html_content` becomes a BLOB rather than
TEXT. That is a migration plus every reader of the column.

### DEC-10 · "Fix the parser and re-run over the snapshots" does not actually work
The seam's stated product is that a wrong parse is re-run against stored snapshots with
nothing re-fetched (`GENERIC-FETCH-SEAM.md`). **It was tried on 2026-08-20 and wrote
nothing at all.**

`approve_candidate` short-circuits on `_approved_ingestion(conn, snapshot_id,
locator)` — same site, same dataset, same `schema_hash` means "already approved", and
it returns `recovered=True` without touching a row. A **corrected parser produces the
same schema and different values**, so all 864 pages came back recovered and the four
empty columns stayed empty. Worse, the caller cannot tell: the return value looks like
success, and the script that drove it reported 864 re-approvals that were 864 no-ops.

The repair only landed because the ARABIC snapshots were merged in the same pass —
a genuinely new `(snapshot, locator)` pair, so a genuinely new approval.

**The gap is that the idempotency key does not include the ROWS.** A candidate hash
alongside `schema_hash` would make a corrected parse a different request — replay of an
identical request still short-circuits, so the tested behaviour is kept — and the
re-ingestion would write revisions, which is what a repair should leave behind. Not
built, because it changes the approval path's atomicity guarantee and that is a ruling.

Until it is built, **re-parsing means approving against a snapshot that has never been
approved**, and that has to be said out loud rather than discovered again.

---

### DEC-8 · The engine's Data page is a PORT, not a rebuild — measured 2026-08-16

**This answers [REQ-07](REQUESTS.md#req-07--the-data-page-must-carry-everything-the-engines-page-carries)**
— his request on the board, which did not cite it in either direction.

**The owner asked directly:** «هل يمكن نقل صفحة data الموجودة فى المحرك بكل مميزتها الى
extension ام يلزم اعادة البناء كامل؟» Answered by measurement, not opinion, and the answer
is a port.

**Why it is a port.** Both pages already run the SAME grid library:

| | |
|---|---|
| `scrapex/webui/static/grid.js` | **3,212 lines**, Tabulator |
| `extension/datatable.js` | **100 lines**, Tabulator |

Tabulator was vendored into the extension in #193, so the difference is not a technology —
it is **~3,100 lines of behaviour written on top of the library we already ship in both
places**. `grid.js:5-9` records why that behaviour is ours rather than bought: the owner
asked for the AG Grid look, and the features in those screenshots — set filter, row
grouping with aggregation, the columns tool panel, Excel export — live in
`ag-grid-enterprise`, whose licence field reads *"Commercial"*. So it was built on the MIT
library instead. **Code we own ports; a licence would not have.**

**And MV3 does not block it.** `eval(`, `new Function` and inline `on*=` handlers in
`grid.js`: **zero**. Those are precisely the three things Manifest V3's CSP forbids, and one
of them would have made a port impossible without a rewrite. There is none.

**Where the real work is, and it is not the grid.** `scrapex/webui/templates/source.html`
carries Jinja on **105 of its lines**, and those lines hold **118 expressions** — 61
`{{ }}` substitutions and 57 `{% %}` control statements, counted 2026-08-20. (The
first version of this entry said "105 Jinja expressions": 105 is the LINE count, and
naming it as expressions understated the work by thirteen.) Half the page is assembled
on the server before it reaches a browser. An extension page is a static file, so
every one of those has to become a request and a render in JS. Mechanical, not inventive. The routes it needs already exist
and already answer: `/api/fields`, `/api/promotable`, `/api/views`, `/api/offer` — and the
extension already calls `/api/table` among them.

**What the gap actually is, with evidence.** The owner sent two screenshots on 2026-08-16.
The engine's page carries Datasets · Views · Grid Features · Columns menus, a filter and a
menu on every column, an ALL/ONE toggle, an **EN/AR toggle**, Excel/CSV/JSON export, a
price rendered with its previous value struck through, row checkboxes, Source overview, and
a last-run line with a Crawl history link. The migrated page carries side-by-side AR and EN
columns, a fold checkbox, Reload, and basic pagination. **The migration carried the word
`bilingual` (`extension/datatable.js:55`) and left the feature** — which is why the owner
stopped at B1: «اشياء كثيرة مفقودة لذلك توقفت عند b1».

**Three pieces of work, in order:**

1. **Port `grid.js`.** The largest piece and close to a copy.
2. **Convert the 118 Jinja expressions** across those 105 lines from server-side
   rendering to fetch-and-draw.
3. **A DOM harness that renders the page in tests** — `tools/tabpage_harness.py` was built
   for exactly this in #194 and extended to serve real ES modules in #200.

**(3) is the one not to trade away.** The Data page has already shipped BROKEN once with
2,460 engine and 398 extension tests green on it (#194: every first load aborted itself,
found only by opening it in a browser). Three thousand ported lines with nothing rendering
them is that failure with more surface.

**And a standing warning:** do not delete the engine's page until the harness proves the
ported one works. *"We migrated it"* has been said once already about a page that was
missing everything in the list above.

## 4. Built, not yet verified

### BV-1 · Crawling several sites at once — IT HAS RUN, and the entry was wrong twice
**Re-measured 2026-08-12 against the live warehouse and the job log.**

Both facts this entry rested on are stale:

- **Not off by default on his machine.** `scrapex_meta` holds
  `setting:crawl_parallel_sources = '3'`. The entry says 1.
- **It has run at width 3, at least twice.** `job_log_entry`, job 120:
  *"2026-08-11T13:12:59Z crawling 12 site(s), up to 3 at a time"*, then MADAR
  13:13:50, ALSWEED 13:13:52, ELBUROJ 13:13:59 all *"fetching — 50 requests so
  far"*, interleaving for minutes. Again at job 112 on 2026-08-05.

**And this entry's own proposed check was wrong and would have misled whoever ran
it.** *"Confirm from `crawl_job` that they overlap"* — `crawl_run` brackets the
**ingest**, not the fetch: run 134 records 3,879 requests between 14:50:00Z and
14:50:02Z. A self-join over all 135 runs finds **zero** overlapping pairs at width
3. Use `job_log_entry` timestamps, not `crawl_run` intervals.

**What is actually unverified is the other half of the sentence — the pause.**
The pause handler clears `crawl_job.control` while other lanes are still in
flight (`scrapex/jobs.py:723-724`, and the twin at `:595`).
**Next action:** stop the pause handler clearing `control` until every lane has
observed it, or have the other lanes read their own copy.

### BV-2 · The WAL / sealed-archive cluster
`234cdc1`, `4103e48`, `4dfb9e8` (plus the integration PR #10). Three of the four faults are
POSIX-only — on Windows an open handle blocks the rename, which is the accident that hid
them. The author is explicit for fault D: *"I could not make D's test fail on this machine,
and did not pretend to. Local SQLite is 3.50.4, where optimize behaves; CI's 3.45 is where
the fault bites."*
**The check that would settle it:** a green CI run on `ubuntu-24.04` for those tests. Look
at the run, don't assume it.

### BV-3 · Settings moved into the extension panel — CONFIRMED, and its warning has come true
**Re-measured 2026-08-12. The "not yet confirmed" half is CLOSED by the live
warehouse**, which shows the whole chain working on the owner's machine in a real
crawl: `extension/app.js:840` posts `crawl_honour_delay` → `scrapex/capture.py:95`
reads it → `scrapex/connectors/base.py:485` emits the sentence → `job_log_entry`
for job 120 carries it. Two settings hold non-default values, so something wrote
them: `crawl_honour_delay = '0'`, `crawl_min_interval_s = '1'`.

**THE WARNING IN THIS ENTRY HAS NOW MATERIALISED, and this is the most
consequential thing in this file.** The log line predicted it:

> *"ELBUROJ: robots.txt asks for a 10s crawl delay — IGNORED at your request;
> this run paces itself at 1.0s and may be rate-limited or blocked by the site"*

And then, five times: `failed: 5 refusals in a row (last: HTTP 429 on
https://alsweed.sa/...)` — 2026-08-11 at 13:30:07Z, 13:39:32Z and after. **A
whole source is failing because the delay is switched off.**

**Next action, and it is the owner's:** `crawl_honour_delay` is still `'0'`. He
chose that (SR-9 says turning it off announces the number it overrides, and it
did). He may not know it has cost him ALSWEED. Show him the 429s.

### BV-4 · Sika's trade tier reaching the warehouse
`436105c` reported 0 of 73,084 observations carrying a trade price. **Re-measured
2026-08-12: 185** observations carry `price_trade` (was recorded as 78). The fix
works and keeps working. ~~`price_trade` reaches `BROWSE_COLUMNS` with no
formatter and no alignment~~ — `059820d` closed that; the clause is struck rather
than deleted so it is not re-raised from the old text.
**The check that would settle it:** open a sikaegshop record in the Data page and look at
the Trade price cell.

### BV-5 · Sources re-activated, then partly switched off
`df34761` activated four connectors that had been built and left off. ~~The
uncommitted manifest edit has since switched five sources off~~ — **re-measured
2026-08-12: that edit is long gone**, the four held, and the manifest and the
warehouse agree exactly (see **OP-2**). Twelve sources, seven active.

What is left is only the last sentence, and it is the owner's: **is seven of
twelve the intended set?** That is **Q-11**. Worth putting in front of him
together with **BV-3** — one of the seven, ALSWEED, is currently being refused
with HTTP 429.

---

## 5. Declared debt — deferred on purpose, with the reason

| ID | Debt | Why it was acceptable |
|---|---|---|
| **DEBT-1** | **Migration `0047`'s coverage guard runs *after* the MADAR upgrade that fills its NULLs**, so it checks a narrower condition than its comment claims. | `0047`'s sha256 is verified on every connection and there is no re-stamp path; replaying it over the real pre-0047 warehouse gives an identical result with or without the fix. Recorded as a **strict xfail** at `tests/test_db.py:194` — this is the "1 xfailed" in every suite line, and it should stay visible. (`c7fa4ea`) |
| **DEBT-2** | **ETag / Last-Modified persistence across runs.** In-memory validators exist in `HttpFetcher`; they are not persisted. | Naive 304-skipping breaks price *confirmations* (`last_confirmed_at`) and the volume canary. It needs a content-cache design, not a flag. Owner approved the deferral 2026-07-22. |
| **DEBT-3** | **`_derive_seen` rebuilds the whole derived timeline of every offer a run touched, unconditionally** (`scrapex/ingest.py:1349-1363` — cited as `:1029-1043` until 2026-08-12). | Gating it on success *was* the incident: one contained error left every offer with an appended observation but no `offer_state` and no `price_period`, and the same-day dedupe then blocked the re-append that would have repaired it. The cost is accepted; ت3's claim that it is ~396,000 operations was never refuted (**OP-6** — and OP-6's row for ت3 pointed at DEBT-4 by mistake; it means this entry). |
| **DEBT-4** | **advancedcastle's Egyptian price is deliberately not crawled.** *(Discharged as intended — re-measured 2026-08-12: the 14 ADVANCEDCASTLE rate rows are there and no converted price is.)* | It is a *conversion*, not a price the merchant set — the EGP/SAR ratio is constant at 11.768 across five probed products. `price_basis` / `original_price` live on `COMMODITY_PRICE`, not `PRODUCT_PRICES`, so recording it honestly is a schema migration and therefore the owner's call. He took it: capture the published **rate**, never the converted price. Note the warehouse *would* keep the two countries apart correctly (`source_offer` is keyed on `country_code_alpha2`) — the reason is the derivation, not a modelling limit. (`e639310`, `b43405c`) |
| **DEBT-5** | **`region` keeps its name in three places on purpose** — the manifest's `default_region` / `extract.regions`, `tax_rule.region`, and `pricekey`'s own field. | They *scope* a row rather than describe it. The column itself did move (`0042`). |
| **DEBT-6** | **`origin` and `spec` are hashed into the price key but no connector supplies them** (`scrapex/ingest.py:898-902` — cited as `:597-599` until 2026-08-12 — its own comment: "Not collected by any connector yet"). | Wired and unreachable. Harmless today; it matters the day a connector starts publishing one, because the field set changing is `fields_changed`, not `price_change`. |
| **DEBT-7** | **Named in the UI as not built:** ~~funnel HMAC signing, adaptive batching,~~ two-way Sheet sync, proxy / anti-bot, connector-drift repair, OTA updater. **Re-measured 2026-08-12: funnel HMAC signing and adaptive batching are BUILT and shipping** — four items remain, not six, and the interface should stop naming two things it has. | Post-release, demand-driven. Saying so in the interface is what keeps it honest. (memory `scrapex-phase5-integrations.md`) |
| **DEBT-8** | **GPP electricity stays on the rank table as converted USD.** | Electricity country pages are a different page type and the site's own JSON-LD there is broken (`EGP 0.000`). It needs its own parser; the rows are honestly marked `price_basis=converted`. Measured: 333 of GPP's 695 offers are still priced in USD. |

---

## 6. Open questions for the owner

Each is phrased as a question with its options. Nothing below can be answered by code.

**Q-6 · Topology: is the TypeScript engine still the plan?**
You chose Topology A on 2026-07-18 and nothing has been built toward it since; the Python
product has instead become the whole thing. Options:
**(a)** Reaffirm A — then Spike 2 (wa-sqlite + OPFS running `db/schema.sql` in MV3) is the
next real piece of work and everything else queues behind it.
**(b)** Defer A explicitly — keep Python as the product, mark MASTER-PLAN as history, and
stop measuring ourselves against a roadmap we are not on.
**(c)** Reverse to B — the study's own recommendation, which is now almost entirely built.
*Recommended: (b) or (c). Either way MASTER-PLAN.md gets corrected in the same session.*

**Q-1 · ANSWERED — Heidelberg Materials Egypt: how should the price matrix be modelled?**
*(Closed 2026-08-12 by re-measurement, and the closure survived a sceptic. Kept
for the reasoning, which is the only place the modelling trade-off is written
down.)*
Their price is a function of product × city(46) × segment(5) × plant(3) × tier(2) and
`PRODUCT_PRICES` has a column for none of the four (`docs/recon/heidelberg-materials-eg.md`
§4.1). Options: **(a)** public price only — one row per product, zero schema change, loses
~95% of what they publish; **(b)** synthetic variants via `variant_axes` — captures
everything with no migration, but calls a pricing context a "variant" and the variant UI
will present them as choices; **(c)** widen the contract with real `city` / `segment` /
`plant` / `qty_tier` columns plus pricekey identity fields — correct, and the largest change.
*Built naively, one product's ~276 prices would read as the same offer changing price
repeatedly inside a single crawl.*

**Q-2 · STILL OPEN — Heidelberg: `maxPrice` (1,950) is never displayed; the site
shows `salePrice30*` (3,950.02).** Record only the displayed one, or both with the
unshown one flagged? *(A 2026-08-12 pass called this closed; the sceptic refuted
it — what exists is declared, not driven, and only part of what the question asks
was settled.)*

**Q-3 · ANSWERED — Heidelberg: which customer segments?** `Y6` is what the public
sees; `YM`/`YT` publish 5 prices each; `YO`/`YR` publish none. *(Closed 2026-08-12
by re-measurement.)*

**Q-4 · STILL OPEN — Heidelberg: VAT.** Record `evidence: stated, rate_pct: 14`
scoped to the order total, or `unknown` for the listing price? ~~*My reading: the
site makes no VAT claim about the per-tonne price, so `unknown` is the honest
answer.*~~ **Struck 2026-08-12:** a `tax:` block is real and on `main`, so that
suggested answer is now wrong and must not be re-proposed from the old text. The
closure was refuted by mutation — the test that would prove the behaviour does
not drive it.

**Q-5 · STILL OPEN — Heidelberg: is a 9-product source worth a bespoke connector
at all?** Two requests for ~211 real Egyptian cement price points — cheap to run,
but it is a new connector class and possibly a contract change.
**Re-measured 2026-08-12:** the connector is **built**, and `sources.yaml` has
`HEIDELBERG_EG` **`active: false`** — so it exists and has never crawled. The
question is now smaller and more concrete: switch it on, or delete it.

**Q-11 · Which sources should actually be running?** ~~Right now the manifest on
disk, the manifest on `main`, and the warehouse give three different answers~~ —
**re-measured 2026-08-12: they now give ONE answer**, twelve sources with seven
active (see **OP-2**). The disagreement is gone; the decision is not.

The question is purely yours now: **is seven of twelve the set you want?** The
five that are off are MADAR, ELBUROJ, SIKAEGSHOP, HEIDELBERG_EG, SPARK_ESHOP.
Worth answering beside **BV-3**: one of the seven that IS on, ALSWEED, is being
refused with HTTP 429 because the crawl delay is switched off.

**Q-9 · Exchange-rate cadence.** ~~~93 fetches per refresh, ~372 requests a day~~
— **re-measured 2026-08-12: 119 currencies, ~476 Google Finance requests a day**
at the 6-hour default. Raised in `c63ec21` rather than quietly changed, because
Google Finance being the rate authority is your ruling.
Options: keep it, or reduce the cadence. ~~Or fetch only the currencies the
*active* sources actually price in~~ — **struck**: it saves nothing while
GPP_ENERGY is active, which it is.

**Q-10 · GPP's country/material pairs with no local price.** ~92 pairs publish a USD figure
and no local price, and your rule is that the local price is the record — so today they are
stored as nothing. On screen, should they be blank, hidden entirely, or shown as "the site
publishes no local price"?

**Q-8 · `/api/native-host/register`.** It has no authentication and replaces the allowlist
rather than joining it. Options: add authentication; make it merge instead of replace; both;
or accept it because it is already unreachable from any web page. *(It cannot simply be
locked down — it is the route that repairs a broken extension link, so it must stay
reachable from an extension whose id the old manifest does not know.)*

**Q-7 · `open` vs `product_url` → `product_link`.** Both target the same name and
`dataset_field` has a UNIQUE constraint. One of the two has to lose; which?

**Q-12 · Branch cleanup.** Delete the stale `codex/*` heads and `saved/unified-ui-design-system`?
`git worktree remove` has to come first for the two under `~/.codex/worktrees/`.

---

## 6a. In flight right now — 2026-08-11

*The only section that goes stale by the hour. Check it against `gh pr list`
before trusting it.*

| what | where | state |
|---|---|---|
| ~~Side panel startup~~ | **MERGED `815ecae` (#152)** | Owner-verified in real Chrome after the rebase. Nine semantic conflicts resolved by a separate session, which also surfaced four gate failures none of us had run and one silent-pass bug in a test guard. |
| ~~Carry the split databases over~~ | **MERGED `61ded7e` (#159)** | Ran on the owner's real data before merge — pointer moved, `database-status` Healthy, 338,000 rows with zero short. Full suite green locally and in CI on the rebased head. |
| ~~The 48px touch target~~ | **MERGED `6ccdd3c` (#162)** | Not a flake under load, as I had guessed: `showView` animates every view in over 180ms and the test measured ~17ms in, reading a box through a live transform as a float32 quad. 47.99999237060547 is 48 − 2⁻¹⁷. **And the mutation test found worse** — a global `.button { min-height: var(--control-height) }` meant `height >= 48` could never have caught a height regression at all. The guard was blind on the axis it named. |
| Four panel-placement defects | issue #160 | Not started. The version banner should now be gone — the extension is 0.2.2. |
| The untested remote-control promise | issue #161 | Not started |

**Owner-side, no code involved:** the privacy policy is published and its whole
chain verified; the Chrome Web Store listing still needs uploading without the
`key` field. The engine stays **unsigned** by decision on 2026-08-11 — sole user,
so a certificate buys trust from strangers there are none of. Do not re-propose
it; the only consequence is Defender scanning each new download once, which the
splash now covers.

### OP-18 · A test guard was blind to the thing it was written to find

Found on 2026-08-11 by the session that rebased #152, while hardening a line I
had asked it to look at for a different reason.

`side-panel-startup.test.mjs` stripped script comments with
`.replace(/\/\/[^
]*/g, "")` before asserting the diagnostic page makes no
request. The `//` in a URL reads as a comment marker, so everything after it on
that line is deleted — **including a real `fetch(` on the same line**. Proved
with a probe: `fetch("https://example.invalid/probe")` passed the guard silently
on the old strip and fails loudly on the new one.

~~The strip is now line-by-line: a whole-line comment is dropped, a line
containing any quote is kept verbatim, otherwise a trailing `//` goes.~~

**THAT NEVER LANDED. Re-measured 2026-08-12, and this is the worst error in this
file** — a notebook recording a fix that does not exist is worse than one
recording nothing, because it closes the question.

`extension/tests/side-panel-startup.test.mjs:562-563` on `4fcc14f`:

```js
  const script = read("tests/diagnostic-panel.js")
    .replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/\bfetch\s*\(/.test(script), "the diagnostic page makes a request");
```

That first `replace` is verbatim the blind expression the paragraph above claims
was replaced. Re-run of the entry's own probe — the real
`extension/tests/diagnostic-panel.js` with
`const u = "https://example.invalid/probe"; fetch(u);` appended:

```
guard sees a fetch(  -> false
probe line after strip -> "  const u = \"https:"
```

The `//` inside `https://` eats the rest of the line, `fetch(` never reaches the
assertion, and the suite is green for a page that plainly fetches.

**Next action:** apply the hardening this entry already describes. It is one hunk
in one file, and the description of what it should do is above — the work was
done once and lost, not designed and abandoned.

**And a suggestion of mine was refuted in the same reply, correctly.** I proposed
a fixpoint loop by analogy with the `<!--` strip beside it. Removing an inner
`<!-- -->` joins its two sides into a fresh comment, so that one needs the loop;
the line-comment regex ends at `
`, so two `/` can never be brought together.
Fuzzed 20,000 strings: zero changed on a second pass. Copying the loop would have
been ritual.

**Still open, deliberately:** the `/* */` strip on the following line has the same
class of hazard — a `/*` inside a string literal deletes forward to the next
`*/`. Latent today. Before hardening it, check whether the file contains a block
comment at all: if not, the line is dead code and deleting it is safer than
making it clever.



*Added 2026-08-11 after it appeared NINE times in a single day. Not a task — a
lens to hold while reading everything above.*

**A gate that checks something is DECLARED, not that it WORKS.**

Every instance looked like coverage and was not:

- ~2,200 tests, and **not one starts the built binary**. The engine could ship
  68 MB with `pytest` inside it and pass everything, because the binary *works* —
  it is merely enormous and slow, which no assertion about behaviour notices.
- `source_site.active` was read through `WHERE active = 1`, a filter matching
  every row because nothing ever wrote 0. It looked like maintenance for months.
- A touch target asserted at `>= 48` was **loosened to 47.5 so it would pass**.
  Measured afterwards: the button renders at exactly 48. The relaxation bought
  nothing and lowered an accessibility floor permanently.
- A hover test compared the foreground colour, which the fix never changed. It
  passed with the fix reverted — proved by reverting it.
- An assertion on the finance switch was satisfied by the ENGINE POWER switch
  elsewhere on the page. An assertion another element can satisfy is not a test
  of this one.
- `publish-docs.yml` ended by printing two URLs it never opened.
- The privacy policy's truth is asserted against the shipped manifest — good —
  but nothing checked the page a reader actually loads.
- A ledger exemption was added to `carry_over` with **nothing holding it to
  account**, which is how "these two tables" quietly becomes "and these others".
- The panel's own comment promises that closing it never stops a run (OP-16).

**The test.** For any guard, ask: *if the thing it protects were broken right
now, would this fail?* If you cannot answer without running it, run it — break
the thing, watch it fail, restore. Three tests written on 2026-08-11 exist only
because their first versions passed while guarding nothing.

**And the same discipline applies to diagnosis.** Four hypotheses about the blank
side panel were measured and killed before the right one — Windows occlusion, the
opening strategy, a zero-width layout, the engine's absence. Three mechanisms
were recorded WRONGLY on PR #152 and corrected. The conclusions converged only
because nothing was accepted without a number.

### Measured: what a backup bundle actually weighs — 2026-08-12

Built from the owner's real warehouse (113.6 MB database, 22.4s to build) when
he asked why the backup is zipped at all. The answer is a number, not a
preference:

| | files | size | share |
|---|---:|---:|---:|
| `warehouse.db` | 1 | 113.6 MB | 54.6% |
| `.jsonl` | 34 | 62.0 MB | 29.8% |
| `.csv` | 34 | 28.2 MB | 13.6% |
| `panel.jsonl.gz` | 1 | 4.0 MB | 1.9% |
| **total** | **73** | **207.9 MB** | |

Zipped: **36.0 MB — 17.3%**, in 1.8 seconds. So 1.8 seconds of CPU saves 172 MB
of upload, and with `KEEP = 3` Drive holds 108 MB instead of 624 MB. Uploading
unzipped is not a trade-off, it is six times everything.

**But the question was right about the part that mattered.** `panel.jsonl.gz` is
already gzip, which browsers read natively, and it was locked inside a zip they
cannot open at all. Lifting that one file out beside the archive costs 11% more
upload and removes the need for a zip reader — which is what made the
no-engine Data page reachable.

**Worth recording for later:** the bundle carries the same data three times —
in the `.db`, as `.jsonl` + `.csv`, and as `panel.jsonl.gz`. That is deliberate,
for three different readers, and compression hides it. If space ever becomes a
problem, the 90 MB of `.jsonl`/`.csv` is the part regenerable from the `.db`;
the zip is not the thing to reconsider.

### OP-20 · CI has not executed since 2026-08-19, and the reason is billing

**Measured 2026-08-20.** Every workflow run since `2026-08-19T14:28Z` fails in
**0-3 seconds with ZERO steps** — lint, test, contract-parity, scope,
migration-authority, and the store-documents publish alike. The last run that
actually executed anything was `2026-08-19T11:50Z` on
`claude/blissful-swartz-bdca44` (13/11/9 steps, the test job 1,030 seconds, and it
failed on code). The last CI success was `2026-08-19T11:11Z`.

GitHub's own annotation on the job, read out of the API rather than guessed:

> *"The job was not started because recent account payments have failed or your
> spending limit needs to be increased. Please check the 'Billing & plans' section
> in your settings"*

**This is an account setting and only the owner can clear it.** Nothing in the
code is involved, and `repos/.../actions/permissions` is `enabled: true,
allowed_actions: all`, so it is not a policy block.

**What it has already cost, and this is the part that matters:**

- **#214 — the whole documentation system — merged with CI never having run.**
  Its own merge run at `2026-08-20T04:57Z` is one of the zero-step failures. The
  system now telling every session to trust these documents was itself verified
  only locally.
- **SR-23 cannot be satisfied at all right now.** *"CI must be green on every
  push"* is not a rule anyone can follow while no job starts, and a red check that
  means "unpaid" is indistinguishable at a glance from a red check that means
  "broken" — which is how a real failure gets waved through.
- Every open pull request shows three failing checks that say nothing about its
  code. #219, #213 and `ci/the-suite-a-docs-change-actually-needs` all inherit it.

**Until it is cleared, a local full-suite run is the only verification available**,
and a PR should say so rather than showing a red tick and hoping the reader knows
why.

### OP-19 · The chaos test races the startup sweep it is checking — STILL LIVE, re-measured 2026-08-20

> **RE-MEASURED 2026-08-20, and "MOSTLY fixed" is too generous.** Thirteen runs of
> `test_a_killed_engine_does_not_leave_a_job_claiming_to_run` across two
> checkouts: **8 failed, 5 passed.** The `swept=True` marker did not close the race.
>
> It fails on **unmodified `cab69b1`** — 1 of 5 there — so it is not caused by any
> branch in flight; a separate worktree carrying only documentation changes failed
> 7 of 8. That asymmetry is this entry's own thesis rather than a second bug: the
> conditions differed, and **two other sessions were editing this repository at the
> time**, which is precisely the "loaded Windows machine" named below. The failure
> is always the same assertion, `tests/test_the_engine_survives_being_killed.py:266`
> — after crash and restart the job still reads `running`.
>
> The trap described below was walked into again on the way here, and this entry is
> what stopped it: three consecutive failures in the modified worktree looked like
> proof the branch had caused them. Four passes on the unmodified checkout refuted
> that in one command. **Never conclude from runs on one side only.**
>
> **Re-measured again on the evening of 2026-08-20, and this time the load was
> deliberate.** The partitioned muqawil crawl was running — ~1,964 requests against a
> live site — which is the loaded machine this entry names, rather than a coincidence
> of other sessions. Under it: **3 of 3 failures on unmodified `main` at `2366d6d`**,
> same assertion at `tests/test_the_engine_survives_being_killed.py:266`, and the same
> failure inside the branch. Both sides, as this entry demands. So a crawl in progress
> is now a known way to reproduce it fairly reliably — which is worth more to whoever
> fixes it than another run of the flake in quiet conditions.
>
> Consequence unchanged and worth restating: `_source_is_busy` reads that status,
> so a real crash leaves the source blocked from every future crawl with nothing
> anywhere saying why. That is the defect; the flaky test is only how it is seen.

Found 2026-08-11 while removing the engine's Google surface. The suite went red
on `test_a_killed_engine_does_not_leave_a_job_claiming_to_run`, and the first
comparison — one run with the change, one without — said the change had caused
it. **That comparison was worthless and the conclusion was wrong.** Four runs on
the unchanged code failed three times.

`Engine.start()` waits for `/api/health` to answer and nothing more, then the
test reads `crawl_job.status` immediately. The stale-job sweep that clears a
crashed run is a separate startup step, so whether the assertion passes depends
on which of the two lands first. It is a race by construction.

CI has been green all session, which means the sweep reliably wins on the Linux
runner and reliably loses on a loaded Windows machine — the worst arrangement,
because it makes the flake look like "works in CI, broken locally" and invites
exactly the wrong diagnosis.

**The fix was not a sleep.** `reclaim_orphaned_jobs` now records when it
finished, in `scrapex_meta` beside the heartbeat that was already there, and
`Engine.start(swept=True)` waits for that value to change. The marker is written
UNCONDITIONALLY — a marker that appears only when there were orphans would be
absent on every healthy start, and anyone waiting for it would wait for ever on
exactly the machines where nothing had gone wrong.

> **RE-MEASURED 2026-08-19 AND IT IS BACK, under load.** Three consecutive runs of
> `tests/test_the_engine_survives_being_killed.py` on the owner's Windows machine --
> while a full suite and twenty review agents were running -- gave **pass, FAIL,
> FAIL** on an unchanged tree. The marker fix does not hold at this load, so
> "MOSTLY" in the heading is doing real work.
>
> Recorded rather than diagnosed, and deliberately not blamed on the change that was
> in flight: this entry's own warning below is that a with-and-without comparison
> proved nothing here before. What is new is the load. The next step is to find
> whether `Engine.start(swept=True)` is on this path at all, not to add a sleep.

**Four runs in four, green.** And an honest note on the check: removing the wait
again passed three runs in three that afternoon, having failed three in four
that morning. A race that depends on machine load cannot be reproduced on
demand, so the mutation check proved nothing — which is precisely why "it passes
now" was never evidence in the first place. The proof is structural and readable
in the code: health is answered by the HTTP thread the moment the port binds,
and the sweep runs on the worker thread after it connects. Two tests in
`test_jobs.py` hold the marker's two properties deterministically.

**NOT FULLY CLOSED, and saying so is the point.** Later the same day it failed
once more inside a FULL `-m "not extension"` run, then passed the next full run
and every targeted one. So the sweep wait removed the race it was aimed at and
something else in that test is still load-sensitive — the kill/restart cycle
runs real subprocesses and a 90-second health wait, and the whole suite is a
heavier neighbour than any subset.

Recorded rather than declared fixed, because "it passed this time" is exactly
the evidence this entry exists to reject. The next step is to find what ELSE in
the cycle depends on timing, not to run it again until it is green.

## 6c. The extension/engine separation, audited — 2026-08-11

The owner asked whether the extension is fully separated from the engine. What
follows is what was measured, including the note that turned out to be my own
misreading. Four were raised; one was a defect, two were correct by design, one
did not exist. A fifth was found only by comparing the two directories directly
instead of trusting the tool's own list.

**Separated, verified.** Zero `.py` or `.pyc` under `extension/`. The shipped
package is literally `cp -r extension build/scrapex` minus `tests/`, `README.md`
and `*.pem` (`release-extension.yml:85`), so no Python byte reaches the store.
Two independent release triggers — `scrapex-v*` and `engine-v*` — neither
building the other's artifact. Runtime contact is two narrow paths and nothing
else: native messaging for CONTROL, HTTP on `127.0.0.1:8000` for DATA
(`extension/transport.js`). The extension id is a runtime argument to
`nativehost.build_manifest`, not a constant in Python.

### SEP-1 · The extension's own tests are written in Python — DECISION, not debt

`release-extension.yml:64` installs the Python package and runs
`pytest -m extension`; 21 test files carry that mark. CI *also* runs
`node --test extension/tests/*.test.mjs` — 9 files, **zero npm dependencies**.

The split is not accidental. The Python tests drive a real Chrome through
Playwright and assert rendered geometry, resolved CSS and live DOM; node cannot
do that without an npm dependency, and this repository refuses npm dependencies
on purpose (the reason is written out in `extension/bundleview.js`, which reads
a gzip stream with the browser's own `DecompressionStream` rather than bundling
a zip library).

So the recorded position is: the extension's **runtime** carries no Python; its
**browser-driving test harness** does, by choice. The cost is stated rather than
paid — if `extension/` is ever moved to its own repository, that harness has to
be ported or replaced, and that is a real day of work, not a footnote. Nobody
has asked for a separate repository, and until someone does this is not debt.

### SEP-2 · Generated copies that did not say they were generated — FIXED

Five files exist on both sides of the boundary. Four were generated from
`design/` by `tools/sync_design_assets.py` and carried no marking at all —
`extension/appearance.js` opened straight with `(function () {`, and
`design/tokens.css` said *"canonical source … run the tool after editing this
file"*, a sentence copied verbatim into both generated copies where **both
halves of it become false**.

This is not theoretical: it is the trap this session fell into. See Q1b in
`ENGINEERING.md` for the rule and `test_every_generated_copy_says_it_is_one` for
the guard, which was mutation-tested — the banner was stripped from one copy and
the test failed by name before it was restored.

### SEP-3 · `timezone.js` had a rule of its own — FIXED

The fifth file. `extension/timezone.js` and `scrapex/webui/static/timezone.js`
were 493 identical lines with **no source between them**, kept equal by
`test_display_time_zone.py::test_the_two_copies_of_the_module_are_identical`.

That test works and was never missing — the first draft of this audit was about
to report it as an unguarded duplicate, and re-reading the file refuted that.
What the test could not do is say which copy is right. Its failure message reads
*"copy one over the other"*, and a reader who had just fixed the extension copy
and a reader who had just fixed the workspace copy receive the same instruction;
one of them reverts the other's work while obeying it.

`timezone.js` is now authored in `design/` and generated into both, like the
other four. The byte-equality test is kept — it guards the property directly
rather than through the tool, and deleting a working test to lean on a script is
the weaker arrangement.

### SEP-4 · `PROTOCOL_VERSION` in two languages — CORRECT, no change

`scrapex/native.py:49` and `extension/transport.js:25` both state the number,
because JavaScript cannot import Python. `test_native.py::test_the_two_protocol_constants_cannot_drift`
holds them together, and it has the shape section 6b demands: it asserts the
regex **found** the line, by name, before comparing the value. A reformatted
declaration fails the test rather than passing it vacuously. It is inside the
extension gate (`test_every_test_file_that_reads_the_extension_carries_the_mark`),
so a change to `transport.js` cannot route around it. There is exactly one
literal on each side — `engine.js` and `webui/app.py` both import rather than
restate. Closed as a correct contract coupling.

### SEP-5 · "The engine reads the extension's manifest" — WITHDRAWN, my error

I reported that `scrapex/version.py:10` makes the engine depend on
`extension/manifest.json`, reversing the dependency. It does not. `version.py`
contains no `open`, no `read_text`, no `Path` and no `json.load` at all — line 10
is prose in the module docstring saying the extension's number is deliberately
**not** there, and explaining why the two versions are allowed to differ. I read
a docstring as code.

The only Python that reads that manifest is `tools/panel_harness.py:119`, a
development harness that never ships. There is no reversed runtime dependency.
Recorded here so the note is not raised a second time by someone reading the
same docstring.

## 6d. The whole file re-measured — 2026-08-12

Six agents read the code, the git history and the live warehouse, one entry at a
time, and were told explicitly never to verify a claim against this file's own
prose. A sceptic then tried to refute every closure, because striking an item off
is the only irreversible move here: an item wrongly left open costs a second
look, an item wrongly closed is forgotten.

| | |
|---|---|
| items measured | 47 |
| still open (or *changed* — real, but not the problem described) | **45** |
| genuinely closed | **2** — Q-1, Q-3 |
| closures claimed and **refuted** | **6** — OP-2, ت2, Q-2, Q-4, Q-5, Q-11 |

**What this file got wrong, as a class.** Not the judgements — the *numbers*, and
the *statuses of things fixed elsewhere*. Almost every figure quoted more than
once had drifted: `app.py` 2,955 → 3,347 lines; Sika 78 → 185 observations;
branches 117 → 148; currencies 93 → 119 requests; sources "six of twelve" →
seven. Two entries described fixes that exist (OP-13, OP-14) and one described a
fix that **does not** (OP-18). The lesson is mechanical, not moral: a number
written down once is a number nobody re-counts, so every figure now carries the
date it was measured.

**Three things are broken on the owner's machine right now** — not paperwork:

1. **ALSWEED is being refused with HTTP 429**, five times on 2026-08-11, because
   `crawl_honour_delay` is `'0'`. **BV-3**.
2. **The engine's own Settings page says "Not running" while it crawls** — a
   second `worker_alive` computation at `app.py:2438` that the fix never reached
   — and the runtime heartbeat freezes under `database is locked` when a job
   holds a write transaction. **OP-6 · ت2**.
3. **The diagnostic-page guard is still blind**, and this file said it had been
   fixed. **OP-18**.

**And two failures of mine, recorded because they are the same failure twice.**
#177's guards are string greps over `app.py`'s text — the code the commit changed
has no executing coverage (**OP-2**). The same day, a test I wrote for the
spreadsheet chooser passed against the mutation because it drove the helper
rather than the feature; that one was caught before merging, by attacking my own
branch. The rule that follows: **a guard must fail when the behaviour is broken,
which is only demonstrable by breaking it.**

---

## 7. Done — newest first, so it is not re-proposed

*This table and `CHANGELOG.md` answer two different questions and neither replaces the
other. Here: what was done, when, and by which commit — the session-level record. There:
which VERSION a capability is guaranteed from, generated from `scrapex/version.py` and
never hand-written (`e9dd17e`). A feature can appear here the day it is built and there
only when a release carries it.*

| when | what | commit |
|---|---|---|
| 08-11 | **The Side Panel opened blank until you clicked elsewhere.** Chrome creates the panel document HIDDEN and reveals it only after `load` (8.9ms and 6.5ms after it, two traces); a hidden document's resource loading is deprioritised, so the panel stayed hidden until `load` and `load` was slow *because* it was hidden. `app.js` is now appended by `boot-app.js` on `load`, and its entry point asks `readyState` instead of waiting on a `DOMContentLoaded` that has already passed. Owner-verified in real Chrome | PR #152 |
| 08-11 | **The engine had not started since the collapse to one database.** `databases.json` still said `mode: split`, and the refusal message named `init-db` — which creates an EMPTY database and has never read `marketlens.db`. Following it would have left 110 MB of prices orphaned. `scrapex carry-over` copies both files read-only, counts distinct source rows against a destination baseline, and moves the pointer only if every table of data agrees. Ran on the owner's data: 338,000 rows, 88,286 price observations, zero short | PR #159 |
| 08-11 | The release built the engine in the same environment that ran the tests, so `pytest` and Playwright shipped inside the binary (193 references to playwright in the published exe). Build moved to a venv with runtime extras only, plus a 45 MB ceiling. **Measured honestly: 67.6 MB → 60.1 MB, eleven per cent — not the two thirds the disk sizes suggested.** A `--splash` covers the unpack, which is the part that actually looked broken | `756fa39` (#154) |
| 08-11 | `source_site.active` said all twelve sources were live while `sources.yaml` had five switched off. The column is written once on insert and never set to 0 — an inactive source is never crawled, so the only code touching its row never runs. Its one reader filtered on `WHERE active = 1`, matching every row. `reconcile_active` writes the manifest's intent on every panel flip; a source the manifest no longer names is left alone, because that is `undeclared_sources`' business | `b90c239` (#155) |
| 08-11 | "Five currencies with no exchange rate" was never five and never currencies: `UNKNOWN` (3,149 obs, all belonging to the deleted SPARK_ESHOP), `USD` (the base), and `SLL`/`ZWD` — retired in 2022 and 2009. The engine asked Google for all three every refresh cycle, failed, and wrote three warnings nobody could act on. Named in `UNQUOTABLE` with a reason and date each | `0010677` (#156) |
| 08-11 | `publish-docs.yml` ended by echoing two URLs. The publish writes through the Contents API; the page reads through raw.githubusercontent.com, and hangs on a `data-sx-doc` attribute in a separate repository. Either half could break with the publish still reporting success — and the first to notice would have been a Google reviewer rejecting the store listing. Both halves are now checked, with a retry for CDN lag and no browser | `bf0912b` (#158) |
| 08-11 | `mypy --strict` over the price files for the first time: 72 findings, 14 correctness-shaped, **10 false and 2 real** — a `None` ruled out only by a raise twenty lines up, and a cache typed `dict[str, object]` feeding a function that needs a `RobotsReport`. Both were mine from the same day. The gate itself is NOT here: 60 of the 72 are annotations, and that churn buys no defect | `1631af8` (#157) |
| 08-11 | robots.txt became the owner's decision per site — follow the tool default, obey that site, or write a rule for it alone | `adf31b2` (#153) |
| 08-11 | The Engine page: status, install disclosure, overflow menu, and a disabled power placeholder. Final review found a touch target loosened from 48 to 47.5 to pass (measured: it renders at exactly 48), a hover test that stayed green with its own fix removed, and eight dead class names the UI-kit gate was right to reject | `db44ce0` (#151) |
| 07-30 | Version management: one version with drift-tested mirrors in `pyproject.toml` and `extension/manifest.json`, a capability ledger whose minimum-extension gate is derived from it, a baseline that fails the build when the capability set moves while the number stands still, and a panel that says which version it is and what that version can do | `e9dd17e` |
| 07-29 | Crawl pace controls moved into the panel; the web page proved display-only by a test that fails if it grows an input | `2253308` |
| 07-29 | A market rate now outranks a storefront's in all four USD subqueries — authority first, then recency | `69e986c` |
| 07-29 | advancedcastle's own published exchange rate captured under `source_kind='shop'`, on a session of its own because the country is a cookie, not a path (188 shop rows live) | `b43405c` |
| 07-29 | Sika's trade tier reaches the warehouse — 78 observations now carry `price_trade`, was 0 of 73,084 | `436105c` |
| 07-29 | The reason advancedcastle's Egyptian price is not crawled, filed beside the source it describes | `e639310` |
| 07-29 | The sealed-archive / WAL cluster: a sealed archive keeps its rows, the in-flight guard reads the seal not a filename, a compaction says "superseded" not "moved", `Repair` really refreshes statistics | `234cdc1`, `4103e48`, `4dfb9e8` (PR #10) |
| 07-29 | Reconnaissance of onlinestore.heidelbergmaterials.eg committed *before* any decision — 23 live requests, three traps recorded, five questions left open | `73af22b` |
| 07-29 | The panel stops storming the engine with N+1 requests and stops stealing the log selection | `f901638` |
| 07-29 | CI made to actually run the guards it had: the 53-test panel suite (with the only XSS guard) had been silently skipping, and `extension/app.js` got its first behavioural tests | `48ec48b` |
| 07-29 | Ten dead native-host commands retired; the HTTP transport states its protocol version; one commit point for where the warehouse lives | `0a2209c` |
| 07-28 | `main` repaired so it starts from a clean checkout: nine defects including magento's half-brand (which read as ~536 price periods closing on prices that never moved), salla/zid honouring Cancel, and `engine.log` finally rotating | `c7fa4ea` |
| 07-28 | The row fold stops merging two countries into one row — measured 628 → 561 with 58 silent country merges | `10dc4ab` |
| 07-28 | Variation folding + `category_leaf` (MADAR 3,322 of 3,417; ADVANCEDCASTLE 163 of 168 across depths 1–6) | `e569753` |
| 07-28 | Edit, rename, stop-tracking and wipe a source, from the panel and from the API, with the rename moving nine tables in one transaction | `412785b`, `8c1d661` |
| 07-28 | Grid sorting that reads the column instead of a list of names, Arabic collation, and a fit that stays fitted | `059820d` |
| 07-28 | The header's buttons and a set filter that means it (numeric filters matched nothing; blanks were unselectable) | `d3bfd21` |
| 07-28 | The crawl-delay switch, shipping *honouring*, announcing the number when overridden; and the rate-refresh lock that was blocking queued jobs | `c63ec21` |
| 07-28 | Per-page resume journalling for zid and hybris | `fd2b6d9` |
| 07-28 | Seven detail groups, generated migration, and a static test that fails when a connector's `group=` hint disagrees with the map | `ba8ee09` (0046) |
| 07-27 | Exchange rates from Google Finance with the date on every number | `5c7f2dc` |
| 07-27 | GPP Libya — it publishes a local price and the parser can now read the page it publishes it on. **Verified today: LY carries DIESEL and GASOLINE at 0.15 LYD, observed 2026-07-29.** This closes the open question in memory `gpp-libya-missing.md` | `292bfea` |
| 07-27 | A web page can no longer drive the local engine (origin lock, three layers) | `3d7d1a9` |
| 07-26 | The bilingual vocabulary sweep: unmarked = English, `_ar` = Arabic, `PAYLOAD_VERSION 2` refusing every pre-sweep payload | `cd5348a` + 0038–0042 |
| 07-21 | GPP rebuilt around the local-currency price each country page publishes; USD list figures demoted to a canary | `ff28f41`, `f769c59`, `7cfa8f2` |
| 07-19/20 | Phases 5 and 6: settings, outputs, retention-by-compaction, and the 17 defects an adversarial review found past 527 green tests | `f8b6d6c` |

*(GPP's ten-year history backfill appears to have run: 62,761 of 73,162 observations carry
`provenance='reported'`, measured today. memory `gpp-local-currency.md` still lists it as an
owner to-do — **inferred**; the check is which run wrote them.)*

---

## Appendix A — where the material for this file came from

- `git log` on `main`, last ~130 commits. The commit messages in this repository are the
  single best record of decisions and their reasoning; most of §1 and §5 came from them.
- `gh pr list --state all` (15 PRs total; #10–#15 all closed or merged on 2026-07-29, and
  no PR is currently open), `git branch -a`,
  `git cherry -v origin/main <branch>` for each unmerged branch.
- `~/.claude/projects/C--Users-User01-source-repos-mbiXaddin/memory/` — the standing rules.
- Every file in `docs/`, and `sources.yaml`'s `notes:` blocks.
- The live warehouse, read-only
  (`sqlite3.connect("file:...?mode=ro", uri=True)`), for every measured number.

## Appendix B — status of every file in `docs/`

| file | status |
|---|---|
| `BACKLOG.md` (this file) | **live** — the tracking document |
| `CANDIDATE-SOURCES.md` (07-31) | **live** — the queue of sites the owner has sent and nobody has probed yet. Deliberately outside `sources.yaml` (SR-13). A row leaves it when the site becomes a manifest entry |
| `SOURCES-REGISTER.md` (07-31) | **live, derived** — the developer's per-source scoreboard, split price capture / generic extraction. Reads out of the manifest, the connector directory and this file; when it disagrees with `sources.yaml`, the manifest wins. Delete a reference in it when the matching `OP-`/`DEC-`/`BV-` closes |
| `plan-closing-the-gaps.md` (07-25) | **superseded by this file.** Phases 0–2 delivered; its still-live items are DEC-4, DEC-5, DEC-6, DEBT-2, Q-10. Keep for its measured 07-25 snapshot |
| `MASTER-PLAN.md` (07-18/23) | **stale and misleading** — see DEC-1. Its §8 asks the owner to confirm a topology its own header says he already rejected, and it cites a `spikes/` directory that has never existed in this repo. Keep as a design study; correct the header once Q-6 is answered |
| `REVIEW-2026-07-28.md` | **live as evidence, superseded as a queue.** Its open items are OP-4, OP-5, OP-6, OP-7, OP-12, OP-13, OP-14 |
| `column-vocabulary.md` | **live** — the map is the contract; §Status feeds DEC-4 and Q-7 |
| `robots-policy.md` | **live** — SR-8 |
| `data-page-schema.md` | **live** — the Data page ruling |
| `DESIGN-SYSTEM.md` | **live** |
| `recon/heidelberg-materials-eg.md` | **live** — Q-1…Q-5 |
| `COMPATIBILITY.md`, `GENERIC_CATALOG.md`, `archive/db1-domain-database-isolation.SUPERSEDED.md` | **live** — the generic/price split (G0/G1/DB1). Not touched since 07-20; nothing in the last 130 commits builds on them, so their roadmap half is dormant **(inferred)** |
| `CLAUDE-after-database-separation-20260720.md`, `CLAUDE-after-price-history-20260720.md` | **historical.** These are two saved copies of the original product brief, not plans. Keep; do not read them as current requirements |

## Appendix C — memory files that are NOT about ScrapeX

These belong to the **mbiXaddin Excel add-in**, a different project. Listed only so they are
not lost when someone sweeps the memory folder:

`arch-review-2026-decisions` · `activation-dialog-redesign` · `sync-version-review` ·
`ndepend-baseline` · `ribbon-button-view-refactor` · `schema-guard-system` ·
`update-system-review-plan` · `codebase-consolidation-campaign` · `systemconstants-slim` ·
`library-menu-plan` · `pipelinelogger-removal-audit` · `identityintelligence-retained` ·
`connectivity-odc` · `logging-v42-plan` · `logging-roadmap` ·
`pipeline-observability-fragmentation` · `pipeline-observability-roadmap` ·
`configpresetentity-planned-removal` · `dead-file-check-by-types` ·
`export-presentation-config` · `config-bag-validation` · `debug-mode-via-build-config` ·
`docs-headers-translation-pass` · `core-test-coverage` · `expert-assessment-backlog`

Cross-project working rules that apply to both: `git-commit-heredoc-quotes` (SR-20),
`present-issues-as-questions`, `explain-before-options`, `always-recommend-option`,
`recommend-as-architect`.
