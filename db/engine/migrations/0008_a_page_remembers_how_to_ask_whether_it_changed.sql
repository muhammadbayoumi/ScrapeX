-- =====================================================================
-- 0008 — A PAGE REMEMBERS HOW TO ASK WHETHER IT CHANGED
--
-- Item 2 of the owner's speed plan, after he asked whether a new user
-- waits the same hours every time: «هل سينتظر كل هذا الوقت ايضا ؟ ام
-- هناك استراتجية افضل؟».
--
-- The answer is that they should not, and the machinery for it has been
-- built the whole time and never connected. `HttpFetcher` keeps every
-- response's `ETag` and `Last-Modified`, sends `If-None-Match` on the next
-- visit, handles the 304, and counts it in `not_modified_count`. Its own
-- docstring promises "Every response's ETag / Last-Modified is kept and
-- replayed on the next crawl".
--
-- IT IS KEPT IN A DICT IN MEMORY AND DIES WITH THE PROCESS. Measured
-- 2026-08-21: `remember_validators` — *"Load validators kept from a
-- previous crawl"* — and `validators()` — *"The validators to keep for the
-- next crawl"* — have **ZERO callers anywhere in the repository**. Nothing
-- keeps them. So every re-crawl asks for full bodies for pages that had
-- not changed, and the promise in that docstring has never once been true
-- across two runs.
--
-- That is the same shape as this project's founding failure, recorded in
-- `CLAUDE.md`: `crawl_to_snapshots` was committed with no caller, so the
-- other machine could read how it worked and could not run it. A
-- capability with no caller is a claim.
--
-- ---------------------------------------------------------------------
-- WHY A TABLE AND NOT A COLUMN ON `generic_page_snapshot`
--
-- The snapshot table holds one row PER CAPTURE, and a validator is a fact
-- about a URL's LATEST state. Putting it on the snapshot would mean asking
-- for "the newest row for this url" on every lookup — a window function
-- over 9,600 rows to answer a dictionary lookup — and would leave stale
-- validators on every older row to be misread later. One row per URL says
-- what it means.
--
-- KEYED ON THE URL, which is already the identity the resume matches on:
-- `snapshotcrawl.already_stored` compares `generic_page_snapshot.source_url`
-- and `pagesource.Cell` orders its params precisely so two runs of one cell
-- produce the same string. The same reasoning applies here — a validator
-- filed under a differently-ordered query string is a validator that will
-- never be found.
--
-- BOTH COLUMNS NULLABLE, AND NEITHER IS REQUIRED. A site may send an ETag,
-- a Last-Modified, both, or neither; a row with neither would be pointless
-- rather than invalid, so nothing is stored for such a page. `HttpFetcher`
-- already treats a missing validator as "ask for the whole thing".
--
-- `seen_at` IS FOR PRUNING AND FOR READING, not for correctness. A
-- validator for a URL the site stopped serving is harmless — the
-- conditional request simply misses — but a warehouse that never forgets
-- one accumulates a row per URL ever visited. This makes that answerable.
-- =====================================================================

CREATE TABLE IF NOT EXISTS fetch_validator (
    url            TEXT PRIMARY KEY,
    etag           TEXT,
    last_modified  TEXT,
    seen_at        TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    -- A row that carries neither validator cannot answer the question it
    -- exists for. Refused rather than stored, so "has a validator" and
    -- "has a row" are the same question.
    CHECK (etag IS NOT NULL OR last_modified IS NOT NULL)
);

-- "Which validators are worth keeping" and "what has this warehouse
-- visited lately" are the same scan, and it has no other index.
CREATE INDEX IF NOT EXISTS ix_fetch_validator_seen
    ON fetch_validator(seen_at);
