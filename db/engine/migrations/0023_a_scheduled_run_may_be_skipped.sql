-- A job may end `skipped`: a scheduled firing that did not run, and says why.
--
-- HIS RULING D4 ON #1596, 2026-10-09. A schedule that comes due while its source is
-- already running (one he started by hand, or one paused and waiting for him), or while
-- another app holds the warehouse write lock, is skipped. It leaves a visible job row
-- whose `error_summary` says why ("a run is in progress"), and it fires again at its next
-- slot; it never waits in a queue. He chose a status of its own over reusing `cancelled`,
-- because a cancel is something he did and a skip is something the schedule did.
--
-- NOTHING WRITES IT YET. This is step 1 of 5 on #1596: the status, the engine knowing it
-- is terminal and not blocking, and the panel drawing it. The scheduler starts writing it
-- in the next step. The vocabulary lands first so that no engine ever writes a status its
-- own warehouse refuses.
--
-- WHY A REBUILD FOR ONE STRING, and it is the reason `0017`, `0018` and `0019` gave:
-- SQLite accepts a CHECK and then offers no way to alter it. Without this, the scheduler
-- writes `skipped` and SQLite answers `CHECK constraint failed`.
--
-- THE DIRECTION IS THE SAFE ONE. This only WIDENS a CHECK, so no row that satisfied the
-- old constraint can fail the new one, and every other column is copied exactly as `0019`
-- declared it: same types, same NOT NULLs, same defaults. `0014` is the counter-example
-- this folder remembers -- a DEFAULT never applies to a column an INSERT names.
--
-- `legacy_alter_table = ON` IS REQUIRED, NOT DEFENSIVE. Four tables carry
-- `REFERENCES crawl_job`: `change_event`, `crawl_run`, `job_log_entry` and
-- `organization_enrichment_job`. Without the pragma the RENAME rewrites their REFERENCES
-- clauses to point at `crawl_job_old`, which is then dropped.
--
-- NO TRIGGER IS ON `crawl_job`, measured on a warehouse built by this stream at v22
-- (`sqlite_master` WHERE `tbl_name = 'crawl_job'`: the table, its UNIQUE autoindex and
-- `ix_crawl_job_status`), so there is none to recreate. The UNIQUE autoindex comes back
-- with the table; `ix_crawl_job_status` does not, and is recreated below, because it is
-- what `/api/jobs` orders by.

PRAGMA user_version = 23;
PRAGMA legacy_alter_table = ON;

CREATE TABLE crawl_job_rebuilt (
    job_id             INTEGER PRIMARY KEY,
    job_ref            TEXT NOT NULL UNIQUE,
    run_mode           TEXT NOT NULL
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild',
                            'history_backfill')),
    -- THE ONE CHANGE: `skipped`, which is `scrapex.vocab.JobStatus.SKIPPED`.
    -- `tests/test_schema.py` writes every `JobStatus` member through this CHECK, so the
    -- enum cannot name a status the warehouse refuses without a test saying so.
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
