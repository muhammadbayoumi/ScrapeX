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
  Two weak guards to name as such: a test that only asserts a string appears in a source
  file catches the string's deletion, never the string ceasing to take effect; and a
  browser test that reads an animated or measured value once (a colour under a
  transition, a size before layout settles) passes on a fast machine and fails on a slow
  one, so it waits, with a bound, for the expected value instead.
- **performance** — N+1 and query patterns, memory, caching, slow paths. Judge against
  the real warehouse, not a fixture: ~17,900 contractor profiles, 408,547 memberships,
  a 2.1 GB database.

**A change that adds or rewords user-facing text** is also read against Supabase's
`copywriting.mdx` at the pin, as `docs/DESIGN-SYSTEM.md#copy` sets out. The wording test
checks only the rules a machine can; the rest are the review's.

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
   only record of its false negatives. A finding that something is unused, dead or has
   no caller is believed only after a search of the whole tree — templates, the
   extension, the authored sources and their generated copies, and the later branches of
   a stack — because a reviewer reads the files around the diff, and the caller is often
   on another surface.
4. **Fix what survives, push, review again.** On a branch that is not yours, what the
   pass finds goes back to its author; the merging session pushes no behaviour change it
   did not write.
5. **Clean means no must fix and no should fix.** An *optional* becomes an issue —
   `gh issue create` — and never a fix in the same PR.
6. **Merge only a head that contains today's `main`.** Right before merging, run
   `git log <head>..origin/main`. If it prints anything, merge `origin/main` into the
   head, push, and wait for green on that new SHA, then merge. Other sessions merge to
   `main` all day: the ruleset refuses a merge whose required checks were reported on a
   head behind `main` ("N of N required status checks are expected"), and a `VERSION`
   bump on `main` fails `version-intent` on any head that lacks it.

Rules that decide the outcome:

- **The report names each reviewer and its verdict, as a comment on the PR the moment
  each pass returns.** A verdict held only in a session's context dies with the session,
  and the next one runs the gate again. For one that returned no verdict, the report
  says which of three it was: it died, it timed out, or it was **refused before it
  started**. A report that cannot is a **failed pass, not an empty one** — all three read
  as "this dimension found nothing", and a refusal never reaches the runner at all, so
  the dimensions most likely to be blocked are the ones that touch secrets and identity.
- **A finding advances only with a demonstration**: a failing test, a quoted line whose
  own text shows the defect, or a counted query. Undemonstrated, it drops one rank and is
  filed.
- **Review a part of a stack where it will run.** A part that nothing loads yet — a
  renderer, a stylesheet, a module the next part wires in — passes every test at its own
  head, because no test reaches it. Its reviewers also run their probes against the top
  of the stack, rebuilt on today's `main`, and a guard that only bites there is added in
  this part when it can be written here, or else in the part that wires it in.
- **Split before the review, not after.** Over 1,000 changed lines outside `tests/` and
  fixtures, split first. Five passes that do not converge say the same thing too late.
- **A split leaves a stack, and a squash merge breaks it.** Merging the parent collapses
  its commits into one, so the child's `git rebase` fails outright — *"Could not apply"* —
  because its commits correspond to nothing in `main`'s history. Do not force it past
  that. Rebuild the child on `main` from its own commits, in this order:
  1. **Find them: `git cherry -v <parent-branch> <old-child>`.** A parent rebased after
     the child branched leaves the child holding stale copies of its commits, and both
     `git log <parent-branch>..<old-child>` and `git diff <parent-branch>...<old-child>`
     include them. `git cherry` marks each unchanged copy `-` and every other commit `+`.
     A `+` is still a copy, one the rebase changed, when
     `git log --format='%ad %s' <parent-branch>...<old-child> | sort | uniq -d` (Git Bash)
     prints its author date and subject. Do not decide it from `git range-diff`: it pairs
     by likeness, and calls a small own commit a copy. A merged parent's deleted branch
     is still on the remote:
     `git fetch origin pull/<parent>/head:refs/remotes/origin/pr/<parent>`, then use
     `origin/pr/<parent>`; a bare fetch lands only in `FETCH_HEAD`, which the next fetch
     overwrites.
  2. **`git switch -c child-v2 origin/main`, then `git cherry-pick` the child's own
     commits in the order `git cherry` prints them.** Never
     `git checkout <old-child> -- <files>`: a file the parent changed again after the
     child branched comes back in its old version, silently. The cherry-pick stops on
     that file instead; keep `main`'s side and re-apply the child's change to it, and a
     resolution that picks a behaviour goes back to the author. Resolve only the authored
     file: a conflict in a generated copy is settled by regenerating the copies with the
     repository's tool (`tools/sync_design_assets.py`), never by editing them. Before
     `git cherry-pick --continue`, prove no conflict marker is left — `git diff --check`
     prints any, and `git diff --cached --check` once they are staged — because a scripted resolution that fails without stopping the script
     leaves the markers in, and `git add -A` commits them.
  3. **Read it: `git range-diff --creation-factor=100 <parent-branch>..<old-child>
     origin/main..HEAD`.** Each `<` must be a copy step 1 found. Each own commit shows
     `=`, or `!` where every changed patch line (`-` or `+` in the second column) is a
     conflict you resolved; a changed context line (blank second column) is `main`
     moving beside it, and a `Commit message` hunk is your own edit.
  4. **Retarget, then push**: `gh pr edit <n> --base main`, then
     `git push --force-with-lease=<branch>:<old-child> origin HEAD:<branch>`, the lease
     pinned to the SHA it replaces. Pushed first, the head is tested against the parent's
     branch, or not at all when it conflicts with it; and the retarget starts no `ci.yml`
     run, because a base change arrives as `edited`, which `ci.yml`'s default event types
     leave out.

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

**Every reviewer is given a time budget — about an hour — and told to report what it has
when it is spent.** A mutation pass has no natural end and will run for hours; one that
overruns is asked to report its results so far, never restarted, and its unrun mutations
are listed in its verdict.

**After a fix, re-run the dimension whose file changed**, not the panel.

**Eight agents is the ceiling for one PR.** Needing more is evidence the change is too big
to review — the same answer the line-count rule already gives.

Documentation-only changes are exempt — **except `CLAUDE.md`**, which takes one pass, not
the loop, asking whether the edit weakens a control and whether each added line meets
"How this file evolves".
