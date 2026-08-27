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

**ONE plan is live** ([R-58](../RULINGS.md#r-58--drive-is-the-second-plan-muqawil-finishes-first-and-its-problems-with-it)).
**A row below the live one is QUEUED whatever its own file says about itself** — eight rows
here carried `LIVE` at once on 2026-08-26, which meant none of them was the plan.
One sentence per row on purpose ([R-57](../RULINGS.md#r-57--a-document-carries-what-is-needed-and-consequential-and-nothing-else)):
what the plan is for goes in the plan.

| # | plan | what it is |
|---|---|---|
| **1 · LIVE** | [2026-08-26-what-remains-of-muqawil.md](2026-08-26-what-remains-of-muqawil.md) | Ten steps in the order he asked for. **Five are blocked on him, and they are every defect that publishes a false value** — so the route to a correct dataset runs through five decisions, not through more crawling. Evidence: [MUQAWIL-AUDIT-2026-08-26.md](../MUQAWIL-AUDIT-2026-08-26.md) |
| **1a** | [2026-08-24-a-generic-crawl-is-a-run.md](2026-08-24-a-generic-crawl-is-a-run.md) | Step 2 of the above in detail — `R-52` / `OP-68`, and the `C5` disagreement that became [R-54](../RULINGS.md#r-54--the-state-column-is-fixed-at-its-root-first-a-confirmation-moves-last_seen_at). Step 1 of it needs no ruling |
| **1b** | [2026-08-20-finish-muqawil-then-the-source-queue.md](2026-08-20-finish-muqawil-then-the-source-queue.md) | **FOLD PENDING.** Superseded by row 1 as a queue; its §D (built-and-not-wired, measured) and §E (held by him) have not yet been checked against `LESSONS` and `BACKLOG`, and it is 671 lines. Not deleted until they are |
| **2** | Drive | Branch `claude/drive-without-a-server` at `e00711d` — pushed, **no PR since 2026-08-22**. Second by his ruling |
| 3 | [2026-08-22-the-source-page-moves-into-the-extension.md](2026-08-22-the-source-page-moves-into-the-extension.md) | `REQ-07` — the engine's `/source/{key}` becomes the panel's. Step 0 is done; the gate on steps 3 and 5 was lifted 2026-08-26 |
| 4 | [2026-08-21-the-tool-itself.md](2026-08-21-the-tool-itself.md) | Everything tool-wide, opened so general work stops competing with muqawil. Holds `REQ-20`, `R-21`, `REQ-04`, `REQ-11` |
| 5 | [../MIGRATION-PLAN.md](../MIGRATION-PLAN.md) | The base plan ([R-49](../RULINGS.md#r-49--migration-planmd-is-the-base-plan-and-its-date-is-the-test)). Its living state is [HANDOFF-resume-the-migration.md](../HANDOFF-resume-the-migration.md) |

## Historical

Kept because they record decisions, measurements and reasoning that nothing else
holds. Do not follow them as instructions without checking
[../STATE.md](../STATE.md) first.

**Folded 2026-08-27, not archived** ([R-60](../RULINGS.md#r-60--a-finished-document-leaves-the-tree-and-git-is-the-archive)) —
`git show d6f4967:docs/plans/<name>` returns either in full:

- **`2026-08-16-muqawil-contractor-source.md`** (170 lines) — all six build steps shipped in
  #202-#209 and #211. Its measured site facts are in
  [CONTRACTOR-SOURCE.md](../CONTRACTOR-SOURCE.md) — `data-cfemail`, the `143` segment, 20
  rows a page, 865 pages, Cloudflare not blocking — checked term by term before deleting.
  Its rulings are `R-10`.
- **`2026-08-22-finish-muqawil-workers-crawl-columns.md`** (152 lines) — steps 1 and 3 done
  (#249), step 2 done when the crawl finished at 34,834 of 34,834, step 4 is `R-19`. Its
  appendix of his four sync decisions is `R-44`, which carries all four.

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
