> # ✅ DONE — 2026-08-20
>
> **Every step of this plan was executed.** It is archived here so its state is
> legible without reading it, and so it is visible from both of the owner's machines
> — `~/.claude/plans/` is one machine and one account, which is what
> [R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository) exists to
> prevent.
>
> **What it delivered — nine pull requests merged, in this order:**
>
> | | |
> |---|---|
> | `a683d70` | **#215** the profile background reverted, which unblocked `main` |
> | `bf2ae66` | **#220** the Arabic half was a column and not a value, and `/source/{key}` answered 404 for a dataset |
> | `a1d077f` | **#213** DEC-8: the engine's Data page is a port, not a rebuild |
> | `3d265cd` | **#216** the CI tiers, the docs gate, and two guards that had become silent skips |
> | `cb869f9` | **#222** [R-18](../RULINGS.md) — merge it when it is green |
> | `785533c` | **#221** the two generic flags lit, at `PARTIAL` |
> | `ce80886` | **#217** the Engine page is two screens, plus three defects an adversarial review confirmed |
> | `42dbf23` | **#223** a dataset exports a workbook and loads whole |
> | `72f93a8` | **#218** `main`'s padding is a token, and the two full-bleed screens finish #217's refactor |
>
> Plus: **six pieces of uncommitted work rescued** onto branches of their own,
> `DEC-7` re-measured over 172 refs, and `docs/STATE.md` corrected — it had been
> stating something **false**, not merely stale.
>
> ## And the reason this archive carries a status banner rather than just a date
>
> **Steps 6–8 were nearly dropped.** Steps 1–5 landed, the pull requests merged, and
> the work looked finished. Then the owner asked directly:
>
> > «هل تم الانتهاء من تنفيذ Plan… فكثير من الخطط توضع ولا تستكمل الى النهاية»
>
> He was right. Three steps were outstanding, and the tail was the valuable part: the
> state file was **actively false** on `main`, the `DEC-7` measurement would have been
> taken a fourth time for want of being written down, and six drafts were one
> `git checkout` from gone. A plan filed with a date alone would have read as complete
> at exactly the moment it was not.
>
> **Provenance, stated because the index below promises the rescued plans are
> verbatim:** this plan was authored on 2026-08-20 and restored into this file from
> the session transcript — the working copy at `~/.claude/plans/` had been overwritten
> in the same session, before the request to archive it arrived. It is a faithful
> restoration, not an untouched artefact.

---

# Plan — review every uncommitted change, then land the five open pull requests

## Context

The other workers have stopped. What they were holding is now spread across
uncommitted working trees and open pull requests, and nobody is watching any of it.
The owner asked for a review of all uncommitted work and for the outstanding work to
be landed.

**Scope, as he set it: the five open pull requests, plus the uncommitted work.** The
remaining branches are to be **measured and reported, not merged and not deleted.**

That boundary is the right one, and it is his own prior finding that shows why.
`docs/BACKLOG.md` **DEC-7** measured this on 2026-08-12 across 117 branches:

| result | count |
|---|---|
| fully contained in `main` — merging changes **nothing** | **47** |
| merging would **conflict** | 68 |
| merges cleanly and **adds** something | **1** |

Of the 68 conflicting, **31 carry a subject line already on `main`** — squash-merged,
conflicting only because `main` moved on. "Merge everything remaining" would
therefore have meant merging almost nothing and touching a hundred branches to find
it out.

DEC-7 also fixes the method, and two obvious tests are wrong here:

- `git branch --merged` is **meaningless** — this repository squash-merges, so a
  squash-merged branch reads as unmerged for ever.
- `git diff origin/main...<branch>` is **also wrong** for "is it in main now": three
  dots means merge-base-to-branch, which answers what the branch added when it
  forked. It produced the discredited figure of 105 branches holding work.
- **The test that settles it:** `git merge-tree --write-tree origin/main <branch>`
  against `git rev-parse origin/main^{tree}`. Equal trees means merging changes
  nothing.

---

## What is established

### CI works again — verified, not taken on trust

The account-level block on GitHub Actions has cleared. Runs from 06:34 today onward
complete with steps genuinely executed (latest: 9 steps, success), where every run
from 2026-08-19 14:28 until then failed with **no step run at all** and the
annotation *"The job was not started because recent account payments have failed."*

**So the normal gate applies again — SR-23, green CI on every push** — and it is a
real gate rather than a formality. Two consequences below: #213 and #216 carry
**stale red from the outage** and need their checks re-run, not fixed.

### `main` is at `27ab00f`

#215 (the background revert), #214 (the documentation system, REQ-08 + REQ-09) and
#219 are in. `VERSION` has not moved; R-07 still blocks it.

### The five pull requests, as they actually stand

| PR | state | what blocks it |
|---|---|---|
| **#220** | `MERGEABLE`/**CLEAN**, everything green incl. CodeQL | nothing — but the uncommitted docs work belongs in it first |
| **#213** | `MERGEABLE`/`UNSTABLE`, all checks FAILURE | **stale red from the outage.** Re-run; the content is one documentation file |
| **#216** | `MERGEABLE`/`UNSTABLE`, lint+scope+parity FAILURE, test SKIPPED | same outage. Re-run |
| **#217** | **`CONFLICTING`**, lint/parity green, `test` FAILURE on one run and SUCCESS on the other | rebase off `ac3a5af`; the split verdict needs explaining before it merges |
| **#218** | **`CONFLICTING`**, `test` FAILURE | rebase, **and it depends on #217** |

### The uncommitted work is real, measured, and exists nowhere else

The main working copy is on **`the-arabic-half-was-a-column-not-a-value`** (#220, two
commits `00dbd7e`, `14598f6`) with `docs/LESSONS.md` (+45) and `docs/STATE.md`
(+48 −11) modified on top. Verified absent from every commit:

```
git log --all -S'Presence is not arrival' -- docs/LESSONS.md            → nothing
git log --all -S'A success count is not a write count' -- docs/LESSONS.md → nothing
```

It carries facts held nowhere else: 1,728 snapshots (864 EN + 864 AR), 34,550
revisions, an 835 MB warehouse, per-column Arabic fill rates for all seven pairs, and
a six-pass sweep concluding the warehouse holds **11,059 of at least 17,283
contractors — about 64%, and not converged.** Plus two lessons: *presence is not
arrival* (a test asserting a column exists can never catch an empty column) and *a
success count is not a write count* (864 "re-approved" pages wrote zero rows).

Left untouched deliberately: **SR-19** forbids sweeping another session's work into a
commit, **SR-21** treats it as a draft to review rather than build on.

### Neither #217 nor #218 introduces the colour literal

Both are based on `ac3a5af` so both *inherit* `#FFFFFF` at `extension/app.css:1180`,
the literal that reddened `main` for two days. Neither adds it:

```
git diff origin/main...origin/<branch> -- extension/app.css | grep '^+' | grep -E '#[0-9a-f]{3,8}'
→ empty, for both
```

**They need a rebase, not a fix.**

---

## The plan

### 1 · Review the uncommitted #220 work, then commit it onto #220

Highest risk first: it is the only work that exists in one place, and one
`git checkout` erases it.

- Check **every** measured figure against the live warehouse at
  `~/.scrapex/engine/scrapex-engine.db` — re-count `generic_page_snapshot`,
  `generic_record_revision`, the per-column Arabic fill rates and the database size.
  The text claims measurements; #214's citation guard exists because a document that
  claims one must be one.
- Confirm `DEC-9` and `DEC-10` really exist in `docs/BACKLOG.md` before committing
  text that cites them — `14598f6` appears to add them; verify, because the guard
  reads both files.
- Run `tests/test_the_documents_cite_what_they_claim.py`.
- Commit onto **#220's branch**: C2 puts the state document in the same pull request
  as the work it describes.

**Files:** `docs/LESSONS.md`, `docs/STATE.md`.

### 2 · Merge #220

Green and `CLEAN` already. Merge once step 1's commit is green on the same terms.
It fixes a real data defect — four of seven bilingual columns NULL across 11,059
rows — so it should not wait behind the others.

### 3 · Re-run and merge #213, then #216

Both are `MERGEABLE` with **stale red from the outage**. Push an empty-effect
refresh (rebase onto current `main`) so the checks re-run against a working CI, then
read them properly.

- **#213** — DEC-8, one documentation file. Already rebased and conflict-free.
- **#216** — the CI tiers, two commits. **Ask the owner to make
  `migration-authority` a required check**: a new job is not added to branch
  protection automatically, and until it is, a migration-stream failure will not
  block a merge — weaker than the inline variable it replaced.

### 4 · Rebase #217, explain its split test result, then act on the review

- Rebase onto `main` (it is based on `ac3a5af`; the rebase also drops the inherited
  literal).
- **Explain the split first:** `test` reported FAILURE on one run and SUCCESS on the
  other for the same commit. Either it is OP-19's load-dependent race — which was
  re-measured 2026-08-19 as pass/FAIL/FAIL on an unchanged tree — or it is a real
  defect in this branch. Read the failing run's log and say which. Do not
  rerun-until-green.
- Then apply the confirmed findings of the adversarial review now running over six
  lenses: behaviour of the two-screen split and the new `extension/releases.js`, the
  design system (`components.css` copied into three directories), whether the
  rewritten `tests/test_panel_dom.py` (+387 −278) dropped assertions, injection in
  the new rendering, and the project's own rules — including **C2**, since neither
  #217 nor #218 touches `docs/STATE.md`.

**Files:** `extension/app.css`, `extension/app.html`, `extension/app.js`,
`extension/releases.js`, `tests/test_panel_dom.py`, `components.css` ×3,
`tools/engine_verify.py`.

### 5 · Rebase #218 onto the result of #217, then merge

**Last, and only after #217.** Its premise is #217's two-screen layout, and both
touch `extension/app.css` and `tests/test_panel_dom.py` — so it rebases on the
post-#217 `main`, not on today's. Check specifically whether both add a test function
of the **same name** to `test_panel_dom.py`, which would collide silently.

### 6 · Settle the other uncommitted trees — review and report, no deletion

For each worktree holding changes, decide **real content or noise**: a CRLF-only diff
collapses under `git diff -w --ignore-cr-at-eol`; whitespace-only and
mass-pure-deletion trees are stale scratch, not authored work.

| worktree | branch | first-pass signal |
|---|---|---|
| `Temp/wt-43`, `wt-60`, `wt-64`, `wt-main`, `claude/pr180` | `review-*`, detached | ~36 files each, **pure-deletion** numstat |
| `.claude/worktrees/gracious-kare-dd515a` | `claude/issue-33-display-time-zone` | 6 modified |
| `.claude/worktrees/keen-blackburn-7d94e9` | same name | 3 modified |
| `.codex/worktrees/1431/ScrapeX` | `codex/source-card-display-review` | 4 modified — DEC-7 says superseded |
| `C:/tmp/ScrapeX-selected-card-layout` | `codex/selected-card-layout` | 3 modified — same |
| `.claude/worktrees/happy-swartz-9ca21d` | `claude/beautiful-lichterman-659ad2` | 2 modified |
| worktree on `every-recommendation-recorded` | — | 1 modified |

Real work gets committed to its own branch or reported as a draft under SR-21.
**Nothing is deleted and no worktree removed** — that is his call, and it is in the
open-questions list below rather than in this plan's actions.

### 7 · Measure the branches and report — no merging, no deleting

Run DEC-7's test over every branch with no open PR and sort into its three buckets
(contained / conflicting / cleanly-adds), with the current local and remote counts
against DEC-7's 148 and 128. Deliver it as a table with a one-line description and a
recommendation per branch.

Then **update DEC-7 itself** with the re-measurement. It is the entry that asked to
be reminded, it has been re-measured twice, and a third measurement that is not
written down will be repeated a fourth time.

### 8 · Record the position, per C2

Update `docs/STATE.md` with where the five PRs ended and what the branch measurement
found. Any recommendation the owner declines is kept with its reason, per **C4**.

---

## Verification

- `python -m pytest -q` on each branch before merging. Expect **one** pre-existing
  failure: `test_a_killed_engine_does_not_leave_a_job_claiming_to_run` — **OP-19**, a
  load-dependent race, pass/FAIL/FAIL on an unchanged tree on 2026-08-19. It is not
  caused by anything here, and it is also the first suspect for #217's split result.
- `tests/test_the_documents_cite_what_they_claim.py` after every documentation edit.
- `ruff check scrapex/` and the eslint invocation from `.github/workflows/ci.yml`.
- For #217: `tests/test_vendor.py` (the colour-literal guard) and
  `tests/test_panel_dom.py`, plus the CI floor — the panel suite must still collect
  **≥ 40** tests, and the extension gate **≥ 300**.
- **CI is the gate, and it works again.** Every merge waits for green on the PR
  rather than on a local run, per SR-23.

## What needs the owner

1. **`migration-authority` as a required check** — branch protection, his settings,
   named in #216.
2. **The two feature flags** — `GENERIC_EXTRACTION` and `GENERIC_DATASET_CATALOG` are
   still `False` at `scrapex/features.py:57` and `:62` while their own written
   condition is met.
3. **Deleting branches and removing scratch worktrees** — deliberately outside this
   plan; he gets the measurement and decides.

---

## Postscript — how each step actually ended

Written after the fact, because a plan that records only its intentions teaches less
than one that records the difference.

| step | outcome |
|---|---|
| 1 | Done. `76f725c` — and **every figure re-measured**; one (`835 MB`) had gone stale the same day and was corrected to `796 MB + 393 MB WAL` |
| 2 | Done. `bf2ae66` |
| 3 | Done. `a1d077f`, `3d265cd`. **#216 needed a real code fix first**: its own new docs gate failed on `tests/test_the_request_board_matches_its_entries.py`, which arrived on `main` in #219 and carried no mark |
| 4 | Done. `ce80886`. **The split was NOT OP-19** — the `push` run tested the branch alone with the inherited literal, the `pull_request` run tested the merge with `main`'s revert. Three MAJOR review findings fixed; the citation guard caught five pinned citations shifted by four lines |
| 5 | Done. `72f93a8`. **Rebased rather than resolved**, because #218's side of the one conflict carried the reverted `#FFFFFF`, and its side of the test conflict would have resurrected a test #217 deleted on purpose |
| 6 | Done. Six drafts committed onto their own branches; **pushed to `preserve/*` names** after discovering `origin` held ten commits the worktree did not — force-pushing over unread work is the opposite of preserving it. Five `Temp/` trees confirmed as stale scratch, nothing deleted |
| 7 | Done. **172 local / 125 remote: 60 contained, 110 conflicting, 2 adding.** One of the two is a **trap** — `feat/the-warehouse-travels-through-drive` reads as adding because its commit landed and `scrapex/drive.py` was then deliberately deleted |
| 8 | Done. And the state file was found **false**, not stale: it claimed CI had not run since the outage and that every open PR showed red checks, with zero PRs open and CI working |

**Two mistakes of mine belong in the record.** `git add -A` swept 33 MB of `.vs/`
indexes into a commit — the exact `SR-19` violation being quoted all session; caught
in `--stat`, rewound, and `.vs/` added to `.gitignore` with the incident named. And
twice a narrow test run was called sufficient: `tests/test_features.py` alone missed
four things asserting on the feature manifest, and the panel suite was run without
the guard that watches the *shape* of the suite. Both were caught by the full run,
after the pull request was already open.
