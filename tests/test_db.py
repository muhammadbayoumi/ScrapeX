"""A10/S6: db layer — pragmas, migrations, the CLI write lock."""
from __future__ import annotations

import sqlite3
import os
from pathlib import Path

import pytest

from scrapex import db as dbmod


def test_connect_sets_mandated_pragmas(tmp_path: Path):
    conn = dbmod.connect(tmp_path / "t.db")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path: Path):
    conn = dbmod.connect(tmp_path / "t.db")
    try:
        first = dbmod.migrate(conn)
        second = dbmod.migrate(conn)
    finally:
        conn.close()
    # THE WHOLE CHAIN, ASKED RATHER THAN TYPED. It used to be a literal list ending
    # at 61; that number belonged to a stream retired on 2026-08-29, and a literal
    # here would have to be edited by hand every time a migration is added.
    #
    # AND IT STARTS WHERE THE BASELINE SAYS, not at 1. `range(1, ...)` was right by
    # coincidence -- `db/engine/schema.sql` happens to declare version 1 -- so the
    # assertion agreed with the code for a reason that had nothing to do with the
    # property it is about, which is that migrate() reports EVERY number it applied.
    baseline = dbmod.declared_schema_version(dbmod.SCHEMA_FILE)
    assert first == list(range(baseline, dbmod.latest_schema_version() + 1))
    assert second == []  # T4: running again applies nothing


def test_latest_schema_version_matches_the_migration_chain():
    # NOT a tautology: the left side reads the last NUMBER and the right counts the
    # FILES, so a gap or a duplicate in the chain shows up here rather than in a
    # migration that silently never runs.
    #
    # THE COUNT IS OFFSET BY THE BASELINE'S OWN VERSION. `latest == len(files)` held
    # only because the baseline declares 1; stated that way the assertion breaks the
    # moment the baseline declares anything else, and it breaks by going FALSE on a
    # correct chain -- which is the worst direction for a guard to move.
    files = dbmod._migration_files()
    baseline = dbmod.declared_schema_version(dbmod.SCHEMA_FILE)
    assert dbmod.latest_schema_version() == baseline + len(files) - 1


def test_foreign_keys_actually_enforced(tmp_path: Path):
    conn = dbmod.connect(tmp_path / "t.db")
    try:
        dbmod.migrate(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO source_product (source_id, external_product_id) VALUES (999, 'x')"
            )
    finally:
        conn.close()


def test_write_lock_blocks_second_holder(tmp_path: Path):
    db_path = tmp_path / "t.db"
    with dbmod.write_lock(db_path, timeout_s=0.1):
        with pytest.raises(dbmod.DbLockedError, match="is writing to the database"):
            with dbmod.write_lock(db_path, timeout_s=0.3):
                pass  # pragma: no cover — must not be reached


def test_two_threads_of_one_process_serialise_rather_than_refuse(tmp_path: Path):
    """The bug that made concurrent JOBS unsafe. The file lock is keyed by pid,
    and _reclaim_if_stale refuses to steal a LIVE owner's lock — so a second
    THREAD of this same runtime found a live owner (itself), waited out its whole
    timeout, and was refused, naming its own pid. Two per-host lanes whose
    ingests overlapped by more than the timeout would lose a source outright.

    An in-process gate in front of the file lock fixes it: threads of one runtime
    queue and each one holds the lock in turn — nobody is refused."""
    import threading
    import time

    db_path = tmp_path / "threads.db"
    order: list = []
    guard = threading.Lock()
    errors: list = []

    def worker(name: str) -> None:
        try:
            with dbmod.write_lock(db_path, timeout_s=10.0):
                with guard:
                    order.append(("in", name))
                time.sleep(0.15)
                with guard:
                    order.append(("out", name))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    threads = [threading.Thread(target=worker, args=(name,)) for name in "ABC"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [], f"a thread was refused its own runtime's lock: {errors}"
    # Strictly serialised: every 'in' is immediately followed by its own 'out'.
    assert len(order) == 6
    for i in range(0, len(order), 2):
        assert order[i][0] == "in" and order[i + 1][0] == "out" \
            and order[i][1] == order[i + 1][1], f"held by two at once: {order}"


def test_the_in_process_gate_still_bounds_its_wait(tmp_path: Path):
    """The gate must not hang forever: a thread that cannot get in within its
    timeout is told so, with nothing written — the same contract the file lock
    always had, so an HTTP route stays answerable."""
    import threading

    db_path = tmp_path / "gate.db"
    holding = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with dbmod.write_lock(db_path, timeout_s=5.0):
            holding.set()
            release.wait(5.0)

    thread = threading.Thread(target=holder)
    thread.start()
    assert holding.wait(5.0)
    try:
        with pytest.raises(dbmod.DbLockedError):
            with dbmod.write_lock(db_path, timeout_s=0.2):
                pass  # pragma: no cover — must not be reached
    finally:
        release.set()
        thread.join()


def test_write_lock_releases_on_exit(tmp_path: Path):
    db_path = tmp_path / "t.db"
    with dbmod.write_lock(db_path, timeout_s=0.1):
        pass
    # Immediately acquirable again:
    with dbmod.write_lock(db_path, timeout_s=0.1):
        pass
    assert not Path(str(db_path) + ".lock").exists()


def test_stale_lock_from_a_dead_process_is_reclaimed(tmp_path: Path):
    """Regression: a hard-killed runtime left a lock file that bricked every
    future crawl until someone deleted it by hand."""
    db = tmp_path / "h.db"
    lock = Path(str(db) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999999", encoding="ascii")      # a pid that cannot exist

    with dbmod.write_lock(db, timeout_s=2.0):
        assert lock.exists()                            # we now own it
        # pid:start-stamp — the stamp is what makes a RECYCLED pid detectable.
        assert lock.read_text(encoding="ascii").split(":")[0] == str(os.getpid())
    assert not lock.exists()


def test_a_live_holder_is_never_stolen_from(tmp_path: Path):
    db = tmp_path / "h.db"
    lock = Path(str(db) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="ascii")  # alive by definition

    with pytest.raises(dbmod.DbLockedError, match="is writing to the database"):
        with dbmod.write_lock(db, timeout_s=0.5):
            pass
    assert lock.exists()                                 # untouched


def test_unreadable_lock_is_left_alone(tmp_path: Path):
    db = tmp_path / "h.db"
    lock = Path(str(db) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("not-a-pid", encoding="ascii")
    with pytest.raises(dbmod.DbLockedError):
        with dbmod.write_lock(db, timeout_s=0.5):
            pass


def test_a_recycled_pid_does_not_keep_a_dead_holders_lock(tmp_path: Path):
    """The outage the owner hit: the lock names a pid, Windows recycles pids,
    and a live UNRELATED process wearing that number made the lock immortal —
    every crawl refused until a file was deleted by hand. The start stamp
    settles identity: same pid, different run, reclaim."""
    db = tmp_path / "h.db"
    lock = Path(str(db) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    # OUR pid (certainly alive) with a stamp from a different run.
    lock.write_text(f"{os.getpid()}:000000000000", encoding="ascii")

    with dbmod.write_lock(db, timeout_s=2.0):
        assert lock.read_text(encoding="ascii").split(":")[0] == str(os.getpid())
    assert not lock.exists()


def test_the_live_holders_own_lock_is_still_never_stolen(tmp_path: Path):
    """The other half: a stamp that MATCHES is a genuinely live holder."""
    db = tmp_path / "h.db"
    lock = Path(str(db) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{os.getpid()}:{dbmod._process_started_at(os.getpid())}",
                    encoding="ascii")
    with pytest.raises(dbmod.DbLockedError):
        with dbmod.write_lock(db, timeout_s=0.5):
            pass


# ---- 0047: the guard that stops a brand being dropped unseen -----------------

def test_connect_with_no_path_refuses_instead_of_opening_the_wrong_file(monkeypatch):
    """The old default was ~/.scrapex/harvest.db — NOT the warehouse, which is
    ~/.scrapex/scrapex-engine/scrapex-engine.db. So a caller that forgot its path got a
    blank database, and a WRITE would have gone into a file nothing else in the
    product reads. It happened: one settings write landed there before it was
    caught. A guess that is wrong in silence is worse than a refusal."""
    import importlib
    monkeypatch.delenv("SCRAPEX_DB_PATH", raising=False)
    fresh = importlib.reload(dbmod)
    try:
        assert fresh.DEFAULT_DB_PATH is None
        with pytest.raises(fresh.NoDatabasePathError) as caught:
            fresh.connect()
        # The message must name both files, or the reader repeats the mistake.
        assert "harvest.db" in str(caught.value)
        assert "scrapex-engine.db" in str(caught.value)
    finally:
        importlib.reload(dbmod)


def test_naming_a_path_by_env_var_is_still_honoured(monkeypatch, tmp_path):
    """Omitting a path is an accident; naming one is a decision. Only the
    accident is refused."""
    import importlib
    chosen = tmp_path / "named.db"
    monkeypatch.setenv("SCRAPEX_DB_PATH", str(chosen))
    fresh = importlib.reload(dbmod)
    try:
        assert fresh.DEFAULT_DB_PATH == chosen
        conn = fresh.connect()
        conn.close()
        assert chosen.exists()
    finally:
        monkeypatch.delenv("SCRAPEX_DB_PATH", raising=False)
        importlib.reload(dbmod)


# ---- the engine says when its database is behind, 2026-07-30 --------------

def test_pending_migrations_names_what_has_not_been_applied(tmp_path):
    """CI was green and the Data page was broken at the same moment, and both
    were right: CI builds a database from EVERY migration, so a query reading a
    new column passes there by construction, while the owner's machine had the
    code and not the migration and answered `no such column: so.weight`.

    Nothing said the database was one migration behind. A lag the engine can
    measure must not be something the owner discovers from a stack trace."""
    conn = dbmod.connect(tmp_path / "behind.db")
    try:
        # A brand new file is behind by every migration there is.
        waiting = dbmod.pending_migrations(conn)
        assert waiting, "a fresh database is behind everything"
        assert all(isinstance(n, int) and name.endswith(".sql") or name
                   for n, name in waiting)
        dbmod.migrate(conn)
        # And level once they are applied — the normal case, which must report
        # nothing at all rather than a badge that is always on screen.
        assert dbmod.pending_migrations(conn) == []
    finally:
        conn.close()


def test_pending_migrations_agrees_with_migrate(tmp_path):
    """What the guard reports must be a SUBSET of what migrate() applies, never
    a superset — the banner may under-report in an edge case, but it must never
    name a migration that will not run.

    Not equality, and the difference is the point: the legacy migrate() applies
    every file in the directory, which holds BOTH database streams, while the
    guard reports only this database's own. Asserting equality was asserting
    that the two streams are one, which is how 0013, 0014 and 0017 — General
    migrations — were announced as pending on a current MarketLens database."""
    conn = dbmod.connect(tmp_path / "agree.db")
    try:
        reported = {n for n, _name in dbmod.pending_migrations(conn)}
        applied = set(dbmod.migrate(conn))
        assert reported <= applied, (
            f"the guard named migrations migrate() never ran: "
            f"{sorted(reported - applied)}")
        assert dbmod.pending_migrations(conn) == []
    finally:
        conn.close()


def test_the_lag_guard_does_not_cry_wolf_on_a_current_database(tmp_path):
    """TWO WRONG ANSWERS, both of which announced work that was already done —
    and a guard that cries wolf is worse than no guard.

    1. Comparing filename numbers against user_version: the ledger numbers a
       migration by its POSITION in this database's stream (0057 is recorded as
       55), so a fully current database was told 0056 and 0057 were pending.
    2. Comparing filenames against the ledger: 0013, 0014 and 0017 are GENERAL
       database migrations. One directory holds both streams and the legacy
       facade cannot tell them apart, so a current database was told three
       migrations were waiting that will never apply to it.

    A fully migrated database must report NOTHING. That is the whole promise.
    """
    conn = dbmod.connect(tmp_path / "current.db")
    try:
        dbmod.migrate(conn)
        assert dbmod.pending_migrations(conn) == [], (
            "a fully migrated database was told it is behind")
    finally:
        conn.close()


def test_the_lag_guard_reports_every_migration_this_database_is_missing(tmp_path):
    """THIS ASSERTED THE OTHER DIRECTION AND THAT IS WHY IT NEVER FIRED.

    It used to check that nothing STRAY was reported — every number reported had
    to be in `_MARKETLENS_LEGACY_NUMBERS` — and never that nothing was SUPPRESSED.
    A filter can only shrink the reported set, so the old assertion could not
    fail no matter how much the filter hid, and it stayed green for as long as
    `0013` and `0014` were invisible to the banner (`OP-115`).

    Its docstring also stated the premise as fact — "the migrations directory
    holds BOTH streams" — after `R-72` had deleted the second one.
    """
    import sqlite3

    from scrapex.databases.domain import EngineDatabase

    path = tmp_path / "engine.db"
    EngineDatabase(path).initialize()
    conn = sqlite3.connect(path)
    try:
        assert dbmod.pending_migrations(conn) == [], (
            "a database built from every migration must be behind nothing")

        # Forget three, one of them on each side of the old filter's blind spot:
        # 0013 and 0014 were the suppressed pair, 0016 was always reportable.
        forgotten = []
        for prefix in ("0013", "0014", "0016"):
            row = conn.execute(
                "SELECT migration_name FROM database_migration "
                "WHERE migration_name LIKE ?", (f"{prefix}%",)).fetchone()
            assert row, f"no {prefix} migration in the ledger to forget"
            forgotten.append(row[0])
            conn.execute("DELETE FROM database_migration WHERE migration_name = ?",
                         (row[0],))
        conn.commit()

        reported = {name for _n, name in dbmod.pending_migrations(conn)}
        missing = [name for name in forgotten if name not in reported]
        assert not missing, (
            f"the banner cannot report {missing}. A migration this database has "
            "not applied and the engine will not name is the silence "
            "pending_migrations exists to break.")
    finally:
        conn.close()
