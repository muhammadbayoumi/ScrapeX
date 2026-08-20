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
| [2026-08-16-muqawil-contractor-source.md](2026-08-16-muqawil-contractor-source.md) | 2026-08-16 | **LIVE.** The contractor directory — the plan behind #202–#209 and PR #211. Holds the owner's three rulings ([R-10](../RULINGS.md#r-10--the-contractor-directory--three-rulings)), the four build steps, verification, and four open questions. Was `iterative-dreaming-prism.md` |
| [../MIGRATION-PLAN.md](../MIGRATION-PLAN.md) | 2026-08-12 | **LIVE.** The Console, the migration, and the debt. Already in the repo (moved 2026-08-15, [R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository)). Its living state is [HANDOFF-resume-the-migration.md](../HANDOFF-resume-the-migration.md) — and **two of its claims were measured false**; that table is in the handoff |

## Historical

Kept because they record decisions, measurements and reasoning that nothing else
holds. Do not follow them as instructions without checking
[../STATE.md](../STATE.md) first.

| plan | date | what it is |
|---|---|---|
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
