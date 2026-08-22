# Plans

Every plan that governs or has governed work on ScrapeX. Read the relevant one
before picking up a track — [../STATE.md](../STATE.md) says which track is live.

**These seven were rescued on 2026-08-17.** They had been written into
`~/.claude/plans/` — one machine, one user account — and were invisible on the
owner's second machine. One of them was the plan for a pull request that was open
at that moment. They are copied here **verbatim**, original codenames and all;
nothing was rewritten, because a plan edited after the fact stops being evidence
of what was decided when. See
[R-09](../RULINGS.md#r-09--one-documentation-system-in-the-repository-all-english).

> Some are written in Arabic. They are kept in their original language for the
> same reason — the system's own documents are English
> ([R-09](../RULINGS.md#r-09--one-documentation-system-in-the-repository-all-english)),
> but a historical record is not rewritten.

---

## Current

| plan | date | status |
|---|---|---|
| [2026-08-20-finish-muqawil-then-the-source-queue.md](2026-08-20-finish-muqawil-then-the-source-queue.md) | 2026-08-20 | **LIVE.** Finish muqawil completely — «كلّ ما ينشره الموقع» — then the six queued sources. **Written to be picked up on his other machine**, per [R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository): the studying is finished, the building has started, and the build order plus what is blocked on him is in one place. Coverage is 11,059 of 17,403 with **zero** profile pages fetched. **Step 1 is now built** — the partitioned crawl, verified against the live directory at an exhaustiveness deficit of **0** — and has RUN: 47 of 56 cells proven, exhaustiveness deficit 0, 13,727 ids sighted. **It now carries the CHECKLIST** of everything open on muqawil — requested-and-unbuilt, not-started, and built-but-unwired — which is the tracking surface he asked for |
| [2026-08-21-the-tool-itself.md](2026-08-21-the-tool-itself.md) | 2026-08-21 | **LIVE.** Everything tool-wide, opened on his instruction so general work stops competing with muqawil: «اى تعديلات عامه … ضعها فى خطة عامة للاداة ككل». Holds `REQ-20` (the rename must reach every user — a release blocker), `R-21` (one owner for every outbound request, his unified connection point), `REQ-04`, `REQ-11`, and the generic-source machinery muqawil exposed but does not own. **Nothing here starts before the quick wins and the muqawil plan**, by his order |
| [2026-08-22-finish-muqawil-workers-crawl-columns.md](2026-08-22-finish-muqawil-workers-crawl-columns.md) | 2026-08-22 | **LIVE.** Finish muqawil: workers for `--details` (**done**, #249 — 87 h to 11–14, and it found a real dictionary race), then the 34,834-page profile crawl, then the 48 columns, then `R-19`'s remaining four groups — three of which measure as *do not build*. Written on the machine that did NOT have the warehouse, which is [R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository) proving itself again |
| [2026-08-22-drive-without-a-server.md](2026-08-22-drive-without-a-server.md) | 2026-08-22 | **LIVE.** The multi-device DATA track, opened on «افتح جلسة session تبدا فى خطة drive» — which amends his own «أرجئ كلّ شىء» of the same day, so [R-44](../RULINGS.md#r-44--no-sync-server-and-no-backup-encryption-for-now-and-the-sync-work-is-deferred-behind-muqawil) stays and [R-46](../RULINGS.md#r-46--the-drive-track-starts-now-and-r-44s-blanket-deferral-is-amended-to-cover-only-what-costs-crawl-time) says what changed. **Phase 0 is BUILT and mutation-proven**: `quick_check` before a bundle, the sha256 checked AFTER the upload, a typed phrase on the destructive restore, and `init-db` backing up before it advances a schema — that last one a live defect, proven by a v3→v9 upgrade of his 1.1 GB warehouse with no `pre-upgrade` backup beside it. **AND IT OPENS WITH THE THING THAT CANNOT WAIT** — `OP-46`: `merge-warehouse` has no INSERT for any price table, so it silently discards the other machine's **92,740 price observations** spanning 2014-05-19 → 2026-08-16, which `raw_snapshot`'s 0 rows make unrecomputable. Not knowable from one side, recoverable because the table is append-only, and stopped by ~15 lines. **The measurement that reframes the rest:** the conflict-prone data is **566 of 506,464 rows (0.11%)**. Phases 1–5 wait on `Q-19`–`Q-23` |
| [2026-08-16-muqawil-contractor-source.md](2026-08-16-muqawil-contractor-source.md) | 2026-08-16 | **LIVE.** The contractor directory — the plan behind #202–#209 and PR #211. Holds the owner's three rulings ([R-10](../RULINGS.md#r-10--the-contractor-directory--three-rulings)), the four build steps, verification, and four open questions. Was `iterative-dreaming-prism.md` |
| [../MIGRATION-PLAN.md](../MIGRATION-PLAN.md) | 2026-08-12 | **LIVE.** The Console, the migration, and the debt. Already in the repo (moved 2026-08-15, [R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository)). Its living state is [HANDOFF-resume-the-migration.md](../HANDOFF-resume-the-migration.md) — and **two of its claims were measured false**; that table is in the handoff |

## Historical

Kept because they record decisions, measurements and reasoning that nothing else
holds. Do not follow them as instructions without checking
[../STATE.md](../STATE.md) first.

| plan | date | what it is |
|---|---|---|
| [2026-08-20-land-the-open-pull-requests.md](2026-08-20-land-the-open-pull-requests.md) | 2026-08-20 | **DONE 2026-08-20.** Review every uncommitted change, then land the five open pull requests. All eight steps executed: **nine PRs merged** (#215, #220, #213, #216, #222, #221, #217, #223, #218), six uncommitted drafts rescued onto `preserve/*` branches, `DEC-7` re-measured over 172 refs, and `STATE.md` corrected — it had been stating something **false**. Carries a postscript on how each step actually ended, including two mistakes of mine. **Steps 6–8 were nearly dropped**, which is why this row leads with a verdict and not a date |
| [2026-08-09-menu-layout-ribbon-shape.md](2026-08-09-menu-layout-ribbon-shape.md) | 2026-08-09 | `MENU_LAYOUT` — making a ribbon menu's *shape* data rather than code, for the mbiXaddin side. Carries owner decisions already taken, the four layouts, and two existing defects to fix while in those files. Was `piped-swimming-parasol.md` |
| [2026-07-29-sync-green-main-and-merge.md](2026-07-29-sync-green-main-and-merge.md) | 2026-07-29 | Arabic. Sync, get `main` green, merge the scattered branches, then resume. **Contains a diagnosed open item** — "Tier 02's price disappeared and will not come back on its own". Was `vast-strolling-raccoon.md` |
| [2026-07-21-data-page-design.md](2026-07-21-data-page-design.md) | 2026-07-21 | **The Data Page build document** — the design B2 is migrating. The owner's eight questions answered by name, the judges' `must_fix` ledger, and a build order where each slice is useful alone. Relevant to Track 1 right now. Was `scrapex-data-page-design.md` |
| [2026-07-20-review-implementation-plan.md](2026-07-20-review-implementation-plan.md) | 2026-07-20 | Prioritised plan from 78 surviving findings, each verified by direct read before writing. Includes what is genuinely done — "do not rebuild, prove it instead" — and a section of owner decisions that are not code choices. Was `scrapex-review-notes-plan.md` |
| [2026-07-20-review-findings.json](2026-07-20-review-findings.json) | 2026-07-20 | The raw findings behind that plan — 1,015 lines, each with `file:line` evidence and a state. Produced by the audit described in [APPROACHES.md A5](../APPROACHES.md) |
| [2026-07-19-completion-plan.md](2026-07-19-completion-plan.md) | 2026-07-19 | Arabic. The completion plan built on an audit of 76 agents against every section of the specification. Has a "three barriers before any new work" section and a deliberately-deferred list that is declared in the UI. Was `scrapex-completion-plan.md` |

---

## Where a new plan goes

**Here, in this repository, at the moment it is written** — not in `~/.claude/`,
not in a scratchpad, not in the conversation. Name it `YYYY-MM-DD-<subject>.md`
and add a row above. If it governs live work, add it to the **Current** table and
link it from [../STATE.md](../STATE.md).

A plan the other machine cannot open does not exist.
- [2026-08-21 · the platform, not a price tracker](2026-08-21-the-platform-not-a-price-tracker.md) — `R-32`: categories (`products`, `contractors`), one source registry, a database per account. **Nothing built; `Q-14` is his.**
