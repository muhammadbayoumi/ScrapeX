# Drive without a server — the multi-device data plan

**LIVE. Written 2026-08-22, on his instruction «افتح جلسة session تبدا فى خطة
drive» ([REQ-34](../REQUESTS.md#req-34--open-a-session-that-starts-on-the-drive-plan),
[R-46](../RULINGS.md#r-46--the-drive-track-starts-now-and-r-44s-blanket-deferral-is-amended-to-cover-only-what-costs-crawl-time)).
Phase 0 is BUILT in the pull request that carries this file. Phases 1–5 are not
started.**

This plan lives in the repository and not in `~/.claude/plans/`, per
[R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository). It is
the plan for the half of ScrapeX that `CLAUDE.md` cannot hold: the **data**, which
is not committable, and which by
[R-43](../RULINGS.md#r-43--drive-is-the-single-source-of-truth-for-data-the-repository-stays-it-for-code)
lives on Drive while the repository stays the single source of truth for code.

**Method chosen (`C6`, [APPROACHES.md](../APPROACHES.md)): A2 — measure, don't
reason — for every number below, and A7 — mutation testing — for every guard
Phase 0 adds. A2 was picked because the audit this plan builds on was one day old
and four of its claims did not survive re-measurement; A1's diagnose-confirm-fix
governs Phase 1 onward, where nothing is built before he rules.**

---

# READ THIS FIRST · two things to act on before anything else in this plan

## ① You have been warned about the wrong button, for two days

**`drive-restore` is SAFE.** It downloads the latest backup, checks its size and
tells you what it found. Its own code says *"DOWNLOADED, NOT RESTORED"*
(`extension/app.js:5881`) and the button is labelled **"Fetch the latest backup"**
(`extension/app.html:1892`). Nothing on the panel's path can replace your warehouse.

`docs/STATE.md` and `scrapex/warehousemerge.py` both told you in capitals never to
press it. That was wrong, and it was wrong in the expensive direction: **the control
that really does displace your only copy is the command `scrapex restore-database`,
and until this branch it asked nothing at all** — no flag, no phrase, while
`start-fresh` beside it made you type one. It now requires
`--confirm "replace my warehouse"` and its refusal points at `merge-warehouse`
instead. Both documents are corrected in place rather than quietly rewritten (`C5`).

## ② Two numbers from the other machine, and they take thirty seconds

Everything in the next section is analysis you cannot act on. **This you can.** On
the machine that is *not* this one, run:

    scrapex merge-warehouse --status
    sqlite3 "file:$HOME/.scrapex/engine/scrapex-engine.db?mode=ro" "SELECT COUNT(*) FROM price_observation;"

That pair settles the only open question below, and **nothing on this machine can
substitute for it.** This warehouse holds **92,740** price observations; if that
machine's count is greater than zero, its history has never had a route across, and
`OP-46` is the work that gives it one.

---

# The price half of the warehouse has no route between machines

**A merge CANNOT carry price history, and no merge has been asked to yet.** Both
halves of that sentence are measured, and keeping them apart matters: the first is a
defect in the code, the second is why nothing is lost *so far*. `OP-46` in
[BACKLOG.md](../BACKLOG.md) carries the full working; this section is here so it is
not found by reading down to §3.4.

`warehousemerge.merge` inserts into exactly three tables. **There is no INSERT for
any price table anywhere in the module.** Measured read-only against
`~/.scrapex/engine/scrapex-engine.db` on 2026-08-22, with the profile crawl in
flight:

    merge covers                                    44,525 rows
    EVIDENCE rows no merge path covers             106,138
      of which price_observation                    92,740     append-only by trigger
    raw_snapshot, the page behind a price                 0     nothing can recompute them
    business_date span                    2014-05-19 .. 2026-08-16     608 distinct dates
    observations by source           GPP_ENERGY 70,747 · MADAR 7,548 · SPARK_ESHOP 6,969 · nine more

**Twelve years of price history with no page behind it.** `price_observation` is
append-only by `trg_price_obs_no_delete` / `trg_price_obs_no_update`, and
`raw_snapshot` holds **0 rows** — already written down twice in this repository, at
`scrapex/rowspec.py:219` and in migrations `0056`/`0057`. These rows are not derived
from anything on disk; they *are* the record. And `price_observation` is the table
this warehouse was originally built for — `R-32`'s correction says price is one
category and filing it as the whole thing was a mistake; here the same mistake
arrives from the other side, in the tool built for `R-43`.

## 1 · Has anything been lost?

**Not on this side — and the distinction between "cannot carry" and "did lose"
is the whole of the honest answer.** Nothing here has been deleted or overwritten;
what is missing is a *route*. Whether the other machine has history that has never
had one cannot be determined from here, and that limit is itself the finding.

- **`merge` records nothing.** No merge table exists, and no `scrapex_meta` key
  mentions one. Nothing in the warehouse says a merge ran, when, or from what file.
- **There is no link from a stored page to a run.** `generic_page_snapshot.crawl_run_ref`
  is free text and **`crawl_run` has no `run_ref` column at all**, so the obvious
  probe — pages naming a run this machine never performed — cannot be built. A
  fallback time probe put **0 of 29,906** snapshots inside any local `crawl_run`
  window, because `crawl_run` belongs to the price pipeline and the contractor
  crawls write no row there. Both probes are reported here because their failure is
  the answer.
- **What can be said.** All **140** distinct `crawl_run_ref` labels follow this
  machine's own conventions (`profiles-2026-08-22`, `dammam-2026-08-21`,
  `residual-2026-08-21-region_id_1-…`) on one continuous local timeline
  2026-08-17 → 2026-08-22; the 1,728 null-ref pages are the documented
  pre-`--run-ref` era; and the growth from `R-43`'s 20,379 to 29,906 is fully
  accounted for by the running profile crawl (7,798 under `profiles-2026-08-22`).
  **No page in this warehouse looks imported.** The lock was claimed at
  `2026-08-22T07:19:56Z`, which proves `--machine` ran; `--from` can be neither
  confirmed nor denied from here.
- **And it does not change the answer.** Whether or not `--from` was supplied, no
  price row could have crossed in either direction, because there is no INSERT for
  those tables. A merge that ran would have carried **0%** of the other machine's
  price history and said nothing about it — which is a route that does not exist,
  not a deletion that happened.

**What would settle it is the two commands at the top of this file** — nothing else
is needed, and nothing on this machine can substitute for them.

> **AND THE WORDING HERE IS DELIBERATE, because the first draft of this section
> overstated it.** It said the merge *"silently discards"* the other machine's price
> history. What is measured is narrower and more useful: **the merge cannot carry
> price history, and nothing has yet asked it to.** The defect is real and the
> exposure is real — the moment he runs `--from` with price rows on the far side,
> they will not arrive and nothing will say so — but no loss has been demonstrated,
> and claiming one would have sent him looking for missing rows instead of at a
> missing `INSERT`.

## 2 · Is it recoverable?

**Yes — in every scenario that can be enumerated, and the trigger is why.**

- Append-only means nothing this side did could have deleted anything. Rows never
  read are still where they were: on the other machine.
- A second merge with a fixed path recovers them, and is safe to repeat:
  `ux_price_obs_dedupe (offer_id, business_date, record_hash)` makes it
  insert-if-absent, and `record_hash` is content-derived, so it is stable across
  machines. That is the same property that makes the existing merge idempotent.
- Neither destructive path erases: `EngineDatabase.restore` and `storage.restore`
  both move the current file to `<stem>.replaced-<stamp>.db`. And `drive-restore` —
  **the button `STATE.md` warned about in capitals — does not restore at all**
  (§2.2a). So none of them can have destroyed the other machine's copy.
- **The one thing that could make recovery impossible is the defect Phase 0 just
  fixed:** `init-db` advancing that machine's schema with no backup, which is
  exactly what `warehousemerge._same_shape`'s own refusal tells him to run.

## 3 · What is the smallest fix?

**Yes — the merge simply has no INSERT for that table.** Two fixes, both priced.

| | cost | what it buys |
|---|---|---|
| **stop the harm** | **~15 lines** in `merge` | count what no path carries and refuse, or report it loudly. It would name **174,487 rows across 5 tables** today. Turns a silent total loss into a named refusal, and needs no ruling |
| **carry the rows** | **five `INSERT…SELECT`s** | each keyed on its natural key with a subquery resolving the parent's local id — the pattern `merge` already uses for `html_dict_id`, so it builds **on** the module rather than beside it |

The chain resolves further than the four-level remap §5 first estimated:

| obstacle | measured |
|---|---|
| `source_offer`'s `branch_id` leg | **0 non-null, and no `branch` table exists** — free |
| `source_offer`'s `selling_unit_id` | 1,238 rows, and `selling_unit` has UNIQUE `unit_code` — resolves |
| `source_product.external_product_id` | **0 NULLs of 9,270** — resolves to `(source_key, external_product_id)` |
| `source_variant` | **11 of 13,681** satisfy neither partial unique index — unresolvable, and must be NAMED in the refusal rather than dropped |
| `price_observation.snapshot_id` | NULL on every row — free |
| `price_observation.run_id` | **NOT NULL on all 92,740**, pointing at `crawl_run`, which has no natural key. The only real decision in the fix, and it is **`Q-23`** |

**Recommended order, and it is deliberately not "build the fix":** land the refusal
first, because it is 15 lines, needs no ruling of his, and converts the one failure
mode that cannot be noticed into one that cannot be missed. Then ask him `Q-23` and
carry the rows.

## And one thing he should see, because I have been warning him about the wrong button

`STATE.md` and `warehousemerge.py` both told him, in capitals, never to press
`drive-restore` on the other machine because it REPLACES the live warehouse. **It
does not** — it downloads, checks the size and reports (§2.2a). The destructive
control was `scrapex restore-database` all along, and it had no guard at all until
Phase 0. He has been given a warning about a safe button while the dangerous one sat
unmarked; that correction is his to see, not a footnote.

## And a ruling of his landed while this was being written

`R-45` — **«ما يقوله الموقع هو مصدر الحقيقة الوحيد لا نعدل عليه»**, the site's words
are the record and we never substitute our own. **Nothing in Phase 0 transforms
stored data**: `quick_check` reads, the digest comparison compares, the typed phrase
refuses, and the backup copies. But the ruling is load-bearing for what comes later
and it is recorded here so no phase is designed against it:

- it is the principle underneath this plan's evidence/derived split — evidence is
  what the source said, and that is precisely why `price_observation` must **travel**
  rather than be regenerated from something more convenient;
- it forbids any "normalise on the way into the bundle" shortcut in Phase 1;
- and it constrains Phase 5: encryption may change how the bytes are *stored*, never
  what they *say*.

---

## 1 · His constraints, which this plan does not relitigate

From [R-44](../RULINGS.md#r-44--no-sync-server-and-no-backup-encryption-for-now-and-the-sync-work-is-deferred-behind-muqawil),
all four still standing:

| | his words | what it forbids here |
|---|---|---|
| **No server** | «لن ابنى خادم الان (لا اعرف وجه الاستفادة اصلا منه)» | no service to arbitrate, so **nothing can reject an operation** |
| **No encryption yet** | «لا داعى للتشفير ربما خطة مستقبلية» | Phase 5 exists and stays unbuilt |
| **Solo now, published later** | — | what makes 1 and 2 revisitable rather than permanent |
| **Never commit user data** | `CLAUDE.md`, and it predates all of this | no database, credential or token in git; **GitHub is not a transport** |

**And one thing R-46 changed:** R-44's «أرجئ كلّ شىء» deferred all of it behind
muqawil. He has now opened this track while the 34,834-page profile crawl is still
running. The deferral is amended, not deleted: it now covers only work that
competes for **crawl time or his attention on muqawil**, which is why Phases 1–5
are ordered and gated rather than started.

---

## 2 · What is built today — read from the code, not from the audit

The sync audit of 2026-08-22 is in the
[muqawil plan's appendix](2026-08-22-finish-muqawil-workers-crawl-columns.md).
Everything below was re-read on 2026-08-22 in this worktree. **Four of its claims
were wrong, and they are the reason this section exists.**

### 2.1 · The path a backup actually takes

| file | what it really does |
|---|---|
| `scrapex/archive.py:17` `backup_database` | a point-in-time copy through sqlite3's online backup API; refuses a source that is not there, because it once produced an empty database and reported success |
| `scrapex/bundle.py:158` `build` | that copy as `warehouse.db`, plus a per-dataset JSON Lines + CSV export, plus `panel.jsonl.gz`, plus a manifest with a sha256 for every file |
| `scrapex/bundle.py:279` `verify` | reads it back: every named file present, right size, right digest, no unnamed file, and the row counts re-counted from the files |
| `scrapex/bundle.py:392` `pack` | one zip. **Refuses to pack a bundle that does not verify** |
| `scrapex/webui/app.py:2604` `POST /api/bundle` | the engine's side; hands the panel a name, a size and a digest |
| `extension/drive.js:243` `upload` | resumable, 4 MiB chunks, handles Drive's 308 correctly |
| `extension/drive.js:450` `backUp` | archive first, pack second, pointer third, prune last — so `latest.json` can only ever name files that arrived |
| `extension/drive.js:535` `fetchLatest` | refuses a newer `bundle_format`, refuses a truncated download |
| `scrapex/warehousemerge.py:239` `merge` | ATTACH the other file and add what this one lacks, keyed on natural keys, inside one transaction |

**NO ENCRYPTION ANYWHERE — the audit's finding is confirmed.** `grep -ni
"encrypt\|crypto\.subtle\|aes-gcm\|cipher"` over `scrapex/bundle.py`,
`scrapex/archive.py`, `scrapex/warehousemerge.py` and `extension/drive.js` returns
**nothing**. The bundle is a plain zip of a plain SQLite file, and the transport
is HTTPS to Google and nothing more. His decision, recorded without argument in
R-44; the fact is restated here because Phase 5 is where it stops being true.

### 2.2 · Four things the audit got wrong

**(a) `drive-restore` is not destructive, and the warning about it is false.**
`docs/STATE.md` and `scrapex/warehousemerge.py:38` — that line now carries the
correction — both said, in capitals, *"DO NOT PRESS `drive-restore` ON THE OTHER
MACHINE. Restore REPLACES the live warehouse"*. It does not. `drive-restore` is wired to `fetchFromDrive`
(`extension/app.js:6100` → `extension/app.js:5881`), whose own comment reads
*"DOWNLOADED, NOT RESTORED"* and whose return sentence ends *"It is not installed —
this only checks it is there."* The button's label in `extension/app.html:1892` is
**"Fetch the latest backup"**. There is no `registry.engine.restore` anywhere on
the panel's path.

That matters twice over. The warning **sent a reader to guard the wrong control**,
and the control that is genuinely destructive — `scrapex restore-database` — had
no guard at all. Phase 0 fixes the real one and both documents are corrected here
rather than quietly rewritten (`C4`, `C5`).

**(b) "delete and rebuild everything derived" is not what `--approve` does, and
could not be.** `STATE.md` describes the merge as deduping evidence and then
deleting and rebuilding the derived rows. `generic_record_revision` carries
`trg_generic_record_revision_append_only_delete`, measured on the live file, which
answers `RAISE(ABORT, 'generic record revisions are append-only')` — so a delete is
impossible. What actually happens is an **upsert on the natural key**:
`scrapex/extract/service.py:576` is `ON CONFLICT(dataset_definition_id, record_key)
DO UPDATE`, and `scrapex/taxonomy.py:154` the same for memberships. `grep` for
`DELETE FROM generic_record` across `scrapex/` returns nothing.

The consequence is not academic and it is the opposite of the written claim:
re-approving is idempotent (good, and it is what makes the merge safe), but a
derived row that is **wrong** is never removed — only overwritten if the same
natural key is derived again. A record whose `record_key` changes leaves the old
row behind for ever.

**(c) "48 of 48 primary keys are autoincrement integers" is wrong in both halves.**
Measured on the live warehouse, 56 tables:

- **51 of 56** have a single INTEGER primary key, not 48 of 48.
- **None of the 56 declares `AUTOINCREMENT`.** `grep AUTOINCREMENT` over the DDL of
  every table returns nothing. They are `INTEGER PRIMARY KEY` **rowid aliases**,
  which is materially different and slightly worse: a rowid alias is assigned as
  `max(rowid)+1`, so it is **reused after a delete**. Two machines do not merely
  both hold a `page_snapshot_id = 1`; one machine can hand the same id to two
  different rows over time.
- **5 tables already key on something machine-independent** — `fetch_validator`
  (`url`), `scrapex_meta` (`key`), `source_attribute_promotion` (`source_key`,
  `attribute_code`), `generic_record_node` and `schema_version_field` (composite).
  So a natural key is not a foreign idea in this schema; it is a precedent.
- **Zero `uuid`/`guid`/`ulid` columns exist**, in any table.

**(d) `lease.py` is not part of anything.** Its docstring opens *"DECISION 3: one
device at a time, with restore"* (`scrapex/lease.py:3`) and it is a careful,
well-reasoned module — renewing lease, expiry, atomic write, stable device id. It
has **no production caller at all**: `grep` for `from scrapex import lease` /
`from .lease` across the repository returns exactly one hit, and it is
`tests/test_one_device_writes_at_a_time.py:25`. `may_write` is called nineteen
times, all of them in that test file.

What is actually live is the other lock: `scrapex_meta.checkout_holder`, written by
`scrapex/warehousemerge.py:125` `claim` and read by `holder`, driven from
`scrapex/cli.py:185` `_cmd_merge_warehouse`. It is live **on his own warehouse
right now** — `checkout_holder = 'home-user01'`, `checkout_at =
2026-08-22T07:19:56Z`.

> **So: does the Drive plan supersede `lease.py` or live inside it? It lives inside
> the SHAPE and supersedes the FILE.** The two disagree about one thing that
> matters and `lease.py` is right about it: a lock is held until released, and the
> machine holding it can be closed, reinstalled or thrown away —
> `scrapex_meta.checkout_holder` has **no expiry**, so a machine that dies
> mid-session locks him out of his own warehouse with no route back except editing
> a row by hand. `lease.py`'s answer is `LEASE_MINUTES = 15` with renewal
> (`scrapex/lease.py:38`, `:42`), and its reasoning cites a 34-hour crawl by name.
>
> The recommendation is therefore **not** to keep two locks: it is to give the live
> lock the expiry the dead module already worked out, and to delete `lease.py`
> once its expiry logic and its nineteen tests have moved. Two locks for one
> question is how a merge is refused by one and allowed by the other. **Phase 1,
> gate stated below.**

### 2.3 · Two defects in the merge command's own surface

Both found by reading `scrapex/cli.py` against `scrapex/warehousemerge.py`:

- **The refusal names a flag that does not exist.** `scrapex/warehousemerge.py:140` tells
  the loser of a race to *"take it deliberately with `--force` if you know it is
  finished"*. There is no `--force` on `merge-warehouse` — `grep` for `--force` in
  `scrapex/cli.py` returns nothing, so argparse answers *"unrecognized arguments"*.
  The one moment R-43 says he must find out from a refusal is the moment the
  refusal sends him to a dead end.
- **`--claim` is declared and never read.** `scrapex/cli.py:1227` adds it;
  `_cmd_merge_warehouse` reads `args.status`, `args.release`, `args.machine` and
  `args.source` and never `args.claim`. It happens to work — `--machine` without
  `--from` claims — so this is dead code rather than a wrong answer, but the help
  text describes a flag that does nothing.

Filed as [`OP-44`](../BACKLOG.md) and [`OP-45`](../BACKLOG.md); the fix is Phase 1
item 1, not Phase 0, because Phase 0 is deliberately limited to the four things
that are true whatever he decides about sync.

---

## 3 · The three populations, re-measured

Read-only against `~/.scrapex/engine/scrapex-engine.db` on **2026-08-22**
(`sqlite3.connect(f"file:{path}?mode=ro", uri=True)` — a 34,834-page profile crawl
is writing to this file, and `?mode=ro` reads through the hot WAL). **Schema v9.
1,135,677,440 bytes plus a 4.2 MB WAL. 56 tables, 506,464 rows.**

Every one of the 56 tables is in **exactly one** population — nothing is
unclassified and nothing is counted twice, which is itself the checkable property
that the partition is honest.

> **THE SNAPSHOT COUNT IS MOVING WHILE THIS IS READ, and the ratios are the point
> rather than the totals.** `generic_page_snapshot` was 20,379 when `R-43` measured
> it, 26,407 an hour before this census and 27,106 during it. `STATE.md` already
> learned this once about the file size: *a bare total goes stale the same day.*

| population | tables | rows | share | property |
|---|---|---|---|---|
| **evidence** | 14 (10 non-empty) | **150,663** | 29.7% | cannot be recomputed; most of it immutable by trigger |
| **derived** | 28 (19 non-empty) | **355,235** | 70.1% | recomputable from evidence with **zero network** |
| **user-authored config** | 14 (7 non-empty) | **566** | **0.11%** | the only genuinely conflict-prone data |

### 3.1 · Evidence — 150,663 rows

| table | rows | why it cannot be recomputed |
|---|---|---|
| `price_observation` | **92,740** | append-only by `trg_price_obs_no_delete` / `trg_price_obs_no_update`. **And there is no page behind it:** `raw_snapshot` holds **0 rows** — a fact this repository has already written down twice, at `scrapex/rowspec.py:219` and in migrations `0056`/`0057` |
| `generic_page_snapshot` | 27,106 | immutable by trigger; natural key `(source_url, content_hash)`, **27,106 rows, 27,106 distinct** |
| `dataset_sighting` | 17,417 | what the site showed and when; UNIQUE `(dataset_key, external_id)`, 17,417 distinct |
| `generic_ingestion` | 4,587 | append-only by trigger — the audit trail of what was interpreted |
| `currency_rate` | 4,328 | an observation with an `as_of`, not a decision (R-44 settled this) |
| `job_log_entry` | 4,185 | what a run said while it ran |
| `crawl_run` / `crawl_job` | 155 / 134 | what was attempted, and where it stopped |
| `tax_rule` | 9 | what the source SAYS about tax, in three states — an observation |
| `snapshot_dictionary` | **2** | without the exact body, every `zstd-raw-dict` page is unreadable for ever |

### 3.2 · Derived — 355,235 rows

`change_event` 141,455 · `generic_record_revision` 53,143 ·
`source_product_attribute` 41,257 · `price_period` 22,537 · `generic_record`
18,008 · `offer_state` 17,539 · `source_offer` 17,539 · `generic_record_node`
15,559 · `source_variant` 13,681 · `source_product` 9,270 · `identity_alias`
4,842 · `classification_node` 214 · and seven more under 100 totalling 191.

**But "derived" is a claim about the CONTRACTOR half only, and that is the finding
of this plan.** The generic half is genuinely recomputable: 27,106 stored pages
re-approve into records, revisions, memberships and the 214-node taxonomy with no
network at all. The **price** half is not. `source_product`, `source_variant`,
`source_offer`, `source_product_attribute`, `price_period`, `offer_state` and
`change_event` — **263,278 rows** — were derived from crawl payloads that
`raw_snapshot` does not hold. Nothing on disk can reproduce them.

So the audit's neat three-way split is really a **two-by-two**: evidence and
derived, times the two categories `R-32` named. And the products category has no
evidence at all, only conclusions.

### 3.3 · User-authored config — 566 rows, and this is the good news

| table | rows | what a conflict looks like |
|---|---|---|
| `dataset_field` | 512 | he reorders columns on one machine and renames one on the other |
| `scrapex_meta` | 27 (**18 are `setting:`**) | two machines with different `crawl_min_interval_s` |
| `source_site` | 12 | a source switched active on one machine, edited on the other |
| `selling_unit` | 10 | a vocabulary row |
| `dataset_definition` / `site_profile` | 2 / 2 | **how a new source is added** — the highest-value rows in the file |
| `retention_policy` | 1 | **destroys data**, and see `Q-21` |
| `retention_pin` · `saved_view` · `schedule` · `feed_assignment` · `source_attribute_promotion` · `attribute_definition` · `brand` | 0 each | conflict-prone the moment they are used |

**566 rows out of 506,464.** The thing a no-server design has to arbitrate is
**one-tenth of one percent** of the warehouse — and the other 99.89% is either
immutable or recomputable. That is what makes «بلا خادم» achievable rather than
brave, and it is the number that should drive the design.

### 3.4 · What the merge covers today, and what it drops in silence

`warehousemerge.merge` touches exactly three tables:
`generic_page_snapshot` (27,106), `dataset_sighting` (17,417) and
`snapshot_dictionary` (2) — **44,525 rows.**

    total rows in the warehouse             506,464
    rows no merge path covers               461,939
    EVIDENCE rows no merge path covers      106,138   ← the number that matters

Of those 106,138 unmergeable evidence rows, **92,740 are `price_observation`** —
append-only by trigger, with no page behind them and no recomputation possible.

**So a merge cannot carry price history at all** — and nothing has asked it to
yet (see the top of this file). It is not wrong about what it does; its docstring says "only the
evidence is merged" and it means the contractor evidence. But `CLAUDE.md`'s own
`R-32` correction says price is one category and filing it as the whole thing was a
mistake — and the tool built for R-43 covers only the other category. This is the
same defect wearing the opposite face.

### 3.5 · `seen_count` merged with `MAX`

`scrapex/warehousemerge.py:329` is `seen_count = MAX(seen_count,
excluded.seen_count)`. That is commutative and idempotent, and the reasoning
recorded beside it is right: two machines crawling the same listing observe the
same site state.

**Measured, so the size of what is discarded is known:** 17,417 sightings on this
machine carry **157,622 observations** (avg 9.05, max 21, and 3,331 rows at
exactly 1). A second machine that had run its own passes contributes a comparable
number, and `MAX` keeps the larger of the two per row and discards the rest
entirely. The consumer is `sighting_frequencies`
(`scrapex/sightings.py:589`), which reads the distribution to estimate coverage —
so after a merge it estimates from one machine's passes while reporting on both.
`Q-20` puts the choice to him with both numbers.

### 3.6 · `git pull` is a precondition of every transfer

`scrapex/warehousemerge.py:216` `_same_shape` refuses across schema versions and
`:227` is the raise. This is not tidiness: it would have blocked him on
2026-08-22, when the installed CLI was 0.2.2 and the arriving bundle was v9. And
its refusal message says *"Run `scrapex init-db` on the older one first"* — which
until Phase 0 was the one route through a schema change with no backup on it
(§4.4).

---

## 4 · Phase 0 — true whatever he decides, and BUILT

**Gate for the whole phase: `SCRAPEX_FULL_MIGRATIONS=1 python -m pytest -q` green
and `node --test extension/tests/drive.test.mjs` green, and every guard below
proven by restoring the defect it names and watching it go red.** Result: **twelve
mutations, twelve killed, no survivors.**

### 4.1 · A bundle is not built from a damaged warehouse

`bundle.verify` proves every file is the file the manifest names — and a corrupt
database has a perfectly valid checksum for its corrupt self. So the strongest
claim a bundle could make about `warehouse.db` was *"these are the bytes we
copied"*.

`scrapex/bundle.py:122` `refuse_a_damaged_warehouse` now runs `PRAGMA
quick_check(1)` on the copy at `:173`, before anything is written around it. On
the **copy** and not the source, because that catches a source that was already
damaged *and* a backup torn on the way out — the second being exactly what the
online backup API exists to prevent, now asserted rather than assumed.

**Measured cost:** 3.8 s cold and 0.35 s warm on a 482 MB engine database, against
a build that has just copied the whole file and is about to write ~93 MB of
exports beside it. `quick_check(1)` matches the form `scrapex/databases/domain.py:276`
already uses.

> **AND #251 MEASURED THE SAME PRAGMA ON THE REAL WAREHOUSE, which is the better
> number:** `quick_check(1)` costs **0.879 s** and `pragma_foreign_key_check`
> **0.398 s** at 1,067 MB. That is why #251 gave `health()` an `integrity=False`
> mode — the panel polls `/api/health` on a timer and 3.8 s blew its 2.5 s deadline,
> reporting a healthy engine as *"Not detected"*. **It does not weaken this guard,
> it sharpens it:** a bundle build is a deliberate act that already copies a
> gigabyte, so a second of scanning is free there and unaffordable on a poll. The
> two callers want different answers, and #251 is what made that sayable.
>
> **It also forced a change here.** §4.4's guard reads `health()` to tell *behind*
> from *damaged*, and that distinction only exists if the scan ran — so it now
> passes `integrity=True` by name and **refuses a report whose `integrity_checked`
> is false** rather than trusting a default that has already moved once.

**Gate:** a warehouse with one interior page overwritten — which still opens and
still lists its tables — makes `build()` raise and leaves **no `manifest.json`**
behind. A healthy one still builds.

### 4.2 · The sha256 is checked after the upload, not before

The engine hashed the archive on its own disk, `backUp` copied that hex string
into `latest.json`, and **nothing on either side ever compared it with anything.**
`fetchLatest` checks `pointer.bytes` against the blob size and never the digest.
The one number in the pointer whose entire purpose is to prove the upload arrived
intact was decoration.

`extension/drive.js:346` `verifyStored` now asks Drive what it stored —
`files/{id}?fields=id,name,size,sha256Checksum`, a digest **Google computes on its
own side**, so the comparison is genuinely end to end and not this module agreeing
with itself. It is called from `backUp` after the archive and **before the
pointer**, extending that function's existing doctrine from *"arrived"* to
*"arrived intact"*. A missing checksum falls back to the size and says so:
`verified_by` is `"sha256"`, `"size"` or `"none"`, and the panel's own sentence
reports which (`extension/app.js:5875`).

**Gate:** an upload Drive stores with the right byte count and a different digest
is refused, and the previous `latest.json` is neither replaced nor deleted. A
truncated one is refused with no digest at all. The digest comparison case-folds.
The check happens between the archive and the pointer, proven by order.

### 4.3 · The destructive restore asks first

Not the panel's button — §2.2(a) — but `scrapex restore-database`, which took a
path and displaced his only warehouse with nothing asked, while
`POST /api/storage/start-fresh` beside it makes him type a phrase because *"a
checkbox is one habitual click; typing is a decision"*.

`scrapex/cli.py:233` `RESTORE_PHRASE = "replace my warehouse"`, required by
`:236`. The refusal names the phrase **and names `merge-warehouse`**, because the
whole of R-43 is that restore replaces and merge adds.

**Gate:** the empty string, `yes`, `replace`, `replace my`, a superset, and the
wrong case are all refused with exit 2 and the live file byte-identical; the exact
phrase proceeds and keeps the displaced warehouse aside; surrounding whitespace is
not a different answer.

### 4.4 · `init-db` no longer advances a schema without a copy

`cli._upgrade_what_is_only_behind` promises *"A BACKUP FIRST, ALWAYS"* and
`registry.ensure_ready` promises *"Nothing else in the codebase may migrate an
existing file"* (`scrapex/databases/registry.py:130`). **Both sentences were
false.** `scrapex init-db` → `registry.initialize()` →
`EngineDatabase.initialize()` (`scrapex/databases/domain.py:198`) migrates
whatever is already there at `:206` and copies nothing — and `init-db` is the
command the product's own refusals send people to, from
`scrapex/databases/domain.py:329` and from `scrapex/warehousemerge.py:229`.

**Proven on his own warehouse, which is why this is a defect and not a theory.**
Engine migrations `0004`…`0009` are all stamped `2026-08-22T07:11:47Z` in
`database_migration` — a **v3 → v9** upgrade of a 1.1 GB file holding his only copy
— and `~/.scrapex/engine/` holds **no `pre-upgrade` backup at all**. Retention
cannot explain it: the one backup that is there is dated two days earlier, and no
prune keeps the older copy and drops the newer.

`scrapex/cli.py:54` `_back_up_before_init_db_advances_a_schema` takes the copy
first, and **only when the database is `BEHIND`** — a healthy file applies no
migration so there is nothing to protect, and a damaged or newer one is left alone
rather than copied, which is the reading `_upgrade_what_is_only_behind` already
takes.

**Gate:** a real engine database two migrations short gains exactly one
`pre-upgrade` backup that opens, passes `quick_check` and reports the version it
was taken from; a current one gains none; and when the copy fails the schema does
**not** move.

**AND THE BOUNDARY IS STATED RATHER THAN LEFT TO BE DISCOVERED.** `init-db --db
<path>` still migrates the named file with no copy. That branch does not go through
the registry at all — it calls `dbmod.migrate` on a path a developer typed — so
`health()` and `BEHIND` do not apply to it, and it is what the test suite and the
split-era `harvest.db` use. It is a developer path and it is not the one his
refusals send him to, but it is not covered, and a reader should not infer from
"`init-db` backs up" that every spelling of the command does.

---

## 5 · Phase 1 — make the manual round trip trustworthy

Nothing here needs a ruling, nothing here is automatic, and all of it is on the
path he already described: back up → download → merge → work → upload → release.

1. **`merge-warehouse --force`, and delete `--claim`.** `OP-44`, `OP-45`.
   **Gate:** the refusal's own remedy runs — a test that takes the sentence
   `warehousemerge.claim` raises, extracts the flag it names, and asserts
   `cli.build_parser()` accepts it. That shape is what stops the next message from
   inventing another flag.
2. **Give the live lock the expiry `lease.py` already worked out**, then delete
   `lease.py` and move its tests. §2.2(d). **Gate:** a `checkout_holder` written
   more than `LEASE_MINUTES` ago no longer refuses another machine, the holder's
   own renewal keeps it, and `grep -r "from .lease"` returns nothing because the
   file is gone rather than merely unused.
3. **THE PRICE MERGE — and it comes FIRST within this phase, ahead of items 1 and
   2.** The whole working is at the top of this file and in `OP-46`; it is not
   repeated here. Two steps, in this order: **the refusal (~15 lines, no ruling
   needed)**, then the five `INSERT…SELECT`s once `Q-23` is answered.
   **Gate:** merging a warehouse holding price rows either lands all of them —
   proven by count, and by merging three times and asserting no VALUE moved, the
   test that caught the `seen_count` sum — **or** exits non-zero naming the number
   of rows it will not carry, including the **11 of 13,681** `source_variant` rows
   that satisfy no unique index. What it must never do again is report success.
4. **`--status` says what will be lost.** `Merged` counts what arrived; nothing
   counts what did not. **Gate:** `--status --from <file>` prints, per table, rows
   the other file holds that no merge path covers.
5. **A bundle records the schema version it was taken at**, so `_same_shape`'s
   refusal can arrive before a 36 MB download rather than after.
   **Gate:** `manifest.json` carries `user_version`, `fetchLatest` refuses a
   pointer whose version this build cannot read, and the message names
   `git pull`.

---

## 6 · Phase 2 — a client-generated key, which is the hinge

**This is the phase that decides whether the tool can ever be published**, and it
is `Q-19` because the cost is his to weigh, not mine.

51 of 56 tables key on a rowid alias (§2.2c). Two devices independently assign
`1, 2, 3…`, so **no row can be named across machines** — which is precisely why
R-43's merge carries no primary key and rebuilds everything downstream. That
design is correct and it has a ceiling: it works for evidence with natural keys
and it cannot work for a row a person edited, because there is nothing to say
*which* row.

The change is one column, `row_uuid TEXT UNIQUE`, generated by the client, on the
tables that need naming. **Today that is `ALTER TABLE` on a file only he holds.
After the tool is published it is a migration across every user's data.**

**Gate:** every table in the config population carries a `row_uuid`; a row
inserted on either machine keeps the same `row_uuid` through a merge, an export
and a re-import; and no existing integer key changes, because `R-24` says upgrade
rather than replace.

---

## 7 · Phase 3 — the config log, which is the only real sync

566 rows (§3.3). Drive holds an **append-only log of small immutable per-device
files** — never the SQLite file itself, because WAL plus partial sync corrupts a
database, which is R-44's own recorded answer. Each file is one device's ordered
operations since its last upload; every device reads every file and folds them in.

**No server means nothing can reject an operation**, so *last writer wins* has to
be decided by a clock nobody controls — which is why **Hybrid Logical Clocks
become necessary here** where a server would have made them pointless. R-44
records exactly that trade.

**Gate, and it is the whole phase:** two devices edit the same `dataset_field`
row while offline, both upload, and after both fold the log they hold **byte-identical
rows** — in either upload order, with either device folding first, and folding
twice changing nothing. Convergence proven by replaying a recorded log in every
permutation, not by one happy path.

---

## 8 · Phase 4 — automatic, and the part that cannot be automatic

Once Phase 3 converges, the round trip stops being a ritual: the panel uploads the
device's log on a schedule (`scrapex/backupschedule.py` already decides *when* and
says which setting decided it) and folds what it finds.

**One thing does not follow, and it is `Q-21`.** Retention policy **destroys
data**, and a design that cannot reject an operation cannot ask a human. So either
retention is driven by an automatic rule — a rule that deletes his pages because
the other machine said so — or it is the one table excluded from sync and set per
device. R-44 named this and left it open; it is his.

---

## 9 · Phase 5 — encryption, deferred by R-44 and kept visible

Not built, by his decision. The fact recorded against it, unchanged: **a
compromised Drive account today means the whole warehouse is readable**, because
there is no encryption anywhere on the path (§2.1). The moment "published later"
becomes "published", this stops being his own data on his own Drive.

**Gate when it comes:** a bundle that a person holding the Drive file and not the
key cannot read, and a key path that never puts the key in the repository, in
`chrome.storage`, or in the bundle beside the thing it protects.

---

## 10 · Open questions — his, not mine (`R-02`)

Each with the measured consequence of each option. None can be answered by code.

### `Q-19` · Does a client-generated key go in now, or never?

| option | measured consequence |
|---|---|
| **now** | `ALTER TABLE` on 14 config tables — **566 rows** — on one file, his. No user data anywhere else exists yet. Cost is one migration and Phase 2's tests |
| **later** | the same migration across every published user's warehouse, and `R-24` forbids replacing rather than upgrading — so it must be a real backfill on files this project never sees |
| **never** | Phase 3 is impossible. 51 of 56 tables cannot name a row across machines, so the 566 conflict-prone rows can be transferred only by overwriting one machine's copy with the other's |

### `Q-20` · Is `seen_count` an observation count or a floor?

| option | measured consequence |
|---|---|
| **keep `MAX`** (today) | commutative and idempotent. Discards the other machine's observations: 17,417 rows here carry **157,622** observations, and after a merge `sighting_frequencies` (`scrapex/sightings.py:589`) estimates coverage from one machine's passes while reporting on both |
| **sum** | the count becomes two machines' observations — and **not idempotent**: this was measured taking one id from 4 → 8 → 12 → 16 over three merges of the same file |
| **count per device** | correct and idempotent: one row per `(dataset_key, external_id, device)`, and the answer is a `SUM` over devices. Costs a column, a key change, and Phase 2 first. At today's size: **17,417 rows becomes 17,417 × devices** |

### `Q-21` · May retention be driven by an automatic rule?

Retention destroys data; a no-server design cannot reject an operation.
`retention_policy` holds **1 row** and `retention_run` holds **0** — it has never
run — so today the question is free. Options: an automatic rule that lets one
machine's policy delete the other's pages; per-device policy excluded from sync,
which means two machines can hold different amounts of history for ever; or a
policy that only ever **widens** (the most permissive setting across devices
wins), which converges without a server and can never delete more than the most
cautious device intended.

### `Q-22` · `REQ-26` is not built, and he believes it is

`extension/accounts.js:1` remembers several accounts and writes nothing to disk;
`scrapex/databases/registry.py:23` has one `DATABASE_ROOT`; and
`scrapex/account.py:9` says in its own docstring that it does not use per-account
directories and does not refuse another owner's warehouse. **Two accounts on one
machine open the same file today.** For himself, on two machines with one Google
account, that costs nothing — which is exactly why it has not bitten. The moment a
second person installs the tool, their data lands in his layout. Does per-account
isolation come before Phase 3, or does Phase 3 assume one account per device?

---

## 11 · Files

**Phase 0, in this pull request:** `scrapex/bundle.py` ·
`scrapex/cli.py` · `extension/drive.js` · `extension/app.js` ·
`extension/tests/drive.test.mjs` ·
`tests/test_a_backup_is_checked_before_it_is_trusted.py` (new) ·
`docs/RULINGS.md` (`R-46`, and `R-44` amended per `C4`) · `docs/REQUESTS.md`
(`REQ-34`) · `docs/BACKLOG.md` (**`OP-46`** — the price merge — plus `OP-44`,
`OP-45`, `Q-19`–`Q-23`) ·
`docs/STATE.md` (Track 6) · `docs/LESSONS.md` (§11 — a checksum proves the bytes,
never the thing) · `tests/test_the_documents_cite_what_they_claim.py` (the new
pinned citations, and five that had drifted) ·
`tests/test_the_registers_cannot_collide.py` (`RESERVED` — the holes this branch
left for #253 and #254) ·
`scrapex/warehousemerge.py` (the false `drive-restore` warning) ·
`docs/plans/README.md` · this file.

**Nothing in Phase 0 changes `warehousemerge.merge` itself.** `OP-46` is filed and
priced, not fixed, because `R-01` says diagnose and confirm before fixing and the
15-line refusal still needs his word on whether a merge that cannot carry everything
should refuse or warn. It is the first thing Phase 1 does.

**Phase 1 onward:** `scrapex/warehousemerge.py` · `scrapex/cli.py` ·
`scrapex/lease.py` (deleted, its expiry moved) · `scrapex/bundle.py` ·
`extension/drive.js` · new migrations under `db/engine/migrations/`.
