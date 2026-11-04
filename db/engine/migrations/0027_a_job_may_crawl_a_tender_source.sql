-- A sixth job kind: crawling a tender source, `tender_crawl`.
--
-- PART 3B-2A OF MILESTONE 51, HIS WORD OF 2026-10-24 (#1733). The World Bank collector
-- (`scrapex/sites/worldbank_collect.py`, #1765) gets the job that runs it:
-- `scrapex/tenderjob.py`, registered in `jobs.SPECIALISED_RUNNERS`. No route creates one
-- yet, and no control draws one: part 3b-2b adds both in one change.
--
-- WHY A REBUILD FOR ONE STRING, and it is the reason `0017`, `0018`, `0019` and `0023`
-- gave: SQLite accepts a CHECK and then offers no way to alter it. Without this, a
-- `tender_crawl` job is refused with `CHECK constraint failed` the moment it is written.
-- `tests/test_the_button_drives_the_collector_the_source_needs.py` writes every kind in
-- `jobs.JOB_KINDS` through this CHECK, so the registry cannot name a kind the warehouse
-- refuses without a test saying so.
--
-- THE DIRECTION IS THE SAFE ONE. This only WIDENS a CHECK, so no row that satisfied the
-- old constraint can fail the new one, and every other column is copied exactly as `0023`
-- declared it: same types, same NOT NULLs, same defaults.
--
-- `legacy_alter_table = ON` IS REQUIRED, NOT DEFENSIVE. Five tables carry
-- `REFERENCES crawl_job` at schema 26, measured on a warehouse this stream built:
-- `change_event`, `crawl_run`, `job_log_entry`, `organization_enrichment_job`, and since
-- `0025` `fetched_responses`. Without the pragma the RENAME rewrites their REFERENCES
-- clauses to point at `crawl_job_old`, which is then dropped.
--
-- NO TRIGGER IS ON `crawl_job` at schema 26 (`sqlite_master` WHERE `tbl_name =
-- 'crawl_job'`: the table, its UNIQUE autoindex and `ix_crawl_job_status`). The UNIQUE
-- autoindex comes back with the table; `ix_crawl_job_status` does not, and is recreated
-- below, because it is what `/api/jobs` orders by.

PRAGMA user_version = 27;
PRAGMA legacy_alter_table = ON;

CREATE TABLE crawl_job_rebuilt (
    job_id             INTEGER PRIMARY KEY,
    job_ref            TEXT NOT NULL UNIQUE,
    run_mode           TEXT NOT NULL
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild',
                            'history_backfill')),
    status             TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                           'scheduled','queued','preparing','running','pausing','paused',
                           'resuming','cancelling','cancelled','completed',
                           'completed_with_errors',
                           'partially_completed','failed','requires_review',
                           'skipped')),
    control            TEXT NOT NULL DEFAULT 'none'
        CHECK (control IN ('none','pause','resume','cancel')),
    source_keys        TEXT NOT NULL,
    current_source_key TEXT,
    stage              TEXT,
    progress_done      INTEGER NOT NULL DEFAULT 0,
    progress_total     INTEGER NOT NULL DEFAULT 0,
    counters_json      TEXT,
    checkpoint_json    TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at         TEXT,
    finished_at        TEXT,
    last_heartbeat_at  TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    output_status      TEXT,
    error_summary      TEXT,
    job_kind           TEXT NOT NULL DEFAULT 'crawl'
        CHECK (job_kind IN ('crawl', 'organization_enrichment', 'directory_crawl',
                            'dataset_interpret', 'profile_crawl', 'tender_crawl'))
);

-- EVERY COLUMN NAMED ON BOTH SIDES, in the table's own order, so a column added to one
-- and forgotten in the other is a SQL error here rather than a silent NULL later.
INSERT INTO crawl_job_rebuilt (
    job_id, job_ref, run_mode, status, control, source_keys, current_source_key,
    stage, progress_done, progress_total, counters_json, checkpoint_json, created_at,
    started_at, finished_at, last_heartbeat_at, retry_count, output_status,
    error_summary, job_kind)
SELECT
    job_id, job_ref, run_mode, status, control, source_keys, current_source_key,
    stage, progress_done, progress_total, counters_json, checkpoint_json, created_at,
    started_at, finished_at, last_heartbeat_at, retry_count, output_status,
    error_summary, job_kind
FROM crawl_job;

ALTER TABLE crawl_job RENAME TO crawl_job_old;
ALTER TABLE crawl_job_rebuilt RENAME TO crawl_job;
DROP TABLE crawl_job_old;

CREATE INDEX ix_crawl_job_status ON crawl_job(status, created_at DESC);

PRAGMA legacy_alter_table = OFF;
