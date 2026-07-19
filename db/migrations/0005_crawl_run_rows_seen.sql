-- ============================================================================
-- Migration 0005 — record how many rows a run actually saw.
--
-- The F6 volume canary (min_expected_rows / max_drop_pct) was declared per source
-- in sources.yaml but could never be evaluated: nothing persisted the row count,
-- so a connector that silently started returning zero rows still recorded
-- status='success'. rows_seen is that missing measurement, and it is what the
-- max_drop_pct comparison reads from the previous successful run.
-- ============================================================================

ALTER TABLE crawl_run ADD COLUMN rows_seen INTEGER NOT NULL DEFAULT 0;

PRAGMA user_version = 5;
