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
| [REQ-07](#req-07--the-data-page-must-carry-everything-the-engines-page-carries) | The Data page carries everything the engine's page does | **In flight** — he raised it again 2026-08-22 and ruled «كلها»; [the plan](plans/2026-08-22-the-source-page-moves-into-the-extension.md) has seven steps and step 0 is done | 2026-08-12 |
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
| [REQ-21](#req-21--the-nested-audit--a-subdivision-must-be-checked-against-its-parent) | The nested audit — a subdivision checked against its parent | **In flight** — the audit is built and guarded; no subdivision is wired to a site yet | 2026-08-21 |
| [REQ-22](#req-22--what-happens-on-a-new-contractor-a-vanished-one-a-changed-one-and-on-update) | What happens on a new / vanished / changed contractor, and on "update" | **Captured** — answered by measurement; 3 of 4 are gaps ([OP-26](BACKLOG.md)) | 2026-08-21 |
| [REQ-23](#req-23--test-my-own-ruling-before-building-it-with-strict-review-criteria) | Test my own ruling before building it, with strict review criteria | **Done** — [R19-CHILD-TABLES-MEASURED.md](R19-CHILD-TABLES-MEASURED.md); ruling upheld, a refinement proposed as `Q-13` | 2026-08-21 |
| [REQ-24](#req-24--a-shipped-command-so-a-new-user-can-crawl-the-directory-at-all) | A shipped command, so a new user can crawl the directory at all | **Done** — `scrapex contractors`; the panel path is still missing | 2026-08-21 |
| [REQ-25](#req-25--one-source-registry-with-a-category-visible-to-every-user) | One source registry, with a category, visible to every user | **Planned** — ruled 2026-08-27 as [R-62](RULINGS.md#r-62--one-source-registry-site_profile-merges-into-source_site--and-q-24-is-answered-by-that-migration): he chose the migration, `site_profile` into `source_site`. Measured: **2 rows to move, 2 tables to repoint, `price_observation` untouched**. Answers `Q-24` inside it and unblocks the crawl button | 2026-08-21 |
| [REQ-26](#req-26--a-database-per-account-not-per-machine) | A database per account, not per machine | **In flight** — `Q-14` answered (`R-34`): the account is the signed-in address, and his warehouse records it; the per-account layout remains | 2026-08-21 |
| [REQ-27](#req-27--a-second-source-of-a-category-reuses-the-firsts-machinery) | A second source of a category reuses the first's machinery | **Done** — `scrapex/directories.py`; `--source`, and the crawl is inherited | 2026-08-21 |
| [REQ-28](#req-28--the-engine-would-not-install-and-showed-a-black-screen) | The Engine would not install — a black screen, and no way to install it | **In flight** — cause proven, gate closed, and `engine-v0.3.0` published 2026-08-22 after he raised it a second time; his confirmation that it installs is what remains | 2026-08-21 |
| [REQ-29](#req-29--an-install-surface-that-looks-like-a-professional-program-and-an-update-anyone-can-apply) | An install surface that looks like a professional program, and an update anyone can apply | **In flight** — the engine reads, fetches and verifies; the panel downloads with progress. The swap awaits a real frozen build | 2026-08-21 |
| [REQ-30](#req-30--the-three-dots-button-appears-twice-on-a-source-card) | The three-dots button appears twice on a source card | **In flight** — cause proven, fixed and guarded; merging is his | 2026-08-22 |
| [REQ-31](#req-31--start-the-profile-parser--and-the-pages-are-not-consistent) | Start the profile parser — and the pages are not consistent | **In flight** — the cards are built, guarded and mutation-tested; `Q-17` and `Q-18` are his | 2026-08-22 |
| [REQ-32](#req-32--fixed-columns-and-everything-else-in-the-rows-own-card) | Fixed columns, and everything else in the row's own card | **Ruled** ([R-45](RULINGS.md#r-45--the-site-is-the-only-source-of-truth-and-a-field-the-table-does-not-need-goes-in-the-rows-card)) — not built; the card does not exist on either surface | 2026-08-22 |
| [REQ-33](#req-33--the-dataset-cards-said-no-successful-crawl-over-crawled-rows) | The dataset cards said "no successful crawl yet" over 17,304 crawled rows | **Done** — the date is derived from the evidence; the two registries stay his | 2026-08-22 |
| [REQ-35](#req-35--the-card-must-say-the-engine-is-running-from-source-not-that-it-is-missing) | The card must say the engine is running from source, not that it is missing | **In flight** — the engine now reports its run mode and commit; the check-window wording is still owed | 2026-08-22 |
| [REQ-36](#req-36--the-three-dots-are-missing-on-a-contractor-card-and-unprofessional-on-the-others) | The three dots are missing on a contractor card, and unprofessional on the others | **In flight** — a session is measuring which treatment he means before restyling | 2026-08-22 |
| [REQ-37](#req-37--one-card-per-site-and-its-crawls-are-options-under-it--the-way-gpp-does-it) | One card per site, and its crawls are options under it — the way GPP does it | **In flight** ([R-47](RULINGS.md#r-47--muqawil-is-one-card-with-two-crawls-and-the-two-stored-datasets-stay-two)) — muqawil is ONE card and the population is stated once; the two crawl OPTIONS are blocked on a panel path to a dataset crawl ([OP-52](BACKLOG.md)) | 2026-08-22 |
| [REQ-38](#req-38--the-backup-must-check-its-own-digest-and-the-panel-must-be-able-to-finish-the-build) | The backup must check its own digest, and the panel must be able to finish the build | **Captured** — measured: the digest is written and never read; the button aborts at 10 s on a 5-minute build | 2026-08-22 |
| [REQ-39](#req-39--the-extension-must-report-what-drive-holds-because-nothing-else-can-ask) | The extension must report what Drive holds, because nothing else can ask | **Captured** — the panel is the only holder of the token and it stores no answer | 2026-08-22 |
| [REQ-40](#req-40--the-extension-is-the-phone-and-the-engines-are-apps-installed-on-it) | The extension is the phone and the engines are apps installed on it — study which of the engine's duties shrink into it | **Captured** — measured: the premise is HALF BUILT since 2026-08-12 and undocumented; three counted holes, chief of them 0 of 18,008 contractors in the offline pack | 2026-08-23 |
| [REQ-41](#req-41--the-two-crawls-disagree-so-the-code-must-reconcile-them-itself) | The two crawls disagree, so the code must reconcile them itself — fetch or approve whichever side is short | **Captured** — re-measured 2026-08-24 now the profile crawl has finished: 148 have a profile and no listing row (all 148 already on disk, zero requests); **188** have a listing row and no profile, and **zero of them need fetching** — every one has a profile snapshot stored and was refused at approval, 59 by `OP-64` (the id is dead and the site answers with the listing) and 129 by `merge_locales` (see `OP-66`). The figure here read `35` when it was written, taken mid-crawl. The listing reorders under the crawl so any two passes drift | 2026-08-23 |
| [REQ-42](#req-42--a-contractor-the-site-withdrew-is-entered-with-what-we-know-and-a-state-that-says-so) | A contractor the site withdrew is entered with what we know and a state that says so | **Captured** — measured: all **202** with no *active* profile row DO have their listing card, 24 fields each, and 0 have nothing. **Two counts, and which one is meant has to be said**: 188 have no profile row AT ALL, and 202 have none that is `active` — the difference is the 14 rows `--impostors --repair` retired. `203` was written here on 2026-08-23 against the same definition as the 202; one contractor gained a profile in the `gap-2026-08-23` run. The state must separate 'the site withdrew it' from 'we never fetched it' from 'we wrote it wrong' | 2026-08-23 |
| [REQ-44](#req-44--the-state-gets-its-own-column-and-the-user-never-infers-it) | The state gets its own column, and the user never infers it | **Done** — ruled as `R-27` and built the same day (#235 + migration 0006), and the column it asked for now lies: `OP-68` measures it reporting 17,256 of 17,304 contractors as gone after a crawl that read every one | 2026-08-21 |
| [REQ-45](#req-45--the-crawl-button-does-not-work-for-muqawil) | The crawl button does not work for muqawil | **Captured** — root cause proven on the live engine: `POST /api/jobs` validates against `sources.yaml` and muqawil lives in `site_profile`, so the route answers 404 and the panel hides the button deliberately. The fix needs `REQ-25`; **four parts do not** and he approved all four | 2026-08-26 |

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
**Captured 2026-08-16 · Ruled ([R-10](RULINGS.md#r-10--the-contractor-directory--three-rulings), [R-11](RULINGS.md#r-11--a-contractor-directory-is-a-separate-table-and-a-table-like-any-other)) · Planned ([plan folded 2026-08-27](plans/README.md#historical)) · Done — #202–#212**

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

**Captured 2026-08-12 (the migration plan is his) · Planned · In flight — raised
again 2026-08-22, and step 0 of the seven is built**

**Answered by measurement:** [DEC-8](BACKLOG.md#dec-8--the-engines-data-page-is-a-port-not-a-rebuild--measured-2026-08-16) settled his direct question — «هل يمكن نقل صفحة data الموجودة فى المحرك بكل مميزتها الى extension ام يلزم اعادة البناء كامل؟» — by measuring rather than guessing, and the answer is **a port, not a rebuild**. The link was missing in both directions, so a reader of this board could not see the question had been answered at all.

Four capabilities remain before the workbook link may be removed from the source
card: the details drawer, Choose-Columns, saved views, and promotion. The order
is reasoned and is in [STATE.md](STATE.md#track-1--the-console-migration).

**Blocked in part:** saved views waits on
[O-5](RULINGS.md#open--awaiting-the-owners-ruling) — he has comments on B1 and
will raise them first.

### He raised it again on 2026-08-22, ten days after capturing it

> «كان فى خطة لنقل http://127.0.0.1:8000/source الى extension
> chrome-extension://ekcgggphcfdbjgfkcmjagehfjhijeang/data.html?source=»

He was right that there was a plan, and **the fact that he had to ask is the
defect.** Captured 08-12, answered by measurement 08-16, and on 08-22 nothing had
been built — which is `REQ-04`'s sixteen days happening again in a different row
of the same table. **Recorded here in the session he asked it**, per **C7**,
because a brief to an agent is not a record.

**Asked again the same day, and he refused the framing of the question put to
him.** He was asked whether to build the products half or the contractors half
first, since `REQ-07`'s four capabilities are all products-shaped while `R-45`'s
stated reason was contractors:

> «ضع خطة لتنفيذها كلها وتتبع التنفيذ حتى لا نفقده»

*All of it, and track the execution so we do not lose it.* So it is an order and
not a choice, and **the tracking is part of what he asked for** — the plan carries
a status table with a gate per step, and each step says which category it serves:
[plans/2026-08-22-the-source-page-moves-into-the-extension.md](plans/2026-08-22-the-source-page-moves-into-the-extension.md).

**And he asked for the payload cost to be measured rather than argued** —
«قِسْ أوّلاً ثمّ قُل لى» — after this session flagged the panel's 5,000 ms deadline
against a ~21 MB payload as a risk. **Measured: 616 ms of the 5,000, 12% of the
budget.** The flag was wrong, and the measurement is in the plan.

**One of `DEC-8`'s four is not remaining, and one that is remaining was never
counted.** The details drawer exists on the engine for products and has since
2026-07-22 — `R-45` says otherwise and is being corrected. What is not in
`DEC-8` at all is the same card for a DATASET, which is `REQ-32`: it needs a new
engine endpoint, because `/api/offer` is products-only on every axis. So this
request is a port and `REQ-32` is a build, and the plan sequences them together.

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
**(b)** Fold `R-01..R-13` back into BACKLOG.md §1 as `SR-24..SR-38`, delete
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
**Captured 2026-08-21 · In flight — the audit is built; the subdivision is not**

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

### What was missing, and it was a gap in my own plan — now built

**`crawl_partition`'s audit compared `Σ N_cell` against the WHOLE listing, not against
a parent cell.** Running the 151 city cells as a partition would have compared them to
17,414 and reported a deficit of thirteen thousand rows that were never in scope — a
number so wrong it would have to be ignored, which is how a check stops being one.

Built as **one parameter and one refusal**:

| | where | what it does |
|---|---|---|
| `crawl_partition(..., parent=Cell)` | `scrapex/partitioncrawl.py:1019` | sizes the PARENT, so every number is measured against it; `WHOLE` is the default and top-level runs are unchanged |
| `Cell.is_under(other)` | `scrapex/pagesource.py:146` | subset-hood expressed in filters — adding a filter can only narrow, so a child carrying all of the parent's name/value pairs selects a subset, **in any order** |
| `NotASubdivision` | `scrapex/partitioncrawl.py:1012` | raised **before a single request** when a cell is not inside the parent. A child that dropped a parent filter is measured over a larger set and could report a comfortable zero deficit while covering none of the parent |
| `PartitionOutcome.parent` / `.scope` / `.nested` | | so the report says what it audited, and a nested proof reads *"PROVABLY COMPLETE FOR cell … — AND FOR THAT CELL ONLY"* rather than claiming the listing |

Guarded by seven tests in `tests/test_a_crawl_that_can_prove_it_read_everything.py`
and **eight mutations, all killed** — including the reversed subset test, the ordered
comparison, and the nested proof claiming the listing.

The re-size at the end follows the same scope, which is not cosmetic: a nested run
that re-sized the whole listing would report the site's churn as the parent's, and a
child ending one id short would then be excused by a departure that happened in
another region entirely.

**A nested crawl is runnable today, and that was worth checking rather than
assuming.** Measured 2026-08-21: `listing_url` builds from `cell.query`
generically, so a city cell is a URL like any other —
`?region_id=1&company_size=verysmall&city_id=21&page=3` — and `in_cell` yields its
pages in both locales. So `crawl_partition(cells=<city cells>, parent=<the cell>)`
works end to end now.

What is **not** built is a *published* city-cell generator: `cells()` still returns
only the 56 `region_id x company_size` cells, and the 151 city cells were computed
in a scratchpad from stored evidence. Deriving them inside the source module means
querying the warehouse for what we have seen, which is a design decision — and the
measurement below says it would buy 9% for the cell that motivated it, so it is not
being built ahead of his ruling ([R-25](RULINGS.md#r-25--the-crawl-method-is-settled-first-the-schema-and-retention-questions-come-last)).

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

## REQ-23 · Test my own ruling before building it, with strict review criteria
**Captured 2026-08-21 · Done — measured; the ruling is upheld and a refinement is
proposed for him to rule on**

> «ادمج لما يخضر وابدأ R-19 (ادرس حكمى اولا هل هو صحيح ام هناك الافضل ضع معايير
> صارمة للمراجعة مثل الاداء والسرعة والاحترافية الخ)»

Said when `R-19` came up for building. It is the second time he has asked for a
ruling of his own to be challenged rather than obeyed — `R-19` itself records
«ربما يكون قرار خاطى» — and it is now clearly a standing preference rather than a
one-off: **a ruling is a decision, not an instruction to stop measuring.**

### What he asked for, and what it produced

"Strict criteria" was taken literally: eleven of them, **set before any shape was
measured** so that no shape could be judged on whichever number happened to flatter
it. Five shapes, 518,490 rows.
[R19-CHILD-TABLES-MEASURED.md](R19-CHILD-TABLES-MEASURED.md) is the study.

| | |
|---|---|
| **his ruling is upheld** | JSON costs **1,168 ms** on the query `R-19` names, against **0.6 ms** for the best shape — 47x worse than even a bespoke table |
| **and it decided only half the question** | *where* the child rows live was ruled; *how the value is stored* was never put to him |
| **the criterion nobody had raised** | the site **relabels a category**: 103,698 rows rewritten in 5.9 s, against 1 row in 0.1 ms — about 59,000x |
| **two errors in the ruling's own evidence** | the licensed-activities table is not generally empty (a different contractor has six rows), and the value is a two-level bilingual path, not a flat string |

Recorded as **`Q-13`** in [BACKLOG.md](BACKLOG.md) with three options and a
recommendation. **Nothing was built** — the choice is his, which is the whole point
of the request.

---

## REQ-24 · A shipped command, so a new user can crawl the directory at all
**Captured 2026-08-21 · Done**

> «لو انا مستخدم جديد زحف مقاول هيتعمل ازاى للحصول على كل البيانات بشكل صحيح»
> · «نفذ البند ١ الامر المشحون»

He asked how a **new user** would run the crawl, and the measured answer was that
they could not — not by any supported path:

| | |
|---|---|
| `pyproject.toml` | `include = ["scrapex*"]`, so **`tools/` is never shipped**. `pip install` does not put the script on their machine |
| `scrapex crawl` | takes a `source_key from sources.yaml`, and **muqawil is not in `sources.yaml`** |
| `cli.py` | **zero** references to `muqawil`, `partitioncrawl`, `snapshotcrawl` or `generic_record` |
| `jobs.py` and the panel | zero references — the update button runs the price connectors |

**That is why his own screenshot showed the Engine as "not detected" while a crawl
was running.** The crawl was `python tools/crawl_muqawil_listing.py`, a developer
script writing straight into SQLite. It never went near the Engine, and did not need
to. Everything built for this directory — the provable partition, the sightings
ledger, the resume, the approval from disk — was reachable only by cloning the
repository.

**Built:** `scrapex/contractors.py`, shipped inside the package, with
`scrapex contractors --plan / --crawl / --approve / --coverage`.
`tools/crawl_muqawil_listing.py` is now a four-line pointer, kept because six
documents and one running command name that path.

**One implementation, two front doors.** `add_arguments` and `run` are shared by the
subcommand and by `python -m scrapex.contractors`, so neither can grow a flag the
other lacks — the same rule `publish.workbook_tables` follows. Guarded by a test
that the flag set is declared in one place, and by another that the module is inside
the package rather than in `tools/`.

**What this does NOT do:** there is still **no path from the panel**. `jobs.py` does
not know this crawl, so it cannot be started, paused or resumed from the product's
own interface. That is the next item, and it is separate.

---

## REQ-25 · One source registry, with a category, visible to every user
**Captured 2026-08-21 · Ruled 2026-08-27 · Planned**

> **Ruled 2026-08-27 as [R-62](RULINGS.md#r-62--one-source-registry-site_profile-merges-into-source_site--and-q-24-is-answered-by-that-migration): one registry.** He chose to merge `site_profile` into `source_site` rather than teach `POST /api/jobs` the other two registries, which is what I recommended. **Measuring it for the ruling showed my cost estimate was too high**: 2 rows to move, 2 tables to repoint (`dataset_definition`, `dataset_relationship`), and `price_observation`'s 94,664 rows are untouched because they do not reference `source_site`. It answers `Q-24` inside the same migration — id 1 (`muqawil`) closes, id 2 (`muqawil_org`) survives — and it is what unblocks [REQ-45](#req-45--the-crawl-button-does-not-work-for-muqawil), the crawl button.

> «اى مصدر اعطيه لك ونشتغل عليه لازم يظهر ضمن المصادر المسجلة لاى مستخدم ويستطيع
> عمل زحف عليه · اى مصدر ادتهولك ولم ناسس له زحف يحفظ فقط فى قائمة مصادر حتى ياتى
> دوره» · «ونعمل category للمصادر لدينا الان 2 منتجات ومقاولين»

**Half of this is already built, and finding that out first is the point.**
`sources.yaml`'s own header says sources start `active: false` and are activated only
when their collector lands with tests, and `family: TBD-probe` already means
*registered, no collector yet* — validation **refuses** `active: true` while the
family is unproven: *"A source that has not been probed cannot be active."* So
*"waits in the list until its turn"* exists — measured with the new `scrapex sources`:
**twelve** registered, seven active, five built, and **nothing in the `registered`
state**, so the mechanism is real and currently empty.

**What does NOT exist is one registry and a category.** Measured: `source_site` holds
the four price sources, `site_profile` holds `muqawil_org`, and **muqawil is not in
`sources.yaml` at all**. A source lands in one or the other by accident of which
pipeline collected it, so nothing answers *"what sources does this installation have,
and what state is each in"* — which is the question he asked.

Categories, in his words: **`products`** and **`contractors`**, with `jobs` and
`tenders` named as coming. Planned in [the platform plan](plans/2026-08-21-the-platform-not-a-price-tracker.md).

**Open for him:** whether `site_profile` merges into `source_site`, or both become
views over one table. Merging is correct and is a migration over live rows.

---

## REQ-26 · A database per account, not per machine
**Captured 2026-08-21 · In flight — the identity is settled, the layout is not**

> **`Q-14` ANSWERED 2026-08-21 → [R-34](RULINGS.md#r-34--an-account-is-the-signed-in-address-and-a-warehouse-records-whose-it-is).**
> The account is the **signed-in address**, and his own warehouse now records it in
> `scrapex_meta.account_owner`. What remains is engineering rather than a decision:
> `DATABASE_ROOT` is still `~/.scrapex`, one directory per operating-system user, so
> a per-account root is the next step — and enforcement waits for it, because
> refusing a warehouse claimed by someone else before there is anywhere else to go
> would lock him out of the only one there is.

> «كيف تتعامل الاداة مع الحسابات المختلفة يعنى انا لو عامل sign in بكذا حساب
> المفروض قاعدة البيانات تخص حساب واحد لا تخص الجميع لكل حساب قاعدة بيانات · وايضا
> اذا كنت مثبت الاداة على كذا كروم بروفيل بكذا حساب اى حساب مختلف له قاعدة خاصة به»

**Measured: there is no account concept anywhere.**

    DATABASE_ROOT = os.environ.get("SCRAPEX_DATA_ROOT", Path.home() / ".scrapex")

One database per **operating-system user**. A grep for `google_account`,
`user_email`, `signed_in` and `def account` returns nothing across `scrapex/`. So two
Google accounts on one Windows user share one database, and so do two Chrome profiles
with different accounts. The only isolation available is an environment variable,
which is a workaround rather than a design.

**`R-23` and `R-24` already point the right way** — a warehouse is per installation,
an empty one is the normal first-run state, and a database is upgraded rather than
replaced. A per-account root is that rule one level finer, and `carry_over` already
exists to move a warehouse forward rather than starting over.

**Blocked, deliberately, on `Q-14`: what identifies an account?** It decides where
other people's data lands, so it is not a default to be guessed.

---

## REQ-27 · A second source of a category reuses the first's machinery
**Captured 2026-08-21 · Done — `scrapex/directories.py`**

> **Built the same day.** A directory is now four facts and a partition in a
> registry — `key`, `display_name`, `base_url`, `dataset_key`,
> `identity_field`, `candidate`, `partition_factory` — and `--source` names it.
> The crawl itself is **inherited**: the provable partition, the sightings
> ledger, the resume and the approval-from-disk are untouched, because the
> engine was already protocol-shaped. A mistyped `--source` is **refused** and
> names what is known, rather than falling back to the only directory there is
> and collecting the wrong site for hours. Three guards, and 23 tests on the
> module.

> «علشان لما اديك مصدر لمقاولين تانى فى المستقبل منخترعش الذرة نكمل على الى موجود
> بالمثل كالمنتجات اعتقد انها مستقرة الى حد ما»

**And the wheel in question is the one shipped this morning.** `REQ-24` closed a real
gap — no user could run any crawl — and closed it by hardcoding the one site we have:

    BASE = "https://muqawil.org"      DATASET = "contractors"
    SITE_NAME = "Saudi Contractors Authority"     partition = MuqawilPartition()

A second contractor directory today would need a **copy of that file**. Stated
plainly because it is a defect introduced hours earlier, for a good reason, and it
must not survive contact with a second source.

**He is right that products are the shape to copy.** A products source is a contract
entry naming a `family`, and `build_connector(entry)` returns its collector — a second
Shopify shop needs no new module. The engine underneath is already protocol-shaped:
`partitioncrawl.PartitionedListing` is a `Protocol`, and its muqawil mentions are
docstrings citing where a number was measured, not code. So what is missing is the
**registry entry and the factory**, not the crawler.

**Open for him:** whether `ConnectorFamily` grows contractor families or the category
gets its own enum. Planned in [the platform plan](plans/2026-08-21-the-platform-not-a-price-tracker.md).

---

## REQ-28 · The Engine would not install, and showed a black screen
**Captured 2026-08-21 · Reported again 2026-08-22 · In flight — gate closed and
`engine-v0.3.0` published that same day; his confirmation that it installs remains**

> He downloaded the Engine, it did not install, he got a **BLACK SCREEN**, and he
> does not know how to install it. The panel read: *"ScrapeX Engine — Not detected —
> Available to install — The panel could not reach the Engine."*

**Recorded in English, and that is a departure from rule 2 below.** His own words
did not reach this session; writing an Arabic quote to satisfy the format would put
words in his mouth, which is the one thing this file exists to prevent. If he said
it in Arabic, that quote replaces the paragraph above.

**NOTHING WAS WRONG WITH HIS DOWNLOAD**, proved before anything else was touched.
Both copies he saved are **70,872,447 bytes** with sha256 `df7a00ee6a0d5360…`,
matching `ScrapeX/json/version.json` on the hub to the byte.

**The cause: the only installable engine is the build made BEFORE the fix for this
exact symptom.** `engine-v0.2.1` is commit `4386d25`; at that commit
`4386d25:packaging/engine_entry.py:62` reads `return serve()` for bare invocation
(today's line 62 is a comment), so a
double-click became the Chrome native messaging host, waiting on stdin for framed
JSON. `_first_run` landed six hours later at `7a067c5`, the unpack splash the next
day at `756fa39`, and **no release has been cut since**. `git tag` lists exactly one
engine tag. Reproduced on his machine, on his file:

    ./scrapex-engine.exe --version   ->  ScrapeX-Engine 0.2.1 (protocol 1)
    ./scrapex-engine.exe             ->  0 bytes, exit 0 (stdin closed)
    ./scrapex-engine.exe             ->  0 bytes, still alive at 20s (stdin open)

**And a second cause stands behind it, which the release will not fix.** His
warehouse is at schema **v8**; `main` ships engine migrations to **0006** and reads
v6, so `scrapex ui` exits 1 before binding a port. Both are recorded as `OP-32` and
`OP-33` in [BACKLOG.md](BACKLOG.md).

~~**What is his to decide:** whether to cut the release now.~~ **— HE DECIDED, AND
IT IS OUT.** *«اقطع الوسم»*, 2026-08-22, after reading the finding below. The tag
`engine-v0.3.0` sits on `451468d`, the release workflow completed in 28m36s, and the
manifest the panel reads was verified on the wire rather than inferred from a green
run:

    "version": "0.3.0"   "tag": "engine-v0.3.0"
    "published_at": "2026-08-22T13:17:13Z"
    "minimum_extension_version": "0.2.2"   protocol 1

It had said `0.2.1` since 9 August. **The gate that let `0.2.1` through is closed and
this is the first release to pass it** — the binary is now launched the way a person
launches it, with no arguments, and a build that prints nothing is refused. So the
engine he can install is, for the first time, one that carries `_first_run`.

**He reported it a second time on 2026-08-22** — *«المحرك الموجود على github 0.2.1»*,
with the panel reading `Latest version 0.2.1 · Available to install`. The finding is
the same one and no new defect stands behind it: the only engine tag in the
repository is still `engine-v0.2.1`. **What HAD gone stale is the number this entry
and five other places named.** `VERSION` reached **0.3.0** at #247 (2026-08-22), so
`engine-v0.2.2` would have been refused by the release workflow's first step —
`test "$tag" = "$version"`, before anything is built. Corrected above and
guarded by `tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py`;
the measurement is in `OP-32`.

~~**But `OP-37` has to go first.**~~ **— closed by #243.** `main` was red from 12:00Z
on 2026-08-21 for a reason unrelated to any of this, and the release workflow runs
the whole suite before it builds, so the tag would have failed before it reached the
compiler. That is no longer in the way: nothing now stands between the tag and the
release except pushing it.

---

## REQ-29 · An install surface that looks like a professional program, and an update anyone can apply
**Captured 2026-08-21 · In flight — ruled by [R-36](RULINGS.md#r-36--the-engine-updates-itself-the-panel-only-asks-and-a-published-sha-256-over-https-is-enough-to-trust-a-download), and being built**

> **IN FLIGHT the same day.** *«ابدأ بالمحدث داخل الـEngine وشريحة downloads»* —
> both are built. `scrapex/release.py` gives the engine its own reading of the
> release feed (the **third** reader of that one file, so a three-way guard holds
> it to `releases.js` and the workflow); `scrapex/update.py` fetches and
> **verifies** before anything is staged; `GET`/`POST /api/update` and
> `GET /api/update/plan` are the surface the panel asks through; and the panel now
> hands the first install to `chrome.downloads` with a live percentage and a
> **Show in folder**, instead of `window.open` and letting go.
>
> **What is NOT built, stated plainly: the swap.** Replacing a running `.exe`
> cannot be honestly tested without a frozen build, so `plan_swap` returns the
> plan as data — inspectable, logged, tested — and performs nothing. `OP-39`.
>
> **Ruled** before that. He answered the study below with «اوافق على اقتراحاتك
> وتوصياتك», and the four parts of what he approved are written out in `R-36` rather
> than left in the conversation. Build order: `OP-36` and `OP-35` first, because an
> Update button on top of them would report success and change nothing.

> «انا اريد واجهة التثبيت واجهة تشبه اى برنامج محترف واضحة بها كل ما يجب ان
> يظهر للمستخدم · لو حصل update يقدر يعمل update بسهولة»

**He said it in the same message that closed `OP-37`, and it is the direct
consequence of `REQ-28`:** he met the install surface as a black window, and what he
is asking for is that the surface exist at all as a product rather than as a
download link plus a hope.

**TWO REQUESTS, NOT ONE**, and they fail differently:

1. **The install surface** — what a person sees from "I want this" to "it is
   running", including every state that can go wrong on the way.
2. **The update** — a version already installed, a newer one published, and one
   press between them.

**Do not start from zero: a real amount of this exists and is measured below.**
Writing a second install surface beside it is the mistake `REQ-27` names —
*«منخترعش الذرة»*. What exists, and what it cannot do, is the study this request
needs before a line is written.

**MEASURED 2026-08-21, BEFORE ANY DESIGN — most of the *surface* exists; what is
missing is the *mechanics*.** The Engine detail screen already renders nineteen
elements. Counting them honestly is what stops this request becoming a second
install page beside the first:

| what a professional installer shows | in ScrapeX today |
|---|---|
| a state, in words, for every case | **built** — six: Checking / Running / Not running / Installed-not-running / Check timed out / Incompatible / Not detected |
| installed version vs latest published | **built** — `engine-installed-version`, `engine-latest-version` |
| a verdict | **built** — badge: *Available to install* / *Update available* / *Up to date* / *Update status unavailable* |
| an action whose label says what it will do | **built** — the button reads `Update to 1.0.2` when a version is installed |
| what it will refuse to talk to | **built** — `protocol_version` and `minimum_extension_version` are published beside the release and read *before* installing |
| release-feed polling that survives a CDN and a rate limit | **built** — `extension/releases.js`, minute-bucket cache key, own timeout, four named states |
| instructions, and the SmartScreen warning named in advance | **built** — and they auto-open on Download (`app.js:3621`) |
| diagnostics, a setup guide, copyable technical details | **built and wired** |
| **download progress** | **CANNOT BE BUILT AS IT STANDS** — see below |
| **verifying the checksum it displays** | **never checked — the SHA-256 on screen is decorative** — nothing compares anything to it |
| **handing the file over** ("here it is, press it") | **not built** — the user must find it in Downloads |
| **replacing a running engine in place** | **not built, and broken underneath** — `OP-36` |
| **not needing a window left open** | **not built** — `B6` (tray icon, log window), never started |
| **a signed binary** | **not built**, and only he can supply the certificate |

**THE ARCHITECTURAL FINDING, and it decides the whole design.** The panel is a
Chrome extension, and Chrome will not let an extension do the three things an
installer does:

    manifest.json permissions: activeTab, identity, nativeMessaging,
                               sidePanel, storage, tabs        <- no `downloads`

    download.onclick = () => { window.open(installer.url, "_blank"); }   app.js:3620

It hands a URL to the browser and lets go. It cannot show progress, it cannot read
the file off disk to hash it, and it can never launch a process. **So the panel can
never be the professional installer — not because nobody wrote it, but because the
sandbox forbids it.**

**The engine can.** It is a local process with a filesystem and a network stack. The
division that follows is the recommendation:

| | first install | every update after |
|---|---|---|
| **who does the work** | the browser — unavoidable, there is nothing installed yet | **the engine** |
| **what the panel does** | shows state, verdict, instructions; starts the download | shows state and verdict; **asks** the engine to update |
| **what is possible** | progress + reveal-in-folder, if `downloads` is added | download, **verify sha256**, swap, relaunch, report — all of it |

That inverts the obvious plan. "Make the install page better" buys a progress bar
and a Show-in-folder button. **"Let the engine update itself" buys the whole
professional experience, and it is the half that is not sandboxed.**

**THREE THINGS BLOCK THE SECOND HALF, and they are in order:**

1. **`OP-36`** — a frozen engine cannot restart itself today, so any *Update* button
   would lie. It has to be fixed first; there is no way around it.
2. **`OP-35`** — the shipped binary cannot even be asked `database-status`, so an
   updater that needs to talk to its own CLI has half a CLI.
3. **A ruling from him on what makes a download trustworthy.**
   `packaging/build_engine.py` already refuses to guess: *"shipping an updater that
   fetches and executes unsigned code would be worse than none."* The available
   chain is a `sha256` published in the manifest, fetched over HTTPS from
   `raw.githubusercontent.com`, checked before the swap — no certificate needed.
   Whether that is enough is his call, and the answer decides whether an updater
   can exist before code signing does.

**What is cheap and visible today, if he wants a first slice:** add the `downloads`
permission, replace `window.open` with `chrome.downloads.download()` plus
`chrome.downloads.show()`, and the first install becomes a progress bar and a file
handed over instead of a tab that opens somewhere. It does **not** solve the
checksum — an extension cannot read a downloaded file — so the honest options there
are to have the engine verify it after the fact, or to stop displaying a number
nothing checks.

**And one thing is already dead on that screen and should be named:**
`engine-power-switch` has no listener anywhere in `app.js`. Its own label says
*"Control is not connected yet."* A switch that does nothing is worse on a
professional surface than no switch.

**Open for him, and these are the questions the design turns on:**

- **Where does the surface live?** The panel's Engine page, the standalone
  onboarding page, or the engine's own window? Each is a different product.
- **What does "install" mean for a 60 MB unsigned one-file binary?** Today it is
  *"run the .exe and leave the window open"*, which is honest but is not what a
  professional program looks like. A tray icon and a service are `B6` in
  [STATE.md](STATE.md) and were never built.
- **Does an update replace a running engine?** `scrapex/relaunch.py` exists for
  exactly that and **is broken in the frozen build** (`OP-36`), so "update easily"
  has a defect underneath it that must be fixed first or the button will lie.
- **Code signing.** `packaging/build_engine.py` states plainly that it is not
  implemented and needs a certificate only he can hold. Every install will show
  SmartScreen's blue warning until it exists, and no UI can hide that.

---

## REQ-30 · The three-dots button appears twice on a source card
**Captured 2026-08-22 · In flight — cause proven, fixed and guarded; the PR is his to merge**

> «لماذا تظهر مرتين»

Sent with screenshots of the Data screen. He opened the `⋮` menu on the
`aramco.com` card and a **second `⋮` sat inside the open dropdown**, over the
*Recent changes* row.

**Nothing renders it twice.** It is the NEXT card's button painting through the
menu, and the cause is a stacking context rather than a z-index that is too small:
`.dataset-card > .split-button` carries `z-index: 1`, which makes each card's
wrapper a stacking context and spends the open menu's own `z-index: 120` inside
it. Every wrapper then ties at level 1 and document order hands the win to the
card below. Reproduced in the panel harness and measured — with the wrapper at 1
the following card's trigger is the topmost element at the centre of that row with
the menu at 120, at 1200 and at 2147483647.

**Fixed** by lifting the wrapper to `var(--z-overlay)` while its menu is open —
the layer `.sx-select-list`, `.account-menu` and `.finance-converter-options`
already use on this screen. Guarded by
`test_panel_dom.py::test_an_open_source_menu_is_not_overpainted_by_the_next_cards_button`,
which hit-tests what is in front rather than reading a number back, and refuses to
pass if no button lies under the menu at all.

**The same screenshots showed a second thing he did not ask about:** the two
`muqawil.org` cards carry no `⋮` at all. That is a different cause and a
deliberate one — `sourceMenu` hides the whole menu for a generic dataset — but it
is now over-broad by one entry. Recorded as `OP-42` in
[BACKLOG.md](BACKLOG.md#op-42--a-generic-dataset-card-offers-no-actions-at-all-and-one-of-the-six-would-work),
not folded into this fix, because it changes what the panel offers rather than
where it paints.

---

## Adding a request

1. Give it the next `REQ-nn`. Never reuse a number.
2. Quote **his own words**, in the language he used them.
3. Set the state to **Captured**, add a row to the board.
4. Commit it in the session it was said — not later.

When it advances, move the state, add the link the new state produces (a ruling,
a plan, a PR), and say so in [STATE.md](STATE.md) if it is live work.

---

## REQ-31 · Start the profile parser — and the pages are not consistent
**Captured 2026-08-22 · In flight — the cards are built, guarded and mutation-tested; two questions are his**

> «ابدأ القارئ»

and then, in the middle of the measurement, the sentence that changed the design:

> «contractor-tabs — المعلومات غير ثابته ولا متفقثة بين الصفح يعنى ممكن تلاقى معلومات
> تانية وطريقة عرض مختلفة»

*The information is neither fixed nor consistent between pages — you may find other
information and a different presentation.*

**He was right, and four written premises in this repository were wrong.** Everything
believed about the muqawil profile page came from **two committed fixtures**, which are
one contractor. `R-19` had labelled that limit honestly; the conclusions outlived the
label. Re-measured over **2,419 real profile pairs** read read-only out of the running
crawl — the full account is in `OP-43` and [LESSONS.md](LESSONS.md) §11.

**The page publishes seven cards. Three had no reader at all**, and one of the three is
a **price**: the card titled `العقود سعر البناء (برنامج البناء الذاتي)` carries a
self-build price per square metre in three award tiers, and no document here had named
it. It was invisible because a regex that chunked "from `id=contractor-tab4` until the
next tab id" ran past an empty pane and attributed the table to a tab that holds **zero
tables on 2,360 of 2,360 pages**.

**Built, in the same session he asked:** six new columns — `commercial_registration`
(2,542 of 2,543 pages, ten digits, no two contractors sharing one), the three
self-build price tiers, and the two contract counts — taking the profile row from 21
fields to 27, which `R-31` makes an additive schema upgrade rather than a migration.
And `licensed_activities` is wired as a **second taxonomy**, in its own scheme: 1,685
rows over 228 pages from a closed vocabulary of 22 activities.

**His warning is now mechanical rather than remembered.** `PROFILE_CARDS` declares all
seven cards and `undeclared_cards()` reports any data-carrying card that is not among
them, so the next section the site grows is something a test says out loud. Twenty-five
guards, and **seven of seven mutations killed** — including the one that matters most,
that reading the price rows by position instead of by label goes red.

**What is left is his:** `Q-17` (the readiness level, empty on 1,490 of 1,500 rows, and
the three activities whose English the site itself publishes wrongly) and `Q-18` (do the
two contractor-relation groups still get tables at 2 rows in 2,419 pages).

---

## REQ-32 · Fixed columns, and everything else in the row's own card
**Captured 2026-08-22 · Ruled ([R-45](RULINGS.md#r-45--the-site-is-the-only-source-of-truth-and-a-field-the-table-does-not-need-goes-in-the-rows-card)) · Not built**

> «فى كاتوجرى المنتجات كنا مثبتين اعمدة محددة فى الجدول واى معلومة زيادة عند الضغط على
> الصف يظهر كارد تحتها ونضع فيه المعلومة · نفس الشى اريده فى كاتوجرى المقاولون · لان
> المقاولون سيكون هناك عدة مصادر له فى المستقبل · الفائدة اى ان معلومة مثل مستوى
> الجاهزيّة لا داعى لوضعها فى عمود خاص فى الجدول ولكن عند الضغط على صف معين وهو يحملها
> تظهر فى الكارد الخاص بالمقاول»

He said this answering `Q-17`, which had offered him a migration or nothing. He refused
both framings: the field is **stored** and it is simply not a **column**.

**HIS REASON IS ABOUT THE FUTURE, NOT ABOUT THIS FIELD.** `المقاولون` is a category and
it will have several sources — Balady, the UAE registries, the Gulf and Egypt sources
queued in [STATE.md](STATE.md) Track 5. A column is a promise every source in the
category must keep, so a table whose columns are the union of every source's extras
grows a column per source and a NULL per row. That is measured, not hypothetical: on the
products side madar reached **59 variation axes, 33 of them non-empty on under 1% of
rows**, and he asked three times to have them moved.

**AND HE REMEMBERS THIS AS BUILT. It is half built, and not the half he needs.** Measured
2026-08-22 across `extension/` and `scrapex/webui/`:

| piece | state |
|---|---|
| a per-row card under a clicked row | **does not exist on either surface** — no `rowFormatter`, no expansion handler |
| which fields are columns, for PRODUCTS | **built** — `/api/promotable/{source_key}`, `fields.promotable_attributes` / `set_promotion`, over `source_product_attribute` |
| which fields are columns, for DATASETS | **not built**; `field_definition` is where it belongs |
| the grid both surfaces ship | **Tabulator** — row expansion is a native feature, so this is a feature to use rather than a library to add |
| the contractors' extras themselves | **already stored** in `generic_record.data_json`; nothing needs re-crawling |

So the products category has the fixed-columns half and no card; the contractors category
has neither half and its data is already on disk.

**What it will take, in the order the dependencies fall:**

1. **A row card for a DATASET table** — Tabulator's row expansion, rendering every field
   the row carries that is not a visible column. This is the piece he actually asked for
   and it unblocks nothing else, so it can go first.
2. **Column visibility for datasets** — the `field_definition` equivalent of
   `set_promotion`, so *which* fields are columns becomes his choice rather than the
   parser's declaration order.
3. **The same card for the products category**, which already has step 2.
4. **The readiness level** — one value in that card. It stops being a schema question the
   moment the card exists, which is why `Q-17` is closed rather than deferred.

**Not started.** `REQ-31` (the profile parser) is what is in flight, and this is the
surface it feeds.

**CORRECTED 2026-08-22, same day — and the correction is that HE WAS RIGHT.** Kept per
**C4**, because what was wrong here is more useful than what is right.

The table above says a per-row card exists on **neither** surface. **It has shipped on
the engine since 2026-07-22** — 967 lines, opened by row **selection** rather than by
`rowFormatter`, with an image gallery, AR/EN pairing, a price timeline and a *"Moved out
of the table"* card that `scrapex/reports.py` builds under a comment reading *"the
owner's ask, using the mechanism that already exists."*

So the line *"he remembers this as built. It is half built, and not the half he needs"*
is wrong twice. It is **fully built for products**, and he was not half-remembering
anything — he said «نفس الشى اريده فى كاتوجرى المقاولون» and meant exactly that: the
contractors category does not have it. **Step 3 below was already done before this entry
was written.**

**The measurement failed by searching for one symbol** — `rowFormatter`, `row-detail`,
`expandRow`, `detailsDrawer` — and finding none. See
[R-45](RULINGS.md#r-45--the-site-is-the-only-source-of-truth-and-a-field-the-table-does-not-need-goes-in-the-rows-card)
for the full correction and for the two things it turned out to be worse than assumed:
the chooser has registered **11 price-path keys** against the `contractors` dataset, and
`dataset_table_payload` never reads `dataset_field` at all, so every hide and rename on a
dataset is a silent no-op.

**And this entry is now the same work as [REQ-07](#req-07--the-data-page-must-carry-everything-the-engines-page-carries)'s
"details drawer"** — asked for independently, in his own words, two weeks apart. The
session on `REQ-07` is writing one plan covering both, on his instruction: «ضع خطة
لتنفيذها كلها وتتبع التنفيذ حتى لا نفقده».

---

## REQ-33 · The dataset cards said no successful crawl over crawled rows
**Captured 2026-08-22 · Done — the date is derived from the evidence; the two registries stay his**

> He reported it from the extension's source list. The two muqawil datasets read
> `17,304 products` / *"no successful crawl yet"* and `704 products` / *"no
> successful crawl yet"*, while `aramco.com` and `spark-eshop.com` beside them read
> *"Last crawled 16 August 2026, 8:00 AM — Africa/Cairo · N rows seen"*.
> **17,304 rows plainly did come from a crawl.**

**Recorded in English, the same departure `REQ-28` documents.** His own words did not
reach this session, and writing an Arabic quote to satisfy rule 2 below would put
words in his mouth — the one thing this file exists to prevent. If he said it in
Arabic, that quote replaces the paragraph above.

**The cause was not the missing `crawl_run` row**, which is the finding that decided
the fix. `_dataset_rows` handed the panel `"last_success": None` as a literal, and
`freshnessLine` prints that sentence for a missing key — so giving muqawil a
`crawl_run` row would have changed nothing on his screen. It could not honestly be
written either: `crawl_run.source_id` is NOT NULL into `source_site`, muqawil is in
`site_profile`, and that split is [REQ-25](#req-25--one-source-registry-with-a-category-visible-to-every-user)'s
to settle.

**So the date is read off the evidence the crawl already stored** —
`max(generic_page_snapshot.captured_at)` over the pages `generic_ingestion` says the
dataset was built from. Nothing new is recorded, and
[`GENERIC-FETCH-SEAM.md`](GENERIC-FETCH-SEAM.md) had already asked for exactly that:
*"It may be enough to ask `generic_ingestion`; check before adding a column."*

**What this did NOT do, and it is his:** merge the two registries. A dataset still
has no run ledger of its own, and whether a generic crawl belongs in the price job
queue is still the open question at the foot of that document. The measurement, the
four findings it produced and the mutation results are in
[BACKLOG.md](BACKLOG.md) as `OP-44`.
## REQ-35 · The card must say the engine is running from source, not that it is missing
**Captured 2026-08-22 · In flight — partly built**

> «المحرك يعمل الان عن طريقك ويتجدد باستمرار لاننا نطوره · انا عاوز طريقة توضح فى الكارد
> ان المحرك غير مثبت على الجهاز ولكنه يعمل فى نظام developer · ويظهر المحرك يعمل»

The engine on his machine is not an installed build. It is started from this
checkout and it changes several times a day because that is what we are doing to
it. The panel has no word for that state, so it uses the word for the other one:

    Installed version   Not detected
    Protocol            Not available

Both are literally true — nothing is installed — and both read as **broken**, which
is the second time this month the panel has told him the engine was absent while it
was serving. The first was `/api/health` taking 3.8 s against a 2,500 ms deadline
(`R-45`'s sibling, fixed in #251); this one is not a bug at all. It is a state the
product has no vocabulary for.

**THE ENGINE ALREADY KNOWS AND HAS NEVER BEEN ASKED.** The frozen build enters
through `packaging/engine_entry.py`, which `cli.py`'s own `--version` comment says
*"cannot reach this parser at all"* — so the two ways of starting it are already
distinct in the code. What is missing is that neither says so on the wire: nothing
in `/api/health` reports **how** this engine is running.

**So the shape is: the engine reports its own run mode, and the panel has a third
word.** Not the panel guessing from an empty version string, which is what it does
now (`extension/app.js:3526` on empty `state.engineVersion`) — a guess is how
"running from source" became "not detected" in the first place.

**And it is not cosmetic.** He works from two machines and the update path is real:
`REQ-28`/`OP-32` exist because the engine he *downloaded* was behind the source, and
a panel that cannot tell "installed 0.2.1" from "source 0.3.0" cannot help him see
which one he is looking at. A developer-mode engine must also never be offered an
update that would overwrite his checkout.

**Blocked on nothing.** It is one field on an endpoint the panel already polls, plus
the words on the card.

**THE FIELD IS BUILT; THE WORDS ARE HALF BUILT. And the cause named above is wrong —
kept rather than erased, per `C4`, because the mistake is instructive.** Measured
2026-08-23 against the live engine on port 8000:

| asked | answer |
|---|---|
| `GET /api/health` version | **`"0.3.1"`** — not empty, and never was |
| how long it took | **486 ms**, against a 2,500 ms deadline |
| top-level keys | **11**, and **none states how the engine was started** |

So the paragraph above is right that the panel has no word for developer mode, right
that the engine knows and is never asked, and **wrong about the mechanism**. The panel
is not guessing from an empty version string the engine sent. `state.engineVersion` is
empty because **no answer has arrived yet**: `setEngineChecking()` renders the spec
rows before the request returns, so *Installed version — Not detected* appears during
**every check window on a perfectly healthy engine**, then is overwritten ~half a
second later. That is a render-ordering defect and it is **not fixed** by the
provenance work.

**What was built** (`scrapex/provenance.py`, `LESSONS` §14): `/api/health` now carries a
`build` block stating `mode` — `source` or `frozen` — with the commit the process
started on, and the panel renders it as a **Build** row under *Installed version*. So
"running from source" now has a word, which is the request's substance. **What is
not:** the words *Not detected* still flash during the check window, because that
sentence is written before any answer exists to render. **Partly closed, and the
remaining half is a two-line guard on the render, not a new field.**

---

## REQ-36 · The three dots are missing on a contractor card, and unprofessional on the others
**Captured 2026-08-22 · In flight**

> «ال 3 نقاط لا تظهر فى كارد مقاول»
>
> «توجد ال3 نقاط بشكل غير احترافى فوق الكارت وداخل مربع اعتقد ان ال3 نقاط معمولة فى صفحة
> profile بشكل احترافى عن هذا الشكل»

Sent with a screenshot of the Data screen after he reloaded the extension and confirmed
#252's fix had worked — the duplicated `⋮` is gone. These are what remained.

**FILED LATE, AND THAT IS THE POINT OF `C7`.** He said both of these hours before this
entry existed. They were briefed to a session and acted on immediately, and **a
delegation is not a record**: nothing on the board carried them, so nothing but one
agent's context knew they had been asked for. `test_every_finding_that_quotes_him_is_reachable_from_the_request_board`
is what caught it — a *different* session quoted him in a `BACKLOG` entry and the guard
refused it, because a finding may quote him only where a request of his exists to
answer. The guard found my omission, not that session's.

`REQ-04` is why this rule exists: ruled, unbuilt, and out of sight for sixteen days.

**One · no menu at all on a dataset card.** `sourceMenu` returns `""` for
`kind === "dataset"` (`extension/app.js`), and its comment justifies it — every action
posts to a manifest-backed route and a dataset is not in the manifest, so *"a button that
cannot work is worse than no button."* Right for five of six. **Wrong for the sixth:**
`/api/table/{key}` resolves the dataset catalogue first, so *Open the data table* works
today. Measured: `contractors` and `contractor_profiles` render **0** triggers,
`LONG_AR`/`SHORT` render 1 each. Already recorded as `OP-42`, which is now his ask.

**Two · the trigger's treatment.** `.dataset-card > .split-button` is absolutely
positioned in the card's corner (`extension/app.css`), and he reads the result as a
filled box crowding the card's edge. He is comparing it against something he calls the
profile page, and **which** control that is has to be measured rather than guessed —
the panel and the engine UI ship several overflow triggers (the shared split button,
`.account-menu`, `.sx-select-list`, `.source-filter-menu`), each with its own size,
padding and open state. The session on it is enumerating them, naming the one he means,
and bringing the card's trigger to that treatment in **card-local rules only**:
`design/components.css` generates the shared copy that five surfaces consume, and
`OP-47` already records that fixing consumers instead of the component is how this class
of defect spreads.

**Verified visually, not by reading CSS back**, in both themes — the panel renders light
and dark, and a trigger that reads well on one ground often does not on the other.

---

## REQ-37 · One card per site, and its crawls are options under it — the way GPP does it
**Captured 2026-08-22 · Ruled ([R-47](RULINGS.md#r-47--muqawil-is-one-card-with-two-crawls-and-the-two-stored-datasets-stay-two)) · In flight 2026-08-23 — the card is one, the crawl options are not**

> «المفروض مصدر مقاول يظهر مرة واحدة فقط واختيارات الزحف الخاصة به تكون متعغددة · انظر
> الى gpp لتفهم كيف تم عمل هذا»

Sent with a screenshot of two cards that are both `muqawil.org`:

```
muqawil.org   Saudi Contractors Authority   contractors          [Row 17,304]
muqawil.org   Contractor profiles           contractor_profiles  [Row 704]
```

**THE CAUSE IS ONE CLAUSE, and it is not a display bug.** `_dataset_rows` in
`scrapex/webui/app.py` ends its query with `GROUP BY d.dataset_definition_id` — **one row
per dataset**, keyed on `dataset_key` as its `source_key`. The panel draws a card per row,
so two datasets under one site are two cards, and neither knows the other exists.

**AND HIS COMPARISON IS EXACT, which is why he made it.** `GPP_ENERGY` is **one**
`source_key` in `sources.yaml`, and everything that varies underneath it — four energy
types across 169 countries — lives *inside the connector*, never as a second source. So
the panel has always drawn GPP as one card. muqawil's multiplicity was modelled one level
higher, as two `dataset_definition` rows, and the listing has no notion of a site above
them.

**The shapes differ in a way that matters, and the fix is not "copy GPP".** GPP's axes
are one crawl producing many rows; muqawil's are **two different crawls** — the listing
sweep (`--crawl`, a 56-cell partition) and the profile sweep (`--details`, 34,834 pages) —
which run separately, resume separately, and are approved separately. So the card must
carry *two crawls*, not two column-sets. That is what he means by «اختيارات الزحف الخاصة
به تكون متعددة».

### What this needs, and the coupling that decides its order

1. **`_dataset_rows` groups by `site_profile_id`**, emitting one row carrying its datasets
   rather than one row per dataset. The `site_profile` row already holds the display
   identity — which is why the first card reads `Saudi Contractors Authority` (the site's
   name) and the second reads `Contractor profiles` (the dataset's).
2. **A card-level identity that is a SITE.** Today `source_key` on a dataset row *is* the
   `dataset_key`, and `/api/table/{key}` and `/source/{key}` resolve on it. A site-level
   card needs its actions to say **which dataset**, or those routes break.
3. **So this is the same surface as `REQ-36`.** That request gives a dataset card the
   `⋮` menu it can use; this one asks the menu to offer *per-dataset* actions under one
   card. Building them apart would mean writing the menu twice.

**Therefore it lands after `REQ-36`**, and this is a sequencing decision rather than a
priority one: the branch `fix/a-dataset-card-gets-the-menu-it-can-use` is editing
`extension/app.js`'s `sourceMenu` right now, and two sessions in that function is the
collision `docs/ORCHESTRATION.md` §3 exists to prevent.

**ANSWERED THE SAME DAY — «زحفين لمجموعة واحدة».** Two crawls of one dataset. Recorded
as [R-47](RULINGS.md#r-47--muqawil-is-one-card-with-two-crawls-and-the-two-stored-datasets-stay-two),
which also records the half he did not have to decide because the code already had:
**the two `dataset_definition` rows stay two.** `contractors._approval` refuses to put a
27-field profile and a 28-field listing under one approved schema, because a subset is
what a broken parser looks like (`R-31`) — so it is one CARD over two datasets, joined by
the relationship he already had confirmed. And the second number stops being a population:
704 of 17,304 is **coverage**, which is what `--coverage` already computes.

### BUILT 2026-08-23 — points 1 and 2 of three, and the third cannot ship yet

**HE ASKED FOR THIS ON 2026-08-22 AND HE GOT HIS ANSWER THE SAME DAY. It was still
not built on 2026-08-23**, which is why he asked «حل المشكلة لم يصل لى ما السبب ؟» — the
fix has not reached me, why? Measured before starting: **no file under `extension/`,
`scrapex/` or `tests/` cited `R-47` or `REQ-37` at all.** Ruled, recorded, and never
carried into code. That gap — a ruling with no line of code behind it — is the whole
answer to his question, and it is the failure `C7` and `REQ-04` exist to catch.

**What landed**

1. **One card per site.** `_dataset_listing` in `scrapex/webui/app.py` folds a
   confirmed one-to-one child dataset into its parent for `/api/sources`. `muqawil.org`
   is listed once. «المفروض مصدر مقاول يظهر مرة واحدة فقط» — done.
2. **The population once, the second crawl as coverage.** The card reads
   `Contractor profiles: 704 of 17,304 (4.1%)` where it used to read a second
   population — and, on the way, stopped reading `17,304 products` over a directory
   ([`OP-63`](BACKLOG.md)).

**What did not, and it is blocked rather than skipped: «اختيارات الزحف».** `R-47`'s
third point is two crawl OPTIONS on the card. **There is no panel path to a dataset
crawl at all.** `POST /api/jobs` answers `404 unknown source_key 'contractors'` —
measured, and already recorded as [`OP-52`](BACKLOG.md); `REQ-24` shipped
`scrapex contractors` as a CLI command and says the panel path is still missing. Adding
two menu entries now would put two buttons on his card that answer 404, which is the
rule #258 built a guard for: *a button that cannot work is worse than no button.* So
**this request stays In flight until a dataset crawl can be started from the panel**,
and closing it before then would be the `REQ-04` failure wearing a green tick.

### THE FOLD KEYS ON THE RELATIONSHIP, NOT ON THE SITE — and measuring said so

Point 1 above names `site_profile_id`. Measured read-only on his warehouse 2026-08-23,
that is true and **insufficient**, and `base_url` — the obvious shortcut — is wrong:

| | |
|---|---|
| `dataset_definition` | `contractors` and `contractor_profiles`, **both `site_profile_id = 2`** |
| `dataset_relationship` | parent `contractors`, child `contractor_profiles`, `one_to_one`, **`confirmed`** |
| active rows | 17,304 and 704 |
| `site_profile` | **TWO muqawil rows** — id 1 `https://muqawil.org/ar/contractors`, id 2 `https://muqawil.org/`. Same host, different `base_url`; grouping on the URL works today only because id 1 carries no datasets |

So the key is the site **plus a confirmed one-to-one relationship**, which is `R-47`'s
own justification — *"the join is the thing that makes the single card honest rather
than a label over two unrelated tables"* — rather than a caution added on top of it.
Two datasets that merely share a site are two populations, and one card over them
would state a number nobody could act on.

### AND HIS GPP COMPARISON HAS NO PRESENTATION TO COPY, which is worth stating plainly

He said «انظر الى gpp لتفهم كيف تم عمل هذا». Measured: **`grep -rin gpp extension/`
returns nothing.** There is no GPP branch, no GPP card, no split-button, no accordion
and no picker anywhere in the panel. `GPP_ENERGY` is one `source_key` in `sources.yaml`
and its five energy types live in a dict inside `scrapex/connectors/gpp.py`, so the
panel has always drawn it as one card *without knowing it was one card*.

**The GPP pattern is therefore "collapse below the surface", and it is the right
lesson even though it does not transfer as a control**, which is what this request and
`R-47` both already say: GPP's axes are one crawl producing many rows, muqawil's are
two crawls. So the multiplicity that could be hidden was hidden — the listing is one
row per site — and the multiplicity that cannot be (two separately-run, separately-
resumed, separately-approved crawls) is left for the `⋮` menu `REQ-36` built, rather
than given a second vocabulary of its own. That is Decision 26 of `PLATFORM-PLAN.md`
applied: no second implementation of an existing one.

---

## REQ-38 · The backup must check its own digest, and the panel must be able to finish the build
**Captured 2026-08-22 · Not built**

> «ضع طلب بتصليح هذا العيب … اتوماتكيا فى المستقبل»

He said it after being shown that the first real backup of his warehouse had to be built
with `curl --max-time 3600` and its digest compared **by hand**. He is right that a
safeguard a person has to remember is not a safeguard.

### The three defects, measured 2026-08-22 on a 1.18 GB warehouse

**1 · THE DIGEST IS WRITTEN AND NEVER READ.** `extension/drive.js` puts `sha256` into
`latest.json` on upload and nothing on `main` ever compares it again — the download path
checks a **byte count** and nothing else. A file that arrived complete and corrupt passes.
Two bytes swapped inside a 309 MB zip is exactly the failure the digest is for, and it is
the one case the byte count cannot see.

**2 · THE PANEL'S BUTTON CANNOT FINISH, AND FAILS DESTRUCTIVELY.**
`extension/app.js` sends `POST /api/bundle` with **no `deadlineMs`**, so it matches no
policy in `extension/startup.js` and takes the `localMutation` default of **10,000 ms**.
The build measured **73 seconds** on this machine and would be minutes on a slower disk —
so the client aborts, always.

**And the abort does not stop the engine**: `/api/bundle`'s handler is a synchronous `def`
running in a threadpool, so it keeps going and writes the whole archive. Measured today:
a **309,589,440-byte** zip plus a **4,386,341-byte** panel pack that **nothing ever
deletes** — `scrapex/storage.py` prunes `scrapex-engine.*backup*` and these are named
`scrapex-bundle-*`. So every press of a button that cannot succeed leaves 314 MB behind on
a disk that is 95% full, and reports failure.

**3 · THE SIZE FIGURES IN THE CODE ARE STALE BY TEN TIMES.** `scrapex/bundle.py`,
`scrapex/webui/app.py`, `extension/drive.js` and `scrapex/backupschedule.py` all describe
this archive as **33–40 MB**. It is **309 MB**. Every one of those numbers was written
when the warehouse was 112 MB, and one of them is inside the very docstring that explains
why the upload had to become resumable.

### What "automatically" has to mean here

- **The engine hashes the archive it just wrote and the reply carries it** — it already
  does this correctly, which is why the hand-check succeeded: `aabf5c26…` matched, first
  time, on both files. The gap is entirely on the *reading* side.
- **The download verifies the digest before anything is allowed to use the file**, and
  says which evidence it had — Drive's own `sha256Checksum`, a local re-hash, or none.
  Reporting *"verified by size only"* is honest; treating an absent digest as a pass is
  not.
- **The button gets a deadline that fits the work**, or the route stops being
  synchronous. A 10-second clock on a job that measured 73 seconds is not a timeout, it
  is a guarantee of failure.
- **A build that is abandoned cleans up after itself**, or the pruner learns the name it
  actually writes. Two hundred failed presses is 63 GB of orphans on a full disk.
- **The stale numbers get a guard**, not a correction: a comment saying 40 MB will be
  wrong again the next time the warehouse doubles, and this class has already cost a red
  `main` today through a different register.

### What exists to build on, so this is not a rewrite

`claude/drive-without-a-server` (`e00711d`, pushed, no PR) already adds `PRAGMA
quick_check` before a bundle is written and a `files.get` that compares Drive's own
`sha256Checksum` against the manifest, reporting which evidence it had. **It does not fix
the deadline** — `git show` on that commit touches none of `extension/startup.js`,
`extension/backend.js`, or the call site. So the branch closes defect 1 and leaves defects
2 and 3 open, and merging it does not make the button work.

**Filed while the workaround is still fresh**, which is the point: the manual procedure
that produced tonight's backup is written down in the same session, so this request can be
measured against something that actually ran rather than against a description of it.

---

## REQ-39 · The extension must report what Drive holds, because nothing else can ask
**Captured 2026-08-22 · Not built**

> «اذن يجب ان نجعل الاضافة تخبرنا بحالة الرفع · امال هنتاكد ونتابع ازاى»

He said it after being told that the session could verify the local bundle completely —
73 files CRC-checked, both digests matched — and could **not** confirm the upload, because
Drive authentication lives in the extension (`chrome.identity`) and no session is going
into his account.

**He is right, and the gap is larger than tonight's verification.**

### The measurement

`extension/drive.js` is the only holder of a Drive token in the product. Measured on
`main`: the panel's Drive surface calls `renderDriveFacts` with `state: "error"` and a
failure detail — and there is **no success state carrying what Drive actually contains.**
No file listing, no size, no digest, no time of the last upload that worked.

**And the knowledge does not leave the panel.** Nothing writes it anywhere. So closing the
side panel closes the only window onto Drive, and nothing in the repository, the
warehouse, or the CLI can answer *"is the backup there?"*

### Why that contradicts a ruling of his own

`R-43` makes **Drive the source of truth for DATA** and the repository the source of truth
for CODE. A source of truth nobody can query is not a source of truth. Today the honest
description is: the backup exists in a place only one browser tab can see, and only while
it is open.

It also makes `REQ-38` unobservable. That request asks for the digest to be verified
automatically — but **a verification whose result is not recorded cannot be trusted or
audited**, only re-run. The two requests are halves of one thing: *check it by machine*,
and *say what the machine found, durably.*

### The channel already exists and has never been used this way

The panel already talks to the engine over `127.0.0.1:8000` on every poll. So:

1. **The panel asks Drive**, which only it can do: the backup folder's listing with
   `id, name, size, createdTime, sha256Checksum` — the same `files.get` fields the
   unmerged branch `claude/drive-without-a-server` already added for its own check.
2. **It compares** each file against the local manifest the engine produced, and forms a
   verdict per file: verified by digest, verified by size only, mismatched, or absent.
3. **It reports the verdict to the engine**, which stores it — so the state is durable and
   readable with the panel closed.
4. **`scrapex drive-status` prints it**, the way `database-status` prints the warehouse's.

**The evidence, not the conclusion.** The stored record must say *which* evidence it had —
Drive's own `sha256Checksum`, a size match, or nothing — because on `main` today the
download path compares a byte count and an absent digest is treated as a pass. A status
line reading *"verified by size only"* is useful; one reading *"verified"* when nothing was
compared is worse than silence.

**And it must be honest about staleness.** What the panel last saw is not what Drive holds
now — another machine may have uploaded since. So the record carries the time it was taken
and the CLI says so, rather than presenting a remembered answer as a current one. That is
the same rule this repository learned four times today about measurements and their bases.

### What it buys, concretely

- **Tonight's question answered by a command** instead of by reading a size in a browser.
- **Multi-device tracking at all**, which is what he asked for originally: «حتى استطيع
  الوصول اليها من عدة اجهزة». Two machines can only coordinate through a state both can
  read, and right now neither can read anything.
- **A pruning decision that can be reviewed.** `extension/drive.js` keeps three files and
  deletes the rest with `files.delete`, which **bypasses the trash** — and it chooses by
  Drive's own `createdTime`, not by anything it verified. A recorded listing makes that
  reviewable before it is destructive rather than after.

### The workaround, until it is built

The two numbers to compare by hand in Drive's file details, for the backup of
2026-08-22 — recorded here because a workaround that is not written down is a workaround
that gets misremembered:

| file | bytes | sha256 |
|---|---|---|
| `scrapex-bundle-20260822-153242.zip` | **309,589,440** | `aabf5c2678218cf82d60d6e42b86e8f7c9e46305d8c8ee045466e8e844c555e7` |
| `scrapex-bundle-20260822-153242-panel.jsonl.gz` | **4,386,341** | `fa58ea4bf5022a19bcb86df6ac35f429bbea0c37c3e3279c7ead123e4db28ff6` |

A browser upload does not leave a truncated file — it either completes at full size or
fails and leaves nothing — so a size match is sufficient evidence that it finished.

---

## REQ-40 · The extension is the phone and the engines are apps installed on it
**Captured 2026-08-23 · Study in flight**

> «دور المحرك يجب ان يتقلص امام extension ازاى بما ان المحرك بيحفظ البيانات فى قاعدة sql
> اذا وجوده سواء مثبت او لا يعمل او لا لا يوقفنا على قراءة وتصفح البيانات · ولهاذا اصلا يتم
> نقل صفحة الداتا من المحرك الى الاداة · ايضا قد ناقشت مسبقا كل مهام المحرك وبعد دراسة تم
> تحديد ما سيبقى مع المحرك وما سيذهب الى الاداة وبم ان ربما تم فقد جزء من هذه المناقشة ولم
> تسجل اريد عمل دراسة بحيث تظل الextension هى الكل فى الكل تعتبر هى موبيل والمحركات تعتبر
> applications عليها مثبته او لا ربما تزيد apps مستقبلا»

**Five things, and only the last one is new work. The other four are him telling us the
model we have been building against was never written down completely.**

1. **The engine's role must shrink**, and he asks *how* rather than *whether*.
2. **His premise:** the engine stores the data in a SQL database, so whether the engine is
   installed, and whether it is running, must not stop him **reading and browsing** that
   data.
3. **That premise is the reason for a port already in flight** — «ولهاذا اصلا يتم نقل صفحة
   الداتا» — which is `REQ-07` / `DEC-8`. So the port is not a tidy-up. It is the first
   instalment of this request, and it was being built without its own justification
   written beside it.
4. **He remembers a prior study** that decided what stays with the engine and what moves,
   and he suspects part of it «لم تسجل» — was never recorded. This is a `C3`/`C7` question
   about our own filing, and it is the reason the study has a lens pointed at git history
   and closed pull requests rather than only at documents.
5. **The model he wants, stated as an analogy:** the extension is **the phone** — «هى الكل
   فى الكل» — and the engines are **applications installed on it, installed or not**, with
   **more apps expected later**.

### Why the analogy is load-bearing and not decoration

A phone does not stop being a phone when an app is uninstalled. It keeps its home screen,
its settings, its files, and it can still tell you what it has. **Everything he asked for
follows mechanically from that one sentence**, which is why it is quoted rather than
paraphrased: the data page moves because a phone can open its own files; the engine becomes
*an* app rather than *the* app because a phone has an app list; and «ربما تزيد apps
مستقبلا» means the seam has to admit a second one before there is a second one to admit.

### CORRECTED — his premise is HALF BUILT, and no document says so

**What this section said first was wrong, and it is left visible rather than rewritten
away.** It claimed Decision 25 was a built-in contradiction of his requirement. Twelve
agents measured the question and **nine independent refuters overturned that**, three of
them on this exact point. The corrected finding is better news than the error was, and it
changes the request from *build this* to **finish and re-document this**.

**THE DATA PAGE ALREADY READS HIS DATA WITH NO ENGINE. It has since 2026-08-12.**
`extension/app.js:4414-4429` is the `catch` around `loadDatasets`, and its own comment says
what it is for:

> *"NOT A DEAD END ANY MORE. This is the machine with no engine on it — the case the whole
> bundle format was designed for — and until now the panel said "couldn't reach the engine"
> and stopped, while a complete copy of the owner's data sat in their Drive."*

It offers a **Read my Drive backup** button wired to `browseFromDrive` (`app.js:4440`), which
reaches `fetchPanelPack` (`extension/drive.js:508`) and `readPanelPack`
(`extension/bundleview.js:28`). Landed in `fc8525f`, *"Carry the panel pack beside the
archive, and let the Data page read it"* (#167), **2026-08-12 09:18** — the same week
`MIGRATION-PLAN.md` recorded the division of labour this request is about.

**So Decision 25 is stale TEXT, not a built contradiction, and the distinction matters.**
The rail's boundary IS built and IS guarded: `.rail-tablist` at `extension/app.css:1144`
with its reason at `:1137-1143`, asserted green at `4522158` by
`test_the_rail_groups_say_which_pages_need_an_engine` and
`test_finance_tab_sits_immediately_above_workspace` (`tests/test_panel_dom.py:3358` and
`:1291`). What is false is only Decision 25's **consequence sentence** — *"The second group
is dead on a device with no engine installed"* — and it is false for **exactly one** of the
four pages it covers. Source, Run and Google Finance have no offline route; **Data does.**
That is a `C2` documentation-drift defect, one sentence wide.

### The three measured holes, which are the whole of what he loses today

Not "the data page has not moved". Three specific, countable gaps:

| hole | measured |
|---|---|
| **The pack carries no contractors at all** | `scrapex/bundle.py:140` sources the bundle from `list_sources`, which is `SELECT source_key FROM source_site` (`scrapex/reports.py:104`). `source_site` holds the **12 price shops**; muqawil lives in `site_profile`. So **0 of 18,008** contractor records — 17,304 + 704 — are in the one artefact an engine-less panel can read |
| **The offline view shows counts, never rows** | `extension/app.js:4471-4477` renders only the dataset key, `N rows`, and *"with change history"* / *"current prices only"*. No click handler, no grid |
| **And it cannot export** | `bundleview.js` exports `rowsOf` (`:82`) and `toCsv` (`:94`) **for exactly this purpose** and nothing imports them: `extension/app.js:23` takes only `readPanelPack, datasetSummaries` |

**Against Decision 8 — *"the owner sees his data and exports it"* — he measurably sees
counts and cannot export.** The reader exists; the supply and the export do not.

### Decision 9's assertion, re-tested rather than inherited

> *"A browser extension cannot create a SQLite file."*

**This repository disproved half of that itself, and then quoted the wrong row of its own
spike.** `spikes/opfs-sqlite/FINDINGS.md:353-371` measured an MV3 extension creating the
whole schema inside OPFS: DDL for 40 tables in **65 ms**, **196,871 rows** copied in
**14,332 ms**, 15,150 ms in total. Reading is measured separately at `:130-149` — 40 tables,
59 indexes, 2 triggers, 2 views, `user_version` 54, 73,278 price observations, **identical
to Python** under both engines.

**Three blockers must not be merged into one, and the plan merges them:**

1. **Location, not capability.** Decision 9's four controls are *location, backup, restore,
   migration* — and OPFS provides none of them. An extension can create a database **it
   alone can reach**; it cannot create one at a path the owner chooses or the engine can
   open. That row of Decision 9 is about the file, and it stands.
2. **The stamp.** The created database came out with `user_version = 0` from a source stamped
   **54** — and `FINDINGS.md:369` notes that is the stamp *"every migration gate keys off"*.
3. **Concurrency, which is the one that bites his actual question.** The fast path's sync
   access handles are **exclusive with no queue** — `NoModificationAllowedError` at 0 ms,
   cross-worker (`FINDINGS.md:157-158`). So it cannot serve *"read the data while the engine
   is running and holding the file"*, which is the ordinary case.

**And the library the plan cites is the one its own spike rejected.**
`docs/PLATFORM-PLAN.md:134` reproduces the *"70–208× slower"* row, which is true of
`wa-sqlite` — the library `FINDINGS.md:18-19` calls *"the one part that is simply the wrong
choice."* The spike's headline is that a **different** library, `@sqlite.org/sqlite-wasm`
3.53 over the OPFS SAH pool, runs the same Data-page query at **1.4–1.6×** of Python. The
document is incomplete rather than wrong, and the omission is the number that would change
the decision.

### And the phone model is further along than anyone wrote down

Measured above the transport, so the step is **parameterising what works, not inventing it**:
a live backend address field (`extension/app.html:1772`), a switch that re-activates and
re-adopts appearance, timezone and the UI contract (`extension/app.js:6326-6334`),
abort-and-generation-bump on change (`extension/backend.js:68-77`), and a repaint guard
whose own comment already names the multi-app hazard (`extension/data.js:74-76`):

> *"A DIFFERENT BACKEND IS NOW AUTHORITATIVE. Painting this answer would put one engine's
> rows under another engine's name"*

Installedness is measured **twice** — Chrome's `absent` verdict on the native host
(`extension/transport.js:51-52`) and a six-rung health ladder that already includes
*"Installed, not running"* (`extension/app.js:3408`). **There is one slot, not a list**:
`activeBackend` in `extension/backend.js:38`, from a single `chrome.storage.local` key
(`extension/engine.js:11`), prefixing all 40 `/api/…` calls. Sixteen constants across the two
products name exactly one product and **none is parameterised by app**.

**So what is missing is plurality and per-app identity — not the tier.**

### What this request does NOT decide

It does not decide *where the database lives*, and it must not be read as deciding it.
Decision 10 says an external tool «never touches Engine's database»; if the phone owns the
data page and three apps exist, ownership becomes a real question with real costs. That is
his to rule on once the numbers are in front of him, per `R-02`.

### State

**Two studies have landed: twenty-nine agents, nine refutations applied above.** What they
settle and what they do not:

**Settled.** The prior discussion he thought was lost is **recorded** —
[MIGRATION-PLAN.md](MIGRATION-PLAN.md)`:38-45`, drafted 2026-08-12, quotes him directly
(*"leave the engine only fetch + SQLite"*) and **already names today's question as an
accepted tension**: that sentence and *"remove the 127.0.0.1 service"* cannot both hold
*"until the extension can read SQLite itself, because nothing else reaches a 119 MB local
database."* His memory of the study is correct. **What was never done is turning it into a
ruling** — `docs/RULINGS.md` has no entry for it, so `C1` sends every session to a register
that does not contain the decision governing this whole request.

**Also settled: nothing shrank.** Between `5cccfb5` (2026-08-13, the day after that plan)
and `4522158`, the engine's interface went from 17,755 lines to **17,772** — plus seventeen
— while the extension's went from 17,749 to **24,943**, plus 7,194. The extension grew
**beside** the engine, not instead of it, because Phase B1 is still *Not started*
([STATE.md](STATE.md)). And the warehouse arithmetic says the premise is affordable:
of 1,198,592,000 bytes, **893,860,727 — 74.6% — is `generic_page_snapshot.html_content`**,
raw HTML provenance no human browses, on a table `retention.py` and `compaction.py` never
mention. Everything he would actually browse is **16,151,610 bytes gzipped, 1.34%** of the
file — **74x smaller than the database**, and a browser decompresses it with no library
and no WebAssembly (`extension/bundleview.js:29`).

**[CORRECTED 2026-08-23.]** This line first read *"9,511,282 bytes, 0.79%, 126x"*, and
that number was reported to him in conversation before it was checked. The study's own
second pass **could not reproduce it** and re-measured 164,771 rows into 161,459,448
bytes of JSON Lines, 16,151,610 gzipped, built in 3.4 seconds against the live file while
a crawl was writing. **The conclusion survives at 59% of the strength first claimed** —
which is why the weaker number is the one recorded. The full study is
[ENGINE-ROLE-MEASURED.md](ENGINE-ROLE-MEASURED.md).

**Not settled, and his to rule.** Eleven questions, the first of which governs the rest:
**"only" in «المحرك له مهام محددة فقط» — on which axis?** The *interface* axis, where the
engine keeps `extract`, `domain` and `store` and only the display leaves — or the *pipeline*
axis, where everything but the fetch leaves. `MIGRATION-PLAN.md:38-39` and
`PLATFORM-PLAN.md:96-97` each support one reading, neither cites the other, and neither is
marked superseded. **Recorded here, ruled in [RULINGS.md](RULINGS.md) when he has answered —
not before**, per `R-02`.

**One dating error is carried here as a caution**, because the study made it and its own
verifiers caught it: it dated *text* by each **file's** last commit, which inverts the
seniority of two documents in one of its headline contradictions. A line's age is not its
file's age, and this register should not repeat the mistake.
## REQ-41 · The two crawls disagree, so the code must reconcile them itself
**Captured 2026-08-23**

> «هو طريقتين الزحف مختلفة بين contractor و contractor profile وبكدا اى مستخدم هيعمل زحف
> هيلاقى اختلافات فلازم الكود لو لاقى مقاول مش موجود فى profile يجيبه مقاول مش موجود فى
> listing يجيبه»

**He is generalising from a number he was shown, and the generalisation is the request.**
Asked whether 34,834 ÷ 2 = 17,417 was the contractor count, he was told it was exact and
that the listing table nevertheless held 17,304 — 148 with a profile and no listing row,
35 with a listing row and no profile. His answer was not "fix those 183". It was: **two
collection methods will always drift, every user will meet this, so closing the gap
belongs in the code and not in a session.**

### Why he is right, measured rather than assumed

The drift is not a bug being worked around. The listing **reorders under the crawl** —
4,556 of one pass's contractors turned up on more than one page — so the listing pass and
the profile pass necessarily read two different arrangements of one site. Any two passes
separated in time will disagree; ours were separated by two days.

And the disagreement is **two-directional**, which is why one repair cannot serve:

| | | today's cost |
|---|---|---|
| profile crawled, no listing row | 148 | **zero requests** — all 148 were found in listing snapshots already stored |
| listing row, no profile crawled | 35 | 70 requests |

### What it asks for

A reconciliation the tool performs on its own: after a crawl, compare the id sets the two
datasets hold and **fetch or approve whichever side is short**, rather than leaving a
number that only set arithmetic in a session would ever notice. `--coverage` today answers
"17,269 of 17,417" for one dataset and "nothing has been sighted" for the other, so
neither surface states the gap and nothing closes it.

**The evidence-first half is free and should be the default**: the 148 needed no network
at all, because a listing page that was already stored carried their cards. A
reconciliation that fetches before it looks on disk would spend requests it does not need.

### Open, and his

Whether reconciliation runs **automatically at the end of a crawl** or is a command he
invokes. Automatic closes the gap without anyone noticing it existed; a command keeps the
gap visible and reportable, which is this project's usual preference — see
[R-32](RULINGS.md) on the tool being a platform rather than one behaviour.

---

## REQ-42 · A contractor the site withdrew is entered with what we know and a state that says so
**Captured 2026-08-23**

> «لو اختفى اى مقاول من الموقع ولازال لدينا معلومات عنه ربما مش كاملة ادخله الى قاعدة
> البيانات يدويا واكتب حالته · وايضا هذا يستدعى مراجعة عدائية لان الجودة فى الدقة»

**He ruled on the 203, and the ruling is the opposite of what the code does now.** A
contractor whose profile page no longer resolves currently produces **no profile row at
all** — the page is refused (`OP-64` layer 1) and nothing is written. He wants the row
written from what we hold, carrying a state that says it is partial and why.

### It is not a concession, because we hold a great deal

Measured 2026-08-23, over the 203 contractors with no valid profile row:

| | |
|---|---|
| we hold their **listing card** | **203 of 203 — all of them** |
| we hold nothing at all | **0** |

And the card is not thin. For contractor `1016`: name and `company_name_ar`, city and
region in both languages, company size in both, classification and its grade, membership
number, account status, training hours, main/sub-contractor flags, the logo, and both
profile URLs — **24 fields**. What is missing is only what the profile page alone
publishes: email, coordinates, address, licences, interests.

So the choice is not between a good row and a partial one. It is between **a partial row
that says it is partial** and **no row at all**, which reads as a contractor that never
existed.

### And this is `dataset_table_payload`'s own rule, extended

The payload already refuses to filter `status`, quoting him: *"a contractor the site
stopped publishing would simply VANISH from his screen"*. Today's states already carry
this — `absent`, `unavailable`, `retired`, each with a sentence a reader sees. This
request says the same principle must apply one level earlier: **not only "do not hide a
row we have", but "write the row we can".**

### The state has to distinguish three different facts, which today it does not

| what happened | whose fault | today |
|---|---|---|
| the site withdrew the contractor | the site's | no profile row |
| the profile page was never fetched | ours (coverage) | no profile row |
| we wrote a row from the wrong page | ours (a defect) | `retired` |

All three currently look alike from the profile table's side: a missing row. **They are
three different answers to "why is this incomplete" and a reader needs to know which.**

### Open, and his

The **state vocabulary**: whether "withdrawn by the site" is a new `status` value, a
`generic_record` state alongside `absent`/`unavailable`, or a field on the row. It touches
`sightings.row_state` and every surface that renders it, so it is a naming decision before
it is a code one.

**He asked for an adversarial review of this specifically** — *«الجودة فى الدقة»* — and it
earns one: this is the first feature that would write rows the site did not serve, which
is a different risk class from everything else in the contractor track.

---

---

## REQ-44 · The state gets its own column, and the user never infers it
**Captured 2026-08-21 · ruled as `R-27` and built in #235 the same day · reached the board only on 2026-08-26 · Done**

> «ضيف الحالات التى ذكرتها ولا يتم تغطيتها الان وايضا عمود يوضح الحالة الجديدة لا تدع
> المستخدم يستنتج الحالة»

*Add the states you named that are not covered now, and a column that shows the new state —
do not leave the user to infer the state.*

**FIVE DAYS LATE, AND THE LATENESS IS WHY THIS ENTRY EXISTS AT ALL.** His instruction was
**ruled** as [R-27](RULINGS.md#r-27--a-row-never-disappears-from-the-users-view-its-state-becomes-a-column)
and **built** the same day — migration `0006_a_row_says_when_it_was_last_proved_absent.sql`,
merged as #235 (`ec53b17`) — and it never reached this board. It survived in the code that
implements it: quoted in that migration's header, in `scrapex/sightings.py:102` and `:361`,
in `scrapex/extract/service.py:63` and `:984`, and in
`tests/test_a_dataset_is_a_table_like_any_other.py:849`. **Six citations in code and
migrations, zero on the register that tracks what he asked for.**

**It was found by a guard refusing a pull request.**
`tests/test_a_request_of_his_reaches_the_board.py::test_every_finding_that_quotes_him_is_reachable_from_the_request_board`
failed on `#267` because `OP-68` quotes him and nothing on the board carried the quote. The
guard was written after this exact failure happened three times in one afternoon; **the debt
it caught here is older than the branch it blocked**, and blocking that branch is how it
surfaced.

### What he asked for, in two halves

| half | state |
|---|---|
| **add the states not yet covered** | **Done.** Six were computable from what the schema held — `new`, `updated`, `confirmed`, `absent`, `unsighted`, `retired`. One was not, and migration `0006` is the reason it now is: **`returned`** — absent in an earlier crawl, and here again |
| **a column that shows the state, so the reader never infers it** | **Built, and now WRONG.** See below |

### The column he asked for is currently telling him the opposite of the truth

**[`OP-68`](BACKLOG.md) measured it read-only on the live warehouse**, and it is the loudest
false alarm the product can produce:

| | `contractors` | `contractor_profiles` |
|---|---|---|
| rows reported **absent** | **17,256 of 17,304** | 17,384 |
| rows reported **new** | — | **1**, where **121** were first seen that day |
| `dataset_sighting` rows | 17,417 | **0** |

**The screen tells him 17,256 of his 17,304 contractors have stopped being published — after
a crawl that read every one of them.** The cause is that `newest` is `MAX(last_seen_at)` **to
the second**, and a crawl writes its rows over half an hour, so only rows written in the
final second survive the comparison. The reasoning that fixes it is already in the same file
eight lines below the defect, where `last_absent_at` uses `>=` *"because both timestamps are
`strftime(…,'now')` at SECOND resolution"* — and that argument was never carried across.

**So this request is `Done` and its product is lying, which is a worse state than
`Not built`.** `Not built` shows him nothing; this shows him a number and the number is
wrong. That is why the board row says **"Done, and the column now lies"** rather than
**Done**.

### Why it is filed here rather than folded into `OP-68`

**`OP-68` is a finding — we measured it. This is a request — he said it.** `CLAUDE.md`'s
boundary is exactly that test, and the two must not drift into each other. `OP-68` stays in
`BACKLOG.md` as the defect; this entry is the instruction the defect betrays.

**And it is filed independently of `#267` deliberately.** That branch has been red for two
days holding a data recovery. Had this record ridden along with it, it would depend on that
branch landing — which is the identical mechanism that lost `OP-69` for three days. A record
that can be lost by a stalled branch is not a record.

### What is owed

The fix is `OP-68`'s to carry. What this entry adds is the standard the fix is measured
against, in his words: **the user never infers the state.** A state column that is present
and wrong does not satisfy that; it violates it more completely than a missing column would,
because it is believed.

---

## REQ-45 · The crawl button does not work for muqawil
**Captured 2026-08-26 · root cause proven · partly blocked on `REQ-25`**

> «مشكلة زر الزحف لا يعمل مع موقع مقاول»

**The button does not fail. It is not there** — and that is a deliberate decision whose
reason is four links long, every one measured on the live engine rather than argued.

| link | evidence |
|---|---|
| 1 | the panel's crawl action sends `POST /api/jobs` with `source_keys` — `extension/app.js:4064` |
| 2 | that route validates the key against `app.state.manifest` — `scrapex/webui/app.py:3392-3396`, whose own comment reads *"fail before queueing, not mid-crawl"* (re-derived at `72ca371`: `GET /api/dry/{source_key}` was inserted above it in #274 and moved it 43 lines. The quoted comment, not the number, is what made it findable) |
| 3 | the manifest is `sources.yaml` — **12 price sources, and neither `muqawil` nor `contractors` is in it.** muqawil lives in `site_profile`, not `source_site` |
| 4 | `scrapex/jobs.py`, which is what the button drives, contains **zero** references to `muqawil`, `generic_record`, `partitioncrawl`, `snapshotcrawl`, `contractors` or `dataset` |

**Confirmed against the running engine:**

```
POST /api/jobs {"source_keys":["contractors"]}
  -> HTTP 404   {"detail":"unknown source_key 'contractors'"}
```

**And the panel hides the action on purpose.** `#258` measured exactly this and labelled it:
`MANIFEST_ONLY = "route-404-for-a-dataset-key"` against `{action: "update", label: "Update
now", route: "POST /api/jobs"}`. The rule it applies is *a button that cannot work is worse
than no button.* **So what he is seeing is the absence of a path, not a broken control** —
and every muqawil crawl to date, all 34,834 pages, ran from a terminal.

### The whole crawl menu, measured — because it is four kinds of pass, not one

He asked what the options even are: «اى كل الاختيارات الى ممكن نعملها فى الزحف لمصدر مقاول؟»
Read off `scrapex/cli.py`'s own parser:

| kind | passes | network |
|---|---|---|
| **price it** | `--plan` — sizes all 56 cells | ~114 requests |
| **fetch** | `--crawl` (the listing, partitioned) · `--details` (profiles, frontier built from stored pages) | yes |
| **interpret** | `--approve` — stored pages into rows | **zero** |
| **inspect** | `--coverage` · `--impostors` (dry) | **zero** |
| **repair** | `--ids` · `--impostors --repair` | only `--ids` fetches |

**Four of the six passes make no network request at all**, so *"Update now"* as a single
button never described any of them. And the **scope** is not a flag: `--details` says the
scope *"comes from `site_profile.crawl_scope` and never from a flag"*, with three values —
`listing_only`, `listing_plus_slice`, `full_then_listing`.

### What blocks the button itself, and it is not small

**`REQ-25`** — which registry owns a generic crawl. And measuring for this entry found the
question is wider than it was filed as: **there are TWO `site_profile` rows for one site.**

| id | key | scope | datasets |
|---|---|---|---|
| **2** | `muqawil_org` | `full_then_listing` | **both** — 17,304 + 17,371 rows |
| **1** | `muqawil` | `listing_only` | **none — an orphan** |

So *"which key does the button use"* is a live question with a wrong answer available.

### The four parts that need NO ruling, and he approved all four

Asked for options useful *«فى كل الاحوال»* — under any answer to `REQ-25` — he took all four.
This is `CLAUDE.md`'s own instruction applied: build what does not depend on the open ruling
and leave the undecided fact visible rather than absorbed by a default.

1. **The scope becomes visible and settable.** Already ruled **twice** and built **zero**
   times: `PLATFORM-PLAN.md` Decision 17 — *"Crawl scope is a per-source setting"* — and
   Decision 23 — *"A newly added source has no default crawl scope; ScrapeX asks, and no
   crawl starts until the owner answers."* Measured: `crawl_scope` appears **nowhere** in
   `scrapex/webui/app.py` or in any `extension/*.js`, so it is settable only by editing the
   database by hand. Meanwhile `--details` **refuses** under `listing_only` and tells the
   owner to *"change the scope"* — with no place to change it.
2. **The three zero-network passes get a surface** — `--coverage`, `--impostors` dry, and
   the resume state. Reads over stored data: no job queue, no manifest, no crawl registry.
   They answer the three questions he keeps asking and that keep being answered by hand.
3. **The orphan `site_profile` row is closed.** Dead under every answer, and it removes a
   trap from `REQ-25`'s own decision.
4. **The 404 says why.** `unknown source_key 'contractors'` is false — the key is known and
   lives in another registry. A refusal that names the reason and points at `REQ-25` is the
   difference between *"broken"* and *"waiting on a decision"*.

**What is NOT safe to build before `REQ-25`:** the button. Which key and which registry is
the open question itself, and guessing it is how a default absorbs a ruling.
