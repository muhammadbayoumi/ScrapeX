> # ⚠ FROZEN HISTORY — NOT A LIVE RULE
>
> This document was retired on **2026-09-04** on the owner's instruction. It is kept for
> one reason only: **881 references in the code cite the numbers below** (`R-84`,
> `REQ-57`, `OP-145` and their kin), and a comment whose reason cannot be looked up is
> worse than no comment.
>
> **Nothing here is maintained, and no new number is ever issued from it.**
> How we work now is [CLAUDE.md](../../CLAUDE.md); open work is `gh issue list`; what is
> in flight is `gh pr list`; why a line exists is the comment beside it and
> `git log --grep`.

# State — where the work stands

**Last updated: 2026-09-04.** `main` is at `ef3121d` (#320), and **there are ZERO open
pull requests** — checked against GitHub, not inferred from this file. **Thirty-four merges**
landed after this line last said `ef86a19` (#287), measured with
`git rev-list --count ef86a19..origin/main` rather than carried, and every one of the
thirty-four is a squash commit naming its PR. **And this conflict is
the argument itself:** resolving it once, one side said `f1844af` (#261) with "fifteen"
and the other `d10e974` (#258) with "thirteen", and both were already wrong before
either could be read. A commit pointer written into prose is stale by the time it is
read: `git log --oneline -1 origin/main` is the answer that cannot be — **and this
very line has now proved it nine times**, reading `4615a14` with #251 and #252
already in, then `5f63bb0` with #254 in, then `451468d` with #255 in, then
`31c369e` with #258 in, then `f1844af`, then `467a3ac` with #265 in, then `759a9df`
with #287 in, then `ef86a19` **six days and thirty-four merges stale**, and now this.
Each correction is the argument for the sentence rather than a counter-example to it.

> **THE NINTH CORRECTION IS THE LOUDEST ONE, AND IT WAS NOT FOUND BY READING THIS FILE.**
> It was found by auditing **228 branches against `main`** on 2026-09-04, which is also how
> `R-85`, `R-86` and two of his requests were discovered sitting on branches with **no pull
> request at all** — see the section below. This file said "open PR" about six things that
> had merged and said nothing about four that had not been proposed. **A status document
> that is only corrected when somebody happens to edit it is not a status document**, and
> the audit that fixed it is the kind of thing `C2` means by a stale document being a bug.

**THE ENGINE ON GITHUB IS `engine-v0.4.8`, CUT 2026-09-04 ON `9b5d920`.** The first
release since 2026-08-23, and **the first that carries `R-84`'s squashed baseline**, so
**v17 is a ceiling a released engine can reach for the first time** — which is what
`OP-134` asked for and what closes it. He asked for it directly — *«اقطع الوسم عند
baseline الحالى»* — and gave the standing rule with it
([R-87](RULINGS.md#r-87--no-version-sits-unreleased--the-published-engine-follows-the-code-and-the-lag-is-the-defect)):
**no version sits unreleased.** `REQ-57`.

The gap it closed, measured: **60 commits and five unreleased `VERSION` bumps over twelve
days**, 38 of those commits in shipped code. And the blocker predicted for it did not
exist — the release build runs the suite on `windows-latest`, `OP-98` fails there on HIS
machine, and a `dry_run` of the workflow proved that same step **green on GitHub's Windows
runner**. `OP-98` is corrected in place rather than left as written.

**AND THE MECHANISM FOR `R-87` IS BUILT, not promised**:
`.github/workflows/tag-the-release.yml` tags the SHA CI passed and starts the release
itself, so the next `VERSION` bump publishes without anybody remembering. He chose it over
a guard — *«واعمل workflow يقطع الوسم تلقائيا»*. One precondition is his:
`default_workflow_permissions` on this repository is **read**, so if the workflow's own
`permissions:` block is ever capped by policy the tag push fails and says which setting.

**AND WITHIN THE HOUR HE INSTALLED IT AND FOUND `OP-144`.** The refusal works exactly as
shipped — it names `R-84`, changes nothing, and prints no command — **and there is nothing
he can press**: the console sends him to the engine's page, which is not served because
the engine did not start, and the panel's only database command is the upgrade that
correctly refuses. `storage.start_fresh` is the remedy and its only door is inside the
thing that will not start.

**What a person installing 0.4.8 gets that 0.3.1 did not**: a below-baseline warehouse
refused with the reason and no command line (`OP-135`), no full copy of the warehouse per
launch and the copies bounded by his own policy (`OP-136`), an atomically written backup,
and a deletion ordered by the stamp rather than the file clock (`OP-141`).

> **The paragraph that follows is the record of the PREVIOUS release** and is kept for its
> reasoning about `OP-32`, not as the current state.

**THE ENGINE ON GITHUB WAS `engine-v0.3.0`, AND IT WAS CUT ON 2026-08-22.** He asked for it
directly — *«اقطع الوسم»* — after reading the finding that the panel was offering
`0.2.1`, the build whose bare invocation printed nothing. The tag sits on `451468d`,
which is this `main`; `scrapex/version.py:76` and the `pyproject.toml` mirror both
read `0.3.0` there. **Thirteen days and two `VERSION` bumps of unreleased engine,
closed.** `OP-32` · `REQ-28` · guarded by
[#253](https://github.com/muhammadbayoumi/ScrapeX/pull/253) — **open, not merged**
([R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)).

> **SUPERSEDED 2026-09-04 BY [R-87](RULINGS.md#r-87--no-version-sits-unreleased--the-published-engine-follows-the-code-and-the-lag-is-the-defect),
> AND KEPT UNDER `C4`.** He ruled that no version may sit unreleased — *«حتى لا يكون هناك
> تاخير بين الكود والمنشور»* — so the paragraph below is no longer the standing
> expectation. What it says about `OP-32` remains true and is why the distinction was
> drawn; what it says about a gap being *normal* is what he reversed, having measured
> this one at **60 commits and five unreleased bumps over twelve days**.

**AND THE NORMAL STATE FROM HERE IS SOURCE AHEAD OF PUBLISHED, WHICH IS NOT `OP-32`
RETURNING.** `VERSION` moved on a contract change under the rule in force then (now replaced by [R-77](RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build), which removes the engine's version entirely))
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
(packaging was not a contract change under the rule in force then, since replaced by
[R-77](RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build)). **Cutting the tag is his call**, and until he does
there is nothing installable that serves a page.

**AND ON 2026-09-04 HE ASKED WHY THE ENGINE DOES NOT WORK, AND THE ANSWER WAS NOT THE
ENGINE.** *«اريد مراجعة لماذا لا يعمل المحرك ؟»* — measured read-only on his warehouse on
this machine: **`PRAGMA user_version = 10` against a baseline of v17 with no migrations at
all**, so `R-84`'s refusal is correct and total, and every start printed one line and made
a **316,760,064-byte** copy first. The engine's own code is healthy — booted from source on
a fresh v17 database, `/api/health` answers `ok: true` and `GET /` returns **200**.

**He ruled the data away rather than have it upgraded**: *«لا ترقى القاعدة لا مشكلة فانا لا
احتاج الداتا عليها»*. What he asked for instead was whether the failures recur *«من اول
baseline الحالى»* — from the current baseline onwards — and the answer is measured in
`OP-133` and `OP-134`: **a squash strands a warehouse if and only if that warehouse is
behind the head when it happens**, both sides of which are already tested, and **the gate
cannot see the condition** because it reads a manual publication flag whose own docstring
excludes his two machines. `OP-134` is why one of them is reliably behind: **every
published engine tops out at schema v10**, so a machine on a release can never be at the
head. Both are his calls — a guard he set, and a tag.

This is the document that is **wrong the moment it is out of date**. Update it
when a phase lands, a PR merges, or the owner rules — in the same pull request as
the work it describes (**C2**, [../CLAUDE.md](../../CLAUDE.md)).

**AND THE OPENING LINE ABOVE IS NOW ITSELF A CASE STUDY, filed as instance 3 in
[LESSONS §14](LESSONS.md).** It read `31c369e` while `main` was `d10e974`, and
`4522158` landed while that was being written. The line is not being rewritten to
chase the pointer — the sentence it already carries is the right answer, and
`git log --oneline -1 origin/main` remains the only one that cannot rot.

### The engine can now say which code it is running — **merged as `4868f91` (#266)**

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

### The engine's page is where the engine lives now (2026-08-30, `REQ-50`) — **merged as `1d8816d` (#293)**

**The incident.** His engine was running code older than the code on disk. The panel
detected it and said so — the Build row rendered `Restart needed` with the engine's own
sentence beneath it — and **there was nothing on that page to press**. Because the engine
kept serving the old tree, the bundle build lock from `#288` was not active, two builds
overlapped, and a **0-byte archive reached Google Drive as though it were a backup**.

**Measured, not assumed.** `POST /api/engine/restart` had **four** callers and none of them
on the Engine page: two in the panel's Settings and two on the engine's own web pages. Across
the product, **11 `/api` routes are called from both surfaces**, **31 live routes only from
the engine's own pages**, **18 only from the panel**, and **eight settings can be changed
nowhere but the engine's web UI**.

**He ruled [R-80](RULINGS.md#r-80--one-feature-one-place-and-a-read-only-second-copy-is-still-a-second-copy)
on that count**, retracting his own concession of 2026-07-29 that the engine's web page could
stay display-only: *«لا اريد حتى صفحة الويب للعرض فقط ... اريد فقط الميزة فى مكان واحد
محدد»*. `test_the_web_page_still_shows_what_the_engine_holds` currently asserts the retracted
rule and is inverted by whichever change first moves a value off that page.

**Landed on the branch:** the duplicate restart implementation deleted and the survivor moved
onto the Engine screen; its confirmation budget raised from 30 s to the engine's own worst
case of 121.5 s (`OP-112`); `schema_lag` carried across `checkEngine` so the *"Database is
behind the engine"* banner can appear for the first time (`OP-113`); the spec-row grid
repaired so a version stops printing one character per line (`OP-114`).

**AND THE POWER SWITCH IS NOT IN IT, for a reason worth reading before anyone tries.** He
asked for one — *«اريد Engine power حيث ايقافه ثم تشغيله تعنى restart»* — and the ON half is
already built as the native `START_ENGINE` command. The OFF half needs `POST /api/engine/stop`,
which exists in no form. **Adding it turns `test_the_contract_has_not_moved_without_the_version_moving`
red**, because the endpoint fingerprint moves — while
[R-77](RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build),
merged the same day, says the engine has no version to move. **The ruling is in force and the
gate has not been rebuilt**, so the route waits on either that work or his word. Named as a
precondition rather than worked around.

**A stop is safe to build when it can be built**, and that was measured rather than assumed:
`reclaim_orphaned_jobs` re-queues anything left `running` at the next start, and
`tests/test_the_engine_survives_being_killed.py` kills a real engine mid-crawl with no chance
to clean up and proves it. What a hard kill still costs is the journal for the source in
flight, so the design drains before it exits rather than mirroring restart's `os._exit(0)`.

---

## RESUME HERE — written for the other machine, 2026-08-22

He works from two machines and asked to continue from the other one, which has neither
this session's context nor this warehouse. Everything below is the whole handover.

> ### 2026-08-27, end of day — the newest three facts, because everything under this
> ### heading was written five days earlier
>
> **Step 1 of the muqawil plan is applied to his live warehouse.** `#279` merged at
> `11773ab`; `0013` reached the warehouse through the engine's own backup-then-migrate path
> and `--reapprove-schema --repair` moved the rows. Verified on a second read-only
> connection: `v4` approved with **27 fields and 17,371 `active` rows**, **zero active rows
> on a retired version**, `OP-64`'s 14 impostors still `status='retired'` on `v3`, 74,574
> revisions unchanged, `foreign_key_check` clean. Through the engine,
> `/api/table/contractor_profiles` serves **33 columns and zero `x_*` keys**.
>
> **His engine had been serving from an unmerged branch's worktree** —
> `C:\tmp\ScrapeX-organization-enrichment`, `0.3.4`, migration ceiling `0012`. That is how
> the warehouse reached `user_version 12` before `0011`/`0012` were on any merged branch, and
> **`POST /api/engine/restart` cannot repair it** because it relaunches from the running
> process's own `__file__`. Measured in [OP-88](BACKLOG.md). It now runs `0.4.2` from the main
> checkout, started through `ScrapeX Engine.vbs`.
>
> **AND THE SOURCE REGISTRY IS ONE, with a second stream retired behind it.** `R-62`
> executed as migration `0014`: `site_profile` merged into `source_site`, eight rows
> repointed across four tables, 31 triggers before and 31 after, `foreign_key_check` clean,
> 6.5 s on a copy of his 1,421 MB warehouse. `R-71` records the three decisions the merge
> forced and corrects two of `R-62`'s own measurements.
>
> **Then he ruled `R-72`**: nothing is kept because deleting it is work. `db/migrations/`
> — 61 files, frozen since 2026-08-04 — is gone, with `db/schema.sql`, a duplicate migration
> runner and five tests that guarded deleted migrations. **No test fixture moved**:
> `db.migrate` delegates to the engine runner instead of owning a stream.
>
> **The deletion found three defects the duplication had been hiding** (`LESSONS` §23), the
> worst of them that **a new installation has never had a default retention policy** — the
> seed row lived in the retired stream and the schema derivation carried `CREATE` and not
> `INSERT`. His own warehouse has the row and was checked first; `0015` is the repair.
>
> `VERSION` → **0.4.4**. `R-69` reserves `0.5.0` for `feat/organization-enrichment`
> and that ruling was not overridden here.
>
> **STEP 2 IS BUILT, BOTH HALVES.** The root half shipped in `#281`; the second half is
> `0016` plus `scrapex/runs.py`, and he ruled `R-75` for it: **one run table for
> everything.** A snapshot now names the run that fetched it with a typed `run_id`, and
> `row_state` reads a row against THAT run instead of against `MAX(last_seen_at)`. The
> latest run is asked THROUGH THE ROWS -- `MAX(run_id)` for the source would call every
> profile row `absent` the moment a listing sweep finished, while the site still lists
> every one of them. Fifteen new guards, three mutations, three killed.
>
> **`R-52` IS SUPERSEDED BY `R-75`, and its text stays** (`C4`). Its measurement --
> *"`crawl_run` is the price path alone"* -- was true on 2026-08-24 and expired when
> `R-62`'s merge (`0014`) put `muqawil_org` into `source_site`. A second run table would
> then be exactly what `R-72` forbids.
>
> **`OP-99` is the honest remainder:** the price path still opens and closes its own
> `crawl_run` inline in `ingest.py`, not through `runs.py`. Recorded, not slipped in.
>
> **STEP 5 IS BUILT IN THE PARSER** — `R-55`, absence rather than a placeholder. Two rules,
> both re-measured on his warehouse on 2026-08-29 before a line was written:
>
> | field | the placeholder | measured now |
> |---|---|---|
> | `logo_url` (`contractors`) | the bare directory `.../companyLogo/`, no filename | **13,042 of 17,304 — 75.4%**, against 4,262 distinct real filenames. `default.jpg`, the string the document asks for, appears **zero** times |
> | `latitude`/`longitude` (`contractor_profiles`) | the site's default pin `24.4493518, 46.6220053` | **14,621 of the 17,352 rows that carry a coordinate — 84.3%** |
>
> Nineteen guards, **four mutations, four killed** — including the OVER-correction, a
> radius instead of the exact pair, which would eat the 30 rows on `(24.7135517, 46.6753)`
> that are ordinary real data.
>
> **`R-45` IS UNTOUCHED and a guard proves it**: `read_coordinates` still reports the
> default pin faithfully. What changed is only whether it is promoted to a column.
>
> **HIS EXISTING 27,663 ROWS STILL CARRY THE PLACEHOLDER**, and that is a separate
> decision because it writes to his warehouse. The parser is honest from the next parse
> onward; the stored rows are not. Measured cost of each route is in the pull request.
>
> **Next after this is step 3** (`R-69`), then `R-68`'s reconciliation.
>
> The root half, for the record — `R-54`, on his order 1 → 2 → 5 → 3 (`R-69`). A
> confirming pass now moves the record's own `last_seen_at`, which is the field the state
> comparison rests on; `approve_candidate` returned seventy lines above the only write that
> moved it. Nine mutations, nine killed, 993 tests green across 45 suites.
>
> **And the State column is already wrong on screen, not merely predicted.** Computed with
> the panel's own `sightings.row_state` on 2026-08-27: `contractors` reads **`absent` on
> 17,221 of 17,304 rows — 99.5%**, because its sighting ledger is already full (17,417) so
> the `MAX(last_seen_at)` comparison runs, and only the 48 rows written in the crawl's final
> second survive it. `contractor_profiles` escapes with `unsighted` only because its ledger
> is empty.
>
> **The second pull request needed a table, and my earlier note here
> > was wrong.** It said the comparison needs no migration because
> > `generic_page_snapshot.crawl_run_ref` carries a value on 55,313 of 57,041 snapshots. The
> > column exists; **it is not a run identity.** Measured 2026-08-27:
> >
> > - **141 distinct values** across 55,313 snapshots — per CELL for listing crawls
> >   (`listing-2026-08-20` alone has 64, `residual-2026-08-21` 40, `deficit-2026-08-21b` 33)
> >   and per crawl for the profile run (`profiles-2026-08-22`, one ref for 34,834 pages).
> > - It **joins to nothing**: zero matches against any column of `crawl_run` or against
> >   `crawl_job.job_ref`. It is the free-text `--run-ref` the operator types, and one stored
> >   value is literally **`R`**, on two snapshots.
> > - Simulated: comparing against "the run of the most recently captured snapshot" would read
> >   **`absent` on 17,030 of 17,304** listing rows and **17,384 of 17,385** profile rows —
> >   worse than today, not better.
> >
> > `R-52` had already measured this and he had already chosen the answer: **option B, a generic
> > crawl-run table**, because `crawl_run` is the price path alone and its `source_id` points at
> > `source_site`, where muqawil does not exist. So the second half is a migration plus a writer
> > plus the comparison — and its `source_id` problem is `R-62`'s registry merge, the same thing
> > that blocks the crawl button.
>
> He ruled that rows whose run cannot be established read `unsighted` -- a standing state
> meaning "stored before the ledger existed", not `absent`, which would claim the site
> stopped publishing a contractor it still lists. 1,728 snapshots on his warehouse are in
> exactly that position.
>
> **AND `crawl_run_ref` STAYS.** It is what `--run-ref` resumes an interrupted crawl on.
> `0016` adds a typed `run_id` beside it rather than overloading a free-text label.

### The code and the decisions are in the repository. The DATA is not.

**Merged and done:** the six muqawil engineering items (#245), four rulings of his
executed (`R-38`…`R-41`), and the engine release gate (#244).

**His warehouse on THIS machine, measured after the profile approval:**

| | |
|---|---|
| the listing | 17,417 sighted of 17,414 declared — `D = 0` **for the sighting ledger**, which is not the population: see the reconciliation below, where the union is **17,452** |
| `generic_record` | **17,304 listing rows** and **17,385 profile rows** (14 of them retired by `OP-64`) — 17,264 before `R-51`'s recovery approval, which added exactly the 121 it was measured to add |
| `generic_page_snapshot` | **36,358 profile snapshots**, covering **17,452 distinct contractor ids — the whole union, with nothing left to fetch** |
| `classification_node` | **243** nodes, levels `{1: 12, 2: 39, 3: 192}` |
| `generic_record_node` | **391,761** memberships — `R-38` proved on real data |
| datasets | `contractors` and `contractor_profiles` |
| schema | **v13**, 2026-08-27 — `0013` lifted `UNIQUE (dataset_definition_id, schema_hash)` so two versions may share a shape across time ([R-70](RULINGS.md#r-70--0013-reaches-his-warehouse-through-the-engines-own-upgrade-path-and-step-1-is-applied-after-he-reads-the-dry-run)). It read **v9** when this table was written |

### And the crawl is finished — asked and answered 2026-08-24

He asked whether another crawl was needed. **No, and not for coverage ever again**: every
one of the 17,452 ids in the union has a profile snapshot stored. What was missing was
**rows, not pages** — 188 contractors had a listing row and no profile row, and all 188
had their snapshot on disk. Replaying the parser over them, read-only:

| count | refused by | fixable by crawling? |
|---:|---|---|
| **59** | `PageIsNotAProfile` — the id is dead and the site answers with the listing (`OP-64`) | **no, the page does not exist** |
| **129** | `merge_locales` — the Arabic page publishes an address box the English one omits | **no, it was a parser question** |
| **0** | would approve without a code change | re-approval wrote nothing |

**And the 129 are being recovered, not described.** He ruled on it the same day
([R-51](RULINGS.md#r-51--the-two-locales-are-lined-up-around-a-missing-box-and-no-arabic-label-is-ever-read)):
`align_locales` locates the missing box from the ENGLISH side, so the two locales line up
without an Arabic label ever being read. **121 of the 129 align; 24 of those gain an
address the English page cannot supply for anyone; 8 stay refused** because Arabic is the
shorter side there and which box *it* dropped is unknowable. `OP-66` carries the
measurement.

**AND IT HAS RUN.** `--approve --run-ref profiles-2026-08-22` read 17,417 stored page
pairs in **83.9 minutes with no network requests at all**: profile rows **17,264 →
17,385, exactly 121 added**, of which **24 carry an address** — the prediction to the row
— and the gap **188 → 67**, which is the 8 refused plus the 59 dead ids. 17,249 pages were
unchanged and wrote nothing, and **0 were re-parsed with new values**: not one
already-approved row was rewritten. Checked across the whole table, **0 rows** have
`activity_ar` equal to `address`, which is the corruption a tail-drop would have caused.

**Superseded for the final eight on 2026-09-01 by
[R-83](RULINGS.md#r-83--a-known-arabic-omission-loses-one-locale-value-not-the-whole-profile).**
Their Arabic pages all omit `Address`: seven stop after `Region`, while contractor `2079`
continues with `Activity`. A strict observed-label fallback now identifies that one omission,
keeps every correctly aligned value, and replays all eight stored pairs as 27-field profiles
with no warning. This is code state, not yet warehouse state: those eight remain absent until
their snapshots are re-approved after the running enrichment job.

A refresh crawl is a question about FRESHNESS — the listing is from 2026-08-21 — and not
about coverage. The 148-and-35 reconciliation below was measured mid-crawl; the 35 became
188 as the profile crawl reached the rest of the listing while the parser refused this
population.

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

**Neither number is the population.** The honest total is the **union, 17,452**.

> **THE "FLOOR" ARGUMENT IS WEAKER THAN THIS PARAGRAPH FIRST CLAIMED**, and an adversarial
> review is what narrowed it. It said the sweep *"stopped at its pass ceiling rather than
> converging"*. That is true of the sweep whose pages were never stored — it read one
> language, kept nothing, and reached "at least 17,283". But the two sweeps whose evidence
> IS on disk **converged**: `deficit-2026-08-21b` brought +28 / +6 / **+0** over its last
> three passes, and `residual-2026-08-21` +0 / +1 / +1. So "any two passes drift" is well
> supported — 4,556 contractors on more than one page in a single pass — while "the
> population is larger than 17,452" rests on the sweep that kept no evidence, and is a
> weaker claim than it was written as.

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

## Pull requests — where each one landed

**THERE ARE ZERO OPEN PULL REQUESTS as of 2026-09-04**, checked against GitHub. This section
keeps its name's promise by recording where each one went instead: an entry saying *"open"*
about something merged sends the other machine to a ref that no longer exists, which is the
failure the 2026-08-30 rewrite below already recorded once — and it had happened again to
**six** of the entries here before this update.

### The system is Supabase's exactly — **merged as `ef3121d` (#320)** on 2026-09-04

**It is `R-85`, not `R-84`** — the number moved when `R-84` was taken by the migration
baseline, and the ruling was renumbered on its own branch before either landed. **Both
questions below were answered by him and the work is built**; they are kept because `C4`
wants the questions visible as having been ASKED, not settled by a session's default.

**It sat on a branch with no pull request for four days.** Found by auditing 228 branches
against `main`, not by anything pointing at it — and `R-86`, a standing instruction to every
session, was on that same branch. **`main` ended at `R-84` while two of his rulings existed
only on a ref nobody was reading.**

> «انا اريد النظام مطابق تماما لنظام supbase عدل اى قرار يتعارض مع هذا النظام»
> · «احذف الثلاثة وابق supabase وحده»

**IT SUPERSEDES `R-74` PARTS 2, 3 AND 4.** `R-74` made Supabase the baseline and named three
exceptions on it — `whatsapp`, `github`, `device`. Asked directly whether they survive, he
deleted them. `supabase` is now the only colour choice.

**Measured before building:** 134 filled palette cells, 120 registry lines, 20 device
declarations, and the contrast matrix goes **168 executions over 8 states to 21 over 2**. The
stored-preference migration is **free** — `resolvePalette` already returns the default for an
id it does not know. And it deletes `R-79` entirely, which was all device: the cascade fix,
`contrast-color()`, the per-surface ink, two tests. Correct work under the then-standing
ruling, and `C4` keeps that visible.

**THE TWO QUESTIONS HE WAS ASKED, because their answers differ by orders of magnitude.**
Both are answered in `R-85` §4; the measurement is what made them askable rather than
defaulted:

| | |
|---|---|
| **which layer** | VALUES = 14 of 168 assertions red · SYSTEM = +124 declarations, `THEME_PROPERTIES` 36→72, 144 cells, matrix 168→448, **minus** the bidi contract, four accessibility accommodations, 79 `aria-live` sites, the 48px floor · IMPLEMENTATION = 351 `.tsx` files and 26 npm deps against 20 stylesheets, inside an MV3 panel and a Flask app with no root `package.json` |
| **is Arabic exempt** | Supabase: **268 physical directional properties against 6 logical**, zero `rtl:`, zero `unicode-bidi`, no mention of rtl in 105 docs. Here: 190 logical against 20, 22 bidi declarations, 55 `*_ar` fields, `"Noto Sans Arabic"` in both stacks. **17,417 of 34,834 crawled pages are Arabic.** There is nothing to copy, so exact match is subtraction only |

**Thirteen components are structurally impossible rather than expensive**, and each for the
same reason: what is being copied is a runtime. `form.tsx` has **no visual output at all** —
it wires react-hook-form to `aria-describedby` ids from `React.useId`.

**And measuring the ruling corrected the record of the departures.** `--accent-contrast` was
**never** a departure — byte-exact both schemes. `--amber`'s justifying pair is this
repository's invention; Supabase never renders it. `--focus` fails in **one** scheme, not two.
Three positions, not five values.


**Everything this section listed on 2026-08-30 has merged.** It said *"no PR yet"* for three
branches that are now on `main`, which would send the other machine to refs that are gone --
so the entries are replaced by the record of where they landed, and the one branch still open
is described in full.

| landed | as | what it was |
|---|---|---|
| `claude/the-backup-that-uploaded-nothing` | **#296** (`a167417`) | `OP-111` -- a backup of nothing reached Drive, and the check was disabled by zero |
| `claude/two-migrations-the-banner-could-not-report` | **#295** (`6f8bbbb`) | `OP-115` -- the schema-lag banner could not name two real migrations |
| `claude/the-guard-that-reads-half-the-product` | **#297** (`42ef068`) | `OP-116` -- the restart poll asked a route M5 deleted; the guard read only `extension/` |
| (design review) | **#298** (`69ce391`) | `OP-103` -- every custom property a stylesheet reads is one something defines |
| `codex/organization-enrichment-main` | **#302** (`bf033ca`) | organization enrichment, +7,242/-99 across 36 files, **merged by the owner himself on 2026-08-31** |
| `claude/scrapex-engine-consolidation-d69e0a` | **#293** (`1d8816d`) | `REQ-50`, `R-80`, `OP-112`-`OP-114`, `OP-119` -- the engine page consolidated, and the Restart button the warning had nothing to press |

**AND IT HAPPENED AGAIN, TO SIX MORE.** Everything below this line was written as *"no PR
yet"* or *"open"* and every one of them has merged. The sub-sections are kept in full —
their measurements are what the next question gets answered from — but each heading now
says where it landed. Added 2026-09-04, from `gh pr list --state merged`, not from memory:

| landed | as | when |
|---|---|---|
| `fix/a-known-omission-loses-one-value-not-the-profile` | **#303** (`43f6ae5`) | 2026-09-02 |
| `fix/the-engine-reports-the-commit-it-was-built-from` | **#305** (`bc06101`) | 2026-09-02 |
| `claude/one-migration-plan-not-two` | **#306** (`3c2aaa0`) | 2026-09-02 |
| `claude/the-drift-check-that-was-off` | **#307** (`27ed85f`) | 2026-09-03 |
| `claude/a-citation-nothing-reads` | **#309** (`8a3592d`) | 2026-09-03 |
| `feat/the-crawl-button-drives-the-collector-it-needs` | **#310** (`588f904`) | 2026-09-03 |
| `fix/a-directory-crawl-passes-the-admission-too` | **#313** (`f221abc`) | 2026-09-03 |
| `claude/the-base-changes-now` | **#318** (`9a34a01`) | 2026-09-04 · `REQ-52`, `OP-131`, under `R-84` |
| `claude/the-command-that-outlived-its-removal` | **#319** (`c233a21`) | 2026-09-04 · `OP-124`, `R-81` |
| `claude/the-system-is-supabases-exactly` | **#320** (`ef3121d`) | 2026-09-04 · `R-85`, `R-86`, `OD-09` — **had no PR** |
| `req/a-source-declares-what-it-can-be-asked-to-do` | **#321** (`28144ae`) | 2026-09-04 · `REQ-53`, `REQ-54`, `OP-132` — **had no PR** |

**THE LAST TWO ROWS ARE THE ONES TO READ.** Neither had a pull request; both were found by
auditing every branch against `main`. Between them they carried **two rulings** (`R-85`,
`R-86` — one of them a standing instruction to every session) and **two of his requests**
(`REQ-53`, `REQ-54`). `C7` exists because `REQ-04` was ruled, never built, and dropped out of
sight; this is the same failure caught one step earlier — recorded, but not where anyone reads.

**WHAT THE AUDIT COST TO GET RIGHT, because the next one will pay it too.** `#319` and `#320`
each needed a rebase after the merge before them, and the rebases were not textual. `#318`
changed **one line region** of `scrapex/webui/app.py` (+14 lines at line 202) and that moved
**26 citations across four documents** — of which the guards could see **four**. The other
twenty-two would have landed on real, non-blank, wrong lines. `OP-123`'s subject, measured
again. And one pinned row on `main` had been **two lines stale inside the ±3 window** the
whole time, so it had always passed.

**`#297` LANDED WITH A DEFECT AND IT IS ON `main` NOW -- read `OP-119` before touching that
guard.** Its fix repointed `settings.html` at `/api/engine/health`, which
[`scrapex/webui/app.py:617`](../scrapex/webui/app.py#L617) mounts only `if databases is not
None`, and [`scrapex/cli.py:856`](../scrapex/cli.py#L856) sets `registry = None` for
`scrapex ui --db <path>`. On that start the restart poll 404s its whole sixty-attempt budget
and reports a failure that did not happen -- **the defect `OP-116` set out to fix, reproduced
by its own fix.** The engine-page branch below repoints it at `/api/health`, which is mounted
on every start. **The instance is closed there; the guard's blindness is not**, and that is
what `OP-119` is for.

### The two version rows — what #293 left open, and it is his

**`#293` merged as `1d8816d` on 2026-09-02.** Everything below is the half that did not
land with it, kept here because it is a decision of his and there is no branch holding it:
the next change to it starts from `main`.

**It delivered the three things he asked for:** **enough notifications** -- the schema-lag banner can
appear for the first time (`OP-113`: `engine.js` published the field and never carried it, so
nothing was ever drawn); **a Restart button** on the engine's own page, under the warning that
asks for it, with a **121.5-second** budget derived from the engine rather than the 30 seconds
guessed (`R-80`); and **consolidation started at the engine**, with the rest measured -- 31
engine routes the panel cannot reach, 8 settings changeable only on the engine's own web UI.

**Still open, and his:** whether `Installed version` and `Latest version` stay
on the consolidated page. He said *"commit it"*; measurement afterwards changed the answer,
because an installed `.exe` reports **no commit SHA at all**
([`scrapex/provenance.py:238`](../scrapex/provenance.py#L238) returns before HEAD is read, and
no stamping mechanism exists anywhere in the repository), so `Build` renders the constant
string `installed build` and deleting the version rows leaves him unable to identify which
engine he is running. `engineProtocolText` is additionally gated on the version, so the other
kept row would read `Not available` once `R-77`'s engine half lands. **The decision stands and
its order is wrong**: stamp the SHA at build time, un-gate Protocol, re-home the
no-installer sentence, then cut.

**Not built, and deliberately:** a power switch. Half of it exists -- `POST /api/engine/restart`
and the button -- and the stop half needs a route the node gate would redden while
[R-77](RULINGS.md#r-77) says the engine has no number to raise. Spending a version to pass a
gate whose question a ruling has retired is the wrong order.


### MarketLens is gone — 2026-09-02 · **merged as `2ce06b82` (#300)**

**`OP-117`, `REQ-52`.** Landed on `main` at 14:42 UTC. Kept here rather than reduced to a table row because
the measurement below is what the next MarketLens question gets answered from.

He asked for the retired product deleted. **189 references became 17, and every one that
stays names something that still exists.**

**The defect found on the way:** `/data-model` reported **134 tables where 67 exist**, because
both its reports opened the same engine database -- one of them labelled *MarketLens*. Fixed by
comparing paths rather than by deleting the second report, which would have been right today
and wrong with `general_db_path` set.

**What stays, and it is not caution.** `marketlens_path` is a key in `~/.scrapex/databases.json`
whose rename fails SILENTLY and orphans the priced warehouse; `compaction.py`'s paragraphs
explain why the kind check reads the file header, and a file wearing that value is on his disk;
`schema.sql` and `0002` are checksummed and applied. **And the column they name does not exist
in any database** -- measured: `schema.sql` creates `site_profile.marketlens_source_key`,
`0002` renames it, and `0014` drops the whole table, so it lives for one migration step of a
fresh install and appears in no warehouse at v16.

**A guard keeps it deleted:** a new file naming it goes red, every exception must say what it
protects, and an exception whose file no longer names it goes red too. It caught two of its
author's own mistakes while being written.

**And the reservation table was shadowing its own row.** `RESERVED["REQ"]` carried the key `50`
twice -- this branch added one above one already there, and Python keeps the last, so the row
carrying the verified holder was the one discarded. The failure this table's guard exists for,
one level in, introduced by the pass that was de-duplicating the level above it.

**`REQ-52` has moved on since this branch was written.** He ruled the squash on 2026-09-02, it
was priced, and it is now four changes rather than one: `OP-120` (the drift check that proves
it), `OP-122` (one migration plan, not two), `OP-123` (the citation guard's free floor), then
the squash itself. His ruling is recorded as `R-84` **on the `OP-122` branch, not here** --
deliberately, because a ruling recorded only on the branch it authorises is unrecorded until
that branch merges, and the squash is the slowest thing in the queue. Read all four before
touching the migration framework.
### A known omission loses one value, not the profile — **merged as `43f6ae5` (#303)**

**`R-83`.** 691 insertions across 19 files that existed only as three commits on one
machine's local `main` for a day, unpushed and unreachable from anywhere else — which is the
exact failure [CLAUDE.md](../../CLAUDE.md) opens with. The branch is those three rebased onto
`main` at `1d8816d`, plus what the rebase found.

**What it carries.** The eight profiles whose Arabic page omits `Address` are recoverable and
now recovered in code (`R-83`, replaying 8 of 8 stored pairs as 27-field profiles); `--approve`
can be narrowed to named ids instead of reapproving all 17,417 rows; and the enrichment page
gains incremental and complete modes.

**What the rebase found, and neither was in the three commits.** The ruling arrived as `R-80`
and `#293` had already taken that number for a different ruling of his, so it is `R-83` —
`R-82` is held by `#299`, verified against `217d9c48` rather than taken from a message. And
`RESERVED` in
[tests/test_the_registers_cannot_collide.py](../tests/test_the_registers_cannot_collide.py)
carried `"R"` **twice**: Python keeps the last, so the row reserving 80 for `#293` was dead the
day it was written, and `test_a_reserved_number_is_not_also_declared` stayed green through
`#293`'s merge because the number it would have caught was in the discarded row. Third
instance of the same defect in this repository and the second in that file, so it stops being
advice: `test_the_reservation_table_has_no_shadowed_rows` reads the source with `ast`.
[LESSONS §23.3](LESSONS.md) has it.

**One fixture repair was the only red.** `test_the_cross_check_refuses_inside_approve`
monkeypatches `_pairs` and its stub predated the `ids` keyword, so `approve` raised
`TypeError` — the first thing to exercise the keyword at all. The stub records what it was
handed rather than swallowing it, and the test now asserts the forward.
### One migration plan, not two — **merged as `3c2aaa0` (#306)**

**`OP-122` and [`R-84`](RULINGS.md#r-84--the-base-changes-now--and-at-publication-no-migration-is-ever-deleted-again).**
Rebased onto `main` at `43f6ae50`. Secondary session;
`recursing-shannon-068e63` merges
([R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)).
Fifth in the primary's fixed queue, behind `OP-120`.

**Stage 1 of `REQ-52`'s squash, and correct with or without it.** Two builders resolved
the engine migration plan and the baseline's version was a literal in both, while the
only copy SQLite obeys is the `PRAGMA user_version` inside `db/engine/schema.sql`.
`latest_schema_version()` derives from those literals and reaches `health()`, which is
what tells the owner a warehouse is too new to open. Read `OP-122` in
[BACKLOG.md](BACKLOG.md) before touching the migration framework.

**HE HAS RULED AND THE SQUASH IS UNBLOCKED — `R-84`, carried by this branch.** The
base may be collapsed before publication; after it, no migration is ever deleted. It
supersedes nothing: `R-24`'s own words already scoped the data guarantee to *«عند نشر
الاداة»*, and he restates that guarantee in this ruling's first clause. **And it
dissolves the blocker rather than answering it** — his warehouse is at the head of the
chain, so a baseline squashed there replays nothing over it and no carry-over path
needs writing.

**Stage 2, the squash itself, is priced and NOT built.** See `OP-122`'s closing
paragraph for the one piece deliberately held back, `OP-120` for the shipped migration
defect the squash absorbs, and `R-84` for the two things it must carry: a check that
refuses to delete a migration once a release marker exists, and the separation of
tests that exercise a one-off migration from tests that assert a property of the
resulting schema.
### The listing phase has a door — 2026-09-02 · **merged as `9bc4680d` (#304)**

**`OP-118` corrected, `OP-121` filed.** His muqawil listing crawl has been blocked since
2026-08-30 on one refusal, and the refusal's stated reason was **false when it was written
down**. It is gone.

**What was measured, because the entry it corrects repeats the wrong reason.**
`crawl_partition` refused any scope but `listing_only`, saying a `full_then_listing` run
"would fetch a detail page for every row it read" and turn ~2,000 requests into ~40,000. But
`crawl_partition` passes `listing_phase_only=True` to the walker **unconditionally**, and the
walker short-circuits on that flag *before* it reads the scope. Bypassing only the gate, with
the row still reading `full_then_listing`, a real cell crawl fetched **9 listing pages, 0
detail pages** and closed provably complete.

So the refusal never prevented the 40,000 requests. It prevented `full_then_listing`'s own
second phase — *"then the listing catches the changes"*, the half its name is about —
from running at all, and the only route offered him was editing `source_site.crawl_scope` and
editing it back afterwards, because the detail crawl reads the same column. He does not use a
terminal ([R-81](RULINGS.md#r-81--a-command-line-answer-is-not-an-answer-the-panel-is-the-only-door)).

**What replaces it is stronger than what it removed.**
`test_the_listing_phase_fetches_no_detail_page_under_any_scope` asserts the behaviour over
all three scopes. The refusal could never have caught a change that dropped
`listing_phase_only`; this reddens on exactly that, with the count in the message.

**And the guard was vacuous until a mutation said so.** `Partition.detail_urls` in the
fixture returned `()`, so no scope could ever produce a detail fetch and the new assertion
passed under the very defect it was written for. The fake publishes and serves its detail
pages now.

**`OP-121`, found while writing that guard:** the same mistake in two more places.
`SliceRequired` was asked of the registration rather than the phase, in
`snapshotcrawl.crawl_to_snapshots` and `pagewalk.walk`, so a partitioned listing crawl of a
site registered `listing_plus_slice` with no slice **died before its first request** on a
demand it could not act on. The same call feeds `declare_frontier`, so progress on a
`full_then_listing` source could only ever stall at a fraction it can never close. Three
checks above the walker were never revisited when `listing_phase_only` was added on
2026-08-21.

**THE OTHER HALF OF THE BUTTON IS STILL NOT BUILT, and this branch does not pretend
otherwise.** `POST /api/jobs` queues `muqawil_org` since `REQ-45`, and the worker still hands
every source to `capture_source` — the price path. The route to follow is the one
`organization_enrichment` already took: a job KIND with its own runner
([scrapex/jobs.py](../scrapex/jobs.py), `_start_job`), not a widened `CaptureResult`, whose
counters are price-shaped. That chain is two kinds today and a third makes it a registry,
which is what «خلى الشغل dry» asks for. **Until that lands he still cannot press a button;
what changed is that the engine no longer refuses the run when something does press it.**
### The engine reports the commit it was built from — **merged as `bc06101` (#305)**

**`R-77`'s first two clauses, built. The third leaves this repository, and that is why it
stops here.**

`R-77` split one number into three questions and answered each with an architecture:
identity is the **commit**, compatibility is a **protocol number**, and the product version
is the **extension's alone**. Measured against the code, the first was never built and the
second was coupled to the thing being retired.

**1 · An installed engine reported no commit at all.**
[`scrapex/provenance.py`](../scrapex/provenance.py)'s `seal()` returned before `HEAD` was
read whenever the build was frozen — correctly, because a one-file `.exe` carries no
repository — and **no stamping mechanism existed anywhere in the repository**, so
`commit` was `None` on every published build and the panel's `Build` row rendered the bare
words `installed build`. `engineBuildText` has always known how to draw `installed ·
<sha7>`; the fact was simply never in the bundle.

`packaging/build_engine.py` now writes `build-stamp.json` from `git rev-parse HEAD` and
bundles it; `provenance` reads it when frozen. **It still answers `None` for every failure**
— a bundle from before the stamp, a torn file, anything that is not a 40-character hex
commit — because under `R-77` that string is the engine's identity and a guess there is
worse than a blank. Eight such cases are asserted, and the honesty test that predates this
(`a frozen build answers None and never False`) is untouched: **which code this is** and
**whether newer code exists** are different questions, and only the second is unknowable
from inside an `.exe`.

**2 · `Protocol` was gated on the version, so retiring the version would have silenced
it.** `engineProtocolText` opened `const installed = state.engineVersion; if (!installed)
return "Not available"`, so an engine that had just stated protocol 1 on `/api/health` and
carried no version would have reported *Not available* about a fact it supplied. It asks
`state.engineUp` now — whether an engine answered — which is `R-77`'s second clause
made structural: a compatibility boundary and a release cadence are independent facts.

**3 · THE CUT IS BLOCKED OUTSIDE THIS REPOSITORY, and this is the measurement to put to
him.** `Latest version` is not a label. It feeds `engineReleaseVerdict`, whose verdicts —
`Update available`, `Up to date`, `Available to install` — come from
`isOlder(installed, latest.version)`, and from those verdicts come the download button and
the install steps. **Remove the engine's version and the comparison loses its own side**, so
the update check has to become *is the published build's commit mine?*

That needs the published side to carry a commit, and the published side is
`mbiX-hub/ScrapeX/json/version.json` — `extension/releases.js`'s `VERSION_MANIFEST`, a
manual manifest **in a different repository, which he publishes**. Nothing here can add a
field to it. So:

| | |
|---|---|
| stamp the SHA at build time | **done, this branch** |
| un-gate `Protocol` from the version | **done, this branch** |
| make the update check compare commits | **needs `version.json` to carry the release's commit — his repository** |
| cut the two rows | after the above, and not before: cutting first removes his only way to install a new engine |

**The decision stands and the order was the wrong part**, which is what `#293` recorded. Two
of the four steps are now behind us.

### The drift check that was off — **merged as `27ed85f` (#307)**

**`OP-120`.** Branched from `main` at `1d8816d8`. Secondary session;
`recursing-shannon-068e63` merges
([R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)).
Fourth in a queue the primary fixed: `#299`, `#300`, its own branch, this, then the squash.

The two-way drift check `ENGINEERING.md` T5 mandates had been skipping since the M5 collapse,
because its stop point was the deleted price stream's version number. Turned on, its first run
found `0014_one_source_registry.sql` cannot upgrade a row whose `base_url` is NULL. **Read
`OP-120` in [BACKLOG.md](BACKLOG.md) before touching the migration framework**, and read it
before the squash: this check is what proves that squash, and it was not running.

**`REQ-52`'s squash is priced and NOT built.** Measured cost, in one line each so the next
session does not re-derive it: two independent migration-plan builders carry the same
gapless-from-1 rule ([`scrapex/databases/domain.py:196`](../scrapex/databases/domain.py#L196)
and [`scrapex/db.py:140`](../scrapex/db.py#L140)); `latest_schema_version()` hardcodes the
baseline as 1 ([`scrapex/db.py:125`](../scrapex/db.py#L125)) and that 1 reaches the Storage
page through `storage.py` `health()`; the baseline has 51 `CREATE TABLE` and no
`IF NOT EXISTS`, so replaying it over a populated database fails on the first table; and
[`.github/workflows/release-engine.yml:154`](../.github/workflows/release-engine.yml#L154)
aborts the release when the migrations folder is empty. **Stage 1 unifies those four and is
correct with or without the squash. Stage 2 is the squash, and it needs his word on the
sentence "a database below v16 is not upgraded — it is carried over or rebuilt" before it
merges.**

> **That half is built, in the entry below** — a third job kind and its runner — **and the
> last sentence turned out to be wrong about why he could not press a button.** The engine
> was not the only thing in the way: the card offered no control at all, and the one it
> would have offered sent a run mode the engine refuses. `OP-126`.
### The crawl button drives the collector the source needs — **merged as `588f904` (#310)**

**`REQ-45`'s second half.** `#301` taught `POST /api/jobs` to accept `muqawil_org` — it had
been answering 404, which is why every muqawil crawl to date ran from a terminal. **The
worker then handed it to `capture_source`.** That is the price collector, and its
`CaptureResult` carries `observations`, `duplicates`, `products`, `variants` and
`attributes`; a contractor listing crawl produces none of them. It produces stored pages, a
per-cell completeness proof, arrivals and departures.

**And every test written for `#301` asserted `status == "queued"`, which was true.** Nothing
looked at the job **kind**, and the kind is the only field that says which collector runs.
That assertion exists now and it is the one that would have caught this.

**A third job kind, on the route the second one already took.** `directory_crawl`, runner
`scrapex/directoryjob.py`, reached from `jobs.SPECIALISED_RUNNERS` — a table, because the
`if job_kind == ... else` was two branches long and `JOB_KINDS` listed the same strings a
thousand lines above it. `JOB_KINDS` is **derived** from the table now, so the set of kinds
the route accepts cannot drift from the set a worker can run. «خلى الشغل dry».

**Not one line of crawling was written.** `contractors.crawl` stays the single
implementation both front doors call. What the runner adds is the three things a job needs
and a command line does not: the crawl's own report goes to the job log through a sink on
`say` (whose docstring has always claimed "one line to the console AND to the log"),
progress is counted in **cells**, and a pause or cancel is applied at a **cell boundary** —
the only safe place, because a cell's proof compares an id sequence against a witness read
of page one, so a cell interrupted halfway has fetched pages and proved nothing.

**`0017` widens one CHECK, and it is the safe direction.** `job_kind` arrived in `0011` with
`CHECK (job_kind IN ('crawl','organization_enrichment'))`, and SQLite cannot alter a CHECK —
it needs a table rebuild. Widening it means no row that satisfied the old constraint can
fail the new one, which is worth saying because the last rebuild in that folder
(`0014`, `source_site.base_url`) got the direction wrong and refuses a legal pre-v14 NULL.
**`R-64`: it reaches his warehouse only after it is on `main`.**

**A regression this nearly shipped, and it is the reason the sink has its own test.** The
first draft put `if sink is None: return` in FRONT of `say`'s file write — so every
command-line run, which is every run with no sink installed, would silently have stopped
writing `~/.scrapex/trial/listing.log`. That file is what his own crawl of 2026-08-23 was
read back from.

**Three mutations, each restored:** the route dropping `job_kind`; the kind losing its
runner; and `0017`'s CHECK reverted. Each reddened the guard written for it.

**AND THE CARD HAD NOTHING TO PRESS EITHER — `OP-126`, found after the collector was
built.** Three defects on one action: `sourceActions` filtered "Update now" off every
dataset card (correctly, on the card's own key); the handler sent `run_mode: "current"`,
which is not a `RunMode`, so the engine answered **400 about the mode and never read the
key** — on every card, since it was written; and it sent the card's `source_key`, which
for a dataset card is the DATASET key, where the route resolves the site key.

**Every guard over it was green.** One asserted the action must be **absent** — the third
guard today holding a limitation in place. `tools/panel_harness.py` answers `/api/jobs` with
a canned success, so no DOM test could fail on a bad request, and it carried no `site_key`
at all, a field the engine sends on every dataset row. And
`test_an_action_withheld_for_its_route_really_is_refused` accepted any `4xx`, so the 400
about the mode satisfied a test whose stated claim is that the route refused the **KEY**.
The assertion that would have caught all three — press it and read the recorded request —
did not exist and does now, mutation-tested both ways.

**A first draft of the repair added a second channel for a value that already had one**:
`update:<site_key>`, copying `table:<dataset_key>`. The site key already reaches
`runSourceAction` as its third argument. `table:` is not that precedent — a folded card
stands for several datasets, so which one an action means cannot be a property of the card;
there is exactly one site behind a card.

**VERSION 0.4.6 → 0.4.7**, because a migration moves the contract fingerprint and the gate's
only sanctioned answer is a bump. The three generated homes were regenerated by
`python -m scrapex.cli export-version` in the same commit.

### A directory crawl bypassed the politeness gate — **merged as `f221abc` (#313)**

**`OP-128`, and this session wrote it and merged it an hour earlier in `#310`.**

`SPECIALISED_RUNNERS` mapped a job kind to a `(conn, job_ref)` callable, so `_start_job`
chose the runner and handed the cross-job admission to `run_job_once` alone. **A
`directory_crawl` job therefore crawled outside the per-host reservation** — the property
`_CrawlAdmission`'s docstring calls *"the safety property the task calls the whole risk"*.

**His `job_capacity` is 3, not the shipped 1**, so two `muqawil_org` jobs — two presses of
the panel's button, or a schedule plus a press — ran with their own fetcher at 1.0 s each
and doubled the request rate on that site. `R-21`, `SR-8`.

**The guard that pins the rule drives `run_job_once` directly**, so it is blind to the
dispatch. Second instance in two days of a guard asserting something true and *adjacent* to
what broke.

**Fixed as option (a)**: the contract accepts the gate, the runner holds the reservation
around its own crawl, and the host rule is **extracted** to `jobs.host_of_url` rather than
copied — a second `urlsplit(...).netloc.lower()` in the runner would have been the exact
crack `_host_of`'s docstring names. Four guards, three mutations.

**The open half is named and unbuilt:** whether two concurrent enrichment jobs should
serialise per PROVIDER. Its requests go to third parties rather than to one registered
site, so there is no host to reserve, and the parameter arriving does not settle it.

### A citation nothing reads — **merged as `8a3592d` (#309)**

**`OP-123`.** Branched from `main` at `80659faa`. Secondary session;
`recursing-shannon-068e63` merges
([R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)).

The citation guard checks that a cited line EXISTS, and that it still holds its
subject **for the 66 rows in `PINNED`**. Measured: 296 citations across the nine
documents, and **30 of the 68 pinned rows are not held against any citation at all** —
free units of the floor that exists to stop rows being deleted. One three-day-old
evidence blocks, measured independently by two sessions, held eight citations of
which **seven were wrong and two were detected** — and both detections were accidents,
each one a citation pushed onto a blank line by an unrelated change.

Adds an automatic content check for every citation written in the repository's own
`path:line   <the code>` form, a guard over `PINNED`'s document side, and a ratchet on
the 26. **The general fix is deliberately refused** — an automatic repointer would
rewrite every number that is a record rather than a pointer. Read `OP-123` before
touching the citation guard.

### The base changes now — **merged as `9a34a01` (#318)**

**`REQ-52`'s last half, `OP-131`, under [`R-84`](RULINGS.md#r-84--the-base-changes-now--and-at-publication-no-migration-is-ever-deleted-again).**
Secondary session; `recursing-shannon-068e63` merges
([R-42](RULINGS.md#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)).

Sixteen migrations collapsed into `db/engine/schema.sql` at schema version **17** — 179
objects and the three rows the chain seeded, including `0015`'s shipped retention
default, **which a schema-only dump would have lost in silence**.
`tools/squash_engine_baseline.py` generates it and refuses to write a baseline it
cannot verify against a database built through the whole chain.

**Read `R-84` before touching the migration framework, and know two things about this
change specifically.**

**A generated baseline is a claim about a chain that any merge can invalidate.** One
landed while this branch was being written and the suite said *"at schema v17, expected
v16"* — not a test bug. **So the squash cannot hold a queue position: it is either the
last thing to land, or it is regenerated on every rebase.** `--check` compares every
absorbed digest against the ref it will merge into and says **REGENERATE** when they
differ.

**And a database below the baseline is refused, not replayed.** The baseline has 51
`CREATE TABLE` and no `IF NOT EXISTS`; before this, `_migrate` would have run the whole
schema over a populated database. The refusal names `R-84`, says nothing has been
changed, and offers the two actions `R-84` allows.

### Why the engine would not start, and the four fixes it earned — 2026-09-04

**On the branch `claude/engine-failure-review-4287b1`, base `3c45086`, not yet proposed.**
It began as a review — *«اريد مراجعة لماذا لا يعمل المحرك ؟»* — and what it found is at the
top of this file. He then narrowed the question to recurrence and ruled that the v10
warehouse is not to be upgraded, so the branch carries no migration and touches no data.

**Register numbers `OP-133`..`OP-142` claimed** after sweeping every local and remote ref
for `^#{2,4} +OP-13[3-9]` and `OP-140`..`OP-142` (nothing declared them anywhere) — §3 of
[ORCHESTRATION.md](ORCHESTRATION.md). Contiguous, so no `RESERVED` row was needed.

| number | what it is | state |
|---|---|---|
| `OP-133` | the squash gate asks whether the tool is published, not whether his warehouses are at the head | **open — his ruling** |
| `OP-134` | no release ever carried the chain past v10, so a machine on a release is behind by construction | **open — his call to cut a tag** |
| `OP-135` | `health()` answered "Needs upgrade. Run 'python -m …init-db'" about a database no command can upgrade | closed here |
| `OP-136` | nothing removed a pre-upgrade copy: 963,768,320 bytes, and the policy that would have had no caller on this path | closed here |
| `OP-137` | "The database is already up to date" about a database the engine refuses to open | closed here |
| `OP-138` | the five tests that prove `R-84`'s refusal are skipped on `main` and in CI | open, with its reason |
| `OP-139` | `OP-127` closed the unprotected upgrade on one of the two doors | open, with its reason |
| `OP-140` | the panel prints the raw key `too_old`; the vocabulary for it exists only on the engine's page | open, with its reason |
| `OP-141` | the backup prune orders a deletion by mtime, and a reset-backup carries the warehouse's — measured deleting TODAY's copy | **closed** on `claude/a-deletion-ordered-by-the-wrong-clock`, on his instruction |
| `OP-142` | four pointer messages name commands on the panel, and two cannot be reworded because the control does not exist | open — needs a control, so his call |

**THE PATTERN IS WORTH MORE THAN ANY ONE OF THEM, and it is now three instances.**
`OP-131`, `OP-135` and `OP-139` are each **a repair applied to one of two surfaces that
tell the same thing** — two `health()` implementations, two upgrade doors — where the fixed
one was the one being read at the time and the other went on being wrong. `OP-138` is the
same shape one level up: the change that made the refusal necessary also turned off the
tests that prove the refusal is right.

**What landed, all of it behind guards that do not depend on `origin/main`'s deleted
chain:** a status of its own for a below-baseline database, so the panel stops offering
«Upgrade database» for a repair that cannot exist; `no_upgrade_path`, one sentence read by
the three places that tell that fact, none of them naming a command (`R-81`); the owner's
own `backups_kept_per_tag` policy called on the path that makes the copies, rather than a
second prune written beside it; a refusal that names the fault instead of reporting
success; and `test_no_database_status_ever_answers_with_a_command_line`, which sweeps every
state that carries an action — the guard whose absence let one sentence reach the panel, the
engine's every page, `database_unavailable.html` and the first-run console at once, with
**three tests demanding it**.

Measured after, on a copy of his warehouse and on his real registry read-only: the panel is
told `check_storage` with no command in the detail, a refusal makes **no copy at all**, and
a real in-chain upgrade to v18 applies, backs up once and bounds the copies at three with
`pre-ledger-repair` and `rebuild` untouched.

### A deletion ordered by the wrong clock — 2026-09-04, `OP-141`

**On `claude/a-deletion-ordered-by-the-wrong-clock`, stacked on the branch above** because
it edits the same file and closes the entry that branch records. He asked for it separately
— *«واصلح OP-141 فى فرع مستقل»*.

`storage.start_fresh` does not copy the warehouse aside, it **renames** it, and a rename
carries the warehouse's own last-write time; `restore` copies that time back with
`shutil.copy2`. So a reset / undo / reset cycle leaves several `reset-backup` files sharing
**one** mtime — and the prune, ordered by mtime at one-second resolution, kept whichever
three the glob returned first. Measured: **the file it deleted was today's**, the only copy
of everything the reset had just wiped.

Ordering now reads the stamp out of the name (`backup_taken_at`), normalises the three
spellings `_STAMP` admits, and breaks ties by name descending. Three new guards, all
proved by mutation; the containment `OP-136` added stays, because narrowing what a caller
may delete is right even once the ordering under it is right.

### A warehouse below the baseline can be carried to it — 2026-09-04

**Built because he lost a machine to it.** He reported *«كان ظاهر على جهاز آخر ومنذ
تحديثات اليوم اختفى»* — the work machine, which `R-84` itself measured at
`user_version = 16`. Everything between **v11 and v16** is locked out by the squash, and
`OP-134` measured that no release ever carried the chain past v10, so the refusal's own
advice named an artefact that does not exist.

`tools/carry_a_warehouse_to_the_baseline.py` is that artefact. It recovers the absorbed
chain from history and **proves each file against `squashed-from.json`'s digest** (17 of
17), applies it with the ENGINE's runner rather than a second one, rehearses on a real
copy by default, backs up before `--apply`, and ends by asking the shipped build:
`health().ok` or it fails.

Rehearsed on a v13 warehouse with a `muqawil_org` row: `applied [14, 15, 16, 17]` →
**Healthy at v17**, the row surviving `0014`'s rebuild of `source_site`. Seven guards,
including a tampered-digest refusal and a rehearsal that must not touch the original.

**It is run FOR him from a checkout, not by him** (`R-81`) — the panel-side answer to the
same fault is `OP-144`'s missing control and `OP-133`'s ruling.
### The panel's source list is one category — 2026-09-04, `OP-145`

He asked why muqawil is not among the sources he can crawl. **The answer is the empty
warehouse, and the entry says so only after correcting itself**: it first claimed
`/api/sources` walks the manifest alone, and the route's last statement is
`out.extend(_dataset_listing())`, which appends dataset-backed sites. His fresh warehouse
holds **zero** `dataset_definition` rows, so there is nothing to append; the old one held
two and drew one folded card. The false claim and the reason it was made are kept at the
top of `OP-145` (`C5`).

`sourceboard` was written for that exact question and has **one caller, the CLI**. The
panel cannot ask it. That is the day's fourth instance of one shape, after `OP-124`,
`OP-136` and `OP-144`.

Second, independent gap: the row itself is created by the collector's first run
(`catalog.register_site`), so a fresh installation has no muqawil even with a route — the
baseline's seed carries three rows and none of them is a source.

`R-32` at the level of the interface, and the fix is a route over a module that already
exists. **His to approve.**

## Track 1 · The Console migration

**Plan:** [MIGRATION-PLAN.md](../MIGRATION-PLAN.md) · **Detailed state:**
[HANDOFF-resume-the-migration.md](../HANDOFF-resume-the-migration.md)

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
   (`extension/app.js:1583`) and `saveSourceColumns` (`:1641`), speaking the same
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

> **The R-19 data-model study is [R19-CHILD-TABLES-MEASURED.md](../R19-CHILD-TABLES-MEASURED.md)**
> — 11 criteria against 5 shapes at 518,490 rows, written because the owner asked for
> his own ruling to be tested before it was built. It upholds the ruling against JSON
> (47x) and recommends a refinement of how it is implemented. **Not built — his call,
> recorded as `Q-13` in [BACKLOG.md](BACKLOG.md).**

**Design:** [CONTRACTOR-SOURCE.md](../CONTRACTOR-SOURCE.md) · **Storage:**
[STORAGE.md](../STORAGE.md) — **the mechanism is built** (`scrapex/snapshotbody.py`,
engine migration 0005), so nothing gates the crawl any more · **Seam:**
[GENERIC-FETCH-SEAM.md](../GENERIC-FETCH-SEAM.md) · **Plan:**
[plans/2026-08-26-what-remains-of-muqawil.md](../plans/2026-08-26-what-remains-of-muqawil.md) (the 2026-08-16 build plan it replaced was folded 2026-08-27 — `git show d6f4967:docs/plans/2026-08-16-muqawil-contractor-source.md`)
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

**Not in, and named so it is not mistaken for done:** the compression migration `DEC-9`
asks for.

> **THIS PARAGRAPH LISTED THREE MORE AND ALL THREE ARE DONE** — re-measured 2026-08-29
> rather than re-read. The detail files were crawled (`profiles-2026-08-22`, 34,834
> pages); the contractors the sweep counted were fetched, and the union is complete at
> 17,452 with nothing left; and **`DEC-10`'s row-aware key IS built** — `_rows_unchanged`
> asks `generic_record.content_hash` per row in `extract/service.py`, so a corrected
> parser re-run over stored snapshots now writes, with revisions. That last one is not a
> detail: it is what makes `R-55`'s repair a re-parse rather than an 11-hour re-crawl,
> which is the whole reason `R-40` ordered it built BEFORE the profile crawl.

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
[R19-CHILD-TABLES-MEASURED](../R19-CHILD-TABLES-MEASURED.md) recommends shape F and its own
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
| 1 | **muqawil.org** | [CONTRACTOR-SOURCE.md](../CONTRACTOR-SOURCE.md) | Track 2 above — 11,059 of 17,403 rows, listing pages only, profiles never crawled |
| 2 | **Balady engineering offices** | [BALADY-ENG-OFFICES.md](../BALADY-ENG-OFFICES.md) | **Queued.** [REQ-14](REQUESTS.md#req-14--balady-engineering-offices-as-the-next-source-after-muqawil) |
| 3 | **UAE contractors and consultants** | [UAE-SOURCES.md](../UAE-SOURCES.md) | **Queued.** [REQ-15](REQUESTS.md#req-15--the-uae-sources-third-in-the-queue) |
| 4 | **Egypt, Oman, Qatar, Bahrain, Kuwait** | [GULF-EGYPT-SOURCES.md](../GULF-EGYPT-SOURCES.md) | **Queued.** [REQ-16](REQUESTS.md#req-16--egypt-oman-qatar-bahrain-and-kuwait-fourth-in-the-queue) |
| — | **Official diesel prices, 7 countries** — a PRODUCT source, not a firm directory | [DIESEL-PRICES.md](../DIESEL-PRICES.md) | **Queued.** [REQ-17](REQUESTS.md#req-17--official-diesel-prices--a-product-source-not-a-firm-directory) |
| — | **Bitumen 60/70 prices, 7 countries** — a product source that **cannot be crawled** | [BITUMEN-PRICES.md](../BITUMEN-PRICES.md) | **Queued.** [REQ-18](REQUESTS.md#req-18--bitumen-6070-prices--the-first-source-that-cannot-be-crawled) |
| — | **Reinforced-concrete materials, 7 countries** — cement, rebar, aggregate, water | [CONCRETE-MATERIALS.md](../CONCRETE-MATERIALS.md) | **Queued.** [REQ-19](REQUESTS.md#req-19--reinforced-concrete-material-prices--its-turn-will-come) |

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
> [DIESEL-PRICES.md](../DIESEL-PRICES.md) carries the reasoning.

**And the bitumen brief cannot be crawled at all** — by its own conclusion, five of
its seven countries have no public official price, so its acquisition mode is a
written quotation to a producer. What this project can do for it is store a dated,
caveated observation that is never mistaken for a live market price. It is also the
**second** independent case against `SR-6`'s key: for diesel the key is the period,
for bitumen the commercial basis, because two observations can carry the same number
and different bases. [BITUMEN-PRICES.md](../BITUMEN-PRICES.md).

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

**Ruling:** [R-77](RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build)
(every merged PR raises `VERSION`) · **Blocked by:**
[R-77](RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build)

`VERSION` is `0.2.2` at [scrapex/version.py:76](../scrapex/version.py); the
manifest is `0.2.2` too. It last moved at `adf31b2` on **2026-08-10**, and as of
2026-08-19 there are **62 commits since** — the count was 48 when the ruling was
written and 58 two days ago. It grows every time this is deferred.

**The blocker, verified 2026-08-17 and still present:**
`"latest_extension_version": VERSION` at
[scrapex/version.py:517](../scrapex/version.py) and
[scrapex/webui/app.py:1845](../scrapex/webui/app.py), drawn by
[extension/app.js:612](../extension/app.js) and `:646`.

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
- ~~[ENGINEERING.md](ENGINEERING.md) **W4** states the superseded
  per-capability rule.~~ **FIXED 2026-08-17.** It was stale twice: the trigger,
  and a claim that `extension/manifest.json` is an enforced mirror — which PR
  #112 undid and `tests/test_version.py:536` now actively guards against. W4
  would have sent a reader into re-welding the two numbers.

---

## Named gaps — recorded, not forgotten

- **`behaviourVersion` is ScrapeX's own bookkeeping, not a signal.** mbiXaddin has
  no such field; both numbers live here and one commit raises both. The real fix
  is [HANDOFF-mbiXaddin-contract-producer.md](../HANDOFF-mbiXaddin-contract-producer.md).
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
[plans/](../plans/README.md). Read that index before assuming a track has no plan.
