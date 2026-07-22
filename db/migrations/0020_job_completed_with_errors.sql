-- =====================================================================
-- 0020 — A JOB THAT FINISHED, BUT NOT CLEANLY (اكتمل مع أخطاء)
--
-- The job vocabulary could say "completed" (everything clean),
-- "partially_completed" (a whole source died) and "failed" (they all
-- did) — but had no word for the case that actually happened live: every
-- source ran to the end, yet one run's ingest degraded to partial. The
-- worker folded those ingest error MESSAGES into a bare integer counter,
-- so the job finished 'completed' with error_summary NULL and the reason
-- eighteen offers lost their derived price layer was unrecoverable from
-- any log.
--
-- 'completed_with_errors' names that case: the crawl finished, the data
-- that could land landed, and something along the way still needs the
-- owner's eyes. It is terminal, like the other three.
--
-- SQLite cannot widen a CHECK constraint in place, so crawl_job is
-- rebuilt. job_log_entry and crawl_run reference it by job_id; the
-- rebuild keeps every id, so the references stay valid — enforcement is
-- suspended for the swap and re-enabled after.
-- =====================================================================

PRAGMA foreign_keys = OFF;

CREATE TABLE crawl_job_new (
    job_id             INTEGER PRIMARY KEY,
    job_ref            TEXT NOT NULL UNIQUE,   -- stable public id used by the extension
    run_mode           TEXT NOT NULL
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild')),
    status             TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                           'scheduled','queued','preparing','running','pausing','paused',
                           'resuming','cancelling','cancelled','completed',
                           'completed_with_errors',
                           'partially_completed','failed','requires_review')),
    -- Owner intent, applied by the worker at the next safe boundary (never mid-write).
    control            TEXT NOT NULL DEFAULT 'none'
        CHECK (control IN ('none','pause','resume','cancel')),
    source_keys        TEXT NOT NULL,          -- JSON array, in execution order
    current_source_key TEXT,
    stage              TEXT,                   -- preparing | fetching | ingesting | finalizing
    progress_done      INTEGER NOT NULL DEFAULT 0,   -- sources finished
    progress_total     INTEGER NOT NULL DEFAULT 0,   -- sources requested
    counters_json      TEXT,                   -- aggregated observations/products/errors/...
    checkpoint_json    TEXT,                   -- {"completed_source_keys": [...]} — resume point
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at         TEXT,
    finished_at        TEXT,
    last_heartbeat_at  TEXT,                   -- worker liveness; a stale beat = crashed runtime
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

-- Indexes die with the old table; rebuild them on the new one.
CREATE INDEX ix_crawl_job_status ON crawl_job(status, created_at DESC);

PRAGMA foreign_keys = ON;

PRAGMA user_version = 20;
