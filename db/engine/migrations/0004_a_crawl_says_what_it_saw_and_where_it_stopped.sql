-- =====================================================================
-- 0004 — A CRAWL SAYS WHAT IT SAW, AND WHERE IT STOPPED
--
-- The owner asked about membership number 10001274. It is not in the
-- warehouse. The site answers 200 for it: شركة عبر المملكة سبك, active,
-- a member since 2018/08/25. Its neighbours bracket it exactly —
-- membership 10001271 is our contractor 1298, 10001276 is our 1303, and
-- the id in his URL is 1301. So the warehouse silently answered "does
-- not exist" about a real, active company, and could not say it was
-- guessing.
--
-- TWO THINGS WERE MISSING, AND THEY TURN OUT TO BE ONE THING.
--
-- (1) NOBODY RECORDS WHAT THE SITE SHOWED US. scrapex/sweep.py holds
--     every id it sees in `self._found` and offers it as `found` — and
--     tools/sweep_muqawil.py calls `record()`, prints `summary()`, and
--     never touches it. Six passes over 8h37m saw at least 17,283
--     contractors; the COUNT survived in a log file and the IDS were
--     discarded at process exit. So "fetch the ones we are missing" is
--     not a runnable instruction: we do not have the list, only its
--     length.
--
-- (2) AN INTERRUPTED CRAWL CANNOT RESUME. snapshotcrawl.py commits each
--     page as it arrives, deliberately — "a crawl interrupted at page
--     800 keeps 800 pages" — so the EVIDENCE survives. What does not
--     survive is the knowledge of which pages those were:
--     generic_page_snapshot has no run column, so a second attempt
--     re-fetches all 800. On a full pass that is hours of requests to
--     re-learn what is already on disk.
--
-- BOTH ARE THE SAME GAP: a crawl cannot say what it covered. One
-- migration, because one answer serves both.
--
-- WHY A SIGHTING IS NOT A RECORD, and why it needs its own table. A
-- `generic_record` is a contractor we PARSED AND STORED. A sighting is a
-- contractor the site SHOWED US — those differ by exactly the set this
-- entry is about. Keeping sightings in generic_record would mean rows
-- with no data, which every reader of that table would then have to
-- filter; and `status` cannot carry it, because a sighting has never
-- been ingested at all.
--
-- WHY seen_count IS KEPT. The 2026-08-17 pass produced 17,275 card slots
-- and 11,059 distinct contractors: 6,216 slots (35%) went to a
-- contractor already seen, and the appearance counts were 6,503 seen
-- once, 3,249 twice, 1,021 three times, 232 four, 41 five, 13 six. That
-- frequency distribution is a capture-recapture sample — it estimates
-- the population AND its confidence interval from data already on disk,
-- with no extra request. A count is one integer per row and it buys
-- that.
--
-- WHAT THIS DOES NOT DO. It does not decide how to crawl, and it takes
-- no position on partitioning, concurrency or retention. It records what
-- happened so those decisions can be made against measurements instead
-- of guesses.
--
-- AND IT IS IN THE ENGINE CHAIN, WHICH IS NOT WHERE I FIRST PUT IT. The
-- first draft went into db/migrations/ as 0062 and the table was never
-- created: EngineDatabase reads db/engine/migrations (domain.py:31),
-- db/migrations is the legacy PRICE chain, and db/engine/schema.sql
-- already carries the generic tables. The test failed with "no such
-- table" against a database that had applied every migration it knew
-- about — which is the only reason this was caught before it shipped.
-- =====================================================================

-- ---------------------------------------------------------------------
-- WHICH RUN FETCHED THIS PAGE
-- ---------------------------------------------------------------------
-- NULLABLE, and that is deliberate: 1,728 snapshots already exist and no
-- run can be attributed to them honestly. A backfill would be an
-- invention, and this column's whole purpose is to stop inventions.
-- NULL means "stored before crawls said who they were".
ALTER TABLE generic_page_snapshot ADD COLUMN crawl_run_ref TEXT;

-- The index a resume actually uses: given a run, has this URL been
-- stored yet? Run first because that is the equality, URL second.
CREATE INDEX IF NOT EXISTS idx_snapshot_run_url
    ON generic_page_snapshot(crawl_run_ref, source_url);

-- ---------------------------------------------------------------------
-- WHAT THE SITE SHOWED US
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dataset_sighting (
    dataset_sighting_id INTEGER PRIMARY KEY,
    -- The dataset this id belongs to, by KEY rather than by
    -- dataset_definition_id: a sighting can precede the dataset being
    -- defined, which is exactly the case on a first crawl of a new site.
    dataset_key   TEXT NOT NULL,
    -- The site's own identifier, as text. muqawil publishes two id
    -- series in one space — short (881, 5210) and long (20008518) — so a
    -- numeric column would be a claim about a shape the site has not
    -- promised.
    external_id   TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    -- How many times any pass has shown it to us. See the header: this
    -- is the capture-recapture sample, not bookkeeping.
    seen_count    INTEGER NOT NULL DEFAULT 1,
    -- The run that saw it FIRST. Nullable for the same reason above.
    first_run_ref TEXT,
    UNIQUE(dataset_key, external_id)
);

-- The question this table exists to answer — "which sightings have no
-- record" — is a left join on these two columns, so it gets the index.
CREATE INDEX IF NOT EXISTS idx_sighting_dataset
    ON dataset_sighting(dataset_key, external_id);

PRAGMA user_version = 4;
