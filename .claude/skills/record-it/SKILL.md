---
name: record-it
description: Where ScrapeX keeps its work — the gh and git command for each kind of record and each kind of question. Use when recording a finding, a plan, a handover or progress; when asked what is open or in flight; and when digging for why a line exists, what an R- or OP- number means, or whether something was already decided.
---

# The tools, not the files

## First, pin the account to THIS process

```bash
export GH_TOKEN=$(gh auth token --user <the account that owns the repository>)
```

**Never `gh auth switch`.** It writes global state: the active account changes for every
session on this machine, and the others collapse mid-work with `Repository not found` —
GitHub answers 404, not 403, for a private repository the active token cannot see, so the
failure reads as a deleted repo rather than a wrong account. That happened on 2026-09-11,
with three sessions running.

`gh` ignores the active account entirely when `GH_TOKEN` is set, and `git push`/`fetch`
take it through gh's credential helper. The variable is per-process, so two sessions can
work on two different accounts at the same moment and neither touches the other, and no
setting is changed permanently.

Every command below is a `gh` command, so this comes first.

## Where the work lives

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
