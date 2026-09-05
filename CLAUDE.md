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
- **The panel is the operating system; everything else is an app, the engine included.**
  It is the only surface, it chooses which app runs a job, and it starts them —
  `extension/transport.js` sends `START_ENGINE` and `scrapex/native.py` obeys; the engine
  launches nothing. Every app is started that same way, through the one native host, so no
  app depends on another and dropping one costs nothing.
- **An app brings its own way of working, and holds only the permissions it needs.**
  Adding a project like Scrapy is worth it for its own network path and concurrency, not to
  be wrapped in ours; ours grows where the external ones do not serve and neither pauses
  the other. Choose per run by measured performance, not by authorship. More permission
  than an app needs is a defect to fix, not a status to keep. Registries:
  `scrapex/connectors/factory.py`, `scrapex/enrichment/providers/__init__.py`.
- **The warehouse write permission is exclusive, and the panel cannot hold it.** One writer
  at a time, whichever app it is. Not a privilege — a measurement: the warehouse is WAL, no
  OPFS VFS implements `xShmMap`, and a browser reads it minus every transaction still in
  the WAL, silently (`spikes/opfs-sqlite/FINDINGS.md`). Reading a copy is a different
  question and it passes.
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

## Review

Four dimensions: **architecture** (boundaries, coupling, data flow, bottlenecks, single
points of failure, the security surface) · **code quality** (module structure, DRY, error
handling and the edge cases it misses, over- and under-engineering) · **tests** (coverage
gaps, assertion strength, missing edge cases, untested failure paths) · **performance**
(N+1 and query patterns, memory, caching, slow paths). Rank every finding **must fix** ·
**should fix** · **optional** · **not an issue**, and report nothing rather than pad it.

**When he asks for one**: one dimension at a time, stopping after each for his word. Per
issue: the problem with `file:line` · two or three options **including "do nothing"** ·
per option the effort, risk, blast radius and maintenance burden · the recommendation
mapped to the preferences.

**Before every merge — green is not mergeable.** A code change merges only when a critical
review returns nothing. On green: run a panel over all four dimensions, let an adversary
attack what it found, fix what survives, push, review again. Clean means no *must fix* and
no *should fix*; *optional* becomes an issue, never a fix in the same PR. The biggest
finding here arrived on the fifth pass — and if five passes do not converge the change is
too big to review, so split it. Documentation-only changes are exempt.

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

**Several live checkouts, and both imports and edits default to the main one.** `scrapex`
is pip-installed editable against `C:\Users\User01\source\repos\ScrapeX`, and the worktrees
under `.claude\worktrees\` are full checkouts too. Derive every path from the worktree
root, and in a scratch script assert on a **symbol you just added** — `__file__` catches a
misdirected import, never a misdirected edit.

**Never hash a repo file's raw bytes.** `.gitattributes` sets `* text=auto`, so the repo
stores LF and Windows checks out CRLF. Normalise `b"\r\n"` → `b"\n"` first.

## How this file evolves

**Keep improving it — every session.** But growth here means *sharper*, not *longer*.

- **A rule earns its place by changing what a session does.** If it changes no action, it
  does not belong; if it belongs beside a line of code, put it there instead.
- **Write it as an instruction, not a story.** One clear, unambiguous line. No dates, no
  quotes, no incident reports — the reason lives in the PR that added the rule.
- **Add by replacing.** Before adding a line, delete one that stopped being true, and
  merge into an existing rule rather than repeating it.

Every session reads this before every task, so a wasted line is paid for on every read.
Keep it under 150.
