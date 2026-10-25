-- A job may end `stopped_by_site`: every source that did not finish was stopped by its site.
--
-- HIS RULING (a) ON #1772, 2026-10-24. A site that keeps refusing stops its source, and the
-- source keeps its fetched pages and continues from them on its next run (#1448, #1449). A
-- job whose sources were ALL stopped that way used to end `failed`, because nothing in it
-- succeeded (`scrapex/jobs.py`, `succeeded == 0`) -- and #1448 ruled that a site's block is
-- not a failure. He chose a status of its own over `partially_completed`, which would say a
-- part completed when no row was written. It is finished, not held: a held (`paused`) job
-- makes that site's next scheduled run skip (`scheduler.py`, D3 on #1596).
--
-- WHY A REBUILD FOR ONE STRING, the reason `0023` gave: SQLite accepts a CHECK and then
-- offers no way to alter it. Measured on his warehouse 2026-10-24: `crawl_job` holds 213
-- rows, so the copy below is instant.
--
-- THE DIRECTION IS THE SAFE ONE. This only WIDENS a CHECK, so no row that satisfied the
-- old constraint can fail the new one, and every other column is copied exactly as `0023`
-- declared it: same types, same NOT NULLs, same defaults, the same `job_kind` list. No
-- migration since `0023` changed `crawl_job` (`0025` only references it).
--
-- `legacy_alter_table = ON` IS REQUIRED, NOT DEFENSIVE, for `0023`'s reason: four tables
-- carry `REFERENCES crawl_job`, and without the pragma the RENAME rewrites their REFERENCES
-- clauses to point at `crawl_job_old`, which is then dropped. `0025` added a fifth,
-- `fetched_responses.crawl_job_id`, and the pragma covers it the same way.
--
-- NO TRIGGER IS ON `crawl_job` (`0023` measured it). The UNIQUE autoindex comes back with
-- the table; `ix_crawl_job_status` does not, and is recreated below.

PRAGMA user_version = 27;
PRAGMA legacy_alter_table = ON;

CREATE TABLE crawl_job_rebuilt (
    job_id             INTEGER PRIMARY KEY,
    job_ref            TEXT NOT NULL UNIQUE,
    run_mode           TEXT NOT NULL
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild',
                            'history_backfill')),
    -- THE ONE CHANGE: `stopped_by_site`, which is `scrapex.vocab.JobStatus.STOPPED_BY_SITE`.
    -- `tests/test_schema.py` writes every `JobStatus` member through this CHECK, so the
    -- enum cannot name a status the warehouse refuses without a test saying so.
    status             TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                           'scheduled','queued','preparing','running','pausing','paused',
                           'resuming','cancelling','cancelled','completed',
                           'completed_with_errors',
                           'partially_completed','failed','requires_review',
                           'skipped','stopped_by_site')),
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
                            'dataset_interpret', 'profile_crawl'))
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
