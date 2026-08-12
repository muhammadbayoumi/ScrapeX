# ScrapeX — the one tracking document

Written **2026-07-29**. This file exists because decisions kept getting lost between
sessions. It is the single place where the project's *state* lives: what is settled, what
is broken, what was approved and never built, what shipped but nobody has confirmed, what
we deferred on purpose, and what is waiting on the owner.

It is **not** an architecture guide. It does not explain how the code works. Every entry
carries its evidence — a commit hash, a `file:line`, a number measured against the live
warehouse, or the owner's own words. Anything I inferred rather than verified is marked
**(inferred)**.

**Repository state at the moment of writing**

| | |
|---|---|
| `origin/main` = `main` | `2253308` — *feat(panel): the crawl pace moves to where the owner actually works* |
| checked-out branch | `feat/crawl-several-sites-at-once` @ `1deff23`, **1 commit ahead of main, no PR** |
| working tree | `M sources.yaml` (uncommitted — see **OP-2**) |
| suite, as last reported by a commit | 1494 passed · 1 xfailed · contract parity 3/3 (`1deff23`) |
| live warehouse | `~/.scrapex/engine/scrapex-engine.db`, 75.4 MB · 73,162 price observations · 7,332 offers · 3,799 products · 9 sources · 53 migrations applied |

**How to read an entry.** Every entry has a stable ID (`SR-`, `OP-`, `DEC-`, `BV-`,
`DEBT-`, `Q-`). IDs are never reused; when something is finished, move it to §7 and keep
the ID. Sections are ordered by consequence, not by category — data-correctness sits above
cosmetics everywhere.

---

## 1. Standing rules — settled, do not re-litigate

These are the owner's rulings. Each is one line and its reason. Re-proposing one of these
is a waste of a session.

| ID | Rule | Why | Evidence |
|---|---|---|---|
| **SR-1** | **Source truth is never edited.** What the site publishes is the record, typos included. Rules decide *where* a fact is shown, never *what* it says. | A cleaning rule silently forks the warehouse from the source; the next crawl can no longer tell "the shop fixed it" from "our rule stopped firing". | Owner 2026-07-28: «مصدر الحقيقة هو ما ينشره الموقع حتى لو كان فيه خطأ بشرى… القواعد فقط لمعلومة تُعرض أين، ولكن لا لتغييرها» — *the source of truth is what the site publishes even if it contains a human error; rules only decide where a fact is shown, never change it.* memory `source-truth-never-edited.md` |
| **SR-2** | **Bilingual capture.** Anything a site publishes in AR *and* EN is captured in both — names, category levels, attribute labels *and* values, descriptions, units. A missing translation the site does publish is a **defect**, not a nicety. | The owner reads and reports in both languages and refuses to re-extract to see the other one. | Owner 2026-07-23: «أى محتوى أجيبه من أى موقع متوفر باللغة الإنجليزية والعربية أريد أن أجيبه باللغتين» — *any content available in both English and Arabic, I want in both.* memory `bilingual-capture-rule.md` |
| **SR-3** | **A price is never converted.** A converted number is never shown without the rate that produced it *and* that rate's date. Google Finance is the rate authority. | The one time this was broken it put 3,312 figures in the warehouse that no page had ever printed. | Owner 2026-07-26; `scrapex/config.py:74`, `scrapex/rates.py:5`, `grid.js:1382` |
| **SR-4** | **Authority first, then recency, for exchange rates.** A rate *provider* always outranks a shop's own published rate; among providers the newest wins. A shop's rate is still used where no provider published one. | advancedcastle publishes a SAR/EGP ratio of 13.46 while pricing its own Egyptian pages at 11.768. On recency alone that number would have converted every EGP-priced row in the warehouse. | `69e986c`, migration `0054` |
| **SR-5** | **Retention never deletes a price observation.** Space is reclaimed by *building* a new database and switching a pointer; the predecessor is sealed beside it and never removed. The UI may never say "recovered space" (a test fails if that phrase appears). | Observations can never be re-observed. | memory `scrapex-phase5-integrations.md`; append-only enforced by SQLite triggers (ENGINEERING A7) |
| **SR-6** | **An unchanged price is confirmed, not appended.** History is a timeline of real changes. Availability and stock have no history at all — latest state only. | A year of unchanged diesel used to be 52 identical "history" rows. | memory `scrapex-price-semantics.md` |
| **SR-7** | **Development beats crawling.** A migration blocked by a running crawl → pause the crawl (never cancel), back up, apply via `init-db`, restart, resume. Do not ask again. | A crawl is repeatable and resumable; a half-applied change is not. | Owner 2026-07-29: «وقف الزحفة … التطوير اهم من الزحف» — *stop the crawl; development matters more than crawling.* memory `development-beats-crawling.md` |
| **SR-8** | **robots.txt: `Crawl-delay` honoured automatically; `Disallow` NEVER enforced and never a warning** — one info-level job-log line only where a disallowed path intersects one we crawl. | The owner wants uninterrupted crawling, but wants a future block to have a traceable cause. | Owner 2026-07-22, `docs/robots-policy.md` |
| **SR-9** | **Silence is never permission to go faster.** Absent config reads as *honour the delay* at every layer. Turning it off announces the number it is overriding. | A crawler that outpaces a site by default gets its owner blocked without him choosing it. | `c63ec21` |
| **SR-10** | **Every setting lives in the extension; the web page is display-only** — but display-only is not blank: the page must still show every value it stopped editing. | A setting that exists only on the web page is a setting the owner does not have — proven: crawl pace was built, plumbed to `HttpFetcher`, and he asked for it as if it did not exist. | Owner 2026-07-29: «لا اريد اى اعدادت على صفحة الويب الاعدادت كلها على extension بينما صفحة الويب للعرض فقط». Enforced by `tests/test_settings_live_in_the_extension.py` (`2253308`), not by memory |
| **SR-11** | **Delete is two actions, never one.** *Stop tracking* keeps every row ever collected; *Erase collected data* keeps the registration. Both confirmed by typing, not by an OK. | Removing an entry is not a claim that none of the data happened. | Owner 2026-07-28, `412785b` |
| **SR-12** | **A rename moves the data with the name** — all nine tables in ONE transaction, manifest rewritten only after the rows have moved. | Renaming the manifest alone would not rename a source, it would orphan one. | `412785b`, `scrapex/sources_admin.py:11` |
| **SR-13** | **Nothing is collected that is not declared in `sources.yaml`.** The manifest is an extraction contract with a scope guard that rejects out-of-contract rows. | Owner principle: «له أساس ليس جمعاً عشوائياً» — *it has a basis, it is not random collection.* | `sources.yaml:1-18` |
| **SR-14** | **GPP: the latest published price only, never their paid historical series.** Our history accumulates from our own weekly observations. | A licence obligation, and it is tested (ENGINEERING T6). | `sources.yaml:436`, memory `scraper-ecosystem-design.md` |
| **SR-15** | **Names state their language: unmarked = English, `_ar` = Arabic; the key and the label are the same word.** A monolingual Arabic source fills `product_name_ar` and leaves `product_name` **empty** — never "helpfully" carry Arabic into the unmarked column. | The reader had to learn a private vocabulary to use his own spreadsheet. | `docs/column-vocabulary.md`, migrations `0038`–`0042`, `PAYLOAD_VERSION 2` |
| **SR-16** | **Column presence is per source.** Every gate in `reports.column_presence` asks *this* source's own rows, never a global table. | A global `currency_rate` count once put fuel-implied USD estimates on every shop. | memory `scrapex-columns-classification.md` |
| **SR-17** | **Detail groups are a closed vocabulary of seven, and a code the map has never seen goes to the owner before it gets a group.** | A silently widened catch-all misinforms every later reader. | Owner 2026-07-28, migration `0046`, `scrapex/vocab.py` `_DETAIL_GROUP_BY_CODE` |
| **SR-18** | **Commit and push after each plan step; do not batch, and do not end a step asking "shall I continue?".** | The owner works across parallel sessions and worktrees; unpushed commits are invisible to them — that is how a duplicate `0012` migration happened. | Owner, repeated. memory `commit-and-push-each-step.md` |
| **SR-19** | **Never `git add .` or stage a path list — read the whole cached diff before committing.** | Twice this swept another session's half-finished work into a commit and broke `main` from a clean checkout. | `e2573e1` ("I staged that file after reading only `--stat`. Reading the whole cached diff is the rule that would have caught it, and it is the rule I agreed to"), `0a2209c` |
| **SR-20** | **Commit messages carry no double-quote characters** (PowerShell here-strings break on them). | Mechanical, but it costs a retry every time. | memory `git-commit-heredoc-quotes.md` |
| **SR-21** | **Every worker other than me produces drafts.** `codex/*` branches and other sessions are pull requests awaiting review with `file:line` evidence, never work to build on. | The owner said plainly he does not trust anyone else in the code; the arrangement only survives because the audits catch things (17 real defects past 527 green tests). | memory `scrapex-review-gate.md` |
| **SR-22** | **Build, don't stop to review** — write code that already satisfies the review rules; pause only for genuinely forking product decisions. | Owner 2026-07-16: «انا مش عاوز اراجع حاجة دلوقتى انا عاوز ابنى ولكن بكود يحترم المراجعة» — *I don't want to review anything now, I want to build, but with code that respects the review.* | memory `build-not-review-bake-rules-in.md`, `ENGINEERING.md` |
| **SR-23** | **CI must be green on every push.** `.github/workflows/ci.yml` runs on `push` and `pull_request`: manifest validation, a floor of ≥40 collected panel tests, the full pytest suite, the JS↔Python contract-parity gate, and the extension `node:test` suite. | A guard that can vanish quietly is the defect — the panel suite silently skipped for months. | `.github/workflows/ci.yml`, `48ec48b`. *(The "must be green" phrasing is the observed convention across every commit message, which reports the suite total — **inferred** as a rule, not stated by the owner in those words.)* |

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

**Next action:** decide the intended set with the owner (**Q-11**), commit it, and settle
what `source_site.active` is *for* — right now it is a column nobody reads and nobody
maintains. *(That last clause is **inferred** from the mismatch, not from reading the write
path.)*

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

### OP-4 · `webui/app.py` grew 660 lines in one day and is now 2,480 lines / 89 routes
**Status: open, and it has grown at every measurement.** `REVIEW-2026-07-28` §3 #10
measured 1,820 lines and 82 routes. Measured 2026-07-29: **2,480** lines, **89**
routes. **Re-measured 2026-08-09: 2,955 lines, 95 routes** — another 475 lines in
eleven days, while `catalog_api.py` (122 lines) and `database_api.py` (82) were
extracted out of it and did not slow it down. The router-factory
pattern that fixes it is already applied inside the same file to four fragments, and a test
has to scrape the file with a regex to learn its own routes.
**Next action:** either continue the extraction the file already started, or state plainly
that the file is allowed to be this size and delete the half-done pattern so it stops
implying a plan. *"Keep extracting when there is time" is not a third option — that is
what has been happening.*

### OP-5 · `reports.py` computes the six history statistics twice, and the price has already been paid once
**Status: open.** `export_source_table` (`scrapex/reports.py:982`) and `table_payload`
(`:1664`) each carry their own copy. This was a maintenance argument until the review found
the owner's own comment in the code recording that adding one column shifted
`observations` / `min` / `max` / `previous` by one during the brand work.
**Next action:** one expression source read by both.

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
| ت1 restore / start-fresh always broken while the worker thread runs | **unknown** — both routes now call `app.state.runner.release_database()` (`app.py:1966`, `:1998`), which may already be the answer |
| ت2 the heartbeat is written between jobs only, so the engine declares itself dead mid-crawl | **unknown** — `2d82be8` *"a busy worker is alive, and says what it is busy with"* may cover it |
| ت3 every run rebuilds the full derived timeline of every touched offer | **still present by design** — see **DEBT-4** |
| ت8 the `grid.js` XSS guard scopes itself by splitting on two comments and leaves a gap | **unknown** — grepping `tests/test_vendor.py` for `xss` returns nothing, so the guard has been renamed, moved or removed |

**Next action:** refute ت1, ت2 and ت8 against running code (the review's own method: run it,
don't read it). Two of them may already be closed and are costing us attention for nothing.

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

**Status: open.** No `ruff`, no `mypy`, no `eslint` anywhere (`REVIEW-2026-07-28` §9).
Every style and type rule in `ENGINEERING.md` §2 (Q5: "type hints everywhere") is enforced
by attention alone.

### OP-13 · There are no end-to-end or chaos tests
**Status: open.** Killing the engine mid-job, corrupting a checkpoint, force-closing the
browser — all named in the project's own test matrix (ENGINEERING T7), none implemented
(`REVIEW-2026-07-28` §9). This is the class of fault that produced OP-1.

### OP-14 · The Native Messaging size ceiling is documented in the wrong direction (probably)
**Status: open, unverified.** `scrapex/native.py:5` says the megabyte cap applies
extension→host. The reviewer believes it is host→extension, which is exactly the direction
`GET_RECORDS` results travel. He tried to fetch the documentation twice, failed, and
refused to assert it from memory (`REVIEW-2026-07-28` §9). Worth settling because it
decides whether a large record set can be returned at all.

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
flight. **No test exercises any of it** — every panel test opens the panel,
drives it, and ends. Issue #161.

Two halves, failing differently. *Closing never stops a run* is probably true —
the engine owns execution — but the panel holds a poll loop and, since #152, work
that begins on `load`; if the close path aborts a request the engine reads as a
cancel, a long crawl dies because the owner closed a side panel to read a page,
and they would never connect the two. *Reopening reconnects* is the fragile half:
a reopened panel is a **fresh document** that must find the running job and
re-attach to its progress. If it shows idle, the owner sees a crawl vanish while
it is still running, and starts it again.

Five minutes by hand settles it: start a long crawl, close the panel, wait 30
seconds, reopen.

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
**RE-MEASURED 2026-08-09: 117 local branches, 106 remote, 21 worktrees.**

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

---

## 4. Built, not yet verified

### BV-1 · Crawling several sites at once
`1deff23`. 1494 tests green including a three-way barrier proving three sources are inside
`capture` simultaneously. But it is **off by default** (`crawl_parallel_sources = 1`), it
has never been run at width > 1 on the owner's machine. It is **merged** now — that half
of this entry closed with **OP-1** — so the only thing left here is the run.
**The check that would settle it:** merge, set the width to 3, run three sources on three
hosts, and confirm from `crawl_job` that they overlap and that a pause still stops all of
them.

### BV-2 · The WAL / sealed-archive cluster
`234cdc1`, `4103e48`, `4dfb9e8` (plus the integration PR #10). Three of the four faults are
POSIX-only — on Windows an open handle blocks the rename, which is the accident that hid
them. The author is explicit for fault D: *"I could not make D's test fail on this machine,
and did not pretend to. Local SQLite is 3.50.4, where optimize behaves; CI's 3.45 is where
the fault bites."*
**The check that would settle it:** a green CI run on `ubuntu-24.04` for those tests. Look
at the run, don't assume it.

### BV-3 · Settings moved into the extension panel
`2253308`. Five Playwright tests, and a guard that fails the build if the web page grows an
input again. Not yet confirmed by the owner actually using it. Worth telling him: the live
setting is `crawl_honour_delay = '0'` — **the delay is currently NOT being honoured**, which
is a real choice with real consequences (SR-9) and may have been made by accident while
testing the new control.

### BV-4 · Sika's trade tier reaching the warehouse
`436105c` reported 0 of 73,084 observations carrying a trade price. Measured today: **78**
observations carry `price_trade`. The fix works. But `059820d` recorded that `price_trade`
reaches `BROWSE_COLUMNS` with **no formatter and no alignment** in the grid — latent then
because no source published one; those 78 rows make it live now.
**The check that would settle it:** open a sikaegshop record in the Data page and look at
the Trade price cell.

### BV-5 · Sources re-activated, then partly switched off
`df34761` activated four connectors that had been built and left off. The uncommitted
manifest edit has since switched five sources off (**OP-2**). Nobody has confirmed the
intended end state.

---

## 5. Declared debt — deferred on purpose, with the reason

| ID | Debt | Why it was acceptable |
|---|---|---|
| **DEBT-1** | **Migration `0047`'s coverage guard runs *after* the MADAR upgrade that fills its NULLs**, so it checks a narrower condition than its comment claims. | `0047`'s sha256 is verified on every connection and there is no re-stamp path; replaying it over the real pre-0047 warehouse gives an identical result with or without the fix. Recorded as a **strict xfail** at `tests/test_db.py:194` — this is the "1 xfailed" in every suite line, and it should stay visible. (`c7fa4ea`) |
| **DEBT-2** | **ETag / Last-Modified persistence across runs.** In-memory validators exist in `HttpFetcher`; they are not persisted. | Naive 304-skipping breaks price *confirmations* (`last_confirmed_at`) and the volume canary. It needs a content-cache design, not a flag. Owner approved the deferral 2026-07-22. |
| **DEBT-3** | **`_derive_seen` rebuilds the whole derived timeline of every offer a run touched, unconditionally** (`scrapex/ingest.py:1029-1043`). | Gating it on success *was* the incident: one contained error left every offer with an appended observation but no `offer_state` and no `price_period`, and the same-day dedupe then blocked the re-append that would have repaired it. The cost is accepted; ت3's claim that it is ~396,000 operations was never refuted (**OP-6**). |
| **DEBT-4** | **advancedcastle's Egyptian price is deliberately not crawled.** | It is a *conversion*, not a price the merchant set — the EGP/SAR ratio is constant at 11.768 across five probed products. `price_basis` / `original_price` live on `COMMODITY_PRICE`, not `PRODUCT_PRICES`, so recording it honestly is a schema migration and therefore the owner's call. He took it: capture the published **rate**, never the converted price. Note the warehouse *would* keep the two countries apart correctly (`source_offer` is keyed on `country_code_alpha2`) — the reason is the derivation, not a modelling limit. (`e639310`, `b43405c`) |
| **DEBT-5** | **`region` keeps its name in three places on purpose** — the manifest's `default_region` / `extract.regions`, `tax_rule.region`, and `pricekey`'s own field. | They *scope* a row rather than describe it. The column itself did move (`0042`). |
| **DEBT-6** | **`origin` and `spec` are hashed into the price key but no connector supplies them** (`scrapex/ingest.py:597-599`, its own comment: "Not collected by any connector yet"). | Wired and unreachable. Harmless today; it matters the day a connector starts publishing one, because the field set changing is `fields_changed`, not `price_change`. |
| **DEBT-7** | **Named in the UI as not built:** funnel HMAC signing, adaptive batching, two-way Sheet sync, proxy / anti-bot, connector-drift repair, OTA updater. | Post-release, demand-driven. Saying so in the interface is what keeps it honest. (memory `scrapex-phase5-integrations.md`) |
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

**Q-1 · Heidelberg Materials Egypt: how should the price matrix be modelled?**
Their price is a function of product × city(46) × segment(5) × plant(3) × tier(2) and
`PRODUCT_PRICES` has a column for none of the four (`docs/recon/heidelberg-materials-eg.md`
§4.1). Options: **(a)** public price only — one row per product, zero schema change, loses
~95% of what they publish; **(b)** synthetic variants via `variant_axes` — captures
everything with no migration, but calls a pricing context a "variant" and the variant UI
will present them as choices; **(c)** widen the contract with real `city` / `segment` /
`plant` / `qty_tier` columns plus pricekey identity fields — correct, and the largest change.
*Built naively, one product's ~276 prices would read as the same offer changing price
repeatedly inside a single crawl.*

**Q-2 · Heidelberg: `maxPrice` (1,950) is never displayed; the site shows `salePrice30*`
(3,950.02).** Record only the displayed one, or both with the unshown one flagged?

**Q-3 · Heidelberg: which customer segments?** `Y6` is what the public sees; `YM`/`YT`
publish 5 prices each; `YO`/`YR` publish none. All five, or the public one?

**Q-4 · Heidelberg: VAT.** Record `evidence: stated, rate_pct: 14` scoped to the order
total, or `unknown` for the listing price? *(My reading: the site makes no VAT claim about
the per-tonne price, so `unknown` is the honest answer.)*

**Q-5 · Heidelberg: is a 9-product source worth a bespoke connector at all?** Two requests
for ~211 real Egyptian cement price points — cheap to run, but it is a new connector class
and possibly a contract change.

**Q-11 · Which sources should actually be running?** See the table in **OP-2**. Right now
the manifest on disk, the manifest on `main`, and the warehouse give three different
answers, and the on-disk one is uncommitted so it will vanish.

**Q-9 · Exchange-rate cadence.** Refreshing every currency GPP prices in is ~93 fetches per
refresh, ~372 Google Finance requests a day (raised in `c63ec21` rather than quietly
changed, because Google Finance being the rate authority is your ruling). Options: keep it;
reduce the cadence; or fetch only the currencies the *active* sources actually price in.

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

The strip is now line-by-line: a whole-line comment is dropped, a line
containing any quote is kept verbatim, otherwise a trailing `//` goes. The trade
is stated in the comment — a comment mentioning `fetch(` beside a string now
causes a loud false failure instead of a real one being swallowed.

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

### OP-19 · The chaos test races the startup sweep it is checking — FIXED 2026-08-12

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

**Four runs in four, green.** And an honest note on the check: removing the wait
again passed three runs in three that afternoon, having failed three in four
that morning. A race that depends on machine load cannot be reproduced on
demand, so the mutation check proved nothing — which is precisely why "it passes
now" was never evidence in the first place. The proof is structural and readable
in the code: health is answered by the HTTP thread the moment the port binds,
and the sweep runs on the worker thread after it connects. Two tests in
`test_jobs.py` hold the marker's two properties deterministically.

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
