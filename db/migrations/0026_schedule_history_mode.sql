-- =====================================================================
-- 0026 — A SCHEDULE MAY NAME ANY RUN MODE ITS SOURCE SUPPORTS
--
-- The Schedules page is the owner's central control for automation, and
-- crawl_job learned 'history_backfill' in 0025 — but schedule.run_mode
-- kept the older three-word CHECK, so scheduling a history backfill
-- would die on the constraint at save time. The two vocabularies must
-- not drift: a mode a job can run is a mode a schedule can name.
-- (Whether a SOURCE supports it stays the capability gate's job, in the
-- panel and again in capture.)
--
-- Same rebuild recipe as 0020/0025; schedule has no children, ids kept.
-- =====================================================================

PRAGMA foreign_keys = OFF;

CREATE TABLE schedule_new (
    schedule_id       INTEGER PRIMARY KEY,
    source_key        TEXT NOT NULL UNIQUE,
    frequency         TEXT NOT NULL DEFAULT 'manual'
        CHECK (frequency IN ('manual','daily','weekly')),
    run_at            TEXT NOT NULL DEFAULT '09:00',
    timezone          TEXT NOT NULL DEFAULT 'UTC',
    weekday           INTEGER,
    run_mode          TEXT NOT NULL DEFAULT 'update'
        CHECK (run_mode IN ('initial_crawl','update','full_rebuild',
                            'history_backfill')),
    missed_run_policy TEXT NOT NULL DEFAULT 'run_when_available'
        CHECK (missed_run_policy IN ('run_when_available','skip')),
    overlap_policy    TEXT NOT NULL DEFAULT 'queue'
        CHECK (overlap_policy IN ('queue','skip')),
    enabled           INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    last_run_at       TEXT,
    next_run_at       TEXT,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

INSERT INTO schedule_new SELECT * FROM schedule;

DROP TABLE schedule;
ALTER TABLE schedule_new RENAME TO schedule;

CREATE INDEX ix_schedule_due ON schedule(enabled, next_run_at);

PRAGMA foreign_keys = ON;

PRAGMA user_version = 26;
