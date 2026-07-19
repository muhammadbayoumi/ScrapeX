-- ============================================================================
-- Migration 0009 — per-source schedules (spec section 26).
--
-- HONESTY CONSTRAINT: nothing here can wake a sleeping or powered-off machine.
-- Browser alarms certainly cannot, and the local runtime only runs while it is
-- running. So a MISSED slot is a normal, expected state, and the design says so
-- out loud: next_run_at is a due-time, and missed_run_policy decides whether a
-- slot that passed while we were off fires once on catch-up or is let go.
--
-- next_run_at is always stored in UTC; run_at + timezone are what the owner set.
-- ============================================================================

CREATE TABLE schedule (
    schedule_id       INTEGER PRIMARY KEY,
    source_key        TEXT NOT NULL UNIQUE,   -- one schedule per source
    frequency         TEXT NOT NULL DEFAULT 'manual'
        CHECK (frequency IN ('manual','daily','weekly')),
    run_at            TEXT NOT NULL DEFAULT '09:00',   -- 'HH:MM' local to `timezone`
    timezone          TEXT NOT NULL DEFAULT 'UTC',     -- IANA name, e.g. Asia/Riyadh
    weekday           INTEGER,                          -- 0=Monday .. 6=Sunday (weekly only)
    run_mode          TEXT NOT NULL DEFAULT 'update'
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild')),
    missed_run_policy TEXT NOT NULL DEFAULT 'run_when_available'
        CHECK (missed_run_policy IN ('run_when_available','skip')),
    overlap_policy    TEXT NOT NULL DEFAULT 'queue'
        CHECK (overlap_policy IN ('queue','skip')),
    enabled           INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    last_run_at       TEXT,
    next_run_at       TEXT,                    -- UTC ISO8601; NULL for manual
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX ix_schedule_due ON schedule(enabled, next_run_at);

PRAGMA user_version = 9;
