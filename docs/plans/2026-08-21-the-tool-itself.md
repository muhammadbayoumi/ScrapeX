# The tool itself — everything that is not one source

**LIVE. Opened 2026-08-21 on his instruction.**

> «ام اى تعديلات عامه مثل توحيد نقطة الاتصال وادارة الطلبات ضعها فى خطة عامة للاداة
> ككل · واريد الانتهاء من كل المكاسب السريعة وخطة مقاول فى المقام الاول»

**This file exists so tool-wide work stops competing with muqawil for attention.**
Anything specific to one source belongs to that source's plan; anything that would be
true no matter which site we crawled belongs here. His priority is explicit: **the
quick wins and the muqawil plan come first**, and nothing in this file starts before
they are done unless it is blocking them.

**The muqawil checklist is
[on the registers](README.md#historical), that plan having been folded 2026-08-27.**

Tick a box only when it is MERGED. `⚡` marks a quick win. `🚫` marks a release blocker.

---

## A · What he asked for and has not been built

- [ ] 🚫 **`REQ-20` · the database rename must reach every user.** `carry_over` has one
      caller: the manual `scrapex carry-over`. A user starting the engine from the panel
      gets `ok: false`, `action: "check_storage"` — a dead engine — and the panel's own
      repair button **cannot fix this transition at all**. Under
      [R-24](../archive/RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
      that is a release blocker. **The missing piece is a test that a split
      installation STARTS**; every carry-over test calls the function directly, which is
      exactly why a manual-only remedy looked finished. [OP-24](../archive/BACKLOG.md).
- [ ] **`R-21` · one source owns every outbound request** — «مصدر واحد يدير اى استعلام
      او اتصال بالانترنت»، adapting to what each site tolerates AND what the local
      connection carries. **The ruling says half of it is built and none of it is
      used.** This is his "unified connection point".
      *Note from 2026-08-21:* `partitioncrawl` deliberately paces in ONE layer
      (`HttpFetcher.min_interval_s`) and passes `pace_s=0` to the walker — so there are
      now two pacing mechanisms in the tree, and R-21 is where they get reconciled.
- [ ] **`REQ-04` · every setting moves into the extension.** Ruled 2026-08-01
      ([R-04](../archive/RULINGS.md), `SR-10`), he chose the most thorough option, and nothing
      has been built. **The entry that justifies the whole request board.**
- [ ] **`REQ-07` · the Data page carries everything the engine's page carries.**
      Planned. Track 1's B2 is the work.
- [ ] **`REQ-11` · branch protection for `main`.** The API answers 404 — there is none,
      so [R-18](../archive/RULINGS.md#r-18--merge-it-when-it-is-green) is the entire gate,
      enforced by discipline. He deferred it to its own session. **The trap that stopped
      it:** `test` and `migration-authority` are gated on `needs: scope`, a docs-only
      change makes them `SKIPPED`, and a required check that is skipped can leave a pull
      request unmergeable for ever.
- [ ] **`REQ-12` · justify the volume, not compress it.** The study is done
      ([STORAGE.md](../STORAGE.md)); the ruling is his. Tonight's real-crawl measurement
      revised its headline: **47× not 187×**.

## B · Quick wins

- [ ] ⚡ **Make `migration-authority` a required check.** It was split out of `test` for
      speed and **is not required**, so a migration-stream failure will not block a
      merge — weaker than the inline variable it replaced. Blocked on REQ-11's trap.
- [ ] ⚡ **`register_site`'s conflict message should print BOTH values.** It names only
      the existing one, so a trailing-slash difference prints two strings that look
      identical. That cost a real diagnosis on 2026-08-21 —
      `scrapex/catalog.py:129`.
- [ ] ⚡ **`OP-21` · `snapshotcrawl`'s resume saves the write and none of the requests.**
      The skip is checked inside `store`, which the walker calls *after* fetching, so a
      resumed crawl re-fetches every page and then declines to store it — measured. Its
      docstring promises the hours. `partitioncrawl` works around it locally with
      `_Unstored`; the fix belongs in the walk.

## C · Known broken, with the measurement

- [ ] **`OP-17` · `carry_over` cannot merge a table present in BOTH old databases.**
      Both number rows from 1, so any shared table collides and `INSERT OR IGNORE` drops
      the second file's rows silently. It did not bite this installation because
      `general.db` held **zero data rows** — measured 2026-08-21, only its own ledger.
- [ ] **`OP-19` · the chaos test races the startup sweep.** Re-measured under load
      2026-08-21: **3 of 3 failures on unmodified `main`**. The defect is not the flake —
      it is that `_source_is_busy` reads a status a crashed run leaves as `running`, so a
      real crash blocks a source from every future crawl with nothing saying why.
      **A crawl in progress reproduces it reliably**, which is worth more to whoever
      fixes it than another quiet run.
- [ ] **`OP-4` · `webui/app.py` is 3,347 lines and 95 routes**, and the extraction it
      started stopped.
- [ ] **`OP-2` · three different answers to "which sources are active".**
- [ ] **`OP-7` · `/api/native-host/register` takes no authentication and REPLACES the
      allowlist** rather than joining it.

## D · The tracks already open

- [ ] **Track 1 · the Console migration.** B2's remaining four endpoints, then B1, B3–B6.
      `O-5` is explicitly held by him — do not start saved views.
- [ ] **Track 3 · the version debt.** `VERSION` is `0.2.2` and last moved 2026-08-10;
      [R-06](../archive/RULINGS.md#r-06--version-moves-with-every-merged-pull-request) says it
      moves with every merged pull request. Blocked by
      [R-07](../archive/RULINGS.md#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert).
      **The count grows every time this is deferred** — it was 48, then 58, then 62.
- [ ] **Phase C** · `127.0.0.1` cannot go until the extension can read SQLite itself
      (**DEC-1**, wa-sqlite + OPFS), and jobs cannot move while the heartbeat is broken
      under load (**T2**).

## E · Generic-source machinery that muqawil exposed but is not muqawil's

- [ ] **The job runner cannot crawl a generic source at all.** `scrapex/jobs.py` has no
      reference to `generic_record`, `partitioncrawl` or `snapshotcrawl`, so every
      generic dataset is terminal-only. This will be true of Balady, the UAE sources and
      every source in the queue — which is why it is here and not in muqawil's plan.
      [OP-26](../archive/BACKLOG.md) item 3.
- [ ] **`DEC-10` · a row-aware idempotency key**, so "fix the parser and re-run over the
      stored snapshots" actually works. Today `approve_candidate` short-circuits on
      `(snapshot, locator)` plus `schema_hash` and returns `recovered=True` while writing
      nothing. Every future source inherits this.
- [ ] **Schema drift has a data model and no code.** `dataset_schema_version` carries
      `version_number` and `valid_to`; `approve_candidate` never writes a second version.
      It is [OP-25](../archive/BACKLOG.md)'s route (c) and it would answer DEC-10 too.
- [ ] **`DEC-12` · the append gate's key is not the number.** Three of his price briefs
      prove it separately — diesel says the **period**, bitumen the **commercial basis**,
      concrete the **source type**. Not needed for muqawil; needed before the first price
      collection, because a dropped period is not a wrong row a later fix corrects — it
      is a row that never existed, in a table whose whole purpose is history.

---

## How this file is used

It is a **register, not an order**. The order is his, and today it is: quick wins,
then muqawil, then this. When something here becomes blocking for muqawil it moves up
by itself — `R-20` did exactly that, which is why it sits in muqawil's checklist and
not in this one.
