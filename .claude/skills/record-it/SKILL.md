---
name: record-it
description: Where ScrapeX keeps its work — the gh and git command for each kind of record and each kind of question. Use when recording a finding, a plan, a handover or progress; when asked what is open or in flight; and when digging for why a line exists, what an R- or OP- number means, or whether something was already decided.
---

# The tools, not the files

Work is never recorded in a repository markdown file. Every kind of record has a home,
and every kind of question has a command.

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

## The three that are not obvious

- **`git log -S '<the line>'`** finds the commit that introduced or removed a line, which
  is how you reach the argument behind it. The comment beside the line comes first; the
  PR that added it comes second.
- **`git log --grep=R-84`** is the only bridge from an old requirement number cited in a
  code comment to what it meant. `docs/archive/` is where it lands.
- **`gh pr list --state all --search R-84`** answers "was this already decided", which is
  the question that saves a session from re-litigating a closed argument.

## On this machine

`gh` is not on `PATH`. In bash: `export PATH="/c/Program Files/GitHub CLI:$PATH"`.
