-- A third job kind: the directory listing crawl the panel's button starts.
--
-- WHY A REBUILD FOR ONE STRING. `job_kind` arrived in `0011` as
-- `ADD COLUMN job_kind TEXT NOT NULL DEFAULT 'crawl' CHECK (job_kind IN ('crawl',
-- 'organization_enrichment'))`. SQLite accepts a CHECK on an added column and then
-- offers no way to alter it: a constraint can only be changed by rebuilding the table.
-- Without this the route accepts `muqawil_org`, `create_job` runs, and SQLite answers
-- `CHECK constraint failed: job_kind IN ('crawl','organization_enrichment')` -- measured,
-- and it is what turned `test_the_route_queues_a_registry_source_instead_of_answering_404`
-- red the moment the route learned to name the new kind.
--
-- THE DIRECTION IS THE SAFE ONE, AND IT IS WORTH SAYING BECAUSE THE LAST REBUILD IN THIS
-- FOLDER GOT IT WRONG IN THE OTHER DIRECTION. `0014` rebuilt `source_site` with
-- `base_url TEXT NOT NULL DEFAULT ''` while copying the old, nullable column through by
-- name -- and a DEFAULT never applies to an explicitly named column, so any pre-v14 row
-- holding NULL fails that upgrade. This migration only WIDENS a CHECK, so no row that
-- satisfied the old constraint can fail the new one, and the copy below is asserted
-- rather than assumed.
--
-- `legacy_alter_table = ON` IS REQUIRED, NOT DEFENSIVE. `crawl_job(job_id)` is referenced
-- by `crawl_run`, `job_log_entry` and `crawl_job_source`; without it the RENAME rewrites
-- their REFERENCES clauses to point at `crawl_job_old`, which is then dropped.
--
-- AND THE INDEX IS RECREATED BECAUSE A REBUILD TAKES IT WITH THE TABLE.
-- `ix_crawl_job_status` is what `/api/jobs` orders by; losing it turns the panel's job
-- list into a full scan of every job ever run, which is slow rather than wrong and so
-- would not have failed anything.

PRAGMA user_version = 17;
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
                           'partially_completed','failed','requires_review')),
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
    -- THE ONE CHANGE. `directory_crawl` is `scrapex/directoryjob.py`'s `JOB_KIND`, and
    -- `scrapex.jobs.JOB_KINDS` is derived from `SPECIALISED_RUNNERS` so the Python side
    -- cannot list a kind this constraint refuses without a test saying so.
    job_kind           TEXT NOT NULL DEFAULT 'crawl'
        CHECK (job_kind IN ('crawl', 'organization_enrichment', 'directory_crawl'))
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
