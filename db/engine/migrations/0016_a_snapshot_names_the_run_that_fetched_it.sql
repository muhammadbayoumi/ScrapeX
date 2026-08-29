-- A SNAPSHOT NAMES THE RUN THAT FETCHED IT, WITH AN ID RATHER THAN A LABEL.
--
-- `R-54`'s second half: state is computed against the RUN that wrote a row, not against
-- `MAX(last_seen_at)`. The root half shipped in `#281` — a confirming pass now moves the
-- record's own date — and this is the field that half was waiting for.
--
-- WHY `crawl_run_ref` COULD NOT BE IT, measured on his warehouse on 2026-08-29 before a
-- line of this was written:
--
--     distinct values                          141   across 55,313 snapshots
--     listing-2026-08-20                        64   distinct refs -- ONE PER CELL
--     residual-2026-08-21                       40
--     profiles-2026-08-22                        1   -- one ref for 34,834 pages
--     one stored value is literally  'R'         2   snapshots
--     matches against crawl_run.* or crawl_job.job_ref:  0
--
-- It is the free-text `--run-ref` an operator types. Nothing validates it, nothing joins to
-- it, and its granularity is per PARTITION CELL for a listing crawl and per CRAWL for a
-- profile crawl — so "the latest run" would mean two different sizes of thing depending on
-- which dataset asked. Simulated: comparing against it would have read `absent` on 17,030
-- of 17,304 listing rows and 17,384 of 17,385 profile rows. Worse than the defect.
--
-- AND `R-52` CHOSE A NEW TABLE FOR A REASON THAT HAS SINCE EXPIRED. Its own words: "crawl_run
-- is the price path alone — its `source_id` points at a price source, nothing for a dataset."
-- That was true on 2026-08-24. `R-62`'s registry merge (`0014`) put `muqawil_org` in
-- `source_site` at `source_id = 14`, so `crawl_run.source_id` now resolves for a dataset
-- source like any other. He was shown the measurement and ruled: **one run table for
-- everything**, which is `R-72`'s own reasoning applied one layer down — two concepts for one
-- thing is what the second migration stream cost all day.
--
-- SO THIS ADDS A COLUMN AND NOT A TABLE.
--
-- `ADD COLUMN` rather than a rebuild, deliberately: `generic_page_snapshot` holds 57,041 rows
-- and 1.4 GB of compressed bodies, and adding a nullable column with no default is a
-- metadata-only change in SQLite — it does not rewrite a page of that. A rebuild would copy
-- every stored body to add one integer.
--
-- NULL IS A REAL ANSWER AND NOT A GAP. 1,728 snapshots predate run identity entirely, and
-- every snapshot stored before this migration has no run to name. His ruling for those rows
-- is `unsighted` — the state that says "stored before the ledger existed" and claims nothing
-- about the site — rather than `absent`, which would claim the site stopped publishing a
-- contractor it still lists.
--
-- `crawl_run_ref` STAYS. It is what the operator typed and it is how `--run-ref` resumes an
-- interrupted crawl (`contractors.py` matches on it to build the skip set). This column
-- answers a different question — WHICH RUN, provably — and the two are not substitutes.

PRAGMA user_version = 16;

ALTER TABLE generic_page_snapshot
    ADD COLUMN run_id INTEGER REFERENCES crawl_run(run_id);

-- The state computation asks "which run wrote this row" once per row and "which run is the
-- latest for this dataset" once per dataset. Both go through this column, and without an
-- index the first is a scan of 57,041 rows per dataset render.
CREATE INDEX ix_generic_page_snapshot_run ON generic_page_snapshot(run_id);
