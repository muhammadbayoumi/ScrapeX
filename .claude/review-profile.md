# Review profile — ScrapeX

The project's half of the `review` skill. The skill is the same file in every project and
carries the dimensions, the ranks, the gate and the budget. This carries the six things it
cannot know, and nothing else.

**Standing facts only.** A finding, a plan or a progress note in here is the thing
`CLAUDE.md` forbids; those go to `gh`, by the `record-it` skill. And **no `file:line` in
either half** — a citation is one more thing that drifts, and neither file needs one to
say what a reviewer must open.

## 1. The rules document

`CLAUDE.md`. All of it is in force, and its preferences decide every close call and every
recommendation a review makes. This file repeats none of it except where a dimension has
to act on it — §2, and the closing note.

`AGENTS.md` is a generated copy. Edit `CLAUDE.md`, then regenerate:
`python -m scrapex.cli export-version`.

## 2. The controls whose lines a reviewer opens

The architecture dimension says which of these it opened:

- SQL built by string — scraped content is untrusted input, all SQL is parameterised
- a bare `except`, or a caught error that never becomes a visible, structured record
- a second writer to the warehouse, or a route around `DbLockedError`
- a secret in code, or a shipped browser key that is hidden rather than restricted
- parsing outside `normalize` — money, units, Arabic-Indic digits, VAT
- a source left `active: true`, or `robots` at its default — the politeness budget
- an append-only table written where the schema says append-only, or a rebuild that
  deletes instead of archiving
- a capability with no panel control, or a control drawn for a route that 404s
- a wrong value corrected in the exporter, the Apps Script or the Sheet instead of at the
  connector or `normalize`
- a parse that asserts nothing about its shape, so a site changing fails quietly as wrong
  data instead of loudly at the parse

## 3. The real scale the performance dimension judges against

~17,900 contractor profiles, 408,547 memberships, a 2.1 GB database. Never a fixture.
Numbers age: re-count at the warehouse before a finding rests on one.

## 4. Proving the environment, before any fan-out

Several live checkouts exist, and `scrapex` is pip-installed editable against one that may
not be this worktree. Take both:

- `python -c "import scrapex; print(scrapex.__file__)"` — catches a misdirected import
- an assertion on a symbol the change itself added — catches a misdirected edit

Neither catches a stale engine: Python imports once, so an engine started before the
change keeps serving the tree it loaded while `__file__` stays correct throughout. The
panel reports it — `/api/health` says `stale`.

## 5. The surfaces a cold read crosses

panel ↔ engine ↔ warehouse. A change inside one surface does not earn a cold read; one
that crosses does. A change to `normalize` or a connector crosses into the frozen corpora
as well — `python -m scrapex.contract` re-freezes, and every changed vector is explained
in the PR body.

## 6. The record

`gh issue list --search` before the pass, `gh issue create` for every *optional* that
survives it. The `record-it` skill carries the command for each kind of record and each
kind of question. `gh auth switch` is global and repoints every other session — scope the
account to your own process instead, per `CLAUDE.md`.

## Also from `CLAUDE.md`, because the tests dimension acts on it

A local green ran no browser test unless Playwright is installed, and `pytest` never
reaches the JS suites — `node --test extension/tests/*.test.mjs` and
`node --test apps_script/tests/*.test.mjs` — which CI runs separately, alongside a lint
the Node test runner says nothing about. A tests-dimension verdict that rests on `pytest`
alone covers less than it sounds like.
