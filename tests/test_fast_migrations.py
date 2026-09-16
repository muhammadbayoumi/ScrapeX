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
from pathlib import Path

import pytest

from scrapex import db as dbmod

ROOT = Path(__file__).resolve().parent.parent

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

#: ROWS, NOT COLUMNS, and it needs its own list because `scrapex_meta` is one
#: table holding many unrelated facts: excluding a COLUMN there would drop every
#: setting the migrations write, which is most of what this gate reads.
#:
#: `schema_written_by` and `schema_written_at` are per-RUN by design -- the
#: build that migrated the file and the instant it did -- so two honest runs a
#: second apart differ there, and a source checkout differs from itself between
#: commits. That is the same reason `applied_at` above is excluded, one level in:
#: this gate compares what the MIGRATIONS decide, and who ran them is not one of
#: those things.
_PER_RUN_META_KEYS = {"schema_written_by", "schema_written_at"}


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
        rows = [tuple(row) for row in conn.execute(f"SELECT {picked} FROM {name}")]
        if name == "scrapex_meta" and columns and columns[0] == "key":
            rows = [row for row in rows if row[0] not in _PER_RUN_META_KEYS]
        shape[f"rows:{name}"] = sorted(repr(row) for row in rows)
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
        # A LONGER STREAM, NOT A TRUNCATED ONE, and the reason is `R-84`. Cutting the
        # last file proved the fingerprint notices a DIFFERENT stream, and it worked
        # only while there were two files to cut between. The squash made the chain
        # one file, `every[:-1]` empty, and the assertion above it -- "a one-file
        # stream cannot be truncated, so nothing is proved" -- fired exactly as its
        # author intended. Adding a file tests the same property and cannot run out
        # of stream: what is under test is that the template refuses a fingerprint
        # it did not build, in either direction.
        longer = [*every, (every[-1][0] + 1, every[-1][1].with_name("0099_probe.sql"))]
        monkeypatch.setattr(dbmod, "_migration_files", lambda: longer)
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


def test_the_controller_sums_what_every_worker_restored(tmp_path):
    """`STATS` is a module global and every xdist worker is its own process.

    THE CONTROLLER IS THE ONLY PROCESS THAT PRINTS THE SUMMARY, and without the
    hooks this pins it counts zero, takes the early return, and the whole line --
    including the "only N restores across M tests" warning that exists to catch a
    silent 10x slowdown -- disappears under `-n`. That is the shape this file is
    about: a mechanism that breaks without ever going red.

    IT ASSERTS THE SUM AGAINST EACH FILE MEASURED ALONE, and that took three
    attempts. The first ran ONE file; under `--dist loadfile` a file is
    indivisible, so one worker got all of it and the other got nothing, and the
    controller's `STATS[key] = STATS.get(key, 0) + value` was never once executed
    against a second contribution -- `STATS[key] = value`, the natural `.update()`
    simplification, passed it five times out of five. The second ran two files and
    compared the parallel total against the same two run serially, which is still
    arithmetic: if one file stops restoring, the whole total lands on one worker
    and `parallel == serial` holds with the `+` never exercised. A gate
    demonstrated that, green 4/4 with either file in `NEVER_RESTORE`. What closes
    it is asking three separate questions -- both files really restore
    (`min(alone) > 0`), two different processes really ran them (the worker
    prefixes), and the total is their sum.

    NOT test_jobs.py, WHICH IS THE SUITE'S CONCURRENCY FILE. The first version
    used it, and it holds `threading.Barrier(2, timeout=10)` and event handshakes
    that assert one job is held while another runs -- driven from a nested pytest
    while the outer suite may be running the same file in a sibling worker.

    WORST CASE THIS TEST CREATES, SAID OUT LOUD: three nested pytest runs, one
    after another, and only the first at `-n 2` -- so under CI's own `-n 2` six
    pytest processes share the runner's two cores for the length of that one arm.
    The other two are serial and each carries half of what the combined serial arm
    used to, so the total work is roughly unchanged. That peak is the same
    oversubscription `ci.yml` removed when it went from `-n 4` to `-n 2`, and it
    is bounded to this test rather than the whole suite.

    Run as subprocesses because what is under test happens BETWEEN processes;
    there is no in-process way to ask it.
    """
    import os
    import re
    import subprocess
    import sys

    files = ["tests/test_catalog.py", "tests/test_catalog_api.py"]

    def child(*flags: str, only: "list[str] | None" = None) -> str:
        environment = {key: value for key, value in os.environ.items()
                       if key != "SCRAPEX_FULL_MIGRATIONS"}   # the alarm's own branch
        environment["SCRAPEX_DATA_ROOT"] = str(tmp_path)
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *flags,
             *(only or files)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=environment, timeout=600)
        assert run.returncode == 0, (
            f"the child pytest exited {run.returncode}, so nothing below is "
            f"about the plumbing. stderr tail: {run.stderr[-800:]!r}")
        return run.stdout

    def restored(stdout: str) -> int:
        # `re-armed` stays in the PATTERN, so a change to the summary's shape is
        # caught, and out of every ASSERTION: it counts processes that armed the
        # template, and anything rebinding `dbmod.migrate` arms it again --
        # `importlib.reload(scrapex.db)`, which tests/test_db.py already does four
        # times. A number pinned to it goes red for reasons that have nothing to
        # do with this plumbing.
        counted = re.search(r"schema template: (\d+) restored.*re-armed (\d+)x",
                            stdout)
        assert counted, (
            "the schema-template summary is missing, so the controller is "
            "counting its own empty STATS instead of the workers'. stdout "
            f"tail: {stdout[-1000:]!r}")
        return int(counted.group(1))

    # `-v -v` cancels the `-q` in addopts and then asks for a line per test, each
    # prefixed by the worker that ran it. That prefix is the only place the split
    # is observable from outside the child, and the assertion below is worth its
    # cost: `--dist loadfile` keeps a file whole but does not promise WHICH worker
    # gets it, and if both files land on one, a controller that overwrites is
    # indistinguishable from one that adds -- every remaining assertion passes.
    output = child("-n", "2", "--dist", "loadfile", "-v", "-v")
    parallel = restored(output)
    ran_on = {name: set(re.findall(rf"^\[(gw\d+)\].*{re.escape(name)}::",
                                   output, re.MULTILINE))
              for name in files}
    assert all(ran_on.values()) and not set.intersection(*ran_on.values()), (
        f"the two files ran on {ran_on}, and this arm needs one worker each so "
        "that two separate processes have a count to send. Either the run was "
        "not split or the worker prefix changed shape.")

    alone = [restored(child(only=[name])) for name in files]
    assert min(alone) > 0, (
        f"measured one at a time these files restore {alone}, so one of them "
        "pins nothing and the sum below would hold with a single contributor. "
        "Pick files that use the template.")
    assert parallel == sum(alone), (
        f"the controller summed {parallel} restores across two workers, but the "
        f"files restore {alone} = {sum(alone)} when each is measured alone. A "
        "worker's count is being dropped rather than added, which is the "
        "undercount the alarm reads.")
