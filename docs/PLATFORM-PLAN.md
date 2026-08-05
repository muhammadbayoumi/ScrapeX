# ScrapeX Platform Plan

**Status:** the agreed plan, revised 2026-08-05 from fourteen owner decisions.
**Supersedes:** `scrapeX-architecture-and-implementation-plan` in full.
**Subordinate to:** `CLAUDE.md`, except where a decision below overrides it — each override is named.

Two products and one contract:

- **ScrapeX** — the Chrome extension. The control room, and the only interface.
- **Engine** — the local Python program ScrapeX installs. It crawls, stores, and tracks.

Everything else — open-source crawlers, the Console — hangs off those two.

---

## 1. The decisions

| # | Decision | Consequence |
|---|---|---|
| 1 | An engine is a **separate installed program**. | ScrapeX needs an install / launch / monitor / version contract, not a plugin loader. |
| 2 | **Engine crawls everything, not only prices.** Prices are one domain beside contractors, tenders, equipment, jobs. | The name `MarketLens` retires. The schema stops being price-shaped. |
| 3 | **One device at a time, with restore.** | Drive is enough. No server, no shared SQLite file. A lease stops two devices at once. |
| 4 | **Releasing is manual; updating is not.** We cut a release on GitHub; the tool reads it, tells the owner, and installs it itself — like any desktop application. | **Overrides `CLAUDE.md`'s "silent OTA" requirement**: the install is not silent, it is announced and accepted. It is also not a manual download — the earlier wording said "explicit user install" and that was wrong. The pattern is already proven in `mbiXaddin/Infrastructure/Update/UpdateService.cs`: `CheckForUpdatesAsync` → `ShowUpdatePromptIfNeeded` → `ExecuteFullInstallAsync`, with a 10-second check timeout held separately from the client timeout so a stalled GitHub fetch cannot hang startup. Copy it. |
| 5 | The existing Excel add-in **reads from a Google Sheet**. | The Console's job is to write that Sheet. Sheets is a publishing target, never the configuration store. |
| 6 | First publish: **owner plus a few testers, unlisted**. | A privacy policy and a support contact are required; the repository has neither. The shipped build needs only `drive.file`, which is not sensitive — see Decision 20 — so verification is not a gate here or later. |
| 7 | **Engine gets ONE database** covering every crawl type it performs. | `general.db` retires. One migration stream. A question can cross types: *which contractor also sells?* |
| 8 | On a new device with no engine, the owner **sees his data and exports it**. | The backup bundle must carry a plain export beside the `.db`. See §5. |
| 9 | Databases are **managed only through ScrapeX** — location, backup, restore, migration. | The controls live in the extension; Engine executes them. A browser extension cannot create a SQLite file. |
| 10 | Open-source tools **hand their output to Engine**, which imports it. | The tool writes its own files in its own shape and never touches Engine's database — so there is no interference and no third SQLite. |
| 11 | Open-source tools come **last, one at a time**, each for a stated need. | The install contract is proved once with Engine, then widened by one tool that has a real requirement behind it. |
| 12 | Drive upload frequency is **a user setting**. | Default: compressed, after any crawl that changed something. The warehouse is 112 MB; a daily full upload that changes nothing is not free. |
| 13 | Entity tracking records **appearance, disappearance, AND field-level change**. | A contractor's grade moving 3rd → 2nd, a tender's closing date slipping, are events — not just "still there". |
| 14 | The extension is **ScrapeX**; the local engine is **Engine**. | In the catalogue: `Engine — installed, v1.2.3` beside `Scrapy — not installed`. Ours by role, theirs by name. |
| 16 | **An audited source and a user-added one are visibly different.** | `sources.yaml` carries 12 audited sources today with no field telling them apart. A user who adds a site and gets poor data must see *why* — `audited` beside `you added this` — or they will read it as the product being broken. |
| 17 | **Crawl scope is a per-source setting**, not a project-wide rule. | listing only · listing + details for a named slice · full once then listing. See M6. |
| 18 | **For external tools, build the seam and not the tools.** | The install/health/import contract is laid so it can be used when a need appears; if Engine does the job, the matter is dropped. See M8. |
| 21 | **Two release paths, and a manual tag starts each.** `scrapex-vX` builds the extension and pushes it to the Chrome Web Store; `engine-vY` builds and publishes a GitHub Release. | The owner decides when each ships. Neither triggers the other, which is what makes them genuinely separate. |
| 22 | **The engine binary is unsigned for now.** | The owner and a few testers accept one SmartScreen warning. A certificate costs money and identity verification yearly and buys nothing before commercialisation; the release path is built so signing is one step added later. |
| 20 | **The Console is the owner's alone and is never published.** | It therefore carries the only Google scope that is sensitive, and the shipped build asks for `drive.file` only — see below. Excluding it is a security decision, not just a commercial one. |
| 19 | **The data path is a published Google Sheet.** Engine writes the table there; the Console puts its TSV link in `SOURCE_URI`. | The only path that works today with no change to XaddIn and from any machine. A local file passes the validator and is refused by the ingester at `DataIngestionService.cs:734` — see §5b. The table is readable by anyone holding the URL; acceptable for the owner's own data, a separate decision at commercialisation. |
| 15 | **The Python package stays `scrapex/`.** `Engine` is the product name, not the directory. | The user never sees a directory. Renaming costs 748 import lines in tests alone, 188 `python -m scrapex` call sites in CI, docs and JS, a reinstall of the editable package, and five hard-coded paths — for nothing anyone can see. A capitalised `Engine/` would also work on Windows and fail on Linux, where CI runs. |

---

## 2. What the previous plan got factually wrong

Measured against the repository and the live warehouse on 2026-08-05.

| The plan said | Measured |
|---|---|
| `apps/extension`, `apps/marketlens`, `apps/engine-host` | The tree is `scrapex/ extension/ contract/ contracts/ db/ tests/ packaging/ apps_script/ docs/ spikes/ design/ tools/`. Relocating touches **620 tracked files and 1,044 import lines**, and breaks five hard-coded root paths including the migration directory and `sources.yaml`. Deleted — see §7. |
| scrapeX 0.6.0 · MarketLens 0.9.2 · protocol 2 | **0.2.0 · 0.2.0 · protocol 1** — and one gate enforces the same number across three files, which is why the compatibility check in Decision 4 is impossible today. |
| MarketLens is a stores-and-products engine | **GPP_ENERGY alone is 67,677 of 88,286 price observations — 76.7%** — fuel prices from a static HTML table. Decision 2 settles it. |
| Five connector families | **Eleven connector modules**: aramco, custom_json, gpp, heidelberg, hybris, jsonld, magento, salla, shopify, woocommerce, zid. |
| Domain Engines: Price, Listing, **Table** | "Table" is an *extraction method*, not a domain — the exact collapse `CLAUDE.md` §40 forbids. §4 separates the two axes. |
| §4.3 SQLite is the writer · §13 Drive is where the data lives | Twenty lines apart and incompatible. Decision 3 settles it: **Drive is backup and restore; the local database is the writer.** |
| Phase 1 = relocate the monorepo | `CLAUDE.md` forbids it three times, including *"Do not rename, relocate, or rewrite stable modules."* |

---

## 3. What already exists, so it is never budgeted twice

- **The generic model is already built.** Eleven tables exist in the general stream and are unused: `dataset_definition`, `dataset_schema_version`, `field_definition`, `generic_record`, `generic_record_revision`, `generic_ingestion`, `generic_page_snapshot`, `dataset_relationship`, `relationship_field_pair`, `schema_version_field`, `site_profile`.
- **The lifecycle Decision 13 asks for is already built and tested**, on the price side: `first_seen_at`, `last_seen_at`, `status`, and `absence_period` with `missing_since` / `returned_at`. *Appeared, was confirmed, disappeared, came back* is generic machinery — a price is just one thing hung on it.
- **Two databases with typed registries**, distinct `application_id`s, independent migration streams, locks, health, backup and restore. Decision 7 collapses them; the machinery stays.
- **60 migrations**, in two streams sharing one directory — a hazard that has broken the engine twice.
- **Google Drive + Sheets in the engine**, least-privilege `drive.file` + `spreadsheets`, chosen to stay out of sensitive-scope verification.
- **Native messaging for control, local HTTP for data** — a deliberate split. Nine data commands were removed from native messaging once; they do not return.
- **A side panel and a full workspace**, job persistence, pause/resume/cancel, checkpoints, a mini-player.
- **A price model with real semantics**: `price_hash`, price periods, absence periods, append-only observations, unit charters with ranked witnesses, and row-level provenance enforced by triggers.
- **PyInstaller one-file packaging**, 109 test files, and a curated `sources.yaml` of 12 audited sources.

---

## 4. The architecture

```text
ScrapeX (extension) — the control room, and the only interface
    profile · engines · sources · jobs · browse · export · console
        │
        │  control: native messaging — small, paginated commands
        │  data:    HTTP on 127.0.0.1 — records, logs, exports
        ▼
Engine (installed) ─────────────────────► one database
    fetch ─→ extract ─→ domain ─→ store        prices + entities together
                                                  │
open-source tool ─→ its own output files ─────────┘  imported by Engine
                                                  │
                                                  ▼
                              Google Drive — backup, restore, lease
                              Google Sheets — what the Excel add-in reads
```

### Two axes that must never collapse

`CLAUDE.md` §40 forbids one enum meaning both *what the data is* and *how it was obtained*. Engine keeps them apart:

```text
extraction method          domain
  html_table                 prices      offers, periods, witnessed units
  repeated_dom               entities    contractors, tenders, equipment, jobs
  json / json_ld
  rest_api
  rendered (browser)
```

A tender in an HTML table goes `html_table → entities`. A price in the same table goes `html_table → prices`. Same extractor, different meaning.

### Four rules that follow

1. **The local database is the writer.** Drive holds versioned backups and one lease, which names the device and expires, with a recovery path for a stale one.
2. **Engine owns exactly one database.** An open-source tool never writes to it; it writes its own files and Engine imports them, so its output gains the same lifecycle and provenance as everything else.
3. **Control and data use different transports.**
4. **Sheets is an output.** The product is fully usable with no Google account.

---

## 5. The new-device requirement, and why it is cheap

Decision 8 asks that a fresh machine, signed in, with no engine installed, shows the data and exports it.

The expensive reading is "run SQLite in the extension". Spike 2 measured that (`spikes/opfs-sqlite/FINDINGS.md`): the schema runs in MV3 and survives restart, but OPFS loses WAL, an access handle is exclusive, the service worker cannot write, and `wa-sqlite` is **70–208× slower** than Python on the Data page's own query, with a fast VFS that cannot open an existing database.

**None of that is needed.** Viewing and exporting is read-only:

> Every Drive backup is a **bundle**: the `.db`, **plus a plain per-dataset export** (JSON Lines and CSV), **plus a manifest** with row counts and checksums. The extension downloads the bundle and reads the plain export.

The `.db` stays the restorable artefact for a machine that installs Engine. The plain export is what a bare extension reads. One writer in the backup path and a reader in the panel, against months for a browser-side database.

---

## 5b. The XaddIn boundary

**XaddIn is a separate product in a separate repository, and this plan does not
touch it.** ScrapeX serves it. That is the whole relationship, and the section is
organised around the boundary rather than around either side.

### Two products, one contract

```text
        THIS PLAN                    │            NOT THIS PLAN
                                     │
  ScrapeX (extension)                │   mbiXaddin (VSTO, C#, 49,600 lines)
  Engine  (python)                   │     ingestion · its own SQLite · sync
  Console (module in ScrapeX)        │     validation · licensing · updates
                                     │     ribbon rendering · icons
        produces ──────────────────► │ ◄────────────────── consumes
                                     │
            one TSV per dataset      │
            six configuration rows   │
```

Everything on the right already exists and works. **ScrapeX rebuilds none of it**
— duplicating ingestion, a local database, sync, validation, licensing or an
update channel is the easiest way to lose months to work already done.

Everything crossing the line is data and configuration. No code, no library, no
shared runtime, no build dependency. The two repositories never import each
other.

### What ScrapeX must produce — the entire obligation

1. **A TSV per dataset**, reachable at an `http(s)` URL. Decision 19: a published
   Google Sheet.
2. **Six rows describing it**, written into the six configuration sheets XaddIn
   already reads: one `TableDefinition`, its `SchemaRule` fields, one
   `DataSource`, its `DataMap`, one `ExportViews`, one `RibbonControls` button.

That is all. If both are right, the button appears in Excel. If either is wrong,
XaddIn's own validator refuses the row and the button does not appear — which is
the failure mode we want, because it cannot corrupt anything.

### The vocabularies ScrapeX must emit exactly

The configuration columns are closed enums declared in XaddIn's C#. ScrapeX must
write these strings verbatim, and refuse to write anything else:

```text
EntityType        COST PERF REF COMP CONVERSION COST_ENG AUDIT ASSEMBLY LIBRARY SYSTEM
BusinessDomain    MATERIAL LABOR EQUIPMENT VENDOR PROJECT FINANCE SYSTEM GARB
UpdateStrategy    ReplaceAll MergeUpsert Append
ColumnDataType    TEXT DECIMAL INT BOOL DATE DATETIME GUID JSON PERCENTAGE BLOB
SemanticRole      NONE PRICE QTY TOTAL UNIT NAME CONV_* and eleven MENU_*
MapSourceType     Header Index Context Constant Formula
MapMatchMode      Exact Contains StartsWith Regex Fuzzy
SyncFrequency     Manual Hourly Daily Weekly Monthly
```

These are the contract. They change only when XaddIn changes them, and then
ScrapeX follows — never the other way round.

### What is deliberately NOT ScrapeX's problem

- **How XaddIn stores what it pulls.** It has `LocalDbManager` and builds its own
  SQLite. Engine's database and XaddIn's database are unrelated files that never
  meet.
- **How the ribbon renders.** `RibbonControlService` owns that.
- **Licensing.** `LicenseService`, device fingerprinting and tiers are XaddIn's.
  ScrapeX writes a `LICENSE_TIER` string into a row and knows nothing else about
  it.
- **Sync scheduling on the Excel side.** ScrapeX writes `SyncFrequency`; XaddIn
  decides when to act on it.

### What would require changing XaddIn — a different project's backlog

Recorded so it is never smuggled into a ScrapeX milestone:

- **Reading a local file.** `DataIngestionService.cs:734` refuses any URI not
  starting with `http`, although the validator accepts local paths and
  `SourceType` declares `LocalCsv`, `LocalSqlite` and `RestApi`. Those three have
  no implementation. Teaching it local files is a few lines *there*, and it is
  what would let the data path stop being public — see Decision 19.
- **Authenticated fetching.** `HttpClientService` sends a request id and a user
  agent and nothing else; `DataSourceEntity.cs:667` says so: *"Currently all
  sources are public (Google Sheets published URLs — no auth needed)."*

Neither is required for anything in this plan. Both are the reason the data path
is a published sheet today.

### One thing worth copying, not importing

The two products independently arrived at the same rule. `SchemaRuleEntity` binds
**by role, not by physical column name, so a rename is safe** — which is exactly
`dataset_field`'s stable `field_key` against its editable `display_name`. And
XaddIn's `UpdateService` is the pattern Decision 4 adopts.

Copying a proven shape is not coupling. Sharing a library would be.

---

## 5c. The two release paths

They are not variations of one mechanism. They differ in who reviews, who
decides, and when the user gets it — and that difference is the reason the
compatibility check exists.

```text
EXTENSION                             ENGINE
tag scrapex-vX                        tag engine-vY
CI builds the zip                     CI builds on windows-latest (PyInstaller
CI uploads via the Web Store API      cannot cross-compile), attaches to a
Google REVIEWS it — a day or three    GitHub Release
Chrome pushes it to every user,       nothing reviews it
automatically, without asking         the EXTENSION notices, tells the owner,
                                      and installs on acceptance
```

**Google's store does not read GitHub.** It has no idea the repository exists.
Automation means our workflow pushes *to* the store through its API — the arrow
points the other way from how it is usually described, and the difference decides
what secrets are needed.

### What this asymmetry costs, and why M1 exists

Chrome can update the extension **tonight**, silently, while a user's Engine is
last month's. Nothing prevents that; it is how extension distribution works.

So the extension must state compatibility before any job starts, and refuse with
a named action rather than failing somewhere further in. That is not defensive
programming — it is the only thing standing between two independent release
cadences and a dead panel. The owner has already seen this failure once, on
2026-08-05, from a migration rather than a version.

### What must exist before the first upload

**Extension:** a Chrome Web Store developer account; a Google Cloud project
owning an upload client; three GitHub secrets (`client_id`, `client_secret`,
`refresh_token`); and a privacy policy and support contact — the repository has
neither today.

**Engine:** `runs-on: windows-latest`, because `packaging/build_engine.py` uses
PyInstaller and PyInstaller does not cross-compile. It already produces
`dist/scrapex-engine.exe` as one file; nothing publishes it yet.

### What exists today

Nothing. `.github/workflows/` holds `ci.yml` (one job: tests, parity, extension
tests, manifest) and `scrapex.yml` (a scheduled crawl). There is no release
automation of any kind, for either product.

---

## 6. Milestones

Each leaves the product runnable and ends in something the owner can open.

**The order was wrong in the first draft and is corrected here.** It ran M0 → M1 →
one database → entities, which is three milestones before anything new is visible.
But the single database is a prerequisite for the entity work and **for nothing
else** — backup, restore, the bare-extension view and publishing do not need it.

So the schema is left alone until there is a published, backed-up, multi-device
product. There are 88,286 price observations from 12 audited sources running daily
today; that is the thing to protect, not to rebuild around a capability that does
not exist yet.

### M0 — separate the three products *(nothing else works without this)*

Decision 4 asks the extension to detect an incompatible engine. **That is impossible while one version number covers both** — there is no "incompatible" when they always move together.

- Split the versions: ScrapeX and Engine get their own, and **the protocol number becomes the contract between them**.
- Move the panel tests to the extension. 134 Python tests drive a JavaScript UI today — they are not wrong, they caught a real `Escape` defect, but they bind the two products so a button change runs the whole engine suite. This needs a browser runner on the JS side and is the only real work in M0.
- Split CI by path, so an extension change does not rebuild the engine.

**Done when:** a button change runs the extension suite alone, and the two products carry different version numbers.

### M1 — sign in, and state the version truth

- Google sign-in moves to the extension (`identity`, an `oauth2` client, the same `drive.file` + `spreadsheets` scopes). The extension owns the token and lends it to Engine.
- The extension reads Engine's installed version and protocol and **states compatibility before any job can start**, with the exact action when it is insufficient.
- A GitHub Release feed is the source of truth for "latest Engine" (Decision 4).
  Three calls, mirroring what XaddIn already does: check on startup (with its own
  short timeout, so a stalled fetch never delays the panel), prompt when there is
  something newer, install on acceptance. The owner is never sent to a browser to
  fetch an installer.

**Done when:** an intentionally mismatched engine is refused with a named action, instead of a dead panel.

### M2 — backup, restore, and the lease

- The bundle of §5: `.db` + plain per-dataset export + manifest + checksums.
- Drive upload with the frequency setting of Decision 12.
- `latest.json` pointing only at a validated bundle; retention of N versions.
- A lease with device id and expiry, and a stale-lease recovery path.

**Done when:** a second machine restores the warehouse and refuses to run while the
first holds the lease.

### M3 — the bare-extension view

The panel reads the plain export from the bundle and shows datasets, rows and
history with no engine installed, and exports to XLSX/CSV.

### M4 — publish, unlisted

Privacy policy, data-handling and deletion statement, support contact — **none
exist today**.

Both release paths are built here, and §5c is the specification:

- `engine-vY` → build on `windows-latest`, attach `scrapex-engine.exe` to a
  GitHub Release. Unsigned (Decision 22).
- `scrapex-vX` → build the extension zip, upload through the Chrome Web Store
  API, unlisted listing.
- Neither tag triggers the other (Decision 21).

Google reviews the extension and does not review the engine, so the two arrive
on different days by design. M1's compatibility check is what makes that safe.

**Done when:** a tester installs from a link, signs in, and restores the owner's
data. *At this point the product is real: published, backed up, portable.*

### M5 — one database

- Collapse `general.db` into Engine's single database, and the two migration streams into one. `general.db` holds six rows, five of them bookkeeping — there is no data to migrate, only a schema to unify.
- Bring the eleven generic tables in beside the priced offers.
- Rename `MarketLens` → `Engine` throughout: kind marker, `~/.scrapex/` path, package name, docs.

**Done when:** one file, one migration stream, and every existing price test still passes.

### M6 — the first entity domain

One vertical slice, end to end, on `muqawil.org` — chosen because it is
server-rendered with `?page=` pagination and needs no browser.

**CRAWL SCOPE IS A PER-SOURCE SETTING, NOT A PROJECT DECISION** (owner, 2026-08-05).
Measured on muqawil to show why it has to be one: the listing is 860 pages — at the
shipped 1s pace, **14 minutes**. Every detail page is **121,157 requests: 34 hours
at 1s, 17 at 0.5s.** One crawl would take a day and a half, and change-tracking
means repeating it. Fourteen minutes and thirty-four hours are different products,
and which one a user wants is theirs to say.

So every source carries a scope, chosen in ScrapeX:

```text
listing only        the fields the listing page already shows
listing + details   details for a slice the user names — a city, a grade
full, then listing  one founding crawl, then the listing catches the changes
```

muqawil is the example, not the rule. It happens to publish grade, status, rating
and city **on the listing page itself**, so `listing only` may be the whole answer
there — but that is a fact about one site, discovered when it is added, not a
decision the schema should assume.

- A contractor is discovered, stored, and tracked: appeared, confirmed, disappeared, returned.
- **Field-level change** (Decision 13): a grade moving 3rd → 2nd is an event with a before, an after, and a date.
- It renders in the same table the prices use, from the dataset's own schema.

**Done when:** the owner opens a contractor and sees when its grade changed.

### M7 — the Console

**Scope: ScrapeX only.** Nothing in this milestone changes XaddIn, and nothing in
it may depend on XaddIn changing. See §5b for the boundary.

An owner-only module inside ScrapeX, authorised at the write layer and excluded
from the commercial build by build configuration.

**M7a — one dataset becomes one button.** The smallest thing that is real:

1. Engine publishes one dataset's table to a Google Sheet and holds its TSV link.
2. The Console generates the six rows that describe it.
3. It writes them into the six configuration sheets.
4. XaddIn — untouched — pulls, and the button appears.

**Done when:** the owner crawls a source, presses one thing in ScrapeX, opens
Excel, and the table is there, having typed nothing into a sheet.

**M7b — keep them true.** A schema that changes must not leave a stale
`SchemaRule` behind: a column appears, a hidden one stops being exported, a
display name changes. The Console re-generates and reports what moved.

**What ScrapeX can fill from what it already stores** — `ENTITY_KEY`,
`DISPLAY_NAME`, `ATTRIBUTE_KEY`, `DISPLAY_HEADER`, `ORDINAL_POS`, `IS_VISIBLE`,
`SOURCE_URI`, `VERSION_TAG`, and the `DataMap` rows. All of it is in
`dataset_field`, `sources.yaml` and the export header today.

**What it can derive** — `DATA_TYPE` from the stored values, and `SEMANTIC_ROLE`
for `PRICE`, `QTY` and `UNIT`, which Engine knows per row and can name the witness
for.

**What the owner will always type** — `SCREEN_TIP`, `SUPER_TIP`, `ICON`,
`LICENSE_TIER`, `BUSINESS_DOMAIN`, and where a button sits in the ribbon tree.
Judgements, not facts. The Console asks once and remembers.

**The guard.** Every enum value written must come from the closed vocabularies in
§5b, and the Console refuses to write a row carrying anything else. XaddIn's own
`ValidationOrchestrator` is the second line, not the first — relying on it would
mean discovering mistakes in Excel instead of in ScrapeX.

**THE SCOPE CEILING IS GONE, AND THIS MILESTONE IS WHY.**

Reading a Sheet the app did not create needs `https://www.googleapis.com/auth/spreadsheets`,
which Google classes as sensitive: verification to go public, and a 100-user cap
until then. Earlier drafts of this plan treated that as a standing cost of the
product.

It is not. **Only the Console needs it** — it is the only thing that touches the
six sheets the owner wrote by hand. Everything else writes to spreadsheets
ScrapeX created itself (`gdrive.ensure_spreadsheet` creates them inside the
app's own folder), and `drive.file` covers app-created files completely.

So, given Decision 20:

```text
shipped build     drive.file only        non-sensitive · no verification · no cap
owner build       + spreadsheets         the Console, never published
```

The scope must be declared in the owner build alone, not in the published
`manifest.json`. That makes excluding the Console a **security** decision as well
as a commercial one, and it removes what was the single largest obstacle between
this product and a public listing.

### M8 — the browser tier, and only then a tool

`developmentaid.org` returns an almost empty page to a plain fetch, and `cat.com`
refuses the connection outright. Those two are the browser tier.

**BUILD THE SEAM, NOT THE TOOLS** (owner, 2026-08-05): the foundation is laid so
it can be used when a need appears, and if Engine does the job the matter is
dropped.

`BrowserFetcher` exists in `connectors/base.py` — Playwright, an owner decision from
day one — and **no source uses it today**. The stated reason for installing an
external tool is "sites that need JavaScript", which is exactly what that class
does. Point it at developmentaid first. If it reads the tenders, this milestone is
a fetcher setting on a source and nothing more.

What an external tool genuinely buys is what we do not have: rotation,
fingerprinting, getting past a refusal. `cat.com` closing the connection outright
is evidence for that; a JavaScript page is not.

So the deliverable here is the **contract** — install, health, version, and an
importer that takes a tool's own output files into Engine's database (Decision 10)
— proved by one tool, for one site that actually blocked us. Not a catalogue.

---

## 7. Deleted, and why

- **The `apps/` relocation.** Its goal is met in place: `extension/package.json`, CI split by path, `scrapex-vX` and `engine-vY` tags, two distribution channels. Zero files move.
- **Four uncommitted backends** with "exact domain role TBD". M8 replaces them with one tool for one measured need.
- **MSIX and AppInstaller.** A code-signing certificate and a hosted feed, for an update mechanism Decision 4 replaced. PyInstaller already produces the artefact; GitHub Releases distributes it.
- **"Domain Engines: Price / Listing / Table."** No such modules; the taxonomy collapses domain into extraction method.
- **Google Sheets as the configuration store.** Decision 5 makes it a publishing target.
- **Hand-typed version numbers.** They come from the ledger the build gate enforces.

---

## 8. `CLAUDE.md` amendments

- **"Local Runtime Distribution and Updates"** requires silent OTA updates.
  Decision 4 replaces *silent* with *announced*: the tool checks GitHub, says
  there is a newer version, and installs it itself on acceptance. The brief's
  intent — that a non-technical user never touches a command line, `pip`, or a
  download page — is not weakened by this; it is how it gets delivered.
- **Cross-Cutting Gate DB1** mandates two physically separate databases. Decision 7 replaces it with one database per *engine*, which is what the gate was protecting: no engine may write into another's store.

Everything else stands, including the sections the previous plan omitted: bilingual capture and RTL, the price-history semantics of §15, OS resource limits, proxy and anti-bot handling, and adapter drift.

---

## 9. Still open

1. **Is there a Chrome Web Store developer account, and which Google account owns it?** M6 cannot start without one.
2. **Which Google Cloud project owns the OAuth client?** The consent screen, test-user list and scopes live there.
3. **What does the Excel add-in expect the Sheet to look like** — tab names, header
   row, a view or the whole dataset? M7's shape depends on it.
4. **How much of the register a user wants**, per source, is the scope setting in M6
   — but the DEFAULT for a newly added source is not decided. `listing only` is the
   safe one: it can never cost 34 hours by accident.
