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

import atexit
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

# THE SUITE MUST NOT WRITE HIS WAREHOUSE, and this has to run before the import
# below rather than in a fixture. `scrapex/databases/registry.py` freezes
# `DATABASE_ROOT` from this variable at IMPORT time, so a fixture setting it has
# already lost: by then the constant points at `~/.scrapex`, which is where
# `databases.json` sends the panel. Observed before this line existed, during a
# full run: `~/.scrapex/engine/scrapex-engine.db-wal` at 3.0 MB with a timestamp
# inside the run, and `contractors.log` growing with it. CLAUDE.md calls a second
# writer on that warehouse a defect, and a test run was being one (#910).
#
# `if not set` rather than an unconditional assignment: a developer or a workflow
# pointing the suite somewhere deliberately keeps that choice. The default is the
# only thing that must never be his home.
if not os.environ.get("SCRAPEX_DATA_ROOT"):
    _TEST_DATA_ROOT = tempfile.mkdtemp(prefix="scrapex-tests-")
    os.environ["SCRAPEX_DATA_ROOT"] = _TEST_DATA_ROOT
    atexit.register(shutil.rmtree, _TEST_DATA_ROOT, ignore_errors=True)

from scrapex import db as dbmod
from scrapex import relaunch

# AND IT MUST NOT WRITE HIS ENGINE LOG, which the redirect above does not reach.
# `relaunch.engine_log()` is `Path.home() / ".scrapex" / "engine.log"` — no
# environment variable, no data root, no override (`scrapex/relaunch.py:145`) — and
# `open_engine_log()` is not a read: it mkdirs the parent, calls `rotate_engine_log`
# and opens the file for append (`scrapex/relaunch.py:89`). `scrapex/native.py:360`
# calls it WITH NO ARGUMENT, so a test that reaches `_spawn_engine` appends to the
# log every panel failure sends him to read, and can roll it out from under the
# engine that is running.
#
# LATENT BY LUCK, NOT BY DESIGN (#983). #961's coverage has `open_engine_log`'s body
# running while `engine_log()`'s return line never does: every caller in the suite
# happens to pass an explicit `path=`, so the `or` short-circuits before
# `Path.home()`, and the tests that do take the default branch stay safe only
# because one fixture monkeypatches `relaunch.engine_log` to `tmp_path`
# (`tests/test_native.py:491`). A convention held in one fixture is not a guard.
#
# THIS REPORTS THE ASYMMETRY, IT DOES NOT FIX IT. Teaching `engine_log()` the data
# root changes where a SHIPPED engine writes, and that is his decision rather than a
# test file's — so nothing under `scrapex/` moves and a silent write becomes a red
# test, which is the failure mode this repository prefers.


def _under(where: str, root: str) -> bool:
    return where == root or where.startswith(root + os.sep)


def _norm(path: Path | str) -> str:
    """One spelling of a path, so that two of them can be compared at all.

    `.resolve()` first: on Windows the temp directory can arrive 8.3-shortened
    (`C:\\Users\\SAPAC~1\\...`) while `Path.home()` never is, and only the filesystem
    knows those are one directory. `normcase` after it, for the part `.resolve()`
    cannot answer — a directory that does not exist YET has no true case to be
    restored to, so a `SCRAPEX_DATA_ROOT` pointing at an uncreated `DataRoot` would
    not match a caller's `DATAROOT` and a file of the test's own would be refused.
    Both are Windows facts; on Linux `normcase` is identity and two spellings
    genuinely are two directories.
    """
    return os.path.normcase(str(Path(path).resolve()))


_HIS_HOME = _norm(Path.home())
# Where a test's OWN files land — and why "under his home" cannot be the whole
# question. `tmp_path` lives under the temp directory, which on Windows is INSIDE
# the home directory (`C:\Users\<him>\AppData\Local\Temp`) and on Linux is not: a
# guard that asked only about home would be green in CI and red on the dev box for
# every correct caller in the suite.
#
# `SCRAPEX_DATA_ROOT` is exempt for the other direction. If `engine_log()` is ever
# given the data root (#983's other option, his to approve), the redirected log
# becomes a file this run made for itself and this must not then refuse it — and a
# developer who pointed the suite at a root of his own keeps that choice, the same
# way the block above honours it.
_NOT_HIS = (_norm(tempfile.gettempdir()), _norm(os.environ["SCRAPEX_DATA_ROOT"]))


def _is_his(target: Path) -> bool:
    """A file the owner reads, rather than a copy this run made for itself.

    "His directories" is also decided in `tests/test_the_suite_writes_nothing_of_his.py:39`
    (`~/.scrapex`, `~/ScrapeX`), and the two stay apart rather than merge. That file
    asks which module CONSTANTS point into a directory of his and can therefore name
    them; this asks where one CALL is about to write, and the answer has to cover a
    path nobody listed — `open_engine_log(Path.home() / "engine.log")` is his home
    just as much. Merging them would also mean conftest importing a test module at
    import time, or a test module importing conftest under a second name.
    """
    where = _norm(target)
    return _under(where, _HIS_HOME) and not any(_under(where, mine) for mine in _NOT_HIS)


_REAL_OPEN_ENGINE_LOG = relaunch.open_engine_log


def _guarded_open_engine_log(path=None):
    """`relaunch.open_engine_log`, with his own log taken off the table.

    `path or relaunch.engine_log()` mirrors `scrapex/relaunch.py:91` exactly, the
    module-global lookup included: a test that redirects `relaunch.engine_log` to
    `tmp_path` — which is how the suite reaches that branch at all — has to be
    judged on the file it actually redirected to, not on the shipped default. The
    argument is handed on untouched, so a caller that is allowed through gets the
    real function's own resolution and not ours.

    `pytest.fail` rather than an error of our own, BECAUSE THE CALLERS CATCH:
    `relaunch._spawn_detached` wraps this call in `except OSError` and falls back
    to a sibling file, and `scrapex/native.py` answers the panel out of an
    `except Exception`. Either would turn a refusal into a quiet fallback and leave
    the run green, which is the failure mode this exists to end. `Failed` derives
    from BaseException and passes through both.
    """
    target = path or relaunch.engine_log()
    if _is_his(target):
        pytest.fail(
            f"a test called relaunch.open_engine_log() on {target} — his own engine "
            f"log, the file every panel failure tells him to open. It would have "
            f"been appended to, and rotate_engine_log can roll it aside under the "
            f"running engine. `engine_log()` reads no environment variable, so "
            f"conftest's SCRAPEX_DATA_ROOT redirect does not reach it (#983): pass "
            f"an explicit `path=` under tmp_path, or monkeypatch "
            f"`relaunch.engine_log` the way tests/test_native.py:491 does.")
    return _REAL_OPEN_ENGINE_LOG(path)


relaunch.open_engine_log = _guarded_open_engine_log

# THE OTHER DOOR IN THE SAME MODULE, and the more destructive of the two.
# `rotate_engine_log` carries the identical `target = path or engine_log()`
# (scrapex/relaunch.py:77) and does not append: it unlinks the kept copy and
# RENAMES the live log (`:82-83`). Wrapping only the opener left a call with no
# argument free to roll his log aside -- demonstrated by an adversary against
# the first version of this guard, which stayed silent through it. Appending is
# dirty; renaming the file every panel failure tells him to open is destructive,
# and it leaves no trace except a log that is no longer there.
ENGINE_LOG_KEEP_SUFFIX = getattr(relaunch, "ENGINE_LOG_KEEP", 1)
_REAL_ROTATE_ENGINE_LOG = relaunch.rotate_engine_log


def _guarded_rotate_engine_log(path=None):
    """`relaunch.rotate_engine_log`, with his own log taken off the table.

    Same shape as the opener above and for the same reasons: the module-global
    lookup so a redirected `engine_log` is judged on what it was redirected to,
    the argument handed on untouched, and `pytest.fail` because this caller
    catches too -- `rotate_engine_log` swallows `OSError` itself (`:85`), so an
    error of our own would become its `return False` and leave the run green.
    """
    target = path or relaunch.engine_log()
    if _is_his(target):
        pytest.fail(
            f"a test called relaunch.rotate_engine_log() on {target} — his own "
            f"engine log. It would have been RENAMED to {target.name}."
            f"{ENGINE_LOG_KEEP_SUFFIX} and the previous copy deleted, under a "
            f"running engine, leaving nothing behind to say so. `engine_log()` "
            f"reads no environment variable, so conftest's SCRAPEX_DATA_ROOT "
            f"redirect does not reach it (#983): pass an explicit `path=` under "
            f"tmp_path, or monkeypatch `relaunch.engine_log`.")
    return _REAL_ROTATE_ENGINE_LOG(path)


relaunch.rotate_engine_log = _guarded_rotate_engine_log

# AND IT ANSWERS ITS TWO QUESTIONS BEFORE THE FIRST TEST RUNS, once per worker.
# Nothing in the suite calls `open_engine_log` on a file of his — that is the
# point of the guard — so no test can go red when the predicate above stops
# telling his log apart from a temporary one: measured, the whole suite returns
# the identical 4111 outcomes with this block present and with it deleted. A
# guard that nothing can notice failing is the failure mode this repository
# keeps finding, so it is asked both questions here, on paths that are NEVER
# opened and whose parents are never created.
#
# Not the third question, deliberately: whether the line above is still wired
# cannot be asked here, because asking it means CALLING the opener, and on a
# conftest where the line was deleted that call is the write. That one belongs
# in a test file, where a monkeypatched `relaunch.engine_log` makes it safe.
_GUARD_PROBE = Path.home() / "__scrapex_engine_log_guard_probe__" / "engine.log"
_TMP_PROBE = Path(tempfile.gettempdir()) / "pytest-of-someone" / "test_0" / "engine.log"
if not _is_his(_GUARD_PROBE):
    raise RuntimeError(
        f"the engine-log guard has stopped recognising {_GUARD_PROBE} as a file "
        f"of his, so it would let a test write ~/.scrapex/engine.log (#983). "
        f"Either `_is_his` is broken, or SCRAPEX_DATA_ROOT "
        f"({os.environ['SCRAPEX_DATA_ROOT']}) or the temp directory "
        f"({tempfile.gettempdir()}) now sits at or above {Path.home()}, which "
        f"exempts his whole home.")
if _is_his(_TMP_PROBE):
    raise RuntimeError(
        f"the engine-log guard now refuses {_TMP_PROBE}, which is where every "
        f"correct caller in the suite writes (tmp_path). It would fail "
        f"tests/test_relaunch_log.py and tests/test_native.py rather than the "
        f"defect it is looking for (#983).")

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


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Hand this worker's restore counts to the controller.

    UNDER `pytest-xdist` THE SUMMARY BELOW CANNOT PRINT WITHOUT THIS. `STATS` is
    a module global, and every worker is a separate process with its own copy; the
    controller -- the only process that runs `pytest_terminal_summary` -- counts
    zero and returns early, so the line disappears at exactly the moment the suite
    gets harder to watch. `#654` calls this the measurement regression that should
    be decided rather than discovered; this is the decision.

    IT RESTORES THE LOCAL RUN, NOT CI, and that is worth saying rather than
    leaving to be read. CI's only pytest run that collects more than 1000 tests
    carries `SCRAPEX_FULL_MIGRATIONS=1` on its step, which takes the DISABLED
    branch below and returns before the line AND before the red WARNING under it.
    So that warning has been unreachable in CI since #851, whatever xdist does --
    #862 holds that finding and its options, and this hook neither closes it nor
    depends on it.

    `workeroutput` exists only inside a worker, so this does nothing serially.
    """
    output = getattr(session.config, "workeroutput", None)
    if output is not None:
        output["scrapex_schema_stats"] = dict(STATS)


def pytest_testnodedown(node, error) -> None:          # `error` is xdist's signature
    """Controller side: add a finished worker's counts to ours.

    Defined unconditionally because `pytest-xdist` is a `[dev]` dependency. If it
    is ever removed, pytest rejects this hook by name at startup rather than
    silently ignoring it, which is the failure mode worth having.
    """
    got = (getattr(node, "workeroutput", None) or {}).get("scrapex_schema_stats")
    if got:
        for key, value in got.items():
            STATS[key] = STATS.get(key, 0) + value


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
