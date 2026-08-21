-- =====================================================================
-- 0006 — A ROW SAYS WHEN IT WAS LAST PROVED ABSENT
--
-- His instruction, 2026-08-21: «ضيف الحالات التى ذكرتها ولا يتم تغطيتها
-- الان وايضا عمود يوضح الحالة الجديدة لا تدع المستخدم يستنتج الحالة» —
-- add the states that are not covered, and give the state its own column
-- instead of leaving the reader to infer it.
--
-- Under R-27 a row never leaves the screen and its state becomes a column.
-- Six states were computable from what the schema already held:
--
--     new · updated · confirmed · absent · unsighted · retired
--
-- One was NOT, and this migration is the reason it now is:
--
--     returned — absent in an earlier crawl, and here again
--
-- WHY IT COULD NOT BE DERIVED. `dataset_sighting` records `first_seen_at`,
-- `last_seen_at` and `seen_count`. Absence leaves NO trace in that shape:
-- a row simply stops being touched, and a `last_seen_at` two crawls old
-- is indistinguishable from one whose id was missed once and seen again.
-- "Was this id absent at some point" is a question about a moment that
-- has already passed, so it cannot be recomputed later — it has to have
-- been WRITTEN when the crawl proved it.
--
-- WHY ONE COLUMN AND NOT A ROW PER RUN. A `(dataset_key, external_id,
-- run_ref)` table answers more questions — the full attendance register —
-- and costs 17,403 rows per crawl for them. What the state column needs is
-- only the LATEST absence, because `returned` is
-- `last_seen_at > last_absent_at` and nothing finer. So this stores the
-- one fact that cannot be derived and declines to store a history nobody
-- has asked for. The register can be added later; this cannot be skipped.
--
-- ABSENCE IS ONLY EVER WRITTEN FROM A PROOF. A crawl may miss a
-- contractor for its own reasons — a dead page, a rolled cache generation,
-- a cell above the witness ceiling. So this column is written only for a
-- cell that closed with D = 0, where every published row provably WAS
-- seen. Writing it from a partial crawl would retire contractors because
-- the crawler had a bad afternoon, which is the exact failure R-27 exists
-- to prevent, arriving from the other side.
--
-- NULLABLE, AND EVERY EXISTING ROW STAYS NULL. Nothing has ever proved an
-- absence, so nothing may claim one: NULL means "never proved absent",
-- which is the truth about all 14,180 sightings on disk today.
-- =====================================================================

ALTER TABLE dataset_sighting ADD COLUMN last_absent_at TEXT;

-- The run that proved it, so a reader can go and look at the evidence
-- rather than trusting the timestamp. Same reasoning as
-- `generic_page_snapshot.crawl_run_ref`: a fact with no provenance is a
-- fact nobody can check.
ALTER TABLE dataset_sighting ADD COLUMN last_absent_run_ref TEXT;

-- FOUND BY THE STATE COLUMN AND NOT BY THIS MIGRATION, but it belongs
-- here: every state question starts with "which rows of this dataset",
-- and `dataset_sighting` is indexed on `(dataset_key, external_id)` only.
-- A scan by `last_seen_at` — which is what "seen in the last crawl" is —
-- had no index at all.
CREATE INDEX IF NOT EXISTS ix_dataset_sighting_last_seen
    ON dataset_sighting(dataset_key, last_seen_at);
