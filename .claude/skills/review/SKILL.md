---
name: review
description: How a ScrapeX change is reviewed, and the gate it passes before it merges. Use before merging any code, tests or workflow change, and whenever a review is asked for by name or by description ("review this", "what is wrong with this PR", "is this ready").
---

# Review

Four dimensions, and every review covers all four:

- **architecture** — boundaries, coupling, data flow, bottlenecks, single points of
  failure, the security surface. Name the `CLAUDE.md` controls you opened the lines for:
  SQL built by string, a bare `except`, a second writer to the warehouse, a secret in
  code, parsing outside `normalize`, a source left `active: true` or at default `robots`.
- **code quality** — module structure, DRY as `CLAUDE.md` defines it, error handling and
  the edge cases it misses, over- and under-engineering.
- **tests** — coverage gaps, assertion strength, missing edge cases, untested failure
  paths. The strongest finding here is a vacuous guard: a test that still passes when the
  code it claims to protect is deleted or inverted. Name the mutation that survives.
- **performance** — N+1 and query patterns, memory, caching, slow paths. Judge against
  the real warehouse, not a fixture: ~17,900 contractor profiles, 408,547 memberships,
  a 2.1 GB database.

Rank every finding **must fix** · **should fix** · **optional** · **not an issue**, and
**report nothing rather than pad it**. A padded review spends a pass and teaches the next
session to discount the output.

A reviewer reads the diff and the repository. The PR body is a claim to check against
them, never a defence that settles a finding.

## When he asks for one

One dimension at a time, stopping after each for his word. Per issue:

- the problem, with `file:line`
- two or three options, **including "do nothing"**
- per option: the effort, the risk, the blast radius, the maintenance burden
- the recommendation, mapped to the preferences in `CLAUDE.md`

## The merge gate

`CLAUDE.md` binds this: green is not mergeable. Run it before every merge of a code,
test or workflow change.

0. **Read the record before you spawn anything.** `gh issue list --search`, the branch's
   own PRs, and the comments on them. The most expensive finding of the study that wrote
   this section was already written down: one `gh issue list` surfaced a recorded *must
   fix* that fourteen reviewer sessions had not found, because it was recorded rather
   than hidden in the code.
1. **Identify the green by head SHA, never by a tally.** A recorded green expires — a
   commit can land after the green that produced it. And a row count is an artifact of
   the CI config, not a number of checks: `gh pr checks` prints a row per run, so an
   unfiltered `on: push` doubles most rows, and it exits non-zero while any duplicate is
   still pending, which reads as red on a head that is green. Take `headRefOid`, then
   read the check-runs for that exact SHA and require each context by name.
2. **Reviewers after the green, never before it, and only as many as the change earns**
   — see *What a pass may spend*. Each covers one dimension over the same diff. A panel
   launched at a head whose CI then goes red bought nothing.
3. **An adversary attacks what they returned.** It opens every cited `file:line`, kills
   what the line does not support, demands a demonstration for every must fix, and then
   reads the change cold to find what all four walked past. It records **every kill with
   its reason** — its own success metric is killing findings, so the kill list is the
   only record of its false negatives.
4. **Fix what survives, push, review again.** On a branch that is not yours, what the
   pass finds goes back to its author; the merging session pushes no behaviour change it
   did not write.
5. **Clean means no must fix and no should fix.** An *optional* becomes an issue —
   `gh issue create` — and never a fix in the same PR.

Three rules that decide the outcome:

- **The report names each reviewer and its verdict**, and for one that returned no
  verdict, which of three it was: it died, it timed out, or it was **refused before it
  started**. A report that cannot is a **failed pass, not an empty one** — all three read
  as "this dimension found nothing", and a refusal never reaches the runner at all, so
  the dimensions most likely to be blocked are the ones that touch secrets and identity.
- **A finding advances only with a demonstration**: a failing test, a quoted line whose
  own text shows the defect, or a counted query. Undemonstrated, it drops one rank and is
  filed.
- **Split before the review, not after.** Over 1,000 changed lines outside `tests/` and
  fixtures, split first. Five passes that do not converge say the same thing too late.
- **A split leaves a stack, and a squash merge breaks it.** Merging the parent collapses
  its commits into one, so the child's `git rebase` fails outright — *"Could not apply"* —
  because its commits correspond to nothing in `main`'s history. Do not force it past
  that. Rebuild the child on `main` and carry its files over:
  `git switch -c child-v2 origin/main`, then `git checkout <old-child> -- <its files>`.
  That stages them, so read the result with `git diff HEAD` and confirm it is the addition
  you expect — a plain `git diff` shows nothing and looks like an empty change.

## What a pass may spend

A review is paid for in tokens, and an agent that reads the wrong tree — or a tree CI is
about to reject — buys nothing. These counts are the rule, not a target to reach.

**Before any fan-out the orchestrator proves the environment once, itself, cheaply:** the
head SHA it means to review, where `import scrapex` resolves from, and a symbol the change
itself added. `__file__` catches a misdirected import and never a misdirected edit, so it
takes both. Seconds, and no tokens — and it is the whole distance between a panel and
eight green mutations that measured nothing.

**How many, from the lines changed outside `tests/` and fixtures:**

| changed | reviewers |
|---|---|
| ≤ 50 | **none** — read it and run the mutations yourself |
| 51–200 | 1–2, the dimensions the diff actually touches |
| 201–600 | 4, one per dimension |
| 601–1000 | 4, plus one adversary per **surviving** finding |
| > 1000 | split first, by the rule above |

**The table sizes the fan-out and nothing else.** Steps 0 and 1 — the record, and the
green proved by head SHA — run at every size including **none**: they are the two
cheapest checks in the gate, and no reviewer buys either.

**A cold read is for a change that crosses a surface** — panel ↔ engine ↔ warehouse — not
for every pass.

**No agent without a falsifiable question and a demonstration it must run.** "Review this"
is not a question, and what comes back from one cannot be ranked.

**After a fix, re-run the dimension whose file changed**, not the panel.

**Eight agents is the ceiling for one PR.** Needing more is evidence the change is too big
to review — the same answer the line-count rule already gives.

Documentation-only changes are exempt — **except `CLAUDE.md`**, which takes one pass, not
the loop, asking whether the edit weakens a control and whether each added line meets
"How this file evolves".
