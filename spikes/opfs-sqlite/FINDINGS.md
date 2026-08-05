# Spike 2 — wa-sqlite + OPFS in an MV3 extension

*Run 2026-07-30. Windows 11 (10.0.26200), Intel Core i7-13700 (16C/24T), 31.7 GB
RAM, SK hynix PC801 NVMe. Python 3.14.6 / SQLite 3.50.4. Chromium 1228 via
Playwright 1.61, headless, unpacked MV3 extension. `wa-sqlite` 1.0.0 (SQLite
3.44.0) and `@sqlite.org/sqlite-wasm` 3.53.0-build1. An ELBUROJ crawl was
running at ~1 req/s throughout, on the same machine — every Python number below
was measured against that background load, and it is the reason the Python
figures carry a range rather than a point.*

---

## Verdict

**Topology A is viable with four constraints, none of which the plan accounts
for: the warehouse loses WAL, only one context may hold it at a time, the engine
cannot live in the MV3 service worker, and the browser refuses to mark the
storage non-evictable — and `wa-sqlite`, the library the plan names, is the one
part that is simply the wrong choice.**

Capacity and speed both pass. The schema — all 40 tables, both append-only
triggers, both views, all 59 indexes — runs verbatim under WASM SQLite over OPFS
and survives a browser restart, which is precisely what `MASTER-PLAN.md:25-27`
asked this spike to find out. What it did **not** ask about is what breaks the
engine's design, and that is where the four constraints are.

| # | Question | Answer |
|---|---|---|
| 1 | Capacity | **Pass.** 74.8 MiB lands in OPFS in under a second, and is still there after a browser restart. |
| 2 | Speed | **Pass — with a different library.** A sync-access-handle OPFS VFS runs the real Data page within **1.4–2.0×** of Python. wa-sqlite's *importable* VFS is **70–208×** off, and its *fast* VFS cannot be handed the warehouse at all. |
| 3 | Concurrency & durability | **Fail as architected.** No WAL (no OPFS VFS implements `xShmMap`); one exclusive handle per file with no queue, against a crawler that runs 8 lanes on 8 connections; the service worker can read the warehouse but can **never write** it; `persist()` refused. |
| 4 | The resume journal | **Works, ~18× slower to write and ~22× slower to list** — and the failure that lost 3,570 pages this morning was a payload-version gate, which A would have hit identically. |

The one the brief expected to be fatal — MV3 killing a long crawl — was **not**
reproduced: a service worker doing 7 minutes of continuous OPFS writes with no
`chrome.*` calls survived on a single boot. The lifecycle is not the blocker.
The missing write primitive is.

---

## What was measured, and against what

Everything ran against a **copy of the live warehouse**, not a fixture.
`prepare.py` opens `~/.scrapex/marketlens/marketlens.db` with `?mode=ro` and
copies it with SQLite's backup API — never `shutil.copy`, because the live file
had **15,693,112 bytes of hot WAL** at the time and a file copy would have taken
a smaller, older database and flattered every number that followed.

| | Measured |
|---|---|
| `marketlens.db` | **78,450,688 bytes (74.8 MiB)** + 15.0 MiB WAL |
| `price_observation` | **73,278 rows** |
| All tables | 196,854 rows across **40 tables** |
| Schema objects | **59 indexes, 2 triggers, 2 views**, `user_version` 54 |

The brief said 72 MB and 73,162 observations; the crawl had appended 116 more by
the time this ran. The gap is the crawl, not a disagreement.

**The SQL is not re-typed.** `baseline.py` runs the real
`reports.table_payload` through a recording connection and dumps the statements
it actually issued, with their parameters, to `.work/trace-queries.json`; the
browser replays those strings. Same for the ingest: `ingest_payloads` is run
over a real ELBUROJ crawl's journal, and its 18,297 statements are captured and
replayed. So "the same query" is literally the same string, not a paraphrase.

---

## 1. Capacity — pass

| Measurement | Result |
|---|---|
| 74.8 MiB streamed into OPFS (sync access handle, chunked) | **205–447 ms** over eight imports across four runs |
| Two full copies resident (156.9 MB) | fine |
| `navigator.storage.estimate().quota` with `unlimitedStorage` | **13.3–13.6 GB** in the committed runs, and up to 16.0 GB earlier in the session — Chrome sizes it from free disk, so it is a share of the machine, not a fixed allowance |
| Written to one OPFS file before stopping | **6,144 MiB in 30.8 s, no error** — the probe's own ceiling, not the browser's. Reported quota fell to 9.3 GB while those 6 GiB were resident |
| Peak OPFS resident during the run | 239 MB (two warehouses + 3,570 journal files + a VFS pool) |

**Survives a browser restart: yes.** The browser was closed and relaunched on
the same profile directory. OPFS still held **239,217,546 bytes across 3,584
files** — `/marketlens.db` (78.5 MB), `/marketlens-wal.db` (78.5 MB), the
3,570-file journal (3.8 MB) and the SAH pool's twelve opaque files (78.5 MB) —
and wa-sqlite reopened the warehouse and counted its rows.

**`unlimitedStorage` is not what makes it fit.** With the permission the quota
was 13.3–13.6 GB; with the permission removed from the manifest it was
**10.7 GB**, and the 74.8 MiB warehouse still imported without complaint
(205 ms). The permission raises a ceiling that a 75 MB warehouse was never
close to.

**But the storage is evictable, and cannot be made otherwise.**
`navigator.storage.persist()` returns **`false`** for the extension origin, and
`navigator.storage.persisted()` reports `false` before and after — with and
without `unlimitedStorage`. Worse for A specifically: `StorageManager.persist()`
**does not exist in a worker at all** (`navigator.storage.persist is not a
function` in a `DedicatedWorker`), so the context where the engine and its OPFS
handles would actually live cannot even ask.

`MASTER-PLAN.md:70` names this risk as "OPFS is wiped by *clear browsing data*
with **no restore path**". The measurement says it is broader than a settings
click: the bucket is best-effort and eligible for eviction under storage
pressure, and the request to opt out is refused.

---

## 2. WAL is not available — the finding that shapes everything else

The live warehouse is a **WAL database** — `db.py:59` sets
`PRAGMA journal_mode = WAL` on every connection, and header bytes 18/19 of the
snapshot read `2, 2`.

**wa-sqlite cannot open it.** Handed the real file, it fails with
`unable to open database file` (`SQLITE_CANTOPEN`). Handed the *identical
bytes* with `journal_mode = delete`, it opens and reads everything. The cause is
not a bug: WAL needs SQLite's shared-memory hook, and **no wa-sqlite VFS
implements `xShmMap`** — not the OPFS ones, not even the base class.

**The SQLite project's own build hides the same fact.** Its OPFS SAH-pool
`importDb` accepts the WAL file and succeeds — because it rewrites the header:

```js
sah.write(new Uint8Array([1, 1]), { at: 18 });   // dist/index.mjs, importDbChunked
```

Bytes 18/19 are the write/read format version. `2,2` is WAL; `1,1` is rollback
journal. **The library silently downgrades the warehouse on the way in.** Both
engines report `journal_mode = delete` afterwards.

This is not a detail about a pragma. WAL is what lets the Data page read while a
crawl writes, and it is what lets eight lanes hold eight connections to one
file. Section 3 is what happens when it is gone.

### The schema itself survives intact

Under both engines, from the real 74.8 MiB file:

| | Python (source) | wa-sqlite | sqlite-wasm SAH pool |
|---|---|---|---|
| tables | 40 | 40 | 40 |
| indexes | 59 | 59 | 59 |
| triggers (incl. the append-only guards) | 2 | 2 | 2 |
| views | 2 | 2 | 2 |
| `user_version` | 54 | 54 | 54 |
| `price_observation` | 73,278 | 73,278 | 73,278 |

So the half of Spike 2 that `MASTER-PLAN.md:26` actually asks about — "`db/schema.sql`
verbatim (triggers + view) inside MV3" — **passes**. It is the surrounding
guarantees that do not.

---

## 3. Concurrency and durability — the reason A fails as architected

### OPFS sync access handles are exclusive, immediately and without a queue

| Attempt | Result |
|---|---|
| Second handle on the same file, same worker | **`NoModificationAllowedError`**, 0 ms |
| Second handle on the same file, a different worker | **`NoModificationAllowedError`**, 0 ms |
| Same request after the first handle is released | acquired in **9 ms** |

There is no lock wait, no `busy_timeout`, no retry-until-free. The second caller
gets an exception straight away.

There is one apparent exception, and it is worse than it looks: with the
dedicated worker still holding the handle, the **service worker opened the same
warehouse and read it** — because wa-sqlite's fallback read path takes no handle
at all (`getFile()` + `blob.slice()`, its own comment: *"Not using an access
handle is slower but allows multiple readers"*). That is not a concurrent reader
in the sense WAL provides one. It is an **unsynchronised** reader: there is no
shared memory, so there is no lock protocol between it and the writer, and
nothing measured here says the pages it reads are a consistent snapshot. What
was measured is that the open succeeded — not that the result would be correct
mid-write.

Against that, here is what the engine does today:

- `jobs.py:224` buckets sources into **per-host lanes**; `jobs.py:262-272` runs
  them concurrently on a `ThreadPoolExecutor`, up to `MAX_PARALLEL_SOURCES = 8`
  (`jobs.py:192`).
- `jobs.py:275-277` gives **each lane its own database connection** — the
  docstring says so outright: *"on a connection of this lane's own"*.
- Meanwhile the web UI opens **another** connection per request
  (`webui/app.py:360-361`), which is how the Data page renders while a crawl is
  writing.

Every one of those is a separate SQLite connection to one file, and every one of
them works because of WAL. Under OPFS, one context holds the file and everyone
else gets `NoModificationAllowedError`. Topology A does not get to port
`jobs.py`; it has to replace the concurrency model with a single owning writer
that every lane and every read is funnelled through.

### An MV3 service worker can read the warehouse but can never write it

This is the sharpest single result in the spike, and it is not the one the brief
expected. Probed in all three scopes of the same extension, in one run:

| | `createSyncAccessHandle` | `createWritable` | spawn a `Worker` |
|---|---|---|---|
| Window (extension page) | **undefined** | function | yes |
| **Dedicated worker** | **function** — acquired | function | yes |
| **MV3 service worker** | **undefined** | function | **no** — `Worker` is undefined |

`FileSystemFileHandle.createSyncAccessHandle()` is `[Exposed=DedicatedWorker]`,
and every OPFS SQLite VFS needs one to write. The service worker has neither the
method **nor the ability to spawn the one context that has it**. What that looks
like in practice, measured:

- Opening the warehouse **from the service worker: works.** 40 tables, 2 triggers,
  2 views, 59 indexes, `user_version` 54, 73,278 observations. wa-sqlite's OPFS
  VFS falls back to `getFile()` + `blob.slice()` for reads, which needs no handle.
- One `INSERT` into `scrapex_meta` from the service worker: **`unable to open
  database file`** — SQLite needs its rollback journal, and that needs a real
  write handle.

(`createWritable()` does exist in the service worker, but it is not a
substitute: it copies the file to a swap before each write, which for a 75 MB
warehouse is not a write path anyone would ship.)

So Topology A's engine **cannot live in the MV3 service worker**. It has to live
in an **offscreen document** that spawns a dedicated worker — a second lifetime
to create, keep alive and tear down, which `MASTER-PLAN.md` does not mention at
all. Dynamic `import()` is also disallowed there
(*"import() is disallowed on ServiceWorkerGlobalScope by the HTML
specification"*, w3c/ServiceWorker#1356), which is only a nuisance — static
imports work — but it is one more thing the port would meet on day one.

### The service worker's lifetime is **not** the problem

The brief expected aggressive termination to be the most likely reason A fails.
Measured, it is not.

A service worker doing **7 minutes of continuous OPFS writes with no `chrome.*`
call anywhere in the loop** — deliberately, because a crawl's inner loop is
fetch, parse, write, and extension API traffic is exactly what would reset the
idle timer and answer an easier question — survived the whole span:

| | |
|---|---|
| Requested | 420 s |
| Survived | **420 s** |
| Ticks completed | **414** |
| Service-worker boots during the run | **1** (`lives: 1`, `alive_ms: 421,815`) |

Past the 30-second idle timeout and past the old five-minute cap, on one boot.
An hour was not tested, so this does not prove an hour-long crawl survives — but
it does retire the idle-timeout story as the headline risk. **The blocker is the
missing write primitive, not the lifecycle.**

---

## 4. The resume journal

Today the journal is one JSON file per fetched page on the filesystem
(`localinbox.py:37` `write_payload`), and resume rebuilds its skip set by
**scanning filenames** (`localinbox.py:73` `list_tokens`) rather than parsing
them. Both halves were measured at the real scale — 3,570 pages:

Both sides write the same 1,069-byte page — the real journal's mean
(930,534 bytes over 871 files).

| | Filesystem (today) | OPFS (Topology A) | Best run vs best run |
|---|---|---|---|
| Write 3,570 payload files | **1,093–1,823 ms** (0.31–0.51 ms/page) | **20,054 ms** (5.62 ms/page) | **18×** |
| List 3,570 filenames (the resume skip set) | **16.4–27.2 ms** | **367 ms** | **22×** |

It works. It costs 20 seconds of a crawl's wall clock to journal what the
filesystem does in 1.1 seconds, and a third of a second of latency every time a
crawl resumes. Three filesystem runs are reported because it spreads under the
background crawl; the comparison uses its fastest, which is the least flattering
reading for the filesystem and the most generous to OPFS — and it is still 18×.

### Where it would live — and the failure it does not fix

In A the journal lives in OPFS beside the warehouse — a separate file per page,
so it does not contend with the warehouse's handle, and it survives a restart
(verified: all 3,570 files were still there after the browser was restarted).

**But the failure that lost 3,570 pages this morning is not a storage failure
and A does not fix it.** Those pages were rejected by a *version gate*:
`payload.py:54` declares `PAYLOAD_VERSION = 6` and `payload.py:101-106` refuses
anything else, while the pages on disk in
`~/.scrapex/journal-dropped-v5-ELBUROJ/` (871 files, 930,534 bytes, sampled for
this spike) carry `"payload_version": 5`. A journal in OPFS would have been
rejected by exactly the same check. **The lesson belongs to the payload
contract, not to the topology** — and it is worth saying plainly, because it is
the kind of loss that a topology decision can look like it is addressing while
leaving it entirely untouched.

---

## 5. Speed — a pass, and the reason `wa-sqlite` is the wrong library for it

wa-sqlite ships **two** OPFS VFSes, and Topology A has to pick one:

- **`OriginPrivateFileSystemVFS`** uses real OPFS paths, so an existing 74.8 MiB
  warehouse can be dropped in and opened. It is built on Asyncify, and when it
  holds no sync access handle it reads **every 4 KiB page** with
  `getFile()` + `blob.slice().arrayBuffer()` — its own comment says
  *"Not using an access handle is slower but allows multiple readers"*.
- **`AccessHandlePoolVFS`** uses sync access handles and no Asyncify, and is
  fast. But every database lives inside an opaque pool file behind a private
  4,096-byte header, and wa-sqlite ships **no import API**. The only supported
  way in is to let SQLite build the database itself.

### The `_LATEST_PER_OFFER` statement — the Data page's main query

min-of-7 repeats, except the last row (min-of-3: one repeat takes ~50 s). Python
is min-of-7 across three separate runs, and the "vs Python" column is measured
against **Python's best run of the three** — the least flattering reading for
the browser.

| Engine | Storage | GPP_ENERGY (695 rows out) | MADAR (3,425 rows out) | vs Python's best |
|---|---|---|---|---|
| **Python 3.14.6 / SQLite 3.50.4** | file, WAL | **81.2** ms (81.2–88.3 across runs) | **150.3** ms (150.3–266.4) | 1× |
| SQLite 3.53 WASM, OPFS SAH pool | OPFS, sync handles | 126.2 ms | 203.5 ms | **1.4–1.6×** |
| wa-sqlite 1.0.0 `AccessHandlePoolVFS` | OPFS, sync handles | 161.9 ms | 252.5 ms | **1.7–2.0×** |
| wa-sqlite 1.0.0 `OriginPrivateFileSystemVFS` | OPFS, no handle | **16,888 ms** | **10,541 ms** | **70–208×** |

Against Python's *slowest* run the two sync-handle engines beat parity on MADAR
(0.76× and 0.95×) — worth stating so the 1.4–2.0× above reads as a spread, not
a ceiling.

### The whole Data-page statement list, in the order `table_payload` issues it

| | GPP_ENERGY | MADAR |
|---|---|---|
| Python `table_payload` end to end (SQL **plus** payload building) | 265–304 ms | 386–708 ms |
| SAH pool, SQL only | 412–458 ms | 412–432 ms |
| wa-sqlite `AccessHandlePoolVFS`, SQL only | 590–774 ms | 610–691 ms |
| wa-sqlite `OriginPrivateFileSystemVFS`, SQL only | **47.4–54.6 s** | **38.1–39.0 s** |

The Python row is *not* like-for-like — it also builds the payload dicts, tax
states and grouping that the browser replay does not do. The statement table
above it is the apples-to-apples comparison; this one is here so the end-to-end
figure is not missing.

### Ingest — one real crawl, replayed as its 18,297 statements in one transaction

871 pages of a real ELBUROJ crawl, 10,455 of the statements being writes.

| | ms |
|---|---|
| Python `ingest_payloads` — the real code, not a replay | **158–337** |
| SAH pool (replay) | 478 |
| wa-sqlite `AccessHandlePoolVFS` (replay) | 488 |
| wa-sqlite `OriginPrivateFileSystemVFS` (replay) | 650–1,741 |

The replay is deliberately not idempotent — it replays literal `INSERT`s,
`source_site` among them — so each engine gets one run per database. A second
attempt fails with `UNIQUE constraint failed: source_site.source_key`, which is
the captured trace behaving correctly, not an engine fault.

### The migration wa-sqlite's fast VFS forces

Because `AccessHandlePoolVFS` cannot be handed a file, the warehouse has to be
rebuilt inside it. Measured: attach the plain-OPFS copy, create the schema,
copy every table, then build the indexes —

| Step | ms |
|---|---|
| DDL (40 tables) | 65 |
| Rows (**196,871** copied) | 14,332 |
| 49 indexes, triggers and views | 753 |
| **Total** | **15,150** |

Fifteen seconds, on every existing user's machine, the first time the extension
starts. And the rebuilt database came out with **`user_version = 0`** from a
source stamped **54** — a logical rebuild does not carry the schema stamp that
`db.py:64` `schema_version()` reads and every migration gate keys off. Any
migration into A has to restamp it explicitly or the engine will read a complete
warehouse as schema version 0.

**So performance is not the reason A fails.** A sync-access-handle OPFS VFS runs
the real Data page within **1.4–2.0×** of the shipping engine — close enough
that no user would notice. It is, however, exactly why `wa-sqlite` as named at
`MASTER-PLAN.md:26` and `:60` is the wrong pick: of its two OPFS VFSes, the one
that can be given the warehouse is **70–208× off**, and the one that performs
cannot be given the warehouse at all.

---

## The three questions

### 1. What does A buy that the current Python engine cannot do?

Concretely, one thing: **distribution.** "Add to Chrome" instead of a
PyInstaller `.exe` that trips SmartScreen and needs code-signing
(`MASTER-PLAN.md:177` budgets for exactly that pain). For a public,
non-technical audience that is a real advantage and it is not small.

Everything else on A's list is either already reachable or already built:

- **`activeTab` DOM capture of logged-in / JS-rendered pages** — named as A's
  unique edge (`MASTER-PLAN.md:32`). The shipping extension **already holds the
  `activeTab` permission** (`extension/manifest.json`), and nothing in
  `extension/*.js` uses it yet. It is a content script plus a POST to the local
  API — reachable today, in the current topology, without changing the engine's
  language. It is not a reason to move the warehouse into a browser.
- **The warehouse, the ingest, the read model** — 12 connectors
  (`scrapex/connectors/`, up from the "exactly one real connector" the plan
  records at `MASTER-PLAN.md:5`), 26,953 lines of engine, 26,828 lines of tests,
  **1,560 tests collected**, and **eight commits on 2026-07-30 alone** — four
  features and four fixes, spanning Zid images, the Heidelberg price matrix,
  MADAR units, crawl parallelism and the resume UI.

And A costs one thing the Python engine has that no browser can give back: a
warehouse in a **normal file the user can copy**, which is the whole of the
current backup story (`MASTER-PLAN.md:70`).

### 2. What does A cost — in months, and in what stops shipping?

The plan's Phase 1 is "port connectors + normalize + rowspec + ingest to TS"
(`MASTER-PLAN.md:28-30`). Measured, that is:

| Surface | Lines |
|---|---|
| `normalize` + `rowspec` + `payload` + `ingest` + `pricekey` + `pricehistory` + `vocab` + `contract` | **3,275** |
| `connectors/` (12 modules) | **5,699** |
| **Phase 1 total** | **8,974** |
| `reports.py` — the Data page's read model, needed for Phase 2's UX | **2,398** |

~9,000 lines re-implemented in TypeScript and held byte-identical to Python
under a shared conformance suite, plus ~2,400 more for the screen the user
actually looks at — and *then* the redesign section 3 forces: a single-writer
warehouse, a lane model that no longer holds eight connections, a UI that reads
through the writer instead of beside it, and an offscreen-document lifecycle.

I will not put a month number on someone else's velocity. What I can say from
the repo: `scrapex/` has taken **278 commits** to reach 26,953 lines with 1,560
tests, and the parity artefact that exists today —`contract/parity/` — is
**42 lines of JavaScript against 16 frozen vectors** (8 fold, 5 fingerprint,
3 record-hash). That is the honest scale of what has been proven portable so
far, against what would have to be.

What stops shipping: everything, unless the two lanes are staffed separately.
The plan's own instruction is *"the Python engine is NOT touched until the TS
engine is done"* (`MASTER-PLAN.md:15`), which means the TS lane is additive
work, not a migration — and the eight commits that landed today are the
opportunity cost of every week it takes.

### 3. What is the smallest step that keeps A possible without committing to it?

There is one, and it is cheap.

**Make the warehouse portable, and keep widening the frozen contract. Neither
requires a line of TypeScript.**

1. **A WAL-free, self-contained export.** The single hardest gate this spike
   found is that the live file cannot be opened by a browser at all. A
   `journal_mode = delete` copy costs **0.31–0.37 s** for the consistent
   backup-API snapshot of 74.8 MiB plus **30 ms** for the journal-mode flip
   (both measured in `prepare.py`), and it is the only artefact any future
   browser engine needs. It
   is also, independently, a better backup than the current story — a
   consistent, restore-able snapshot the owner can copy. Building it serves
   today's product whether or not A ever happens.
   **Caveat this spike found the hard way:** a logical rebuild loses
   `PRAGMA user_version` (the AccessHandlePool migration in §5 came out at
   `user_version = 0`, from a source stamped 54). Any export path has to carry
   the schema stamp explicitly or the engine will read the restored file as
   schema version 0.
2. **Grow `contract/normalize-vectors.v1.json`.** It is 16 vectors today. Every
   vector added is portability proven at the only place it matters — the
   fingerprint that decides whether two engines fork one warehouse's history —
   and every one of them is useful to the Python lane as a regression test on
   its own merits. This is Spike 1's *actual* surviving descendant doing the job
   `spikes/fingerprint-parity/` was recorded as having done.

Together those two keep the door open at near-zero cost, deliver value to the
shipping product on the day they land, and mean that a future decision to build
A starts from a portable warehouse and a proven contract instead of from a
plan.

What is **not** the smallest step: starting Phase 1. Section 3 shows the target
architecture is not the one being ported to, so ~9,000 lines would be
re-implemented against a concurrency model that has to change anyway.

---

## What this means for `docs/MASTER-PLAN.md`

Not mine to edit — leaving it alone, per the brief. For the record, what this
spike contradicts:

| Line | What it says | What was measured |
|---|---|---|
| `MASTER-PLAN.md:17-22` | Spike 1 **PASSED**, artefact `spikes/fingerprint-parity/` | `git log --all -- spikes` returns **0 commits**; the directory has never existed. The surviving artefact is `contract/parity/` — 42 lines, 16 vectors. |
| `MASTER-PLAN.md:25-27` | Spike 2 will show `db/schema.sql` runs "verbatim (triggers + view) inside MV3, surviving restart" and then "A is fully de-risked" | The schema **does** run and **does** survive restart, so this clause holds. The conclusion drawn from it does not: WAL, single-holder access, persistence and the fact that the service worker cannot write are all unresolved, and none of them is a schema question. (The service-worker *lifetime*, which the plan does not mention either, turned out to be fine.) |
| `MASTER-PLAN.md:5` | "exactly one real connector (Shopify)" | **12 connector modules**, 11 manifest sources. |
| `MASTER-PLAN.md:60` | A runs "over a WASM SQLite (wa-sqlite/OPFS) warehouse" | wa-sqlite's importable OPFS VFS is 70–208× slower than Python on the real query; its fast VFS cannot be handed an existing database at all, and rebuilding into it takes 15.2 s and loses `user_version`. |
| `MASTER-PLAN.md:267` §8 Q1 | asks the owner to "Confirm Topology B" | already answered A in its own header at line 9. `BACKLOG.md` DEC-1 flags this; unchanged. |

---

## What this spike did **not** test

Stated so the next reader does not over-read it:

- **No TypeScript engine.** The browser replays Python's SQL; it does not
  re-implement `ingest.py`. So these are measurements of *SQLite over OPFS*, not
  of a ported engine. The ingest figure is the storage cost of one crawl's
  writes, not the cost of computing them.
- **No network.** No crawl was started and no connector ran in the browser. The
  running ELBUROJ crawl was left alone throughout.
- **One machine, one browser.** Chromium 1228 headless on one Windows box.
  Firefox and Safari have their own OPFS and extension stories and were not
  touched.
- **Eviction was not provoked.** `persist()` was refused, which is the fact;
  actually filling the disk to watch the bucket be evicted was out of scope.
- **An hour-long crawl was not run.** The service worker was held for 7 minutes
  of continuous work, which clears the 30-second idle timeout and the old
  five-minute cap. It does not prove an hour.
- **Read consistency under a concurrent writer was not verified.** §3 records
  that a handle-less reader can open the file while a writer holds it; whether
  what it reads is a coherent snapshot was not tested, and there is no shared
  memory for SQLite to coordinate through.
- **`contract/parity`'s vectors were not extended**, and no claim is made here
  about cross-language fingerprint parity beyond what those 16 vectors already
  cover.

---

## Re-running it

See [README.md](README.md). Every number above comes from `results/*.json` and
`.work/baseline-*.json`, all regenerated by the commands there;
`python collect_evidence.py` copies the run this document quotes into
[`evidence/`](evidence/), which is committed so the numbers survive the next
re-run.
