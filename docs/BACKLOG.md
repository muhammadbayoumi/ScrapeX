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
| live warehouse | `~/.scrapex/marketlens/marketlens.db`, 75.4 MB · 73,162 price observations · 7,332 offers · 3,799 products · 9 sources · 53 migrations applied |

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

### OP-1 · The engine on the owner's machine ran unmerged, half-written code, and the fix is still unmerged
**Status: open — one action away from closed.**
Three crawl jobs failed on 2026-07-29 between 15:23 and 15:25 with
`worker error: name '_host_lanes' is not defined` (`crawl_job` rows `job_aebc47261d01`,
`job_50a7783ad32a`, `job_b094a0510dce` — measured). The engine restarted while `jobs.py`
had the call and not yet the helpers; the commit `1deff23` says so itself. The file is
whole now, but `1deff23` is **not on `main`** and no PR exists for it (`gh pr list` tops
out at #15).
**Next action:** open the PR for `feat/crawl-several-sites-at-once`, merge it, and confirm
`/api/health` after restarting.

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
**Next action:** decide the intended set with the owner (**Q-11**), commit it, and settle
what `source_site.active` is *for* — right now it is a column nobody reads and nobody
maintains. *(That last clause is **inferred** from the mismatch, not from reading the write
path.)*

### OP-3 · Five currencies have no exchange rate, and the cause is a page-shape change
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
**Status: open, worsening.** `REVIEW-2026-07-28` §3 #10 measured 1,820 lines and 82
routes. Measured today: `wc -l` = **2,480**, `@app.` decorators = **89**. The router-factory
pattern that fixes it is already applied inside the same file to four fragments, and a test
has to scrape the file with a regex to learn its own routes.
**Next action:** either continue the extraction the file already started, or state plainly
that the file is allowed to be this size and delete the half-done pattern so it stops
implying a plan.

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

### OP-12 · The repository has no linter, no formatter and no type checker
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
memory `branch-cleanup-pending.md` (2026-07-28) listed three stale branches. Measured today
it is worse — 12 local branches. `codex/selected-card-layout`,
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
has never been run at width > 1 on the owner's machine, and it is unmerged (**OP-1**).
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

## 7. Done — newest first, so it is not re-proposed

| when | what | commit |
|---|---|---|
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
| `SOURCES-REGISTER.md` (07-31) | **live, derived** — the developer's per-source scoreboard, split MarketLens / General. Reads out of the manifest, the connector directory and this file; when it disagrees with `sources.yaml`, the manifest wins. Delete a reference in it when the matching `OP-`/`DEC-`/`BV-` closes |
| `plan-closing-the-gaps.md` (07-25) | **superseded by this file.** Phases 0–2 delivered; its still-live items are DEC-4, DEC-5, DEC-6, DEBT-2, Q-10. Keep for its measured 07-25 snapshot |
| `MASTER-PLAN.md` (07-18/23) | **stale and misleading** — see DEC-1. Its §8 asks the owner to confirm a topology its own header says he already rejected, and it cites a `spikes/` directory that has never existed in this repo. Keep as a design study; correct the header once Q-6 is answered |
| `REVIEW-2026-07-28.md` | **live as evidence, superseded as a queue.** Its open items are OP-4, OP-5, OP-6, OP-7, OP-12, OP-13, OP-14 |
| `column-vocabulary.md` | **live** — the map is the contract; §Status feeds DEC-4 and Q-7 |
| `robots-policy.md` | **live** — SR-8 |
| `data-page-schema.md` | **live** — the Data page ruling |
| `DESIGN-SYSTEM.md` | **live** |
| `recon/heidelberg-materials-eg.md` | **live** — Q-1…Q-5 |
| `COMPATIBILITY.md`, `GENERIC_CATALOG.md`, `db1-domain-database-isolation.md` | **live** — the General/MarketLens split (G0/G1/DB1). Not touched since 07-20; nothing in the last 130 commits builds on them, so their roadmap half is dormant **(inferred)** |
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
