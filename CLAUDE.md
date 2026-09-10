# ScrapeX — how we change this code

ScrapeX is contract-driven web data collection into a SQLite warehouse, publishing to the
Google Sheet the mbiX Excel add-in reads (`scrapex/publish.py`, [README.md](README.md)). A
second Sheet runs the other way — the Apps Script staging inbox `scrapex funnel-test`
posts to (`scrapex/funnel.py` → `apps_script/` → `scrapex/ingest.py`). **It collects in
categories; price is one of them, not the whole tool.** `products` and `contractors`
work; `vacancies` and `tenders` are named, unbuilt.

## The loop

1. **Measure before you change.** A real `file:line` beats a plausible reading.
2. **Smallest change that does the job.** No refactor, and no extra feature, rides along.
3. **Guard it, then break the fix on purpose and watch the guard fail.** A test that
   passes against the old code tests nothing.
4. **The argument goes in the PR body**, beside its own diff. A finding you are not
   fixing now becomes an issue, never a paragraph in a file.
5. **One session merges.** Ask; default to not merging. Take it first —
   `gh pr edit <n> --add-assignee @me`; an already-assigned PR is another session's. That
   session rebases what it merges, and a conflict whose resolution picks a behaviour goes
   back to the author.

## Preferences that decide close calls

- **DRY = one source of truth per piece of knowledge**, not fewer repeated lines. Merge
  two things only if they hold the same knowledge **and would change for the same
  reason**. Scrutinise rules, validation, permissions, mappings, state transitions,
  config values, API paths and status names; repeated CSS and similar-looking components
  usually are not duplication. Name both locations with `file:line` before calling it
  duplication, and prefer duplication to the wrong abstraction: no helper with one
  caller, no generic wrapper, nothing that makes control flow harder to read. Put a
  shared thing where the repo already puts shared things.
- **Tests are non-negotiable** — too many beats too few.
- **More edge cases, not fewer.** Thoughtfulness over speed.
- **Engineered enough, explicit over clever**: not fragile or hacky, not premature
  abstraction.
- **Never assume his priorities on timeline or scale.** Ask.

## Rules

- **He works only from the extension panel — never a terminal.** A `scrapex ...` command
  is not an answer to him.
- **A capability and its control ship in one change.** A capability with no panel control
  has no control; and if the route 404s, do not draw the control.
- **The panel is the operating system; everything else is an app, the engine included.**
  It is the only surface, it chooses which app runs a job, and it starts them —
  `extension/transport.js` sends `START_ENGINE` and `scrapex/native.py` obeys; the engine
  launches nothing. Every app is started that same way, through the one native host, so no
  app depends on another and dropping one costs nothing.
- **An app brings its own way of working, and holds only the permissions it needs.**
  Adding a project like Scrapy is worth it for its own network path and concurrency, not
  to be wrapped in ours; ours grows where the external ones do not serve and neither
  pauses the other. Choose per run by measured performance, not by authorship. More
  permission than an app needs is a defect to fix, not a status to keep. Extending is an
  entry in a registry, not a new module: `scrapex/connectors/factory.py`,
  `scrapex/directories.py`, `scrapex/enrichment/providers/__init__.py`.
- **The warehouse write permission is exclusive, and the panel cannot hold it.** One
  writer at a time, whichever app it is; the engine holds the write lock, and a second
  writer is a defect. `DbLockedError` means another app has it — wait for it, never route
  around it. A browser reads the warehouse minus every transaction still in the WAL,
  silently (`spikes/opfs-sqlite/FINDINGS.md`); reading a copy is a different question
  and it passes.
- **A recorded plan is not an approved plan.** Nothing in a milestone is built until he
  reviews it and says what he wants.
- **He does not write code; advise before you comply.** An instruction that would worsen
  the result gets the objection, its evidence and a better option — or a question, where
  his reason is not visible. Then his word decides. Silent compliance is the failure.
- **His decisions are his**: an un-computable mapping, a schema change, a new source, a
  `VERSION` bump — merging one ships the engine to every installation. Offer options with
  the measured cost of each.
- **Diagnose, confirm, then fix.** Prove the cause with evidence, ask before editing.
- **Answer a study with counts from live data**, not adjectives.
- **A wrong number is diagnosed at the stored row first.** Right in the warehouse and the
  defect is in export or publish; wrong there and it is in the connector or `normalize`.
  Never correct a value in the exporter, the Apps Script or the Sheet.
- **He asks in Arabic and expects Arabic back.** Code, comments, commits and PR prose
  stay English.
- **Scraped content is untrusted input. All SQL is parameterised.** A crawled page
  controls strings that reach the warehouse and the panel.
- **Secrets never in code.** A browser key that must ship is restricted, not hidden.
- **No silent failures.** No bare `except`; a caught error becomes a visible, structured
  record. One source failing never kills a run and is never swallowed.
- **A red check is never argued past.** Re-run it once; if it flips, `gh issue create`
  against the named test, and the green re-run stands.
- **Every parse asserts its shape**, so a site changing fails loudly at the parse rather
  than quietly as wrong data.
- **The warehouse is append-only where the schema says so**; triggers enforce it. A
  rebuild archives, it does not delete.
- **A backup before anything destructive**, named out loud, and the copies are bounded.
- **Parsing lives in one `normalize` module.** A connector parsing money, units,
  Arabic-Indic digits or VAT locally fails review.
- **A change to `normalize` or a connector proves itself against the frozen corpora**:
  `python -m scrapex.contract` re-freezes, `CONTRACT_VERSION` bumps only when the change
  is breaking, and every changed vector and `tests/fixtures/live/` row is explained in
  the PR body.
- **No module without its test file**, and error paths are tested like happy ones.
  `node --test extension/tests/*.test.mjs` and `node --test apps_script/tests/*.test.mjs`
  run the JS suites `pytest` never reaches; there is no `package.json`, and the extension
  ships one vendored library (`extension/vendor/tabulator.min.js`) — add no second.
- **A local green ran no browser test.** The `importorskip("playwright")` suites report
  *skipped* until `pip install -e .[dev,browser]` and `python -m playwright install
  chromium`.
- **Integration tests run the real `db/engine/schema.sql`**, never a fixture schema.
- **Respect the politeness budget.** A crawl that hammers a site is a defect, and
  `crawl_obey_disallow` ships at `0` (`scrapex/settings.py:84`): never set a source
  `active: true`, or leave `robots` at its default, without his word.
- **Never start a run you cannot watch to the end.** A crawl outlasts a session and holds
  the write lock while it runs.

## Review

Four dimensions: **architecture** (boundaries, coupling, data flow, bottlenecks, single
points of failure, the security surface) · **code quality** (module structure, DRY, error
handling and the edge cases it misses, over- and under-engineering) · **tests** (coverage
gaps, assertion strength, missing edge cases, untested failure paths) · **performance**
(N+1 and query patterns, memory, caching, slow paths). Rank every finding **must fix** ·
**should fix** · **optional** · **not an issue**, and report nothing rather than pad it. A
reviewer reads the diff and the repository; the PR body is a claim to check against them,
never a defence that settles a finding.

**When he asks for one**: one dimension at a time, stopping after each for his word. Per
issue: the problem with `file:line` · two or three options **including "do nothing"** ·
per option the effort, risk, blast radius and maintenance burden · the recommendation
mapped to the preferences.

**Before every merge — green is not mergeable.** A change merges only when CI is green on
the head it has right now — a recorded green expires — and a critical review returns
nothing: a reviewer session per dimension, an adversary attacking what they returned, fix
what survives, push, review again. On a branch that is not yours, what the pass finds goes
back to its author, and the merging session pushes no behaviour change it did not write.
Clean means no *must fix* and no *should fix*; *optional* becomes an issue, never a fix in
the same PR. **The report names each reviewer and its verdict; a report that cannot is a
failed pass, not an empty one.** **A finding advances only with a demonstration** — a
failing test, a quoted line whose own text shows the defect, or a counted query;
undemonstrated, it drops one rank and is filed. **Split before the review, not after**:
over 1,000 changed lines outside `tests/` and fixtures, split first, and five passes that
do not converge say the same thing too late. Documentation-only changes are exempt —
except this file, whose one pass asks whether the edit weakens a control and whether each
added line meets "How this file evolves".

## The tools, not the files — never record findings, plans or progress in a markdown file

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

`docs/archive/` and `docs/plans/` are frozen, kept only because code comments cite their
numbers. **No new `R-`/`REQ-`/`OP-` number is issued** — GitHub assigns the number now.

## Three traps that cost an afternoon each

**A running engine is not your edit.** Python imports once, so an engine started before
your change keeps serving the tree it loaded, and `__file__` is correct throughout.
Restart it from the panel; `/api/health` reports `stale` and the badge reads *Restart
needed* (`scrapex/provenance.py`).

**Several live checkouts, and both imports and edits default to one of them.** `scrapex`
is pip-installed editable against a checkout that may not be this worktree —
`python -c "import scrapex; print(scrapex.__file__)"` says which. Derive every path from
the worktree root, and in a scratch script assert on a **symbol you just added**;
`__file__` catches a misdirected import, never a misdirected edit.

**Never hash a repo file's raw bytes.** `.gitattributes` sets `* text=auto`, so the repo
stores LF and Windows checks out CRLF. Normalise `b"\r\n"` → `b"\n"` first.

## How this file evolves

**Keep improving it — every session**, and this stays the only rules document.

- **A rule earns its place by changing what a session does.** If it changes no action, it
  does not belong; if it belongs beside a line of code, put it there instead.
- **Write it as an instruction, not a story.** One clear line. No dates, no quotes, no
  incident reports — the reason lives in the PR that added the rule.
- **Delete one that stopped being true** before adding, and merge into an existing rule
  rather than repeating it — but **never delete a control to make room**. Past 150 lines
  the next change here starts by pruning what no longer changes an action; if nothing can
  go, move detail to a comment beside the code or to a `.claude/` skill.
