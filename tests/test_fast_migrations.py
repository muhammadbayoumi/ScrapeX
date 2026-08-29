"""What tests/conftest.py must keep being true (ENGINEERING.md Q8, P2).

That file swaps a real `migrate()` for a template restore roughly 760 times per
run. Q8 says a workaround ships with a test pinning current behaviour; these are
those tests, and they exist because every way this can break is SILENT:

  - a template that is not a real migration hands every test a wrong schema
  - a guard that vetoes forever makes the suite slow again, never red
  - a guard that under-fires lets an upgrade test assert against v57

The one that matters most is the first. If the template IS one honest run of the
real 57-file stream, then every restore that copies it is honest too, and the
whole mechanism reduces to that single claim.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

from scrapex import db as dbmod

# `retention_policy.updated_at` defaults to strftime('%Y-%m-%dT%H:%M:%SZ','now')
# (db/migrations/0011_retention.sql), so two HONEST migrations a second apart
# differ there. Comparing it would make this test fail at random, which is worse
# than not having it — a gate people learn to ignore is not a gate.
#: Columns whose value is the WALL CLOCK, which two runs can never agree on. Comparing
#: them would make this gate fail on the passage of time rather than on a difference in
#: the schema, which is the one thing it exists to see.
_CLOCK_COLUMNS = {
    ("retention_policy", "updated_at"),
    # `database_migration.applied_at` JOINED THIS LIST ON 2026-08-29, and it could not have
    # been needed before: `db.migrate` did not write the ledger at all, so the table was
    # empty in both databases and matched trivially. Retiring the second stream made
    # `db.migrate` delegate to the engine runner, which DOES record every migration -- so
    # the two runs began to differ by the second they happened to run in.
    ("database_migration", "applied_at"),
}


def _shape(conn: sqlite3.Connection) -> dict:
    """Everything about a database that a real migration decides."""
    shape: dict = {
        "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
        "application_id": conn.execute("PRAGMA application_id").fetchone()[0],
        "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
        "foreign_keys": conn.execute("PRAGMA foreign_key_check").fetchall(),
        "schema": sorted(
            (row[0], row[1], row[2] or "")
            for row in conn.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        ),
    }
    for kind, name, _sql in shape["schema"]:
        if kind != "table":
            continue
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({name})")
                   if (name, r[1]) not in _CLOCK_COLUMNS]
        if not columns:
            continue
        picked = ", ".join(f'"{c}"' for c in columns)
        # tuple() because dbmod.connect sets row_factory = sqlite3.Row while a
        # plain connection yields tuples; comparing the raw objects compares
        # their addresses and every row looks different.
        shape[f"rows:{name}"] = sorted(
            repr(tuple(row))
            for row in conn.execute(f"SELECT {picked} FROM {name}"))
    return shape


def test_the_template_is_one_honest_run_of_the_real_migrations(schema_template, tmp_path):
    """THE gate. Every restored database is a copy of this one, so if this holds,
    all ~760 of them are as good as a real migration — and if it ever stops
    holding, the whole suite has been testing a schema nobody ships."""
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: there is no template to check")

    honest = dbmod.connect(tmp_path / "honest.db")
    schema_template.real_migrate(honest)

    served = sqlite3.connect(str(schema_template.dir / "template.db"))
    try:
        assert _shape(served) == _shape(honest)
    finally:
        served.close()
        honest.close()


def test_the_template_carries_the_whole_stream(schema_template):
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: there is no template to check")
    assert schema_template.user_version == dbmod.latest_schema_version()
    # Not a rebuilt range(): the list the real migrate actually returned.
    assert schema_template.applied[-1] == schema_template.user_version
    assert schema_template.applied == sorted(set(schema_template.applied))


def test_a_reloaded_db_module_does_not_disable_the_template(schema_template):
    """tests/test_db.py calls importlib.reload(scrapex.db) four times.

    The guard that shipped first compared `dbmod._migration_files` by IDENTITY.
    Reload installs a NEW function object that behaves identically, so that guard
    became a permanent veto and every file collected after test_db.py silently
    paid full price again — 41 of the 57 migrate-calling files. Nothing turned
    red; the suite just got slow. This pins the content comparison that replaced it.
    """
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: nothing is armed")

    before_obj = dbmod._migration_files
    assert schema_template.fingerprint() == schema_template.stream

    importlib.reload(dbmod)
    try:
        assert dbmod._migration_files is not before_obj, (
            "reload did not replace the object; this test would prove nothing")
        # Same stream by content, which is the only thing that matters.
        assert schema_template.fingerprint() == schema_template.stream
    finally:
        schema_template.arm()   # leave the session as we found it


def test_a_truncated_stream_is_never_served_the_template(schema_template, monkeypatch, tmp_path):
    """A test that replays history by cutting the stream short must not be handed the
    template: it would not fail, it would quietly assert against the wrong schema.

    THE CUT IS RELATIVE, and it used to be the literal 46. That number belonged to
    `db/migrations/`, retired on 2026-08-29 — and once the chain ended at 15, `<= 46` kept
    every file, truncated nothing, and the assertion below flipped. A guard whose premise
    is a magic number from another stream stops being a guard the moment the stream goes;
    one short of whatever the chain is today can never stop truncating.
    """
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: nothing is armed")

    conn = dbmod.connect(tmp_path / "truncated.db")
    try:
        assert schema_template.may_restore(conn) is True     # pristine: eligible
        every = dbmod._migration_files()
        assert len(every) > 1, "a one-file stream cannot be truncated, so nothing is proved"
        monkeypatch.setattr(dbmod, "_migration_files", lambda: every[:-1])
        assert schema_template.may_restore(conn) is False    # ...but not this stream
    finally:
        conn.close()


def test_a_database_that_already_has_a_schema_is_upgraded_not_replaced(schema_template, tmp_path):
    """Three files hand-replay a migration prefix and then upgrade over it. A
    restore would discard their rows, and `backup()` would not complain."""
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: nothing is armed")

    conn = dbmod.connect(tmp_path / "populated.db")
    try:
        conn.execute("CREATE TABLE something (id INTEGER PRIMARY KEY)")
        conn.execute("PRAGMA user_version = 20")
        conn.commit()
        assert schema_template.may_restore(conn) is False
    finally:
        conn.close()


def test_an_open_transaction_is_never_restored_into(schema_template, tmp_path):
    """A destination inside a write transaction raises; a SOURCE inside one hangs
    forever with no exception. No call site does this today — this is what keeps
    that true."""
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: nothing is armed")

    conn = dbmod.connect(tmp_path / "busy.db")
    try:
        assert schema_template.may_restore(conn) is True    # pristine: eligible
        # Explicit BEGIN, because the database has to stay PRISTINE for this to
        # test the transaction guard rather than the emptiness guard — and with
        # no tables there is no DML to open one implicitly.
        conn.execute("BEGIN")
        assert conn.in_transaction
        assert schema_template.may_restore(conn) is False
    finally:
        conn.rollback()
        conn.close()


def test_the_file_that_tests_migrate_itself_is_declared(schema_template):
    """test_db.py asserts on migrate()'s RETURN VALUE on a pristine connection,
    which no predicate can tell apart from an ordinary caller. Defect injection
    proved two of its tests pass while migrate() is broken, so it is excluded by
    name. If that name ever changes, this fails and the exclusion gets revisited
    instead of silently lapsing."""
    if schema_template.disabled:
        pytest.skip("SCRAPEX_FULL_MIGRATIONS: nothing is excluded")
    from pathlib import Path

    for name in schema_template.never_restore:
        assert (Path(__file__).parent / f"{name}.py").is_file(), (
            f"{name} is excluded from the schema template but no such test file "
            f"exists — the exclusion is now protecting nothing")
