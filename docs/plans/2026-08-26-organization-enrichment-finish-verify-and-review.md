# Organization enrichment — finish it, prove it, and review what it produces

**Written 2026-08-26.** Governs the completion of the work now sitting on
`feat/organization-enrichment`. Every measurement below was taken against that
branch at **`c0cd695`** and against `main` at **`35962cc`**; like
[../ENGINE-ROLE-MEASURED.md](../ENGINE-ROLE-MEASURED.md), the citations are pinned
to those commits and not to `HEAD`.

> «لسه لم ينتهى تطوير هذا الجزء بشكل كامل — اريد وضع خطة لتطويره واختباره
> ومراجعة البيانات التى ينتجها بشكل دورى اولا» — 2026-08-26

Three demands, and the third one is new. `REQ-43` asked for the feature. This asks
for **the feature to be finishable, provable, and reviewable on a period** — the
last of which nothing in the branch can do today, for a reason that is measured in
G3 below.

---

## Where the work actually stands

| fact | measured |
|---|---|
| branch | `feat/organization-enrichment`, published as `origin/feat/organization-enrichment` |
| commits | `cf3f5eb` (workspace) · `c0cd695` (hardening), both 2026-08-24 |
| pull request | **none** — `gh pr list --head feat/organization-enrichment` returns nothing |
| position | forked at `4868f91`; `main` is one commit ahead (`35962cc`, #263) |
| size | 41 files, +4,168 / −101 |
| registers | `REQ-43` **In flight**, `STATE.md` and `BACKLOG.md` updated — **all three inside the branch only** |

**That last row is the quiet defect.** Every session begins at `CLAUDE.md` and
`docs/STATE.md` on `main`, and neither one mentions this feature. A session
starting tomorrow would not know it exists, and would find neither a PR nor a
register entry to trip over. The work is invisible by construction until it lands.

### What is built and works (verified by reading, not by claim)

| layer | what exists |
|---|---|
| schema | `db/engine/migrations/0011_an_organization_can_accumulate_verified_facts.sql` — five tables, `job_kind` on `crawl_job` |
| evidence model | `organization_fact` carries provider, source URL, confidence, verification status and a `valid_from`/`valid_to` interval |
| service | `scrapex/enrichment/service.py`, 1,099 lines — proposal, definition, job, materialization |
| providers | `website.py` (359 lines, SSRF-guarded) · `google_places.py` (176 lines, opt-in) · LinkedIn declared unavailable |
| jobs | `job_kind` dispatch, pause/resume/cancel at record boundaries, checkpoint resume |
| API | `/api/enrichment/sources/{key}`, `/definitions`, `/definitions/{id}`, `/definitions/{id}/runs`, `/definitions/{id}/review` |
| extension | `enrichment.html/.js/.css` — mapping, providers, run, progress, browse, review list |
| tests | 22 in `tests/test_organization_enrichment.py` + 3 in `tests/test_enrichment_page.py` |

---

## The seven gaps, measured

### G1 — The review queue can be read but never answered

`review_queue` (`service.py:1079`) returns every fact whose `verification_status`
is `manual_review` or `conflict`. The router exposes it as
`GET /definitions/{id}/review` (`scrapex/enrichment/api.py`). **There is no POST.**
`manual_review_status` is written in exactly one place — `_materialized_data` at
`service.py:745`, computed from the machine's own statuses.

So an uncertain fact stays uncertain for ever, `counts.needs_review`
(`service.py:152`) can only grow, and `extension/enrichment.js:360-389` renders
rows with a **Refresh** button and nothing else. The owner's verdict has nowhere to
go. **This is the missing half of "مراجعة البيانات": he can look, he cannot rule.**

### G2 — Every run is a full sweep of the whole directory

`_active_source_rows` (`service.py:847`) pages through *every* active record of the
source dataset from the checkpoint forward, ordered by id. There is no filter on
when an organization was last checked, on whether its last check failed, or on
whether its source row changed.

Against muqawil that is **18,008 contractors × every enabled provider, every run.**
A weekly period would re-fetch 18,008 websites to discover that almost nothing
moved. Periodic execution is not merely unscheduled — at this cost it is
unaffordable.

### G3 — Nothing in ScrapeX can schedule an enrichment definition

The clock exists and is good: `scrapex/scheduler.py` fires due schedules, and
`scrapex/osschedule.py` keeps a Windows task so a slot fires with the panel closed.
Neither can reach this feature:

- `upsert_schedule` (`scheduler.py:107`) keys a schedule on **`source_key`**, one
  row per source.
- `fire_due` (`scheduler.py:194`) resolves that key against the **manifest** and
  skips anything it cannot find there.
- It queues with `create_job(conn, [source_key], run_mode)` (`scheduler.py:216`),
  which defaults to `job_kind="crawl"` (`scrapex/jobs.py:57`).

An enrichment definition is not a manifest source and has no `source_key`.
**"دورى" is currently impossible, not merely unbuilt.**

### G4 — The fact history has no retention

`organization_fact` opens a new row on every changed value and closes the old one.
Nothing ever prunes it. `retention.py` and `compaction.py` touch `price_observation`
only — already declared in [../../CLAUDE.md](../../CLAUDE.md) as the platform's
standing hole, and this feature widens it from one dataset to two.

### G5 — Five published columns are permanently empty

`OUTPUT_FIELDS` (`scrapex/enrichment/models.py`) publishes `linkedin_company_url`,
`linkedin_employee_count`, `key_decision_makers`, `linkedin_match_status` and
`linkedin_match_score`. `provider_availability()`
(`scrapex/enrichment/providers/__init__.py`) declares LinkedIn `available: False`
with no provider behind it.

The repository already owns a test named
`tests/test_the_sites_own_gaps_do_not_become_false_facts.py`. A column that is
always blank in a published dataset is that same trap on the output side: a reader
cannot tell "we did not look" from "there is nothing".

### G6 — Definitions cannot be enumerated

The router offers `/sources/{key}` and `/definitions/{id}`. There is no
`GET /api/enrichment/definitions`. Nothing — not a report, not a scheduler, not the
panel — can ask *"what enrichment definitions exist?"*. A periodic review needs
that list before it needs anything else.

### G7 — Provider behaviour is proved only against invented HTML

`test_website_provider_extracts_only_after_the_published_name_matches`
(`tests/test_organization_enrichment.py:686`) builds its pages inline as string
literals. The repository's convention for the crawl side is dated live fixtures —
`tests/fixtures/live/*_2026-07-20.html`. **No test has ever pointed this provider at
a real contractor's website.** The precision of the output is therefore unknown, and
unknown precision is what a periodic data review exists to expose.

---

## The plan — seven steps, each with a gate

A step is done when its gate is a **recorded measurement**, not an assertion.

### Step 0 — Ground truth on today's `main`

Rebase the branch onto `35962cc`, run the whole suite, record what passes and what
fails, with counts. `REQ-43` says "built and verified"; it was verified at a commit
that two merges to `main` now sit above.

**Gate:** a pasted run — total, passed, failed, skipped — with any failure named.
Nothing below starts before this number exists.

### Step 1 — The owner's verdict becomes a fact (closes G1)

- `POST /api/enrichment/definitions/{id}/review/{fact_id}` taking
  `{decision: accept | reject | replace, value?, note?}`.
- The decision is written as an `organization_fact` with provider `owner`, and
  `_PROVIDER_RANK` (`service.py:694`) gains `owner` above `source`, so a human
  verdict outranks every machine on that field for ever.
- A rejected value is **closed** (`valid_to`), never deleted — **C4** expressed in
  data.
- `enrichment.js` gets Accept / Reject / Replace per review row.

**Gate:** a test that runs the job, rejects a fact, runs the job **again**, and
proves the rejected value neither returns to the output nor re-enters the review
queue. Per [../LESSONS.md](../LESSONS.md), the second run is where this class of bug
lives; the first run cannot see it.

### Step 2 — A run touches only what is due (closes G2)

- Per organization and provider, record `last_checked_at` and `next_due_at`.
- The definition gains `recheck_after_days` (**proposed default 30** — his to
  change).
- The run's selection order becomes: never enriched → last attempt failed → due by
  staleness → source row changed since last check. Nothing else is fetched.
- `_active_source_rows` becomes a due-set query rather than a full scan.

**Gate:** a second run started immediately after a first issues **zero** provider
requests, counted; a run after the staleness window issues **exactly** the due
count, counted.

### Step 3 — Periodic execution becomes possible (closes G3)

Extend the existing clock rather than adding a second one:

- `schedule` gains a target kind so a row can point at an enrichment definition
  instead of a manifest source.
- `fire_due` dispatches by `job_kind`, keeping its existing "re-arm before queueing"
  order (`scheduler.py:211`) — that ordering is load-bearing and must not move.
- `osschedule.py` needs no change: it already owns the machine-level clock.

**Gate:** a schedule fires an enrichment job **with the panel and engine UI closed**,
proven by the `crawl_job` row and its `job_kind`, not by a screenshot.

### Step 4 — The periodic review report (the thing he actually reads)

Per definition, per period, one report:

| section | content |
|---|---|
| coverage | organizations total / verified / candidate / needs review / not found |
| per provider | requests, facts produced, verification rate, errors, circuit trips |
| empty fields | every output column never once filled — the G5 detector, generalised |
| changes | values that changed this period: old → new, with both evidence URLs |
| staleness | organizations not checked in N days |
| **delta** | every number against the previous report |

The delta is the point. A verification rate that halves between two periods is a
provider outage or a site redesign — a single-period report cannot tell him that,
and that is precisely the class of silent failure [../LESSONS.md](../LESSONS.md)
exists for.

Delivered three ways, because he works from two machines: a card in the workspace,
`scrapex enrichment report --definition N` on the CLI, and a stored snapshot row so
periods can be compared later.

**Gate:** two consecutive reports over a seeded database reproduce a known answer,
including one deliberately broken provider that must show up as a collapsed rate and
not as a bad directory.

### Step 5 — Precision measured once, on real data

Draw a random sample of **50** muqawil organizations, check each field by hand
against the real site, and publish precision per field per provider, with the false
positives listed verbatim.

`ORGANIZATION-ENRICHMENT.md` states *"Null is preferred to a guess"*. Nothing
measures how often it guesses anyway. Until this number exists, whether the dataset
is publishable is an opinion — and per [../RULINGS.md](../RULINGS.md) `R-02`, that
judgement is the owner's, answered with counts.

**Gate:** the measurement written into this plan's postscript, sample listed.

### Step 6 — History, columns, and the seams (closes G4, G5, G6, G7)

- A retention policy for `organization_fact` and closed facts, in the same shape as
  the price policies rather than a second vocabulary.
- **LinkedIn columns:** proposed — remove them from `OUTPUT_FIELDS` until a verified
  provider exists. `ORGANIZATION-ENRICHMENT.md` already declares that adding output
  fields is an additive schema operation, so removing them now costs nothing to
  restore later, and it stops publishing five columns of silence.
- `GET /api/enrichment/definitions`.
- Dated live fixtures for the website provider, captured from real contractor sites
  under the existing `tests/fixtures/live/` convention.

### Step 7 — Land it, and make it visible

Rebase, open the PR, and update `STATE.md`, `REQUESTS.md` and — where he has ruled —
`RULINGS.md` **in the same pull request** (**C2**). Confirm the engine migration
number is still free at merge time: `0011` is unclaimed on `main` today, and the
first branch to merge takes it.

The version ledger is already correct on the branch: `VERSION = "0.3.2"` with the
capability carrying `commit=""`, which `version.py:328` permits only while
`since == VERSION` — that is, only while it is landing. It must be stamped at merge.

---

## Testing strategy — five layers

| layer | today | to add |
|---|---|---|
| 1 · schema & contract | `test_the_engine_migration_keeps_definitions_facts_and_job_kind` | retention tables; `job_kind` on a scheduled job |
| 2 · unit | matching, coordinate and email validation, provider parsing | dated live fixtures (G7); the empty-field detector |
| 3 · **second run** | `test_runs_are_resumable_idempotent_and_keep_changed_fact_history` | the owner's rejection must survive a re-run (Step 1); a due-set run must fetch nothing (Step 2) |
| 4 · failure injection | provider circuit, provider removed mid-life, bounded paging | timeout, 429, DNS failure, `database is locked` mid-run, cancel and pause at a record boundary |
| 5 · **data review** | none | the report itself, against a seeded database with a known answer and a deliberately broken provider |

Layer 3 is the one the repository has been burned by before and the one this feature
is most exposed to, because a human decision that a machine silently overwrites on
the next run is worse than no review button at all.

---

## Status

| step | state |
|---|---|
| 0 · ground truth on `main` | not started |
| 1 · the owner's verdict becomes a fact | not started |
| 2 · a run touches only what is due | not started |
| 3 · periodic execution | not started |
| 4 · the review report | not started |
| 5 · precision on 50 real organizations | not started |
| 6 · history, columns, seams | not started |
| 7 · land it and make it visible | not started |

---

## What this plan does not touch

The source crawl. `contractors` and `contractor_profiles` stay exactly what they
are; enrichment is a third derived dataset and reads them without writing to them.
That boundary is `REQ-43`'s and is not reopened here.

---

## Decisions this plan needs from the owner

1. **Cadence and scope of the period.** Weekly full sweep, or staleness-based with a
   30-day recheck? The second is the only one that is affordable at 18,008 rows
   (G2), and it is what Step 2 assumes until he says otherwise.
2. **The five LinkedIn columns.** Remove them until a provider exists (proposed), or
   keep them visible and empty as a declaration of intent?
3. **Merge order.** Open the PR now so the feature stops being invisible on `main`
   and finish the seven steps in the open — or finish first and merge once? The
   first makes it reviewable; the second keeps `main` free of a half-built
   capability. **Nothing merges without his word** (`R-42`).

The register number for the periodic-review demand of 2026-08-26 is **not claimed
here** — per [../ORCHESTRATION.md](../ORCHESTRATION.md) it comes from the primary
session, and `REQ-41`, `REQ-42` and `REQ-43` are already taken on other branches.
