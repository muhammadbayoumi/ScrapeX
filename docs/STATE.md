# State — where the work stands

**Last updated: 2026-08-23.** `main` is at `759a9df` (#264). #246 through #264 are
all merged — **eighteen merges** landed after this line last said `afb8648` (#244),
across two days, and the count here was measured with
`git log --oneline afb8648..origin/main` rather than carried. **And this conflict is
the argument itself:** resolving it, one side said `f1844af` (#261) with "fifteen"
and the other `d10e974` (#258) with "thirteen", and both were already wrong before
either could be read. A commit pointer written into prose is stale by the time it is
read: `git log --oneline -1 origin/main` is the answer that cannot be — **and this
very line has now proved it seven times across two days**, reading `4615a14` with
#251 and #252 already in, then `5f63bb0` with #254 in, then `451468d` with #255 in,
then `31c369e` with #258 in, then `f1844af`, then `467a3ac` with #265 in, and now
this. Each correction is the argument for the sentence rather than a counter-example
to it.

**THE ENGINE ON GITHUB IS `engine-v0.3.0`, AND IT WAS CUT TODAY.** He asked for it
directly — *«اقطع الوسم»* — after reading the finding that the panel was offering
`0.2.1`, the build whose bare invocation printed nothing. The tag sits on `451468d`,
which is this `main`; `scrapex/version.py:76` and the `pyproject.toml` mirror both
read `0.3.0` there. **Thirteen days and two `VERSION` bumps of unreleased engine,
closed.** `OP-32` · `REQ-28` · guarded by
[#253](https://github.com/muhammadbayoumi/ScrapeX/pull/253) — **open, not merged**
([R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)).

**AND THE NORMAL STATE FROM HERE IS SOURCE AHEAD OF PUBLISHED, WHICH IS NOT `OP-32`
RETURNING.** `VERSION` moves on a contract change ([R-35](RULINGS.md#r-35--the-engines-version-moves-on-a-contract-change-the-extensions-on-a-user-visible-one))
and releases are cut by hand (PLATFORM-PLAN Decision 4), so the two are *expected* to
differ between releases. Migration `0010` has already taken the source to **0.3.1**
on the branch that carries it, against a published **0.3.0** — that gap is
development, not a defect.

**What made `OP-32` a defect was never the gap itself.** It was that **nothing** had
been released across two bumps, the newest installable engine printed nothing when
double-clicked, and the documents were telling him to cut a tag the workflow would
refuse. A source one patch ahead of a published engine that works shares none of
those three. Anyone reading a version gap as `OP-32` returning should check those
three first.

**AND `engine-v0.3.0` CANNOT SERVE A PAGE. Reported by him on 2026-08-23, one day after
the tag was cut.** He double-clicked the published engine and it unpacked, found his
warehouse, announced `[3/3] Starting the engine...` and then said:

```
error: Directory 'C:\Users\User01\AppData\Local\Temp\_MEI000036d42\scrapex\webui\static' does not exist
```

`packaging/build_engine.py` told PyInstaller to carry **two** things — `db` and
`sources.yaml` — and the runtime opens **five**. `scrapex/webui/static`,
`scrapex/webui/templates` and `apps_script/StagingAppScript.txt` were never in any
archive ever published. **`OP-62`**, fixed on the branch carrying this line and proved
on a rebuilt `.exe`: bare invocation now reaches `ScrapeX UI → http://127.0.0.1:8000`,
`GET /` answers 200 with a rendered page, and `/api/outputs/apps-script/script` answers
200 for the first time in the product's history.

**So read the paragraph above with this next to it.** *Source ahead of published* is the
normal state and is not `OP-32` returning — but the three conditions that made `OP-32` a
defect are asked of the PUBLISHED build, and the second of them is true again right now:
**the newest installable engine does not work.** `VERSION` reads `0.3.1` against a
published `0.3.0`, so `engine-v0.3.1` ships the fix and no bump is needed
([R-35](RULINGS.md#r-35--the-engines-version-moves-on-a-contract-change-the-extensions-on-a-user-visible-one) —
packaging is not a contract change). **Cutting the tag is his call**, and until he does
there is nothing installable that serves a page.

This is the document that is **wrong the moment it is out of date**. Update it
when a phase lands, a PR merges, or the owner rules — in the same pull request as
the work it describes (**C2**, [../CLAUDE.md](../CLAUDE.md)).

**AND THE OPENING LINE ABOVE IS NOW ITSELF A CASE STUDY, filed as instance 3 in
[LESSONS §14](LESSONS.md).** It read `31c369e` while `main` was `d10e974`, and
`4522158` landed while that was being written. The line is not being rewritten to
chase the pointer — the sentence it already carries is the right answer, and
`git log --oneline -1 origin/main` remains the only one that cannot rot.

### The engine can now say which code it is running (open PR)

**The incident, 2026-08-23.** His panel said *"no successful crawl yet"* over **17,304
rows**. #255 had fixed exactly that two days earlier and the fix was on `main`. The
engine process started at **07:35:44**; the checkout moved off `451468d` at
**07:39:03** — **199 seconds later**. Python imports a module once, so it served the
old tree for as long as it ran, and `/api/health` answered `"version": "0.3.0"`
truthfully the whole time, because **ten distinct commits report `0.3.0`** and one
string cannot name one of them.

`scrapex/provenance.py` seals what the process loaded and compares it against the
disk: `mode` (`source`/`frozen`), the commit it started on, `stale`, `moved`. It rides
`/api/health`, and the panel renders a **Build** row under *Installed version* with a
`Restart needed` badge. A frozen build answers `None`, never `False`. `REQ-35` moves
to **In flight** — partly closed, and its stated cause was measured and corrected in
its own entry. Open items: `OP-60` (a frozen build's commit needs a build-time stamp)
and `OP-61` (continuation citations are invisible to the citation guard).

---

## RESUME HERE — written for the other machine, 2026-08-22

He works from two machines and asked to continue from the other one, which has neither
this session's context nor this warehouse. Everything below is the whole handover.

### The code and the decisions are in the repository. The DATA is not.

**Merged and done:** the six muqawil engineering items (#245), four rulings of his
executed (`R-38`…`R-41`), and the engine release gate (#244).

**His warehouse on THIS machine, measured after the profile approval:**

| | |
|---|---|
| the listing | **17,417 sighted of 17,414 declared — `D = 0`**, complete |
| `generic_record` | **17,304 listing rows**, and the profile approval is still running (10,133 of 17,417 when this line was written) |
| `generic_page_snapshot` | **56,941**, of which **34,834** are the completed profile crawl |
| `classification_node` | **243** nodes, levels `{1: 12, 2: 39, 3: 192}` |
| `generic_record_node` | **391,761** memberships — `R-38` proved on real data |
| datasets | `contractors` and `contractor_profiles` |
| schema | **v9** (`0009` = the link table) |

### Two counts, and the 183 contractors between them — measured 2026-08-23

**The owner did the arithmetic and it was right**: 34,834 profile pages ÷ 2 = **17,417**
contractors, and every one of the 17,417 has BOTH halves — `EN 17,417 · AR 17,417 ·
lonely 0`. The division is exact, not approximate.

But the listing table holds **17,304**, and the difference is not rounding. Reconciled
by set arithmetic over the ids, not by estimate:

| | |
|---|---|
| have a profile crawled, **no listing row** | **148** |
| have a listing row, **no profile crawled** | **35** |
| in both | 17,269 |
| **the union — what is known to exist** | **17,452** |

`17,417 − 148 + 35 = 17,304` closes exactly.

**Neither number is the population.** The honest total is the **union, 17,452**, and even
that is a floor: the sweep that produced the profile frontier **stopped at its pass
ceiling rather than converging**, its sixth pass still bringing 62 unseen names.

**Why two passes of one directory disagree.** The listing reorders under the crawl —
4,556 of one pass's contractors turned up on more than one page — so the two passes ran
against two different arrangements of the same site. The 148 slipped between pages while
the listing was being read; the 35 were in the listing on 21 August and were not in the
frontier the sweep handed the profile crawl.

**Both gaps are cheap and neither needs a re-crawl of any size.** All 148 were found in
listing snapshots ALREADY ON DISK — checked by decoding 20,683 stored listing pages and
matching ids, 148 of 148 present — so they are an approval, not a fetch. The 35 need 70
requests, about a minute and a quarter at the governed pace.

**That ratio is the whole of `R-38`:** 391,761 memberships share 243 nodes — **1,612x**, re-measured 2026-08-23 after the profile approval; the 15,559-over-214 figures this line carried were a day and two crawls old. Shape A would
have stored 15,559 repeated strings; the study measured that at 4.7x and it is
conservative.

### What the other machine can do with NO database at all

Two of the four next steps need nothing but this repository — the tests run on committed
fixtures, never on his warehouse:

1. ~~**Workers for `--details`.**~~ **DONE 2026-08-22.** `--details` takes `--workers`,
   the same shape as `crawl_partition`: a connection per worker, and the pace unchanged
   because `HttpFetcher._throttle` holds its lock across the sleep. Measured before:
   **9.03 s a page** single-threaded, so 34,834 pages was **87 hours**; the number to
   beat is the listing crawl's 1.14 s a page at six workers, which puts this at
   **11–14 hours**. `R-39`'s 11.1 h is amended rather than deleted — it was measured on
   the **listing** command and priced the profile one, which is a narrower lesson than
   bad arithmetic: *a rate measured on one command is not a rate.*

   **And the first six-worker run found a real race**, which is the argument for the
   guard rather than for the feature: six workers all miss the `snapshot_dictionary`
   SELECT, all attempt the INSERT, and five lose on `UNIQUE(label)` — 20 pages stored
   14 and reported 6 failures that were not about the pages at all. `_dictionary` now
   re-reads after a conflict and uses the winner's body, because the winner's body is
   what the winner's rows were compressed against.
2. **Branch protection on `main`.** Measured: `protected: False`, 404 on the protection
   endpoint. Require the check suite, require branches up to date, forbid direct pushes.
   His to switch on, and it is what makes `ac3a5af` — which left `main` red for two days
   with no pull request — impossible rather than merely regretted.

   **AND IT HAS A SECOND REASON NOW, measured 2026-08-22.** *Require branches up to
   date* is the clause that matters, and *require the check suite* on its own would
   **not** have caught it: #251 and #252 both passed every check, shared no changed
   file, and merged into a **red `main`** — #251 moved a line in
   `scrapex/webui/app.py`, #252 wrote that line's old number into the PINNED citation
   table, and #252's checks passed against a base that stopped existing when #251
   landed. Repaired on `feat/the-profile-page-becomes-columns`; the mechanism is in
   [LESSONS.md](LESSONS.md) under *Two pull requests, disjoint in files and coupled
   in content*.

### What needs the data, and his plan for moving it

3. **The full profile crawl** — 34,834 pages. **RUNNING on this machine since
   2026-08-22**, `--run-ref profiles-2026-08-22 --workers 6`, measured at **1.01 s a
   page**. Belongs on whichever machine holds the warehouse.
4. ~~**The remaining four groups of `R-19`.**~~ **RE-MEASURED AND HALF BUILT
   2026-08-22**, and the re-measurement is the point: every reason recorded here was
   read off **two committed fixtures**, which are one contractor, and he warned that
   the pages are not consistent — «المعلومات غير ثابته ولا متفقثة بين الصفح». Counted
   over **2,419 real profile pairs** off the running crawl:

   | group | what the corpus says | done |
   |---|---|---|
   | `licensed_activities` | 1,685 rows over 228 pages, a **closed vocabulary of 22**. The "unseparated string" was separated after all — the dashes are **hierarchy** separators inside each language, and the language boundary is the first Latin letter, `AL` on 1,500 of 1,500 cells | **built**, its own taxonomy scheme |
   | `contract_counts` | 92 pages, one row of two numbers — the flat row was right | **built**, two columns |
   | `sub_contractors` · `main_contractors` | rows on **2** and **0** pages of 2,419 | declared, not built — `Q-18` |
   | ~~`technical_rating`~~ | **not a table at all.** `contractor-tab4` holds zero tables in its DOM subtree on 2,360 of 2,360 pages | nothing to build |

   **And the page has SEVEN cards, not five, one of which is a PRICE.** The card titled
   `العقود سعر البناء (برنامج البناء الذاتي)` publishes a self-build price per square
   metre in three tiers — three new columns — and the contract-request form, believed
   absent, carries the **Commercial Registration number** on 2,542 of 2,543 pages, ten
   digits, all distinct. Six new columns in all, 21 → 27, safe because `R-31` upgrades
   a schema additively. See `OP-43`, [LESSONS.md](LESSONS.md) §11, and `Q-17`/`Q-18`,
   which are what is actually left for him.

**HIS RULING ON THE TWO WAREHOUSES, 2026-08-22.** Both machines have developed muqawil, so
the databases must be **merged**, with Drive as the single source of truth for DATA while
the repository stays the single source of truth for CODE. **Do not copy either file over
the other** — each holds work the other does not, and `R-24` says upgrade rather than
replace.

The merge is defined, and it is defined because the natural keys exist — measured
2026-08-22:

    generic_page_snapshot   20,379 rows, 20,379 distinct (source_url, content_hash)
    dataset_sighting        UNIQUE (dataset_key, external_id) in the schema
    generic_record          UNIQUE (dataset_definition_id, record_key) in the schema

So: dedupe snapshots on their natural key; merge sightings taking min `first_seen_at`, max
`last_seen_at`, **summed** `seen_count`, max `last_absent_at`; and **delete and rebuild
everything derived** with `--approve` rather than merging it. That last clause is what
makes the whole thing tractable — no primary key is ever remapped, and the operation is
commutative and idempotent, so it does not matter which machine runs it or how often.

**BUILT 2026-08-22 — `scrapex merge-warehouse`** ([R-43](RULINGS.md#r-43--drive-is-the-single-source-of-truth-for-data-the-repository-stays-it-for-code)).

    scrapex merge-warehouse --status                      # who holds it
    scrapex merge-warehouse --machine work-laptop         # take it
    scrapex merge-warehouse --machine work-laptop --from <downloaded.db>
    scrapex merge-warehouse --release                     # hand it back

The lock lives in `scrapex_meta.checkout_holder`, beside the `account_owner` that `R-34`
already put there, so it needs no migration and an older warehouse answers "nobody" rather
than failing to open. Seventeen tests, and the one that matters asserts that merging three
times changes no VALUE — the first implementation summed `seen_count` and took one id from
4 to 8 to 12 to 16 while claiming to be idempotent.

**The order on the other machine:** download from Drive → `--machine <name> --from
<downloaded.db>` → `contractors --approve --run-ref <ref>` for each run whose pages
arrived → work → upload → `--release`.

**AND THE UPLOAD IS THE PANEL'S, NOT THE CLI'S** — his ruling of 2026-08-11 removed
`scrapex/gdrive.py` and gave every Google operation to the extension. `scrapex/bundle.py`
builds a bundle containing `warehouse.db`, taken through sqlite3's own backup API;
`extension/drive.js` uploads it resumably to a `ScrapeX backups` folder with a
`latest.json` pointer and three kept. The panel button is **`drive-backup`**.

> **DO NOT PRESS `drive-restore` ON THE OTHER MACHINE.** Restore REPLACES the live
> warehouse — `registry.engine.restore` displaces it and says so — so it would lose the
> muqawil and products work that machine has and this one does not. It sits beside
> `drive-backup` in the same card. **Backup here, download there, MERGE.** That distinction
> is the whole of `R-43`, and the destructive path is one button away from it.

**For what the owner has asked for and where each request stands, see
[REQUESTS.md](REQUESTS.md).** This file tracks the *work in flight*; that one
tracks *his requests* through Captured → Ruled → Planned → In flight → Done.

---

## Open pull requests

### muqawil is ONE card, and 17,304 contractors stop being products — 2026-08-23

**`REQ-37` was ruled on 2026-08-22 as `R-47` and was still not built on 2026-08-23**,
which is why he asked «حل المشكلة لم يصل لى ما السبب ؟» — the fix has not reached me,
why? Measured before starting: **no file under `extension/`, `scrapex/` or `tests/`
cited `R-47` or `REQ-37`.** A ruling with no code behind it is the `REQ-04` failure, and
that is the whole answer to his question.

Two of the four defects on that screenshot are this branch's; the other two
(`no successful crawl yet` on both muqawil cards) landed as #255.

- **`REQ-37` / `R-47` points 1 and 2 — BUILT.** `_dataset_listing` folds a confirmed
  one-to-one child dataset into its parent for `/api/sources`, so `muqawil.org` is
  listed once, and the second number stops being a second population: the card reads
  `Contractor profiles: 704 of 17,304 (4.1%)`. **`_dataset_rows` is deliberately
  untouched** — `/source/{key}` resolves one dataset out of it by key, so folding
  in place would have made `/source/contractor_profiles` answer 404 again, which is
  the regression #212 closed. Only the presentation collapses, which is what `R-47`
  ruled.
- **`R-47` point 3 — BLOCKED, not skipped.** «اختيارات الزحف» needs two crawl options
  on the card and there is **no panel path to a dataset crawl at all**: `POST /api/jobs`
  answers `404 unknown source_key 'contractors'` (`OP-52`). `REQ-37` therefore stays
  **In flight**.
- **`OP-63` — the panel half CLOSED, the engine half OPEN.** `17,304 products` over a
  contractor directory. `countLine` replaces the hardcoded noun with three branches
  keyed on what the engine reports, so `jobs` and `tenders` need no new code. The
  engine's own `/source/{key}` page still prints a "Products" tile over the same rows —
  left filed with the measurement because that page shows four tiles and two are
  meaningless for a directory, which is his call, not a noun.
- **`R-47` CORRECTED, ruling intact (`C4`/`C5`).** Its point 2 says the coverage figure
  is *"the one `--coverage` already computes"*. It is not: `coverage("contractor_profiles")`
  answers *"nothing has been sighted"* — `dataset_sighting` holds zero rows for that
  key — and `coverage("contractors")` answers 17,269 of 17,417 (99.2%), a different
  question. The 704-of-17,304 figure comes from the `dataset_relationship` row he asked
  for by name, not from a sighting.
- **His GPP comparison has no presentation to copy.** `grep -rin gpp extension/` returns
  **nothing** — no branch, no card, no picker. `GPP_ENERGY` is one `source_key` and its
  five energy types live in a dict inside `scrapex/connectors/gpp.py`, so the panel has
  always drawn it as one card without knowing it was one. The transferable lesson is
  *collapse below the surface*, which is what the listing now does; the part that cannot
  be hidden — two separately-run crawls — goes to the `⋮` menu `REQ-36` built rather
  than to a second vocabulary (`PLATFORM-PLAN` Decision 26).

**Twelve mutations, twelve caught.** Every guard on this branch had its defect restored
and was proven RED, then GREEN on restore, with `__pycache__` purged between runs and
the restore verified by `git status --porcelain` rather than a content hash. **One
mutation was NOT caught on the first pass and the guard was replaced**: a seam test
asserted the string `c.stored` appears in `app.js`, and `c.stored` appears **twice**
there, so renaming the occurrence the card reads left the substring present and the
test green. It now compares the harness stub's coverage keys to the engine's own —
behaviour at the seam, which is where #255 failed. *A search for one spelling of a
feature is not a measurement of the feature* (`LESSONS.md` §9), arriving through a
fourth door: a test.

**This branch is from a SECONDARY session and does not merge itself** (`R-42`).

**THE REGISTER MOVED THREE TIMES UNDER THIS ONE BRANCH, and the lesson is in the third
move rather than the first two.**

| took | why it moved |
|---|---|
| `OP-53` | correct when written — `main` topped out at `OP-52` |
| → `OP-61` | #261 landed and declared **53…59**. A genuine duplicate, and `test_no_two_entries_share_a_number` would have had it |
| → **`OP-63`** | `OP-61` was **already declared on a pushed branch** — `feat/the-engine-knows-which-code-it-is-running` holds 60 **and** 61 as a cross-linked pair. `OP-62` is a third session's |

**The primary handed out two colliding numbers in one day and said so** — from the
session that owns `ORCHESTRATION.md` §3. Its tables covered the branches it knew about,
and this branch was in neither. **What found the second collision was a sweep of EVERY
ref**, not of a named list:

```bash
git for-each-ref --format='%(refname:short)' refs/remotes/origin | while read -r r; do
  git show "$r:docs/BACKLOG.md" 2>/dev/null | grep -oE '^#{2,4} +OP-[0-9]+'; done | sort -u
```

**Run independently here before accepting 63** rather than resting on the handover: it
confirmed 60 and 61 on that branch and found nothing anywhere above 61. So a number you
are handed is **provisional until you have swept for it** — which is §3's *"an unpushed
claim is invisible and still real"* arriving from the other side: **a pushed claim is
visible and still missed, if you look at a list of branches instead of at all of them.**

**Checked rather than assumed before each renumber:** none of `OP-53`…`OP-59` covers the
noun (they are the price-path columns registered against the directory, Choose-Columns,
the unreachable server capabilities, the truthy `{}`, the `offer_id` index, his deletion
gate, and the `HANDOFF` citations), so this is a distinct finding and not a second entry
for one thing.

**`RESERVED` carries `60`, `61` and `62`.** The first two name a verifiable branch ref
because the sweep found them. **`62` is the weak row and says so** — no ref carries it,
so it cannot name the branch §3 requires and admits that instead of inventing one,
carrying an action: replace it with the ref when that holder pushes, or delete it if 62
turns out free. **`OP-63` still needs the primary's confirmation.**

**`R-49` was checked against this work and does not touch it.** The ruling makes
`docs/MIGRATION-PLAN.md` the base plan for conflicts of *intent*. That document says
nothing about `products`, a noun, or a dataset's row label — grepped — and the noun
decision rests on **measurement** (`dataset_kind` is `'table'` for both muqawil
datasets; nothing in the warehouse names the unit of a row) plus `R-45` part 1, which is
a ruling rather than a plan. Where a measurement and a document disagree, the
measurement wins regardless of dates.

**A DRY review of `#252` recorded `OP-46`, `OP-47` and `OP-48` — documentation only,
no code touched.** The review followed that PR's own comment to the three popovers it
named as its layer precedent, and all three findings came out of checking that claim:

- **`OP-46`** — `setupFinanceConverterSelect` and `setupRunModeSelect` are one
  component written twice; `focusOption` is character-identical after normalising one
  identifier.
- **`OP-47`** — the split button's stacking trap is documented as prose that tells the
  next consumer to re-write the selector by hand, instead of being owned by the shared
  component that ships the trap.
- **`OP-48`** — the layer scale is transcribed **by hand on both sides of the
  extension/engine boundary**: three rules across `extension/app.css` and `webui.css`
  write a token's value as a raw number, and the two sheets share nothing but
  `tokens.css`. `.modal-veil`'s correctness depends on one of those equalities and only
  a comment holds it. A guard scoped to either surface alone goes green with the other
  still wrong.

Nothing in any of the three is broken today; all are filed as cost, each with its
narrow fix and the proof it must carry. **`OP-48` is the one to build first** — a
three-value substitution that cannot change a pixel, and lowering `--z-overlay` today
would undo `#252`'s fix from a file that never mentions it. `OP-47` should wait for the
card-restyle session to land, because it edits a component five surfaces consume.

**This branch is from a SECONDARY session and does not merge itself** (`R-42`). All
three numbers were assigned by the primary session. The `RESERVED` rows in
`tests/test_the_registers_cannot_collide.py` that covered them are **gone as of this
branch**: `44` landed with #255 and `46`/`47`/`48` with #256, and a reservation for a
number now on `main` fails `test_a_reserved_number_is_not_also_declared`. Only `45`,
`49` and `50` remain, all held by `claude/drive-without-a-server` — **delete each row
the day that branch lands.**

### The source card's three dots — three defects in one control, two PRs, one day

He photographed the Data screen three times on 2026-08-22 and each screenshot found
a different defect in the same `⋮`. The first is merged; the other two are the PR
open now.

**1 · It appeared twice.** `REQ-30`, «لماذا تظهر مرتين» — **MERGED as
[#252](https://github.com/muhammadbayoumi/ScrapeX/pull/252) (`5f63bb0`).**
`.dataset-card > .split-button` carried `z-index: 1`, which made every card's menu
wrapper a **stacking context** and spent the open menu's own `z-index: 120` inside
it, so all the wrappers tied at level 1 and the card BELOW painted its button
through the menu hanging over it. Lifted to `var(--z-overlay)` while open. Guarded
by a **hit test**, not a z-index read: measured, the defect survives the menu's own
z-index going to 2147483647.

**2 · It was missing on a contractor card.** `REQ-36`, «ال 3 نقاط لا تظهر فى كارد
مقاول» — and it closes `OP-42`, which this repository had already recorded from the
same screenshot. `sourceMenu` returned `""` for `kind === "dataset"`, which was true
of five of the six actions and false of the sixth: *Open the data table* drives
`/api/table/{key}`, which resolves the dataset catalogue **first**, and was built
after the blanket hide.

The fix is not a per-entry allowlist, because that is the thing that rotted. Each
action now declares **the engine route it drives** and **a proof of what that route
does with a dataset key**, and `tests/test_a_dataset_card_offers_what_works.py`
CALLS all six against a real approved dataset — asserting in both directions, so an
action that is offered must answer with rows and an action that is withheld must be
proven unable. Measured: `table` 200 with 4 rows and 25 columns; `sheet`, `update`,
`pause`, `settings` all 404; `changes` 200 with no changes section on the page. So a
contractor card carries **one live row and no greyed rows**.

**3 · It looked wrong.** `REQ-36` again, «توجد ال3 نقاط بشكل غير احترافى فوق الكارت وداخل
مربع اعتقد ان ال3 نقاط معمولة فى صفحة profile بشكل احترافى» — he named the reference
himself and was right twice. `.split-button-trigger`'s radius computed to
**`0 8px 8px 0`**: it rounds its outer corners only, because in a split button its
inner edge butts against the primary action. On a card there is no primary action,
so the shared rule drew a lopsided filled box on the card's own rounded corner. It
is now `.account-menu-button`'s treatment — a bare 40px circle, `--muted`, tinted on
hover and while open — in rules local to `.dataset-card`, using only tokens the
profile row already uses, so no palette work was needed. Guarded by **comparing the
two controls' computed styles** in light and dark rather than by asserting numbers.

**SEEN, NOT DESCRIBED.** He asked in visual terms, so the answer is four pictures,
committed rather than pasted into a message that lives on one machine:
`docs/screenshots/the-source-card-three-dots-{before,after}-{light,dark}@360.png`.
The *before* pair is `origin/main`'s `app.js` and `app.css` with the same stub, so
it shows what he photographed — a boxed trigger on the two price cards and **none
at all** on the muqawil card, 3 cards and 2 triggers — beside the *after*, which is
3 and 3.

**What the honest stub bought, and it is the part worth carrying forward.**
`tools/panel_harness.py` had no `kind: "dataset"` source, so
`test_dataset_action_opens_the_workspace_directly` asserted that EVERY card has a
menu and passed for ten days while the product did the opposite. Adding one dataset
row failed it immediately, and surfaced two further findings on screens nobody was
looking at: **`OP-51`** (Source settings opens `/sources/{key}`, a route that exists
for nobody; Recent changes opens `#changes`, a fragment that exists nowhere, while
the real `/changes?source_key=` page does) and **`OP-52`** (the Run screen offers a
dataset as crawlable and `POST /api/jobs` 404s it; the Source manager lists it with
an Edit button that cannot reach it). Neither is fixed — both change what a screen
offers, which is his call.

**Still open and NOT touched by any of this:** both muqawil cards read "no
successful crawl yet" while showing 17,304 and 704 rows. That is a third track's
work, and the stub reproduces it rather than hiding it.

**[#244](https://github.com/muhammadbayoumi/ScrapeX/pull/244) — MERGED (`afb8648`);
kept here because the three blockers it named are still his.** `REQ-28`. The release
gate now runs the binary the way a person runs it; the three things that actually
unblock him are `OP-37`, `OP-32` and `OP-33`, and **all three are his**. See the
section below.

**THE NEXT MOVE IS HIS, NOT THE CODE'S.** `Q-13` in [BACKLOG.md](BACKLOG.md) asks how
`R-19` should be implemented, and `R-19` is the largest thing he has ruled on that is
not built. Everything else on Track 2 either waits behind it or waits behind the
crawl. If a session wants work that depends on nobody: `REQ-20`, or run
`--coverage` over what the crawl has already gathered.

> **`main` MOVED WHILE THIS BRANCH WAS OPEN, and it changed the answer — read this
> before the section below.** [#243](https://github.com/muhammadbayoumi/ScrapeX/pull/243)
> (`eb691d9`) merged `claude/his-four-rulings`, and it closed **two** of the three
> things that were blocking him:
>
> - **engine migrations 0007/0008 are on `main`**, so a released engine can open his
> warehouse. `OP-33` closed — verified read-only against his live file: `"status":
> "Healthy", "schema_version": 8`.
> - **the red suite is fixed**, by the identical one line this branch wrote at the same
> time. `OP-37` closed. Two sessions reached the same repair without seeing each
> other; #243's own comment calls it a time-of-day fault, which undersells it, and
> the correction is recorded per **C5**.
>
> It also took `OP-30` and `OP-31` for two different findings, so this branch's six
> entries are renumbered **`OP-32`–`OP-37`**, and `OP-38` is new.


### The updater — 2026-08-21 (evening) · `REQ-29` in flight

**He asked for the engine's updater and the panel's `downloads` slice, and both
are built.** *«ابدأ بالمحدث داخل الـEngine وشريحة downloads»*, under
[R-36](RULINGS.md#r-36--the-engine-updates-itself-the-panel-only-asks-and-a-published-sha-256-over-https-is-enough-to-trust-a-download).

| new | what it is |
|---|---|
| `scrapex/release.py` | the engine's own reading of the release feed — the **third** reader of one file, so `tests/test_the_engine_reads_the_same_release_feed.py` holds it to `releases.js` and the workflow |
| `scrapex/update.py` | fetch, **verify**, stage. Four rules, none of which a caller can switch off |
| `scrapex/webui/update_api.py` | `GET`/`POST /api/update`, `GET /api/update/plan` — wired **unconditionally**, because a database this build cannot open is a reason to want a newer engine, not a reason to hide the way to get one |
| `extension/` | `downloads` permission; the first install now has a live percentage and a **Show in folder** |

**Verified end to end against the real manifest**, and the answer it gives is
itself the story:

```
installed 0.2.2 · latest ok 0.2.1 · verifiable true
update_available false
POST /api/update -> "0.2.2 is already the published version."
```

The published release is **older than what is installed**, because 0.2.2 was
never cut. The updater is correct and has nothing to do until it is.

**Seventeen mutations, seventeen killed — after two survived.** Both survivors
were the same weakness and it was the most security-relevant one: every test
supplied a digest that differed from the truth *everywhere*, so shortening the
comparison to `expected[:8]` or a `startswith` refused them all and passed. A
digest that shares a long prefix and differs late is the only thing that catches
that, and it exists now.

**What is NOT built, and it is one step:** replacing the running executable.
`OP-39` says why stopping here is honest rather than incomplete — the swap cannot
be tested without a frozen build, so the plan is returned as inspectable data and
performs nothing.

**And a new finding, measured while testing:** his warehouse is at **schema v9**
and `main` reads v8 — the third time in one day that an unmerged branch has moved
his live database ahead of `main`. `OP-40`, with `Q-15` for him.

### In flight now — 2026-08-21 (afternoon) · [#244](https://github.com/muhammadbayoumi/ScrapeX/pull/244)

**The Engine would not install on his machine, and the cause is not the installer.**
[REQ-28](REQUESTS.md#req-28--the-engine-would-not-install-and-showed-a-black-screen).
He downloaded it, got a black screen, and could not install it. His download is
perfect — 70,872,447 bytes, sha256 `df7a00ee…`, matching the hub manifest exactly.
**The only installable engine is the build made before the fix for this exact
symptom.** `engine-v0.2.1` is commit `4386d25`, where
`4386d25:packaging/engine_entry.py:62` sends a double-click to the native
messaging host (today's line 62 is a comment);
`_first_run` landed six hours later at `7a067c5` and has never been released.
Reproduced on his file: **0 bytes printed, still alive at 20 s.**

**Built here:** the release now runs the binary **the way a person runs it** —
`.github/workflows/release-engine.yml`, a step that launches it with no arguments at
all, bounded by a timeout because a good first run never returns, and refuses a build
that prints nothing or cannot get past preparing a database. Guarded by
`tests/test_the_release_proves_the_double_click.py`; **eleven mutations, eleven
killed**, one of which caught the guard accepting a data root that was named but
never assigned.

**HE THEN AUTHORISED THE NEXT TWO AND KEPT THE MERGE.** *«ابدأ بـ OP-36 و OP-35
وضمهم لنفس tree واترك الدمج للمبرمج الرئيسيى»* — both are built in this same tree, and
the merge is his. **That last clause is a process ruling, not a preference about one
branch: [R-37](RULINGS.md#r-37--the-agent-does-not-merge-the-main-programmer-does)
supersedes [R-18](RULINGS.md#r-18--merge-it-when-it-is-green)**, and R-18 stays in
place, marked, per **C4**. What changed is who presses the button; R-18's reading of
*green* is now the report rather than the action.

**`OP-36` and `OP-35` are FIXED, and they were one defect wearing two faces.**
`scrapex/enginelaunch.py` is new — `nativehost.py:57`'s three lines generalised — and
`relaunch`, `native`, `autostart` and `osschedule` all call it instead of each
deciding the `-m scrapex.cli` question for itself. `KNOWN_COMMANDS` is gone:
`known_commands()` asks `scrapex.cli.subcommands()`, which reads the choices off
`build_parser()`, so **24 of 24** subcommands are reachable from the shipped binary
against 12 before. **Ten mutations, ten killed**, and the tenth caught my own test
passing for the wrong reason.

**WHAT R-36 UNBLOCKS.** Its part 4 said an Update button on top of these two would
lie. It no longer would. **But it is not yet proved against a real frozen build** —
the guards set `sys.frozen` and `sys.executable`, which is what makes them possible
at all, and the first artifact to exercise them for real is the next release.

**STILL HIS — ~~and now only one~~ NONE. Item 2 is DONE:**

1. ~~`OP-37`~~ **— fixed, and by #243 in parallel rather than by this branch.** So
   the release is no longer blocked by a red suite. The pattern was not invented:
   `tests/test_a_crawl_says_what_it_saw.py:215` already pins every row and then
   overrides one, for the same column.
2. ~~**Cut the release.**~~ **— DONE 2026-08-22. He asked for it directly**
   (*«اقطع الوسم»*) after reading the finding, and the tag `engine-v0.3.0` is on
   `451468d`, which is this `main`. Verified from the tag rather than reported:
   `scrapex/version.py:76` and the `pyproject.toml` mirror both read `0.3.0` there,
   so the workflow's first step had a tag and a version that agreed. **The first
   engine release in thirteen days, and the first that carries `_first_run`** — the
   black window of `engine-v0.2.1` is no longer the only thing installable.
   `OP-32` · `REQ-28`.

   **This line is now history and is written as history on purpose.** It said
   `engine-v0.2.2`, which stopped being cuttable the moment #247 moved `VERSION` to
   0.3.0, and the release the repository was asking for would have been refused
   before anything was built.
   `tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py` is
   what stops that recurring — and the reason the sentence above no longer spells
   the tag inside a command is that guard's own third shape: **a completed release
   must stop reading as an instruction, or it rots at the next bump.** It would have
   rotted at the very next one, which is `0.3.1`.
3. ~~**`claude/his-four-rulings` must merge, or the release will not help him.**~~
   **— merged as #243** (`eb691d9`), which brought engine migrations 0007 and 0008,
   so `main` reads schema v8 and the v8-against-v6 gap this item named is closed.
   `OP-33`. **A v9-against-v8 gap was found later the same day** and is a different
   entry — `OP-40`, with `Q-15` for him.

~~**Until then, the engine that runs on this machine is that worktree's**~~ — **the
instruction is dead: `determined-liskov-0c89fe` is not among the worktrees any
more** (checked 2026-08-22), and #243 merged what it was carrying. Run it from the
checkout you are in:

```
python -m scrapex.cli ui --no-open
```

Whether `main` can open **his** warehouse is a separate and still-open question —
`OP-40` and `Q-15`, not this line.

**AND HE ASKED FOR THE NEXT THING IN THE SAME BREATH — `REQ-29`:** an install
surface *«تشبه اى برنامج محترف»* and an update anyone can apply. **Measured before
designing: the surface is largely built — nineteen elements, six states, a verdict
badge and a label that says what the button will do. What is missing is the
MECHANICS**, and the finding that decides the design is that the panel *cannot*
supply them: Chrome gives it no `downloads` permission, no file read and no way to
launch a process, so `app.js:3620` hands a URL to the browser and lets go. **The
engine can do all three.** So the first install goes through the browser because
nothing is installed yet, and every update after it belongs to the engine. That is
blocked on `OP-36` first, then a ruling from him on what makes a download
trustworthy without a signing certificate. The full study is in `REQ-29`.

Also found and filed, not fixed — all three are the SAME silent fall-through to
`serve()` that produced the black window. **`OP-35`:** twelve of the CLI's
twenty-four subcommands are unreachable from the shipped engine and print nothing,
`database-status` among them — the one command that names `OP-33` in a line.
**`OP-36`:** a frozen engine cannot restart itself, because `relaunch.py` puts
`-m scrapex.cli` in front of an executable that does not honour it. And **`OP-34`** — a launch that dies in a console writes
**nothing** to `~/.scrapex/engine.log`, because `_bind_log_streams` deliberately
no-ops when it has real streams. That log is dated 2026-08-01 and is not evidence
about anything that happened since.

### Merged 2026-08-21

**[#238](https://github.com/muhammadbayoumi/ScrapeX/pull/238) — his ruling tested
before it was built.** `REQ-23`: eleven criteria fixed before measuring, five shapes,
518,490 rows. **`R-19` is upheld** — JSON costs 1,168 ms on the query it names against
0.6 ms for the best shape. It also decided only half the question, and the half it
left open turns on a criterion nobody had raised: relabelling a category costs 103,698
rows in 5.9 s one way and 1 row in 0.1 ms the other. Recommendation recorded as
`Q-13`; **nothing built.**

**[#237](https://github.com/muhammadbayoumi/ScrapeX/pull/237) — the file that starts
every crawl had no tests.** `OP-28`: `tools/crawl_muqawil_listing.py`, 452 lines, zero
tests, and CI cannot see it (ubuntu-only, and `tools/` is outside the linted path).
Nineteen tests, eleven mutations killed — after four of the first twelve mutations
turned out not to have applied at all.

**[#236](https://github.com/muhammadbayoumi/ScrapeX/pull/236) — a subdivision is
checked against its parent.** `REQ-21`: `crawl_partition` takes a `parent` cell and
audits `Σ N_child` against **it**, `Cell.is_under` settles membership as a set
question, and `NotASubdivision` refuses a child that dropped a parent filter before a
request is spent. Eight mutations killed.

**[#235](https://github.com/muhammadbayoumi/ScrapeX/pull/235) — a row says what
state it is in.** The observation state as a column instead of something the reader
infers from two dates: eight states, closed vocabulary, seven of them computed;
engine migration `0006` for the eighth fact (`last_absent_at`, without which
`returned` cannot exist); `R-27`, which stops a vanished row from leaving the sheet;
`R-20`'s unchanged-means-no-revision, without which `last_changed` means nothing;
the profile-page candidate adapter; and a **~1,600×** fix to `coverage()` /
`missing_ids()` (49.7s → 0.03s each). All five CI jobs green including
`migration-authority`. Ten mutations killed.

Also merged 2026-08-21: [#233](https://github.com/muhammadbayoumi/ScrapeX/pull/233)
and [#234](https://github.com/muhammadbayoumi/ScrapeX/pull/234) — a proof that
demanded more than it needed, and 823 pages refused by one column.

### The crawl that is still running

The residual crawl of the nine heavy cells is **live** and resumable
([R-26](RULINGS.md#r-26)). As of 2026-08-21 08:06 it had stored **3,563 listing
pages** across all 56 cells; by 07:13 it was **5,458**, and the ledger held
**THE LISTING IS COMPLETE: 17,414 of 17,414 distinct ids, `D = 0`** (2026-08-21). Stored *records* are 15,707 and climbing, because `OP-25` was
extraction route is deferred by `R-25`; the gap between the two numbers, 14,101, is
exactly the question the sightings ledger exists to answer.

**The listing crawl itself** — `scrapex/partitioncrawl.py`, the `Cell`
vocabulary, muqawil's facets, and the driver that had never existed — merged as
#227-#234. Verified against the live directory: 56 cells, 897 pages, an
exhaustiveness deficit of **0**.

Sixteen merged on 2026-08-20, the last nine in this order, each on green CI under
[R-18](RULINGS.md#r-18--merge-it-when-it-is-green):

| | |
|---|---|
| `a683d70` | **#215** the profile background reverted, which unblocked `main` |
| `bf2ae66` | **#220** the Arabic half was a column and not a value, and `/source/{key}` answered 404 for a dataset |
| `a1d077f` | **#213** DEC-8: the engine's Data page is a port, not a rebuild |
| `3d265cd` | **#216** the CI tiers, the docs gate, and two guards that had become silent skips |
| `cb869f9` | **#222** R-18 itself — merge it when it is green |
| `785533c` | **#221** the two generic flags lit, at `PARTIAL` |
| `ce80886` | **#217** the Engine page is two screens, plus three defects an adversarial review confirmed |
| `42dbf23` | **#223** a dataset exports a workbook and loads whole |
| `72f93a8` | **#218** `main`'s padding is a token, and the two full-bleed screens finish #217's refactor |

> **CI works again, and how it came back is worth knowing.** Every job from
> 2026-08-19T14:28Z until 2026-08-20T06:34Z failed with *"the job was not started
> because recent account payments have failed"* and **no step executed** — absent,
> not red. It cleared because **the repository was made public**: private Actions
> minutes on the free plan had run out, and public repositories get unlimited
> standard-runner minutes. A ruling recording that, and recording that an exposure
> audit was proposed and declined, is drafted but **not yet committed** — see the
> uncommitted-work list under Named gaps.

### What `ac3a5af` cost, kept because REQ-11 exists for it

It reached `main` **with no pull request** — a single-parent commit, so no CI ran
before it landed. It wrote a raw hex literal into `extension/app.css`, which
`tests/test_vendor.py::test_ui_colour_literals_live_only_in_the_canonical_colour_system`
forbids, and `main` was red from 2026-08-18 until #215 reverted it on 2026-08-19.
Every pull request opened in between inherited that red, and I misread the outage's
"failure" as a regression of my own once.

**`main` still has no branch protection at all** — `gh api
.../branches/main/protection` answers 404. So R-18 is the entire gate, enforced by
discipline. Captured as
[REQ-11](REQUESTS.md#req-11--branch-protection-for-main-in-a-session-of-its-own),
deferred by him to a session of its own, with the trap that stopped it being done
at once: `test` and `migration-authority` are gated on `needs: scope`, a docs-only
change makes them **`SKIPPED`**, and a required check that is skipped can leave a
pull request unmergeable for ever.

---

## Track 1 · The Console migration

**Plan:** [MIGRATION-PLAN.md](MIGRATION-PLAN.md) · **Detailed state:**
[HANDOFF-resume-the-migration.md](HANDOFF-resume-the-migration.md)

> ⚠️ That handoff was last updated at #201 and **does not record #202–#209**, which
> are all Track 2. Read it for Phase A/B detail; read this file for the whole
> picture.

**Done:** Step 0 · A0 (the blind settings guard) · **A1–A4, Phase A complete** —
the Console reads and edits all six sheets (#185–#189, #192) · T1 `crawl_pace_s`
(#190) · B2's foundation — `backend.js` extracted, Tabulator vendored,
`data.html`/`data.js`/`datatable.js` (#193) · the Console rendered in a real DOM
test (#200) · sign-out (#201, ruling [R-13](RULINGS.md#r-13--sign-out-of-all-accounts-must-really-sign-out-all-of-them))

**Resume here — the rest of B2, in this order and the order is reasoned:**

1. **The details drawer — `GET /api/offer/{key}/{id}`.** Least entangled; touches
   nothing the panel uses, so it proves the pattern on a second endpoint at no
   risk. The endpoint was built for this — its docstring says *"for the panel the
   Data page opens INLINE"*. Note its ownership rule: an offer that is not this
   source's answers 404 **without confirming the id exists at all**.
2. **Choose-Columns — `GET`/`POST /api/fields/{key}`. Do not write a second one.**
   The panel already has the whole thing: `loadSourceColumns`
   (`extension/app.js:1602`) and `saveSourceColumns` (`:1641`), speaking the same
   bodies. **Extract** it into a shared module the way `backend.js` was, or the
   two surfaces will disagree about how a column is saved.
3. **Saved views — `POST /api/views/{key}`, `DELETE /api/views/{id}`.**
   **HELD** — see [O-5](RULINGS.md#open--awaiting-the-owners-ruling). Do not start.
4. **Promotion — `GET`/`POST /api/promotable/{key}`.** Its contract was not read;
   read it first.

**Then:** remove the workbook link from the source card — but only once all four
are in. Taking it away before the replacement carries them would be a downgrade
wearing the word "migration".

**Not started:** **B1** (delete pure duplication and the dead routes) · **B3**
(Storage and Retention, the destructive half — every safety interlock moves *with*
its control) · **B4** (the rest, cheapest first) · **B5** (one navigation source
instead of three) · **B6** (the engine's new face: tray icon and log window).

**Phase C deferred:** `127.0.0.1` cannot go until the extension can read SQLite
itself (**DEC-1**, wa-sqlite + OPFS), and jobs cannot move while the heartbeat is
broken under load (**T2**).

---

## Track 2 · The muqawil.org contractor directory

> **The R-19 data-model study is [R19-CHILD-TABLES-MEASURED.md](R19-CHILD-TABLES-MEASURED.md)**
> — 11 criteria against 5 shapes at 518,490 rows, written because the owner asked for
> his own ruling to be tested before it was built. It upholds the ruling against JSON
> (47x) and recommends a refinement of how it is implemented. **Not built — his call,
> recorded as `Q-13` in [BACKLOG.md](BACKLOG.md).**

**Design:** [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) · **Storage:**
[STORAGE.md](STORAGE.md) — **the mechanism is built** (`scrapex/snapshotbody.py`,
engine migration 0005), so nothing gates the crawl any more · **Seam:**
[GENERIC-FETCH-SEAM.md](GENERIC-FETCH-SEAM.md) · **Plan:**
[plans/2026-08-16-muqawil-contractor-source.md](plans/2026-08-16-muqawil-contractor-source.md)
· **Rulings:** [R-10](RULINGS.md#r-10--the-contractor-directory--three-rulings),
[R-11](RULINGS.md#r-11--a-contractor-directory-is-a-separate-table-and-a-table-like-any-other),
[R-12](RULINGS.md#r-12--one-row-with-a-button-that-flips-it)

**Landed:** what muqawil knows about its own pages (#202) · reading a contractor
off the page (#203) · a crawl whose output is evidence (#204) · the declared
frontier was half the crawl (#205) · a per-server governor (#206) · cards become
an approval candidate (#207) · the membership number is unique (#208) · names
stop coming (#209) · a 404 storm must not buy speed (#210) · a dataset is a table
like any other (#211) · the contractors appear among the datasets (#212) · the
Arabic half was a column and not a value (#220).

Then: the crawl study and its two corrections (#228 · #229) · a crawl that says
what it saw and where it stopped (#227) · the storage study (#230) · six source
briefs (#231) · **a snapshot says how it is encoded, and 4.55 GB becomes about
90 MB (#232)** — the compression mechanism itself.

**In flight: the partitioned listing crawl** — built, verified against the live
directory, and **running** into this installation's own warehouse; see the section
below. It carried two rulings with it,
[R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)
and [R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema),
and a fixed upgrade path ([OP-23](BACKLOG.md), closed). The track's one remaining
decision is DEC-10 in [BACKLOG.md](BACKLOG.md).

> **Why #210 mattered more than its size suggested.** `HttpFetcher` sends
> conditional requests, so an unchanged page answers **304 with no body** — the
> fastest answer a server can give. Without the ratchet, every re-crawl widened
> on its own emptiness: the #206 governor let 404/301/500 fall through as
> `Strain.NONE` and feed the clean run.

**The full `LISTING_ONLY` pass has run, and it is in the warehouse.** Verified
against the live database on 2026-08-20, not taken from a conversation:

```
generic_record            11,059 contractors
generic_page_snapshot      1,728 pages — 864 English AND 864 Arabic
generic_record_revision   34,550
engine db                    796 MB + a 393 MB WAL   ← 2026-08-20 07:0x
```

**Read the WAL as part of the size.** The figure above was `835 MB` when it was
first written a few hours earlier, and the file has moved since — a bare total goes
stale the same day. What matters is that **393 MB of it is an unmerged write-ahead
log**: `~1.19 GB` on disk today, and a checkpoint will move most of that into the
main file rather than reclaim it. That is the measurement `DEC-9` is arguing about.

**The Arabic snapshots were merged on 2026-08-20**, and they carried the #220
repair with them: four of the seven declared bilingual pairs had been NULL in
all 11,059 rows. All seven now hold values —

```
company_name_ar 97.9% · contractor_classification_ar 98.0%
card_company_size_ar 98.0% · card_status_ar 98.0%
card_city_region_ar 89.5% · card_training_credit_hours_ar 98.0%
membership_level_ar 0.2% (as its English half)
```

**And `/source/contractors` renders.** It answered 404 until #220 — #212's leak
one layer up, the page asking the manifest where the API had learned to ask the
catalogue too. Confirmed in a browser: 20 rows painted, 5,000 in the grid, and
`grid.js`'s EN/AR switch flips all seven pairs.

**HOW MANY CONTRACTORS EXIST, measured and not converged.** The sweep ran six
passes over the English listing, 8h37m:

| pass | new | total |
|---|---|---|
| 1 | +11,191 | 11,191 |
| 2 | +3,960 | 15,151 |
| 3 | +1,334 | 16,485 |
| 4 | +547 | 17,032 |
| 5 | +189 | 17,221 |
| 6 | **+62** | **17,283** |

It **stopped at its pass ceiling, not at convergence** — the sixth pass still
brought 62 names never seen before, so an unknown number remain unseen. The
warehouse therefore holds **11,059 of 17,403 — about 64%**. That denominator is
[DEC-11](BACKLOG.md)'s, `(871−1)×20 + c` from two requests; the sweep's "at least
17,283" cost 8h54m to reach a smaller and less exact answer. The sweep stored no
snapshots and read one language only, deliberately (it needed ids, not values), so
the ~6,344 known-missing contractors have **no evidence and no Arabic half** —
closing that gap is a new bilingual crawl, and DEC-9 argues it should follow the
compression migration rather than precede it.

**The storage question that gated the crawl is answered and built.** `docs/STORAGE.md`
measured what retention costs and what each option spends: the corpus is **4.55 GB**
raw, not the 6.4 GB projected from one sample, and `zstd` against one real page of the
same kind as a raw dictionary stores it in about **90 MB** — 187× on listings, 46× on
profiles, every row independently decompressible. `scrapex/snapshotbody.py` and engine
migration 0005 are that mechanism, and `snapshotcrawl` is its caller, so the pages the
crawl writes arrive compressed. **The 1,728 rows already on disk were deliberately not
rewritten**: `html_codec` defaults to `'plain'` rather than dropping an immutability
trigger to backfill 607 MB.

**AND THE METHOD IS NOW BUILT, AND HAS VERIFIED THE PARTITION AGAINST THE LIVE SITE.**
`scrapex/partitioncrawl.py` (new), `Cell`/`WHOLE` in
[scrapex/pagesource.py:67](../scrapex/pagesource.py), `MuqawilPartition` plus
`REGION_IDS`, `COMPANY_SIZES`, `cells()`, `listing_url()` and `read_ids()` in
`scrapex/sites/muqawil.py`, and — the piece that had never existed —
`tools/crawl_muqawil_listing.py`, a committed driver.

**`--plan` was run against the live directory on the evening of 2026-08-20, 114
requests, and it closed the study's last open question:**

```
listing now:  L=871  S=20  c=14  N=17,414
cells 56   pages 897  (+26 over the unfiltered 871)
declared 17,414 against the listing's 17,414 — exhaustiveness deficit 0
```

**Exact to the unit, by committed code rather than by a scratchpad.** DEC-11
predicted 897 pages and 3% overhead; both are confirmed. Region 13 × verysmall
came back at 128 again, and Riyadh × verysmall has grown 235 → **236**.

Two facts the live run produced that no fixture could have:

- **`region_id=8 & company_size=big` publishes ZERO contractors** and still serves
  a paginator, so `read_last_page` answers 1 and `read_ids` answers nothing. An
  empty cell's page 1 is *read and empty*, which is not the same fact as *never
  read* — and conflating them left that cell permanently unprovable, which makes
  the whole 56-cell partition permanently unprovable. Fixed, and both halves are
  mutation-proven. **21 of the 56 cells are a single page.**
- **A log line killed the run.** The sizing pass made all 114 requests correctly and
  then died on `UnicodeEncodeError` printing `→` to a cp1252 console. On the crawl
  itself that is hours of fetching discarded by a character. `say` can no longer
  raise.

**Sixteen mutations, sixteen killed**, per the rule that a guard is not trusted
until it has been mutated — including the two that would have made the method
worthless while looking like it worked: a witness comparing **bytes**, and one
comparing **sets** instead of sequences.

**IT HAS RUN, and the result corrected the method. 115 minutes, 2,141 requests:**

```
listing declared 17,417 rows over 871 pages
partition declared 17,417 over 56 cells — exhaustiveness deficit 0
distinct ids seen 13,727 — D = 3,690
cells proven complete 47 of 56          1,982 snapshots, all zstd-raw-dict
```

**The exhaustiveness audit came back 0 on live data** and 47 cells closed with `D=0`.
The deficit is concentrated in the **6 cells above the 31-page witness ceiling**
(D=3,680) plus three small cells short by 1, 1 and 8.

**CLOSED 2026-08-21: `D = 0`. 17,414 of 17,414 distinct ids.** The plan opened this
track at a deficit of 3,690.

The last 633 were held by a defect in the stop condition, not by the site. **A resumed
cell reads its ids back off disk** — that is what storing pages is for — so `gained == 0`
was true of a pure replay, and the dry-stop believed it:

```
region_id_1-company_size_verysmall: 3,125 of 4,699, D=1,574 [3 attempt(s), 5 requests]
```

Five requests for a cell holding 4,699 rows. The report was telling the truth and
nothing compared its two numbers. An attempt now counts as dry only if
`attempt.pages_read > 0`, in the loop and in `went_dry` both — and the five heavy cells
went and asked. Recorded in [LESSONS](LESSONS.md): *a stop condition that measures
progress must exclude the work it replays.*

**And conditional requests will not make the recurring pass cheap on this source.**
Measured with one request: no `ETag`, no `Last-Modified`, `Cache-Control: no-cache,
private` — a Laravel app minting a fresh XSRF token per response. `fetch_validator`
holding 0 rows is correct. `R-20`'s `content_hash` comparison still spares the history;
the bandwidth is not reducible here.

**And the 3,690 was partly the method's own fault, which is the finding.**
`provably_complete` required the witness AND the count — so a cell too large to hold
one cache generation was unprovable **by construction**, and the six heavy cells had
no route to closure at all. There are two independent proofs and only one was
implemented:

| | |
|---|---|
| **witness** | page 1 returns the same id sequence ⇒ one generation ⇒ pages disjoint |
| **count** | `distinct == declared`. A cell holding `N` cannot show `N` distinct ids without showing all of them — **no generation needed** |

Both now count, the report says which carried each cell (`[by witness]` / `[by count]`),
and a heavy cell gets `HEAVY_ATTEMPTS = 10` reads to close by counting. Written up in
[LESSONS](LESSONS.md) — *a proof that demands more than it needs fails exactly where it
is needed most*, and twenty-one killed mutations all agreed with each other because
they were all checking the same wrong rule.

**Two more report defects the run exposed:** it said *"the listing grew by -25 rows"*
(it **shrank**, 17,417 → 17,392 overnight), and a cell ending `235 of 236` could not be
told from a cell that lost a contractor. Both fixed; short cells are now re-sized so a
deficit inside the churn is named as churn.

**And the approval path could not take the crawl.** 897 stored page-pairs, **74
approved and 823 refused** — `region_id=0`'s four cells are exactly 74 pages, and they
are the contractors with no location, so they taught the dataset a 21-field schema and
every located contractor's page had 22. [OP-25](BACKLOG.md). The parser now declares
`CARD_FIELDS` the way `BILINGUAL_CARD_FIELDS` was already declared, for the same
stated reason; which of three routes reconciles the 74 pages already landed is
deferred by [R-25](RULINGS.md#r-25--the-crawl-method-is-settled-first-the-schema-and-retention-questions-come-last).

**Coverage is therefore 1,172 records — limited by an unresolved schema decision, not
by the crawl.** The crawl's own result is 13,727 sighted ids and 1,982 stored pages.

**Getting it a warehouse took two rulings of his and a fixed upgrade path.**
Priced from its own measurement: **897 pages × 2 locales + 170 = ~1,964 requests**, and
at the 2.51 s a request the sizing pass actually paid, about **1.4 hours**.

The home machine had no engine database and a pre-collapse `"mode": "split"` pointer
([OP-22](BACKLOG.md)). I asked which machine should hold the warehouse; he answered
that the premise was wrong — ScrapeX is a tool **many people install**, so an empty
installation is the product's normal first-run state and a warehouse is per
installation ([R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)).

**Then `scrapex carry-over` refused on his real data and I stepped around it**, by
pointing `SCRAPEX_DATA_ROOT` at a second location and crawling into an empty database
beside his full one — the exact trap `registry.py`'s own refusal message names, which
I had quoted an hour earlier. He refused that too:
[R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
— **a database is upgraded, never replaced**, because a shipped tool must carry its
users' data across schema changes, which makes the migration path a product feature
rather than maintenance.

**So the upgrade was fixed and run, and the crawl is in the real warehouse.**
[OP-23](BACKLOG.md) is closed: `Backfill` in `scrapex/databases/carry_over.py` supplies
what the engine schema requires and the split-era schema lacked, reusing migration
0058's own `legacy_unwitnessed` rather than a second literal. Verified on the live
installation, both sides counted:

```
price_observation 3,739 → 3,739     source_product_attribute 17,111 → 17,111
source_offer      3,739 → 3,739     change_event              7,410 →  7,410
source_variant    3,739 → 3,739     source_product              966 →    966
261 offers marked legacy_unwitnessed · 3,478 without a unit untouched · rows lost: none
```

The old files were opened read-only and are still where they were.

**And one defect was found in existing code and left standing on purpose.**
`snapshotcrawl`'s resume checks its skip inside `store`, which the walker calls
*after* the fetch — so a resumed crawl re-fetches every page and then declines to
store it. It saves the write and none of the hours its own docstring promises.
[OP-21](BACKLOG.md), not fixed here per **R-01**; `partitioncrawl` works around it
locally with `_Unstored`.

**The earlier study, kept because it is where the numbers came from — measured 2026-08-20.**
`region_id` × `company_size` is an **exhaustive 56-cell partition** of the
directory — 15,966 across regions 1–13 plus **1,437 under `region_id=0`**, the
contractors who publish no location at all, summing to 17,403 exactly. Each cell
publishes its own page count in its paginator's `»` link, so one request sizes it;
a slice re-read against its own first page proves it was read inside a single
cache generation. One cell has been closed end to end already — region 13 ×
verysmall, 128 ids, 128 distinct, `D = 0`. Cost of the whole listing that way:
**~1,065 requests, ~1.7 h**, against 18.4 h for a blind sweep that can never say
"complete". [DEC-11](BACKLOG.md) carries the numbers, the two corrections the
measurement forced, and what it still cannot see.

**The live database is `~/.scrapex/engine/scrapex-engine.db`**, per
`~/.scrapex/databases.json`. The older `~/.scrapex/marketlens/marketlens.db` is
110 MB, does not carry the generic tables at all, and will mislead anyone who
opens it looking for this data.

**Not in, and named so it is not mistaken for done:** the detail files
(coordinates, email, licences, interests) — a second crawl of ~22,000 requests ·
the ~6,344 contractors the sweep counted and nothing has fetched · the
compression migration DEC-9 asks for · the row-aware idempotency key DEC-10 asks
for, without which a corrected parser cannot be re-run over stored snapshots at
all.

**He ruled, and both flags are lit.** `FeatureKey.GENERIC_DATASET_CATALOG` and
`FeatureKey.GENERIC_EXTRACTION` are `True` at
[scrapex/features.py:54](../scrapex/features.py) and `:65`, both at **`PARTIAL`** —
one site, one dataset, listing pages only, and ~6,344 contractors the sweep counted
with nothing stored for them. Their written conditions were measured, not quoted:
11,059 rows through the approval path over 1,728 ingestions, every one
`status=success`.

> **And the reason given for lighting them was wrong, so it is corrected here
> rather than deleted.** This file used to say lighting them "makes `/datasets`
> appear in navigation". It does not, and there is no `/datasets` route — measured,
> not assumed.
>
> **SUPERSEDED 2026-08-21 (#245): they are switches now.** The paragraph above went
> on to say `is_enabled` has *"no production caller"*, which was true and is the
> defect item 3 of the six closed. The two callers are the two ADVERTISEMENTS, and
> they are not symmetrical: `_dataset_rows` puts a dataset in the source listing the
> panel draws, and `scrapex contractors --approve` is a shipped user-facing command
> since `REQ-24`. **The API routes stay outside the flags on purpose** — they are
> mounted on 127.0.0.1 so the slice can be exercised, and gating them would make a
> flag a kill switch for development instead of a switch over what is announced. A
> test asserts that distinction on the route table, because it is the line a later
> reader would tidy away.

### The six that finish muqawil, merged 2026-08-21 (#245)

His instruction after #243: run the six remaining muqawil engineering items in order.
Five are done. The sixth is built as far as a ruling of his allows.

| | item | outcome |
|---|---|---|
| 1 | `status = 'unavailable'` on a departed row | **done** — the whole chain had no caller, not even `record_absences` |
| 2 | the cost of sizing, in the output | **done** — computed, not the `~112` a module header remembered |
| 3 | `is_enabled` becomes a switch | **done** — two callers, and the routes stay outside |
| 4 | the slice scope | **the defect is fixed**; the walk moved into item 5 |
| 5 | the profile crawl | **wired, not run** — 34,834 pages, measured at **11.1 h** |
| 6 | `R-19` child tables | **the reader only** — the write is his to rule |

**Item 6's two blockers are not engineering.**
[R19-CHILD-TABLES-MEASURED](R19-CHILD-TABLES-MEASURED.md) recommends shape F and its own
last line says *"Not built. Awaiting his ruling"*; and the content comes from profile
pages, of which **none is stored**, because the registration is `listing_only`.

**Three written premises that measurement contradicted, all recorded where they were
written:**

| the premise | what was measured |
|---|---|
| the slice scope is "built, tested, never used" | it was also **wrong** — 17 cards paired against 34 URLs, and 17 indices pointed past the last card |
| the profile's five `<table>`s "are exactly" `R-19`'s five groups | five tables, **none of them Interests** — which is the biggest group, and not a table at all |
| the profile crawl is ~17.4 h | **11.1 h**, over 87 minutes of real six-worker crawling |

**And a new sub-question of his to answer:** how are the five groups NAMED? The table
detector returns `Table 1`…`Table 5`, and three of the five share one nearest heading —
so neither position nor the heading above them answers it. Whichever shape is ruled needs
that rule, and it does not exist.

**Four questions are open and are his** — O-1 to O-4 in
[RULINGS.md](RULINGS.md#open--awaiting-the-owners-ruling).

### The dataset cards said "no successful crawl yet" — FIXED 2026-08-22

He reported it from the panel: `17,304 products` and, under it, *"no successful crawl
yet"*, while the price sources beside them read *"Last crawled 16 August 2026"*.
[OP-44](BACKLOG.md) carries the whole measurement; the two facts worth having here:

**The missing `crawl_run` row was not the cause.** `_dataset_rows` handed the panel
`"last_success": None` as a literal, and `freshnessLine` prints that sentence for a
missing key — so writing muqawil a `crawl_run` row would have changed nothing on
screen. It could not honestly be written either: `crawl_run.source_id` is NOT NULL
into `source_site` and muqawil is in `site_profile`, which is the split `REQ-25`
holds and his to decide.

**So the date is derived from evidence already stored** —
`max(generic_page_snapshot.captured_at)` over the pages `generic_ingestion` says the
dataset was built from. Measured read-only on his live warehouse while the profile
crawl ran: `contractors` **2026-08-21T17:56:31Z**, `contractor_profiles`
**2026-08-21T21:44:48Z**, against 155 `crawl_run` rows none of which is muqawil's.
Six mutations, six killed. **The two registries are untouched** — this closes a
display, not `REQ-25`.

---

## Track 5 · The source queue — eight countries and three product classes, none started

**He set the order himself on 2026-08-20**, and for the first two it is a
precondition rather than a preference: each waits for the previous one to be
**finished completely**, where finished is his definition — «كلّ ما ينشره الموقع».
The fourth he added with «المزيد من المصادر ضفها الى القائمة» and named no position,
so it is appended in the order received.

| # | source | where the brief is | state |
|---|---|---|---|
| 1 | **muqawil.org** | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) | Track 2 above — 11,059 of 17,403 rows, listing pages only, profiles never crawled |
| 2 | **Balady engineering offices** | [BALADY-ENG-OFFICES.md](BALADY-ENG-OFFICES.md) | **Queued.** [REQ-14](REQUESTS.md#req-14--balady-engineering-offices-as-the-next-source-after-muqawil) |
| 3 | **UAE contractors and consultants** | [UAE-SOURCES.md](UAE-SOURCES.md) | **Queued.** [REQ-15](REQUESTS.md#req-15--the-uae-sources-third-in-the-queue) |
| 4 | **Egypt, Oman, Qatar, Bahrain, Kuwait** | [GULF-EGYPT-SOURCES.md](GULF-EGYPT-SOURCES.md) | **Queued.** [REQ-16](REQUESTS.md#req-16--egypt-oman-qatar-bahrain-and-kuwait-fourth-in-the-queue) |
| — | **Official diesel prices, 7 countries** — a PRODUCT source, not a firm directory | [DIESEL-PRICES.md](DIESEL-PRICES.md) | **Queued.** [REQ-17](REQUESTS.md#req-17--official-diesel-prices--a-product-source-not-a-firm-directory) |
| — | **Bitumen 60/70 prices, 7 countries** — a product source that **cannot be crawled** | [BITUMEN-PRICES.md](BITUMEN-PRICES.md) | **Queued.** [REQ-18](REQUESTS.md#req-18--bitumen-6070-prices--the-first-source-that-cannot-be-crawled) |
| — | **Reinforced-concrete materials, 7 countries** — cement, rebar, aggregate, water | [CONCRETE-MATERIALS.md](CONCRETE-MATERIALS.md) | **Queued.** [REQ-19](REQUESTS.md#req-19--reinforced-concrete-material-prices--its-turn-will-come) |

> **Four briefs, 8 countries, and not one of them started.** Saudi Arabia twice
> (muqawil and Balady), the seven emirates, then Egypt, Oman, Qatar, Bahrain and
> Kuwait. The queue is a queue, not a plan: none of it competes with finishing
> muqawil, which is what he said the priority is.

**The diesel-price list is a different KIND of source and is listed without a
position.** He classified it himself — **«مصادر منتجات»**, product sources. The
other four describe *firms* and land in `generic_record`; this describes *a product's
price over time* and lands in `price_observation` — the original spine of this
project, which muqawil never touched. It is also **7 pages against muqawil's
36,548**, about fourteen requests a month, so it is an afternoon rather than a track.

> **And it collides with `SR-6`, which is worth knowing before it starts.** `SR-6`
> says an unchanged price is confirmed, not appended. His rule §3 says never
> overwrite a previous price when a new month begins. If Oman's July price equalled
> August's, the gate writes nothing and the August **period** never exists. A
> period-keyed price has to key the gate on the PERIOD, not only the value.
> [DIESEL-PRICES.md](DIESEL-PRICES.md) carries the reasoning.

**And the bitumen brief cannot be crawled at all** — by its own conclusion, five of
its seven countries have no public official price, so its acquisition mode is a
written quotation to a producer. What this project can do for it is store a dated,
caveated observation that is never mistaken for a live market price. It is also the
**second** independent case against `SR-6`'s key: for diesel the key is the period,
for bitumen the commercial basis, because two observations can carry the same number
and different bases. [BITUMEN-PRICES.md](BITUMEN-PRICES.md).

**A third price brief makes it a finding rather than an observation.** The
reinforced-concrete materials brief types its sources explicitly and answers **No** to
*"can it populate `price_amount`?"* for an index, an approved-supplier list and a
specification. So: diesel says the append key is the **period**, bitumen the
**commercial basis**, concrete the **source type** — three products, three axes, three
briefs written separately. Recorded as [DEC-12](BACKLOG.md) before any of it is
collected, because a dropped period is not a wrong row a later fix corrects; it is a
row that never existed, in a table whose whole purpose is history.

**All three briefs are his, stored verbatim**, and they are in the repository rather than
in a conversation for a measured reason: he re-sent the muqawil column specification
on 2026-08-20 because he could not tell whether it had survived. It had. He should
not have to ask twice.

**Neither is a schema to implement.** Balady's brief says so in its own words —
*"Do not assume that any preliminary finding in this brief is correct"* — and demands
every statement be labelled **Verified / Inferred / Unverified / Not available**. The
UAE file is not even one source: its key finding is that **no single public federal
directory covers every emirate**, so the emirate and the regulatory authority are
part of a record's identity.

**Two things worth knowing before either starts**, so the work does not open by
rediscovering them:

- **Ask for the open dataset first.** Both files require checking for an official
  API or download **before** any browser automation. It is the cheapest question
  available and it can delete the crawl. muqawil's equivalent was answered late, and
  the answer was no — three dead ends recorded in [DEC-11](BACKLOG.md) so nobody
  spends those requests again.
- **Abu Dhabi DMT may be better-shaped than muqawil.** It publishes `firm_name` and
  `firm_name_ar` **in one record**. On muqawil the Arabic half is a second full crawl
  — 871 listing pages and 17,403 profiles again — matched by page-order index
  because one label is spelled `رقم العضويه` with `ه`. A bilingual record halves
  the requests and removes that risk.

---

## Track 4 · What CI actually costs, and the tier a documentation change needed

**Measured 2026-08-19**, because PR #214 was documentation only and took the two
slowest runs of the previous twenty:

| | |
|---|---|
| `test` job, median of 15 full-scope runs | **12m49s** |
| of which the `pytest` step | **703s — 92%** |
| `lint` · `contract-parity` | 21–26s · 14–16s |
| PR #214's two runs | **14m21s and 14m40s** |

The slowness is entirely inside one step. Four causes, ranked, with what was done:

1. **A documentation change ran the whole suite.** The scope filter knew
   `extension/` and `docs/` only, and #214 changed `CLAUDE.md`, `ENGINEERING.md`,
   `README.md`, `.gitignore` and a `.claude/` file — none of which match `^docs/`.
   **Fixed:** a third `docs` tier, a `pytest.mark.docs` marker on the nine files
   that read a document, and `tests/test_the_docs_gate_is_complete.py` to keep the
   set honest. **178 tests in 30.6s** against 451s for the whole suite locally.
2. **`SCRAPEX_FULL_MIGRATIONS=1` was replaying 61 migration files 927 times per
   run** — real `migrate()` is 396ms against a 3.6ms template restore, so roughly
   350s of the 703s. **Moved** to a parallel `migration-authority` job. The
   guarantee did not move: the same suite still runs against the real stream.
   ⚠ **It is not a required check until someone makes it one** — until then a
   migration-stream failure will not block a merge, which is weaker than the
   inline variable it replaced.
3. **Nothing was cached.** No `cache: pip`, nothing on `~/.cache/ms-playwright`.
   **Both added.** Worth ~13s of steady browser download; the 104s apt spike seen
   on 2026-08-19 is the runner's package mirror and no cache reaches it.
4. **`tests/test_panel_dom.py` costs 236s of the 703**, about 120s of it literal
   `wait_for_timeout(500)` on 164 panel opens. **Not touched** — the file's own
   comment explains why some animation waits are load-bearing, and telling them
   apart is its own task. Recorded here rather than done.

**And a guard was blind.** The step that refuses a silently-skipping browser suite
grepped `importorskip("playwright"` **with the closing quote**, so
`tests/test_grid_dom.py:24` — which writes `importorskip("playwright.sync_api")` —
never matched, and its 20 tests were invisible to it. One character. Fixed, and
the guard now finds ten suites instead of nine.

The scope rule itself is now tested:
`test_the_workflows_documentation_pattern_admits_exactly_what_it_should` lifts the
bash pattern out of the YAML and classifies fifteen paths with it, over half of them
cases that must **not** be admitted — and it pins the **polarity** of the two
decision lines, because an adversarial pass inverted `! grep -qvE` to `grep -qE` and
every assertion stayed green.

### What an adversarial review caught before this merged, and the worst of it was mine

Twenty agents over four lenses, sixteen refutation verdicts, **eight findings
survived** — three of which had already been found and fixed by hand. The other
three:

1. **A blocker of my own making.** Moving the scope computation into its own job made
   `fetch-depth: 0` look unnecessary and I wrote "Shallow is enough here now". It is
   not: `tests/test_the_privacy_policy_is_true.py:433` and `tests/test_version.py:231`
   both **skip** rather than fail on a grafted clone, and `-q` reports a run full of
   skips as green. Proven by experiment — edit `docs/privacy-policy.md`, leave its
   date, and full history fails while `--depth 1` passes. **The repository had already
   learned this twice**, in `publish-docs.yml` and `release-extension.yml`.
2. **`git diff --name-only` reports only a rename's destination**, so a file moved out
   of `scrapex/` into `extension/` or `docs/` classified as the narrow scope.
   `--no-renames` added; it can only widen.
3. **The pattern guard could not see the logic inverted.** Now pinned.

**And the structural fix found a fourth instance nothing else had.**
`tests/test_the_workflows_check_out_enough_history.py` reads every workflow, finds
every job that runs pytest, and requires full history — and it immediately failed on
`release-engine.yml`'s build job, which runs the **whole suite** at depth 1. Both date
guards have therefore been skipping on **every engine release**. Fixed here.

Why the mistake recurred is the part worth keeping: the requirement lived as prose
beside the file that *needed* the history, never on the jobs that had to *provide* it.
See [LESSONS.md](LESSONS.md#7--a-document-can-drift-into-the-opposite-of-the-code).

---

## Track 3 · The version debt

**Ruling:** [R-06](RULINGS.md#r-06--version-moves-with-every-merged-pull-request)
(every merged PR raises `VERSION`) · **Blocked by:**
[R-07](RULINGS.md#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert)

`VERSION` is `0.2.2` at [scrapex/version.py:76](../scrapex/version.py); the
manifest is `0.2.2` too. It last moved at `adf31b2` on **2026-08-10**, and as of
2026-08-19 there are **62 commits since** — the count was 48 when the ruling was
written and 58 two days ago. It grows every time this is deferred.

**The blocker, verified 2026-08-17 and still present:**
`"latest_extension_version": VERSION` at
[scrapex/version.py:483](../scrapex/version.py) and
[scrapex/webui/app.py:1671](../scrapex/webui/app.py), drawn by
[extension/app.js:607](../extension/app.js) and `:641`.

> **Re-verified 2026-08-19, and three of these citations had already drifted.**
> `webui/app.py` was **1355**, now 1375 — #211 and #212 inserted twenty lines
> above it. And `LATEST_SOURCE`/`UPDATE_INSTRUCTIONS` were written as `:289` and
> `:292` when they have been at **282** and **285** all along; `version.py` has
> not been touched since, so those two were wrong the day they were written.
> **This is [REQ-08](REQUESTS.md#req-08--a-guard-against-the-documents-going-stale)
> arguing for itself within 48 hours** — and it is precisely the class option (b)
> catches. Bumping `VERSION` while
that stands makes the panel's *"your extension is older than the engine"* card
**permanent and false**.

**Do this in its own PR:** drop the advert (plus `LATEST_SOURCE` and
`UPDATE_INSTRUCTIONS`), keep the derived gate, add a guard that fails if
the engine ever answers for the extension's head again. Then bumping is
mechanical.

**Two more things belong in that PR:**
- Fix `LATEST_SOURCE` `:282` and `UPDATE_INSTRUCTIONS` `:285` — the drawn numbers,
  not the ones this file used to quote.
- `robots_per_source` is dated 0.2.2 and cites no commit; the ledger's own guard
  fires, correctly. Read out of `git log`, both `-S"crawl_obey_disallow"` and
  `-S"source-edit-robots"` name `adf31b2` alone — write `commit="adf31b2"`.
- ~~[ENGINEERING.md](../ENGINEERING.md) **W4** states the superseded
  per-capability rule.~~ **FIXED 2026-08-17.** It was stale twice: the trigger,
  and a claim that `extension/manifest.json` is an enforced mirror — which PR
  #112 undid and `tests/test_version.py:536` now actively guards against. W4
  would have sent a reader into re-welding the two numbers.

---

## Named gaps — recorded, not forgotten

- **`behaviourVersion` is ScrapeX's own bookkeeping, not a signal.** mbiXaddin has
  no such field; both numbers live here and one commit raises both. The real fix
  is [HANDOFF-mbiXaddin-contract-producer.md](HANDOFF-mbiXaddin-contract-producer.md).
  What *does* look upstream is
  `test_no_cited_addin_file_has_moved_since_the_reading`, which watches the `.cs`
  files the reading cites and has already found three moved.
- **Two OAuth clients, therefore two grants** — sign-out cannot reach the
  Chrome-Extension grant on a primary account, and must not try. See
  [LESSONS.md §6](LESSONS.md#6--two-oauth-clients-therefore-two-grants).
- **HTTP 400 counts as revoked**, and neither `authorize` nor `revokeToken` has a
  deadline. Same section.
- **[REQ-04](REQUESTS.md#req-04--every-setting-moves-into-the-extension) — the ten
  settings move into the extension — was ruled 2026-08-01 and is still unbuilt,
  measured 2026-08-20.** Parked behind a review and then lost from view; verified
  untouched with `git log -S'excel_folder' -- scrapex/webui/templates/ extension/`,
  which returns nothing since the ruling. It is the entry that justified building
  [REQUESTS.md](REQUESTS.md). The count of days it has sat is deliberately NOT
  written here: the number that used to stand in this line was already stale by
  the time anyone reread it, which is why the rule is a date and never a duration.
- ~~**Two requests await the owner's ruling:** REQ-08 and REQ-09.~~ **BOTH RULED
  AND BUILT 2026-08-19** — he took both recommendations
  ([R-15](RULINGS.md#r-15--the-documents-are-guarded-by-a-test-not-by-good-intentions),
  [R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file)).
  `SR-1`–`SR-23` now live in `RULINGS.md` with every number intact and
  `BACKLOG.md` §1 is a pointer; `tests/test_the_documents_cite_what_they_claim.py`
  guards the citations. **Six citations across four documents were wrong and are
  corrected** — see [LESSONS.md §7](LESSONS.md#7--a-document-can-drift-into-the-opposite-of-the-code).

---

## Where the older plans went

Seven plans and a 1,015-line findings file lived in `~/.claude/plans/` — on one
machine, under one account — until 2026-08-17. They are now in
[plans/](plans/README.md). Read that index before assuming a track has no plan.
