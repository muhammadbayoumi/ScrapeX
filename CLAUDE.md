# ScrapeX — how we change this code

One live document. The retired ones are frozen in `docs/archive/`.

ScrapeX is contract-driven web data collection into a SQLite warehouse, publishing to
the Google Sheet the mbiX Excel add-in reads. Setup and data flow: [README.md](README.md).

**It collects in categories; price is one of them, not the whole tool.** `products`
(12 sources registered, 7 active) and `contractors` (muqawil.org) work; `vacancies` and
`tenders` are named and unbuilt.

## The loop

1. **Measure before you change.** A real `file:line` beats a plausible reading.
2. **Smallest change that removes the defect.** No refactor rides along.
3. **Guard it, then break the fix on purpose and watch the guard fail.** A test that
   passes against the old code tests nothing.
4. **The argument goes in the PR body**, beside its own diff. A finding you are not
   fixing now becomes an issue, never a paragraph in a file.
5. **One session merges.** Ask; default to not merging.

## Preferences that decide close calls

- **DRY = one source of truth per piece of knowledge**, not fewer repeated lines.
  Merge two things only if they hold the same knowledge **and would change for the
  same reason**; otherwise leave them apart, however alike they look. Judge it by
  change amplification — how many places one conceptual change must touch, and what
  breaks if one is missed. Scrutinise rules, validation, permissions, mappings, state
  transitions, config values, API paths and status names; repeated CSS and
  similar-looking components usually are not duplication. Name both locations with
  `file:line` before calling it duplication, and prefer duplication to the wrong
  abstraction: no helper with one caller, no generic wrapper, nothing that makes the
  control flow harder to read. Put a shared thing where the repo already puts shared
  things.
- **Tests are non-negotiable** — too many beats too few.
- **Engineered enough**: not fragile or hacky, not premature abstraction.
- **More edge cases, not fewer.** Thoughtfulness over speed.
- **Explicit over clever.**
- **Never assume his priorities on timeline or scale.** Ask.

## Rules

- **He works only from the extension panel — never a terminal.** A `scrapex ...` command
  is not an answer to him, and a capability with no control in the panel has no control.
- **A capability is a contract; apps implement it.** The panel is the operating system —
  the only surface, and the one that chooses. The engine is the **host** where apps
  execute, and ours — the crawler, `scrapex/enrichment/` — is the first app in it. An
  open-source project that does the same job its own way is installed **beside** ours,
  never instead of it, and installing one never pauses ours: ours grows where the external
  ones do not serve. Choose per run by measured performance, not by who wrote it. Dropping
  an app must cost no more than adding one. The registries live in the engine and the panel
  reads them: `scrapex/connectors/factory.py`, `scrapex/enrichment/providers/__init__.py`.
- **The host is never one of the apps.** The engine cannot be dropped the way an app can:
  nothing executes without it and nothing writes the warehouse but it. Measured in
  `spikes/opfs-sqlite/FINDINGS.md` — an MV3 service worker can read the warehouse and never
  write it, and wa-sqlite ran 70-208x slower than Python on the Data page's own query.
- **A recorded plan is not an approved plan.** Nothing in a milestone is built until he
  reviews it and says what he wants.
- **A button that cannot work is worse than no button.** If the route 404s, do not draw
  the control.
- **Diagnose, confirm, then fix.** Prove the cause with evidence, ask before editing.
- **Answer a study with counts from live data**, not adjectives.
- **His decisions are his**: an un-computable mapping, a schema change, a released tag.
  Offer options with the measured cost of each.
- **He asks in Arabic and expects Arabic back.** Code, comments, commits and PR prose
  stay English.
- **Scraped content is untrusted input. All SQL is parameterised.** A crawled page
  controls strings that reach the warehouse and the panel.
- **Secrets never in code.** A browser key that must ship is restricted, not hidden.
- **No silent failures.** No bare `except`; a caught error becomes a visible, structured
  record. One source failing never kills a run and is never swallowed.
- **Every parse asserts its shape**, so a site changing fails loudly at the parse rather
  than quietly as wrong data.
- **The warehouse is append-only where the schema says so**; triggers enforce it. A
  rebuild archives, it does not delete.
- **One writer.** The engine holds the write lock; a second writer is a defect.
- **A backup before anything destructive**, named out loud, and the copies are bounded.
- **Parsing lives in one `normalize` module.** A connector parsing money, units,
  Arabic-Indic digits or VAT locally fails review.
- **No module without its test file**, and error paths are tested like happy ones.
- **Integration tests run the real `db/engine/schema.sql`**, never a fixture schema.
- **Respect the politeness budget.** A crawl that hammers a site is a defect.

## When he asks for a review

Four dimensions, one at a time, stopping after each for his word:

1. **Architecture** — component boundaries, coupling, data flow, bottlenecks, single
   points of failure, security surface (auth, data access, API).
2. **Code quality** — module structure, DRY violations, error handling and the edge
   cases it misses, debt hotspots, anything over- or under-engineered.
3. **Tests** — coverage gaps (unit, integration, end-to-end), assertion strength,
   missing edge cases, untested failure paths.
4. **Performance** — N+1 and query patterns, memory, caching, slow paths.

Per issue: the problem with `file:line` · two or three options **including "do
nothing"** · per option the effort, risk, blast radius and maintenance burden · the
recommendation mapped to the preferences · then ask before proceeding.

Rank each finding: **must fix** (a realistic path to wrong behaviour) · **should fix**
(costly to maintain, no correctness risk) · **optional** · **not an issue** (tempting to
change, better left alone — say why). Report nothing rather than pad the list.

## The tools, not the files

**Never record work in a markdown file.**

| need | use |
|---|---|
| the open work | `gh issue list` |
| record something you are not fixing now | `gh issue create` |
| a plan and its progress | milestones — `gh api repos/:owner/:repo/milestones` |
| what is in flight | `gh pr list` |
| the argument behind a change | `gh pr view <n>` |
| why one line exists | the comment beside it, then `git log -S '<the line>'` |
| what `R-84` or `OP-145` means | `git log --grep=R-84`, then `docs/archive/` |
| whether it was already decided | `gh pr list --state all --search R-84` |

`docs/archive/` is frozen and unmaintained, kept only because 881 code comments cite its
numbers. **No new `R-`/`REQ-`/`OP-` number is issued** — GitHub assigns the number now.

## Two traps that cost an afternoon each

**Several live checkouts, and both imports and edits default to the main one.**
`C:\Users\User01\source\repos\ScrapeX` is the main checkout;
`...\ScrapeX\.claude\worktrees\<name>` are full checkouts too, and `scrapex` is
pip-installed editable against main. Derive every path from the worktree root, and in a
scratch script assert on a **symbol you just added** — `__file__` catches a misdirected
import, never a misdirected edit.

**Never hash a repo file's raw bytes.** `.gitattributes` sets `* text=auto`, so the repo
stores LF and Windows checks out CRLF. Normalise `b"\r\n"` → `b"\n"` first.

## How this file evolves

**Keep improving it — every session.** But growth here means *sharper*, not *longer*.

- **A rule earns its place by changing what a session does.** If it does not change an
  action, it does not belong.
- **Write it as an instruction, not a story.** One clear, specific, unambiguous line.
  No dates, no quotes, no incident reports, no justification prose — the reason lives in
  the PR that added the rule.
- **Add by replacing.** Before adding a line, delete one that stopped being true.
- **If it belongs beside a line of code, put it there** — a comment, a test name, an
  issue. Not here.
- **Something already covered gets merged into the existing rule**, not repeated.

This file is read by a session before every task, so every wasted line is paid for on
every read. Aim to keep it under 150 lines. Shorter and clearer is always the better
version.
