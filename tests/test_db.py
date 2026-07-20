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
    assert first == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    assert second == []  # T4: running again applies nothing


def test_latest_schema_version_matches_the_migration_chain():
    assert dbmod.latest_schema_version() == 14


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
        assert lock.read_text(encoding="ascii").strip() == str(os.getpid())
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
