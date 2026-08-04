-- =====================================================================
-- 0061 — A RUN SAYS WHETHER IT HAD WARNINGS
--
-- SPARK_ESHOP was crawled on 2026-08-03. The run row says: success,
-- 1,789 products, 3,149 rows. Nothing about it looked wrong, and 1,789
-- English product names had just been filed under the Arabic column
-- because the shop has no /en locale and the connector asked for one
-- anyway.
--
-- The explanation was NOT lost. It is in job_log_entry right now:
--
--   en locale unavailable — names stay single-language this run:
--   Client error '404 Not Found' for url
--   'https://www.spark-eshop.com/en/products.json?limit=250&page=1'
--
-- But a run row could not say it had one. Finding that sentence needs a
-- reader who already suspects something, knows the log exists, and knows
-- which job id to join on — and for two days nobody did. A count on the
-- run is what turns "look for trouble" into "trouble is here".
--
-- Two columns and no more. The count, because a clean run must be
-- VISIBLY clean rather than merely quiet; and the first line, because
-- one sentence is usually enough to decide whether the log is worth
-- opening. The log stays the full record — this is its index, not a
-- second copy of it.
-- =====================================================================

ALTER TABLE crawl_run ADD COLUMN warning_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE crawl_run ADD COLUMN first_warning TEXT NOT NULL DEFAULT '';

-- Backfilled from the log the warnings have always been written to, so a
-- run that already happened can answer for itself. Only WARNING rows,
-- and the earliest one per run — the same thing a future run records.
UPDATE crawl_run
   SET warning_count = (
         SELECT COUNT(*) FROM job_log_entry j
          WHERE j.job_id = crawl_run.job_id
            AND j.source_key = (SELECT source_key FROM source_site s
                                 WHERE s.source_id = crawl_run.source_id)
            AND j.level = 'warning')
 WHERE job_id IS NOT NULL;

UPDATE crawl_run
   SET first_warning = COALESCE((
         SELECT SUBSTR(j.message, 1, 500) FROM job_log_entry j
          WHERE j.job_id = crawl_run.job_id
            AND j.source_key = (SELECT source_key FROM source_site s
                                 WHERE s.source_id = crawl_run.source_id)
            AND j.level = 'warning'
          ORDER BY j.job_log_id LIMIT 1), '')
 WHERE warning_count > 0;

PRAGMA user_version = 61;
