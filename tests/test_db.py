"""A10/S6: db layer — pragmas, migrations, the CLI write lock."""
from __future__ import annotations

import sqlite3
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
    assert first == [1]
    assert second == []  # T4: running again applies nothing


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
        with pytest.raises(dbmod.DbLockedError, match="delete the file"):
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
