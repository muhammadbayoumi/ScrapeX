# ScrapeX — start here

**Read this file before writing a line of code. Every session, every machine.**

ScrapeX is contract-driven web data collection into a SQLite price-tracking
warehouse, publishing curated data to the Google Sheet the mbiX Excel add-in
reads. The add-in is never touched; the two systems meet only at the sheets.
See [README.md](README.md) for setup and the data flow.

---

## Why this file exists

The owner works from **two machines and two different user accounts** — mornings
at work, nights at home. Anything recorded outside this repository exists on
exactly one of them.

This was not a theory. On 2026-08-17 he opened the second machine and could not
continue the work, because everything that said *where the work stood* lived
under one machine's home directory: thirteen memory files, seven plans — one of
them the plan for the pull request that was open at that moment, holding three
rulings he had given and nothing else recorded them. The repository itself held
good documents and **nothing pointed at them**.

So: **the repository is the only memory.** A note that is not committed did not
happen.

---

## The contract

These seven rules govern how this documentation system is used and changed. They
were set by the owner on 2026-08-17 and they bind every session.

**C1 — Consult before building.** No change to the code happens without reading
this system first. Start with [docs/STATE.md](docs/STATE.md) for where the work
stands and [docs/RULINGS.md](docs/RULINGS.md) for what has already been decided.
Building something the owner already ruled against is a defect, and the ruling
being hard to find is not an excuse — it is in one place now.

**C2 — It evolves.** This system is expected to grow and be corrected. A session
that learns something durable writes it down before it ends. A document that has
gone stale is a bug in the system, and fixing it is part of the work, not a
separate chore.

**C3 — Every owner decision is written down.** Not summarised in a commit
message, not left in a conversation: recorded in
[docs/RULINGS.md](docs/RULINGS.md) with its date, the reason given, and the
evidence that produced it.

**C4 — A changed mind is recorded, never erased.** The owner's view is dynamic
and is expected to change as evidence arrives. When a ruling is replaced, the old
one **stays** in place, marked superseded, pointing to the one that replaced it
and saying what changed. The history of a decision is part of the decision — a
reversal that hides its predecessor teaches nobody why the new rule exists.

**C5 — Disagreement is recorded too.** If the evidence contradicts a ruling, say
so and record it. An unwritten objection helps no one on the other machine.

**C6 — No single method is the default.** Several ways of writing code and
solving problems are available here, and the owner's instruction is not to lean
on one: *«لدى كذا skill ولا اريد الاعتماد على واحدة فقط»*. They are registered in
[docs/APPROACHES.md](docs/APPROACHES.md), with the conflicts between them
resolved. Choose per task and say which you chose.

**C7 — Every request he makes is captured the moment he makes it.** Anything he
asks for, adds, or mentions as future work goes into
[docs/REQUESTS.md](docs/REQUESTS.md) as `REQ-nn` **in the session he said it**,
quoted in his own words — then it moves Captured → Ruled → Planned → In flight →
Done, and a plan is written when it is picked up. Done and dropped requests are
kept, never deleted. *«علشان مننساش، ولما نوصله نعمله خطه ونفذها»* — REQ-04 was
ruled on 2026-08-01, was never built, and had dropped out of sight entirely,
which is why this rule exists.

**Registers must not drift into each other.** Three exist, and the test is where
the thing came from: **he asked** → `REQUESTS.md`; **we found it** →
`BACKLOG.md`; **a decision was taken** → `RULINGS.md`. The boundary table is in
[docs/REQUESTS.md](docs/REQUESTS.md#the-boundary--which-file-does-a-thing-belong-in).

---

## The map

| document | what it holds | when to read it |
|---|---|---|
| **CLAUDE.md** (this file) | the entry point, the contract, how the owner works | first, always |
| [docs/STATE.md](docs/STATE.md) | **where the work stands right now** — open PRs, tracks in flight, resume points, live blockers | at the start of every session |
| [docs/REQUESTS.md](docs/REQUESTS.md) | **everything the owner has asked for**, and which of the five states each request is in | when he asks for something, and before starting new work |
| [docs/RULINGS.md](docs/RULINGS.md) | every decision the owner has made, dated, with superseded ones kept | before designing anything |
| [docs/BACKLOG.md](docs/BACKLOG.md) | what *we* found — open problems, declared debt, decided-not-built, questions for him | when hunting for what needs doing |
| [docs/LESSONS.md](docs/LESSONS.md) | hard-won engineering knowledge — the traps that cost real time, the failures that are silent | before touching ingest, the warehouse, the design system, or the version ledger |
| [docs/APPROACHES.md](docs/APPROACHES.md) | **the methods available** for writing code and solving problems, and which wins where two disagree | when choosing how to attack a task |
| [ENGINEERING.md](ENGINEERING.md) | the code rules — architecture, quality, testing, performance | before writing code |
| [docs/plans/](docs/plans/README.md) | the plans, current and historical | when picking up a track |

Other long-standing documents — `docs/MIGRATION-PLAN.md`,
`docs/COMPATIBILITY.md`, `docs/PLATFORM-PLAN.md`, `docs/GENERIC-FETCH-SEAM.md`,
`docs/CONTRACTOR-SOURCE.md`, `docs/STORAGE.md` — are indexed from `docs/STATE.md`
under the track they belong to.

---

## How the owner works

- **He reasons about his own system.** He is the author and he wants evidence,
  not a recommendation on its own. Offer options with the *measured* consequence
  of each.
- **Diagnose, confirm, then fix — one step at a time.** Stated directly:
  «عندى مشاكل عاوز اشرحها وبعد فهمها نحاول نحلها خطوة خطوة». Present the proven
  root cause with `file:line` evidence and **ask before editing**. A fix landed
  before the cause is agreed destroys the evidence he needs to judge it.
- **He asks in Arabic and expects the answer in Arabic.** Code, comments,
  commits, PR prose and every file in this system stay **English** — repo
  convention, and his instruction of 2026-08-17.
- **An un-computable mapping is his call, not a developer's** — and he may
  refuse to rule until studies are measured. See R-02 in
  [docs/RULINGS.md](docs/RULINGS.md).
- **Answer a study with counts from live data.** "72 of 90 rows would have an
  empty price" moves a decision; "this seems wrong" does not.
- Meanwhile, build everything that does *not* depend on the open ruling, and
  leave the undecided fact visible rather than absorbed by a default.

---

## Two traps that will cost you an afternoon

Both make correct work look broken. Both are covered in full in
[docs/LESSONS.md](docs/LESSONS.md); they are repeated here because they bite in
the first five minutes.

**1. There are several live checkouts, and both imports *and* edits default to
the main one.** `C:\Users\User01\source\repos\ScrapeX` is the main checkout;
`...\ScrapeX\.claude\worktrees\<name>` are full checkouts too. `scrapex` is
pip-installed editable against **main**, and an absolute path typed from memory
is a **main** path. Edits land there, the worktree's tests stay red, and
`git status` in the worktree shows nothing. Derive every path from the worktree
root in the session preamble. In any scratchpad script, assert on a **symbol you
just added**, not only on `__file__` — `__file__` catches a misdirected import,
never a misdirected edit.

**2. Never hash a repo file's raw bytes.** `.gitattributes` sets `* text=auto`
and `core.autocrlf` is true, so the repo stores LF and Windows checks out CRLF.
Normalise (`b"\r\n"` → `b"\n"`) before hashing anything tracked. This shipped as
a real outage once already.

---

## Keeping this system true

When a phase lands, a PR merges, or the owner rules:

1. **[docs/STATE.md](docs/STATE.md)** — update it. It is the one document that is
   wrong the moment it is out of date.
2. **[docs/RULINGS.md](docs/RULINGS.md)** — add the ruling, or mark the old one
   superseded per **C4**.
3. **[docs/LESSONS.md](docs/LESSONS.md)** — add the lesson if something silent
   was caught, or a measurement overturned a belief.
4. Commit it **in the same pull request as the work it describes.** A
   documentation update deferred to "later" is the failure this system exists to
   prevent.

**A `file:line` citation in any of these documents is tested.**
`tests/test_the_documents_cite_what_they_claim.py` checks that every one names a
real file and a real line, and that the citations listed in its `PINNED` table
still sit beside the symbol they were written for ([R-15](docs/RULINGS.md#r-15--the-documents-are-guarded-by-a-test-not-by-good-intentions)).
Writing a citation that matters means adding a row there. Three citations had
already drifted when the guard was built.
