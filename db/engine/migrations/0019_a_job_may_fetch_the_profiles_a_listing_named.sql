-- A fifth job kind: fetching the profile pages a listing crawl named.
--
-- WHY IT IS NEEDED, MEASURED ON HIS WAREHOUSE 2026-09-06. Joining the two datasets on
-- `json_extract(data_json,'$.contractor_id')`: 17,768 distinct contractors, 17,379
-- distinct profiles, and **424 contractors with no profile row at all**. The newest
-- profile was written 2026-09-01; nothing has fetched one since. The step that fetches
-- them -- `contractors.details`, reached from `--details` -- had no API route, no job
-- kind and no control in the panel, so under `R-81` it did not exist for the one person
-- the tool is for. His words: «لا استطيع عبر الواجهة ... عمل crawl ل profiles او حتى
-- استكمال profiles الناقصة».
--
-- THIS IS THE SAME HOLE `0018` CLOSED FOR `approve`, one phase further along the
-- pipeline: crawl the listing, fetch the profiles it named, interpret what was stored.
-- Two of the three had a door before this.
--
-- WHY A REBUILD FOR ONE STRING, and it is the same reason `0017` and `0018` gave: SQLite
-- accepts a CHECK and then offers no way to alter it. Without this, the route names the
-- kind, `create_job` runs, and SQLite answers `CHECK constraint failed`.
--
-- THE DIRECTION IS THE SAFE ONE. This only WIDENS a CHECK, so no row that satisfied the
-- old constraint can fail the new one. `0014` is the counter-example this folder
-- remembers: it rebuilt `source_site` with `base_url TEXT NOT NULL DEFAULT ''` while
-- copying the old nullable column through BY NAME, and a DEFAULT never applies to a named
-- column -- so any pre-v14 row holding NULL failed that upgrade.
--
-- `legacy_alter_table = ON` IS REQUIRED, NOT DEFENSIVE. Four tables carry
-- `REFERENCES crawl_job`: `change_event`, `crawl_run`, `job_log_entry` and
-- `organization_enrichment_job`. Without the pragma the RENAME rewrites their REFERENCES
-- clauses to point at `crawl_job_old`, which is then dropped.
--
-- AND THE INDEX IS RECREATED BECAUSE A REBUILD TAKES IT WITH THE TABLE.
-- `ix_crawl_job_status` is what `/api/jobs` orders by; losing it turns the panel's job
-- list into a full scan of every job ever run, which is slow rather than wrong and so
-- would not have failed anything.

PRAGMA user_version = 19;
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
    -- THE ONE CHANGE. `profile_crawl` is `scrapex/profilejob.py`'s `JOB_KIND`, and
    -- `scrapex.jobs.JOB_KINDS` is derived from `SPECIALISED_RUNNERS` so the Python side
    -- cannot list a kind this constraint refuses without a test saying so.
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
