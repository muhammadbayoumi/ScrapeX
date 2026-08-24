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

### OP-43 · Four written premises about the muqawil profile page were wrong, and one of them hid a price
**Found 2026-08-22** under `REQ-31`, measured over **2,419 real profile pairs** read
read-only out of the running crawl, after he warned that the pages are not consistent —
«المعلومات غير ثابته ولا متفقثة بين الصفح يعنى ممكن تلاقى معلومات تانية وطريقة عرض مختلفة».

Everything this repository believed about that page came from two committed fixtures,
which are **one contractor**. `R-19` labelled that limit honestly; the conclusions
outlived the label.

| premise, and where it was written | what 2,419 pages say |
|---|---|
| `extract/muqawil.py`'s module docstring: the fifth `<table>` is *the technical rating* | There is no technical-rating table. `contractor-tab4` holds **zero tables** in its DOM subtree on 2,360 of 2,360 pages. The fifth table is the **self-build price** schedule |
| `GROUPS_NOT_LOCATED`: the technical rating *"carries no table for this contractor"* | Not this contractor — the site. It is a tab button over an empty pane |
| the plan: `contract_request_url` *"has no known URL pattern and is not on the card"* | The card is on **100%** of pages. The URL is one site-wide constant, so it earns no column — and the form carries the **Commercial Registration number** |
| `write_groups`: the licences cell carries both languages *"with no separator"* | There are two dashes in it. They are **hierarchy** separators inside each language, and splitting on them would have cut a path into pieces and called each piece a language |

**All four are fixed and the fixes are in the same pull request**, per **C2**. What is
left over is recorded rather than repaired:

- **The site's own English is wrong on 100 of 1,685 licence rows** — 30 truncated to
  `Civil Engineering -` (the same string for two different activities) and 70 naming a
  *different activity*. Detected by level count, stored with the Arabic path alone.
  Across the corpus that leaves **3 of 29** taxonomy nodes with no English name, which
  are the three the site never publishes correctly. → `Q-17`.
- **`sub_contractors` and `main_contractors` carry rows on 2 and 0 of 2,419 pages.**
  Declared and unbuilt. → `Q-18`.
- **The card census has one stated blind spot.** `undeclared_cards()` reports an
  undeclared card only when it carries a table or a list, because the contractor's own
  name is a text card whose title differs on every page. Measured: filtering by
  position is wrong on 40 of 5,668 pages, by content on 0 — so a new **text** card
  would not be reported. The narrower guard with no false positives was chosen
  deliberately.

**Next action:** none blocking. The 34,834-page crawl is storing evidence now and
`R-40` made the re-parse path work, so every column above lands on a re-approval with
no network.

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
(`app.py:56`, `:161`, `:162`):

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
| `scrapex/webui/app.py:1682` — `/api/health` | the new two-heartbeat `worker` verdict | correct; the panel reads this one (`extension/engine.js:38`) |
| `scrapex/webui/app.py:2749` — `_about` | `worker_is_alive(conn)`, single heartbeat | **the function the fix superseded** |

`_about` renders the engine's own `/settings` page
(`scrapex/webui/templates/settings.html:162-167`), so **the engine still shows
"Not running" while it is crawling**, and advises the owner to check whether the
engine is started at all.

**Next action:** three separate things — the second `worker_alive` at
`app.py:2749`; the heartbeat's behaviour under a held write lock; and the 409 on
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
scrapex/snapshotcrawl.py:164       if page.url in seen:
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
(`scrapex/cli.py:1009`). Nothing automatic calls it: not `ui`, not autostart, not the
native host, not the panel.

**What a split-era user actually gets**, simulated end to end against a fake split
installation:

| path | result |
|---|---|
| any CLI command | clean message naming `scrapex carry-over` — `main()` catches everything (`scrapex/cli.py:1143`) |
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
`_upgrade_what_is_only_behind` is called (`scrapex/cli.py:867`) when the pointer is
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

**RULED 2026-08-21 — (a).** → [R-28](RULINGS.md#r-28--the-74-approved-pages-are-wiped-and-re-approved-from-disk).
**What remains of OP-25 is option (c) alone**: schema-drift review still does not
exist, the error message still points at it, and it was passed over for timing
rather than on merit. It stays open here as the part that serves every future
source.

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
> | `unavailable` | the site is not showing this contractor **right now** — reversible, and the row comes back on the next crawl that sees it. **RULED 2026-08-21: this one** → [R-29](RULINGS.md#r-29--a-contractor-the-site-stops-showing-is-unavailable-not-retired) |
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

### OP-28 · The muqawil crawl driver had 452 lines and no tests at all
**Status: ADDRESSED 2026-08-21** — 19 tests in `tests/test_the_crawl_driver_cannot_lose_a_run.py`, eleven mutations killed.
The account below is kept because the exposure it describes is the reason the tests are shaped the way they are.

> **Corrected:** first written as *"306 lines"*, which was wrong — the number was read off a line in a traceback rather than off `wc -l`. It is **452**.

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

### What the tests cover, and what they found

Nineteen tests, grouped by the way hours get lost rather than by function:

| | |
|---|---|
| a log line kills the run | a real `cp1252` stream (`TextIOWrapper`, `errors="strict"`), not a mock — `say` must not raise, the **log must keep** the character the console could not show, and a line cp1252 *can* encode must not be degraded to ASCII |
| a crawl into a warehouse that is not there | `open_engine` exits 2 and **the file is not created** (`R-24`) |
| a mistyped `--only` | refused, and refused **before the connection is touched** — `conn=None` is passed deliberately, so a late refusal would raise the wrong error |
| `--approve` reading another run's evidence | `_` is a `LIKE` wildcard: unescaped, `my_run-%` also matches `myXrun-…` |
| the two locales of one page | paired on the URL with the locale removed, never on arrival order; and the **later** read wins for a page a retry stored twice |
| an empty departure window | says *"Crawl first"* rather than reporting every contractor as departed |

**And the mutation run found two defects in itself, which is the part worth keeping.**
Three of the first twelve mutations printed `NOT APPLIED` — their literal source
strings had their backslashes mangled passing through a shell heredoc — and they were
the valuable three: the `LIKE` escaping, the last-read-wins ordering, and the log
keeping an unshowable character. A fourth applied but was a **no-op** (a trailing comma
added to a call), "survived", and meant nothing. **A mutation that does not apply is
not a passing guard**, and reporting it beside real results is a harness lying quietly.
Re-authored by line number, with the anchor lines asserted before anything is written.

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

### OP-30 · Two migration ledgers, one number space — and engine `0006` is the first to collide

**Found on the owner's LIVE warehouse, 2026-08-21, while upgrading it at his
instruction.** The upgrade backed the file up, applied both migrations correctly, and
then **refused to stamp them**, leaving a warehouse no current build can open.

```
engine migration 0006_a_row_says_when_it_was_last_proved_absent.sql
checksum changed; restore the original migration file and retry
```

**The message is wrong about the cause, which is what made this take a while.** No
migration file changed. `database_migration` is `migration_number INTEGER PRIMARY
KEY` — **one number space** — and the collapsed warehouse carries **two streams** in
it:

| numbers | stream | applied |
|---|---|---|
| 1–5 | the **engine**: `schema.sql`, `0002…` – `0005_a_snapshot_says_how_it_is_encoded.sql` | 2026-08-20 |
| 6–55 | the **price** database, carried over: `0006_change_event.sql` – `0057_the_weight…` | 2026-07-31 |

So `_verify_checksums` looks up **number 6**, finds `0006_change_event.sql`'s digest,
compares it against engine `0006`'s, and reports a changed checksum. The row keyed 6
is not engine migration 6 — **it is a foreign row.**

**WHY THIS WAS LATENT UNTIL NOW, EXACTLY.** Engine migrations had only ever reached
`0005`. Number 6 is the first the engine has ever wanted, and #235 is what introduced
it. Every earlier engine migration fitted below the carried-over range by luck.

**WHY NO TEST AND NO CI RUN COULD HAVE CAUGHT IT, which is the part worth keeping.**
A fresh `init-db` writes only the engine's own rows, so the number space is empty
above 5 and nothing collides. **CI always starts from a fresh database**, and 273
tracked test files plus the `migration-authority` job — which runs the whole suite
against the real migration stream — all pass. The collision needs a warehouse that
*carried over from marketlens*, and no test has one. That is the same class of gap as
`R-24`: the upgrade path is only exercised by a real user's file.

**WHO IT HITS.** Every installation that carried over from the price database, the
moment it upgrades past engine `0005`. A fresh installation is unaffected.

### What the state actually is, measured rather than feared

| | |
|---|---|
| `PRAGMA integrity_check` | **ok** |
| both migrations | **applied** — `dataset_sighting.last_absent_at` and `generic_record.node_id` are both there, `generic_record_field_change` exists |
| `user_version` | **7**, correct for the applied schema |
| rows | **every one of 53 tables unchanged** except `generic_page_snapshot` +6, which is the crawl writing six more pages before it was stopped |
| the backup | verified restorable: integrity ok, v5, 16,781 sightings, 9,526 snapshots, 1,172 records |

**So no data was lost and the schema is right.** What is wrong is four fields in a
ledger — and `connect()` verifies that ledger, so the warehouse is unopenable until it
is fixed. **The crawl cannot resume until then either**, because `open_engine` goes
through the same `connect()`.

### The fix, and why it is not "renumber and move on"

The engine's verification keys on a number that another stream also owns. The honest
reading is that **it should key on the migration NAME**, which is unique across both
streams, and that a name with no row is simply unstamped. Three ways, and the choice
has data consequences:

- **(a) Verify and stamp by `migration_name`.** Smallest change, and it makes the
  foreign rows harmless rather than fatal. `migration_number INTEGER PRIMARY KEY`
  means a new row cannot reuse 6, so the number becomes `MAX(number)+1` and stops
  meaning "position in the stream" — which it already does not mean, given two streams
  share it.
- **(b) Namespace the ledger** with a `stream` column, keyed `(stream, number)`, and
  backfill the carried-over rows as `price`. Correct, and it is a migration that has
  to run *before* verification — the ordering is the whole difficulty.
- **(c) Have `carry_over` not bring the price ledger across at all,** and repair
  existing warehouses. Cleanest in the long run and the largest change; it also
  discards a record of what the price database did, which `C4` reasoning says to keep.

*Recommended: (a) now, because it unblocks a live warehouse and makes the failure
impossible rather than deferred; (b) or (c) as the real model, once he rules.*
**Not started — his call, on live data.**

### OP-44 · ~~A dataset card said "no successful crawl yet" over 17,304 crawled rows~~ — FIXED 2026-08-22

**He reported it from his own panel** — on the board as
[REQ-33](REQUESTS.md#req-33--the-dataset-cards-said-no-successful-crawl-over-crawled-rows).
The two muqawil datasets read

    muqawil.org · Saudi Contractors Authority · contractors [Row 17,304]
    17,304 products
    no successful crawl yet

while `aramco.com` and `spark-eshop.com` beside them read *"Last crawled 16 August
2026, 8:00 AM"*. 17,304 rows plainly came from a crawl, so the display was wrong
about something it had the evidence to answer.

**Measured on his live warehouse, read-only, 2026-08-22** (schema v9, while the
profile crawl was running against it):

| | |
|---|---|
| `crawl_run` | **155 rows over twelve source keys** — `ADVANCEDCASTLE` … `SPARK_ESHOP`, and **not one for muqawil** |
| `source_site` | the same twelve keys. **muqawil is not among them** |
| `site_profile` | `muqawil` and `muqawil_org` — the other registry |
| `generic_record` | `contractors` **17,304**, `contractor_profiles` **704** |
| `generic_page_snapshot` | **24,480** pages, 1,728 with no `crawl_run_ref`, **139** distinct refs |
| the evidence behind the rows | `contractors` last captured **2026-08-21T17:56:31Z**, `contractor_profiles` **2026-08-21T21:44:48Z** |

**THE CAUSE WAS NOT THE MISSING `crawl_run` ROW.** `_dataset_rows` wrote
`"last_success": None` as a **literal**, and `freshnessLine`
(`extension/app.js:4649`) prints that sentence whenever the key is absent or
carries no `started_at`. So a `crawl_run` row for muqawil would have changed
nothing on the card — the fix had to arrive at that key.

**And the row could not honestly be written anyway.** `crawl_run.source_id` is
`NOT NULL REFERENCES source_site(source_id)` (`db/engine/schema.sql:122`), and
muqawil has no `source_site` row: which registry a source lands in is exactly the
split [REQ-25](REQUESTS.md#req-25--one-source-registry-with-a-category-visible-to-every-user)
holds and it is his decision, not a side effect of fixing a caption.
`crawl_run.job_id` points into `crawl_job`, and *"does a generic crawl belong in
the same job queue as a price crawl?"* is an open question for him at the foot of
[GENERIC-FETCH-SEAM.md](GENERIC-FETCH-SEAM.md) — writing the row from a CLI that
the scheduler does not drive would answer it by default. The same document says
of the second-run question: *"It may be enough to ask `generic_ingestion`; check
before adding a column."*

**So the freshness is DERIVED, and nothing new is stored.**
`extract/service.last_evidence_captured_at` reads
`max(generic_page_snapshot.captured_at)` over the pages `generic_ingestion` says
this dataset was built from, and `_dataset_freshness` puts it in
`ingest.last_successful_run`'s shape so the panel keeps one code path.

Four findings the measurement produced that the fix turns on:

* **`generic_ingestion`, not `generic_record.source_snapshot_id`.** A record keeps
  pointing at the snapshot that last **changed** it (`R-20`), so a confirming
  re-crawl would leave the date stale — the very complaint. On his warehouse:
  3,883 ingestions against 2,139 distinct record snapshots for `contractors`, and
  the two answers differ (`17:56:31Z` against `17:54:31Z`).
* **`ix_generic_page_snapshot_page` is worth 390x and had never been read.**
  It is `(page_snapshot_id, captured_at)` (`db/engine/schema.sql:843`); SQLite
  prefers the rowid because the planner cannot see that the row carries a
  compressed ~100 KB body. Measured over 24,480 pages: **353–373 ms** by rowid,
  **0.9 ms** through `INDEXED BY`, identical answer.
* **`max(page_snapshot_id)` is NOT a cheaper spelling of the same thing.** It
  agrees on this machine (0.2 ms) because `save_snapshot` never supplies
  `captured_at` — but `warehousemerge.py:269` INSERTs the other machine's
  `captured_at` verbatim under fresh local ids, so after the merge `R-43` makes
  routine the highest id can be the oldest page.
* **No measure goes beside the date, because *seen* is already taken.** Both
  surfaces print `rows_seen` after the instant and fall back to
  `requests_count`. The obvious candidate was the row count — and
  `dataset_sighting` already means *what the site showed us*: on `contractors`,
  **17,417 sighted against 17,304 stored**. Putting the stored count under the
  word `seen` would be a wrong answer to a question this schema answers exactly.
  `requests_count` is no better, because retries, 304s and the Arabic half of
  every page leave no second row. Both stay 0, the line reads *"Last crawled …"*
  and stops, and the count keeps its own line on the card.

Six mutations, six killed. The one that mattered is M5 — swapping
`generic_ingestion` for `generic_record` — which the newest-page test caught for
exactly the reason above.

**Still open, and it is his:** the two registries. This closes the display; it
does not merge `site_profile` into `source_site`, and a dataset still has no run
ledger of its own. If he wants one, that is `REQ-25`'s shape to decide.

---

### OP-41 · The test suite writes into the owner's live crawl log

**Found 2026-08-21, by reading the log to check on a crawl.**

`contractors.say` appends every line to `Path.home()/".scrapex"/"contractors.log"` with
no way to redirect it, so any test that reaches it writes to the **real** file. What
surfaced it: two lines saying *"departures not marked: the crawl is not provably
complete"* sat at the tail of the live log while a real crawl was running, and they came
from the gate tests, not from the crawl. A log read to find out what a crawl did is
worth nothing if a test can write to it.

It predates the work that found it — `test_the_crawl_driver_cannot_lose_a_run.py` has
been calling `crawl()` and therefore `say()` since it was written. Two things follow
from it, and the second is the reason this is recorded rather than patched:

* **Wrong content in a file used for diagnosis.** The lines are indistinguishable from
  a real run's, and this one nearly cost a wrong conclusion about a live crawl.
* **A path derived from `HOME` at import time.** In CI that is a container's home and
  harmless; on a developer's machine it is the file they read. The fix is to make the
  destination injectable rather than to monkeypatch it per test file — which is a small
  change to a module that is currently being edited by the six-item track, so it waits
  until that lands rather than colliding with it.

Mitigated where it was found: the new tests redirect `contractors.LOG` to `tmp_path`.
The general fix is still open.

---

### OP-31 · Six crawl workers starve another process out of the warehouse

**Measured 2026-08-21, minutes after `--workers` was built, by using it.** The owner
asked for the Engine to be started while a six-worker crawl was running. It refused:

```
sqlite3.OperationalError: database is locked
  scrapex/jobs.py:932  record_worker_failure
```

Every connection sets `busy_timeout = 5000`, so a writer waits five seconds before
giving up. **Six concurrent writers kept it waiting longer than that** — so the
failure is not a missing timeout, it is a timeout that is too short for the load the
new flag can create.

**THIS IS A COST OF `--workers`, NOT A DEFECT IN THE ENGINE**, and it was not measured
before the flag was written. `R-21` is about pacing outbound requests per site and it
says nothing about how many writers one SQLite file will tolerate — the concurrency
was designed against the site's tolerance and not the warehouse's.

**What is NOT wrong:** the crawl itself. WAL lets readers proceed throughout, the
workers wait for each other correctly, and no row was lost — `integrity_check` is ok
and 53 table counts were unchanged across the whole run. The contention is with
*other processes*, which is exactly what a background crawl is supposed not to do.

Three ways out, and the choice is a trade:

- **(a) Raise `busy_timeout` for the crawl's own connections only.** Smallest, and it
  makes the crawl wait for the Engine rather than the reverse — the right priority,
  since the Engine is what the user is looking at. Does not help a third process.
- **(b) Serialise the crawl's WRITES behind one lock** while leaving the fetches
  concurrent. The DB work is milliseconds against a six-second fetch, so this costs
  almost nothing and bounds the contention at one writer regardless of `--workers`.
  Larger change to `snapshotcrawl`'s write path.
- **(c) Cap `--workers` by measurement** rather than by the latency ratio alone, and
  say in the help what it costs. Cheapest to write, weakest guarantee.

*Recommended: (b) — it is the only one that makes the guarantee independent of how
many workers are asked for, and the cost is bounded by arithmetic rather than by
hoping. (a) as an immediate mitigation.*
**Not started.**

### OP-32 · ~~The fix for the black window has sat in the repository, unreleased~~ — RELEASED 2026-08-22 as `engine-v0.3.0`

**Status: CLOSED 2026-08-22 — the gate that let it happen was closed first, then he
published.** The entry is kept in full rather than trimmed: it is the only record of
why an install path where every component worked still handed him a black window.
Reported by the owner on 2026-08-21 as *"it did not install — black screen"*, and
captured as [REQ-28](REQUESTS.md#req-28--the-engine-would-not-install-and-showed-a-black-screen).

**The install path is neither missing nor broken. It is STALE, which is worse,
because every part of it works.** The panel reads the manifest, gets `0.2.1`,
correctly says *"Available to install"*, and hands over a byte-perfect download.
What arrives is the build from **before** `_first_run` existed:

| | |
|---|---|
| published | `engine-v0.2.1`, tag → commit `4386d25`, 2026-08-09T09:47Z |
| bare invocation there | `4386d25:packaging/engine_entry.py:62` → `return serve()` — the native host. **A citation of a past commit**: today's line 62 is a comment |
| `_first_run` landed | `7a067c5`, 2026-08-09T19:09+03:00 — **six hours after the release** |
| `--splash` landed | `756fa39`, 2026-08-10 |
| `scrapex/version.py:76` | `VERSION = "0.3.0"` — 0.2.2 when this was written, 0.3.0 since #247 |
| engine tags in the repo | `engine-v0.2.1`. That is the whole list, re-checked 2026-08-22. |

**Measured on the published artifact, twice, on 2026-08-21.** Stdin closed: zero
bytes, exit 0 — the window opens and vanishes. Stdin held open, as a real console
holds it: zero bytes, **still running after twenty seconds**. Nothing was written to
`~/.scrapex/engine.log`, which is still dated 2026-08-01, because it never reached
the code that could write.

**WHY CI PASSED IT, and this is the part a test can prevent.** The release asked the
built binary exactly one question — `--version` — which is the one argument no user
ever types, on the one branch that was already correct.
`tests/test_native.py::test_the_entry_point_tells_its_three_callers_apart` has
guarded the *source* dispatch since #141; **nothing has ever run the artifact.** Now
`tests/test_the_release_proves_the_double_click.py` and a new workflow step do: the
release launches the engine with no arguments, bounded by a timeout because a good
first run never returns, and refuses a build whose output is empty or which cannot
get past preparing a database. Eleven mutations, eleven killed — one of which caught
this guard accepting a data root that was named but never assigned.

**It was half-seen and not followed through.** `OP-15` already recorded, on
2026-08-11, that the Engine card read *"Installed version 0.2.2 / Latest released
0.2.1"* — and filed it as a **wording** defect about the two meanings of
"installed". The numbers were the finding: the release had not happened.

~~**Next action, and it is his.**~~ **— HE TOOK IT. `engine-v0.3.0` IS PUBLISHED,
2026-08-22.** *«اقطع الوسم»*, said after reading this entry, so the finding is what
produced the release. Recorded as facts rather than as a green workflow run:

| | |
|---|---|
| tag | `engine-v0.3.0` → `451468d`, which is `main` |
| the version at that tag | `scrapex/version.py:76` **0.3.0**, `pyproject.toml` mirror **0.3.0** — so the workflow's `test "$tag" = "$version"` had two numbers that agreed |
| workflow | completed, 28m36s |
| the manifest the panel reads | `"version": "0.3.0"`, `"tag": "engine-v0.3.0"`, `"published_at": "2026-08-22T13:17:13Z"`, `"minimum_extension_version": "0.2.2"`, protocol 1 |
| what it said before | `0.2.1`, unchanged since 9 August |

**The floor it published is 0.2.2, and that is the number that matters most here:**
`extension/manifest.json` is also 0.2.2, so this release demands nothing the
installed extension cannot do — checked before the tag by
`tests/test_version.py`'s floor guard, not after it.

**This entry is CLOSED as the defect it described.** What is not closed is the
confirmation that the published build installs on his machine; that stays on
`REQ-28`.

> **AND THE VERSION GAP THAT OPENS NEXT IS NOT THIS DEFECT RETURNING.** Migration
> `0010` is a contract change, so `R-35` moved the source to **0.3.1** against a
> published **0.3.0** — which is the ordinary state between two hand-cut releases,
> not a fault. `OP-32` was three things at once: nothing released across two bumps,
> the newest installable engine silent on a double-click, and the documents naming a
> tag the workflow would refuse. A gap alone is none of them.

> **STILL OPEN A DAY LATER, AND THE INSTRUCTION HAD GONE STALE WHILE IT WAITED.**
> He reported it again on 2026-08-22 — *«المحرك الموجود على github 0.2.1»* — with the
> panel reading `Latest version 0.2.1 · Available to install`. **Nothing is broken
> anywhere on that path, and this is the third time that sentence has had to be
> written about it.** `extension/releases.js:32` reads
> `ScrapeX/json/version.json` from the hub, `extension/app.js:3570` prints the
> `version` it finds, the workflow writes that same field
> (`.github/workflows/release-engine.yml:379`), and
> `tests/test_the_two_release_paths.py:276` already pins the writer's output to the
> reader's input. The manifest says 0.2.1 because 0.2.1 is the only engine tag that
> exists.
>
> **What HAD broken is this entry's own next action.** It said `engine-v0.2.2` while
> `VERSION` had moved to 0.2.2 at `adf31b2` and then to **0.3.0** at `e963269`
> (2026-08-22, #247, a schema change under `R-35`). The release workflow's first
> step is `test "$tag" = "$version"`, so the release the documents were telling him
> to cut would have been **refused before anything was built**. Six copies of
> `engine-v0.2.2` across `STATE.md`, `REQUESTS.md` and this file — two of them the
> whole command to copy, three the sentence telling him to cut it, one a note about
> a past failure — and nothing compared any of them with the source. Corrected in
> [#253](https://github.com/muhammadbayoumi/ScrapeX/pull/253), and guarded by
> `tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py`: an
> engine tag named as an *instruction* must equal `VERSION`, while a tag named in
> narrative prose is left alone so history is not rewritten to keep a test green.
> **It found all six on the untouched documents before a single mutation was
> tried.**
>
> **The limit of that guard, stated rather than discovered later:** it proves the
> tag he is told to push is the tag the workflow accepts. It cannot prove a release
> was cut, because nothing committed here knows what the hub holds — the tag list is
> absent from a `fetch-depth: 1` checkout and the hub is a network fetch, and either
> would turn this into a guard that skips or flakes. `Q-16` asks whether he wants a
> scheduled workflow that does look.

### OP-33 · ~~The owner's own warehouse is ahead of `main`, so the engine refuses to start on his machine~~ — FIXED 2026-08-21 by #243

> **CLOSED BY THE MERGE, NOT BY THIS WORK.** `claude/his-four-rulings` landed as
> [#243](https://github.com/muhammadbayoumi/ScrapeX/pull/243) (`eb691d9`) and brought
> engine migrations **0007** and **0008** with it, so `main` reads schema v8. Verified
> against his live file from the merged tree, read-only:
>
> ```
> "status": "Healthy",  "schema_version": 8,  "ok": true
> ```
>
> So a released engine built from `main` can now open his warehouse. **What is NOT
> closed is the panel's sentence**: an engine that refuses to start still never binds
> a port, so `extension/app.js:3424` still reports "Not detected" for a schema fault,
> a permissions fault and an absent engine alike. That half is now `OP-38`.

**The diagnosis, kept as written — it is why the merge mattered.**

    $ scrapex database-status
    "status": "Needs a newer ScrapeX",
    "action": "This database was written by a later version (schema v8; this
               build reads v6). Update ScrapeX and retry, and do not downgrade
               the database."
    $ scrapex ui --no-open
    error: the engine database is needs a newer scrapex — ... ; exit 1

`PRAGMA user_version` on `~/.scrapex/engine/scrapex-engine.db` is **8**.
`db/engine/migrations/` on `main` stops at `0006_a_row_says_when_it_was_last_proved_absent.sql`.
**0007 and 0008 exist in exactly one place** — the worktree
`.claude/worktrees/determined-liskov-0c89fe`, branch `claude/his-four-rulings`,
unmerged — and that branch's code was run against his live warehouse on 2026-08-21,
leaving the `pre-ledger-repair` and `pre-reapprove` backups beside it.

So the engine a release would ship **cannot open his database**, and `R-24` (a
database is upgraded, never replaced) is what forbids the obvious shortcut. Verified
from the branch that owns v8, against the same file: `"status": "Healthy"`, and
`scrapex ui --no-open` there answers `/api/health` **200** with
`worker_alive: true` in about 16 seconds.

**And the panel cannot say any of this.** An engine that refuses to start never
binds a port, so `checkEngine` gets a connection error and
`extension/app.js:3424` reports **"Not detected"** — which is false and sends the
reader to reinstall something that is already installed. The engine knows the
sentence; there is no channel that carries it to a panel.

**Next action:** merge `claude/his-four-rulings` before, or with, the release. Until
then the only engine that runs on this machine is that worktree's.

### OP-34 · A launch that dies in a console writes nothing to `engine.log`

**Status: OPEN, filed not fixed, per `R-01`.** Found while looking for the black
window's trace and finding none.

`_bind_log_streams` (`scrapex/cli.py:992`) says it plainly: *"run it from a terminal
and this does nothing at all."* It exists for the `pythonw` autostart path, which
has no streams. A double-click **does** get a console, so the redirect no-ops and
the failure goes to a window that is closing. `~/.scrapex/engine.log` is dated
**2026-08-01** across every launch attempt described in `OP-32`.

The instinct — *"a black screen very likely wrote something to engine.log"* — is
therefore wrong for the one path a user actually takes, and an hour can be spent
reading a three-week-old log as though it were evidence.

`_first_run` covers the user-facing half already: it holds the window open on
failure and names where it stopped. What is missing is the **record afterwards**,
for the machine the owner is not sitting at.

### OP-35 · ~~Half the CLI is unreachable from the shipped engine, and says nothing about it~~ — FIXED 2026-08-21

> **CLOSED ON HIS INSTRUCTION — *«ابدأ بـ OP-36 و OP-35 وضمهم لنفس tree»*.**
> `KNOWN_COMMANDS` is gone. `packaging/engine_entry.py:18` now calls
> `known_commands()`, which asks `scrapex.cli.subcommands()` — and that reads the
> subparser choices off `build_parser()` itself. **Derived, not extended:** a longer
> literal would have fixed today and drifted again.
>
> Measured after: **24 of 24** reachable, against 12 before. `database-status` and
> `relaunch` among the twelve recovered.
>
> Guarded by `tests/test_the_frozen_engine_can_start_itself.py`, which asserts the
> two sets are equal AND names the twelve casualties separately — because equality
> alone would still pass if both sides shrank together. The one private-argparse
> poke lives in `cli.py`, and `subcommands()` **raises** rather than returning an
> empty set if argparse ever changes shape: an empty set would make every argument
> look like Chrome, which is this defect total instead of partial.

**The diagnosis, kept as written.** Found while diagnosing `OP-32`; it is the SAME
defect, one layer along.

`packaging/engine_entry.py:18` hand-maintains the set of subcommands the frozen
binary will forward to the CLI. Anything not in it is assumed to be Chrome and goes
to `serve()` — which waits on stdin and prints nothing. The set lists **12**
commands. `scrapex.cli.build_parser()` has **24**:

    autostart  backup-databases  carry-over  contractors  database-status
    export-version  relaunch  restore-database  run-due  schedule  sources
    wipe-source

**Measured on the published 0.2.1 artifact, with a control**, so this is not read
off the source. One of the three is in the set; two are not:

| typed at `scrapex-engine.exe` | in the set? | exit | bytes printed |
|---|---|---|---|
| `status` | yes | 1 | **94** — *"engine database is missing: Reconnect the storage…"* |
| `database-status` | no | 0 | **0** |
| `autostart` | no | 0 | **0** |

The listed one answers, correctly and usefully. The unlisted ones are the black
window again. **`OP-33` was
diagnosed with `database-status`** — the command that names a schema-ahead warehouse
in one line — and it is on that list, so the shipped engine cannot answer the
question a stuck user most needs answered. So are `backup-databases`,
`restore-database` and `carry-over`: the three that exist to protect his data.

**The fix is not to extend the literal**, which is what drifted. Derive the set from
`build_parser()`'s own choices, so a new subcommand is reachable the day it is added
and this cannot happen a third time. Then the guard is one line comparing the two.

**Next action:** derive `KNOWN_COMMANDS`, add the comparison test, and mutate it.

### OP-36 · FOUR spawn sites put `-m scrapex.cli` in front of an executable that ignores it

**Status: ~~OPEN~~ FIXED 2026-08-21, on his instruction — *«ابدأ بـ OP-36 و OP-35
وضمهم لنفس tree»*.**

> **ONE MODULE, FOUR CALL SITES.** `scrapex/enginelaunch.py:74`
> (`engine_argv`) is the one that answers the `-m` question, and the module is
> `nativehost.py:57`'s three lines generalised: `frozen()`, `runner()`,
> `engine_argv()`, `engine_command()` and `working_directory()`. `relaunch`,
> `native`, `autostart` and `osschedule` all call it and none of them decides the
> `-m` question any more. It imports nothing from `scrapex`, so the two callers
> reached while the engine is still coming up cannot meet an import cycle.
>
> **All three bugs closed, and the mirrors asserted too** — a fix that made the
> frozen path right by breaking the source path would pass a one-sided test:
>
> | | frozen | source |
> |---|---|---|
> | `-m scrapex.cli` | **absent** | **present** |
> | `pythonw.exe` preference | ignored, with a real decoy beside a real exe | honoured |
> | `cd /d <repo>` in the Startup entry | **absent** | present |
>
> **Ten mutations, ten killed** — and the tenth is why the count is worth quoting.
> The `pythonw` test first passed for the wrong reason: it pointed `sys.executable`
> at a path that did not exist, so re-adding the probe changed nothing and the
> assertion held anyway. Only a **real** `pythonw.exe` beside a **real** `.exe`
> can tell "frozen returns itself" from "the probe happened to miss".

**The diagnosis, kept as written. It was bigger than OP-35 and probably worse.**

> **RE-MEASURED 2026-08-21 AFTER THE #243 MERGE, AND IT IS FOUR SITES, NOT TWO.**
> The first pass named `relaunch.py` alone. A sweep of every `sys.executable` in
> `scrapex/` found the same two bugs repeated at four of the five places that start
> a child process:
>
> **The five sites as they were before the fix.** The line numbers are the
> pre-fix ones and are kept as the record of what was measured; four of them no
> longer name what they named, which is why their pins were retired rather than
> re-aimed.
>
> | site (pre-fix) | what it starts | then | now |
> |---|---|---|---|
> | `relaunch.py:52` | the engine a relaunch brings back | broken | `enginelaunch.engine_argv` |
> | `relaunch.py:146` | the detached helper that does the relaunch | broken | `enginelaunch.engine_argv` |
> | `native.py:286` | the engine Chrome's native host starts | broken | `enginelaunch.engine_argv` |
> | `autostart.py:48` | the Startup entry | broken ×3 | `engine_command` + conditional `cd` |
> | `osschedule.py:65` | the Scheduled Task's interpreter | broken | `enginelaunch.runner` |
> | `nativehost.py:57` | Chrome's launcher | **CORRECT — the precedent** | unchanged |
>
> **THE FIX IS ALREADY WRITTEN, ONCE, IN THIS REPOSITORY.** `nativehost.py:57` is
> three lines and says exactly the right thing:
>
> ```python
> if getattr(sys, "frozen", False):        # the PyInstaller build: run ourselves
>     return sys.executable
> ```
>
> So this is not a design problem. It is one helper the other four never got, and
> the repair is to give them it rather than to write a fifth variation.
>
> **AND THE SECOND BUG AT EVERY SITE, which is quieter:**
> `interpreter.with_name("pythonw.exe")`. Beside `scrapex-engine.exe` there is no
> `pythonw.exe`, so `windowless.exists()` is always false and the console-hiding
> falls back to the visible executable. That one degrades rather than breaks — but
> it means a frozen autostart or Scheduled Task flashes a window on every tick,
> which is the exact thing both of those comments say they exist to prevent.
>
> **`autostart.py:48` IS BROKEN A THIRD WAY, and it is the worst of them:**
>
> ```
> cmd /c cd /d "{repo}" && "{runner}" -m scrapex.cli ui --port N >> engine.log
> ```
>
> `repo` is `Path(__file__).resolve().parent.parent`. Inside a one-file build that
> is the PyInstaller unpack directory under `%TEMP%`, **which is deleted when the
> process exits.** So a frozen install that turns on autostart writes a Startup
> entry pointing at a directory that will not exist at the next boot. `OP-34` is
> why nobody would ever see why.
 Not
reproduced against a running frozen engine — read from the code and stated as such,
because saying so is cheaper than a release to find out.

`scrapex/relaunch.py:52` and `:146` both build the child process the same way:

    [str(runner),      "-m", "scrapex.cli", "ui", ...]         # :52  _engine_command
    [str(interpreter), "-m", "scrapex.cli", "relaunch", ...]   # :146 spawn_helper

`interpreter` is `sys.executable`. Under PyInstaller **that is
`scrapex-engine.exe`**, and its bootloader does not honour `-m`: those become plain
arguments. So `engine_entry.main` receives

    ["-m", "scrapex.cli", "ui", "--port", "8000", "--no-open"]

strips the dash-arguments, finds `argv[0] == "scrapex.cli"`, does not recognise it,
and **returns `serve()`**. The engine asks to be replaced and a mute native host
arrives instead. `pythonw.exe` beside a frozen executable does not exist either, so
`_engine_command`'s windowless branch silently picks the exe.

Everything `tests/test_relaunch_log.py` and
`tests/test_the_engine_survives_being_killed.py` assert is true of the SOURCE tree,
where `sys.executable` really is a Python. The frozen case has never been exercised —
same shape as `OP-32`, where the guarded thing and the shipped thing were different
things.

**Next action:** make the two command builders frozen-aware (`sys.frozen` →
`[exe, "ui", ...]` with no `-m`), and have `OP-35`'s derived dispatch accept it. Then
one test per builder asserting the frozen shape, which needs no real binary — only a
patched `sys.frozen` and `sys.executable`.

### OP-37 · ~~`main` went red at 12:00Z today and stays red, which blocks the engine release~~ — FIXED 2026-08-21

> **CLOSED THE SAME DAY — AND TWICE, INDEPENDENTLY, WHICH IS THE INTERESTING PART.**
> He instructed *«ابدأ بـ OP-35»* (its number before the #243 merge renumbered it),
> and while this branch was writing the fix, [#243](https://github.com/muhammadbayoumi/ScrapeX/pull/243)
> landed **the identical one line** on `main` from another session. Two sessions
> reached the same repair without seeing each other, which is corroboration rather
> than waste — and it is not an invention either: **the sibling test in this same
> file's neighbour already uses the correct pattern for the same column.** `tests/test_a_crawl_says_what_it_saw.py:215` pins every row's
> `last_seen_at` with a bare `UPDATE` and *then* overrides the one it is about. The
> broken test pinned both sides of `last_seen_at` and only one side of
> `first_seen_at`. One line closes the gap.
>
> **AND THE FIX WAS PROVED NOT TO HAVE NEUTERED THE TEST**, which is the real risk
> when a red test goes green. Three mutations, three killed:
>
> | mutation | result |
> |---|---|
> | remove the new pin | **KILLED** — the bomb returns, so the fix is load-bearing |
> | `row_state`: `first_seen_at >= newest` → `>` (**production code**) | **KILLED** — the `new` rule is still guarded |
> | `row_state`: stop calling an unseen row `absent` (**production code**) | **KILLED** — the `absent` rule is still guarded |
>
> The two production mutations are the ones that matter: a test edited into
> passing would have survived them.
>
> **AND ONE CORRECTION TO #243'S ACCOUNT, per C5.** Its comment calls this a
> dependency on the TIME OF DAY — *"new for the whole afternoon and not at all in
> the morning"*. That is true of **2026-08-21 alone**. From the next day onward
> `now` is past `12:00:00Z` at every hour, so the test could never have passed
> again at any time of day. The distinction decides what a reader does: told it is
> time-of-day, they wait for the morning, and the morning never fixes it. The
> comment in the test now says so. All 40 tests in the file pass, and the class
> was swept — the other 13 files holding a hardcoded 2026 timestamp pass every
> value to `row_state()` explicitly, so no `now` is involved, and **no
> future-dated literal exists anywhere in `tests/`** that would arm the same bomb
> for a later date.

**The diagnosis, kept as written — the present tense below is that afternoon's.**
It was the most urgent entry in this file, because `OP-32`'s next action could not
be taken while it stood.

    FAILED tests/test_a_dataset_is_a_table_like_any_other.py::
           test_gone_and_new_are_measured_against_the_most_recent_crawl
    assert 3 == 1   # "and the one that first appeared is new"

**Reproduced on the untouched `main` checkout at `38a1e24`**, so it is not this PR's.

**IT IS A TIME BOMB AND IT HAS GONE OFF.** The test hardcodes the newest crawl at
`2026-08-21T12:00:00Z` (`tests/test_a_dataset_is_a_table_like_any_other.py:906`, and the row it
means to single out at `:909`) and
then sets **only the last row's** `first_seen_at` to the same stamp, expecting exactly
one `new` row. But the other rows' `first_seen_at` is whatever `stored()` wrote at
insertion — *now* — and `row_state` decides:

    if first_seen_at is not None and first_seen_at >= newest:
        return STATE_NEW

At 2026-08-21T13:28Z, `now >= 2026-08-21T12:00:00Z` for **every** row, so all three
are `new`. Proved by moving the stamp and nothing else:

| the stamp | result |
|---|---|
| `2026-08-21T12:00:00Z` as committed | **FAIL**, 3 new |
| `2027-08-21T12:00:00Z` | **pass** |

**AND IT DOES NOT HEAL OVERNIGHT.** `now` only increases, so the comparison is true
for ever from 12:00Z on 2026-08-21. This is not today's flake — **`main` is red from
now on.** It passed every run before 12:00Z, which is why #235 merged green.

**Why it blocks the release.** `.github/workflows/release-engine.yml` runs the whole
suite in *"The engine must pass its own tests before it is shipped"* **before** it
builds. So the release failed at that step whatever it was tagged, and `OP-32` — the
thing the owner actually asked for — could not ship until this was repaired. `R-18`
(merge it when it is green) was also unsatisfiable for every open pull request while
it stood.

**The repair, which preserves what the test means.** Its intent is *one* row first
appeared in the newest crawl and the others predate it. The `last_seen_at` lines two
above already pin both sides explicitly; `first_seen_at` pins only one. Pin the other
side too, rather than leaving it at insertion time:

    conn.execute("UPDATE generic_record SET first_seen_at = '2026-01-01T00:00:00Z'")
    conn.execute("UPDATE generic_record SET first_seen_at = '2026-08-21T12:00:00Z' "
                 " WHERE generic_record_id = ?", (ids[-1],))

**The class, and it is worth a `LESSONS` line if it recurs:** a test that compares a
literal timestamp against `now` is only asserting anything while `now` is on the right
side of it. Every such literal is a date on which the suite changes its mind.
### OP-38 · "Not detected" is what the panel says about an engine that is installed and refusing

**Status: OPEN.** The half of `OP-33` the #243 merge did not close, split out so it
is not filed as fixed with it.

An engine that refuses to start never binds a port. So `checkEngine` in
`extension/engine.js` gets a connection error, and
`extension/app.js:3424` reports:

    text: "Not detected"      detail: "The panel could not reach the Engine."

**That sentence is false in every case except one**, and it sends the reader to
reinstall software that is already installed. The engine knew exactly what was
wrong — *"This database was written by a later version (schema v8; this build reads
v6)"* — and there was no channel to carry it. Same for a locked database, a busy
port, a permissions fault, or a half-written config.

**The states are already distinguished where they CAN be**: `Not running`,
`Installed, not running`, `Check timed out` and `Incompatible` all exist and are
reasoned about in `engineStatusFromState`. The gap is only the case where nothing
answers at all — and it is the case a stuck user is in.

**The cheapest honest fix is not a protocol.** A refusal already knows how to write
a line; it just has nowhere durable to write it (`OP-34`). If a failed start left a
one-line reason where the panel could read it, "Not detected" could become "Installed,
but it stopped: …". Fixing `OP-34` and this entry are the same work.


### OP-39 · The update stops one step short: nothing replaces the running executable yet

**Status: OPEN by design, not by omission.** `REQ-29`'s engine half is built —
the engine reads the release feed, fetches the installer, verifies its SHA-256
and stages it. What it does not do is install it.

**Why it stops there, and why that is the honest place to stop.** Windows will
not let a running `.exe` be overwritten, so the swap is necessarily performed by
a **detached helper after this process exits**. Every part of that is testable
except the part that matters: whether a real frozen engine, replaced underneath
itself, comes back. A test that set `sys.frozen` and asserted a rename would
prove the plan and nothing about the outcome — and this repository has already
paid for the difference once, in `engine-v0.2.1`, where the guarded thing and the
shipped thing were different things.

**So the plan is data instead of code.** `update.plan_swap` returns the steps,
the file it would overwrite, the digest it verified, and whether it is possible
at all; `GET /api/update/plan` serves it. `R-36` bought an updater before code
signing existed, and what makes that acceptable is that every step is inspectable
before it happens — a plan nobody can read is the same trust problem in a new
place.

**The machinery it needs already exists and is already correct**, which is the
one piece of luck here: `scrapex/relaunch.py:spawn_helper` starts a detached
process that waits for a named pid to exit, for exactly this reason. **This is
why `OP-36` had to be fixed first** — before that, the helper a frozen engine
spawned was a silent native messaging host and would have waited for ever.

**Next action, and its precondition is now met.** This belonged after a release
rather than before one, and the release happened on 2026-08-22 (`OP-32`): a published
`engine-v0.3.0` is the first frozen artifact that can exercise any of this. So the
swap can now be implemented against a binary that exists rather than against
`sys.frozen` set by a test.

### OP-40 · His warehouse has moved ahead of `main` again — v9 now, and this is the third time

**Status: OPEN, and it is the pattern rather than the instance that matters.**

Measured while smoke-testing the update API against the live installation:

    RuntimeError: engine database is needs a newer scrapex: This database was
    written by a later version (schema v9; this build reads v8).

**The third time in one day.** It was v8-against-v6 this morning (`OP-33`, closed
by #243 merging migrations 0007/0008), and it is v9-against-v8 this afternoon —
so some other branch now holds migration `0009` and has run it against his real
warehouse.

**Why this is not just #243 again.** Each instance closes by merging; the class
does not. A session that runs unmerged migration code against the owner's only
warehouse leaves `main` unable to open it, which means **the shipped engine
cannot open it either** — and `R-23` says a warehouse is per installation while
`R-24` says a database is upgraded, never replaced. Both hold. What is missing is
any rule about which code may write to the live one.

**It also makes the updater more valuable rather than less:** the owner's engine
being older than his own database is precisely the situation an Update button
exists for. Today the only route is a merge and a release.

**A question for him, not a decision to take:** should a session be allowed to
run an unmerged migration against the live warehouse at all? `SCRAPEX_DATA_ROOT`
already makes a private one free, and `R-24`'s repair path (`carry_over`) exists.
Recorded as `Q-15`.


### OP-42 · ~~A generic dataset card offers no actions at all, and one of the six would work~~ — FIXED 2026-08-22, and he asked for it before the fix was scheduled

**Status: CLOSED. Fixed the same day it was recorded, because he read the same
screenshot and asked for it in his own words: «ال 3 نقاط لا تظهر فى كارد مقاول» —
captured as `REQ-36`.**

**What shipped, and it is not the narrow fix this entry proposed.** The entry
suggested "a per-entry predicate rather than gating the whole menu on `kind`". A
per-entry predicate is still a hand-written claim about somebody else's routing,
which is the exact thing that rotted here — the blanket hide was right when it was
written and wrong ten days later, and nothing noticed. So each action now declares
**the engine route it drives** and **a proof of what that route does with a dataset
key**, and `tests/test_a_dataset_card_offers_what_works.py` CALLS every one of them
against a real approved dataset. Both directions are asserted: an action that is
offered must answer 2xx and carry rows, and an action that is withheld must be
proven unable. The engine's behaviour decides; the panel's list is a mirror that
cannot silently stop matching.

**Measured, and this is the whole answer to "which of the six":**

| action | route it drives | with a dataset key | offered? |
|---|---|---|---|
| `table` | `GET /api/table/{key}` | **200**, 4 rows, 25 columns | **yes** |
| `sheet` | `GET /api/export/{key}` | 404 `no source called 'contractors'` | no |
| `update` | `POST /api/jobs` | 404 `unknown source_key` | no |
| `pause` | `POST /api/sources/{key}/active` | 404 `unknown source` | no |
| `settings` | `GET /sources/{key}` | 404 — **and the route does not exist for anyone**, see `OP-51` | no |
| `changes` | `GET /source/{key}` | 200, and **no changes section on the page** | no |

One live row, no greyed rows — which is his other ruling of the same day, recorded
under `REQ-36`: a menu of dead entries is the "button that cannot work" this menu's
own comment already rejected.

**ONE ROW TODAY IS NOT A CONTRADICTION OF `R-47`, which arrived while this was open.**
That ruling gives the muqawil card **two crawl options**, and this menu offers none —
because `POST /api/jobs` answers 404 for a dataset key, measured. The two fit together
rather than fighting: `R-47` says what the card must eventually offer, and the
mechanism built here is what makes adding it safe. A crawl entry cannot be added
without declaring the route it drives and a proof of what that route does with a
dataset key, and the guard fails until the proof holds — so the day a panel path to a
dataset crawl exists, the entry can be added and *cannot* be added before. That is the
opposite failure mode from the one this entry is about, and it is guarded in the same
place.

**And the hole this entry predicted was real.** It said the guard "currently points
the other way" because the harness stub had no dataset-kind source. Adding one made
`test_dataset_action_opens_the_workspace_directly` fail immediately — 2 triggers
against 3 cards — so the false rule was executed for the first time on 2026-08-22.
The stub carries a dataset permanently now, which is what stops it recurring, and
it surfaced two more places the same way: `OP-51` and `OP-52`.

**The original entry is kept below in full, because its diagnosis is what the fix
was built on.**

**Status when written: OPEN. Found 2026-08-22, in the same screenshots as the
double-⋮ defect, and it is a SEPARATE cause from it.**

**He asked about one thing in that screenshot; this is the other thing in it.** His
question was «لماذا تظهر مرتين» — a `⋮` appearing twice, a stacking-context bug,
fixed and recorded as `REQ-30`. Reading the same picture to reproduce it turned up
a second fact he did not raise: `aramco.com` and `spark-eshop.com` carry a `⋮` and
the two `muqawil.org` cards carry none. So it belongs here and not in
[REQUESTS.md](REQUESTS.md) — we found it.

**That absence is deliberate, and it is written down in both halves.**
`sourceMenu` returned an empty string for a dataset — the line is gone, and what
stands where it stood is the filter that replaced it
([extension/app.js:4755](../extension/app.js#L4755)) — and the engine stamps the
marker it keys on precisely so the panel can do that — `"kind": "dataset"` in
`_dataset_rows`, whose docstring says *"the row menu offers Update, Wipe and
Rename, and every one of those is a price-path action that would answer 400 or
worse for a dataset"* ([scrapex/webui/app.py:665](../scrapex/webui/app.py#L665)).
It was the right call for five of the six entries and it is still right for them:
`update`, `pause` and `settings` post to routes that read the manifest, and
`/api/export/{key}` validates the key against `manifest.sources` and answers 404
for anything else ([scrapex/webui/app.py:2994](../scrapex/webui/app.py#L2994)).

**But `Open the data table` would work, and it was built after the blanket
hide.** `data.html?source=KEY` fetches `/api/table/{key}`, and that route looks
the key up in the dataset catalogue FIRST — *"a generic dataset is a table like
any other table"* ([scrapex/webui/app.py:1176](../scrapex/webui/app.py#L1176)) —
so `/api/table/contractors` serves the directory in full. The panel hides the one
entry that works on the marker that was introduced for the five that do not.

**Measured, not assumed** — the panel driven with two `kind: "dataset"` rows
shaped exactly as `_dataset_rows` builds them:

| card | `.split-button-trigger` |
|---|---|
| `LONG_AR` | 1 |
| `SHORT` | 1 |
| `contractors` | 0 |
| `contractor_profiles` | 0 |

**And the guard for this is not just missing, it currently points the other
way.** `tests/test_panel_dom.py::test_dataset_action_opens_the_workspace_directly`
asserts *"every dataset card must carry exactly one actions menu"*, which holds
only because `tools/panel_harness.py`'s stub contains no dataset-kind source at
all. Add one honestly and that assertion fails — so the rule `sourceMenu`
implements has never been executed by any test. Whichever way this is decided,
the stub needs a dataset row and that assertion needs to be per-kind.

**The narrow fix** is to give `SOURCE_ACTIONS` a per-entry predicate rather than
gating the whole menu on `kind`, and to show a dataset the entries that work.
Deliberately not done inside the double-⋮ fix: that one is a CSS stacking bug
with a hit test to prove it, and this one changes what the panel offers, which is
the owner's call under `R-32`'s reading of what a dataset is.

### OP-46 · The custom `<select>` is built twice, and `focusOption` is character-identical in both

**Status: OPEN. Found 2026-08-22 by a DRY review of `#252`.** That PR's own comment
names `.sx-select-list`, `.account-menu` and `.finance-converter-options` as the
overlay-layer precedent it was following. Reading the three together to check the
claim turned up something the PR did not raise: two of them are not dropdowns that
merely look alike. They are **one component written twice**.

**Nothing is broken today, and this entry says so before anything else.** Both
dropdowns work, both are keyboard-operable, no screenshot produced this and no user
saw it. What is duplicated is the *state machine*, and the cost is that every future
fix to it has two homes.

**The two implementations**, each mirroring a native `<select>` and replacing its
popup:

| | finance converter | run mode |
|---|---|---|
| entry point | `setupFinanceConverterSelect` ([extension/app.js:964](../extension/app.js#L964)) | `setupRunModeSelect` ([extension/app.js:2016](../extension/app.js#L2016)) |
| `close({restoreFocus})` | adds `hidden`, `aria-expanded=false`, removes `is-open`, restores focus | same four steps, same order |
| `open()` | removes `hidden`, `aria-expanded=true`, adds `is-open`, `requestAnimationFrame` then focuses selected-or-first with `preventScroll` | same five steps, same order |
| `choose(value)` | validates against `select.options`, assigns, dispatches bubbling `change`, closes with `restoreFocus: true` | same four steps, same order |
| `focusOption(direction)` | **identical** — see below | **identical** |

**`focusOption` is the same function, measured rather than eyeballed.** Normalise
the candidate-list identifier (`choices` / `enabled`) and the one expression that
builds that list, and the two bodies are **character-identical** — the guard, the
`indexOf(document.activeElement)`, the `aria-selected` lookup, the
`current >= 0 ? current : Math.max(selected, 0)` fallback and the
`(start + direction + n) % n` wrap:

```
function focusOption(direction = 1) {const OPTS = BUTTONS;if (!OPTS.length) return;
const current = OPTS.indexOf(document.activeElement);const selected = OPTS.findIndex(
(button) => button.getAttribute("aria-selected") === "true");const start =
current >= 0 ? current : Math.max(selected, 0);OPTS[(start + direction + OPTS.length)
% OPTS.length].focus({preventScroll: true});}
```

**And the CSS is the same surface twice**, counted by declaration after stripping
comments:

| pair | identical | differ |
|---|---|---|
| `.sx-select-list` (14) vs `.finance-converter-options` (15) | **10** | `max-height`, the `inset` shorthand vs `inset-block`/`inset-inline`, one animation, two scrollbar properties |
| `.sx-select-option` (13) vs `.finance-converter-option` (16) | **10** | `gap`, `min-height`, `border-radius`, three font properties |

Both popovers share `position`, `z-index: var(--z-overlay)`, `display: grid`,
`gap: 2px`, `padding`, `overflow-y`, `border`, `border-radius`, `background` and
`box-shadow` — the same ten. This is the shape `UI-2` already ruled on: `.icon-tile`
was extracted at **six** identical declarations across three sheets, and this is ten
across two blocks of one sheet.

**What looks like drift and is NOT — the part that decides the severity.** A first
reading of this made it look as though the two copies had already diverged in
accessibility. They have not, and the difference is requirement-driven:

* Run mode disables options **individually**, because which run modes are on offer
  depends on the selection — `for (const option of select.options) option.disabled =
  !allow[option.value]` ([extension/app.js:2181](../extension/app.js#L2181)). Its
  `focusOption` filters disabled candidates because it genuinely has some.
* The finance converter disables **the whole control** when there are no stored
  rates — `select.disabled = !state.financeRates.length`
  ([extension/app.js:1149](../extension/app.js#L1149)) — and mirrors that onto the
  trigger inside `sync()`. It never has a disabled option, so it has nothing to
  filter.
* Type-ahead exists only on the finance side, and a currency list needs it where
  four run modes do not.

So this is **not** a case of one copy having been fixed and the other missed. It is
a shared core with three honest local differences, which is why it is filed here as
cost rather than as a defect.

**One difference is accidental, and it is the whole argument in miniature.** Run
mode's `close()` opens with an early return when the list is already hidden; the
finance copy has no such guard. Nobody decided that. It is what a duplicated state
machine does over time, and it is the second edit — not this one — that will hurt.

**The narrow fix, and it is deliberately narrow.** Extract only the shared state
machine — `open`, `close`, `focusOption`, `choose` — to `design/select.js`, on the
exact precedent the repository already set for this class of problem:
`design/split-button.js` exists because *"the dataset Export control and the
Activity panel's log control cannot become two implementations"*
([tools/sync_design_assets.py:25-26](../tools/sync_design_assets.py#L25)), it is
distributed to both surfaces through `ASSETS`, and the copies are held byte-equal by
`sync(check=True)` in
[tests/test_design_system.py:16](../tests/test_design_system.py#L16). The
candidate-set predicate and the optional type-ahead are passed in.

**Do not merge `sync()`.** Rendering the options genuinely differs — one writes a
`<span>` plus a check icon, the other a label and a tick with different tokens — and
that is the part that should stay local. Nor should `.account-menu` or
`.split-button-options` be folded into the CSS half: their surfaces really are
different (`--line` / `--surface-raised` and `--line-strong` / `--surface` /
`--radius` against the two dropdowns' `--outline-variant` /
`--surface-container-high` / `--radius-lg`). Pulling all four together is the wrong
abstraction that `UI-2`'s closing rule warns about.

**Proof it must carry**: `tools/style_snapshot.py` across both surfaces, with no
computed style changed anywhere — the same evidence `UI-2` used, and the same reason
screenshots cannot supply it.

**Why it is not done in this pull request.** Three sessions were open on 2026-08-22
and one of them is editing `extension/app.js` and `extension/app.css`; a behaviour
extraction across those two files from a secondary session is how the register
collisions of 2026-08-21 happened. It also adds a **third** shared JS module to a
surface the owner has opinions about, which is his call and not a reviewer's.

**Its citations are deliberately NOT in `PINNED`.** Every line above points into
`extension/app.js`, which this branch does not touch and another session was editing
when this was written. `main` went red on 2026-08-22 from exactly that shape, and the
account is recorded beside the row it broke
([tests/test_the_documents_cite_what_they_claim.py:209](../tests/test_the_documents_cite_what_they_claim.py#L209)):
`#252` measured a line in `app.py` correctly on its own base, `#251` landed first and
added fifteen lines above it, and because **no file was changed by both**, git found
nothing to conflict on and neither suite could see the other. **That row has since moved
a third time — 2710 → 2725 → 2787 — which is the argument for this paragraph rather than
against it: the line moves whenever anything lands above it, so a pin is a commitment to
re-derive it on every rebase.** "Check whether the
files overlap" is the reflex that fails here.

Tier 1 still guards these seven citations, and that was proved rather than assumed —
the guard's own `CITATION` pattern extracts all seven from this entry and every one
resolves to a real file and a real line. Pin them when `extension/app.js` is quiet,
and pin `setupFinanceConverterSelect` and `setupRunModeSelect` first.
### OP-47 · The shared split button documents its stacking trap instead of owning it

**Status: OPEN — recording, not fixing. Found 2026-08-22 by the DRY review of `#252`,**
the pull request that fixed the trap for `REQ-30`. It fixed it in the right place for
that screen and in the wrong place for the component.

**CITED BY SELECTOR, NOT BY LINE, ON PURPOSE.** `extension/app.css` and
`extension/app.js` were under concurrent edit by another session on 2026-08-22 — it was
giving the `dataset`-kind cards a `⋮` at all (`OP-42`'s tail) and restyling the card's
trigger at his request. **That request is deliberately not quoted or numbered here**:
the session doing the work is capturing it, and a second copy on the board is the drift
`REQUESTS.md` exists to prevent. Every rule below is named so a reader who finds
different text nearby knows the neighbourhood moved rather than assuming this entry
rotted. The stable files carry line numbers.

**AND THIS ENTRY CARRIES ITS OWN CORRECTION.** The request above was filed as `REQ-36`
on another branch while this was being written, so: **cite `REQ-36` once it is on
`main`.** `REQ-30` is its root and is the truthful citation until then — the trigger
being restyled is the same control whose menu `REQ-30` was about. Swapping it is a
one-word edit that needs no rediscovery, which is the point of writing the instruction
down rather than leaving it for whoever picks this up.

**What `#252` did.** `.dataset-card > .split-button` in `extension/app.css` carried
`z-index: 1`, which made every card's wrapper a stacking context and spent the open
menu's own `z-index: 120` inside it. The fix adds
`.dataset-card > .split-button:has(.split-button-menu[open])` lifting the wrapper to
`var(--z-overlay)` while open — correct, measured, and guarded by a hit test.

**Why the rule belongs one level up.** The `120` is the shared component's
([design/components.css:1429](../design/components.css#L1429)), so the knowledge *"this
menu must not be painted over"* is the component's too. The component's own comment,
ten lines under that declaration, states the repository's rule for exactly this
situation: *"When two independent consumers break the same way, the shared rule is the
defect rather than the consumers"*
([design/components.css:1439](../design/components.css#L1439)).

**And the prose now tells the next consumer to write the selector again.**
`docs/UI-KIT.md` records the trap as placement guidance — *"where a layer really is
needed, raise it to `var(--z-overlay)` **only while the menu is open**
(`:has(.split-button-menu[open])`)"* ([docs/UI-KIT.md:202](UI-KIT.md#L202)). That is a
documented invitation to a second copy, and `webui.css` is already the first:
`.source-filter-menu[open]{z-index:var(--z-overlay)}`
([scrapex/webui/static/webui.css:142](../scrapex/webui/static/webui.css#L142)),
asserted as literal text at
[tests/test_workspace.py:274](../tests/test_workspace.py#L274).

**NOTHING ELSE IS BROKEN — measured at `451468d`, and the measurement is sharper than
"no other consumer has a z-index".** The defect needs two things: a stacking context on
the wrapper **and** a later sibling inside it to lose the tie to. Only one consumer
supplies the second, because only one is *repeated*:

| consumer | how it is wired | repeated? |
|---|---|---|
| dataset cards | `querySelectorAll(".dataset-card .split-button")` in `extension/app.js` | **yes — the broken one** |
| Activity log | `$("activity").querySelector(".split-button")` in `extension/app.js` | no, singular |
| Manage account danger menu | `$("drive-disconnect")`, markup at [extension/app.html:1347](../extension/app.html#L1347) | no, singular |
| source page export | one control in `#grid-toolbar` ([scrapex/webui/templates/source.html:291](../scrapex/webui/templates/source.html#L291)), wired by [scrapex/webui/static/grid.js:3118](../scrapex/webui/static/grid.js#L3118) | no, singular |
| gallery example | one control ([design/gallery.html:379](../design/gallery.html#L379)) | not a product surface |
| grid harness fixture | [tools/grid_harness.py:68](../tools/grid_harness.py#L68) | not a product surface |

**THE FIRST VERSION OF THAT TABLE WAS WRONG TWICE, corrected 2026-08-22 when the
re-measurement below came due. Both errors were in the instrument, not the conclusion:**

* **It missed the Manage account danger menu entirely.** The search was
  `class="split-button"` — an exact match including the closing quote — and that markup
  reads `class="split-button danger"`. A multi-class attribute is invisible to it. The
  shared component's own comment *names* this consumer ("Manage account's danger menu")
  and the omission still survived reading that comment.
* **It listed the source page's Export control twice**, once as "grid toolbar" and once
  as "source page export". `grid.js`'s `toolbar` is `document.getElementById("grid-toolbar")`,
  which is the `<div id="grid-toolbar">` enclosing that very control. One control, two
  rows — so the table claimed five consumers where there were four product surfaces.

**Neither error changed the conclusion**, which is the only reason this is a correction
and not a retraction: every consumer except the dataset card template is still
singular, so only that one can lose a tie to a later sibling. **But a table that was
wrong twice is exactly what "measured at a commit" is supposed to protect against, and
it did not, because re-measuring was left to a person remembering.**

Checked at the same commit: `.toolbar` carries no `z-index`, there is no rule for
`#activity .split-button`, and neither `.dataset-card` nor `#datasets` carries a
`transform`, `filter`, `opacity`, `contain`, `isolation` or `will-change` that would
build a context another way. **This is future safety, not a live defect.**

**RE-TAKEN 2026-08-22 at `d10e974`, after `fix/a-dataset-card-gets-the-menu-it-can-use`
landed as `#258` — this is the discharge of that instruction, not a fresh promise.**
The instruction it replaces said the table was a measurement at `451468d` and had to be
re-taken; it was, and the table above carries the result plus the two errors the
re-measurement exposed.

**The conclusion held and only the number moved, as predicted.** `#258` gave the
`dataset`-kind cards the menu entries that work — `OP-42`'s tail — so the stub goes from
3 cards / 2 triggers to 3 cards / 3 triggers. It was card-local: `.dataset-card`'s block
and `sourceMenu`, with the shared component and its generated copies untouched and no
consumer added anywhere new. The cards given triggers are still `.dataset-card`, matched
by the same `querySelectorAll`, so the repeated-consumer fact is **stronger** than when
it was written, not weaker.

**Verified at the same commit** that all four of `OP-46`'s `extension/app.js` citations
still name their symbols after `#258` moved that file, and that no open pull request
touches `extension/app.js` — which is what let the two `PINNED` rows this entry's
neighbour was waiting on finally be added.

**Still true, and now the standing instruction:** any future branch that adds a consumer
or lifts a different wrapper invalidates the table rather than just the count. The
`querySelectorAll`-versus-`querySelector` distinction is the thing to re-derive, and it
must be searched on the CLASS TOKEN rather than on `class="split-button"`, which is the
mistake recorded above.

**The risk is specific, and that session makes it likelier rather than moot.** The
defect is *created* by fixing consumers instead of the component, and another consumer
is being fixed right now. The next list of anything carrying a per-row actions menu
reproduces it, because the component still ships the trap and the guard is bound to one
screen: `test_an_open_source_menu_is_not_overpainted_by_the_next_cards_button` reads
`#datasets .dataset-card .split-button-trigger`, so it would stay green while a new
repeated consumer was broken.

**The narrow fix.** Move the conditional lift into the shared sheet, beside the
declaration whose knowledge it is:

```css
.split-button:has(.split-button-menu[open]) { z-index: var(--z-overlay); }
```

then `python tools/sync_design_assets.py`. It applies — `.split-button` is already
`position: relative` ([design/components.css:1352](../design/components.css#L1352)) —
and it is inert unless a menu is open. The card keeps its own `z-index: 1`, which is
local placement, not this rule.

**The objection on record does not transfer, and that needs saying plainly.**
`extension/app.css` says *"Changing the shared rule would move the Activity log's menu,
which is not broken"*, and a reader may take that as a decision against touching the
shared sheet. It belongs to the block above it — the **positioning** of the wrapper in
the card's corner — not to the layer. No ruling covers sharing the z-index rule.

**Proof it must carry:** `tools/style_snapshot.py` over both surfaces, with no computed
style changed except where a menu is open, and the hit test generalised off `#datasets`
so it covers whatever the second repeated consumer turns out to be.

**Sequencing:** build this **after** `OP-48` and after the card session lands. It edits
a component five surfaces consume, and doing that while one of them is being restyled is
how two correct branches produce one broken screen.

### OP-48 · The layer scale is transcribed by hand on both sides of the boundary, and a comment is all that holds it equal

**Status: OPEN — recording, not fixing. Found 2026-08-22 by the DRY review of `#252`.**
Of the three findings that review produced this is the one to build first: the fix is a
three-value substitution that cannot change a pixel, and the thing it removes is tied to
a defect he photographed the same day.

**THE ARGUMENT, BEFORE ANY INDIVIDUAL VIOLATION.** The extension and the engine each
transcribe the layer scale **by hand**, and the two sheets share nothing but
`tokens.css`. So changing a layer is not editing a token — it is editing a token and then
remembering that two unrelated stylesheets also spell its value out, one of them on the
other side of a boundary the two surfaces cannot import across. That is the defect. The
three rules below are only how it shows today, and a guard scoped to either surface alone
would go green with the other still wrong — `OP-18`'s shape exactly, and the same failure
as a parameterised test that matches nothing: green because it looked in one place.

**Cited by selector for `extension/app.css`, by line elsewhere** — that file was under
concurrent edit on 2026-08-22 and every rule below it shifts when the card block above
it changes. See `OP-47` for the same reason at more length.

**The scale is three tokens** — `--z-sticky: 10`, `--z-overlay: 20`, `--z-modal: 30`
([design/tokens.css:128](../design/tokens.css#L128)) — and **three rules across two
sheets** write a token's value as a raw number instead of reading it. This is the
complete set, measured at `451468d` by matching a bare integer equal to any of the three:

| rule | sheet | writes | which is exactly |
|---|---|---|---|
| `nav.side-rail` | `extension/app.css` | `z-index: 30` | `--z-modal` |
| `.workspace-menu-backdrop` | `extension/app.css` | `z-index: 20` | `--z-overlay` |
| `.workspace-menu-button` | [scrapex/webui/static/webui.css:81](../scrapex/webui/static/webui.css#L81) | `z-index:10` | `--z-sticky` |

**How the third row was found is part of the finding.** The static guard below was first
written scoped to `extension/app.css`. Checking whether that scope was the whole set —
rather than assuming it — produced `.workspace-menu-button` on the engine's side. The
scope was the bug, not the count.

**`.modal-veil` already depends on the first equality, and its own comment says so.** It
uses `z-index: calc(var(--z-modal) + 10)` and explains why: *"--z-modal is 30 and the
side rail is also 30 (see .side-rail above), so the token as it stands ties with the
thing this has to cover and the winner would be decided by source order. Correcting the
token is a design-system decision, not this screen's."*

That comment is an accurate diagnosis and a deferral, and it is also the whole problem:
**a comment is not a constraint.** The veil is modal — it exists so a question about
revoking a grant cannot be navigated away from — and its correctness rests on a number
in a different rule 1,100 lines away staying equal to a token. Move either and the veil
silently stops outranking the rail. Nothing goes red.

**The concrete consequence, and it lands on the bug he just reported.** Lower
`--z-overlay` below 20 — an ordinary design-system decision — and
`.workspace-menu-backdrop`'s raw `20` outranks **every popover that reads the token**:
`.sx-select-list`, `.account-menu`, `.finance-converter-options`, and the
`.dataset-card > .split-button:has(.split-button-menu[open])` rule that `#252` added
hours earlier. The drawer's backdrop would paint over the very menu whose overpainting
he photographed and asked «لماذا تظهر مرتين» about — `REQ-30`, fixed that same day. One
token edit, and the fix is undone from a file that never mentions it.

**Nothing catches any of this, and that is a finding in its own right.** The repository
has **no test that reads a z-index**. The single guard that touches the subject asserts
the literal *text* of one rule —
`assert ".source-filter-menu[open]{z-index:var(--z-overlay)}" in styles`
([tests/test_workspace.py:274](../tests/test_workspace.py#L274)) — which proves that one
line is spelled that way and nothing about layer order anywhere else. The most recent UI
defect he reported was a stacking bug, and `#252`'s own lesson is that reading a z-index
back would have passed on the broken build.

**So what a guard has to assert is order, not numbers.** Two shapes, and **the static
one is the more valuable** — it fires at review time, where the behavioural one can only
fire after a regression has been written:

* **Static, and the one to build:** **no stylesheet in the repository** may write a bare
  integer equal to the value of a layer token — it must read the token. Repo-wide, not
  `extension/app.css` alone: scoping it to the panel would have missed
  `.workspace-menu-button` in `webui.css`, which is how the third row of the table above
  was found. That is exactly the rule `docs/LESSONS.md` now states in prose (*"The
  extension's layers are three tokens …; a fourth number invented at a call site is the
  next instance of this bug"*, [docs/LESSONS.md:831](LESSONS.md#L831)) and nothing
  enforces. It is also cheap: the three substitutions below are the whole of today's
  violation set, so the guard goes green the moment they land.
* **Behavioural, for `.modal-veil`:** open the confirmation and hit-test a point over the
  side rail rather than reading a z-index back, the way
  `test_an_open_source_menu_is_not_overpainted_by_the_next_cards_button` does.

**And that second bullet is the same lesson twice, which is the point of writing it
here.** `#252`'s guard learned it the hard way: an assertion on the computed z-index
**passed on the broken build**, because the broken build's number was already large.
`.modal-veil` would fail the same way — its `calc(var(--z-modal) + 10)` reads back as a
perfectly correct 40 whether or not the rail it must cover has moved. One instance is a
trick; two make it the practice for this codebase. **Hit-test what is in front, because
that is the question a person is asking.**

**The same file breaks the three-token rule in four more places, and those are NOT this
entry.** `.workspace-menu` invents `z-index: 25` between overlay and modal;
`.split-button-options` uses `120` ([design/components.css:1429](../design/components.css#L1429));
`.grid-feature-popover` uses `100` and `.column-chooser-backdrop` `10020`
([scrapex/webui/static/grid-theme.css:663](../scrapex/webui/static/grid-theme.css#L663),
[scrapex/webui/static/grid-theme.css:311](../scrapex/webui/static/grid-theme.css#L311)).
Those are numbers the scale has no name for — renumbering them changes paint order and is
a design-system decision, which is the call `.modal-veil`'s comment already declined to
make on its own. **Recorded here, deliberately not folded in.**

**The narrow fix, and it is provably inert.** Substitute only the three values that are
already exactly equal to a token: `nav.side-rail` → `var(--z-modal)`,
`.workspace-menu-backdrop` → `var(--z-overlay)`, `.workspace-menu-button` →
`var(--z-sticky)`. Same numbers, so no computed style changes — verified with
`tools/style_snapshot.py` across both surfaces, the same evidence `UI-2` used. Then the
equality `.modal-veil` depends on is expressed instead of commented, and lowering
`--z-overlay` moves the backdrop *with* the popovers instead of past them.

**Why it is not done in this pull request.** Two of the three lines are in
`extension/app.css`, which another session was editing on 2026-08-22 on the owner's
instruction. The change is three lines and behaviour-neutral; it should land as its own
change once that file is quiet, together with the static guard above so the fix arrives
with the thing that keeps it. It does **not** need to wait for `OP-47`.
### OP-53 · Eleven price-path columns are registered against the contractor directory

**Status: FIXED 2026-08-22 in code; the eleven rows are still on disk — see `OP-58`.**

Measured read-only against the live warehouse, not reasoned about:

```
dataset_field WHERE source_key = 'contractors'   ->  11 rows
display_method · price · minimum_quantity · quantity_increment · stock_quantity
tax · category_leaf · category_leaf_ar · price_changed_on · last_confirmed_on
curation
```

**Not one of the directory's own 28 fields is among them**, and
`contractor_profiles` has none at all — nobody ever opened its chooser.

**The cause is a missing branch, and the endpoint wrote its own mistake down.**
`/api/fields/{key}` had no dataset path, so a dataset key fell through to the price
path and asked `column_presence` — *"which BROWSE columns does this source
populate"* — about a contractor directory. `ensure_fields` is additive by design,
so **merely opening Choose-Columns registered them permanently.**

Fixed by giving `/api/fields` the catalogue-first order `/api/table` already had,
and by listing a dataset's fields by intersection with its own schema so rows
already written go inert. `dataset_schema_fields` now has one reader instead of
two copies of the same join — the second copy is what caused this.

### OP-54 · Choose-Columns was a silent no-op on every dataset table

**Status: FIXED 2026-08-22.**

`dataset_table_payload` built `columns` from `field_definition` via
`schema_version_field` and **never read `dataset_field`**. So hiding a column on a
contractor table wrote `is_hidden = 1` and changed nothing on screen; a rename was
stored and the heading kept the old text; a reorder was saved and ignored.

**This is the defect `extension/datatable.js` already warns about in its own
comment** — *"dragging a column saved, reloaded the page, and changed nothing on
screen because the grid was reading its own copy"* — arriving from the other
direction, in the file that comment was written to protect.

**Worse than absent, and that is why it was fixed before anything was measured on
top of it.** A control that offers the wrong options and then discards the answer
teaches the owner that the feature is broken, and `R-45` rests on this exact
mechanism working: a hidden column is not lost but MOVED, into the row's card.
`moved_to_details` is now populated for a dataset for the first time.

### OP-55 · Server capabilities on the engine's page that nothing can reach

**Status: OPEN — and the action is "do not port", not "fix".**

Found while censusing `/source/{key}` for `REQ-07`. The page's server side still
supports a global search term, an availability filter, server-side sort links and
server-side pagination. The grid replaced all four in the browser, and nothing in
the current template reaches them.

**Why it matters now:** a port that copies the page copies dead code into a second
place, and the extension is the place we would then have to keep it working in.
Named here so step 4 of the plan carries the working half only.

### OP-56 · The panel prints "bilingual" for every source, because `{}` is truthy

**Status: OPEN. One line, and its test asserts a shape the server never sends.**

`extension/datatable.js`'s `summarise` does `if (payload?.bilingual) parts.push("bilingual")`.
The engine sends `bilingual` as an **object** of AR→EN pairs — `reports.table_payload`
and `dataset_table_payload` both build a dict — and an empty object is truthy in
JavaScript. So a source with no Arabic column at all still reads *"N rows · bilingual"*.

**And the guard cannot see it**, because `datatable.test.mjs` sets
`bilingual: false` in its payload and asserts on `bilingual: true` — booleans,
which is not what either producer returns. The test is green about a shape that
does not exist.

Fix with the feature, in step 1 of the plan: the check becomes
`Object.keys(payload.bilingual || {}).length`, and the fixture starts carrying a
real pair dict.

### OP-57 · The extension's data table is keyed on a column no dataset row has

**Status: OPEN. Fix it with the port, not before.**

`extension/data.js` builds Tabulator with `index: "offer_id"`. A dataset row has
no `offer_id` — `dataset_table_payload` never emits one, and the identity is
`generic_record_id` — so for every contractor row the index is `undefined`.
Tabulator tolerates it for drawing, which is why nothing has reported it, but
`getRow`, `updateData` and selection-by-index cannot work on a dataset. It is
therefore a live blocker for the record card in step 3 rather than a cosmetic
issue.

### OP-58 · Whether to delete the eleven rows — HIS gate, not ours

**Status: OPEN — awaiting the owner. Do not delete them without his word.**

`OP-53`'s code fix makes the eleven rows inert; it does not remove them. Removing
them is a `DELETE` against his warehouse, and `COMPATIBILITY.md` is explicit that
*"Destructive or irreversible migration"* requires programmer approval, and that
old data is *"never rewritten merely to make an internal model look cleaner"*.

**The safe version is narrow and provable:** delete only `dataset_field` rows whose
`field_key` is absent from that dataset's own `field_definition` set. That cannot
touch a products source and cannot touch a field the directory publishes.

**The argument for leaving them:** they are invisible now, and a migration that
deletes rows is a class of change this repository has been careful about.
**The argument for deleting them:** they will resurface the moment anyone removes
the intersection filter, which is a trap for a future session.

Recorded rather than defaulted, per `R-02`.

### OP-59 · `HANDOFF-resume-the-migration.md` sits outside the citation guard, and two of its citations are stale

**Status: OPEN.**

`tests/test_the_documents_cite_what_they_claim.py` checks the eight documents in
`CLAUDE.md`'s map. `docs/HANDOFF-resume-the-migration.md` is not among them, and
it is the living state of Track 1 — the file a session picking up the console
migration is told to read.

**Two citations in it are wrong at `4522158`.** It puts `loadSourceColumns` at
line 1579 of `extension/app.js` and `saveSourceColumns` at 1618; they are at 1594
and 1633. `STATE.md` carries the same pair correctly, which is how the drift was
caught — two documents citing one symbol at different lines.

**Those four numbers are deliberately NOT written in the `path:line` form.**
`extension/app.js` was being rewritten by `#258` when this was written, so a real
citation here would have become a red build the moment that merged —
`ORCHESTRATION.md` §4 — and writing this bug report in the very form the bug
describes would have been a poor joke. **`#258` has since merged at `d10e974` and
both symbols happened to survive at 1594 and 1633**, which is luck and not
stability. Re-derive them rather than trusting them.

**AND THE LUCK RAN OUT ONE PULL REQUEST LATER, which is worth adding rather than
editing the numbers above away.** The branch that added `scrapex/provenance.py`
inserted lines into `extension/app.js` above both symbols: they are at **1602 and
1641** on that branch. The paragraph above is still true *at `4522158`*, and it says
so — that scoping is the only reason it did not simply become wrong. It is also the
best illustration this register has of why the numbers were kept out of `path:line`
form: no guard could have told you they had moved, because no guard can see a line
number written as prose.

**The interesting part is that both citations still point INSIDE the file**, so
Tier 1 would have passed them even if the file were guarded; only the `PINNED`
table catches a citation that moved off its symbol. #256 has since added a check
that a cited line is not blank, which found three more.

**Two options, and they are not equivalent.** Adding the handoff to `DOCUMENTS`
guards it and immediately turns the build red until the two lines are fixed —
which is the point. Fixing the two lines without guarding the file leaves the next
drift silent. The first is recommended.


### OP-51 · Two of the six source-menu entries lead nowhere, and not only for datasets

**Status: OPEN. Measured 2026-08-22 while proving which actions a dataset card may
offer for `REQ-36` — these two are broken for PRICE sources too, which is why they
are here and not folded into `OP-42`.**

Every entry of `SOURCE_ACTIONS` was called against a running engine. Four behave.
Two do not, and neither failure has anything to do with datasets:

| entry | what it opens | what is there |
|---|---|---|
| **Source settings** | `/sources/{key}` | **no such route exists.** Measured: `[p for p in app.routes if p.startswith("/sources")]` is empty, and the request answers `404 Not Found` for a price key and a dataset key alike |
| **Recent changes** | `/source/{key}#changes` | the page renders, and **`id="changes"` exists nowhere in the repository** — `grep -rn 'id="changes"' scrapex/ extension/` returns nothing. The fragment is ignored, so the entry lands at the top of the source page |

**The changes page it should be opening already exists**: `GET /changes?source_key=`
is a real route (`scrapex/webui/app.py:1294`, re-derived at `31c369e`; #257 moved
it from 1223) and answers 200. So this is a wrong
URL rather than a missing feature — one line, but it changes what a card does on
his screen, which is why it was recorded instead of fixed inside a PR about the
three dots.

**Source settings has no obvious right answer, which is the part for him.** There is
no engine page for one source's settings; the panel has its own Source manager view
(`data-view="sources"`) with an editor in it. Whether the entry should open that
panel view, or the engine should grow the page, is a product decision.

**Why the guard did not catch these.** `tests/test_a_dataset_card_offers_what_works.py`
proves what each route does with a DATASET key, and both of these are correctly
withheld from a dataset card — `settings` because it 404s, `changes` because the page
carries no changes section. Withholding them for the right reason is exactly what
that file asserts. Nothing yet asserts that an entry offered on a PRICE card reaches
something, and that is the guard this entry is asking for.


### OP-52 · A dataset appears on two more screens whose only controls cannot touch it

**Status: OPEN. Measured 2026-08-22 while building `REQ-36`, and found by the stub
rather than by reading — this is what the dataset-kind row in
`tools/panel_harness.py` bought.**

`OP-42` was about the Data screen's cards. The same `kind: "dataset"` row shows the
same class of defect on two others, both driven from the same `/api/sources` listing:

| screen | what it offers a dataset | what happens |
|---|---|---|
| **Run** (`#sites`) | an ENABLED checkbox, alongside the price sources | `POST /api/jobs` answers **404 `unknown source_key 'contractors'`**. The crawl a dataset needs is `scrapex contractors`, a CLI command with no panel path — `REQ-24` closed the command and says the panel path is still missing |
| **Source manager** (`#source-manager-list`) | a card, counted in "4 of 4", whose only control is **Edit** | the editor posts to `/api/sources/{key}/edit`, a manifest route. A dataset is not in the manifest |

Measured directly, with the panel driven against a stub carrying the dataset:

    Run screen rows:  LONG_AR(enabled) SHORT(enabled) NOT_READY(disabled)
                      contractors(ENABLED)
    Source manager:   "4 of 4", four cards, every card's only button "Edit"

**AND `R-47` NOW DECIDES WHAT THE RIGHT ANSWER IS, which it did not when this entry
was written.** It landed with #257 and rules that muqawil is **one card with two crawl
options** — the listing sweep and the profile sweep, which "run, resume and approve
separately". So the Run screen offering a dataset a single checkbox is not merely
broken, it is the wrong shape: there is no one crawl to tick. The fix is a card that
offers the two, and it needs a panel path to a dataset crawl, which does not exist
(`REQ-24` shipped `scrapex contractors` as a CLI command and says the panel path is
still missing).

**UPDATED 2026-08-23: HALF OF THAT IS NOW BUILT AND THIS ENTRY IS THE HALF THAT IS
NOT.** `R-47`'s points 1 and 2 shipped — `_dataset_listing` folds the two muqawil
datasets into one listing row and reports the profile crawl as coverage, so the Data
screen draws one card. The sentence this paragraph used to end on — *"`_dataset_rows`
still ends `GROUP BY d.dataset_definition_id`, so the ruling is recorded and not yet
built"* — is **kept as history and no longer true of the listing**: that function still
groups per dataset, deliberately, because `/source/{key}` resolves one dataset out of
it by key and folding there would 404 the profile table. What remains open is exactly
what this entry names: **the Run screen and the Source manager still draw a dataset from
the same `/api/sources` answer and still offer it controls that cannot touch it.** The
fold changed the number of cards on those two screens as well; it did not give either
of them an action that works.

**Note what the Run screen already knows how to do**: `NOT_READY` is rendered
DISABLED with "Not supported yet" on it, because `implemented` is false. So the
screen has a mechanism for "listed but not runnable" and a dataset is not using it —
the engine reports `implemented: True` for a dataset (`_dataset_rows`), which is true
of the DATASET and false of the crawl. That is the cheap fix if he wants one, and it
is a decision about what `implemented` means rather than a bug in either screen.

**Deliberately not fixed with `OP-42`.** That fix changed what one card's menu
offers, on his direct request, and left every other screen's behaviour alone. These
two change what two more screens offer, and the `test_panel_dom.py` line that counts
"4 of 4" carries a comment saying so, so that nobody closes this by shrinking the
stub back.

### OP-62 · The published engine could not serve one page, because PyInstaller was told to carry two files and the runtime opens five

**Status: FIXED in this pull request. Reported by the owner 2026-08-23 against the
published `engine-v0.3.0`, the newest thing the panel's Download button offers.**

His console, in full — every step it announced succeeded:

```
  ScrapeX-Engine 0.3.0
  [1/3] Unpacking...        done.
  [2/3] Preparing your database...
        already there: C:\Users\User01\.scrapex\engine\scrapex-engine.db
  [3/3] Starting the engine...

error: Directory 'C:\Users\User01\AppData\Local\Temp\_MEI000036d42\scrapex\webui\static' does not exist
```

**THE PATH IN THAT MESSAGE IS THE DIAGNOSIS.**
[scrapex/webui/app.py:364](../scrapex/webui/app.py#L364) computes
`Path(__file__).parent / "static"`, which in a one-file build is
`_MEIPASS/scrapex/webui/static` — the string he was shown, `_MEI000036d42` and all.
[scrapex/webui/app.py:539](../scrapex/webui/app.py#L539) hands it to `StaticFiles`,
whose `check_dir=True` refuses a directory that is not there — the
`RuntimeError` is Starlette's own, raised in its `StaticFiles.__init__` — and
[scrapex/cli.py:1318](../scrapex/cli.py#L1318) prints the `RuntimeError` verbatim.

**And the directory was never in the archive.** `packaging/build_engine.py` named two
data entries; there is no `.spec` file and no PyInstaller hook in this repository, so
that list was the whole of it:

| the runtime opens | at | bundled before |
|---|---|---|
| `db/` | [scrapex/db.py:22](../scrapex/db.py#L22), [scrapex/databases/domain.py:20](../scrapex/databases/domain.py#L20) | **yes** |
| `sources.yaml` | [scrapex/config.py:55](../scrapex/config.py#L55) | **yes** |
| `scrapex/webui/templates` | [scrapex/webui/app.py:294](../scrapex/webui/app.py#L294), [scrapex/extract/api.py:33](../scrapex/extract/api.py#L33) | **no** |
| `scrapex/webui/static` | [scrapex/webui/app.py:364](../scrapex/webui/app.py#L364) | **no** |
| `apps_script/StagingAppScript.txt` | [scrapex/outputs.py:214](../scrapex/outputs.py#L214) | **no** |

**Only one of the three crashes, and that is the luck in this.** `Jinja2Templates` does
not check its directory when it is constructed, so a bundle with `static` and no
`templates` starts, reports itself healthy, and answers every page with a
`TemplateNotFound`. And `apps_script` has been missing from **every engine ever
published**: [scrapex/outputs.py:215](../scrapex/outputs.py#L215) returns `""` and the
route answers 404 saying the script *"is not bundled"* — a sentence that was true, that
nobody had read, and that no log anywhere records.

**WHY THE RELEASE GATE PASSED IT, which is worth more than the fix.** The double-click
step demands three lines — `ScrapeX-Engine`, `Preparing your database`, `Starting the
engine`. **All three are printed before `create_app` is called**, by
`packaging/engine_entry.py:_set_up_then_serve`, which then hands over to `scrapex ui`.
The gate had stopped one line short of the only call that can fail — the same shape of
miss as `OP-32`, where it stopped at `--version`. Its own guard could not catch that,
because `tests/test_the_release_proves_the_double_click.py` read `engine_entry.py`
alone and so believed the double-click path ended three lines before the work did.

**Fixed, and measured on a real artifact rather than argued.** `RUNTIME_DATA` in
`packaging/build_engine.py` is now the one list, the build refuses to run when an entry
is missing, and the rebuilt `dist/scrapex-engine.exe` — bare invocation, its own
`SCRAPEX_DATA_ROOT` — printed the line no published engine has ever printed:

```
ScrapeX UI → http://127.0.0.1:8000   (Ctrl+C to stop)
```

Served from that same binary, sizes matching the repository byte for byte:

| request | answer |
|---|---|
| `GET /` | **200**, 26,022 bytes — a rendered template |
| `GET /static/webui.css` | **200**, 13,306 bytes = the repo file exactly |
| `GET /static/grid.js` | **200**, 152,947 bytes = the repo file exactly |
| `GET /static/vendor/tabulator.min.js` | **200**, 445,987 bytes |
| `GET /api/outputs/apps-script/script` | **200**, 35,702 bytes — **this route has never worked in a shipped engine** |

**What keeps it fixed.** `tests/test_the_frozen_engine_carries_its_own_files.py` stages
a directory the way PyInstaller lays out `_MEIPASS` — modules from the package, then
`RUNTIME_DATA`, and nothing else — and starts the engine inside it, so the path
arithmetic under test is the real one and no binary has to be built. It carries its own
mutation: drop the `static` entry and the probe must die with Starlette's own words.
The release gate now also demands `ScrapeX UI`, and
`test_it_proves_a_SERVER_came_up_and_not_only_that_three_lines_printed` locates
`create_app(` by index in `_cmd_ui` and requires one demanded line to come from below
it — the rule rather than the string, because this gate has now missed twice.

**One fact, two hand-maintained lists, and the newer one was wrong.**
`pyproject.toml` `[tool.setuptools.package-data]` already carried the same trees for
wheels. Nothing compared them. It is also incomplete in its own right —
`static/*.svg` is absent while `scrapex/webui/static/x-mark.svg` is tracked — so a
`pip install` of this package drops that file today. Not fixed here: it is a wheel
path nobody installs from, and it wants its own change.

**It needs a tag to reach him.** The fix is in the source; nothing installable carries
it. `scrapex/version.py` reads `0.3.1` against a published `0.3.0`, so `engine-v0.3.1`
would ship it, and cutting it is his call (PLATFORM-PLAN Decision 4). **Until then the
only installable engine cannot serve a page** — the same standing condition as
`OP-32`, which lasted twelve days.

**Not a contract change** ([R-35](RULINGS.md#r-35--the-engines-version-moves-on-a-contract-change-the-extensions-on-a-user-visible-one)):
no migration, no route and no protocol move, so `VERSION` does not move for this.

**The register number, and the two round trips it took.** `OP-60` was claimed before the
primary session was asked, which is a breach of [R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)
and was surfaced rather than left. It came back confirmed — and the *reservations*
that came with it were wrong. Eleven `RESERVED` rows were written for 49–59, and by
the time the rebase ran, `#258` had declared 51 and 52 and `#261` had declared 53–59,
so nine of the eleven would have made `test_a_reserved_number_is_not_also_declared`
red on the tree that merges. The reasoning was right and the base was two hours old,
which is the same lesson the pointer at the top of [STATE.md](STATE.md) keeps teaching.

**Then `OP-60` turned out to be taken too, and the number is `OP-62`.** It was handed
over as free **twice**, by a session that had checked `main` — where the register does
run unbroken to 59 — and not the branches in flight.
`feat/the-engine-knows-which-code-it-is-running` had already pushed 60 **and** 61. That
is §3 of [ORCHESTRATION.md](ORCHESTRATION.md)'s *"a claim can be real and invisible"*
landing on the session that owns §3, and the method that caught it is the one worth
keeping: **sweep the highest declared number on EVERY ref**, not on the branches you
happen to know about —

    for r in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes); do
      git grep -oh -E "^#{2,4} +OP-[0-9]+" "$r" -- docs/BACKLOG.md ...

**That same sweep found a duplicate nobody was tracking:** two pushed branches both
declared `OP-61`. It was ruled to
`feat/the-engine-knows-which-code-it-is-running` and the card branch moved to 63 — on
lower churn rather than on the open-PR rule, and the primary session said so rather
than letting the rule appear to decide it. So the branch ends with **two** `RESERVED`
rows, 60 and 61, both to that one branch, and the row for 61 records that the card
branch's renumber had not yet been pushed when it was written. That last clause is
deliberate: this file's own scar is a row that named a holder who had moved and passed
every guard while doing it.

**What an adversarial review of this fix found, because the fix's own comments were
not exempt.** Sixteen findings raised, twelve refuted, and the survivor worth naming
is a citation *inside this change*: `packaging/build_engine.py` cited
`scrapex/cli.py:1301` for the line that prints the error, while the same change wrote
the correct line in this file and in `LESSONS.md`. `R-15`'s guard scans eight
markdown documents and cannot reach a build script, so it was green with the wrong
number in the tree. Eleven citations in the three unguarded files this change touches
now name **symbols** instead of lines. The refutations are worth as much: one reviewer
checked `RUNTIME_DATA` against the real `.exe` table of contents and found no gap,
and the worry that `contractstamp` reads a `.py` at runtime was refuted — it is a
developer-only path.

### OP-60 · A frozen engine cannot name the commit it was built from, and says so

**Status: OPEN by design, and the honest half of a fix that landed.** Measured
2026-08-23 while building `scrapex/provenance.py` (`LESSONS` §14).

A source-run engine can now answer *which code am I running* — it seals what it
loaded and compares it against the disk. **A PyInstaller one-file `.exe` cannot.** It
carries no `.git`, no source tree, and its modules unpack into a per-run temp
directory that says nothing about whether newer code exists anywhere. So it answers:

    mode    "frozen"
    commit  null
    stale   null      <- unknown, NEVER false

**That is correct, not a stub**, and a test pins it (`stale is not False`): on the one
build where staleness cannot be measured, claiming `False` would tell the owner his
engine is current when nobody knows. The gap is narrower than "the frozen build is
unguarded": what is missing is only the **commit it was built from**, which no amount
of run-time inspection can recover and which only the build can write down.

**The fix is a build-time stamp**, and it is small: the release workflow writes the
commit it is building into a generated module, and `provenance` reads it if present.

**NOT DONE HERE, and the reason is a live constraint rather than laziness.** The
primary session is cutting `engine-v0.3.1` from `.github/workflows/release-engine.yml`,
and a change to that workflow from a branch merging into the same window is a change to
the thing being run. `R-35`'s gate also refuses a version edit from this branch. So the
reader is the whole of this change and the writer is the next one.

**Do not close this by making a frozen build guess.** The `None` is the feature.

### OP-61 · A continuation citation is invisible to the citation guard

**Status: OPEN. Measured 2026-08-23, re-measured at `f1844af`. A latent structural gap, not a live
defect — that distinction is the whole entry.**

A citation written as `` (`extension/app.js:1602`, `:1641`) `` carries two references
and the guard sees one. `CITATION` in
`tests/test_the_documents_cite_what_they_claim.py` requires a path before the colon, so
it matches `app.js:1641` and does not match a bare `:1641`. Measured directly: the
regex returns a match for the first string and `None` for the second.

| | |
|---|---|
| continuation citations in the guarded documents at `f1844af` | **19** |
| of those, resolving to a blank line or past EOF | **0** |
| spot-checked and correct | the `docs/STATE.md` pair citing `scrapex/features.py:54` and `:65` |
| moved silently by this branch's edits, guard green throughout | **4** |

**What makes it real is the fourth row.** Edits on the branch that added
`scrapex/provenance.py` shifted `extension/app.js` by eight lines; four continuation
citations went with it; the guard passed the whole time; they were found by reading the
diff by hand. Tier 2 cannot help, because a `PINNED` row is keyed on a path the tier-1
sweep never discovered — there is nothing to pin.

**What makes it NOT urgent is the second row.** None of the nineteen is currently
wrong. The class also pre-dates the branch that found it; only the four movements were
its own.

**The remedy, and the trap to avoid.** The obvious guard — inherit the path from the
nearest preceding citation — is *deciding by adjacency*, which this repository has
measured and rejected twice (the prose-inference tier the guard's own docstring
records, and the keyword allowlist `LESSONS` §13 threw away). **The non-inferring fix
is to forbid the continuation form:** require every citation in a guarded document to
name its path. One mechanical rule, zero inference, and nineteen invisible citations
become nineteen the existing tiers already handle.

**Cost:** rewriting nineteen citations across five documents — a conflict surface of
its own, which is why it was not bundled into the branch that found it.

**And there is a table this is the fifth row of, which is not on `main`.** *Four shapes
of a wrong citation* lives on `origin/docs/the-boundary-becomes-a-ruling` at `c6d9212`,
unmerged. Whoever lands that branch should add the row.

### OP-68 · "The last crawl" is a TIMESTAMP, so 17,256 of 17,304 contractors are shown as having disappeared

**Found 2026-08-24 by an adversarial review verifying `#267`'s numbers. It predates `#267`
entirely** — `contractors` was not touched by that work, and the skew is older than the
`R-51` recovery run.

**`scrapex/sightings.py:398` decides a row is gone by comparing its `last_seen_at` against
`newest`, and `newest` is `MAX(last_seen_at)` to the SECOND** — a timestamp, not a run
identifier ([scrapex/extract/service.py:929](../scrapex/extract/service.py#L929)):

```python
if last_seen_at is None or last_seen_at < newest:
    return STATE_ABSENT
```

A crawl writes its rows over half an hour, so only the rows written in the **final second**
survive that comparison. Measured read-only on the live warehouse:

| | `contractors` | `contractor_profiles` |
|---|---|---|
| `newest` = `MAX(last_seen_at)` | `2026-08-22T07:39:56Z` | `2026-08-24T11:47:30Z` |
| rows equal to it | **48** | **1** |
| rows earlier than it → `STATE_ABSENT` | **17,256** | 17,384 |
| distinct `last_seen_at` values | **1,034** | 3,412 |
| `dataset_sighting` rows | 17,417 | **0** |

**So the Data screen tells the owner that 17,256 of his 17,304 contractors have stopped
being published — after a crawl that read every one of them.** That is the loudest possible
false alarm on the one screen whose job is to show what the site is doing.

The profile table is wrong differently and it is worse for being quiet: `dataset_sighting`
holds **zero** rows for `contractor_profiles`, so `sighted_at is None` fires two checks
earlier and all 17,371 read `unsighted`. The absence bug is masked by a gap in the ledger.

**The reasoning that fixes it is already in the file, eight lines below the defect.**
`scrapex/sightings.py:403-407` explains that `last_absent_at` needs `>=` rather than `>`
*"because both timestamps are `strftime(...,'now')` at SECOND resolution"*. The same
argument applies to `newest` and was never carried across. A run identifier — or the crawl
run's own start time — answers "was this row seen by the last crawl?"; the maximum of a
column written row by row cannot.

**Two statements nearby are also false, and both predate `#267`:**

* [scrapex/extract/service.py:601](../scrapex/extract/service.py#L601) says *"`last_seen_at`
  still moved: the upsert above sets it unconditionally, so a confirmation is recorded on
  the RECORD."* The `DEC-10` early `return` at
  [scrapex/extract/service.py:503](../scrapex/extract/service.py#L503) fires **before** that
  upsert. Measured: **0** profile rows have a `last_seen_at` on 2026-08-24 with an earlier
  `first_seen_at`; all 17,264 pre-`R-51` rows still read 2026-08-23, after a full
  re-approval that touched every one of them.
* `docs/RULINGS.md` claims `dataset_table_payload` *"filters `AND status = 'active'`"* and
  drops the observation facts. Both were true once and are not now: `ec53b17` (#235) removed
  the filter under `R-27`, and the payload attaches `observed_first_seen`,
  `observed_last_seen`, `observed_status`, `observed_last_changed`, `observed_state` and
  `observed_state_meaning`. **The audit that produced that paragraph asked "does it
  filter?" and never asked "does the derived state say the right thing?" — which is where
  the defect actually is.**

**AND IT IS NOT A DISPLAY BUG — IT IS A PUBLISHED COLUMN.** `publish.py`'s
`dataset_workbook_tables` turns every payload column into a workbook column
([scrapex/publish.py:135](../scrapex/publish.py#L135)), and the payload carries six:
`observed_state`, `observed_state_meaning`, `observed_last_seen`, `observed_first_seen`,
`observed_last_changed`, `observed_status`. Read from the live warehouse just now:

```
observed_state          'absent'
observed_state_meaning  'The most recent crawl did not show this row'
```

on 17,256 of 17,304 rows. So the false sentence is written **into the Google Sheet the mbiX
Excel add-in reads** — the single boundary `CLAUDE.md` says the two systems meet at. That
moves this from "a screen is wrong" to "the product's only output is wrong", and it is why
this entry leads the register rather than sitting in it.

**AND IT IS THREE STATES, NOT ONE.** The docstring states the flawed premise out loud
([scrapex/sightings.py:365](../scrapex/sightings.py#L365)): *"`newest` is the dataset's
latest `last_seen_at` — 'the last crawl'. Everything is relative to it."* Everything is,
and three of the eight states rest on it:

| step | test | what it gets wrong |
|---|---|---|
| 3 · `absent` | `last_seen_at < newest` | **17,256 of 17,304** contractors |
| 4 · `new` | `first_seen_at >= newest` | **1** profile reads `new`; **121** were first seen today |
| 6 · `updated` | `changed_at >= newest` | same second-resolution window |

So the screen under-reports what arrived by the same arithmetic that over-reports what
left. `R-27`'s own instruction was «لا تدع المستخدم يستنتج الحالة» — and the column that
exists so he does not have to infer is wrong in both directions.

**THE HALF THAT NEEDS NO RULING, and it is the half that lies in the sheet.** `absent`
must come from the ledger's own absence record, not from a timestamp race.
`mark_unavailable` / `mark_departures` exist to write exactly that, step 5 already reads
`last_absent_at` for `returned`, and step 3 ignores it. Measured, the ledger is right and
the comparison is noise:

```
dataset_sighting for 'contractors':  17,417 rows
   ever marked absent          0
   absent NOW                  0        <- the ledger's answer
   the timestamp says absent  17,256    <- what the screen and the sheet publish
```

So `if last_absent_at is not None and (last_seen_at is None or last_absent_at > last_seen_at)`
is the whole change for step 3, and it needs no new column and no decision.

**THE HALF THAT IS HIS TO RULE.** What "the last crawl" MEANS for `new` and `updated`,
because this pipeline has no single answer today:

* `crawl_run` is the **price** path only — `source_id` points at a price source, and a
  generic crawl writes nothing to it. 159 rows, none for a dataset.
* `dataset_sighting` carries `first_run_ref` and `last_absent_run_ref` and **no
  `last_run_ref`** — the missing third of three is conspicuous.
* A partitioned listing crawl is **93 run refs**, not one, and they share only a prefix.
* And `first_seen_at` is an **approval** time while `generic_page_snapshot.captured_at` is
  a **fetch** time; the R-51 recovery approved pages fetched two days earlier. Comparing
  the two would call a two-day-old page "new".

So "seen by the last crawl" is not derivable from what is stored, and inventing a rule
here would be answering for him — `R-02`'s shape exactly. The options, with their cost:

| | change | what it buys |
|---|---|---|
| **A** | `dataset_sighting` gains `last_run_ref`; a crawl stamps it | an exact answer for all three states; one migration |
| **B** | a generic `dataset_crawl` run table, started and finished | the same, plus a real progress denominator and history |
| **C** | leave `new`/`updated` blank until A or B | no false state, and two columns that say nothing |

**Recommended: fix step 3 now under this OP — it is the one that reaches the sheet — and
put A against B against C to him as its own decision.** Splitting it that way means the
published lie stops today without a schema change being rushed to carry it.

**RULED 2026-08-24 — «نفذ ب».** `R-52`: a generic crawl is a RUN with an identity, in a
table of its own — one row per crawl, not the per-contractor attendance register `0006`
weighed and refused at 17,403 rows a crawl. `started_at` is what `absent` compares
against, `finished_at` is what stops a run still in flight from declaring departures, and
the same table gives `declare_frontier` the denominator `STATE.md` has been missing. Step
3's ledger fix stands on its own and lands first.

**Why this is not folded into `#267`.** It is not caused by that work, it touches the state
derivation every dataset row on the Data screen reads, and `R-51`'s own three new columns
land directly on top of it. Recorded here so it is picked up as its own change with its own
review, which is what this register is for.

### OP-67 · A SECOND obfuscated email on the page is stored as Cloudflare's placeholder text

**Found 2026-08-24 while checking the `R-51` recovery run for damage.** It found none — and
found this instead, which predates that work entirely.

**16 rows hold the literal string `[email protected]` in a declared column:** 13 in
`contractor_profiles` (all in `address`) and 3 in `contractors`. Verified against the
newly written rows: **0 of the 16 are among the 121 `R-51` recovered**, so this is not the
alignment repair's doing.

**The cause. `read_email` takes the FIRST `data-cfemail` on the page and there can be
two.** Contractor `1006`'s English profile carries exactly two:

```
BOX: Organization Email  [email protected]
     data-cfemail -> ayman@smart-const.com          <- read_email finds this one. Correct.
BOX: Address  Al Khobar Al Shemaliyah Cross 15 - Buldg. # 7484 - ...
     data-cfemail -> info@smart-const.com           <- nothing decodes this one
```

`_CFEMAIL.search(html)` is a `search`, so `organization_email` is right on all 17,385 rows.
But the address box's **text** is stored verbatim, and where the second obfuscated address
sat there is now a placeholder:

```
1006: 'Al Khobar Al Shemaliyah Cross 15 - Buldg. # 7484 - 4th Floor - Office # 10
       P.O. Box 1861 Al Khobar 31952 Tel: 00966138941919 - Fax: 00966138965511
       [email protected] www.smart-const.com'
4776: 'Tel: 0138196000 Fax: 0138113334 Email: [email protected]
       Www.Alosais.com P.O. BOX 1083. Dammam 31431, KSA'
```

**Why nobody saw it.** This is failure #1 of `scrapex/extract/muqawil.py`'s own module
docstring — *"every contractor stores the literal `[email protected]` and any 'is the
column populated' test passes forever"* — and the guard written for it watches
`organization_email`, which is the field that was never wrong. The address is 90% correct,
so it reads as a full value; the placeholder sits at the END on only 5 of the 13, buried
mid-string on the other 8. **1,392 of 17,385 rows carry an address at all**, so this is 13
of 1,392 — under one percent, and invisible at any sample size a person would eyeball.

**The fix, and it is not where the bug looks.** `read_email` is correct and should not
change; what is wrong is that a box's TEXT is read without decoding the `data-cfemail`
inside that box. `read_profile` should decode per box — replace each obfuscated span with
its own decoded value while reading the pair — which fixes `address` and any future field
the site hides an address inside. Replayable from the stored snapshots with no network,
like `OP-66`.

**NOT BUILT, AND DELIBERATELY NOT IN `#267`.** It predates `R-51`, it touches
`read_profile` — the same critical parser the adversarial loop is currently converging on
— and folding it in would restart that loop for a defect affecting 16 rows. Recorded here
with its measurement so it is picked up on its own, which is what this register is for.

### OP-66 · The Arabic profile publishes an address box the English one does not, and 129 contractors are held out by it

**Found 2026-08-24 by the owner asking whether another crawl was needed.** It is not, and
answering that question found this.

**The crawl is complete.** 36,358 profile snapshots on disk, **17,452 distinct contractor
ids — the full union — and zero left to fetch.** What is missing is not pages; it is rows.

| | |
|---|---|
| listing rows (`contractors`) | 17,304 |
| profile rows (`contractor_profiles`) | 17,264, of which 14 retired by `OP-64` |
| listing row with **no profile row at all** | **188** |
| listing row with no *active* profile row | 202 (the 188 plus the 14) |
| profile row with no listing row | 148 |

Every one of the 188 has a stored snapshot. Replaying the current parser over them —
read-only, no network — splits them cleanly:

| count | refused by | can a crawl fix it? |
|---:|---|---|
| **59** | `PageIsNotAProfile` — layer 1 of `OP-64`; the id is dead and the site answers with the listing | **No, ever.** The page does not exist |
| **129** | `merge_locales` — the two locales publish different box counts | **No.** The pages are on disk |
| **0** | would approve today | re-approval adds nothing |

**The cause of the 129, measured.** The Arabic page carries a `عنوان` (address) box that the
English page does not publish at all:

```
[en]  9 info-boxes   ...  8. Region  Eastern Province
[ar] 10 info-boxes   ...  8. المنطقه الشرقية
                          9. عنوان  الرياض - شارع العليا - مقابل أبراج العليا
```

`CONTRACTOR-SOURCE.md` already records that the address is Arabic-only; what is new is that
on these pages the English side omits the box **entirely**, so the counts differ and
`merge_locales` refuses.

**AND THE FIRST VERSION OF THIS ENTRY MEASURED IT WITH THE WRONG ARRAY.** It reported a gap
of **+2** on every pair and concluded that **"121 of 121 are MISALIGNED"**, so no repair was
possible. Both claims were artefacts of the instrument: they compared `Reading.fields`, a
dict whose insertion order is not the page's, because `read_profile` adds
`organization_email` and `commercial_registration` after the info-box loop.
`merge_locales` reads `english.labels[index]` and — since `R-51` — the Arabic value at
the position `align_locales` works out
([scrapex/extract/muqawil.py:1715](../scrapex/extract/muqawil.py#L1715)). Re-measured
against **those**:

| pages | shape | the last label on each side | is the odd box at the END? |
|---:|---|---|---|
| **97** | AR one longer | EN `Region` · AR `عنوان` | **yes** — Arabic simply adds the address |
| **24** | AR one longer | EN `Activity` · AR `الخدمة` | **no — it is interior** |
| **7** | EN one longer | EN `Address` | yes |
| **1** | EN one longer | EN `Activity` | no |

The gap is **±1 on every one of the 129, never ±2**, and **no pair is misaligned before the
divergence** — the digit instrument reports zero disagreements, because the odd box always
falls after the last numeric field. So digits cannot decide this question either; the LABEL
POSITIONS can.

**THE REFUSAL IS STILL CORRECT, AND THE 24 ARE THE PROOF.** Contractor `20000713`:

```
    8   EN Region                AR المنطقه
    9   EN Activity              AR عنوان        <-- diverges here, in the MIDDLE
   10   EN     --                AR الخدمة
```

Zipping to the shorter list would write the Arabic **address** into `activity_ar` for those
24. So the tempting repair — tolerate a trailing extra box — is wrong, and `merge_locales`
is right to refuse rather than zip. What was wrong was the conclusion that NO repair exists.

**The repair that does exist, and reads no Arabic label.** `PROFILE_FIELDS`
(`scrapex/extract/muqawil.py:121`) is an ordered map of the **eleven** English labels **in
page order**. Every one of the 129 English pages carries a subsequence of those eleven, in
order, with no unrecognised label — checked, zero strays. So when the English page omits a
box, *which* box it omitted and *where* is known, and the Arabic list can be indexed around
that gap. Measured over all 188:

| count | outcome under the canonical-position repair |
|---:|---|
| **121** | **recoverable** — Arabic is the longer side, so the gap is deducible from English |
| **8** | refused — Arabic is the SHORTER side, and which field *it* dropped cannot be deduced without reading an Arabic label |
| 59 | untouched — layer 1 still refuses them, and rightly (`OP-64`) |

**Why this preserves the property the current code is built on.** `merge_locales`'s docstring
argues that reading no Arabic label is what stops a spelling change in one from breaking the
merge — and the site's own `المنطقه` is spelled with `ه` where `ة` belongs, so that argument
has teeth: a hand-written Arabic vocabulary would have to carry the site's typo and would
break the day they fix it. The canonical-position repair reads Arabic **values** only, exactly
as today.

**Worth +121 contractors with their address** — a field the English page cannot supply for
anyone. Independent of the network, replayable from the snapshots already stored.

**BUILT AND RULED, 2026-08-24 — `R-51`.** He was shown the two options and chose the
second: «نفذ ب». `align_locales` (`scrapex/extract/muqawil.py`) locates the gap from the
English side and `merge_locales` asks it; no Arabic label is read, which is the property
the old refusal was built on and is worth more than the 129. Guarded by
`tests/test_the_two_locales_line_up_around_a_missing_box.py` on two real page pairs
committed as fixtures, and mutation-tested on eleven branches — one mutant survived the
first draft and proved the order check was passing for the wrong reason.

**Measured after the repair, replaying the 188 through the parser:** 121 merge, 24 of them
carrying an address they did not have, 8 still refused, 59 still at layer 1.

**AND THEN RUN FOR REAL, which is the number that counts.**
`--approve --run-ref profiles-2026-08-22` over 17,417 stored pairs, **83.9 minutes, zero
network requests**:

| | |
|---|---|
| profile rows | 17,264 → **17,385** — **exactly 121 added** |
| of those 121, carrying an address | **24** — the prediction, to the row |
| listing rows with no profile row | 188 → **67** = the 8 refused plus the 59 dead ids |
| pages unchanged, writing nothing | 17,249 (`DEC-10` idempotency held) |
| re-parsed with NEW values | **0** — not one already-approved row was rewritten |
| rows where `activity_ar` equals `address` | **0** — the corruption a tail-drop would have caused, on the whole table and not just the new rows |

The 67 that remain are the floor this repair cannot lower: 59 need a page the site no
longer serves, and 8 need an Arabic label read. `REQ-42` owns the 59. The 59 belong
to `REQ-42` (a withdrawn contractor entered with a state that says so) and are separate
from this.

### OP-65 · A snapshot records the URL we ASKED for, never the one we landed on

**Found 2026-08-23 by the owner asking whether the new guard was even correct.** It is —
and the question found something better than the guard.

`OP-64` diagnoses a dead profile id from the CONTENT of the page that comes back. That was
reading the symptom. The cause, measured live:

```
asked   /en/contractors/20074580/143
302  ->  /contractors
302  ->  /en/contractors
landed  /en/contractors        <- two hops, to the listing
HTTP    200        372,141 bytes        the listing, 20 contractor links

control
asked   /en/contractors/1004/143
landed  /en/contractors/1004/143
HTTP    200        122,717 bytes        a real profile
```

**muqawil redirects a withdrawn id to the contractors listing** and answers 200, in TWO
hops through a locale-less `/contractors`.

> **CORRECTED.** This entry first said the locale switched — *"`en` was asked for and `ar`
> came back"* — and made that the fingerprint. Re-measured live: `en` was asked for and
> `en` came back. The real fingerprint is the two-hop 302 chain, which is stronger and
> which the first measurement never recorded.

### Why nothing in the project could notice

`generic_page_snapshot` stores **`source_url`**, which is the URL the crawler *requested*.
There is no column for the URL the response actually came from, and `httpx` follows
redirects silently (`follow_redirects=True` at `scrapex/funnel.py:194` and three other
call sites). So a page fetched from somewhere else is stored under the address we wanted,
and every reader downstream — the parser, the approval, the coverage report — believes it.

**This is a whole class, not one site's quirk.** Any source that answers a gone resource
with a redirect to an index page produces the same silent substitution, and `OP-64`'s
remedy would have to be written again per parser. A `final_url` on the snapshot catches
all of them at the seam where the evidence is created.

### What it needs

1. **A `final_url` column** on `generic_page_snapshot`, written by the fetch seam.
2. **A refusal at the seam, not in the parser**: if the final URL is not the requested one,
   the page is evidence of a redirect and not of the thing that was asked for. `OP-64`'s
   layer 1 then becomes a second line rather than the only one.
3. **The 78 snapshots already stored under the wrong address stay wrong**, because the
   fact was never captured. They are identifiable by content and that is all.

**It does not replace `OP-64`.** A page can be substituted without a redirect, and the link
test still catches that. But the redirect is the cheaper signal and it arrives first.

### OP-64 · The site answers a dead profile id with the LISTING page, and the parser believes it

**Found 2026-08-23 by the owner asking whether the counts were duplicated.** They were
not. Chasing why the membership number repeated found this instead.

**`card_membership_number` on the listing is unique and the owner's rule holds**: 17,304
rows, 17,304 distinct values, zero blank. The repeats are in the PROFILE dataset —
13,347 rows, 13,333 distinct, **three values shared**, one of them (`117511752`) sitting
on **thirteen different contractor ids**. Fourteen contractors carry a different
membership number in the profile table from the one on their listing card.

**Re-measured 2026-08-24, after the profile crawl finished: 17,264 rows, 17,250 distinct,
still exactly three shared values and still 14 excess rows** — `117511752` on 13 ids,
`121612167` on 2, `587458748` on 2. The row count above was taken mid-crawl and did not
say so, which is the defect; the finding itself did not move, and 3,917 further profiles
added not one new collision.

**The cause is not bad data entry. The site served the wrong document.**

```
GET /en/contractors/20034161/143
    <title>       Contractors | Muqawil Platform
    decoded       375,363 bytes, 22 section-cards
a real profile    ~122,000 bytes,  7 section-cards
```

For an id that no longer resolves, muqawil answers **the contractors listing** with HTTP
200. `read_profile` calls `_boxes(soup)` over the whole document, so it read the first
card of that listing and attributed a stranger's values — `160916095`, `Small`, `96 h`,
`RIYADH - Riyadh` — to whichever id had been asked for. **That is why thirteen ids share
one membership number: they all took the same stranger's card.**

**Measured, and it is small.** A random sample of 500 decoded snapshots:

| | | |
|---|---|---|
| real profile | 499 | 99.8% |
| listing served instead | 1 | 0.2% |

About 70 of the 34,834 snapshots (95% CI 0–206) are the wrong document.

> **CORRECTED TWICE, and the second correction reverses half of the first.** This entry
> first said the rows hold *"another company's address, city, size and email"*. I
> corrected that to *"the membership number alone"*. **Two adversarial reviews measured
> both and both were wrong** — the first overstated it, mine understated it.
>
> **What is actually wrong, dumped from `generic_record_id=20579`:** FIVE declared
> columns carry the stranger's values — `membership_number`, `company_size`,
> `company_size_ar`, `training_credit_hours`, `training_credit_hours_ar` — plus **twelve**
> undeclared `x_*` fields. `address`, `organization_email` and the coordinates ARE null,
> which is the half my correction got right.
>
> **And the blast radius is 39 ids, not 14** *(as of 2026-08-23T16:00Z — see the note
> below; it was 72 before this entry was even committed)*. 78 snapshots, both locales; 14
> produced a row, **25 produced none**, which is why counting rows undercounted the
> defect by 2.8x. Of the 39, **28** sit in the id block `20074580`–`20075073` — 9.96% of
> that block against 0.224% crawl-wide, **44x** — and **eleven** are outside it with no
> story, not two.
>
> **AND THIS CENSUS WAS STALE BEFORE THE COMMIT THAT STATES IT.** Round two measured the
> clock: 39 ids / 78 snapshots was exact at `16:00Z`, and by `16:44Z` — when the commit
> asserting it was authored — a targeted re-crawl had made it **72 ids / 154 snapshots**,
> because re-fetching a dead id stores the listing again. **A census of a growing corpus
> needs an as-of instant or it is a claim about the past written in the present tense.**
> The undercount factor is not 2.8x but 5.2x, and the block percentages below
> (9.96%, 44x) were computed from an intermediate denominator and do not reproduce: the
> block holds 321 ids with profile snapshots, so it is 8.72% and 39x.
>
> **It is the LAST card on the listing, not the first.** `fields[key] = value` is
> last-wins over every `div.info-box` pair on the page, and the poisoned page has 160 of
> them. The values this entry originally quoted — `160916095`, `Small`, `96 h` — belong
> to the FIRST card and appear in no stored row.
>
> The numbers below are kept as written, with their errors, because `C4` says a changed
> mind keeps its predecessor:
>
> ```
> id 20034161   membership 117511752   (its listing card says 355735571)
>               city=None  email=None  latitude=None  company_size='Very Small'
> ```
>
> The profile parser looks for `PROFILE_FIELD_ORDER`'s labels, does not find them on a
> listing page, and emits **nulls**; only the membership number leaked through. Populated
> fields average 18.0 on the wrong rows against 18.2 on healthy ones — they are not
> impersonating anyone, they are empty with one borrowed number.
>
> The original claim came from probing the page with `_boxes()`, which is what
> `read_listing` uses; the stored rows came from the profile path, which behaves
> differently. **A probe is not the pipeline.** The rows themselves were the only honest
> witness and they were one query away.
>
> It still is not harmless: thirteen ids collide on one number, and anyone searching by
> membership number reaches the wrong company.

### What it needs

> **SUPERSEDED, and the paragraph below is the design this entry's own correction
> refuted.** It is kept per `C4`. What shipped counts CONTRACTOR LINKS, not cards: a
> profile links to exactly itself and a listing to many, so there is no threshold to
> defend. The card count was measured with a regex the parser does not use — through
> `soup.select` a real profile has six — and 160 real listing pages carry fewer than 15
> cards, so the gap it relied on did not exist on the side it guarded.

A **shape check before parsing**: a profile page is not a listing, and 22 section-cards
where 7 are expected is the site saying "this id is gone" in the only way it does — with
a 200. Refuse the page rather than parse it; the id belongs in a not-found list, not in
the table. `PROFILE_FIELD_ORDER` already distinguishes the two documents at approval time
(`scrapex/contractors.py`), so the knowledge exists and is applied one step too late.

**And the rows already written must be found and removed**, not left: they are wrong in
the most expensive way, being plausible. The listing's own membership number identifies
them — a profile row whose number disagrees with its listing card is the marker.

### A note on the measurement itself, because it nearly shipped wrong

The first attempt discriminated on *"a profile has no section-cards"*. A real profile has
**seven**, so 398 of 400 sampled fell into "other" and the run reported **0.5%** from two
survivors. The number was an artefact of a broken instrument, not a finding. It was caught
because 99.5% unclassified is not a result. **A discriminator has to be measured against a
known-good example before it is trusted to count anything.**

### OP-63 · The word "products" over a contractor directory, on two surfaces

**Status: the PANEL half is CLOSED by this branch. The ENGINE PAGE half is OPEN and
is a design question, not a noun.** Found 2026-08-23 while diagnosing why his Data
screen still showed two muqawil cards — he did not report this one, which is why it
is here and not in `REQUESTS.md`.

His screen read:

```
muqawil.org / Saudi Contractors Authority · contractors [Row 17,304]
  17,304 products
```

**A contractor is not a product, and 17,304 contractors are not 17,304 products.**

**THE PART THAT MAKES IT A REAL FINDING RATHER THAN A TYPO: the engine already knew
the word was meaningless, in writing.** `_dataset_rows` (`scrapex/webui/app.py`)
carries this comment over the line that fills the field:

> *"`observations` is what the Data screen filters on, and for a directory the honest
> number is its rows. `products` has no meaning for a company, so it carries the same
> count rather than a zero that would read as an empty dataset."*

So the engine deliberately passed a duplicate of the row count through a field it
documents as meaningless for a company, and the panel printed the meaningless word
underneath it. Neither side was unaware; the two notes never met.

#### What was fixed, and why the noun is not a special case

`extension/app.js` hardcoded `${fmtCount(s.products)} products` for every card. The
replacement is `countLine`, three branches, each keyed on what the engine reports
rather than on a key's spelling — because `jobs` and `tenders` are named in
`CLAUDE.md` as coming and `if (contractors)` would be the third wrong noun the day
`tenders` lands:

| the card | the second line | why that |
|---|---|---|
| a price source | `1,812 products` — **unchanged** | there the word is TRUE and the number is a DIFFERENT one: spark-eshop reads `[Row 6,969]` above `1,812 products`. This is why the noun could not simply be replaced |
| a dataset with a confirmed one-to-one detail crawl | `Contractor profiles: 704 of 17,304 (4.1%)` | `R-47`'s second point. For a dataset `observations` and `products` are the SAME number, so any noun would print the figure twice; coverage is the fact that slot was missing |
| any other dataset | `8,412 rows` | the honest generic |

**WHY `rows` AND NOT A BETTER WORD, since `R-45` governs it.** «ما يقوله الموقع هو
مصدر الحقيقة الوحيد» forbids inventing a label the site never gave, and it rules out
the two tempting alternatives: `dataset_definition.original_name` would print
`17,304 contractors` for one dataset and `704 contractor_profiles` for the next, and a
raw key dressed as an English noun is exactly the invented claim `R-45` refuses.
`dataset_kind` was checked and is not the unit of a row — measured read-only on his
warehouse 2026-08-23, it is `'table'` for both muqawil datasets, a structural kind.
**Nothing in the warehouse names the unit of a row.** `rows` claims nothing about the
site, and it is not a new vocabulary either: `sourceIdentity`'s default metric label
is already `Row`, so the line above reads `[Row 17,304]`, and the Drive offline card
in the same function already prints `<n> rows`. The COVERAGE label is the one word
taken from the site, and it is the child dataset's stored `display_name` — what the
approval recorded, never ours.

**`rows` IS THE ANSWER, NOT A FALLBACK, and the distinction matters because nothing
has been ruled here.** No ruling covers the boundary between `products` and a
directory, so this is a choice and it is recorded as one: a generic word that is true
of every dataset beats a specific word that is true of one and invented for the rest.
The moment the site itself gives us a word for what a row IS — not what the table is
called, which `display_name` already holds — that word wins and this branch should be
revisited. **His call if he wants a different word;** the reason for this one is above.

> **CHECKED AGAINST `R-45`'s CORRECTION, 2026-08-23, because that correction landed
> while this was open.** #261 measured that the per-row record card **has existed on
> the engine since 2026-07-22** — 967 lines of `grid.js`, opened by row *selection*,
> which is why a census searching for `rowFormatter` missed it — so `R-45`'s own table
> was wrong about the card, and products have it while contractors do not.
>
> **None of that moves the noun.** This entry rests on `R-45` **part 1** — *"WE NEVER
> TRANSLATE. The site's words are the record… A mapping we invent is our claim dressed
> as the site's data"* — and the correction is about **part 2**, whether the row's card
> exists and what it costs. The ruling's own words are that it *"stands unchanged"*.
> Re-checked rather than assumed, since a reasoning chain resting on a ruling that has
> just been corrected is exactly the thing worth re-reading.

#### The open half: the engine's own page says it too

**`/source/contractors` prints a "Products" tile over the very same rows** — and that
is the surface this branch did not touch. `_source_overview.html` renders four tiles
from `SourceSummary`, and `/source/{key}` fills `products` for a dataset out of
`_dataset_rows`, which is why the field is still sent rather than dropped.

**RENDERED, not read.** The page was fetched from a real engine holding one approved
dataset of 4 rows and the four `<dd>` values read off the returned HTML — because a
claim about what a template prints, reached by reading the template, is the shape this
repository keeps catching:

```
GET /source/contractors -> 200, 42,058 bytes
  Products    4
  Variants    0
  Data rows   4
  Matched     0
```

**Three of those four say nothing about a contractor directory and the fourth
duplicates the first**: `Products` is the meaningless field, `Variants` and `Matched`
are price-path concepts a company has none of, and `Data rows` is the honest number
already. So this is not the panel's one-line fix wearing a different template — it is a
question about what a dataset's overview should show at all.

#### The options, per `W3`, because this one is his

| | what it does | effort | risk | what it costs later |
|---|---|---|---|---|
| **(a) do nothing** | the tile keeps reading `Products 17,304` over a directory | none | the engine page goes on saying what the panel stopped saying — **two surfaces disagreeing about the same rows**, which is the shape `#255` already had to fix once | the disagreement is the maintenance |
| **(b) rename the one tile** | `Products` → `Rows` when `kind == dataset` | one line + a guard | **low, and it looks finished when it is not**: `Variants 0` and `Matched 0` still state price-path facts about a company | invites a third fix later for the same panel |
| **(c) the tile SET follows the kind** | a dataset shows `Rows` and its coverage; a price source keeps all four | ~half a day, template + a shape the template can read | the tile list becomes data rather than a literal — the same move `countLine` just made on the panel | lowest: `jobs` and `tenders` need no new template work |

**Recommendation: (c)**, mapped to **P1** (one source of truth for what a card shows —
the panel now decides its noun from the engine's marker, and the page deciding its
tiles from a hardcoded four is the same defect one surface over) and **P3** (not a
premature abstraction: there are already two kinds and `CLAUDE.md` names two more
coming). **(b) is the trap** — it is what "fix the noun" sounds like, and it would
leave two of the three wrong tiles standing while reading as done.

**The question for him:** *for a dataset like the contractor directory, should the
overview show only the row count and how much of it has been fetched — or do you want
the four tiles kept, with the ones that do not apply shown as blank rather than `0`?*
`0` is the specific problem: it reads as a measured zero rather than as "not a thing
this source has", which is the same distinction `last_successful_run` already documents
for a crawl that never ran.

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

> **RULED 2026-08-21 — [R-40](RULINGS.md#r-40--dec-10-is-built-before-the-profile-crawl-not-after-it):
> built BEFORE the profile crawl.** On 34,834 profile pages a parser defect found
> afterwards costs 11 hours of re-fetching to fix what should be minutes of
> re-parsing, which is a direct contradiction of why the seam exists. Kept here
> rather than deleted, because the measurement below is what produced the ruling.
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
crawl: `extension/app.js:848` posts `crawl_honour_delay` → `scrapex/capture.py:95`
reads it → `scrapex/connectors/base.py:560` emits the sentence → `job_log_entry`
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

**~~Q-17~~ · RULED 2026-08-22 — see [R-45](RULINGS.md#r-45--the-site-is-the-only-source-of-truth-and-a-field-the-table-does-not-need-goes-in-the-rows-card).**
He refused both options this question offered. **We never translate** — where the site
publishes no usable English, the node keeps its Arabic identity and no English name.
And the readiness level is **neither a column nor discarded**: fixed columns in the
table, everything else in the **row's own card**, because contractors will have several
sources and a column is a promise every source must keep. The question is kept below,
unedited, because the answer is only legible beside what was asked (**C4**).

**Q-17 · The licences: a readiness level almost nobody publishes, and three activities the site names wrongly in English.**
Two decisions in one place because they are the same table.
*(a)* `مستوى الجاهزية` is **empty on 1,490 of 1,500 rows** — five distinct values across
the other ten (Gold, Silver, `Dimond` as the site spells it, Basic).
`classification_membership` has no column for a per-membership attribute, so storing it
is a **migration** for a fact 0.7% of rows carry. Options: migrate now; leave it read
and unstored, which is what today does — `read_licensed_activities` returns it either
way, so the day it earns a column it is a re-parse of stored snapshots and not a
re-crawl; or drop it.
*(b)* For the **3 activities of 22** whose English half the site publishes truncated or
simply wrong, the node is stored under its Arabic identity with **no English name**.
Options: leave it empty and let the site fix itself; write our own English, which is a
mapping only you can authorise (**R-02**); or show the raw published string, `Civil
Engineering -`, which is the same string for two different activities.

**Q-18 · Do the two contractor-relation groups still get tables?**
`R-19` ruled child tables for all five groups, on one profile. Measured over 2,419:
`main_contractors` carries rows on **0** pages and `sub_contractors` on **2**. They are
also the only two of the five that are **relations between contractors** rather than
classifications, so `dataset_relationship` — which now has its first tenant — may be
their home rather than the taxonomy. Options: build them now at 2 rows; wait until the
34,834-page crawl finishes and re-measure, which costs nothing because the snapshots
keep the evidence; or rule them out and record it.

**Q-16 · Should anything in CI go red when the published engine falls behind the
source — and the answer got harder the day it was asked.** The repository can prove
that the tag he is *told* to push is the tag the workflow accepts (`OP-32`). It
cannot prove a release happened: the tag list is absent from a `fetch-depth: 1`
checkout and the hub is a network fetch, so a test that looked would either skip
silently or flake, and both are worse than not looking.

**WHAT CHANGED THE QUESTION.** When this was written the source was 0.3.0 and the
published engine was 0.2.1 — two bumps behind, with the newest installable build
silent on a double-click. Hours later he tagged `engine-v0.3.0`, and `R-35`
immediately moved the source to **0.3.1** for migration `0010`. So the steady state
of this
project is **source ahead of published**, by design: `VERSION` moves on a contract
change and releases are cut by hand (Decision 4).

**Which kills option (b) rather than merely weakening it.** A weekly job that fails
whenever published < source would be red in the *normal* case and silent only in the
minutes after a release — the crying-wolf failure
`tests/test_the_published_documents_are_checked_not_announced.py` names in its own
words, reached by arithmetic rather than by bad luck.

**So the live options are:** (a) **nothing** — the gap is expected, and `OP-32`'s
actual defect was three things at once (nothing released across two bumps, a silent
binary, and documents naming a refused tag), none of which a gap alone implies; or
(c) **a threshold rather than a comparison** — red only when the published engine is
behind by more than one minor version, or older than some age, so it distinguishes
*between releases* from *abandoned*. (c) needs a number from him, which is the whole
reason this is a question and not a commit.

*No recommendation on (a) versus (c), because it depends on how often he intends to
release. But (b) is now argued against rather than merely listed.*

**Q-15 · May a session run an unmerged migration against his LIVE warehouse?**
Three times on 2026-08-21 his engine database moved ahead of `main` — v8 against v6
in the morning (`OP-33`, closed by #243), and **v9 against v8** in the afternoon
(`OP-40`). Each instance closes by merging; the class does not.

**What it costs when it happens:** `main` cannot open his warehouse, which means the
**shipped** engine cannot either — so the product is uninstallable-for-him until a
merge and a release catch up. That is the same symptom as `REQ-28`'s black screen
arriving by a different road.

**Why it is his call and not a rule I should take.** The alternative is free and
already exists — `SCRAPEX_DATA_ROOT` gives any session a private warehouse in one
environment variable, and `R-24`'s `carry_over` is the path back. But forbidding it
also forbids the thing that keeps finding real defects: #243's own migration was
written *because* running against his real data exposed a fault a fixture never
would, and `R-24` itself came out of exactly that. So the trade is **evidence from
real data** against **his installation staying installable**, and only he can price
it.

**Three shapes, if he wants them:** (a) never — sessions use a private root and
`carry_over` proves the upgrade; (b) only behind a backup, which is what already
happens informally (`pre-ledger-repair`, `pre-reapprove`, `pre-upgrade-*` are all
sitting beside his database now); (c) freely, and accept that `main` lags — with a
rule that the migration must merge the same day.

**Q-14 · ~~What identifies an ACCOUNT, so a database can belong to one?~~ — ANSWERED 2026-08-21: (a), the signed-in address.**
→ [R-34](RULINGS.md#r-34--an-account-is-the-signed-in-address-and-a-warehouse-records-whose-it-is).
He settled it by naming one: «اجعلها تخص حساب muhammad.bayoumi.ali@gmail.com», and
his own warehouse now carries it in `scrapex_meta.account_owner`. The options and
the reasoning are kept below, because the trade-off is the only place the two
rejected halves are written down.

**Q-14 (as asked) · What identifies an ACCOUNT, so a database can belong to one?**
`REQ-26`. He ruled that a database belongs to one account and not to everyone on the
machine, and that two Chrome profiles with two accounts get two databases. Measured:
**no account concept exists** — `DATABASE_ROOT` is `~/.scrapex` per operating-system
user, and a grep for `google_account`, `user_email`, `signed_in` or `def account`
returns nothing. Options:
**(a)** the **Google address** signed into the panel — matches how he described it
(«لو عامل sign in بكذا حساب») and survives a Chrome profile being recreated, but ties
the warehouse's location to an identity the tool does not yet read anywhere.
**(b)** the **Chrome profile** the extension runs in — matches the second half of what
he said, needs no sign-in at all, and is what the native-messaging host already knows;
but two accounts used in ONE profile would share a database, which is the case he
objected to.
**(c)** an **explicit choice in the panel**, a named workspace the user picks. No
guessing, works with no browser at all, and it is the only option that lets one person
keep two warehouses deliberately — at the cost of a first-run question.
*No recommendation offered: this decides where other people's data lands, and (a) and
(b) each fail exactly one half of what he described. It needs his intent, not a
default.*

**Q-13 · R-19: child tables — as five bespoke tables, or as five child DATASETS
referencing a taxonomy?**
He asked for his own ruling to be tested before it was built — *«ادرس حكمى اولا هل هو
صحيح ام هناك الافضل»*, captured as
[REQ-23](REQUESTS.md#req-23--test-my-own-ruling-before-building-it-with-strict-review-criteria)
— against strict criteria. Measured in
[R19-CHILD-TABLES-MEASURED.md](R19-CHILD-TABLES-MEASURED.md): 11 criteria, 5 shapes,
518,490 rows.

**The ruling's substance is upheld.** JSON costs **1,168 ms** on the query R-19 names
against **0.6 ms** for the best shape — 47x worse than even a bespoke table, and
nothing in the measurements favours it.

**What the ruling did not decide** is how the value itself is stored, and one
criterion nobody had raised turns out to be the biggest gap in the table: when the
site **relabels a category**, a shape holding the string per row rewrites **103,698
rows in 5.9 s**; a shape holding it once rewrites **1 row in 0.1 ms** — about
59,000x. A live directory relabels things.

Options:
**(a)** R-19 read literally — five bespoke SQL tables. Five migrations, five read
paths, and bespoke work in the export, the API, the panel and the CLI, because none
of them speak "bespoke table".
**(b)** Five child **datasets** in `generic_record`, value as a `classification_node`
reference. **Zero migrations**; `dataset_relationship` and `classification_node`
already exist and hold **0 rows each**; provenance is *enforced* by
`source_snapshot_id NOT NULL`; one export tab per dataset from machinery already
built. Costs ~235 MB and ~28 s per full re-extraction.
**(c)** `classification_node` + one bespoke link table — **4.7x less storage** and
**7x faster to write** than (b), at the price of (a)'s bespoke work everywhere.
*Recommended: (b). It wins or ties every operational criterion; (c) is the fallback if
the storage figure is judged too high.*

**RULED 2026-08-21 — (b)**, after he asked for the three to be compared **on time**
specifically. → [R-30](RULINGS.md#r-30--r-19-is-built-as-child-datasets-whose-value-references-a-taxonomy).

**Two things found on the way that need his eye regardless of the option chosen:**
R-19's own sample reported the licensed-activities table as *"one row — the header
only"*, and the committed fixture for a different contractor has **six** — so "empty"
was never general. And `dataset_workbook_tables` returns exactly one tab, justified in
its docstring by *"a contractor directory has one flat table"*, **which any of these
options makes false**; no test anywhere references that function.

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

### OP-20 · ~~CI has not executed since 2026-08-19, and the reason is billing~~ — CLOSED 2026-08-23

> **RESOLVED, and by the owner in one command.** The repository was **made
> public** on 2026-08-20, and Actions came back with it: public repositories get
> unmetered minutes on the standard runners, so the unpaid-minutes block on a
> private free-plan repository simply stopped applying. The switch was confirmed
> at the plan level rather than by the flag alone — `branches/main/protection`
> had been answering `403 Upgrade to Pro` and began answering `404 Branch not
> protected`.
>
> **And the runs are real.** Measured 2026-08-23 on `main`: `CI` succeeded at
> 05:21, 10:30 and 11:19, with the `test` job taking minutes rather than
> failing in seconds with zero steps. PR #220's checks executed in full — `test`
> 5m53s and 12m27s across two runs. So **#214 and #219, both merged with CI
> never having run, have since been verified by real runs**, and SR-23 is a rule
> anyone can follow again.
>
> **The cost this entry predicted was paid in full, and the bill is below.**
> It wrote: *"a red check that means 'unpaid' is indistinguishable at a glance
> from a red check that means 'broken' — which is how a real failure gets waved
> through."* A scheduled workflow had been failing **every day since at least
> 2026-08-16** and nobody looked, because every red looked explained. It is kept
> below rather than deleted, because the reasoning is what caught it.



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

#### The failure it predicted, found and fixed — 2026-08-23

**No number of its own on purpose.** `OP-60` and `OP-61` are held by branch
`feat/the-engine-knows-which-code-it-is-running`, and #263's handoff records them
as that branch's. The rule in [ORCHESTRATION.md](ORCHESTRATION.md) would give me
`OP-60` — an open pull request outranks a branch without one, and #264 is open
while that branch has none — but moving *them* costs two renumbers and
contradicts a committed handoff, and this is not a sibling finding anyway. **It is
this entry's own thesis coming true**, so it belongs inside it.

`Publish the documents the store links to` has failed on **every scheduled run
from at least 2026-08-16 to 2026-08-23** — eight consecutive days, measured, not
sampled. The error each time:

```
the chooser served to owners is not the file this repository tests.
  repository: d43aa7600b053f9ecc473734bd31f75883003facfc80c1865e7bb11b11b3ea2c
  served:     cc04efaff465335b81de2583321437467d8b23d8dfd25579991ec2ec3dc30e80
```

**The served copy was byte-identical the whole time.** Fetching
`https://muhammadbayoumi.github.io/mbiXsite/scrapex-picker.html` on 2026-08-23
gives 10,231 bytes hashing to `d43aa76…` — which *is* the repository's own
normalised hash, and `difflib` reports **zero** differing lines.

**The bug was one shell newline.** `.github/workflows/publish-docs.yml` had:

```bash
mine=$(sha256sum docs/picker/scrapex-picker.html | cut -d' ' -f1)
served=$(curl -sL --max-time 20 "$PAGE" 2>/dev/null || true)
theirs=$(printf '%s' "$served" | sha256sum | cut -d' ' -f1)
```

Command substitution `$(curl …)` **strips every trailing newline** from the body,
and `printf '%s'` puts none back — while `sha256sum` of the file keeps its own. So
`theirs` could never equal `mine` for a file ending in a newline, which this one
does. Proved by construction: the served bytes hash to `d43aa76…`, and the same
bytes with the final newline removed hash to **exactly the `cc04efa…` CI
printed**.

**The docs loop twenty lines above is unaffected, and the asymmetry is the whole
bug** — it *pipes* curl into `sha256sum` instead of capturing it, so nothing eats
its newline.

**Fixed** by hashing the bytes rather than a shell variable: curl writes to
`$RUNNER_TEMP` and `sha256sum` reads the file, with `[ ! -s "$body" ]` keeping
the served-nothing check. Verified locally against the live page — the old
expression mismatches and the new one matches.

**Why it went eight days unread.** Two reasons, and both are lessons rather than
excuses. The guard *"cannot fix what it finds"* by design, so its failure is
normal-looking noise on a schedule nobody watches. And this entry had made every
red check mean "unpaid", so a red that meant "broken" was invisible. **A guard
that cries wolf daily is not a guard**; this one had also never been exercised
against a passing case.

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

The only Python that reads that manifest is `tools/panel_harness.py:121`, a
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
   second `worker_alive` computation at `app.py:2749` that the fix never reached
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
