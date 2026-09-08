-- A profile URL the site declines to serve, recorded where the sighting lives.
--
-- MEASURED ON HIS WAREHOUSE, 2026-09-07. An interpretation of 938 fetched profile pages
-- turned 432 of 469 page pairs into rows and refused 37, every one of them with
-- `ProfileIdDidNotResolve`: the site answered `/contractors/<id>/143` with the
-- contractors listing, at HTTP 200. The row gap fell 469 -> 37 and stopped there, so the
-- card went on saying 37 contractors have work waiting on them, for ever, and coverage
-- could never reach its population.
--
-- AND THE OBVIOUS WORD FOR IT IS THE WRONG ONE, which is why this column is not called
-- `gone_at`. Every one of the 20 ids recoverable from the log carries:
--
--     an ACTIVE listing row, last seen 2026-08-29
--     last_absent_at = NULL
--     and the ledger holds ZERO proven absences out of 17,848 sightings
--
-- The contractor is published. Its PROFILE PAGE is not served. Those are two facts and
-- only the second one has evidence, so the column names the second one.
--
-- `mark_unavailable` CANNOT EXPRESS IT EITHER, and that is not an oversight of this
-- migration. That function needs an existing `generic_record` to set a status on -- these
-- 37 have no profile row at all, which is the whole point -- and it reserves
-- `unavailable` for what a crawl PROVED absent by closing its cells with `D = 0`. Its own
-- docstring refuses to mark a row without `last_absent_at`, for the reason `R-27` exists:
-- a crawler having a bad afternoon must not delist anybody.
--
-- SHAPED ON `last_absent_at` / `last_absent_run_ref`, deliberately and in the same table.
-- That pair already means "we looked and it was not there" about the LISTING; this pair
-- means the same about the PROFILE. A date rather than a flag, so the observation can be
-- re-judged, and the run ref so a pass later found to have been wrong -- a site outage,
-- a redirect -- can have everything it marked lifted in one statement.
--
-- ADD COLUMN AND NOT A REBUILD. Both are nullable with no default and no CHECK, so no
-- existing row can fail this and nothing needs copying. `0014` is the counter-example
-- this folder remembers: it rebuilt `source_site` copying a nullable column through BY
-- NAME into a NOT NULL DEFAULT '' column, and a DEFAULT never applies to a named column,
-- so every pre-v14 row holding NULL failed that upgrade.
--
-- NOT IN `schema.sql`. A fresh install runs the baseline and then every migration, so
-- declaring the columns in both would make this ALTER fail on a new warehouse with
-- `duplicate column name`. `tests/test_migration_drift.py` compares a fresh build against
-- an upgraded one for exactly this.

PRAGMA user_version = 20;

-- WHEN a profile URL for this sighted id was found not to resolve. NULL means it has
-- never been found not to resolve -- which is not the same as "resolves": a contractor
-- whose profile nobody has fetched is NULL here too.
ALTER TABLE dataset_sighting ADD COLUMN profile_unresolved_at TEXT;

-- WHICH RUN judged it, so a pass later found to have been wrong can be undone as a set
-- rather than one id at a time.
ALTER TABLE dataset_sighting ADD COLUMN profile_unresolved_run_ref TEXT;
