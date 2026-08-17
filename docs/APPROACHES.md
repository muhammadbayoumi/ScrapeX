# Approaches — how we write code and solve problems

**No single method is the default.** The owner's instruction, 2026-08-17:

> «واحدة من الطرق التى نكتب بها كود او نحل مشكلة حيث لدى كذا skill ولا اريد
> الاعتماد على واحدة فقط»

This file is the register of the methods available, what each is good for, and —
where two of them disagree — **which one wins here and why**. Pick per task and
say which you are using. A method chosen by habit rather than by fit is the thing
this register exists to prevent.

Governed by **C1** and **C2** in [../CLAUDE.md](../CLAUDE.md): read this before
building, and add to it when a method proves itself or fails.

---

## The register

### A1 · Diagnose → confirm → fix, one step at a time
**The owner's standing rule.** [R-01](RULINGS.md#r-01--diagnose-confirm-then-fix--one-step-at-a-time)

Present the proven root cause with `file:line` evidence and **ask before
editing**. Prefer read-only inspection while diagnosing.

**Reach for it:** always, for anything described as a problem or a bug. This one
is not optional and is not in competition with the others — the rest describe
*how* to build once the cause is agreed.

---

### A2 · Measure, don't reason
**The project's own hardest-won method.** [LESSONS.md §8](LESSONS.md#8--the-method-that-caught-all-of-these)

Run it against reality, repeatedly, and let counts decide. Reading the code found
almost none of this project's real defects.

Its record: two claims in `MIGRATION-PLAN.md` were false and both were caught by
measuring rather than reading; four schema leaks in PR #211 surfaced only across
250 real pages; the append gate's silent NULLs showed up only on a second crawl.

**Reach for it:** before believing any claim about behaviour — including one in
these documents. Especially when a fixture, a single page, or a single ingest is
about to stand in for production.

---

### A3 · The engineering rules
**[ENGINEERING.md](../ENGINEERING.md)** — P1–P5 and the A/Q/T/F/S/W rules.

The standing constitution for code in this repo: DRY-aggressive, tests
non-negotiable, engineered-enough, edge-cases-first, explicit over clever. Each
rule exists so the code passes its review section by construction.

**Reach for it:** every time you write code. It outranks any general-purpose
method below where they conflict — see the resolutions.

---

### A4 · Karpathy guidelines
**Skill:** `.claude/skills/karpathy-guidelines/SKILL.md` ·
**Source:** <https://github.com/multica-ai/andrej-karpathy-skills> · MIT ·
**added 2026-08-17 on the owner's instruction**

Four behavioural rules against common LLM coding failures: think before coding,
simplicity first, surgical changes, goal-driven execution. It biases toward
caution over speed and says so.

**Reach for it:** when the task is an edit inside existing code and the risk is
doing **too much** — scope creep, speculative abstraction, tidying adjacent code
that nobody asked about. Its "surgical changes" test — *every changed line traces
directly to the request* — is the sharpest single check in the register for that
failure.

Invoke it by name: `/karpathy-guidelines`.

---

### A5 · Adversarial review
**Used, and it works.** The engineering rules themselves were verified this way
(traceability critic + project-fit critic, 29 findings incorporated), and the
July audit ran 76 agents — 6 auditors and 70 challengers — against the
specification, producing
[plans/2026-07-20-review-findings.json](plans/2026-07-20-review-findings.json).

**Reach for it:** for a design decision that is expensive to reverse, or a claim
that everything is covered. A critic tasked with *refuting* finds what a reviewer
asked to *check* does not.

---

### A6 · Break the test first
Every one of the ten Console DOM tests was made to fail deliberately before being
trusted. A test never seen red is a test whose failure mode is unknown.

**Reach for it:** whenever you add a guard for something silent — the decoded
email, the plausible coordinate, the append-gate column. Those are exactly the
tests that pass forever while the feature is broken.

---

### A7 · Mutation testing
Used on the sign-out work, and it earned its keep: it found that one surviving
mutant was genuinely **equivalent** rather than a gap, which was recorded instead
of papered over.

**Reach for it:** on a small, high-consequence surface where "the tests pass" is
not enough — auth, revocation, the append gate, a version gate.

---

### A8 · The built-in review skills
`/code-review` (correctness bugs and cleanups, effort-scaled), `/simplify`
(quality only — reuse, simplification, altitude), `/security-review`.

**Reach for it:** `/code-review` before opening a PR; `/simplify` after a feature
lands and before it calcifies.

---

## Where they disagree, and which wins

A register is only useful if it says what to do when two entries point opposite
ways. Four real conflicts, resolved:

### 1 · "No error handling for impossible scenarios" (A4 §2) vs **Q3 no silent failures, T3 error-path parity** (A3)

**A3 wins on the data path.** In ScrapeX the error branches are not impossible
scenarios — a site changes shape, a funnel POST fails, a page returns 304 with no
body. Q3 ("no bare `except`; every caught error becomes a structured record") and
T3 (every happy path pairs with a failure mode) are load-bearing, and the
counter-examples are in the history: the add-in's BulkInsert-swallowing bug, and
a 3,570-page ingest killed by one stale page.

A4's rule still applies to genuinely unreachable branches — defensive code for a
state the type system already forbids.

### 2 · "Minimum code" (A4 §2) vs **P2 tests non-negotiable, too many > too few** (A3)

**Minimum *product* code, not minimum *test* code.** Every failure recorded in
[LESSONS.md](LESSONS.md) came from under-testing — a single-page fixture, a
single ingest, a harness that stubbed too little. Not one came from too many
tests. A4's simplicity rule governs the implementation; P2 governs the suite.

### 3 · "Don't refactor what isn't broken" / "match existing style" (A4 §3) vs **P1 DRY-aggressive** (A3)

**Scope decides.** A4's surgical rule governs *adjacent* code you happen to be
standing next to — do not tidy it, do not restyle it, mention dead code rather
than deleting it. P1 governs *the thing you are building*.

The live example is B2 step 2: the panel already has Choose-Columns
(`extension/app.js:1579`, `:1618`), and the instruction is to **extract it into a
shared module**, not to write a second one. Writing a duplicate in the name of
staying surgical is precisely the failure the migration plan warns about — "or
the two surfaces will disagree about how a column is saved."

### 4 · "Ask when uncertain" (A4 §1) — no conflict, reinforcement

A4 §1 and A4 §4 (state assumptions, present interpretations rather than picking
silently, define verifiable success criteria) agree with
[R-01](RULINGS.md#r-01--diagnose-confirm-then-fix--one-step-at-a-time),
[R-02](RULINGS.md#r-02--an-un-computable-mapping-is-the-owners-call-and-studies-come-first)
and **W3** in ENGINEERING.md. Where a general-purpose guideline and this
project's own rule point the same way, that is the strongest signal in the
register — treat it as binding, not advisory.

---

## Adding a method

1. Vendor or reference it, with its licence and its source.
2. Add an entry here: what it is good for, and **when to reach for it**.
3. Read it against [ENGINEERING.md](../ENGINEERING.md) and
   [RULINGS.md](RULINGS.md), and record any conflict in the section above with a
   resolution. An imported method that has not been checked against the
   project's own rules is a second, contradictory constitution.
