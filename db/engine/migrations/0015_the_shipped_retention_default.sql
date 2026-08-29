-- THE SHIPPED RETENTION DEFAULT, WHICH A NEW INSTALLATION HAS NEVER HAD.
--
-- `retention_policy` holds one row per source plus a global `'*'`, and the global one is
-- what says "keep everything until the owner decides otherwise". The retired
-- `db/migrations/0011_retention.sql` created the table AND seeded that row in the same
-- file. `db/engine/schema.sql` was derived from the two streams' DDL when they were
-- collapsed — and a derivation carries CREATE statements, not INSERTs. So the table came
-- across and the row did not.
--
-- NOBODY NOTICED BECAUSE NOBODY COULD. `derived-from.json` freezes 134 objects and their
-- columns; it says nothing about rows, so the guard that proves the collapse lost nothing
-- was structurally blind to this. And every test that touched retention built its database
-- through `dbmod.migrate`, which ran the legacy stream and therefore seeded the row — so
-- the suite was green on a database no installation would ever have.
--
-- Retiring that stream on 2026-08-29 pointed those tests at the real engine schema and
-- `test_the_shipped_default_changes_nothing` failed with `KeyError: '*'` on the first run.
--
-- HIS OWN WAREHOUSE IS NOT AFFECTED and was checked before this was written: it holds
-- `('*', 3650, 'keep_all', 0)`, because it predates the split and carried the row across.
-- This is for the installation nobody has made yet, which is the harder kind to test.
--
-- `INSERT OR IGNORE` rather than a bare INSERT: a warehouse that already has the row —
-- his, and every other one that existed before today — must not have it duplicated or the
-- migration fail on the UNIQUE. The reason it is a migration at all rather than a line in
-- `schema.sql` is that `schema.sql` is GENERATED (`tools/derive_engine_schema.py`), so an
-- edit there is overwritten the next time it runs.

PRAGMA user_version = 15;

INSERT OR IGNORE INTO retention_policy (source_key, detail_days, older_than_action)
VALUES ('*', 3650, 'keep_all');
