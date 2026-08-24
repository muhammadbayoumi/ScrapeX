# The engine's role, measured — the study behind `REQ-40`, `R-49` and `R-50`

> **THIS IS A MEASUREMENT AT A NAMED BASE, AND THAT IS WHY IT IS NOT IN THE CITATION
> GUARD.** Every `file:line` below was derived against **`31c369e`** (2026-08-22, #257)
> and is true of that commit. `main` has moved four times since — `d10e974`, `4522158`,
> `f1844af` and onward — so a citation here that no longer resolves against `HEAD` has
> not rotted: it is a reading of a tree you can still check out. Verify any line with
> `git show 31c369e:<path>`, never against `HEAD`.
>
> **It is deliberately outside `tests/test_the_documents_cite_what_they_claim.py`'s
> `DOCUMENTS`**, and the reason is the subject of `LESSONS.md` §7: a guard re-deriving
> these against `HEAD` would report hundreds of false failures and teach the next session
> that the guard is noise. **A known gap, named, beats a guard pointed at the wrong
> tree.** If this document is ever revised into a living one, it joins the tuple in the
> same change.
>
> **Produced by twenty-one agents across two studies on 2026-08-23**, every headline claim
> put to independent refuters. **Nine refutations were applied.** Where the text says
> `[CORRECTION APPLIED]`, a first-pass number did not survive re-measurement and the
> weaker number is the one that stands — including the headline one: 9,511,282 bytes /
> 0.79% / 126x could not be reproduced, and 16,151,610 / 1.34% / 74x replaced it.
>
> **Three things landed after it was written and it does not know them:**
> - **`R-49`** — `docs/MIGRATION-PLAN.md` (2026-08-12) is the base plan; older conflicts
>   are superseded, newer ones are his. That settles eight of the contradictions in §6.
> - **`R-50`** — *"the engine is a helper to the extension, and any task the extension CAN
>   perform moves to it."* **This is the owner's own answer to §3.** The four-question test
>   in §3 is not superseded by it — it is the operational form of it, and `T1` ("does the
>   work need the machine?") is `R-50`'s question asked of one row.
> - **`engine-v0.3.0` could not serve a page at all** — `packaging/build_engine.py`
>   bundled two data directories where the runtime opens five. §9's not-measured list does
>   not contain it, because nobody had looked.

---

**Study commissioned 2026-08-23.** Measured on the **main checkout**
`C:\Users\User01\source\repos\ScrapeX` at **`f1844af`**
(`f1844af200f01949638201b3e091ab14f89d1eb0`, branch `main`, tree clean).

Most of the underlying passes measured `31c369e`. Three commits have landed since —
`d10e974` (#258), `4522158` (#259), `f1844af` (#261) — and they moved **line numbers
in `scrapex/webui/app.py` from line 2060 onward** and **overturned one verdict**
(a generic dataset now gets a menu). **Every `file:line` in this document was
re-derived at `f1844af`.** Where an earlier pass was refuted, the correction is
applied and marked **[CORRECTION APPLIED]**.

The live warehouse was opened only as
`sqlite3.connect("file:…?mode=ro", uri=True)`. Nothing in the repository was written.

---

## 1. The verdict on his premise

**Yes — and it costs 16,151,610 bytes, which is 1.34% of the warehouse.** His premise
is arithmetically correct and cheaper than any written document implies. The live
warehouse is **1,203,191,808 bytes** (1,147.5 MiB, `user_version` 10, 56 tables, plus
a 19,067,392-byte hot WAL). I dumped every row a human would ever browse — all 93,620
`price_observation`, all 18,008 `generic_record` (17,304 `contractors` + 704
`contractor_profiles`), all 53,143 `generic_record_revision`: **164,771 rows,
161,459,448 bytes of JSON Lines, 16,151,610 bytes gzipped at level 6, built in 3.4
seconds** against the live file while a crawl was writing. That is **74× smaller than
the database**, and a browser decompresses it with no library and no WebAssembly
(`extension/bundleview.js:29` — `const stream = blob.stream().pipeThrough(new
DecompressionStream("gzip"));`). **[CORRECTION APPLIED:** an earlier pass reported
9,511,282 bytes / 0.79% / 126×; I could not reproduce it and re-measured 16,151,610 /
1.34% / 74×. The conclusion survives at 59% of the claimed strength.**]** But *today*
his premise is met for **12 of 14 datasets and 0 of his 18,008 contractor records**:
the one artefact a bare panel can read is
`C:\Users\User01\.scrapex\engine\scrapex-bundle-20260822-153242-panel.jsonl.gz`
(4,386,341 bytes, 120,769 lines, 72,972,692 uncompressed — I decompressed and counted
it), and it carries only the 12 price shops, because `scrapex/bundle.py:140` —
`available = [s.source_key for s in list_sources(conn)]` — asks
`scrapex/reports.py:104`, which is `SELECT source_key FROM source_site ORDER BY
source_key` (12 rows); `scrapex/bundle.py` contains **zero** references to
`generic_record` or `dataset_definition`. It is also **silently truncated**:
`scrapex/reports.py:1493` reads `limit: int = 40_000`, GPP_ENERGY has 70,747
active-variant observations, and the pack's GPP_ENERGY history block is **exactly
40,000 lines** — 30,747 rows (43.5%) dropped with no notice. And what the panel
*renders* offline is not data: `extension/app.js:4471-4477` paints
`${esc(d.source_key)}`, `${fmtCount(d.rows)} rows` and `"with change history"` per
card, with no `data-open` and no export control, while
`extension/bundleview.js:82` `rowsOf` and `:94` `toCsv` — the row viewer and the
exporter — have **no production caller** (`extension/app.js:23` imports
`{ readPanelPack, datasetSummaries }` and nothing else). So: **the road is open, the
arithmetic is favourable by 74×, three pieces are already written, and against
Decision 8's own words he sees row counts and exports nothing.**

---

## 2. The table — every engine responsibility, and which side it lands on

**Accounting.** 115 route decorators (`scrapex/webui/app.py` 95, `catalog_api.py` 8,
`update_api.py` 3, `database_api.py` 3, `scrapex/extract/api.py` 6), mounting **125
distinct paths** — the extra 8 are `catalog_api` mounted twice
(`scrapex/webui/app.py:2060` and `:2063`). 6 native-messaging commands
(`scrapex/native.py:61-64`). 25 CLI subcommands (`scrapex.cli.subcommands()` returns
25). Below: **60 stay an app · 43 move to the phone · 12 dead = 115.** Every row is
accounted for.

`needs a local process` below means the work is impossible in a browser for a stated
technical reason — network fetch to an arbitrary origin, filesystem or process work,
or the SQLite **writer** lock — not merely that HTTP happens to be the transport today.

### 2A · STAYS AN APP — 60 route decorators

| responsibility | evidence (`file:line`) | today | under the phone model | why |
|---|---|---|---|---|
| Start / restart itself | `scrapex/webui/app.py:1103` `@app.post("/api/engine/restart")`; `scrapex/cli.py:702-703` "It exists because a process cannot free its own port and then bind it." | panel button → engine spawns `relaunch.py`, `os._exit(0)` | unchanged | A process cannot free its own port and re-bind it |
| Register itself with Chrome | `scrapex/webui/app.py:1141` `@app.post("/api/native-host/register")`; `scrapex/nativehost.py:151` `key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"` | panel-reachable, unauthenticated by design | **must gain a per-app host name** (§5) | Writes an HKCU key and a file on disk |
| Say it is installed and alive | `scrapex/webui/app.py:1424` `@app.get("/api/health")` — 11 keys, measured live: 654 ms, `version` `"0.3.1"`, `worker_alive` `true` | one address, one answer | **one such answer per installed app** | Only a running process can report that it is running |
| Apply the version gate | `scrapex/webui/app.py:1562` `@app.get("/api/version")`; R-07 already ruled the *advert* goes | gate + advert | gate stays, `latest_extension_version` goes | The refusal must be enforceable while the panel is stale |
| Fetch an arbitrary origin (probe) | `scrapex/webui/app.py:1841` `@app.post("/api/probe")` | live network I/O | unchanged | Politeness, user-agent and pacing come from `crawl_settings` |
| Read robots.txt as the crawler | `scrapex/webui/app.py:1747` `@app.get("/api/sources/{source_key}/robots")` — `httpx.Client(... headers={"User-Agent": agent})` | live fetch dressed as a GET | unchanged | It must answer *as the crawler*, not as Chrome |
| The source registry — 6 write routes | `:1689` active · `:1711` POST sources · `:1833` edit · `:1880` rename · `:1928` DELETE · `:1944` wipe | rewrites `sources.yaml`, reconciles the scheduler | control on the phone, execution here | YAML file write + in-process reload |
| The source registry — 2 mixed reads | `:1592` `@app.get("/api/sources")` · `:1726` `@app.get("/api/sources/{source_key}")` | reads SQLite **+** `sources.yaml` **+** the journal directory | **must be split**: rows to the phone, machine facts here | Two of three inputs are engine-machine facts |
| Resolve a URL to a source | `:1652` `@app.get("/api/resolve")` | manifest-only, no DB | disappears if REQ-25 moves the registry | Pure function over `sources.yaml` |
| The panel's own navigation contract | `:1409` `@app.get("/api/ui")` | app defines the panel's nav | **becomes the app's capability declaration** (§5) | This is the seam the phone needs; it already exists for one app |
| Write a schedule | `:1994` `@app.post("/api/schedules/{source_key}")` | SQLite write under `write_lock` | unchanged | Whoever owns the writer lock owns the write |
| Column definitions — **a GET that commits** | `:2100` `@app.get("/api/fields/{source_key}")`, then `ensure_fields(...)` and `conn.commit()` inside the GET | commits on read; #261 added a catalogue branch that returns before the write for dataset keys | **cannot be served read-only** without changing behaviour | A read-only connection raises instead of returning a column list |
| Column / promotion / view writes | `:2184` POST fields · `:2167` POST promotable · `:2223` POST views | SQLite writes | control on the phone, execution here | Writer lock |
| Record a review decision | `:2261` POST review · `:2280` undo | SQLite writes | the decision is the phone's, the write is the app's | Writer lock |
| Output-destination status | `:2297` `@app.get("/api/outputs")` → `scrapex/outputs.py` `path.exists()`, `path.stat()` | stats the engine machine's filesystem | unchanged | No phone can answer "does that .xlsx exist on that PC" |
| Write settings | `:2411` `@app.post("/api/settings")` | writes 25 registered settings | crawl settings stay; presentation settings go (§2B) | Crawl pace / UA / obey-disallow govern the crawler |
| Refresh FX rates | `:2435` `@app.post("/api/rates/google-finance/refresh")` — `HttpFetcher(**crawl_settings(conn))` | fetch + write | unchanged | Fetch + writer lock |
| Write an .xlsx to a folder | `:2475` `@app.post("/api/outputs/excel/export")` | writes to an arbitrary local path | unchanged | Chrome cannot write to an arbitrary path |
| Mint the funnel token | `:2505` `@app.post("/api/outputs/apps-script/token")` | writes a secret into SQLite | unchanged | `app.py` states it: a lent token is "a credential living in a second place" |
| Storage status | `:2675` `@app.get("/api/storage")` | DB path, size, free space, backups | unchanged | Describes this machine's disk; nothing else can |
| Storage actions — 9 routes | `:2683` backup · `:2885` restore · `:2910` start-fresh · `:2944` open-folder · `:2966` repair · `:2970` compact · `:2974` export · `:2982` check-move · `:2991` move | file-level, destructive, all engine-page-only | control on the phone **with its interlocks** | Renames files while managing OS handles; launches Explorer |
| Build / hand over a backup bundle | `:2721` POST bundle · `:2788` GET archive · `:2858` GET panel-pack | zips 1.15 GB; streams "the one file a browser can read" | **panel-pack becomes the phone's data plane** | The zip needs a zip reader; only the gzip line does not |
| Retention — 4 write routes | `:3039` policy · `:3059` preview · `:3077` compact · `:3102` prune | rebuilds the warehouse behind a digest interlock | control on the phone **with the interlock** | Builds a candidate DB file on disk to measure it |
| Rebuild the price timeline | `:3142` `@app.post("/api/prices/rebuild")` | write under lock | unchanged | Writer lock |
| Enqueue a crawl | `:3190` `@app.post("/api/jobs")` — validates against the manifest at `:3145`-equivalent, reads the journal directory | job row + journal dir | unchanged | Enqueueing is meaningless without a local worker |
| Pause / resume / cancel a job | `:3268` `@app.post("/api/jobs/{job_ref}/control")` | writes a flag a live thread reads | unchanged | Controls a local thread |
| Build the .xlsx bytes | `:1193` `@app.get("/export/{source_key}.xlsx")` — 501s without `openpyxl` | server-built workbook | **arguable** — see Q4 | `MIGRATION-PLAN.md:60`: "Export stays in the engine \| it is SQL over SQLite, not a file move" |
| Catalogue writes — 4 | `scrapex/webui/catalog_api.py:55, :68, :84, :102` | writes into the General database | unchanged | Writer lock |
| Extraction writes — 2 | `scrapex/extract/api.py:90` save_snapshot · `:100` approve | writes page bytes into SQLite (46,430 rows measured) | unchanged | Writer lock, transactional multi-table |
| Fetch and verify an installer | `scrapex/webui/update_api.py:146` POST · `:224` GET `/plan` | 95 lines, **zero callers** | must gain a caller, cannot move | Its own docstring: Chrome grants "no way to verify a checksum, read a file off disk, or launch a process" |
| Database health / migration | `scrapex/webui/database_api.py:19` `/health` · `:32` `/upgrade` · `:78` `/api/engine/health` | panel-reachable | unchanged | Only the process holding the files can answer |

### 2B · MOVES TO THE PHONE — 43 route decorators

| responsibility | evidence (`file:line`) | today | under the phone model | why |
|---|---|---|---|---|
| **16 HTML pages** the engine renders | `:747` `/` · `:798` `/data` · `:813` `/data/google-finance` · `:900` `/source/{key}` · `:1072` `/data-model` · `:1176` `/schema` · `:1227` `/source/{k}/offer/{id}` · `:1285` `/changes` · `:1298` `/history` · `:1308` `/review` · `:1318` `/jobs` · `:1328` `/schedules` · `:1354` `/logs` · `:1370` `/exports` · `:1380` `/settings` · `:1397` `/sync` | 5,642 lines across 29 templates, **unchanged since 2026-08-12** | deleted (B1/B4/B6) | `docs/PLATFORM-PLAN.md:9`: "**ScrapeX** — the Chrome extension. The control room, and the only interface." |
| One source's whole table | `:1030` `@app.get("/api/table/{source_key}")` | **the single engine dependency of the ported Data page** — `extension/data.js:71-72` | must stop requiring a *running* engine | `extension/data.html:15-16`: "nothing else can read a 119 MB local database yet. Removing that is Phase C" |
| One offer's whole story | `:1254` `@app.get("/api/offer/{source_key}/{offer_id}")` | built for the panel; called only by `grid.js` | pure read | SELECTs only |
| Read the schedules | `:1980` `@app.get("/api/schedules")` | pure read; its payload says "Schedules run only while the ScrapeX engine is running" | pure read | Reading a schedule and running it are different sides |
| Promotable attributes (read) | `:2150` `@app.get("/api/promotable/{source_key}")` | pure read; unlike its `fields` sibling it does **not** commit | pure read | SELECTs only |
| Read settings | `:2334` `@app.get("/api/settings")` | pure read of preferences | **inverts** — the phone holds them, the engine reads them | R-04, ruled 2026-08-01, 8 of 10 still unmoved (§6) |
| Palette + time zone, read **and write** | `:2342` GET / `:2357` POST appearance · `:2379` GET / `:2395` POST timezone | 4 routes for a browser display preference | 4 routes deleted | `extension/appearance.js:19-21` already keeps `scrapex-appearance-v2` in `window.localStorage`; `chrome.storage.sync` needs no engine |
| Google Finance status | `:2427` `@app.get("/api/rates/google-finance")` | pure read, 25 `currency_rate` rows | pure read | SELECTs only |
| The Apps Script source text | `:2488` `@app.get("/api/outputs/apps-script/script")` | the engine serves a constant | ship the file in the extension | It is a static asset |
| Send to the Sheet | `:2496` test · `:2500` send | HMAC + HTTPS from the engine | the phone already does the Google half | `scrapex/gdrive.py` (145 lines) was **deleted** in `8272bf3` and replaced by `extension/sheets.js` — the one completed migration |
| The rows the phone writes to a Sheet | `:2809` `@app.get("/api/export/{source_key}")` | pure read, capped 40,000 | pure read | Its docstring calls it "THE LAST GAP IN THE OWNER'S RULING OF 2026-08-11" — the pattern to repeat |
| Price timeline / price on a date | `:3121` timeline · `:3132` on | pure reads over 22,645 `price_period` rows | pure reads | SELECTs only |
| Change feed | `:3177` `@app.get("/api/changes")` | pure read over 145,239 `change_event` rows | pure read | SELECTs only |
| Job history and logs | `:3243` GET jobs · `:3256` GET jobs/{ref} · `:3288` GET logs | pure reads; `extension/app.js` already notes "`/api/jobs` is destination data" | pure reads; `{ref}` stays live-poll only | Reading history is history, not control |
| Catalogue reads — 4 | `catalog_api.py:62` sites · `:75` datasets · `:93` fields · `:111` relationships | typed, cursor-paginated, `response_model`'d — **zero callers on either prefix** | the cleanest read boundary in the codebase | SELECTs only |
| Extraction reads — 3 | `extract/api.py:96` candidates · `:111` datasets · `:122` records | serve **17,304 + 704 contractor records**, reachable only from a page nothing links to | pure reads over his largest dataset | SELECTs only; the CPU work is HTML parsing a browser does better |

### 2C · ALREADY THE PHONE'S — measured, not asserted

| responsibility | evidence (`file:line`) | today |
|---|---|---|
| Google Sheets + Drive | `scrapex/gdrive.py` deleted in `8272bf3` (145 lines, `−70` from `app.py`, `−214` from `sync.html`, `−118` test lines); `extension/sheets.js` 320 lines, `extension/drive.js` 536 lines | **the only completed move in the repository.** The template for every other row |
| The Console | `extension/console.js` 1,509 lines; imports 10 modules, **none** of which imports `engine.js`, `transport.js` or `backend.js` (verified by import graph, not by its comment) | proof a 1,500-line page can be 100% engine-free |
| The engine release check | `extension/releases.js:31-32` fetches `raw.githubusercontent.com/…/version.json` with its own 4 s timeout | the phone already owns it; the engine's copy (`update_api.py:89`) has **zero** callers |
| The panel shell and all 15 views | `extension/app.html:2241` "The shell above needs no JavaScript to be correct."; `extension/app.js:275` `showView()` never consults `state.engineUp` | paints and navigates with no engine |
| Palette / time zone, local-first | `extension/appearance.js:167` reads `window.localStorage` first; `connect()` is guarded on a non-empty base URL | correct with no engine; sync is best-effort |
| The engine-free reader | `extension/bundleview.js:28` `readPanelPack` · `:70` `datasetSummaries`; `extension/app.js:4440` `browseFromDrive`, guarded by `tests/test_panel_wiring.py:371` | works; renders **counts only**; gated on Google sign-in at `extension/app.js:4441` |
| Per-action capability filtering | `extension/app.js:4544-4576` `SOURCE_ACTIONS` — 6 actions each carrying `route` and a `proof` marker; `:4593-4597` `sourceActions()` filters by measured capability | **the capability-declaration pattern already exists — for source kinds, not for apps** |

### 2D · DEAD — 12 route decorators, plus an 8-path duplicate mount

Every one of the **nine** dead routes named at `docs/MIGRATION-PLAN.md:178-184`
("the **9 dead routes** (class C) with no caller anywhere") is **still dead eleven
days later** — I re-checked each against `extension/`,
`scrapex/webui/templates/` and `scrapex/webui/static/` at `f1844af`.

| responsibility | evidence (`file:line`) | callers | note |
|---|---|---|---|
| Feature manifest | `:1587` `@app.get("/api/features")` | 0 | on B1's list 2026-08-12 |
| Add-a-source page | `:1660` `@app.get("/manage")` | engine template only; absent from `ui_manifest` and the panel's 13-entry nav | B1 names it first |
| Delete a saved view | `:2231` `@app.delete("/api/views/{saved_view_id}")` | 0 | building saved views in the panel **revives** it |
| Review queue (list) | `:2239` `@app.get("/api/review")` | 0 | a **pure read** the phone would need |
| Suggest matches | `:2247` `@app.post("/api/review/suggest")` | 0 | |
| Excel status | `:2467` `@app.get("/api/outputs/excel")` | 0 | machine-local; could never move |
| Apps Script status | `:2480` `@app.get("/api/outputs/apps-script")` | 0 | alive only through `/api/outputs` |
| Retention view | `:3031` `@app.get("/api/retention")` | 0 (the four action routes have callers; the bare GET does not) | a **pure read**; B3 needs it — wire it, do not delete it |
| Browse records | `:3158` `@app.get("/api/records")` | 0 — the only mention is `extension/data.js:16` saying it is the *wrong* endpoint | a **pure read** built for the panel and never wired |
| Capture (the product's core write) | `:3315` `@app.post("/api/capture")` | 0 | `app.py`'s own docstring describes it as the write the extension triggers |
| Engine-side release check | `update_api.py:89` `@router.get("")` | 0 — `grep -rn "api/update"` over `scrapex/`, `extension/`, `tests/` returns only the prefix declaration | the phone does it itself (`releases.js:31`) |
| Generic-extraction workspace | `extract/api.py:82` `@router.get("/datasets")` | 0 — absent from `ui_manifest.py`, from the panel's nav, and from every `href` | **614 lines of interface, and the only surface serving the 5 routes over his 18,008 contractor records** |
| `/api/catalog/*` alias | `scrapex/webui/app.py:2063` — a second mount of the same router | 0 on that prefix | **8 of 125 mounted paths (6.4%) serving nobody.** The cheapest deletion in the study |

### 2E · NATIVE MESSAGING — all 6 commands

`STANDALONE_COMMANDS` at `scrapex/native.py:61-64`. This is the **only transport that
works when the engine's HTTP server is down**, so everything the phone must do on a
dead app has to arrive here.

| command | evidence | side | why |
|---|---|---|---|
| `START_ENGINE` | `scrapex/native.py:132`; `:133-137` "a page cannot start a process, but Chrome starts this host on demand — so the host is the hand that reaches the machine" | **app** | Irreducible |
| `CHECK_STARTUP` | `:140`; `:141-143` "The HTTP engine may be the very thing that cannot start" | **app** | Must answer while HTTP is down |
| `UPGRADE_DATABASE` | `:146`; `:147-149` "its HTTP request had no server left to receive it after a failed restart" | **app** | The repair must not live behind the server it repairs |
| `AUTOSTART_STATUS` | `:152` | **app** | A file in the Windows Startup folder |
| `SET_AUTOSTART` | `:156` | **app** | Same file, written |
| `PING` | `:128` | **dead** | Zero extension callers. `sendNative` is private (`extension/transport.js:63`, not exported) with five call sites, none of them PING; the only `PING` in `extension/` is a **comment** at `transport.js:29`. It now has exactly the property that justified deleting the nine data commands |
| *the nine retired data commands* | `git show 0a2209c^:scrapex/native.py` → 13 commands; `git show 0a2209c:` → 4. **13 − 4 = 9.** `tests/test_native.py:28-31` `RETIRED_COMMANDS` holds nine names | **precedent** | `scrapex/native.py:13-16`: "not one of them had a caller anywhere in the extension; the only thing exercising them was their own tests" |

**The precedent is not "nothing returns."** The host went **13 → 4 → 6**: the nine left
in `0a2209c` (2026-07-29) and `CHECK_STARTUP` + `UPGRADE_DATABASE` were **added** in
`04687f3` four days later. `docs/PLATFORM-PLAN.md:80` says "they do not return", which is
true of the nine and false of the surface. The operative rule is written only in code
comments: **a command belongs on native messaging exactly when it must work while the
engine is down.** `git log -1 --format='%B' 04687f3` is a single line with no body —
**a boundary decision taken and never recorded.**

### 2F · CLI — all 25 subcommands

`scrapex.cli.subcommands()` returns 25. For a CLI command the question is not "which
side executes it" — it is **"can the phone press it at all."** `packaging/engine_entry.py`
derives the shipped command set from the parser, so every row below ships to users.

| command | evidence | reachable from the panel today | under the phone model |
|---|---|---|---|
| `ui` | `scrapex/cli.py:1252` | yes (native `START_ENGINE`) | app |
| `relaunch` | `:1259`; `:702-703` "a process cannot free its own port and then bind it" | yes (`/api/engine/restart`) | app, internal |
| `native-host` | `:1266` | Chrome invokes it | app, the boundary itself |
| `install-native-host` | `:1271`; only `--extension-id` and `--executable`, **no host-name flag** | partly (`/api/native-host/register`, which needs HTTP already up) | **must gain a per-app host name** |
| `autostart` | `:1091`; native `SET_AUTOSTART` | **yes — this is the model to copy** | control on the phone, OS write here |
| `init-db` | `:1115` | yes (native `UPGRADE_DATABASE`) | app |
| `database-status` | `:1130` | yes (native `CHECK_STARTUP`) | app, answers while HTTP is down |
| `backup-databases` | `:1148` | yes (`/api/storage/backup`) | app |
| `restore-database` | `:1153` | yes (`/api/storage/restore`) | app |
| `wipe-source` | `:1158` | yes (`/api/sources/{k}/wipe`) — **manifest sources only** | app; the contractor dataset has no wipe path from either surface |
| `crawl` | `:1212`; `scrapex/cli.py:577` `build_connector(entry)` vs `scrapex/capture.py:222` `build_connector(entry, crawl_settings(conn))` | a *different* implementation is (`POST /api/jobs`) | app — **and the two disagree: `scrapex crawl` ignores his saved politeness and timeout settings** |
| `ingest` | `:1220` | same (through `capture_source`) | app |
| `peek` | `:1227` | yes (`/api/table`) | redundant second door |
| `status` | `:1278` | yes (`/api/sources` carries `last_success`) | redundant second door |
| `export` | `:1243` | yes (`/api/export/{k}`, `/export/{k}.xlsx`) | rows from the app; the file is arguable (Q4) |
| `run-due` | `:1107`; `:1041` `native._spawn_engine(port)` | machine-invoked (the Windows task) | app — **the one responsibility provably impossible in a browser: acting while Chrome is closed** |
| `contractors` (5 verbs: `--plan --crawl --details --coverage --approve`) | `:1203`; `scrapex/contractors.py` imported outside `cli.py` only by `directories.py` and `sightings.py` | **NO** | **a real gap.** 18,008 rows produced by a path the phone cannot press |
| `merge-warehouse` | `:1134` | **NO** | **a real gap.** R-42/R-43 depend on it; it has no surface |
| `schedule` (Windows Scheduled Task) | `:1099`; `osschedule` imported only at `cli.py:944` | **NO** | **the sharpest inconsistency.** The panel can *create* crawl schedules and cannot enable the only thing that fires them while the engine is down — while its twin `autostart` has a switch |
| `carry-over` | `:1122`; named only inside an error message at `databases/registry.py:83` | **NO** | a refusal that must become a button |
| `sources` (the state board) | `:1185` "Works without a warehouse"; `sourceboard` has **zero** callers outside `cli.py` | **NO** | a pure read answering «اى الجديد واى الى خلص» that only a terminal can give |
| `validate-manifest` | `:1166`; its own docstring: "same check runs in CI" | no | **should leave the shipped binary** |
| `export-contract` | `:1170`; writes into `ROOT_DIR / "contracts"` | no | **should leave the shipped binary** — release codegen |
| `export-version` | `:1173`; writes `CHANGELOG.md` and `docs/data-page-schema.md` | no | **should leave the shipped binary** |
| `funnel-test` | `:1177` vs `scrapex/outputs.py:240-244` — same `source_key`, same header `["check"]`, same rows `[["ok"]]` | its duplicate is (`/api/outputs/apps-script/test`) | **should leave the shipped binary** — byte-for-byte duplication |

---

## 3. The test for the boundary, stated so it can be argued with

Derived from the measurements above, not from taste. Four questions in order; the
first "yes" decides it.

> **The boundary test.**
>
> **T1 — Does the work need the machine?** Does it require an arbitrary-origin fetch
> with the crawler's identity, a filesystem or registry or process operation, or the
> **SQLite writer lock**? → **It is an app's.** Evidence that this is the real line and
> not HTTP convenience: `spikes/opfs-sqlite/FINDINGS.md:31` — "the service worker can
> read the warehouse but can **never write** it".
>
> **T2 — Must it work while the app is DOWN?** → **It goes on native messaging**, not
> HTTP. This is the unwritten rule the host's own history proves: 13 → 4 → 6, with
> `CHECK_STARTUP` and `UPGRADE_DATABASE` re-crossing the boundary four days after the
> nine left, for the reason at `scrapex/native.py:141-143` — "The HTTP engine may be
> the very thing that cannot start."
>
> **T3 — Is it only SELECTs over stored rows?** → **It is the phone's, and it must not
> require a running app.** A read that dies with the process fails his premise
> whichever process serves it. `extension/data.js:71-81` is the counter-example: the
> page moved and the dependency did not.
>
> **T4 — Is it a presentation or preference decision?** → **It is the phone's, with no
> app involved at all.** `extension/appearance.js:19-21` and `extension/timezone.js:44-45`
> already keep the value locally; the four `/api/appearance` + `/api/timezone` routes
> are the measured proof the engine's role has not shrunk.
>
> **The tie-breaker, replacing Decision 25's axis.** Decision 25 groups by **who serves
> a page**. Measured, that axis does not predict behaviour: `extension/app.js:4414-4430`
> gives the Data view a no-engine path, so one member of the group Decision 25 calls dead
> is not dead. The axis that does predict behaviour is: **does this page need the app to
> be RUNNING, or only to have RUN once, or not at all?** Data: *have run once* (a pack
> exists). Run: *running, always*. Console: *never*. Group by that.

**One consequence to accept before applying T3.** Every route this test sends to the
phone is a route the phone must be able to serve **without the app**, and 20 of the 43
are pure reads whose rows live in a file only a local process can open. T3 therefore
implies a data plane (§5), not just a page move. Marking that explicitly because the
last migration moved a page and stopped.

---

## 4. "The engine's job is fetch" — shorthand, and here is the missing half

The sentence «**المحرك مهمته fetch**» is recorded on main at
`docs/plans/2026-08-22-the-source-page-moves-into-the-extension.md:48` — "**«المحرك
مهمته fetch».** He has said the engine's job is *fetch*, and a research workflow on
exactly that boundary is running." It is **shorthand**, and it is shorthand in a
direction that matters: **fetch is the part of the engine's job least tied to the
engine.** `extension/manifest.json:27-35` grants `activeTab` and `tabs`, and its
`host_permissions` simply omit shop hosts — that is one manifest line, a **policy**
choice, not a browser limit.

Eight non-fetch responsibilities cannot run in a browser. Each with its technical
reason, all measured in this repository:

1. **Write SQLite.** `spikes/opfs-sqlite/FINDINGS.md:31`: "the service worker can read
   the warehouse but can **never write** it". `createSyncAccessHandle()` is
   `[Exposed=DedicatedWorker]`, and the MV3 service worker has neither the method nor
   the ability to spawn the one context that has it; one `INSERT` returns "unable to
   open database file".
2. **Concurrent writers.** `FINDINGS.md:31`: "No WAL (no OPFS VFS implements
   `xShmMap`); one exclusive handle per file with no queue, against a crawler that runs
   8 lanes on 8 connections."
3. **Own a file at a chosen path.** The warehouse is
   `C:\Users\User01\.scrapex\engine\scrapex-engine.db`; OPFS is origin-private, and the
   spike had to be *handed* the bytes over HTTP. `FINDINGS.md` states the residue:
   a warehouse "in a **normal file the user can copy**". `/api/storage/move` and
   `/api/storage/open-folder` have no browser primitive.
4. **Write to the OS.** A `.vbs` in the Startup folder (`scrapex/autostart.py`), an HKCU
   key (`scrapex/nativehost.py:151`), a Scheduled Task (`scrapex/osschedule.py`).
5. **Start a process.** `scrapex/native.py:133-134`: "a page cannot start a process".
6. **Act while Chrome is closed.** `scrapex/cli.py:1001-1042` (`run-due`). The spike
   explicitly cleared the MV3 lifecycle as the cause: "The lifecycle is not the
   blocker. The missing write primitive is." The reason is Chrome being **absent**, not
   the worker dying.
7. **`ATTACH` a second database** to merge another machine's warehouse
   (`scrapex/warehousemerge.py`) — the mechanism R-42/R-43 depend on.
8. **Migrate the schema under a write lock, backing up first** (`scrapex/cli.py:764-838`).
   Live right now: `/api/health` reports `schema_lag.pending = ['0002_contract_meta.sql',
   '0003_jobs.sql']`.

**The one-line replacement for the shorthand:** *the engine's job is to be the machine's
hands — the single owning **writer** of one SQLite file, and the only thing that can act
when the browser is not there. Fetch is what it does with those hands, not the reason it
exists.*

And one ceiling the phone metaphor cannot have: **`docs/RULINGS.md:928` — "The panel can
never be the installer, and this is a limit rather than a backlog item."** Its stated
reason is partly stale (**[CORRECTION APPLIED]**: it says the manifest grants "**no
`downloads`**", measured 2026-08-21; `extension/manifest.json:30` now grants `downloads`
and `extension/app.js:3599` calls `chrome.downloads.download`). Its **conclusion**
stands: Chrome will not let an extension read a file off disk to hash it, or launch a
process. **A phone that installs its own apps is not available on this platform.**

---

## 5. What the phone does not have yet, as fractions

| what the model needs | what exists | fraction | evidence |
|---|---|---|---|
| **An app registry** | one string in one storage slot | **1 app** | `extension/engine.js:8` `export const DEFAULT_BACKEND = "http://127.0.0.1:8000";` and `:11` `const { backend } = await chrome.storage.local.get("backend");` — one key, no list, no id, no shape for a second entry. All **40** `/api/` call sites in the extension are prefixed by `extension/backend.js:38` `let activeBackend = "";`. `extension/releases.js:171` `ENGINE_CANDIDATES` holds **6 rows**, each with `{id, name, icon, role, shape, licence}` and **no address, port or transport**. `releases.js` names the gap: "When an engine register does exist, this table is what it replaces — one export, one shape, six rows." |
| **Runtime address switching** | built and battle-tested | **1 of 1** | `extension/backend.js:68-77` `activateBackend()` aborts every in-flight request and bumps a generation "so answers from the old engine cannot land in a panel now pointed at a new one"; `extension/app.html:1765-1779` is a shipped "Connection address" control. **Switching apps is modelled; serving two at once is not.** |
| **A capability declaration per app** | a capability table per *source kind* | **0 apps / 6 actions** | `extension/app.js:4544-4576` `SOURCE_ACTIONS` — each action carries `route:` and a `proof:` marker (`RESOLVES_A_DATASET` / `MANIFEST_ONLY` / `NO_SECTION`), filtered at `:4593-4597`. The pattern the phone needs exists, one level down. At the app level: `scrapex/version.py` `CAPABILITIES` holds 8 entries, every one keyed to `Surface.PANEL` or `Surface.ENGINE` — a two-valued enum. `docs/MASTER-PLAN.md:380-395` (§8.4) designs the adapter descriptor with `discover / http_fetch / browser_render / extract / markdown / archive_warc / resume`: **0 lines implemented.** |
| **Install / absent / running states** | 7 verdicts, one probe, one blind spot | **2 of 3 distinguishable on a cold open** | `extension/app.js:3376-3419` `engineStatusFromState()` has 7 branches including "Installed, not running" at `:3407` — reachable only when `state.engineVersion` is truthy, and `state.engineVersion` is **in-memory only**, so it is unreachable on a cold open. `extension/transport.js:35` and `:52` classify `error.kind = "absent"` — "the one case that is genuinely 'not installed'" — and `checkStartup()` is called only from the restart handler, where `absent` is folded into a generic message. **The probe exists and is never generalised.** `extension/app.js:3703` `const installed = engine.id === SCRAPEX_ENGINE.id;` — for the other six, `extension/app.js:3668` prints a literal `<span class="badge">Not installed</span>`. **[CORRECTION APPLIED:** an earlier pass said "installed is never measured anywhere"; it is measured, once, for one host.**]** |
| **The data plane (his premise)** | transport built, payload price-only, renderer unwired | **12 of 14 datasets · 0 rows on screen · 0 exports** | See §1. `extension/bundleview.js:82` `rowsOf` and `:94` `toCsv` are exported, covered by `extension/tests/bundleview.test.mjs`, and imported by **nothing** in the product. `extension/app.js:4437-4438` even claims the wiring was done — "bundleview.js has been able to do this since the day it was written and nothing ever called it; this is the call" — and that call reaches `datasetSummaries` only. |
| **One extension → many apps** | the asymmetry runs the other way | **many→1, hard-coded** | `scrapex/nativehost.py:83` `MAX_ALLOWED_IDS = 5` — up to 5 **extensions** may share one app, added rather than replaced. But `nativehost.py:17` `HOST_NAME = "com.scrapex.engine"` gives one manifest filename, `:74` one `"path"`, `:151` one registry key. **Installing a second app today overwrites the first's manifest and registry key.** `extension/transport.js:20` retypes the same literal on the other side. **Nothing enumerates installed apps**: `winreg` is used only to write (`CreateKey`, `SetValueEx`); `grep -n 'EnumKey'` over `scrapex/` returns nothing. |
| **Per-app protocol versioning** | one scalar for the pair | **1 number** | `extension/transport.js:25` `export const PROTOCOL_VERSION = 1;` and `scrapex/native.py:49` `PROTOCOL_VERSION = 1`. `/api/health` publishes one `protocol_version`. One stale app would collide with the whole panel rather than be quarantined. |
| **A per-app identity on the wire** | published, never read | **0 readers** | `scrapex/webui/app.py:1533`-area and `scrapex/native.py:129` both send `"app": "scrapex"`; no reader exists in `engine.js`, `transport.js` or `app.js`. |
| **Ownership of the database with three apps** | one file, one owner | **1 of 1** | `~/.scrapex/databases.json` = `{"engine_path": "…scrapex-engine.db", "format_version": 2, "mode": "single"}`. `scrapex/database_ids.py:13` stamps `ENGINE_APPLICATION_ID = 0x5358454E`; `databases/registry.py` holds a singular `engine` field. **No table records which app collected a row** — `source_site`, `site_profile`, `dataset_definition`, `crawl_run` and `crawl_job` have no `produced_by` column (measured read-only). `docs/PLATFORM-PLAN.md:29` (Decision 10) says a tool "hands its output to Engine, which imports it" — which makes ScrapeX-Engine a **required hub**, not a sibling. And the only import door is closed: `scrapex/payload.py:215` `extra="forbid"` over `client: PayloadClient`, where `scrapex/vocab.py:441-445` is `PayloadClient = {cli, extension}` — **a third producer cannot construct a valid payload at all.** |
| **A settings store the phone owns** | 2 of 25 | **8%** | 25 registered settings; `extension/appearance.js:19` and `extension/timezone.js:44` keep local copies of exactly two (`ui_appearance`, `ui_time_zone`). R-04's eight remaining settings are still on engine templates (§6). |

**The one thing that is complete.** `extension/manifest.json:37` grants
`http://127.0.0.1/*` — **any loopback port.** The single axis that already admits N
apps, and nothing uses it.

---

## 6. The contradictions

Each stated as: the document says **X** at `path:line`, he now requires **Y**, so one
must be marked superseded under **C4**. **The ruling is his.**

**1 · Decision 25 — the grouping axis. This is the one to supersede.**
`docs/PLATFORM-PLAN.md:43`: "**The icon rail groups pages by who serves them.** Profile
and Engines in one container; Source, Run, Data and Google Finance in the next. The
second group is dead on a device with no engine installed… The boundary is drawn rather
than explained." He now requires that **Data not be dead there**. Two measurements:
(a) the boundary **is** drawn — `extension/app.css:1144-1155` `.rail-tablist` gives the
container a border and a background, and its comment at `:1138-1143` states the intent
("the owner should be able to see that boundary without reading anything"), guarded by
`tests/test_panel_dom.py:3244`. **[CORRECTION APPLIED:** an earlier pass searched the id
`#engine-tablist`, found no CSS, and concluded the boundary was markup-only; the element
is styled through its class.**]** (b) The *claim* is now stale for Data:
`extension/app.js:4414-4415` reads "**NOT A DEAD END ANY MORE.** This is the machine
with no engine on it", and `extension/app.html:2079` still says "every one of them is
dead until an engine is installed." **Decision 25's consequence is what his requirement
contradicts, and its axis is what has to change** (§3, tie-breaker). Nothing disables the
four buttons — `extension/app.js:209` is the only `.rail-item` handling and it positions
the indicator — so there is no gate to remove, only a rule to rewrite.

**2 · Decision 25 versus Decision 8, inside one document, 16 lines apart.**
`docs/PLATFORM-PLAN.md:27` (Decision 8): "On a new device with no engine, the owner
**sees his data and exports it**." `:43` (Decision 25): that group "is dead on a device
with no engine installed". Both stand; **neither is marked superseded.** His request
decides it in Decision 8's favour.

**3 · Decision 9 — the sentence is imprecise, and the imprecise half is load-bearing.**
`docs/PLATFORM-PLAN.md:28`: "A browser extension **cannot create a SQLite file**." Two
things are conflated and only one was measured. What the spike measured is **writing**:
`FINDINGS.md:31`, "the service worker can read the warehouse but can **never write** it";
and the residue that is genuinely true, a warehouse "in a **normal file the user can
copy**". A browser **can** create a SQLite database in OPFS — `FINDINGS.md` records a
40-table rebuild at **15,150 ms** that came out with `user_version = 0` from a source
stamped 54. **[CORRECTION APPLIED:** an earlier pass cited `FINDINGS.md:134-147` as proof
of creation; that table is the object count of an **imported** copy, not a creation.**]**
His premise needs only **reading**. Decision 9's blanket wording forecloses a question its
own evidence leaves open — so it is **not** a contradiction of his requirement, it is a
sentence that has to be split into three: (a) no normal disk file; (b) an MV3 service
worker can never write; (c) reading the live file is blocked by **WAL**, not by file
creation — the live header bytes 18/19 read **2,2** (I read them off disk) and wa-sqlite
refuses a WAL file with `SQLITE_CANTOPEN`.

**4 · §5's speed argument quotes the losing row.** `docs/PLATFORM-PLAN.md:134`: "`wa-sqlite`
is **70–208× slower** than Python on the Data page's own query, with a fast VFS that
cannot open an existing database." That is accurate **about wa-sqlite**. The spike's own
verdict row is `FINDINGS.md:30`: "| 2 | Speed | **Pass — with a different library.** A
sync-access-handle OPFS VFS runs the real Data page within **1.4–2.0×** of Python."
The 1.4–2.0× figure appears **nowhere** in the repository outside the spike, while the
70–208× half is repeated in five places. **[CORRECTION APPLIED:** an earlier pass called
this a contradiction; it is an omission, and it **strengthens** §5's conclusion rather
than undermining it — the surviving blockers (`FINDINGS.md:31`) are WAL loss, handle
exclusivity, refused `persist()`, and no service-worker write primitive, every one of
them a durability or write concern, plus wa-sqlite's read/open failure. Speed was never
the reason.**]** Worth recording so nobody re-opens the browser-database question on a
performance argument, or closes it on one.

**5 · `MIGRATION-PLAN.md:60` versus Decision 8, on export.**
"| Export stays in the engine | it is SQL over SQLite, not a file move |" (2026-08-12,
**later** than PLATFORM-PLAN's 2026-08-05) against Decision 8's "and **exports it**" for
a machine with no engine. They reconcile only through the bundle, and the bundle proves
the engine-side answer cannot serve a bare panel: `scrapex/bundle.py:110-116` writes a
`.csv` per table **inside the zip**, and only `panel.jsonl.gz` is lifted out. For a bare
extension, export is a re-derivation from the pack — which is why `toCsv` must exist.
**One of these two has to be marked superseded before M3 can be built.**

**6 · R-04 is ruled and unbuilt, 22 days on.** `docs/RULINGS.md` requires that the guard
"must read **every** template under `scrapex/webui/templates/`". Measured at `f1844af`:
`tests/test_settings_live_in_the_extension.py:26` is `WEB_SETTINGS = ROOT / "scrapex" /
"webui" / "templates" / "settings.html"` — one file — and **8 of the 10 settings** sit in
files the guard never opens: `excel_folder`, `excel_workbook`, `excel_schema`,
`excel_structure`, `excel_update` in `excel.html`; `funnel_url`, `funnel_token` in
`sync.html`; `backup_folder` in `_storage.html`. This is the measured price of a boundary
decided and not enforced.

**7 · The engine still tells the panel it ships inside the engine.**
`scrapex/version.py` `LATEST_SOURCE` — "the ScrapeX engine you are connected to — it
ships with the extension, and there is no remote update server" — travels on the wire and
is drawn by `extension/app.js:599` and `:633`. That is the phone model **stated
backwards**, and R-07 already ruled it must go. Still live at 7 sites.

**8 · A live 404 in the engine's own page, and the guard written to catch it cannot see
it.** `scrapex/webui/templates/settings.html:573` — `const probe = await
fetch("/api/marketlens/health", {cache: "no-store"});` — calls a route M5 removed
(`scrapex/webui/database_api.py:74`: "there were two files that could be"…).
`tests/test_the_panel_and_the_engine_agree_on_routes.py:107` asserts that route is absent
**from `app_js` only**, and `_panel_calls()` at `:38` walks `(ROOT / "extension")` and
never `scrapex/webui/templates/`. Found by the 2026-08-12 study, still live at `f1844af`.

---

## 7. What was LOST and what was recorded

**His memory is sound, and the prior study is not lost. Three of the four artefacts he
half-remembers are on main right now.** What is missing is narrower and more damaging
than a lost document.

**RECORDED, on main, at `f1844af`:**

- **The division of labour.** `docs/MIGRATION-PLAN.md:38-41`: "**The division of labour
  moved.** The engine keeps only *fetching* and *writing SQLite*; the display layer moves
  to the extension. Measured: **14,340 lines of interface** inside the engine — 5,642
  across 29 templates, 9,126 of web JS/CSS." **This is the paragraph he remembers.**
- **The tension he is now re-raising, named and accepted.**
  `docs/MIGRATION-PLAN.md:43-47`: "*'leave the engine only fetch + SQLite'* and *'remove
  the 127.0.0.1 service'* cannot both hold until the extension can read SQLite itself."
- **The keep/move table.** `docs/MIGRATION-PLAN.md:53-61` — five rows, verbatim: Console
  as an extension page; the workbook base; "Engine's face after the migration | **tray
  icon + a simple log window** (owner: \"2 و 3 معًا\")"; "Export stays in the engine";
  "Jobs stay in the engine | deferred by the owner".
- **His Arabic, on main.** `docs/plans/2026-08-22-the-source-page-moves-into-the-extension.md:48`
  — «**المحرك مهمته fetch**». **[CORRECTION APPLIED:** an earlier pass measured this as
  living only in an unmerged PR; `f1844af` (#261) merged it **today**.**]** That plan also
  carries, at `:47-70`, the dependency map naming exactly which two of its seven steps
  stop if the answer is "fetch only", and why.
- **The port-or-rebuild answer.** `docs/BACKLOG.md:2980` — "DEC-8 · The engine's Data page
  is a PORT, not a rebuild — measured 2026-08-16", answering his own question in his own
  words.
- **The request, tracked.** `docs/REQUESTS.md:186` REQ-07, state line: "Captured
  2026-08-12 · Planned · In flight — raised again 2026-08-22, and step 0 of the seven is
  built."
- **A prior study that already found the rail defect.**
  `docs/code-maps/2026-08-11-drive-bridge.md:372` — "Nothing disables the Data tab when
  the engine is absent… The comment… claims every page in that group 'is dead until an
  engine is installed', which is a statement of intent, not enforced code." Measured
  2026-08-11. **Twelve days old and rediscovered twice since.**

**LOST — five things, precisely:**

1. **The route map, and the `class A / B / C` taxonomy that orders the whole migration.**
   `docs/MIGRATION-PLAN.md:174` "**Order is by evidence, not by taste.** From the map:",
   `:178` "the **9 dead routes** (class C)", `:203` "`schedules` (routes already class
   A)". Grepping `docs/` and `*.md` for a definition of any of the three returns **only
   these uses**. And it was never in git: `git log --all --diff-filter=D --name-only --
   'docs/*.md' 'docs/**/*.md'` returns **zero** deleted markdown files (the only deleted
   `docs/` files are PNG screenshots). **The classification he remembers lived in the
   conversation. §2 of this document is its replacement.**
2. **The options behind «2 و 3 معًا».** `grep -rn "2 و 3"` over `docs/` and `*.md` returns
   `MIGRATION-PLAN.md:59` and nothing else. Five documents propagate the conclusion; none
   can say what option 1 was, or whether there was a 4. **Unrecoverable.**
3. **The reason two native commands re-crossed the boundary.**
   `git log -1 --format='%B' 04687f3` is one line — "Polish runtime settings and complete
   Sika unit capture" — with no body. The justification for `CHECK_STARTUP` and
   `UPGRADE_DATABASE` exists **only** as code comments at `scrapex/native.py:140-150`.
   That is the general rule the boundary needs, taken and never recorded.
4. **No ruling.** `docs/RULINGS.md` is 1,952 lines and its highest entry is **R-47** at
   `:1305`; `grep -c "R-48"` returns **0**. Grepping it for "topology", "TypeScript",
   "MV3", "OPFS", "wa-sqlite", "control room", "only interface", "division of labour",
   "fetch + SQLite" or "display layer" returns nothing. His 2026-07-18 Topology A
   decision (`docs/MASTER-PLAN.md:11` — "**The owner chose Topology A**… *'A, but leave
   the current engine running until the new engine is finished.'*") — the largest
   engine-shrinking decision on record — **is not in the register `CLAUDE.md` sends every
   session to read before designing.** The only boundary rule that made it in is SR-10,
   about settings. **This, not a lost document, is why an eleven-day-old measured decision
   produced zero deleted lines.** C3 was never discharged.
5. **Today's request is not yet captured.** `docs/REQUESTS.md` tops out at **REQ-39**;
   `grep -n "REQ-40"` returns nothing. Under **C7** his words of 2026-08-23 must be filed
   in the session he said them.

**And the measurement that makes the diagnosis unavoidable.** Between `aa03316` (the last
commit of 2026-08-12, the day `MIGRATION-PLAN.md` was written) and `f1844af` (today), I
counted every tracked file myself:

| | 2026-08-12 (`aa03316`) | 2026-08-23 (`f1844af`) | Δ |
|---|---|---|---|
| engine web UI (`scrapex/webui/**.html/.js/.css`, no vendor) | 17,755 (51 files) | 17,771 (51 files) | **+16** |
| — of which templates | 5,642 (29 files) | 5,642 (29 files) | **+0, and 29 files still 29** |
| extension (`.js/.css/.html`, no vendor, no tests) | 17,749 (25 files) | 25,058 (44 files) | **+7,309 (+41.2%)** |
| engine Python (`scrapex/**/*.py`) | 34,018 (81 files) | 44,172 (102 files) | **+10,154 (+29.8%)** |
| `scrapex/webui/app.py` | — | 3,611 | vs "running score — 3,347 today" at `MIGRATION-PLAN.md:254` → **+264** |

**[CORRECTION APPLIED:** an earlier pass reported +17 on the engine's web UI and offered
it as the deciding number. Measured: **+16** — and the framing was the larger error,
because it counted only the surface deliberately frozen pending B1. Over the same eleven
days the engine's Python grew **10,154 lines**, so the engine as a whole is the
**faster-growing** half, and #261 added 56 lines to `app.py` while deleting nothing.**]**
`docs/STATE.md:587` explains the +0 on templates: "**Not started:** **B1** (delete pure
duplication and the dead routes)". **The extension has grown beside the engine, not
instead of it.** Exactly one capability has ever left: `scrapex/gdrive.py`, 145 lines,
deleted in `8272bf3` with `−70` from `app.py`, `−214` from `sync.html`, `−118` test
lines, replaced by `extension/sheets.js`. **That commit is the only proof this system can
shrink, and the template for every row in §2B.**

---

## 8. The open questions only he can answer

**Not answered here.** Each carries the measured consequence of each answer.

**Q1 · Does "read my data without the engine" mean rows, or rows plus filter, sort and
export?**
- *Counts only (today's behaviour):* 0 further work; `extension/app.js:4471-4477` already
  does it; Decision 8's "and exports it" stays unmet.
- *Rows + CSV export:* two existing functions gain a caller —
  `extension/bundleview.js:82` `rowsOf` and `:94` `toCsv`, both already covered by
  `extension/tests/bundleview.test.mjs`. `extension/datatable.js` is 100 lines, pure, and
  would render a pack row exactly as happily as an `/api/table` row.
- *Full parity with the Data page:* `scrapex/webui/static/grid.js` is 3,212 lines, of
  which 0 are SQL and 14 are network; the payload contract is one shape.

**Q2 · Must the no-engine path work on a machine where no engine has ever run in this
account?**
- *Yes:* the pack cannot be the only road — it is written by
  `scrapex/bundle.py:163` (`_write_panel_pack`), i.e. by an engine, and the panel's path
  is gated on Google sign-in at `extension/app.js:4441`. Something else must produce it.
- *No ("have run once" is enough):* Decision 8's own scope at
  `docs/PLATFORM-PLAN.md:132` says "a fresh machine, signed in, with no engine
  installed", so this is already the written intent and the remaining work is Q1 plus Q3.

**Q3 · Do the 18,008 contractor records enter the no-engine path, and does the 40,000-row
history cap stay?**
- *Contractors in:* measured cost **8,346,948 bytes gzipped** on top of the current pack
  (contractors 3,318,183 + revisions 6,522,875, minus overlap). `scrapex/bundle.py` has
  **zero** references to `generic_record`; a generic read path exists in
  `scrapex/webui/app.py`, so this is a port of live queries, not new work.
- *Contractors out:* his newest and largest category stays invisible with no engine —
  and this is the same defect `CLAUDE.md` already names for `retention.py` and
  `compaction.py`, one file over.
- *Cap stays:* GPP_ENERGY loses **30,747 of 70,747** rows (43.5%) silently, every backup.
- *Cap goes:* the pack grows by roughly 3.3 MB gzipped at today's row counts.

**Q4 · Does an .xlsx export require an app to be installed?**
- *Yes:* `MIGRATION-PLAN.md:60` holds unchanged; `/export/{key}.xlsx` stays; a bare panel
  cannot produce a workbook, because `extension/bundleview.js:14-15` records that this
  repository "ships no npm dependency on purpose".
- *No:* CSV from `toCsv` is the bare-panel export, and `MIGRATION-PLAN.md:60` must be
  marked superseded under C4 (§6, contradiction 5).

**Q5 · Do steps 3 and 5 of the source-page plan proceed?** The plan on main states the
consequence itself at
`docs/plans/2026-08-22-the-source-page-moves-into-the-extension.md:55-70`: steps 1, 2
and 4 "are pure client ports and are safe under either answer"; step 3 needs "**a NEW
endpoint** reading `generic_record` + its revisions for one row" and step 5 is "**a
WRITE** that changes which fields are columns". "**If the answer is fetch-only, step 3's
endpoint has to live somewhere else, and that changes the shape of the record card rather
than merely delaying it.**"

**Q6 · Whose database is it when there are three apps?**
- *One shared warehouse:* contradicts `docs/PLATFORM-PLAN.md:26` (Decision 7, "Engine
  gets ONE database") and would need a `produced_by` column that **no table has today**
  (measured: `source_site`, `site_profile`, `dataset_definition`, `crawl_run`, `crawl_job`).
- *One per app, engine imports:* `docs/PLATFORM-PLAN.md:29` (Decision 10) already says
  this — and it makes ScrapeX-Engine a **required hub**, so it can never be "just another
  app". The import door is also closed: `scrapex/vocab.py:441-445` is a two-value enum
  under `extra="forbid"`.
- *One per app, the phone reads all of them:* needs the app registry and the data plane
  in §5, and nothing in the repository designs either.

**Q7 · Does a second app get its own native host name, and who allocates it?**
`scrapex/nativehost.py:17` is a bare module constant and `install-native-host` exposes
`--extension-id` and `--executable` only. *Answer "yes":* one manifest filename and one
registry key per app; the panel needs a list where `extension/engine.js:11` has a string.
*Answer "no":* installing app #2 **overwrites** app #1's manifest and registry key, and
the design's asymmetry (`MAX_ALLOWED_IDS = 5` extensions per app) is the exact inverse of
his model.

**Q8 · Does one stale app block the panel, or get quarantined?**
`extension/transport.js:25` and `scrapex/native.py:49` are one shared
`PROTOCOL_VERSION = 1`. *Per-app version:* the panel can refuse one app and keep the
others. *Shared:* one old app is a panel-wide refusal.

**Q9 · Do `validate-manifest`, `export-contract`, `export-version` and `funnel-test`
leave the shipped binary?** `packaging/engine_entry.py` derives the shipped command set
from the parser on purpose. *Stay:* release codegen that rewrites `CHANGELOG.md` ships to
users. *Go:* four of 25 subcommands leave the user-facing surface at zero functional cost
(`funnel-test` is byte-for-byte duplicated by `/api/outputs/apps-script/test`).

**Q10 · Do the four terminal-only capabilities get a panel surface, and in what order?**
`contractors` (5 verbs, the whole non-price category, 18,008 rows the phone cannot
produce), `merge-warehouse` (his two machines, and R-42/R-43 depend on it), `schedule`
(the only thing that fires his crawls while the engine is down — while its twin
`autostart` already has a switch), `carry-over`. Each has exactly one invocation path in
the package: `scrapex/cli.py`.

---

## 9. NOT MEASURED

- **The panel rendered with the engine actually stopped.** The engine was answering
  throughout (`/api/health` 200 in 654 ms, `version` `"0.3.1"`). Every engine-absent
  outcome above is traced through code and corroborated by the repository's own
  `engine_up=False` DOM tests. **Not observed.**
- **Whether a panel pack has ever reached his Google Drive.** I measured the **local**
  file. Reading Drive needs his OAuth token. `extension/drive.js:508-536` `fetchPanelPack`
  has no happy-path DOM test, and it checks byte length without checking the sha256.
- **Whether two native-messaging hosts can coexist on this machine.** Read-only: I did
  not write HKCU or a second manifest. That two *different* `HOST_NAME`s would get
  different keys is read off `scrapex/nativehost.py:151`, **inference, not execution**.
  What *is* measured is the collision under the **same** name: one filename, one `"path"`,
  one key.
- **Whether Chrome permits one extension to hold two native hosts.**
  `chrome.runtime.sendNativeMessage` takes the host name per call, so it is structurally
  fine; nothing in this repository tests it and I ran no browser.
- **Any browser-side SQLite figure at today's size.** Every OPFS number (1.4–2.0×,
  70–208×, 15,150 ms, 10.7–13.6 GB quota, `persist()` false) comes from
  `spikes/opfs-sqlite/FINDINGS.md`, measured 2026-07-30 against a **78,450,688-byte**
  database. The live warehouse is **1,203,191,808 bytes** — **15.3×** larger — on a
  different schema stream (56 tables, `user_version` 10, versus the spike's 40 tables and
  `user_version` 54). Treat those figures as a floor.
- **Whether a 1.2 GB `ArrayBuffer` can be allocated in a Chrome tab** (the gate on the
  `sql.js` variant). No `.wasm` and no SQLite build exists anywhere in `extension/`
  (`extension/vendor/` is exactly three Tabulator files, 475,586 bytes).
- **Whether OPFS eviction fires in practice.** `persist()` returning false is measured;
  nobody has provoked an eviction.
- **Read consistency under a concurrent writer.** The spike recorded that a reader can
  *open* the file while a writer holds it and never verified that the pages form a
  coherent snapshot. Neither did I.
- **Whether `POST /api/jobs` would accept a dataset source key.** `#258` replaced the
  blanket dataset-menu hide with a measured capability table, and `sourceActions()`
  filters `MANIFEST_ONLY` actions out for a dataset — so the panel does not offer
  "Update now" on the contractor card. Whether the **route** would accept it, I did not
  drive.
- **What `MIGRATION-PLAN.md:40`'s "9,126 of web JS/CSS" counted.** Its two components do
  not sum to its own total (5,642 + 9,126 = 14,768, not 14,340), and measuring
  `scrapex/webui` at that date's tree gives 12,113 lines of `.js`/`.css`. No scoping I
  tried reproduces 9,126. The templates half reproduces **exactly** (5,642 / 29 files),
  which is why the table in §7 uses the +16 / +0 deltas — method-independent — rather
  than a growth figure against 9,126.
- **What `export-contract` does inside a PyInstaller onefile build**, where `ROOT_DIR` is
  a temporary extraction directory. I did not run the frozen binary.
- **Effort estimates.** Every "cost" in this document is bytes, rows, lines or
  milliseconds I measured. No engineering-time estimate appears, because none is
  measurable from the repository.
- **Whether any of the six candidate engines would satisfy a need he has.**
  `docs/MASTER-PLAN.md` §8.3 calls them "candidates, not commitments"; no measurement of
  a second tool exists anywhere in the repository.

---

### Two live conditions found in passing, outside this study's scope

- `/api/health` reports `schema_lag.pending = ['0002_contract_meta.sql', '0003_jobs.sql']`
  — **two migrations on disk are not applied to the live database right now.**
- `docs/STORAGE.md:282-283` records, and I confirmed: **1,728 of 46,430**
  `generic_page_snapshot` rows are `html_codec='plain'` and hold **649,685,736 bytes —
  54.0% of the whole warehouse**; the other 44,715 rows carry `zstd-raw-dict` in
  260,417,017 bytes. "**Backfilling the 1,728 existing rows** would save ~600 MB and
  requires dropping an immutability trigger to do it. Not done, and not recommended
  without him saying so." **[CORRECTION APPLIED:** an earlier pass reported this 75.6% as
  "raw HTML with no retention at all"; `scrapex/snapshotbody.py`, migration
  `0005_a_snapshot_says_how_it_is_encoded.sql` and `docs/STORAGE.md` exist, 96.2% of the
  rows are already compressed, and `docs/RULINGS.md` R-25 records that **he deferred**
  the remaining question. It is an owner-deferred decision, not a hole.**]** It does not
  affect §1: the browsable rows are 16,151,610 bytes either way.
