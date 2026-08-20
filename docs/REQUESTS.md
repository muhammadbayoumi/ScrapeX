# Requests — what the owner asked for, and where each one is

Every request the owner makes is captured here the moment he makes it, and it
stays until it is built or explicitly dropped. Nothing is remembered in a
conversation.

> «عاوز ادارة لطلباتى بحيث توثق وتحفظ ومنها نعمل خطة ومنها ننفذ الخطة»
> — 2026-08-17, the instruction that created this file
> ([REQ-03](#req-03--a-managed-pipeline-for-the-owners-requests)).

**It is not a checklist.** A checklist is ticked and thrown away. A request here
carries an ID, a state, the words he used, and a link to the ruling, the plan and
the pull request it became. That chain is the point.

---

## The pipeline

Every request moves through these states, in order. It may stop at any of them,
and it may **skip** one -- but only forward, and only for a reason the entry
states. The common skip is `Planned`: when a request is small enough that the
ruling *is* the plan, it goes `Ruled` straight to `In flight`. R-15 and R-16 did
exactly that. What is forbidden is moving BACKWARD without saying why, and
recording a state the work has not reached.

| state | means | where the work goes |
|---|---|---|
| **Captured** | He asked. Written down. Nothing decided yet | this file only |
| **Ruled** | *How* it should be is decided | a ruling in [RULINGS.md](RULINGS.md) |
| **Planned** | There is a plan someone else could execute | a file in [plans/](plans/README.md) |
| **In flight** | Being built; a PR is open | the PR |
| **Done** | Merged | recorded here with the PR number, and kept |
| **Dropped** | Decided against | **kept**, with the reason — per **C4** |

**Done and Dropped entries are never deleted.** Same discipline as a superseded
ruling: an entry that vanishes teaches nobody why the answer was no, and invites
the same request again in three weeks.

## The boundary — which file does a thing belong in?

Three registers exist and they must not drift into each other. **The test is
where the thing came from:**

| it came from | it belongs in |
|---|---|
| **The owner asked for it** | **this file**, `REQ-nn` |
| **We found it** — a bug, a debt, a duplication | [BACKLOG.md](BACKLOG.md) — `OP-`, `DEBT-`, `DEC-` |
| **A decision was taken** — by him, on either of the above | [RULINGS.md](RULINGS.md) — `R-nn` |
| **A question only he can answer** | [BACKLOG.md](BACKLOG.md) §6 `Q-n`, or RULINGS.md "Open" |

IDs are stable and never reused, matching the convention BACKLOG.md already uses.

---

## The board

| ID | request | state | since |
|---|---|---|---|
| [REQ-01](#req-01--one-documentation-system-in-the-repository) | One documentation system, in the repo, all English | **Done** | 2026-08-17 |
| [REQ-02](#req-02--more-than-one-way-of-working) | More than one way of working — add the Karpathy skill | **Done** | 2026-08-17 |
| [REQ-03](#req-03--a-managed-pipeline-for-the-owners-requests) | A managed pipeline for his requests | **Done** | 2026-08-17 |
| [REQ-04](#req-04--every-setting-moves-into-the-extension) | Every setting moves into the extension | **Ruled** — not built | 2026-08-01 |
| [REQ-05](#req-05--a-contractor-directory-in-a-table-of-its-own) | A contractor directory, in a table of its own | **Done** | 2026-08-16 |
| [REQ-06](#req-06--one-row-and-a-button-that-flips-it-between-arabic-and-english) | One row, and a button that flips AR\|EN | **Done** | 2026-08-17 |
| [REQ-07](#req-07--the-data-page-must-carry-everything-the-engines-page-carries) | The Data page carries everything the engine's page does | **Planned** | 2026-08-12 |
| [REQ-08](#req-08--a-guard-against-the-documents-going-stale) | A guard against the documents going stale | **Done** | 2026-08-17 |
| [REQ-09](#req-09--one-home-for-rulings-not-two) | One home for rulings, not two | **Done** | 2026-08-17 |
| [REQ-10](#req-10--adversarially-review-the-fixes-then-execute) | Adversarially review the fixes, then execute | **Done** | 2026-08-20 |

---

## REQ-01 · One documentation system, in the repository
**Captured 2026-08-17 · Ruled ([R-09](RULINGS.md#r-09--one-documentation-system-in-the-repository-all-english)) · Done — commits `51e44f3`, `47874b1`**

> «اريد نظام موحد للمعلومات حيث اننى اعمل من جهازين مختلفين» · «واجعله كله
> بالانجلليزى» · «وضيف فيه كل الخبرات التى اكتسبتها»

Built: `CLAUDE.md` (entry point + the C1–C6 contract), `docs/STATE.md`,
`docs/RULINGS.md`, `docs/LESSONS.md`, `docs/APPROACHES.md`, `docs/plans/` with
seven rescued plans.

---

## REQ-02 · More than one way of working
**Captured 2026-08-17 · Done — commit `51e44f3`**

> «واحدة من الطرق التى نكتب بها كود او نحل مشكلة حيث لدى كذا skill ولا اريد
> الاعتماد على واحدة فقط»

The `karpathy-guidelines` skill vendored under `.claude/skills/` (MIT, verbatim),
and registered as **A4** among eight methods in
[APPROACHES.md](APPROACHES.md), with the four places it conflicts with this
project's own rules resolved there.

---

## REQ-03 · A managed pipeline for the owner's requests
**Captured 2026-08-17 · Ruled ([R-14](RULINGS.md#r-14--requests-are-captured-when-made-then-planned-then-executed)) · Done — #214**

> «كل طلب او اضافة او اى شى اذكره ونقرر انه فى المستقبل نحطه … علشان مننساش،
> ولما نوصله نعمله خطه ونفذها»

He proposed the name `CHECKLIST` and asked for a recommendation. **Recommended
and adopted: `REQUESTS.md` with `REQ-nn` IDs** — a checklist is ticked and
discarded, carries no state, no evidence and no history, while what he described
is a pipeline of five states. `ROADMAP` was rejected for promising an order he
has not set; `WISHLIST` for understating what these are.

---

## REQ-04 · Every setting moves into the extension
**Captured 2026-08-01 · Ruled ([R-04](RULINGS.md#r-04--all-ten-web-only-settings-move-into-the-extension), and `SR-10` in [BACKLOG.md](BACKLOG.md)) · Ruled — not built, measured 2026-08-20**

**This is the entry that justifies the whole file.** Ruled 2026-08-01,
offered three options, he chose the most thorough — and nothing has been built.
It was parked behind a review and then simply dropped out of view.

The ten: `excel_folder`, `excel_workbook`, `excel_schema`, `excel_structure`,
`excel_update`, `funnel_url`, `funnel_token`, `google_folder`, `google_workbook`,
`backup_folder`.

**The deliverable is the guard, not just the move** — it must read every template
under `scrapex/webui/templates/`, not `settings.html` alone, keeping the named
runtime-repair exemption. The web page keeps *displaying* every value it stops
editing.

**Next state: Planned.** It has a ruling and no plan.

---

## REQ-05 · A contractor directory, in a table of its own
**Captured 2026-08-16 · Ruled ([R-10](RULINGS.md#r-10--the-contractor-directory--three-rulings), [R-11](RULINGS.md#r-11--a-contractor-directory-is-a-separate-table-and-a-table-like-any-other)) · Planned ([plan](plans/2026-08-16-muqawil-contractor-source.md)) · Done — #202–#212**

> «جدول منفصل تماما عن جداول المنتجات» · «صفحة المقاولين هى جدول سيظهر كاى جدول
> لدينا»

Landed across #202–#212, and the full listing pass is in the warehouse:
**11,059 contractors**, 864 of 864 pages approved, zero rejected — verified against
the live database on 2026-08-19, not read out of a conversation.

**Done does not mean finished asking.** Four questions of his are still open —
O-1 to O-4 in [RULINGS.md](RULINGS.md#open--awaiting-the-owners-ruling) — and one
decision is waiting: the two feature flags that make `/datasets` visible are still
`False`. See [STATE.md](STATE.md#track-2--the-muqawilorg-contractor-directory).

---

## REQ-06 · One row, and a button that flips it between Arabic and English
**Captured 2026-08-17 · Ruled ([R-12](RULINGS.md#r-12--one-row-with-a-button-that-flips-it)) · Done — PR #211**

> «فى النهاية اريد رؤوية جدول اقدر ابدل بين عربى وانجليزى»

Built in `34496db`. Merged by contractor id, never by position — the listing
reorders every thirty seconds.

---

## REQ-07 · The Data page must carry everything the engine's page carries
**Captured 2026-08-12 (the migration plan is his) · Planned · Not started**

Four capabilities remain before the workbook link may be removed from the source
card: the details drawer, Choose-Columns, saved views, and promotion. The order
is reasoned and is in [STATE.md](STATE.md#track-1--the-console-migration).

**Blocked in part:** saved views waits on
[O-5](RULINGS.md#open--awaiting-the-owners-ruling) — he has comments on B1 and
will raise them first.

---

## REQ-08 · A guard against the documents going stale
**Captured 2026-08-17 · Ruled 2026-08-19 ([R-15](RULINGS.md#r-15--the-documents-are-guarded-by-a-test-not-by-good-intentions)) · Done**

> «نفذ توصيتك فى REQ-08 و REQ-09»

**Built: `tests/test_the_documents_cite_what_they_claim.py`, option (b).** Two
tiers, because one tier could not be made both sensitive and precise:

- **Tier 1** — every `file:line` in the eight documents of CLAUDE.md's map
  names a file that exists and a line inside it. 42 citations checked, zero
  inference, nothing that can flake.
- **Tier 2** — a `PINNED` list of 19 load-bearing citations whose subject is
  stated in the test and checked exactly, ±3 lines. This is the tier that
  catches the drift that started it; a mutation test put the citation back to
  1355 and confirmed the guard refuses it.

**Why not infer the subject from the prose.** It was built that way first and
measured: at 220 characters of context it reported eleven failures of which
**four were false** — it kept latching onto the name of a different file. Strict
adjacency instead dropped coverage from 42 citations to 3 and stopped catching
the original defect. The repository's own rule settled it, from
`tests/test_the_published_documents_are_checked_not_announced.py`: *"Two cheap
checks that cannot flake beat one true check that does."*

**`docs/plans/` is excluded, and that is a ruling not a gap** — 200 of the
repository's 289 citations live there, and those files are verbatim history. A
test asserts the exclusion stays deliberate.

Proposed after finding that `ENGINEERING.md` W4 had drifted into pointing at an
action the test suite forbids ([LESSONS.md §7](LESSONS.md#7--a-document-can-drift-into-the-opposite-of-the-code)).

The precedent is the project's own: `tests/test_the_ruling_matches_the_code.py`
exists because `docs/data-page-schema.md` drifted in five ways at once, and PR
#63 was sent back for leaving it behind. Its docstring: *"A document nobody can
trust is worse than no document."*

The new documents carry facts that will drift — `VERSION`, commit counts,
`file:line` citations, PR numbers. Options:

**(a)** Generate the volatile facts, as `data-page-schema.md` does — strongest,
and the largest change.
**(b)** A test that checks only the *citations* — that every `file:line` in the
system's documents still points at a file that exists and a line that matches the
quoted symbol. Cheap, catches the dangerous class.
**(c)** Do nothing, and rely on **C2**.

*Recommended: **(b)**.* It is the class that actually hurt — a citation that
silently moved — and it does not require making the prose machine-generated.

**Evidence arrived on 2026-08-19, two days after this was captured.** Re-checking
STATE.md's own citations found three of them wrong: the `webui/app.py` citation
still said line 1355 when the code had moved to 1375 — #211 and #212 inserted
twenty lines above it — and `LATEST_SOURCE`/`UPDATE_INSTRUCTIONS` were quoted at
lines 289 and 292 when they have been at 282 and 285 all along — wrong the day
they were written, in a file no commit had touched. All three are fixed, and all three are exactly what (b)
catches automatically. **Nothing but a hand-check found them, which is the point.**

---

## REQ-09 · One home for rulings, not two
**Captured 2026-08-17 · Ruled 2026-08-19 ([R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file)) · Done**

**Done, option (a):** `SR-1`–`SR-23` moved into
[RULINGS.md](RULINGS.md#standing-rules--the-data-product-and-process-policy-sr-1sr-23),
every number unchanged, the table spliced **verbatim** by script so no word of
his could be paraphrased in the move. `BACKLOG.md` §1 is now a pointer, and that
file keeps `OP-`, `DEC-`, `BV-`, `DEBT-` and `Q-`. Its title no longer claims to
be *"the one tracking document"*, because it has not been one since 2026-08-17.

**Found while building this file, and it is mine to own:** `RULINGS.md` was
written on 2026-08-17 without reading `BACKLOG.md`, which has held **23 standing
rules `SR-1..SR-23`** since 2026-07-29 and calls itself *"the one tracking
document"*. The project now has two registers of the owner's rulings.

The entries barely overlap in content — `SR-*` are data and product policy,
`R-*` are process and the August decisions — but they overlap completely in
**kind**, and that is enough. It is the same defect the migration plan warns
about at B2 step 2: *"do not write a second one."*

Options:

**(a)** Migrate `SR-1..SR-23` into `RULINGS.md`; BACKLOG.md §1 becomes a pointer.
One home, with the C4 supersession discipline applied to all of them. BACKLOG.md
keeps what it is genuinely best at — `OP`, `DEC`, `DEBT`, `Q`.
**(b)** Fold `R-01..R-13` back into BACKLOG.md §1 as `SR-24..SR-36`, delete
`RULINGS.md`. Fewer files; but the rulings then live inside a 1,151-line document
that **C1** tells every session to read before designing anything.
**(c)** Keep both with a documented split by subject. Rejected — a boundary
nobody can state in one sentence is a boundary that will not hold.

*Recommended: **(a)**.* Separation by kind is what makes C1 followable, and
BACKLOG.md is already too large to be read before every design decision. The cost
is one careful migration pass, and every `SR-` ID keeps its number.

---

## REQ-10 · Adversarially review the fixes, then execute
**Captured 2026-08-20 · Ruled ([R-17](RULINGS.md#r-17--a-fix-is-adversarially-reviewed-before-it-is-written)) · Done — this commit**

> «مراجعة عدائية اولا على 3 اصلاحات» — then «نفذ»

Three drifts had been reported on 2026-08-20 and he asked for them to be
**attacked before being written**, not merely checked. The review is why the work
that followed is not the work that was proposed:

- **It refuted one of the three.** `RULINGS.md:106` reads *"(As of 2026-08-17 the
  gap is 58 commits.)"* — dated, therefore history rather than rot. The finding
  was withdrawn.
- **It widened another.** "16 days" had a second copy in `STATE.md`, and a third
  written out in words as "sixteen days ago".
- **It found what the three had missed:** the board is hand-written with no
  generator, so board and entries must drift; `REQ-05` was `Done` while O-1..O-4
  stayed open; and the pipeline's own *"may not skip one"* was obeyed by **no
  entry at all**.

Built: `tests/test_the_request_board_matches_its_entries.py` — seven tests, every
one mutation-tested by breaking it deliberately first. The board's `request`
column is independently worded from the entry heading in five of nine rows, so it
cannot be generated; what is derivable is checked instead, and the prose stays
hand-written. The skip rule now describes what actually happens.

**And the rule that was written, run and withdrawn**, recorded because a
withdrawn rule teaches more than one that was never tried: the same
no-elapsed-duration rule over the registers' free prose flagged twelve lines and
essentially all twelve were honest history. It lives on the parsed state fields
instead. See [LESSONS.md](LESSONS.md).

---

## Adding a request

1. Give it the next `REQ-nn`. Never reuse a number.
2. Quote **his own words**, in the language he used them.
3. Set the state to **Captured**, add a row to the board.
4. Commit it in the session it was said — not later.

When it advances, move the state, add the link the new state produces (a ruling,
a plan, a PR), and say so in [STATE.md](STATE.md) if it is live work.
