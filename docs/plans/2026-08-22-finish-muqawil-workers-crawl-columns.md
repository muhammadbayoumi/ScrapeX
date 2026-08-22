# Finish muqawil: workers, the profile crawl, and the 48 columns

**LIVE. Written 2026-08-22, approved the same day. Step 1 is DONE (#249).**

Moved out of `~/.claude/plans/` per
[R-08](../RULINGS.md#r-08--the-plan-and-the-state-live-in-the-repository), which
exists because seven plans were once invisible on his second machine — one of them
the plan for a pull request that was open at that moment. This session proved the
rule again: it began on the machine that did **not** have the warehouse.

**Status of the four steps:**

| step | state |
|---|---|
| 1 · workers for `--details` | **DONE** — #249. 87 h → 11–14 h, and it found a real dictionary race |
| 2 · the profile crawl, 34,834 pages | **ready to run**, ~14 h of machine time, resumable |
| 3 · the profile parser | **the cards are done 2026-08-22** — six new columns and a second taxonomy group, on a census of 2,419 real pairs rather than two fixtures. What is left is `Q-17` and `Q-18`, both his |
| 4 · `R-19`'s remaining four groups | **his ruling**; three of four measure as "do not build" |

## Context

The profile crawl is the last big piece of «كلّ ما ينشره الموقع». Measured: the
Dammam run went at **9.03 s a page single-threaded**, so all 34,834 pages is
**87 hours**. The listing crawl measured **1.14 s a page with six workers**. The
same work is already done, correctly, one module away.

`R-39` recorded **11.1 h** and that figure was **wrong** — measured with six workers
and applied to a single-threaded command. **Amended 2026-08-22** with the original kept
per `C4`: a rate measured on one command is not a rate.

## What makes this a port, not a design

`scrapex/partitioncrawl.py` already solved every hard part, and its reasoning is
measured rather than assumed:

- **`workers: int = 1`** with a `connect` callable — `partitioncrawl.py:945,965-968`.
  Each worker gets its own `sqlite3` connection because one is refused across
  threads; a single shared connection behind a lock would serialise the reads
  between fetches too.
- **The rate does not rise.** `HttpFetcher._throttle` holds a lock across its
  sleep. Without it, *measured 2026-08-21*, four workers made 20 requests in
  1.02 s where 3.80 s was owed (`partitioncrawl.py:969-976`). The concurrency buys
  **overlap on a ~9 s latency, never a higher request rate** — which is what keeps
  it inside `R-21` and `SR-8`.
- **WAL + `busy_timeout=5000`** on every connection, so concurrent writers wait
  instead of failing (`partitioncrawl.py:1064-1075`).
- **Deterministic reports** — results ordered by the plan, not by which worker
  finished (`partitioncrawl.py:1087-1089`).

So the arithmetic is a floor set by the pace, not the latency: 34,834 × ~1.4 s
≈ **14 hours**.

## The change

**One function.** `scrapex/contractors.py:522-544` is the single-threaded loop:
`for number, url in enumerate(todo)` → `fetch(url)` → `save_snapshot` → `commit`.

1. Add `workers: int = 1` and a `connect` callable to the `--details` path, mirroring
   `partitioncrawl.crawl_partition`'s signature so the two read alike.
2. Submit `todo` to a `ThreadPoolExecutor(max_workers=workers,
   thread_name_prefix="detail")`. Each worker: its own connection, its own
   `save_snapshot`, its own `commit`.
3. Keep the existing per-URL failure isolation exactly as it is — one dead profile
   out of 34,834 must not discard the rest (`contractors.py:526-531`).
4. Progress and totals: accumulate per worker, report ordered by `todo` index, so
   two runs of the same frontier print the same thing.
5. `declare_frontier(fetcher, len(todo))` stays where it is — the frontier is
   declared once, before any worker starts.
6. Add `--workers` to the CLI beside `--ceiling`, default **1**, so nothing changes
   for a caller who does not ask.

## Then, in order

- **The profile crawl itself** — 34,834 pages, both locales, `body_class` set so the
  bodies compress (`~87 MB` instead of 3.95 GB). Resumable already: `already_stored`
  + `--run-ref`.
- **The profile parser** — ~~48 of ~70 of his columns have no extractor~~ **DONE for
  the cards, 2026-08-22.** The info-box half was already built and measured clean
  (11 labels, all known, on 2,252 pairs); what had no reader was three of the page's
  **seven** cards. Six columns added — `commercial_registration`, three self-build
  price tiers, two contract counts — and `licensed_activities` wired as a second
  taxonomy, in its own scheme.

  **The correction this step was told to carry was itself wrong.**
  `contract_request_url` is not absent from the card: the card is on **100%** of pages,
  and its form action is one **site-wide constant**, so it earns no column — while the
  form's pre-filled `cr` input is the **Commercial Registration number**, on 2,542 of
  2,543 pages, ten digits, no two contractors sharing one. Kept visible per **C4**: the
  premise was recorded honestly off two fixtures and 2,419 pages overturned it.

  Three more premises fell with it — see `OP-43` and [LESSONS.md](../LESSONS.md) §11 —
  including a **price** that no document in this repository had named.
- **`R-19`'s remaining four groups** — only `interests` is wired;
  `contractors.write_groups` records why for each of the others.

## Verification

- `python -m pytest tests/test_a_crawl_that_stores_evidence.py -q` and the
  contractors suite green before and after.
- A new guard proving **the rate does not rise with workers**: N workers over M
  URLs against a fake fetcher must take at least `M × min_interval`. This is the
  assertion that stops a future refactor turning politeness into a 6× request rate,
  and it is the one `partitioncrawl` learned by measurement.
- A guard that the report is identical at `workers=1` and `workers=6`.
- Mutation: remove the per-worker connection and the suite must fail on the
  cross-thread refusal, not pass by luck.
- `SCRAPEX_FULL_MIGRATIONS=1 python -m pytest -q` in full before the PR (`R-22`).
- Then correct `R-39`'s 11.1 h in `docs/RULINGS.md`, marked superseded per `C4`,
  never erased.

## Files

`scrapex/contractors.py` (the loop and the CLI flag) · `tests/` (three new guards) ·
`docs/RULINGS.md` (`R-39`'s figure) · `docs/STATE.md`.

---

# Appendix — the sync audit of 2026-08-22, DEFERRED by his ruling

The full audit was delivered. **His decisions, recorded verbatim so they are not
re-litigated:**

1. **No server for now** — «لن ابنى خادم الان (لا اعرف وجه الاستفادة اصلا منه)».
2. **No encryption for now** — «الداتا لن تنتقل من المستخدم الى اى حد اخر … لا داعى
   للتشفير ربما خطة مستقبلية». The one fact that stands: a compromised Drive account
   today means the whole warehouse is readable.
3. **Solo now, public later** — and he believes each account already has its own
   databases and backups.
4. **Defer all of it** — «أرجئ كلّ شىء — أكمل مقاول».

**Two audit findings that are true regardless and will cost more the longer they
wait:**

- **`REQ-26` is not built, and he thinks it is.** `extension/accounts.js:1-14`
  remembers several accounts but writes nothing to disk;
  `databases/registry.py:23-33` has one `DATABASE_ROOT`; `account.py:10-14` says it
  does not use per-account directories and does not refuse another owner's
  warehouse. **Two accounts on one machine open the same file today.**
- **48 of 48 primary keys are autoincrement integers.** A tool published to other
  people with integer keys can never sync, and adding `row_uuid` after users hold
  data is a painful migration. Today it is an `ALTER TABLE`.

**And one design answer he asked for, recorded for when he returns:** automatic
sync *is* achievable with no server, using Drive as an append-only log of small
immutable per-device files (never the SQLite file itself — WAL plus partial sync
corrupts it). The price is that **Hybrid Logical Clocks become necessary**, where a
server would have made them pointless, and that **nothing can reject an
operation** — so the tables the audit marked "reject and surface" (retention
policy, `tax_rule`) need automatic rules instead. For a published tool,
Drive-per-user also solves isolation for free.

---
