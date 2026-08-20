# State — where the work stands

**Last updated: 2026-08-20.** `main` is at `72f93a8` (#218).

This is the document that is **wrong the moment it is out of date**. Update it
when a phase lands, a PR merges, or the owner rules — in the same pull request as
the work it describes (**C2**, [../CLAUDE.md](../CLAUDE.md)).

**For what the owner has asked for and where each request stands, see
[REQUESTS.md](REQUESTS.md).** This file tracks the *work in flight*; that one
tracks *his requests* through Captured → Ruled → Planned → In flight → Done.

---

## Open pull requests — none

**The board is empty for the first time in this file's short life.** Nine merged on
2026-08-20, in this order, each on green CI under
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
   (`extension/app.js:1594`) and `saveSourceColumns` (`:1633`), speaking the same
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

**Design:** [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) · **Seam:**
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

**In flight: PR #220.** The track is otherwise waiting on decisions — the two
feature flags below, and DEC-9/DEC-10 in [BACKLOG.md](BACKLOG.md).

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

**And that crawl now has a method that can prove itself, measured 2026-08-20.**
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
> appear in navigation". It does not. `is_enabled` has **no production caller** in
> the engine or the panel, and there is no `/datasets` route — measured, not
> assumed. What the flags govern is what `/api/features` **publishes**, so lighting
> one is a *claim* about a capability rather than a switch that reveals it. The
> capability itself already works without them: `/source/contractors` serves today.

**Four questions are open and are his** — O-1 to O-4 in
[RULINGS.md](RULINGS.md#open--awaiting-the-owners-ruling).

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
[scrapex/version.py:477](../scrapex/version.py) and
[scrapex/webui/app.py:1439](../scrapex/webui/app.py), drawn by
[extension/app.js:599](../extension/app.js) and `:633`.

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
