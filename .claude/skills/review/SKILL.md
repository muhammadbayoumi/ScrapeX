---
name: review
description: How a ScrapeX change is reviewed, and the gate it passes before it merges. Use before merging any code, tests or workflow change, and whenever a review is asked for by name or by description ("review this", "what is wrong with this PR", "is this ready").
---

# Review

Four dimensions, and every review covers all four:

- **architecture** — boundaries, coupling, data flow, bottlenecks, single points of
  failure, the security surface.
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

1. **Check CI on the head the branch has right now.** A recorded green expires — a
   commit can land after the green that produced it. `gh pr checks <n>` and
   `gh pr view <n> --json headRefOid`.
2. **A reviewer session per dimension**, all four, over the same diff.
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

- **The report names each reviewer and its verdict.** A report that cannot is a **failed
  pass, not an empty one** — a panel whose reviewers died reports the same silence as a
  panel that found nothing.
- **A finding advances only with a demonstration**: a failing test, a quoted line whose
  own text shows the defect, or a counted query. Undemonstrated, it drops one rank and is
  filed.
- **Split before the review, not after.** Over 1,000 changed lines outside `tests/` and
  fixtures, split first. Five passes that do not converge say the same thing too late.

Documentation-only changes are exempt — **except `CLAUDE.md`**, which takes one pass, not
the loop, asking whether the edit weakens a control and whether each added line meets
"How this file evolves".
