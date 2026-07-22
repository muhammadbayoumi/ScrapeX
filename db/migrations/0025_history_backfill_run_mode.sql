-- =====================================================================
-- 0025 — HISTORY BACKFILL AS A RUN MODE (جمع تاريخ المصدر من الواجهة)
--
-- The owner runs everything from the interface, never the terminal. The
-- ten-year GPP backfill existed only as a CLI flag; making it a job the
-- panel can enqueue means the job vocabulary must know the word. It is a
-- CAPABILITY, not a universal mode — the panel offers it only for
-- sources whose connector publishes history — but the schema must accept
-- it for the sources that do.
--
-- Same rebuild recipe as 0020: SQLite cannot widen a CHECK in place, so
-- crawl_job is rebuilt keeping every id; the runner suspends FK
-- enforcement around the script and foreign_key_check guards the commit.
-- =====================================================================

PRAGMA foreign_keys = OFF;

CREATE TABLE crawl_job_new (
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
    error_summary      TEXT
);

INSERT INTO crawl_job_new (
    job_id, job_ref, run_mode, status, control, source_keys, current_source_key,
    stage, progress_done, progress_total, counters_json, checkpoint_json,
    created_at, started_at, finished_at, last_heartbeat_at, retry_count,
    output_status, error_summary)
SELECT
    job_id, job_ref, run_mode, status, control, source_keys, current_source_key,
    stage, progress_done, progress_total, counters_json, checkpoint_json,
    created_at, started_at, finished_at, last_heartbeat_at, retry_count,
    output_status, error_summary
FROM crawl_job;

DROP TABLE crawl_job;
ALTER TABLE crawl_job_new RENAME TO crawl_job;

CREATE INDEX ix_crawl_job_status ON crawl_job(status, created_at DESC);

PRAGMA foreign_keys = ON;

PRAGMA user_version = 25;
