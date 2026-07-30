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
    assert first == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57]
    assert second == []  # T4: running again applies nothing


def test_latest_schema_version_matches_the_migration_chain():
    assert dbmod.latest_schema_version() == 57   # +0057 the weight the price is quoted against


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

def _at_version_46(monkeypatch) -> sqlite3.Connection:
    """A warehouse one migration short of the brand split, on the REAL stream."""
    every = dbmod._migration_files()
    monkeypatch.setattr(dbmod, "_migration_files",
                        lambda: [f for f in every if f[0] <= 46])
    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    monkeypatch.setattr(dbmod, "_migration_files", lambda: every)
    return conn


def _seed_branded_product(conn, *, source_key: str, brand_raw: str,
                          manufacturer: str | None = None) -> None:
    conn.execute(
        # The column's name AT v46, which is where this fixture stands: 0055
        # renames it to default_tax_mode, and these tests replay the stream to a
        # point before that. Using today's name here would test a database that
        # never existed.
        "INSERT INTO source_site (source_key, source_name, source_name_ar, "
        "default_vat_mode, authority, active) VALUES (?,?,?,?,?,1)",
        (source_key, source_key.title(), source_key, "excl", "official"))
    source_id = conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                             (source_key,)).fetchone()[0]
    conn.execute(
        "INSERT INTO source_product (source_id, external_product_id, brand_raw, "
        "has_variants, curation_status, first_seen_at, last_seen_at, status, "
        "category_path_ar, category_external_id, product_name, product_name_lang, "
        "category_path, parent_sku) "
        "VALUES (?,?,?,0,'inventoried','2026-07-28','2026-07-28','active','','','p','en','','')",
        (source_id, "P-1", brand_raw))
    if manufacturer is not None:
        product_id = conn.execute(
            "SELECT source_product_id FROM source_product WHERE external_product_id = 'P-1'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO source_product_attribute (source_product_id, attribute_code, "
            "attribute_label, raw_value, numeric_value, unit_raw, value_url, "
            "attribute_group, lang, first_seen_at, last_seen_at, is_site_filter) "
            "VALUES (?,'manufacturer','Manufacturer',?,0,'','','detail','en',"
            "'2026-07-28','2026-07-28',0)",
            (product_id, manufacturer))
    conn.commit()


def test_a_brand_no_split_statement_covers_stops_the_migration(monkeypatch):
    """0047's split statements are generated from a SNAPSHOT, so a brand first
    crawled after the file was written matches none of them — and brand_raw is
    dropped at the end. The guard turns that silent loss into a failed
    migration, which is the owner's rule: nothing published is ever discarded
    without saying so."""
    conn = _at_version_46(monkeypatch)
    try:
        _seed_branded_product(conn, source_key="ALSWEED", brand_raw="علامة جديدة BRANDNEW")
        with pytest.raises(sqlite3.IntegrityError):
            dbmod.migrate(conn)
    finally:
        conn.close()


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN AND DELIBERATELY UNFIXED. 0047 is an applied migration: its sha256 is "
    "recorded in database_migration and verified on EVERY connection, so editing "
    "one byte of it stops the owner's engine starting, and the codebase has no "
    "re-stamp path (no UPDATE or DELETE against that ledger exists anywhere). "
    "The blind spot is also unreachable: it needs a row with a non-empty "
    "brand_raw that the MADAR promotion blanked, the promotion is scoped to "
    "MADAR alone, and MADAR published no brand_raw at all (0047 header, and 0 "
    "such rows in the real pre-0047 warehouse). Replaying 0047 over that "
    "warehouse with and without the fix gives an identical result — 2503 brands "
    "either way. So this is recorded, not repaired: if a future migration ever "
    "makes the shape reachable, fix it THERE. If this test starts passing, the "
    "predicate changed underneath us and strict= will say so."))
def test_the_guard_is_blind_to_a_brand_the_madar_promotion_emptied(monkeypatch):
    """The blind spot, pinned rather than fixed.

    The MADAR promotion wraps both its writes in COALESCE(..., ''), so a row it
    touched holds '' and never NULL — and the guard tests `IS NULL`. It cannot
    see the one row it exists to catch. The corrected predicate is
    empty-or-null; see the reason above for why it does not live in the file.
    """
    conn = _at_version_46(monkeypatch)
    try:
        _seed_branded_product(conn, source_key="MADAR",
                              brand_raw="علامة جديدة BRANDNEW", manufacturer="")
        with pytest.raises(sqlite3.IntegrityError):
            dbmod.migrate(conn)
    finally:
        conn.close()


def test_the_madar_promotion_cannot_blank_another_sources_brand(monkeypatch):
    """Why the blind spot above stays unreachable, asserted on the SQL itself.

    The promotion is the only statement in 0047 that can leave a row with an
    EMPTY brand rather than a NULL one. It is scoped to MADAR by source_key, so
    no other source can ever be pushed into the guard's blind spot — which is
    what makes recording the defect the right response instead of editing an
    applied migration.
    """
    text = (dbmod.MIGRATIONS_DIR /
            "0047_the_brand_says_which_language_it_is_in.sql").read_text(encoding="utf-8")
    promotion = text.split("-- MADAR's brand", 1)[1].split(";", 1)[0]
    assert "source_key = 'MADAR'" in promotion, \
        "the promotion is no longer scoped to MADAR — the guard's blind spot may now be reachable"

    # ...and a non-MADAR row with an uncovered brand still stops the migration,
    # because nothing blanked it: it is NULL, which the shipped guard does see.
    conn = _at_version_46(monkeypatch)
    try:
        _seed_branded_product(conn, source_key="ALSWEED",
                              brand_raw="علامة أخرى OTHERBRAND", manufacturer="x")
        with pytest.raises(sqlite3.IntegrityError):
            dbmod.migrate(conn)
    finally:
        conn.close()


def test_a_brand_the_promotion_fills_is_not_reported_as_lost(monkeypatch):
    """The other half: a MADAR row whose manufacturer attribute HAS a value is
    covered, not uncovered. A guard that fired here would block every upgrade."""
    conn = _at_version_46(monkeypatch)
    try:
        _seed_branded_product(conn, source_key="MADAR",
                              brand_raw="اسمنت الرياض", manufacturer="Riyadh Cement")
        dbmod.migrate(conn)
        assert conn.execute(
            "SELECT brand FROM source_product WHERE external_product_id = 'P-1'"
        ).fetchone()[0] == "Riyadh Cement"
    finally:
        conn.close()


# ---- the default path stopped guessing, 2026-07-30 ------------------------

def test_connect_with_no_path_refuses_instead_of_opening_the_wrong_file(monkeypatch):
    """The old default was ~/.scrapex/harvest.db — NOT the warehouse, which is
    ~/.scrapex/marketlens/marketlens.db. So a caller that forgot its path got a
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
        assert "marketlens.db" in str(caught.value)
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
    """The two must never disagree: what migrate() would apply is exactly what
    pending_migrations() reports, or the banner lies in one direction or the
    other."""
    conn = dbmod.connect(tmp_path / "agree.db")
    try:
        expected = [n for n, _name in dbmod.pending_migrations(conn)]
        applied = dbmod.migrate(conn)
        assert applied == expected
    finally:
        conn.close()
