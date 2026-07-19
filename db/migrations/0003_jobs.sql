-- ============================================================================
-- Migration 0003 — the JOB subsystem (spec sections 4, 23, 24, 25).
--
-- A JOB is one owner-requested unit of work: a run mode applied to one or more
-- sources. It owns 1..N crawl_run rows (a run is one source's execution and
-- stays the provenance anchor for price_observation).
--
-- WHY THE DB, NOT MEMORY: the side panel must never own or execute a crawl.
-- Closing the panel cannot stop a job, and reopening must recover the exact
-- current state — so status, progress, counters, checkpoint and the owner's
-- pause/cancel intent (`control`) all live here, not in a process variable.
-- ============================================================================

CREATE TABLE crawl_job (
    job_id             INTEGER PRIMARY KEY,
    job_ref            TEXT NOT NULL UNIQUE,   -- stable public id used by the extension
    run_mode           TEXT NOT NULL
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild')),
    status             TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                           'scheduled','queued','preparing','running','pausing','paused',
                           'resuming','cancelling','cancelled','completed',
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

CREATE INDEX ix_crawl_job_status ON crawl_job(status, created_at DESC);

-- Full technical log lives in the runtime/DB; the panel only ever tails it
-- (spec 25: aggregated entries, never one row per scraped record).
CREATE TABLE job_log_entry (
    job_log_id INTEGER PRIMARY KEY,
    job_id     INTEGER NOT NULL REFERENCES crawl_job(job_id),
    logged_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    level      TEXT NOT NULL DEFAULT 'info'
        CHECK (level IN ('debug','info','warning','error')),
    source_key TEXT,
    message    TEXT NOT NULL
);

CREATE INDEX ix_job_log_job_time ON job_log_entry(job_id, job_log_id DESC);

-- Provenance: which job produced this run (NULL for pre-0003 and CLI runs).
ALTER TABLE crawl_run ADD COLUMN job_id INTEGER REFERENCES crawl_job(job_id);

PRAGMA user_version = 3;
