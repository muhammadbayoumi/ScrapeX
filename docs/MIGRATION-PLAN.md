# ScrapeX — the Console, the migration, and the debt

> **STATUS, 2026-08-15.** Phase A is COMPLETE. B2's foundation is merged and its
> remaining four endpoints are specified. The living record — what is done, what
> is in flight, exactly where to resume, and the two statements in this plan that
> measurement proved WRONG — is beside this file at
> `docs/HANDOFF-resume-the-migration.md`. Read that first; this file is the
> reasoning, that one is the state.
>
> **MOVED INTO THE REPOSITORY 2026-08-15.** It was drafted into
> `~/.claude/plans/`, which exists on exactly one machine — and the owner works
> from two. A plan that governs the code belongs beside it, where both machines
> and every reader can reach it.
>
> Two corrections to what follows, both measured rather than argued:
>   - **T1**: "restore `crawl_honour_delay`" would have done nothing — alsweed.sa
>     declares no Crawl-delay. Fixed as `crawl_pace_s` (#190).
>   - **B2**: "`/api/records` already exists for it" is wrong. That is the
>     panel's CARD endpoint. The Data page runs on `/api/table/{key}` and four
>     more. Building on the card endpoint would have shipped cards.

*Drafted 2026-08-12. Every number here was measured today, not recalled.*

## Context

Two things happened on 2026-08-12 that make this plan necessary.

**The Console got a shape.** The owner asked for a Console that is 100% the
extension's — the engine is not responsible for any part of it — with a button in
the side rail opening a page where the mbiXaddin **configuration workbook** is
read and edited. Not a data pusher: a validating editor with drop-down lists and
warnings, so a human mistake is caught *before* it reaches someone whose Excel
table then fails to load. Seven agents read mbiXaddin's ~350 C# files and returned
**216 answers with `file:line`, zero gaps** — the complete contract for all six
sheets, saved at `docs/reviews/mbiXaddin-config-contract-20260812.md`. The Console
validates against that and must never invent a rule the add-in does not have.

**The division of labour moved.** The engine keeps only *fetching* and *writing
SQLite*; the display layer moves to the extension. Measured: **14,340 lines of
interface** inside the engine — 5,642 across 29 templates, 9,126 of web JS/CSS —
almost all of it duplicating the panel. That duplication is the root of **OP-15**.

One tension was named and accepted: *"leave the engine only fetch + SQLite"* and
*"remove the 127.0.0.1 service"* cannot both hold until the extension can read
SQLite itself, because nothing else reaches a 119 MB local database. This plan
therefore separates **taking the interface out of the engine** (safe, immediate)
from **taking the server out** (a real project, deferred).

**And the exploration found a defect nobody knew about — see A0.**

---

## Decisions taken

| | |
|---|---|
| Console = an **extension page in a tab**, not a web page | token never leaves the extension; no `externally_connectable` widening; no publish step. Costs **zero** manifest changes — `release-extension.yml:91` copies the whole directory |
| It edits the workbook whose base is `2PACX-1vTg9_7sw…` | owner confirmed: the same one the add-in reads |
| Engine's face after the migration | **tray icon + a simple log window** (owner: "2 و 3 معًا") |
| Export stays in the engine | it is SQL over SQLite, not a file move |
| Jobs stay in the engine | deferred by the owner — and T2 must be fixed before anything moves |

---

## Step 0 — clear the board — DONE

[#182](https://github.com/muhammadbayoumi/ScrapeX/pull/182) (OP-18, the blind
guard) and [#183](https://github.com/muhammadbayoumi/ScrapeX/pull/183) (OP-6·ت2,
the engine calling itself dead) are both `MERGEABLE` with **0 checks running, 0
not green**. Merge both, squash, delete branch.

Confirm green **by reading the checks** — never `gh pr merge --auto`. This repo
has no required checks, so `--auto` merges immediately; it did exactly that on
#178 today and is recorded in memory.

Commit the three files already in the working tree:
`docs/reviews/mbiXaddin-config-contract-20260812.md`,
`docs/reviews/PR-180-attack-passes-20260812.md` (19 findings, all subsequently
**refuted** — stated plainly in the file), and `extension/workbook.js` (drafted,
imported by nothing yet).

---

## A0 — the defect the exploration found — DONE

`tests/test_settings_live_in_the_extension.py` enforces SR-10 by reading exactly
one file as **raw text**:

```python
WEB_SETTINGS = ROOT / "scrapex" / "webui" / "templates" / "settings.html"
stray = _control_ids(WEB_SETTINGS.read_text(encoding="utf-8")) - RUNTIME_REPAIR_IDS
```

Jinja `{% include %}` is not expanded when a file is read as text. And
`settings.html` itself contains **zero** matching controls — so the assertion
passes trivially, while:

- `settings.html:191` includes `_storage.html` → **5** controls
- `settings.html:350` includes `_retention.html` → **4** controls

**Nine settings controls driving thirteen write routes** (`/api/storage/*`,
`/api/retention/*`) sit on the engine's page, are unreachable from the panel, and
are invisible to the test written to forbid exactly this. `POST
/api/retention/policy` is the clearest violation — a stored policy, not a runtime
repair, and `RUNTIME_REPAIR_IDS` exempts only `runtime-restart`/`runtime-upgrade`.

The extension corroborates it: `app.js:6011` is `openTab("/settings#s-storage")`
— the panel deliberately hands storage control to the web page.

**Fix the guard first**, so the migration is measured against a test that works:
expand includes before scanning, then let it fail, and let that failing list be
the migration's own checklist.

*Also found, unrelated and free:* `app.js:4307` opens `` `/sources/${key}` `` —
plural. No such route exists; that menu item 404s today.

---

## Phase A — the Console — COMPLETE (A1 #185, A2 #187, A3 #186, A4 #192)

`extension/workbook.js` is drafted: the six tabs, `parseWorkbook`, `vocabularies`
derived from the file itself, and `inspect()`. It is pure — no chrome, no fetch,
no DOM — which is why its rules can be driven with hostile input under
`node --test`.

**A1 · Tests for `workbook.js`, then wire the contract in.** The 216 answers
replace guesses with facts, and three of them change behaviour:

- **A blank `IS_ACTIVE` means TRUE**, not false — and an unrecognised value
  (`Active`, `X`, `TRUE!`) also leaves it TRUE, silently. The failure is **open**.
  The Console offers a closed TRUE/FALSE list and flags anything else.
- Booleans accept Arabic: `نعم صح صحيح` / `لا خطأ غلط`.
- Vocabularies now come from the C# enums, not from values in use — `SOURCE_TYPE`
  (5), `MATCH_MODE` (5), `TRANSFORM_CHAIN` (10, pipe-separated, `:` for args),
  `SEMANTIC_ROLE` (22), `DATA_TYPE` (10), `ENTITY_TYPE`, `STORAGE_STRATEGY`,
  license tiers. `vocabularies(workbook, known)` already takes them.

**A2 · Severity that mirrors the add-in.** It has four levels (Info / Warning /
Error / Critical; only Error+ blocks sync) and a real error-code vocabulary —
`ERR_REF`, `ERR_DUPLICATE`, `ORPHAN_MAPPING`, `PK_MISSING`,
`MANDATORY_UNMAPPED`. Use **its** codes so both surfaces name the same fault.

The two problems already measured in the live workbook behave differently, and
the Console must say which is which:

| | what the add-in actually does |
|---|---|
| source whose PROFILE_KEY has no mappings | **hard-fails that source** — `IngestionResult.Fail` |
| mapping targeting a non-existent attribute | warns, then **silently drops the row** — "its data will be lost" |

Both are `Warn`, so neither blocks sync. That is precisely the gap the Console
closes.

**A3 · The page.** `extension/console.html` + `console.js`, opened from the
existing `#tab-console` rail button with `chrome.tabs.create({url:
chrome.runtime.getURL("console.html")})` — the `onboarding.html` pattern exactly.
Load `tokens.css` + `components.css` + a `console.css`; **not `app.css`**, whose
`body` grid reserves the rail column (`app.css:11-24`, "Nothing may widen the
panel"). `appearance.js` as a classic script **before** the module, or the page
ignores the owner's palette — the onboarding incident, recorded at
`onboarding.html:73-75`.

First screen: pick the workbook (Picker → `fileId`), verify the six `gid`s match
the compiled-in set, then **report before editing**. Refuse to display if the
gids do not match, rather than reassure the owner about a file nobody reads.

**A4 · Editing**, one sheet at a time, `DataSource` first — it is where new
sources are added and where ScrapeX's own three rows live.

---

## Phase B — the display migration — B2's FOUNDATION merged (#193, #194); B1, B3-B6 not started

**Order is by evidence, not by taste.** From the map:

**B1 · Delete what is pure duplication.** `manage.html` (124 lines) — the panel
already does add-a-source through `POST /api/probe` and `POST /api/sources`, both
already called. And the **9 dead routes** (class C) with no caller anywhere:
`/api/features`, `/api/review`, `/api/review/suggest`, `DELETE /api/views/{id}`,
`/api/outputs/excel`, `/api/outputs/apps-script`, `/api/retention`,
`/api/capture` — plus `/api/records`, which is the exception: **built for the
panel's Browse Data screen and never wired**, so it is the *foundation* of B2,
not a deletion.

**B2 · Data — the first real page, and the pattern-setter.** *(FOUNDATION MERGED. `/api/records` below is WRONG — see the banner. The four remaining endpoints and their order are in docs/HANDOFF-resume-the-migration.md.)* `source.html` (427
lines) + `grid.js` (3,212) + Tabulator (446 KB) is the single widest surface in
the product and cannot exist at 360px. `/api/records` already exists for it.

The honest call: **vendor Tabulator into the extension.** The engine already
vendors it under a no-CDN policy; a bundled library is not remote code and MV3
allows it. Writing a second grid to avoid 446 KB would be re-solving Arabic
collation, money formatting and tax verdicts — `grid.js`'s real value.

**Do this one first and completely**, and let it prove or break the pattern
before five more pages follow.

**B3 · Storage and Retention** — the A0 checklist, and the most consequential:
these are *destructive* operations (move the database, start fresh, restore,
prune) whose typed-confirmation guards live in template inline JS today. Every
safety interlock must move with them, not after them.

**B4 · The rest**, cheapest first: `history` and `jobs` (fully covered by
`/api/jobs*` already), `schedules` (routes already class A), `changes`,
`review`, `logs`, `sync` (Apps Script — the panel has no path for it at all),
`excel`, `overview`, `schema`, `data-model`.

**B5 · One navigation source.** It is currently triple-implemented:
`scrapex/ui_manifest.py` defines 13 destinations, `base.html` renders them,
`/api/ui` serves them, and `extension/app.js:187-214` hard-codes the same list.
Deleting the pages invalidates all three. Collapse to one.

**B6 · The engine's new face.** Tray icon (alive / stopped, "Open the panel",
"Stop") plus a plain log window. This dissolves **N0** — "the engine shows a
black window" — at its root: there is no window to be black.

---

## Phase C — deferred, and named so it is not forgotten

**C1 · SQLite in the browser** (wa-sqlite + OPFS). Only this removes
`127.0.0.1`. It is **DEC-1**, a spike was attempted, and it named four
constraints the plan does not yet answer. **Read those four before starting.**

**C2 · Jobs move to the extension.** Deferred by the owner. Additional reason:
the heartbeat is broken under load right now (T2). Moving a thing while it is
broken destroys the ability to tell which change broke it.

---

## The debt, in parallel

T1–T10 already exist as tasks. Two of them are prerequisites, not parallel work:

- **T2** (heartbeat freezes under a held write lock) blocks C2.
- **T1** (ALSWEED refused with HTTP 429 because `crawl_honour_delay` is `'0'`) is
  the only item costing data *right now* and is independent of all of the above.

---

## Verification

- **Console logic**: `node --test extension/tests/workbook.test.mjs` — fixtures
  built from the real workbook, including the 15 orphan profiles and the one bad
  attribute. Mutate `inspect()` and confirm the tests fail.
- **Every new page** is picked up automatically by `tests/test_panel_wiring.py:72`
  (every `<script src>` resolves; every `$("id")` exists), `test_design_system.py`
  (no inline `style=`, no raw SVG paths) and `test_vendor.py:148` (no colour
  literals — and remember a `#` plus three hex digits in a *comment* trips it).
- **Two gaps to close**, or new pages go unchecked: `tests/test_ui_kit.py:100`
  `_markup()` scans only `app.html` + webui templates, and
  `test_the_interface_stays_english` scans only `app.html`. Add each new page.
- **Migration proof**: after each page moves, its routes must leave `app.py` and
  `pytest -m "not extension"` must stay green. `wc -l scrapex/webui/app.py` is the
  running score — 3,347 today.
- **End to end**: open the Console on the real workbook and confirm it reports the
  16 problems the Python probe already found.

---

## Only the owner can do these

- Decide **T1**: restore `crawl_honour_delay`, or accept the 429s.
- Decide **T3** (instrument or quarantine the chaos test) and **T10** (148
  branches).
- Answer **Q-11**: is seven of twelve the intended source set?
- Press *Reset secret* on the Web OAuth client — `GOCSPX-…` appeared in
  conversation and the implicit flow does not use it.
