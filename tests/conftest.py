"""One migrated template database, restored per test instead of rebuilt.

WHY THIS FILE EXISTS (2026-07-31)
---------------------------------
The suite took ~90 minutes because 114 call sites across 57 files each ran
`dbmod.migrate()` inside a FUNCTION-scoped fixture. Nothing was wrong with any of
them individually; the cost is that `migrate()` replays 57 files / 616 statements
every time, and 74 of those statements are `ALTER TABLE` (36 `RENAME COLUMN`).
SQLite re-parses the whole schema DDL per rename, so that is 93-97% of the SQL
time and it is SQLite working as designed — not a pathology to fix.

Measured on the owner's box:

    dbmod.migrate()                          ~1900 ms
    shutil.copyfile of the migrated file       17.8 ms
    template_conn.backup(target)               25.4 ms
    full suite, before                     ~90 min (estimated, never cleanly timed)
    full suite, with this file               6m18s (measured)

`backup()` is the primitive rather than `copyfile` because every one of those 114
sites already holds an OPEN connection when it calls `migrate()`. Restoring into
that connection is what lets this file speed the suite up without editing a single
test. Fidelity was verified rather than assumed: user_version, application_id, all
50 tables, 86 indexes, 18 triggers (including the A7 append-only pair), 2 views,
integrity_check, foreign_key_check and both seed rows are identical to a freshly
migrated database.

Options that were measured and rejected: storage pragmas (`synchronous=OFF`,
`journal_mode=MEMORY`) bought 0% and were marginally SLOWER; one transaction for
all 57 bought 5%; squashing to a v57 baseline bought a lot but deletes the upgrade
path T5 exists to check.

THREE THINGS HERE ARE LOAD-BEARING. Each was found by breaking a version without
it, and two of them fail SILENTLY, which is why they are commented at length.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scrapex import db as dbmod

# Captured at import — before any test module can rebind them. `tests/conftest.py`
# is imported before every test module, so these are the shipped originals.
_REAL_MIGRATE = dbmod.migrate


def _stream_fingerprint() -> tuple[tuple[int, str], ...]:
    """What the migration stream IS right now — by content, never by identity.

    The obvious guard, `dbmod._migration_files is not _THE_ORIGINAL`, is WRONG
    here and fails in the silent direction. `tests/test_db.py:346` calls
    `importlib.reload(scrapex.db)`, which installs a NEW function object that
    behaves identically — so an identity check turns into a permanent veto for
    the rest of the session and every later test quietly pays full price again.
    That is the same failure as an unpatched reload wearing a different mask.

    Comparing the resolved list catches what actually matters (a truncated,
    reordered or repointed stream) and is blind to which object produced it.
    """
    return tuple((number, str(path)) for number, path in dbmod._migration_files())


_REAL_STREAM: tuple[tuple[int, str], ...] = ()

# LOAD-BEARING #3: the one file whose SUBJECT is migrate() itself.
#
# This is NOT a rot-prone blocklist standing in for a predicate — every other file
# in the suite is protected by `_may_restore` below. test_db.py is here because two
# of its tests assert on migrate()'s RETURN VALUE on a pristine connection, which no
# predicate can distinguish from an ordinary caller. Proven by injecting a real
# defect into migrate() (correct schema, under-reports the last applied number):
#
#                                                  defect, no restore | with restore
#   test_migrate_is_idempotent                            FAILED      |   passed
#   test_pending_migrations_agrees_with_migrate            FAILED      |   passed
#
# A synthetic [1..57] equals `pending_migrations()` on a fresh database by
# construction, so the assertion becomes a tautology and the test stops testing.
# Anything added to this set needs the same standard of evidence.
NEVER_RESTORE = frozenset({"test_db"})

_TEMPLATE_DIR: Path | None = None
_TEMPLATE_CONN: sqlite3.Connection | None = None
_TEMPLATE_UV = 0
_TEMPLATE_APPLIED: list[int] = []

# CI is the authority on green, and it runs on Linux where neither of this box's
# pathologies exists (an AV-scanned CA file load, a resident process eating a
# core). Setting this makes the suite byte-for-byte what it was before this file
# existed, so "the fast suite might hide something" has a definitive answer rather
# than an argument: .github/workflows/ci.yml runs the real 57-file stream 805
# times on every push, and the developer's inner loop does not.
_FULL_MIGRATIONS = bool(os.environ.get("SCRAPEX_FULL_MIGRATIONS"))

# A broken re-arm or a mis-firing predicate does not turn anything red — it just
# makes the suite slow again, which is exactly the failure nobody notices until
# an afternoon is gone. A full run restores ~759 times; anything near zero after a
# whole-suite run means this file has quietly stopped working.
_EXPECT_RESTORES_OVER = 500

# Exposed so tests/test_fast_migrations.py can pin this file's behaviour (Q8: a
# workaround ships with a test pinning it). Not read by anything in scrapex/.
STATS: dict[str, float] = {"restored": 0, "real": 0, "rearmed": 0, "restore_s": 0.0}

_bypass = {"on": False}


def _build_template() -> None:
    """Run the REAL migrate once, then hold the result open for restoring."""
    global _TEMPLATE_DIR, _TEMPLATE_CONN, _TEMPLATE_UV, _REAL_STREAM
    _TEMPLATE_DIR = Path(tempfile.mkdtemp(prefix="scrapex-schema-template-"))
    path = _TEMPLATE_DIR / "template.db"

    _REAL_STREAM = _stream_fingerprint()
    conn = dbmod.connect(path)
    # Keep what the real migrate ACTUALLY returned rather than synthesising it
    # later. The numbers happen to be contiguous today, so `range(1, uv + 1)`
    # would agree — but nothing enforces that, and an observed value cannot
    # drift from the thing it describes.
    _TEMPLATE_APPLIED[:] = _REAL_MIGRATE(conn)
    _TEMPLATE_UV = dbmod.schema_version(conn)
    # LOAD-BEARING #1: CLOSE IT. `dbmod.connect` sets `PRAGMA journal_mode = WAL`,
    # so until the last connection closes the migrations live in template.db-wal
    # and template.db itself is ONE PAGE. Reading the file while this connection
    # was open produced a database with 0 tables reporting `user_version = 0` —
    # which every caller here would read as "pristine" and happily hand to a test.
    # Closing checkpoints the WAL into the file. (`PRAGMA wal_checkpoint(TRUNCATE)`
    # also works; closing is simpler and we want a read-only handle anyway.)
    conn.close()

    _TEMPLATE_CONN = sqlite3.connect(str(path), check_same_thread=False)


def _is_pristine(conn: sqlite3.Connection) -> bool:
    if int(conn.execute("PRAGMA user_version").fetchone()[0]) != 0:
        return False
    return conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def _may_restore(conn: sqlite3.Connection) -> bool:
    if _bypass["on"] or _TEMPLATE_CONN is None:
        return False

    # The stream must be the STOCK one. tests/test_db.py:204 `_at_version_46`
    # monkeypatches `_migration_files` to truncate history and replay it; a
    # restore would hand it v57 instead of v46. Three of the four tests it guards
    # fail loudly only by luck — they happen to name a column a later migration
    # renamed. One that didn't would pass against the wrong schema.
    if _stream_fingerprint() != _REAL_STREAM:
        return False

    # The target must be EMPTY. `migrate()` on a partly-migrated or populated
    # database is an UPGRADE and `backup()` would discard its rows. This guard is
    # the only thing catching the three helpers that hand-replay a migration
    # prefix on the stock stream and then upgrade over it:
    #   tests/test_schema.py:158            "the pre-0020 warehouse"
    #   tests/test_display_method_and_quantity_facts.py:556  "the pre-0056 warehouse"
    #   tests/test_the_weight_the_price_is_quoted_against.py:546 "the pre-0057 one"
    # It is load-bearing, not belt-and-braces: with it removed those three fail.
    if not _is_pristine(conn):
        return False

    # No open transaction. A destination inside a write txn raises
    # "destination database is in use"; a SOURCE inside one HANGS FOREVER with no
    # exception (killed at 75s in testing). Measured: 0 of the 114 sites hit this,
    # so this is a guard against a future caller, not a current one.
    return not conn.in_transaction


def _fast_migrate(conn: sqlite3.Connection) -> list[int]:
    """`dbmod.migrate` with the 57-file replay swapped for a template restore."""
    if not _may_restore(conn):
        STATS["real"] += 1
        # Whatever is installed now — an importlib.reload may have replaced the
        # original object, and the reloaded one is the one the test wants.
        return getattr(dbmod, "_conftest_real_migrate", _REAL_MIGRATE)(conn)

    import time

    started = time.perf_counter()
    _TEMPLATE_CONN.backup(conn)
    # migrate() ends by stamping the contract version. The template carries the
    # stamp already, but re-stamping costs nothing and keeps this faithful even if
    # a test has monkeypatched the contract constants.
    from scrapex.contract import stamp_contract

    with conn:
        stamp_contract(conn)
    STATS["restored"] += 1
    STATS["restore_s"] += time.perf_counter() - started
    return list(_TEMPLATE_APPLIED)


def _arm() -> None:
    if dbmod.migrate is not _fast_migrate:
        # LOAD-BEARING #2: tests/test_db.py:346,355,364,372 call
        # `importlib.reload(scrapex.db)`, which re-execs the module in place and
        # rebinds EVERY attribute — including `migrate`, back to the real one. A
        # patch installed once at pytest_configure dies there, silently, for the
        # rest of the session. test_db.py is file 21 of 87 in collection order and
        # 41 of the 57 migrate-calling files sort after it, so ~72% of the suite
        # quietly reverted to full cost. Proven with the same 25 tests reversed:
        #   test_archive.py then test_db.py  -> restored=4
        #   test_db.py then test_archive.py  -> restored=0
        # Re-arming per test is what makes this file's saving real.
        dbmod._conftest_real_migrate = dbmod.migrate
        dbmod.migrate = _fast_migrate
        STATS["rearmed"] += 1


@pytest.fixture(scope="session")
def schema_template():
    """This file's own state, for tests/test_fast_migrations.py to pin.

    A fixture and not an import: pytest owns this module's identity, and
    `from tests import conftest` would build a SECOND module object with its own
    globals — the tests would then be asserting about a template that never
    served anybody, and would pass while the real one was broken.
    """
    return SimpleNamespace(
        dir=_TEMPLATE_DIR,
        conn=_TEMPLATE_CONN,
        applied=list(_TEMPLATE_APPLIED),
        user_version=_TEMPLATE_UV,
        stream=_REAL_STREAM,
        stats=STATS,
        disabled=_FULL_MIGRATIONS,
        real_migrate=_REAL_MIGRATE,
        fast_migrate=_fast_migrate,
        may_restore=_may_restore,
        fingerprint=_stream_fingerprint,
        never_restore=NEVER_RESTORE,
        arm=_arm,
    )


def pytest_configure(config: pytest.Config) -> None:
    if _FULL_MIGRATIONS:
        return
    _build_template()
    _arm()


def pytest_runtest_setup(item: pytest.Item) -> None:
    if _FULL_MIGRATIONS:
        return
    _arm()
    # Helper modules are imported under two names in this suite (`test_ingest` and
    # `tests.test_ingest`, because 28 files do `from tests.test_ingest import ...`),
    # so compare on the bare module name.
    module = getattr(item, "module", None)
    name = module.__name__.rsplit(".", 1)[-1] if module else ""
    _bypass["on"] = name in NEVER_RESTORE


def pytest_terminal_summary(terminalreporter) -> None:
    if _FULL_MIGRATIONS:
        terminalreporter.write_line(
            "schema template: DISABLED (SCRAPEX_FULL_MIGRATIONS) — every "
            "migrate() ran for real")
        return
    if not (STATS["restored"] or STATS["real"]):
        return
    each = STATS["restore_s"] / max(1, STATS["restored"])
    terminalreporter.write_line(
        f"schema template: {STATS['restored']:.0f} restored "
        f"({each*1000:.1f}ms each), {STATS['real']:.0f} real migrations, "
        f"re-armed {STATS['rearmed']:.0f}x")
    # Whole-suite run that barely restored anything = this file has silently
    # stopped working. Say so; do not let it pass for a slow afternoon.
    ran = terminalreporter._session.testscollected
    if ran > 1000 and STATS["restored"] < _EXPECT_RESTORES_OVER:
        terminalreporter.write_line(
            f"  WARNING: only {STATS['restored']:.0f} restores across {ran} tests "
            f"(expected >{_EXPECT_RESTORES_OVER}). The template is being bypassed "
            f"— check the re-arm hook and _may_restore().", red=True)


def pytest_unconfigure(config: pytest.Config) -> None:
    # Windows will not remove the directory while the handle is open.
    global _TEMPLATE_CONN
    if _TEMPLATE_CONN is not None:
        _TEMPLATE_CONN.close()
        _TEMPLATE_CONN = None
    if _TEMPLATE_DIR is not None:
        import shutil

        shutil.rmtree(_TEMPLATE_DIR, ignore_errors=True)


@pytest.fixture()
def one_migration_above_the_baseline(tmp_path_factory, monkeypatch):
    """Make "behind, but ABOVE the baseline" reachable at all.

    `R-84`'s squash collapsed the chain into `db/engine/schema.sql`, so the plan is a
    single file and `baseline == latest`. Every version below the head is therefore
    also below the BASELINE, and `EngineDatabase.health()`'s "Needs upgrade" branch
    cannot be reached by rewinding a version: three tests that rewound by one
    believed they were exercising it and were exercising the refusal instead. One
    real migration above the baseline makes both branches exist.

    `conftest`'s schema template steps aside on its own here -- `_may_restore`
    refuses when `_stream_fingerprint()` no longer matches the stock stream, which
    is exactly what monkeypatching the migrations folder changes.

    Yields the version the extra migration takes a database to.
    """
    from scrapex import db as dbmod

    folder = tmp_path_factory.mktemp("above-the-baseline")
    head = dbmod.declared_schema_version(dbmod.SCHEMA_FILE) + 1
    (folder / f"{head:04d}_a_column_lands_above_the_baseline.sql").write_text(
        "ALTER TABLE crawl_job ADD COLUMN a_column_above_the_baseline INTEGER;\n"
        f"PRAGMA user_version = {head};\n", encoding="utf-8")
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", folder)
    yield head
