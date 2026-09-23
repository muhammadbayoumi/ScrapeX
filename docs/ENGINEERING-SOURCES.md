<!--
  THE AUTHORITY LIST FOR ENGINEERING AND ARCHITECTURE DECISIONS, and the twin of
  docs/DESIGN-SYSTEM-SOURCES.md, which does the same job for the interface. It is a
  REFERENCE, not a register: it records what a decision RESTS ON, never what work is
  outstanding. Outstanding work is `gh issue list` — see CLAUDE.md.

  ITS COMPANION is CLAUDE.md, which states the rules this product is built by. That file
  says WHAT we do. This one says WHAT THAT RESTS ON, so a rule can be re-argued against
  its source instead of defended by seniority. When they disagree, this file is the
  outside authority and CLAUDE.md is the thing under review — the same relationship
  DESIGN-SYSTEM-SOURCES.md has with DESIGN-SYSTEM.md.

  HOW IT IS MAINTAINED. Add an entry when a decision is taken that an outside source
  governs. Mark one SUPERSEDED when the source changes or a better one is found — never
  delete it, because code cites the number. Every edit says WHAT CHANGED AND WHY in its
  commit message, never in a note here.

  WHY THE NUMBERS ARE PERMANENT. `tests/test_the_code_cites_its_sources.py` reads the
  citations in the code and the entries here and fails when either end breaks. That guard
  exists because the same failure already shipped once on the design side: fifty-three
  comments cited `R-84` for a rule that `R-85` makes, and every other guard in the suite
  was blind to it (`tests/test_the_design_system_cites_its_own_rulings.py`).
-->

# The sources a decision rests on

A rule in `CLAUDE.md` is enforced because it is written there. This file is the separate
question: **what is it right?** — so that changing a rule means arguing with its source
rather than with the session that wrote it.

**This is not a reading list.** An entry earns its place by being cited at a line of code
that would be built differently without it. An entry with no citation is removed, and the
guard fails on one, because a register padded to look complete is a register nobody
trusts — the same argument `docs/UI-KIT.md` makes about its own catalogue.

## How to use it

**Taking a decision an outside source governs:** add an entry below, then cite its number
in a comment at the line that implements it:

```python
# ES-1: a pipeline stage is not a user step. See docs/ENGINEERING-SOURCES.md.
```

**Reading a decision:** the number in the comment is a lookup key. It says the decision
was argued rather than assumed, and it says against what.

**Changing a decision:** find every citation of its number — the guard's own table lists
them — and change them together. If the SOURCE changed rather than our reading of it,
mark the entry superseded and say which entry replaces it. The number stays.

## Source-conflict resolution order

When sources disagree, in this order:

1. **A standard with normative force** — a W3C Recommendation, an RFC, an ISO/IEC/IEEE
   standard, a language or platform specification. These are not opinions and nothing
   below outranks them.
2. **The platform's own documentation** for the platform actually being used — Chrome
   extension APIs, SQLite, Python's standard library.
3. **This product's measured behaviour on his machine.** A number from his warehouse
   outranks a general recommendation about what usually happens. `CLAUDE.md`: *"A real
   `file:line` beats a plausible reading."*
4. **A mature published practice with a named author and a stated rationale** — the
   entries below.
5. **A widely used tool's documented design**, read as evidence of what works at scale,
   not as instruction.
6. **Anything else**, which is to say: not a source. An article without a rationale, a
   blog post restating one of the above, or a practice named without a reference does not
   settle an argument here.

A tie between two sources at the same level is not resolved by preference. Record both,
say what each would have us do, and it becomes a decision for the owner — the same rule
`CLAUDE.md` states for his priorities on timeline, scale and spend.

**For the interface, this file does not apply.** `docs/DESIGN-SYSTEM-SOURCES.md` governs
there, Supabase is its base, and its own precedence order is the one to use.

---

## ES-1 · A pipeline stage is not a user step

**Governs:** whether a job that another job's output makes due is started by the engine or
waited for by the owner.

**Cited at:** `scrapex/datasetjob.py`, `scrapex/directoryjob.py`.

### What was measured

A price source is one pass: `scrapex/capture.py`'s `capture_source` *"fetch a source via
its connector and ingest straight into"* the warehouse — crawl, then browse the table.

A directory source is two. The listing crawl stores pages; `dataset_interpret` turns them
into rows. Between them the owner had to press a button, and on 2026-09-23 he named the
cost: *«المستخدم العادى عمل crawl مش هيفهم يعنى اى تفسير اصلا ولية يطر يعمل خطوة زيادة»*.

Measured on his own warehouse, the step he was asked to take:

```
job_7223cf1aa257   471 page pairs   12:52:11 → 12:52:52 = 41 s   0 network requests
job_ff83c29729a8    75 page pairs                       = 20 s   0 network requests
```

And the engine already computes that it is due: `scrapex/webui/app.py`'s `_work_waiting`
holds *"`interpret` is due when a listing crawl has finished MORE RECENTLY than the last
interpretation of this source"*. It draws a line on the card and waits.

### The sources

| source | what it contributes |
|---|---|
| [GOV.UK Service Manual — *Design around user needs, not government structures*](https://www.gov.uk/service-manual/design) | A service is what the person is trying to do. "Crawl, then interpret" is two of our stages, not one of his tasks. The same manual's *"do the hard work to make it simple"* is the cost side: the complexity does not vanish, it moves to us. |
| [Dagster — Software-Defined Assets](https://docs.dagster.io/guides/build/assets) | Declare the **asset** and what it depends on; the system works out what must run. `_work_waiting` already computes exactly that condition and then declines to act on it. |
| [Apache Airflow — DAG dependencies](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html) | A downstream task runs when its upstream succeeds. Sequencing is declared once, not remembered by an operator each time. |
| Hohpe & Woolf, *Enterprise Integration Patterns* — **Process Manager** | A multi-step process holds its own state, and a step's failure is handled inside the process rather than reported to whoever started it. This is what preserves the next paragraph. |

### What it does NOT overturn

`scrapex/datasetjob.py`'s own argument for two jobs stands, and the entry is written to
keep it:

> *interpretation fails on its own terms — a parser that cannot read a page, a schema that
> moved — and a failure reported as the crawl's would send the next session looking at the
> network. It is also a thing worth doing WITHOUT a crawl … Two jobs, two verdicts.*

Every word of that is about **jobs**, and none of it is about **buttons**. A chained job
still reports its own verdict, still runs without a crawl when asked, and still takes no
politeness reservation. What changes is who starts it.

### The decision taken

The owner ruled on 2026-09-23, choosing from three options with their costs:
**the engine starts the dependent job itself, and the panel shows it running with a
control to stop it.** Not silently (he would not see a 41-second write-lock holder), and
not manually (the stage is ours, not his).

`CLAUDE.md`'s *"never start a run you cannot watch to the end"* is satisfied by the second
half: the run is visible and stoppable from the surface it appears on, which is what that
rule protects.

### How to re-open this

If a chained interpret is ever measured holding the write lock long enough to block a
crawl he started, entry 3 of the precedence order applies — a number from his machine
outranks the practice above — and this entry is superseded rather than argued with.
