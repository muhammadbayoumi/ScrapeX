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
| [REQ-11](#req-11--branch-protection-for-main-in-a-session-of-its-own) | Branch protection for `main`, in a session of its own | **Captured** — deferred by him | 2026-08-20 |
| [REQ-12](#req-12--justify-the-volume-not-compress-it) | Justify the volume, not compress it | **Captured** — study done, the ruling is his | 2026-08-20 |
| [REQ-13](#req-13--crawl-muqawil-without-missing-anyone-and-know-the-cost-before-starting) | Crawl muqawil without missing anyone, and price it first | **In flight** — built, priced, and running under [R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation) | 2026-08-20 |
| [REQ-14](#req-14--balady-engineering-offices-as-the-next-source-after-muqawil) | Balady engineering offices, the next source after muqawil | **Captured** — queued behind muqawil | 2026-08-20 |
| [REQ-15](#req-15--the-uae-sources-third-in-the-queue) | The UAE sources, third in the queue | **Captured** — queued behind Balady | 2026-08-20 |
| [REQ-16](#req-16--egypt-oman-qatar-bahrain-and-kuwait-fourth-in-the-queue) | Egypt, Oman, Qatar, Bahrain and Kuwait, fourth in the queue | **Captured** — appended in the order received | 2026-08-20 |
| [REQ-17](#req-17--official-diesel-prices--a-product-source-not-a-firm-directory) | Official diesel prices — a product source, not a firm directory | **Captured** — the smallest item in the queue | 2026-08-20 |
| [REQ-18](#req-18--bitumen-6070-prices--the-first-source-that-cannot-be-crawled) | Bitumen 60/70 prices — the first source that cannot be crawled | **Captured** — 5 of 7 need a written quotation | 2026-08-20 |
| [REQ-19](#req-19--reinforced-concrete-material-prices--its-turn-will-come) | Reinforced-concrete material prices — its turn will come | **Captured** — a provenance-typed price model | 2026-08-20 |
| [REQ-20](#req-20--the-database-rename-must-reach-every-user-not-just-this-machine) | The database rename must reach every user | **Captured** — measured; a release blocker under [R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema) | 2026-08-20 |
| [REQ-21](#req-21--the-nested-audit--a-subdivision-must-be-checked-against-its-parent) | The nested audit — a subdivision checked against its parent | **Captured** — measured (deficit 32 of 4,697); not built | 2026-08-21 |
| [REQ-22](#req-22--what-happens-on-a-new-contractor-a-vanished-one-a-changed-one-and-on-update) | What happens on a new / vanished / changed contractor, and on "update" | **Captured** — answered by measurement; 3 of 4 are gaps ([OP-26](BACKLOG.md)) | 2026-08-21 |

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

**Answered by measurement:** [DEC-8](BACKLOG.md#dec-8--the-engines-data-page-is-a-port-not-a-rebuild--measured-2026-08-16) settled his direct question — «هل يمكن نقل صفحة data الموجودة فى المحرك بكل مميزتها الى extension ام يلزم اعادة البناء كامل؟» — by measuring rather than guessing, and the answer is **a port, not a rebuild**. The link was missing in both directions, so a reader of this board could not see the question had been answered at all.

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

## REQ-11 · Branch protection for `main`, in a session of its own

**Captured 2026-08-20 · Deferred by him, deliberately**

> «حماية فرع main» · then «حماية main اجعلها لجلسة مخصصة»

He asked for it, was shown one trap that could lock him out of merging, and moved
it to a session of its own rather than deciding at the end of a long one. That is
the request: **not "protect main" but "protect main with its own attention".**

### Why it matters more than it sounds

**`main` has no protection at all today.** `gh api
repos/muhammadbayoumi/ScrapeX/branches/main/protection` answers **404** — no
required checks, no restriction on direct pushes, nothing. So
[R-18](RULINGS.md#r-18--merge-it-when-it-is-green) is the *entire* gate, enforced
by discipline alone.

It has already failed once, and expensively. `ac3a5af` reached `main` **with no
pull request**, so no CI ran before it landed; it carried a raw hex literal that
`tests/test_vendor.py` forbids, and `main` stayed red from 2026-08-18 until #215
reverted it. Every pull request opened in between inherited that red.

### The trap that stopped it being done at once

After #216 the suite runs in tiers: `test` and `migration-authority` are jobs
gated on `needs: scope`. **A documentation-only change makes them `SKIPPED`** —
observed, not theorised: #216's own run reported exactly that when `scope` failed.
And a *required* check that is skipped does not read as satisfied by GitHub's
merge gate — it can leave a pull request unmergeable for ever. That is the same
silent-skip shape [R-18](RULINGS.md#r-18--merge-it-when-it-is-green) names as its
third trap.

### The two options, as they stood when he deferred

**(a) The safe subset.** Require `lint`, `contract-parity` and `scope` — all three
run on every change and finish in seconds. Forbid direct pushes to `main`, forbid
deletion and force-push. **No** human-review requirement: there is no second
reviewer, so requiring one locks him out. **No** enforcement on admins, so an
escape hatch remains.

**(b) Require everything, `test` and `migration-authority` included** — stronger,
and it accepts that a docs-only pull request may hang until someone intervenes.

*Recommended: **(a)**, and then measure.* The measurement that settles (b) is
cheap and was offered rather than assumed: open a real documentation-only pull
request and read what GitHub reports for a skipped required job, instead of
trusting either reading of the API docs.

### What the session should also settle

- Whether **`migration-authority`** becomes required. #216 asked for this
  explicitly: until it is, a migration-stream failure does not block a merge,
  which is *weaker* than the inline environment variable it replaced.
- Whether the repository being **public** since 2026-08-20 changes anything —
  protection rules and the audit that was declined are related decisions.

---

## REQ-12 · Justify the volume, not compress it

**Captured 2026-08-20 · The study is done; the ruling is his**

> «انا لم استقر على طريقة خفض حجم المخزن … **ليست الفكرة ضغط الملفات** بل دراسة نشوف
> احنا بنسحب اى ولية وبنحتفظ باية ولية وما الفائدة — دراسة تبرر الحجم الذى قيل انه
> سيصل الى 5 جيجا من مصدر مقاول فقط»

He had already been shown `DEC-9` and did not accept it as the answer, and he was
right not to: `DEC-9` asked **how to store 6.4 GB more cheaply** and he is asking
**why we are storing 6.4 GB at all.** Compression answers the first and cannot
touch the second — a justified 660 MB and an unjustified 660 MB look identical on
disk. He also asked for a wider measurement before any migration
(«أريد قياساً أوسع أولاً»).

### This entry is also a filing defect being repaired

The request was **absent from this file entirely** — no hit for «مساحة», `storage`,
`space`, `compress` or «حجم» — while the research it prompted sat in
[BACKLOG.md](BACKLOG.md) as `DEC-9`. That is exactly the failure this file exists to
prevent: `REQ-04` sat ruled and unbuilt for sixteen days after dropping out of view.
Real work, correctly researched, invisible on the board that tracks what he asked
for. `DEC-9`'s own filing was **correct** — it is a finding of ours; his *request*
is what was missing.

### Where it went

[STORAGE.md](STORAGE.md), and the answer is that the volume he asked us to justify
does not exist:

- The 6.4 GB was projected from **one** profile page at 168 KB. Thirteen real
  profiles average **119 KB**, so the complete corpus is **4.55 GB** raw, not 6.4.
- `zstandard` with a raw page used as a shared dictionary compresses listings
  **187×** and profiles **46×** — **254×** re-measured through the wheel that
  shipped — with every row still independently decompressible. `DEC-9`'s zlib gets 15.6× and 7.7×,
  because its 32 KB window cannot see across a 121 KB page — the cross-page
  redundancy it credited for its ratio was **left on the table**.
- So everything the site publishes, both languages, evidence retained: **~90 MB of
  pages plus ~70 MB of rows — about 160 MB**, against the 5 GB in the question.
- And trimming is **strictly dominated**: keeping only the visible text of every
  profile, uncompressed, costs **139 MB**; keeping the whole HTML compressed costs
  **87 MB**. It is more expensive *and* it spends the ability to re-parse, which is
  in active use while 48 of his ~70 columns remain unextracted.

### What still needs him

**Is a snapshot evidence, or only a parse cache?** `SR-1` makes the site the source
of truth, so a stored page is a record of what it published on a date. If that
matters to him, profiles may never be dropped for a re-fetch; if it does not, 87 MB
is recoverable at the price of 17.4 hours. The study refuses to assume this
([STORAGE.md §5](STORAGE.md)).

**And the migration is not written.** He asked for the measurement first; this is
the measurement.

---

## REQ-13 · Crawl muqawil without missing anyone, and know the cost before starting

**Captured 2026-08-20 · Ruled ([R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)) · In flight — built, priced against the live site, and RUNNING**

> **What changed on the evening of 2026-08-20.** The method stopped being a study
> and became `scrapex/partitioncrawl.py` plus a committed driver,
> `tools/crawl_muqawil_listing.py`. Its `--plan` mode answers his third question —
> *how do we estimate the requests before starting* — **by measuring, not by
> quoting a document**: it sizes all 56 cells in 114 requests and prices the crawl
> from the latency it just paid. Run against the live directory it reported 56
> cells, 897 pages, **17,414 declared against the listing's 17,414 — exhaustiveness
> deficit 0**, and ~1,964 requests at about 1.3 h for both locales.
>
> His first constraint is honoured by construction and now proven twice over: the
> last page held **14** cards that evening, against 15 on 2026-08-16 and 2 that
> morning, so `S` and `c` are read every time. His second — «لا اريد تكرار هذا
> الامر» — is what `record_sightings` per attempt answers.
>
> **And it is running.** It looked blocked — the home machine had no warehouse to
> write to ([OP-22](BACKLOG.md)) — and he ruled the premise away the same evening:
> ScrapeX is a tool many people install, so an empty installation is the product's
> normal first-run state and a warehouse is per installation
> ([R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)).
> One was created here and the crawl went into it. `scrapex carry-over` refused on the
> way — 261 pre-0058 offers against a trigger added after them, [OP-23](BACKLOG.md) —
> so the price half of this installation is untouched and that defect is recorded
> rather than worked around.

> «عدد الصفح غير ثابت وفعدد المقاولين المسجلين على الموقع بالتاكيد يتغيروا مع الوقت شوف
> طريقة ازاى نعرف عدد الصفح او ازاى نزحف صح بدون ان نغفل شى … ازاى نقدر عدد الطلبات قبل
> بداية الزحف … **اريد منك فحص كل الحلول والحالات**»

And the reason it was asked, in his words: **«لقد ذكرت لك اسم مقاول لم ياتى فى قاعدة
البيانات — لا اريد تكرار هذا الامر»**. He named contractor **10001274**; the site
answers 200 and the warehouse did not have it. He asked that it not happen again.

He also set the two constraints the answer has to respect, both correcting an
assumption of ours: **the page count is not fixed**, and **a page need not hold
twenty cards** — «البيانات حية».

### This entry is the third filing defect of the same kind, found by a rule

`DEC-11` is 150 lines of measured research that exists **because he asked for it**,
and it quotes his instruction twice. Nothing on this board recorded the request.
[REQ-12](#req-12--justify-the-volume-not-compress-it) was the same failure and
`DEC-8`/`REQ-07` was the same failure in the other direction. Three in one file is
not an accident, so the signal is now a guard:
`tests/test_a_request_of_his_reaches_the_board.py` fails when a finding quotes him
in Arabic and no request cites it.

### Where it went

[DEC-11](BACKLOG.md#dec-11--how-to-crawl-muqawil-without-missing-anyone-and-what-it-costs),
and each of his three questions has an answer:

- **How do we know the page count?** The paginator publishes it — its `»` link
  carries the last page. **One request**, filtered or not, and `read_last_page`
  reads it. It also honours his warning: the last page carried 15 cards on
  2026-08-16, 2 on the morning of 2026-08-20 and 3 that afternoon, so the count is
  `(L−1)×20 + c` with `c` **read**, never assumed.
- **How do we crawl without missing anyone?** `region_id` × `company_size` is an
  exhaustive 56-cell partition, verified to the unit — 15,966 across regions 1–13
  plus 1,437 under `region_id=0`, the contractors who publish no location, summing
  to 17,403 exactly. A slice read inside one cache generation and witnessed against
  its own first page is **provably** complete. One cell is closed already: region 13
  × verysmall, 128 ids, 128 distinct, `D = 0`.
- **How do we estimate the requests before starting?** 56 requests size every cell
  before a single page is crawled. Total **~1,065 requests, ~1.7 h** — against
  **18.4 h** for a blind sweep that can never say "complete".

And **10001274 is reachable on demand**: `?q=10001274` returns exactly one card. So
the specific thing he asked not to recur has a one-request answer, and
`dataset_sighting` (#227) is the ledger that says which ids need it.

### What is not done

The crawl itself. The method is measured and proven on one slice; nothing runs it
yet, and [STORAGE.md](STORAGE.md) was deliberately settled first so that 36,548
pages are not written under a retention policy that a later decision would rewrite.

Five city×size cells stay above the safe slice size, worst ~212 pages, and no
fourth exhaustive axis is fine enough. The witness makes attempting them safe
rather than risky, so it is a cost question — but it is the open one.

---

## REQ-14 · Balady engineering offices, as the next source after muqawil

**Captured 2026-08-20 · Queued behind muqawil, by his instruction**

> «ضيف هذا الملف ليكون المصدر التالى بعد الانتهاء الكامل من مصدر مقاول وكمل شغل كما
> انت»

He attached a **verification brief** for the Saudi Balady Engineering Offices
inquiry service — `apps.balady.gov.sa/Eservices/Inquiries/InquiryEngOffices/Index`
— and set one precondition: **muqawil finished completely first.** "Finished" is his
own definition, «كلّ ما ينشره الموقع».

### Where it went

[BALADY-ENG-OFFICES.md](BALADY-ENG-OFFICES.md), his brief stored **verbatim** under
a preamble that records what this project already knows that bears on it. It is in
the repository rather than in a conversation because he had to re-send the muqawil
column specification once already, not knowing whether it had survived
(«لان دراسته ربما تكون فقدت»).

### What the brief is, and what it is not

It is **not** a schema to implement. It is a brief to **verify** one, and it says so
in its own words: *"Do not assume that any preliminary finding in this brief is
correct."* Every field list in it is labelled *appears to* and carries a
verification instruction. Nine deliverables, and the report format demands every
statement be labelled **Verified / Inferred / Unverified / Not available**.

**Its deliverable 6 should be answered first** — whether an official API or
downloadable open dataset exists. It is the cheapest question in the brief and it
can delete the crawl entirely. muqawil's equivalent was answered late and the answer
was no, at the cost of the requests it took to find out.

### Nothing about it needs a compliance change

Its guardrail — *"Do not bypass authentication, CAPTCHA, access controls, rate
limits"* — is what `HttpFetcher` already does. `SR-8` honours `Crawl-delay`, and the
class names user-agent rotation, proxy rotation, header spoofing and CAPTCHA
handling as deliberately absent because *"those evade a decision the site has
made"*.

---

## REQ-15 · The UAE sources, third in the queue

**Captured 2026-08-20 · Queued behind muqawil and Balady, by his instruction**

> «ضيف هذا الملف ليكون المصادر التالية بعد الانتهاء الكامل من مصدر مقاول ومصدر
> بلدية»

A survey of official UAE government and municipal sources for engineering
contractors and consultancy firms, with his own recommended priority order.

### Where it went

[UAE-SOURCES.md](UAE-SOURCES.md), verbatim under a preamble.

### Why it is a different shape of work, and it matters for planning

**It is not a source; it is a portfolio.** Its key finding is negative and is the
most consequential line in it: **no single public federal directory covers every
emirate.** Registration and classification are per-emirate, so the emirate and the
regulatory authority are part of a record's **identity** — which is why his schema
opens with `country`, `emirate`, `regulatory_authority`, `source_system`. Seven
emirates, four of them with no confirmed public list at all.

**One of them is better-shaped than muqawil, and by a measurable margin.** Abu Dhabi
DMT publishes `firm_name` and `firm_name_ar` **in the same record**. On muqawil the
Arabic half costs a second full crawl — 871 listing pages and 17,403 profiles again
— and the values are matched by page-order index because the same label is spelled
`رقم العضويه` with `ه` in one place. A bilingual record halves the requests and
removes that risk entirely. If it holds up, DMT is the best-shaped source this
project has been given.

### Two of his rules here are already rulings, and one caution must not be lost

The `_ar` convention is `R-12`; child tables for multi-valued groups is `R-19`
(**«جداول أبناء للخمس كلّها»**). And his own caution about Ras Al Khaimah — a company
listed once per project category must be modelled as a company-category
relationship, **not** collapsed as duplicates — is the same trap as counting a
muqawil contractor twice for appearing on two listing pages, which is why
`dataset_sighting` counts sightings separately from records.

---

## REQ-16 · Egypt, Oman, Qatar, Bahrain and Kuwait, fourth in the queue

**Captured 2026-08-20 · Appended to the queue in the order received**

> «المزيد من المصادر ضفها الى القائمة»

He said *add them to the list* without naming a position, so they are **appended
after the UAE**. Nothing has started on any queued survey, so the order costs
nothing to change — it is written down so there **is** one, not so it is fixed.

### Where it went

[GULF-EGYPT-SOURCES.md](GULF-EGYPT-SOURCES.md), verbatim under a preamble.

### The scale, and where its value actually is

The largest of the three surveys: **five countries, 32 numbered sources, 933
lines.** With this the queue reaches **eight countries**.

**Its most useful content is where it says no.** Only three of the five have
anything resembling a national public directory:

| | |
|---|---|
| **Oman** | ESNAD / Tender Board `Registered Companies` — his own words, *"the closest source found to the Saudi `muqawil.org` use case"* |
| **Qatar** | Monaqasat classified-company profiles |
| **Bahrain** | three separate official lists, not one |
| **Egypt** | **no complete combined directory confirmed** — EFCBC is authenticated; DRSO's consulting-office list is Arabic-only |
| **Kuwait** | **no complete current public list confirmed** |

So its real instruction is his §45 — *"build federated datasets rather than claiming
a single complete national directory"* — and that is a **schema** requirement rather
than a crawl detail. It is why his `firms` table carries `source_system` and
`regulatory_authority`, and why classifications, accreditations and contacts are
separate child tables.

### Two things in it that this project should take even before the work starts

**A stable identifier joining two language views is better than anything muqawil
has.** Oman's ESNAD and Qatar's Monaqasat both publish Arabic and English views
joined by an identifier — PTLC/CR, and the profile file number. On muqawil the
Arabic half is a **second full crawl** of 871 listing pages and 17,403 profiles,
matched by **page-order index** because one label is spelled `رقم العضويه` with `ه`.
His §38.4 and §38.5 already require the identifier join, and it removes that risk
entirely.

**His §38.2 is stricter than any rule we have written down**, and it should be
adopted: keep `source_registration_number_raw` — the identifier **exactly as
published** — beside any cleaned form. muqawil stores the membership number as
published and it has held, but nothing records that as a rule. Eight countries of
identifiers with slashes and leading zeros is the wrong time to find out.

### What has not been done

Nothing. It is queued, and its own §39 requires every one of the 32 sources to be
re-opened and re-verified on the day the work starts, because *"all source status,
counts, classifications, contacts and expiry dates are time-sensitive"*.

---

## REQ-17 · Official diesel prices — a product source, not a firm directory

**Captured 2026-08-20 · Queued; and it is the smallest item in the queue by far**

> «مصادر اخرى لاسعار الديزل فقط مصادر منتجات ضيفها لقائمة المصادر»

Official retail diesel prices for Saudi Arabia, the UAE, Egypt, Oman, Qatar,
Bahrain and Kuwait, with the publisher and the dated announcement for each.

### Where it went

[DIESEL-PRICES.md](DIESEL-PRICES.md), verbatim under a preamble.

### He classified it himself, and the classification matters

**«مصادر منتجات»** — product sources. The other four queued surveys are **firm
directories** and land in `generic_record` through the generic-dataset seam muqawil
pioneered. This describes **a product's price over time**, which is the *original*
spine of this project: `price_observation`, the `db/migrations/` PRICE chain, `SR-6`.

**It is the first queued source that touches the half of the warehouse muqawil never
went near.**

### And it is tiny, which he should know before deciding where it sits

| | requests to collect once |
|---|---|
| muqawil, everything the site publishes | **36,548** |
| this | **7 pages, ~14 with both locales** |

About **fourteen requests a month**. It does not compete with finishing muqawil in
any real sense — an afternoon, not a track. The order stays his; the size is recorded
so the decision is made with it in view.

### One mechanism will silently drop his data, and it is already measured

His rule §3 is *"never overwrite a previous price when a new month or quarter
begins."* `SR-6` says **an unchanged price is confirmed, not appended.** Those
disagree, concretely: if Oman's July price was also `0.258`, the append gate sees no
change and writes nothing, so the **August period never exists** and his §3 is
violated by a rule that is otherwise right.

> A period-keyed price must key the append gate on the **period**, not only the
> value. `SR-6` was written for a shelf price, where an unchanged number carries no
> information. An official price *for a named month* carries information even when
> the number is identical — it says the ministry set it again.

Same shape as a defect already on record: a new `price_observation` column stays NULL
because the gate never learned to notice it. **Settle it before the first collection,
not after a month is missing.**

### Two sources need something this project does not have

- **Bahrain publishes the price as an image.** His own instruction is to preserve the
  screenshot or image hash and treat OCR as a *candidate* extraction only, verified
  against the dated committee announcement. There is no OCR path here, and his rule
  is the right one regardless: the image is the evidence, the number is a claim
  about it.
- **Kuwait's page is stale in the dates, not the price.** He observed a correct value
  beside an out-of-date validity note and says not to derive the effective dates from
  the static page. A collector that trusted it would store a right price under wrong
  dates, which is the worse failure because it looks complete.

---

## REQ-18 · Bitumen 60/70 prices — the first source that cannot be crawled

**Captured 2026-08-20 · Queued; and its acquisition mode is correspondence, not fetching**

> «مصادر اخرى»

Official bitumen 60/70 price sources for the same seven countries as the diesel
list — and its conclusion is that, for five of them, **there is nothing public to
fetch.**

### Where it went

[BITUMEN-PRICES.md](BITUMEN-PRICES.md), verbatim under a preamble.

### Why it is unlike every other source in the queue

| | |
|---|---|
| **`quote_required`** | Saudi Arabia, UAE, Oman, Bahrain, Kuwait |
| **a dated bulletin, not a live price** | Egypt — `EGP 21,542`/tonne, July 2026 |
| **already expired** | Qatar — `2,925`/tonne, 22–31 July 2026, **no currency label on the page** |

Bitumen 60/70 is bulk B2B: the payable price depends on quantity, customer category,
loading point, destination, hot-bulk versus packaged, tax, freight and quote
validity. His brief therefore ends with **a letter to send a producer**, not a URL to
crawl. That is the shape of the product, not a gap in the plan.

**So what this project can do for it is narrower and more valuable than a crawl:** be
the place a dated, sourced, caveated observation is stored so it is never mistaken
for a current market price. His `verification_status` vocabulary —
`quote_required`, `latest_official_bulletin`, `expired_official_price` — is the most
useful column in his design.

### Its most important instruction is a refusal to compare

*"Do not flatten these observations into one comparable price list."* Egypt's official
label is **بيتومين مؤكسد على الساخن 70/60**, possibly a hot-applied **oxidized**
product rather than the paving penetration grade; Qatar's row shows no currency.
Comparing or converting them would manufacture a number nobody published. That is
`SR-1` on a harder case: what was published is *incomplete*, and the record must
carry the incompleteness rather than resolve it.

### And it is the second measured case against `SR-6`'s key

`SR-6` confirms rather than appends an unchanged price. Here two observations can
carry **the same number and different commercial bases** — ex-refinery versus
delivered, taxed versus not. Different facts, equal values; a gate comparing only the
number collapses them and destroys the only thing that makes either usable.

> With [REQ-17](#req-17--official-diesel-prices--a-product-source-not-a-firm-directory)
> this is two independent cases saying the same thing: **the append gate's key is not
> the number.** For diesel it is the period; for bitumen it is the commercial basis.

### One line in it is a hard boundary, not a task

His §12 rejects any figure not traceable to an official producer, public authority,
signed quote, tender award or official statistical publication — trader
advertisements and aggregator sites explicitly excluded. That is a rule about what
may enter the warehouse at all, and it is stricter than anything code enforces today.

---

## REQ-19 · Reinforced-concrete material prices — its turn will come

**Captured 2026-08-20 · Queued, in his own words**

> «مصادر جديدة ضيفها للقائمة **سياتى دورها يوما ما**»

Cement, reinforcing steel, structural steel sections, sand, coarse aggregate and
water, across the same seven countries.

### Where it went

[CONCRETE-MATERIALS.md](CONCRETE-MATERIALS.md), verbatim under a preamble.

### It is the most carefully-typed of his briefs, and that is its contribution

Its §3 source-type table carries a column headed **"Can it populate `price_amount`?"**
and answers **No** for `official_price_index`, `official_approved_source` and
`official_specification`. An index is not a price; an approved-supplier list does not
establish one. That is a **provenance-typed price model**, stricter than anything this
warehouse enforces, and it is why his design gives `price_index_observations` and
`water_tariffs` their own tables rather than a `kind` column on one.

### Water is the sharpest example in any of the seven briefs

His §2.2 refuses to store a single water price at all: the official network tariff is
one component beside meter charges, wastewater, tanker filling, transport, storage and
testing — and *"a potable-water tariff alone does not prove technical suitability"* for
mixing or curing. **One number would be false in both directions** — too low as a
delivered cost, and not evidence of fitness for purpose.

### It completes a pattern, now recorded as [DEC-12](BACKLOG.md)

Third independent case that `SR-6` keys on the wrong thing: diesel says the key is
the **period**, bitumen the **commercial basis**, this one the **source type**. Three
products, three axes, three briefs written separately — and recorded before any
collection is scheduled, because the failure is silent and the data does not wait:
dated bulletins expire, and the Qatar bitumen figure had already expired when he sent
it.

### And its own coverage is narrower than its length suggests

Its §12 bottom line: only **Saudi Arabia, Egypt and Qatar** have usable official
absolute prices. Oman and Kuwait offer **indices**, which its own §3 says are not
prices. Bahrain offers approval and specification evidence, which is not a price
either. So for four of seven countries this is a `quote_required` source in the same
sense the bitumen brief is.

---

## REQ-20 · The database rename must reach every user, not just this machine
**Captured 2026-08-20 · Measured the same evening; the build is his to schedule**

> «قاعدة بيانات marketlens تم تغيير اسمها — هل تم تغيير اسمها عند كل المستخدمين؟»

He asked it as a question and it is a requirement: `marketlens.db` + `general.db`
became `engine/scrapex-engine.db`, and **every existing installation has to make that
transition exactly once.** He had just watched me do it by hand on this machine, and
the question is whether a user gets the same outcome without me there.

### The answer is no, and it was measured rather than argued

`carry_over` has exactly one production caller — the manual `scrapex carry-over`
subcommand. Simulated against a fake split installation:

| how the user starts it | what they get |
|---|---|
| a terminal | a clean message naming `scrapex carry-over` |
| **the extension panel** (`native.startup_check()`) | `ok: false`, `action: "check_storage"` — a dead engine |
| **the panel's own repair button** (`native.upgrade_database()`) | `ok: false`. It **cannot** fix this transition at all |

Full detail in [OP-24](BACKLOG.md).

### Why this is his ruling already, applied to the wrong half

The project decided this on **2026-08-05**, on his instruction, when migration 0061
left the engine refusing to start: *"the one person the refusal speaks to is the one
who does not read a log"*, so the upgrade became part of the startup procedure
(`cli._upgrade_what_is_only_behind`). That reasoning was applied to **migrations** and
never to **carry-over** — the larger transition of the two. Under
[R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
it is a release blocker rather than debt.

### And the automatic version is safer than the one already shipping

`_upgrade_what_is_only_behind` advances the user's file in place and must back it up
first. `carry_over` opens both old files **read-only**, writes a new one, verifies
every table's row count, and moves the pointer **last** — so the old files *are* the
backup, and a failure leaves an installation that refuses to start rather than one
running on half its data.

### What it still needs, and it is the gap that hid this

**A test that a split installation STARTS.** Every carry-over test to date calls
`carry_over` directly, so nothing ever exercised the path a user takes — which is
exactly why a manual-only remedy looked finished.

---

## REQ-21 · The nested audit — a subdivision must be checked against its parent
**Captured 2026-08-21 · Measured; not built**

> «اريد تسجيل التدقيق المتشعب ضمن الطلبات»

He asked for this by name after the weak point of subdividing a heavy cell by
`city_id` was put to him: the city list is chosen from **incomplete** evidence, and
the site is live, so **«ماذا لو تم اضافة مقاول جديد بمدينة جديدة»** — a new
contractor in a city we have never seen.

### The principle, which is the durable part

**A subdivision is an optimisation, never a source of truth.** Correctness comes from
the parent cell, which always remains the fallback. So for every subdivision:

    Σ N_child  ==  N_parent   ⇒ the child list is complete FOR THIS RUN
    short by k               ⇒ k rows live in children we do not know about,
                               named as a deficit and closed by the counting
                               proof on the PARENT, which needs no child list

A new city therefore costs **efficiency, never coverage**. And it self-heals between
runs: the next run re-derives the child list from updated evidence.

### Measured on the worst cell, 2026-08-21

| | |
|---|---|
| evidence showed | 3,094 contractors in 49 cities (**66%** of the cell) |
| the site publishes | 669 cities for that region |
| `Σ N` over the 48 matched city cells | **4,665** |
| the parent declares | **4,697** |
| **deficit — rows in cities the evidence never showed** | **32 (0.68%)** |

**Seeing two thirds of the contractors revealed 99.3% of the rows' cities**, because
cities are few and contractors cluster in them: city coverage saturates far faster
than contractor coverage. That is why choosing a subdivision from partial evidence
works at all, and the audit is what makes relying on it safe.

### What is missing, and it is a gap in my own plan

**`crawl_partition`'s audit compares `Σ N_cell` against the WHOLE listing, not against
a parent cell.** Running the 151 city cells as a partition today would compare them to
17,417 and report a meaningless deficit. The nested comparison has to be built:
a partition needs to know its parent, and the audit has to be relative to it.

### And the subdivision turned out to be worth less than I claimed

`RIYADH × verysmall` alone is **4,268 of that cell's 4,697 rows over 214 pages** — so
subdividing by city moves the unprovable part from 4,697 to 4,268, a **9% improvement**.
DEC-11 was right that no fourth axis is fine enough. The counting proof is not an
optimisation for Riyadh and Jeddah; it is the only route. See
[R-25](RULINGS.md#r-25--the-crawl-method-is-settled-first-the-schema-and-retention-questions-come-last)
for why this is being settled before the schema questions.

---

## REQ-22 · What happens on a new contractor, a vanished one, a changed one, and on "update"
**Captured 2026-08-21 · Answered by measurement; three of the four answers are gaps**

> «اريد معرفة ماذا سيحدث اذا ظهر مقاول جديد اذا اختفى ماقول اذا تغيرت بيانات مقاول ·
> ماذا سيحدث عندما يضغط المستخدم على update · ايضا هل طريقة البحث والحفظ هى المثالية
> فى مصدر مقاول ام هناك ثغرات كثيرة»

Measured against the code rather than reasoned about:

| event | what happens today |
|---|---|
| **a new contractor appears** | seen, sighted, and upserted on `(dataset_definition_id, record_key)` with a revision. **Works** |
| **a contractor disappears** | **nothing at all.** No production code sets `status='superseded'` on `generic_record` — grep returns zero callers. The row stays `active` with a frozen `last_seen_at`, and is indistinguishable from a contractor this run did not crawl |
| **a contractor's data changes** | `content_hash` differs, `data_json` is replaced and a revision written. Works — but a revision is written **whether or not anything changed**: 34,550 revisions for 11,059 contractors. That contradicts [R-20](RULINGS.md#r-20--an-unchanged-contractor-is-confirmed-not-re-recorded), which is a ruling not yet implemented |
| **the user presses "update"** | **nothing happens to contractors.** `scrapex/jobs.py` — what the panel drives — contains no reference to muqawil, `generic_record`, `partitioncrawl` or `snapshotcrawl`. It runs the price connectors. Contractors can only be crawled from a terminal command |

### The answer to his last question

**The collection is sound; the lifecycle is not.** Gathering is now provable, stores
its evidence, resumes, and records every id seen. What is missing is everything that
happens *after* the first crawl: disappearance is invisible, an unchanged row still
writes history, there is no path from the product's own interface, and the schema
question is open. Filed as [OP-26](BACKLOG.md).

---

## Adding a request

1. Give it the next `REQ-nn`. Never reuse a number.
2. Quote **his own words**, in the language he used them.
3. Set the state to **Captured**, add a row to the board.
4. Commit it in the session it was said — not later.

When it advances, move the state, add the link the new state produces (a ruling,
a plan, a PR), and say so in [STATE.md](STATE.md) if it is live work.
