# ScrapeX — the ordered plan

*Written 2026-08-09, from facts re-measured the same day.*

## Why this document exists

Five lists describe the work, and every one of them is honest:

| document | what it is good for | what it cannot tell you |
|---|---|---|
| `docs/PLATFORM-PLAN.md` | the milestones M0–M8 and what each means | which of the open faults blocks which milestone |
| `docs/BACKLOG.md` | every known fault, measured, with its evidence | which one to fix first |
| `docs/MASTER-PLAN.md` | the Topology A decision of 2026-07-18 | that nothing has been built toward it in 130 commits |
| GitHub issues | seven items, two of them real defects | anything about the milestones |
| the session task list | what an agent is doing right now | anything that outlives the session |

They do not contradict each other about facts. **They contradict each other about
order**, because none of them states one — so work gets chosen by whichever list
happens to be open, and the lists grow faster than they shrink.

This document adds the one thing missing: **an order, its reason, and a stop-line.**
It does not restate the facts. Each item below points at the document that holds
its evidence, and that document stays the place to correct it.

---

## What eleven days changed

`BACKLOG.md` was measured on 2026-07-29. It is now 2026-08-09 and about forty
commits later. A plan built on the older measurement plans the wrong work, so
every load-bearing number below was taken again today.

| | the backlog said | measured 2026-08-09 |
|---|---|---|
| **OP-1** engine ran unmerged code | *"open — one action away from closed"* | **closed.** `_host_lanes` is on `origin/main` in `scrapex/jobs.py`. The PR was opened and merged. |
| **OP-2** three answers to "which sources are active" | an uncommitted manifest edit switching five sources off | **the edit is gone**, exactly as OP-2 predicted it would be. `sources.yaml` in the working tree is byte-identical to `main`: six active, six not. Two answers remain, not three — and the warehouse is still the one that disagrees. |
| **OP-4** `webui/app.py` is 2,480 lines / 89 routes | *"open, worsening"* | **worse: 2,955 lines, 95 routes.** It grew another 475 lines in eleven days. Two modules were extracted (`catalog_api.py` 122 lines, `database_api.py` 82) and did not slow it down. |
| **OP-12** no linter, formatter or type checker | open | **unchanged.** No `ruff`, no `mypy`, no `eslint` anywhere. |
| **DEC-7** branch cleanup — *"12 local branches"* | three stale branches, then twelve | **116 local branches, 106 remote, 21 worktrees.** |

One caution about that last row, because it is the sort of number that invites a
wrong conclusion: `git branch --merged origin/main` reports 11, but **this
repository squash-merges**, so a squash-merged branch reads as unmerged forever.
The count of branches holding real unmerged work is **unknown**, and the only
check that can answer it is a diff against `main` — not a merge-base test and not
a title match.

---

## The rule that orders everything below

> **Close before you open. Publish before you polish. Guard before you grow.**

Three clauses, in that order of precedence:

1. **Close before you open.** Work that is finished but unmerged is the most
   expensive kind there is — it has been paid for and delivers nothing, it rots
   against `main` daily, and OP-1 is the proof that it can reach the owner's
   machine as half-written code. Nothing new starts while something finished is
   waiting.
2. **Publish before you polish.** ScrapeX has one user. Every quality improvement
   below is an improvement to a product nobody can install. M4 is the only item
   on any list that changes that, and it is six clicks in Google's console plus a
   tag.
3. **Guard before you grow.** The repository has no linter, no type checker, and
   no end-to-end test. Every phase after this one writes more code into that. The
   guards are cheap and they compound; the faults they would have caught are
   not and do not.

---

## The next ten, in order

Everything below this section explains *why*. This is the list to work from.

| # | | done when | task |
|---|---|---|---|
| **1** | Commit and merge today's branch — the suite is already green | the working tree is clean | #29 |
| **2** | Merge PR #140 — the zip-inside-a-zip | the store will accept the shape of the artifact | #30 |
| **3** | Rebase PR #43 onto `main`, run the suite on the merged result, merge or close it | it is no longer open from July | #30 |
| **4** | Write today's five re-measurements into `BACKLOG.md` | OP-1 no longer says "open" when it is closed | #31 |
| **5** | Diff every branch against `main`; remove the temp worktrees; hand the owner the list of what actually holds work | there is one page instead of 116 branches | #32 |
| **6** | **M4** — upload the package without `key`, the policy URL, the test users, the three scopes, the four `CWS_*` secrets, tag `scrapex-v0.2.1` | someone who is not the owner installs it and runs the engine once | #19 |
| **7** | `ruff` + `eslint`, one config each, both in CI | a new violation fails a PR | #33 |
| **8** | One end-to-end test through the real CLI, and one chaos test that kills the engine mid-job | both bite when re-broken | #35 |
| **9** | Settle which sources are active — the manifest says six, the warehouse says twelve | they agree, and a test fails when they stop agreeing | #37 |
| **10** | **M6** — the walker, a `PageSource` for muqawil, one live `listing_only` run | the owner opens a contractor and sees when its grade changed | #21 |

**Deliberately not in the ten, and why:** issues #100 and #71 are real defects but they
are wrong data in one source, and they wait behind a product anyone can install ·
`mypy` waits for `ruff` to land first, because a type checker on top of an unlinted
tree produces a wall nobody reads · `webui/app.py` (#36) is a decision before it is
work, and the decision is the owner's · M7 is blocked on one question nobody has
asked the add-in yet · M8 starts with an experiment, not a milestone.

---

## Phase 0 — close what is already open

*Nothing here is new work. All of it is finished work that is not yet anywhere.*

**0.1 · Today's branch.** `feat/the-download-button-downloads` holds nine modified
files and **not one commit**: the download button, the per-engine refresh, the
rewritten onboarding page, the collapsible install steps, and the fix for the
black console window — which is the most consequential thing written this week,
because it is the entire first-run experience of the engine. **The full suite is
green on this branch** (run 2026-08-09: `PYTEST EXIT=0`, one xfail — DEBT-1, which
is meant to stay visible — and two skips). Commit, PR, merge.
**Done when:** the branch is on `main` and the working tree is clean.

**0.2 · PR #140** — *"The artifact is a zip inside a zip, and now it says so."*
Open, `MERGEABLE`, all four checks green. It is waiting on nothing.
**Done when:** merged.

**0.3 · PR #43** — *"the pictures both SSR shops publish in markup but not in
JSON-LD."* Open since July, mergeability `UNKNOWN`, and its branch head is a merge
of `main` from an unknown date. Rebase it onto current `main`, run the suite on
the **merged result**, and then either merge it or close it with the reason. It
must not stay in this state a third month.
**Done when:** merged, or closed with a written reason.

**0.4 · Correct the backlog.** Write the five re-measurements above into
`BACKLOG.md` so the next agent that reads it is not sent to fix OP-1, which is
closed.
**Done when:** `BACKLOG.md` §2 matches what the code says today.

**0.5 · The branches.** 116 local, 106 remote, 21 worktrees — and no way to know
which hold work, because squash merges destroy the usual signal. Do it in this
order and no other:

1. For each local branch, `git diff origin/main...branch` — **empty diff means
   superseded**, and that is the only trustworthy test.
2. List the non-empty ones with their subject and age. That list is short enough
   for the owner to read.
3. `git worktree remove` for every worktree under `AppData/Local/Temp` and
   `C:/tmp` whose branch is superseded. **Worktree removal comes before branch
   deletion, always.**
4. Delete only what the owner names. *(Standing rule: never delete a branch or a
   worktree unasked. Q-12 is the owner asking to be asked.)*

**Done when:** the owner has a one-page list of what actually holds work, and the
temp worktrees are gone.

---

## Phase 1 — M4: publish

*The whole of the remaining work is in Google's consoles. None of it is code.*

The engine is released, the manifest is written, the store text is written and
checked against the manifest, the privacy policy is written and tested. What is
left:

1. Upload a package carrying today's manifest — **without the `key` field.** The
   store rejected the artifact twice already, once for the zip-inside-a-zip and
   once for `key`; #140 fixes the first and this is the second.
2. Privacy-policy URL in **Google Auth Platform → Branding**.
3. Test users in the new project `scrapex-505008`.
4. The three scopes in **Data access** — `userinfo.email`, `userinfo.profile`,
   `drive.file`. All three are non-sensitive; that is deliberate and it is what
   keeps the review short (see PLATFORM-PLAN §M7: `spreadsheets` is sensitive and
   belongs only to the owner build).
5. Four `CWS_*` secrets in the repository.
6. Tag `scrapex-v0.2.1`.

**Done when:** a person who is not the owner installs from a link, sees the panel,
presses Download, runs the engine once, and the panel says the engine is there.

**And one thing this phase must not do:** ship an engine whose first run shows a
black rectangle. That fix is 0.1, which is why 0.1 comes first.

---

## Phase 2 — the guards

*Cheap, boring, and every phase after this one is safer for it. This is the
highest-leverage block on the entire list and it is the one that has been on it
longest.*

**2.1 · `ruff` (OP-12).** Lint and format, one config, one CI job, and a first run
that fixes only what is mechanical. Not `mypy` yet — a type checker over 2,955
lines of untyped FastAPI produces a wall of findings nobody reads, and the value
is in the gate, not the backlog it generates.
**Done when:** `ruff check` is green in CI and a new violation fails a PR.

**2.2 · `eslint` for `extension/`.** The panel is the control room and it has no
static check at all.
**Done when:** the extension gate runs it.

**2.3 · `mypy`, narrow.** Not the repository — three files: `scrapex/ingest.py`,
`scrapex/normalize.py`, `scrapex/rowspec.py`. They are where a wrong type becomes
a wrong price. `--strict` on those, nothing elsewhere, and a plan to widen.
**Done when:** those three are strict-clean and the CI job fails on a fourth
file's import errors, not on its style.

**2.4 · One end-to-end test, and one chaos test (OP-13).** Named in the project's
own matrix (ENGINEERING T7) and never implemented — and this is the exact class
of fault that produced OP-1. Two tests, not a suite:
- **end-to-end:** a source is added, crawled, ingested, exported, and the exported
  row equals the fixture — through the real CLI, not through function calls.
- **chaos:** kill the engine mid-job, restart it, and assert the job resumes or
  fails loudly. Never silently.

**Done when:** both are in CI and both bite when re-broken.

**2.5 · Decide `webui/app.py` (OP-4).** It has grown every time it has been
measured. Two honest options, and *"keep extracting when there is time"* is not
one of them, because that is what has been happening:
- **(a)** Finish the extraction: every route group into its own module, `app.py`
  becomes assembly only. Large, mechanical, and testable one module at a time.
- **(b)** Declare the size acceptable, **delete the half-done router-factory
  pattern**, and stop implying a plan that is not being followed.

*Recommended: (a), one module per session, starting with the largest route group.*
The reason is not tidiness — it is that a test currently has to scrape this file
with a regex to learn its own routes, and that test is load-bearing.

---

## Phase 3 — the facts that are wrong

*The warehouse is the product. Every item here is a place where it says something
untrue, and each is small on its own.*

**3.1 · Which sources are active (OP-2 / Q-11).** The manifest says six; the
warehouse says twelve. One of the two is lying, and until the owner names the
intended set (Q-11) nobody can say which. Then settle what `source_site.active`
is *for* — today it is a column nobody reads and nobody re-syncs.
**Done when:** the manifest and the warehouse give the same answer, and a test
fails when they stop doing so.

**3.2 · Issue #100 — the stock count is stored twice and freezes at zero.** Traced
precisely, **not fixed**, and confirmed still open. A detail copy that freezes at
the last positive value when stock hits zero is a warehouse stating a falsehood.
**3.3 · Issue #71 — sikaegshop's gallery rank is dropped at capture.** The payload
states `is_primary` and `sort_order` and nothing reads either. Also confirmed
still open.
*Both were verified as unfixed and must not be closed until a test proves
otherwise.*

**3.4 · The five currencies (OP-3).** `PEN`, `SLL`, `SYP`, `VEF`, `ZWD` have no
rate, and the stored message blames the page shape — but four of the five have
been redenominated or withdrawn, which is a different fault with a different fix.
**One manual page open settles it.** Do that before writing any code.

**3.5 · The names (OP-9, OP-10, OP-11).** In consequence order: OP-11 first (2,385
attribute rows with no language mark, and the count *doubled* since it was
deferred — so find the connector path that emits them **before** back-filling, or
the next crawl undoes the work); then OP-10 (nine MASDAR products with no English
name — establish whether the site publishes one, because if it does not, this is
data and not a defect); then OP-9 (154 rows, which a re-crawl moves).

**3.6 · `reports.py` computes the six history statistics twice (OP-5).** The
owner's own comment in the code records that adding one column shifted
`observations` / `min` / `max` / `previous` by one. One expression source, read by
both call sites.

**3.7 · Refute what was never refuted (OP-6).** Three claims — ت1, ت2, ت8 —
survive from a review whose refutation stage died on a session limit, and at the
observed rate **two or three of the eight should have been wrong**. They are
costing attention as if they were facts. Refute them the review's own way: run
the code, do not read it.

---

## Phase 4 — M6: the first entity domain

One vertical slice on `muqawil.org`. The scope machinery is built and merged
(`crawlscope.py`, migration 0003), the page seam is designed and its first step is
merged (`pagesource.py`). Three steps remain:

1. **The walker** — what turns "there is a next page" into pages, honouring the
   scope and the delay.
2. **A `PageSource` for muqawil** — server-rendered, `?page=`, no browser needed,
   which is why this site was chosen.
3. **One live `listing_only` run** — 860 pages, about fourteen minutes at the
   shipped pace. Not the 34-hour full crawl; that is a user's choice to make, per
   source, and the whole reason scope is a column.

Then the milestone's actual goal: a contractor discovered, stored and tracked —
appeared, confirmed, disappeared, returned — with **field-level change** as an
event that has a before, an after, and a date, rendered in the same table the
prices use.

**Done when:** the owner opens a contractor and sees when its grade changed.

---

## Phase 5 — M7: the Console

Owner-only, excluded from the shipped build by build configuration — which is a
**security** boundary and not only a commercial one, because it is the only thing
that needs the sensitive `spreadsheets` scope.

**Blocked on Q-3 (PLATFORM-PLAN §9):** what the Excel add-in expects the sheet to
look like — tab names, header row, a view or the whole dataset. Nothing here can
start before that answer, and it is one question to one person.

M7a is the smallest real thing: one dataset becomes one button in Excel, with the
owner typing nothing into a sheet.

---

## Phase 6 — M8: the browser tier

Start with the cheap experiment, not the tool: `BrowserFetcher` already exists in
`connectors/base.py` and **no source uses it**. Point it at `developmentaid.org`.
If it reads the tenders, this entire milestone collapses to a fetcher setting on
a source.

Only what is left after that justifies an external tool, and the deliverable there
is the **contract** — install, health, version, and an importer for the tool's own
output files — proved on `cat.com`, which refuses the connection outright and is
therefore the only measured evidence for needing one.

---

## Not doing — and the reason, so it stops being re-proposed

**DEC-1 / Q-6 · The TypeScript engine (Topology A).** Chosen 2026-07-18. **Zero
commits since**, while the Python product became the whole thing. The spike
directory it names (`spikes/fingerprint-parity/`) has never existed in this
repository. `docs/MASTER-PLAN.md` still reads as the live plan and its own §8 asks
the owner to confirm Topology B — a question its own header answers with A.

*Recommendation: defer A explicitly, mark `MASTER-PLAN.md` as history in the same
session, and stop measuring this project against a roadmap it is not on.* It is
the largest single item on any list, and carrying it unstated makes every estimate
below it wrong.

**Everything in `BACKLOG.md` §5 (DEBT-1 … DEBT-8).** Deferred on purpose, each
with its reason written down. They are not oversights and should not be re-raised
without new evidence.

---

## The questions only the owner can answer

Grouped, because several are one decision wearing five hats.

| | question | why it blocks | recommendation |
|---|---|---|---|
| **Q-6** | Is the TypeScript engine still the plan? | everything queues behind it if yes | **defer explicitly** |
| **Q-11** | Which sources should actually be running? | Phase 3.1 | — |
| **Q-1 … Q-5** | Heidelberg: the price matrix, `maxPrice`, segments, VAT, and whether a 9-product source earns a bespoke connector | one connector, one possible contract change | **answer Q-5 first** — if no, the other four vanish |
| **Q-7** | `open` vs `product_url` → `product_link`; `dataset_field` is UNIQUE and one must lose | the last of the vocabulary sweep | — |
| **Q-8** | `/api/native-host/register` has no authentication and *replaces* the allowlist | it writes a registry key, and it is the route that repairs a broken extension link | **make it merge instead of replace** — that removes the eviction without closing the repair path |
| **Q-9** | Exchange-rate cadence: ~372 Google Finance requests a day | — | **fetch only the currencies active sources price in** |
| **Q-10** | GPP pairs with a USD figure and no local price: blank, hidden, or "the site publishes no local price"? | — | **say it plainly on screen** |
| **Q-12** | Delete the stale branches? | Phase 0.5 | ask again with the diff-verified list, not before |

---

## How to tell this plan is working

Not by items closed — by these four, measured monthly:

1. **Uncommitted work in the working tree:** should be zero at the end of every
   session. It is nine files today.
2. **Branches whose diff against `main` is non-empty:** should fall. Unknown
   today, which is itself the finding.
3. **`webui/app.py` line count:** 2,480 → **2,955**. It has only ever gone up.
4. **Days between a fault being measured and being fixed:** OP-11 doubled while
   deferred. That number is the one that says whether this document changed
   anything.
