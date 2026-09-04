"""The runner's two new behaviours around a squashed baseline, and their refusals.

`R-84` collapsed the engine chain into `db/engine/schema.sql`. That makes two things
true that were not true before, and each needs its own guard because each fails in a
different direction:

  1. EVERY EXISTING DATABASE reports the baseline's digest as changed, because it did
     change. Recognising that is necessary and is also the most dangerous kind of
     exception to add to a checksum, so the conditions are tested one at a time --
     each test below removes exactly one and shows the refusal come back.
  2. A DATABASE BELOW THE BASELINE has no upgrade path. The loop in `_migrate` applies
     any migration numbered above the current version, so a baseline at the head would
     replay 51 `CREATE TABLE` statements with no `IF NOT EXISTS` over a populated
     database. Refusing with a sentence is the whole difference between that and a
     crash on every launch.

WHAT MAKES THESE TESTS REAL RATHER THAN CIRCULAR: the pre-squash database is built
from the chain as it existed on `origin/main`, recovered from git into a temporary
directory, and then opened with the shipped code. Nothing is simulated by writing a
digest by hand.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.databases.domain import (
    DatabaseMigrationError,
    EngineDatabase,
    Migration,
)

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "db" / "engine" / "squashed-from.json"

pytestmark = pytest.mark.skipif(
    not RECORD.is_file(),
    reason="this baseline was never squashed, so there is nothing to reconcile")


def _git(*args: str) -> bytes:
    # Not text=True: the locale codec mangles anything outside Latin-1, and these
    # blobs carry Arabic comments.
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          check=True).stdout


@pytest.fixture(scope="module")
def pre_squash_chain(tmp_path_factory) -> tuple[Path, Path] | None:
    """`origin/main`'s baseline and migrations, on disk — or None if unavailable.

    A shallow clone or a detached CI checkout may not have the ref. That is a reason
    to skip, not to invent a fixture: the point of these tests is a REAL pre-squash
    database.
    """
    folder = tmp_path_factory.mktemp("chain")
    try:
        names = _git("ls-tree", "--name-only",
                     "origin/main:db/engine/migrations").decode().split()
        baseline = folder / "schema.sql"
        baseline.write_bytes(_git("show", "origin/main:db/engine/schema.sql"))
    except subprocess.CalledProcessError:
        return None
    if not names:
        return None
    migrations = folder / "migrations"
    migrations.mkdir()
    for name in names:
        (migrations / name).write_bytes(
            _git("show", f"origin/main:db/engine/migrations/{name}"))
    return baseline, migrations


def _build_pre_squash(path: Path, chain: tuple[Path, Path], monkeypatch) -> None:
    baseline, migrations = chain
    monkeypatch.setattr(dbmod, "SCHEMA_FILE", baseline)
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", migrations)
    db = EngineDatabase(path)
    db._migrations = tuple(Migration(n, p) for n, p in dbmod._migration_files())
    db.initialize()
    monkeypatch.undo()


@pytest.fixture
def pre_squash_database(pre_squash_chain, tmp_path, monkeypatch) -> Path:
    if pre_squash_chain is None:
        pytest.skip("origin/main's pre-squash chain is not reachable in this checkout")
    path = tmp_path / "warehouse.db"
    _build_pre_squash(path, pre_squash_chain, monkeypatch)
    return path


def test_a_database_that_went_through_the_chain_opens(pre_squash_database):
    """THE ONE THAT MATTERS: his warehouse.

    Before the reconciliation, measured on this exact fixture: `connect()` raised
    "migration schema.sql checksum changed; restore the original migration file and
    retry" and `health()` answered "Integrity check failed" about a database with
    nothing wrong with it.
    """
    db = EngineDatabase(pre_squash_database)
    db.connect().close()
    assert db.initialize() == []
    health = db.health()
    assert health.ok, f"{health.status}: {health.action}"
    assert health.schema_version == db.latest_schema_version


def test_the_ledger_is_upgraded_once_and_then_it_is_ordinary(pre_squash_database):
    """Accepted on read, upgraded on stamp — the arrangement `legacy_sha256` already
    has. After one initialize the stored digest is the new baseline's, so nothing
    downstream has to know a squash ever happened."""
    db = EngineDatabase(pre_squash_database)
    db.initialize()
    conn = sqlite3.connect(str(pre_squash_database))
    try:
        stored = conn.execute(
            "SELECT sha256 FROM database_migration WHERE migration_name = 'schema.sql'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert stored == db._migrations[0].sha256


def test_a_database_at_the_version_but_without_the_chain_is_refused(tmp_path):
    """The condition that stops this being a disabled checksum.

    A database can claim the baseline's version without ever having applied what the
    baseline absorbed — a hand-set `user_version`, a restored fragment. It must not be
    excused just because the number matches.
    """
    path = tmp_path / "claims.db"
    db = EngineDatabase(path)
    db.initialize()
    conn = sqlite3.connect(str(path))
    try:
        # Wear the OLD baseline's digest, but hold none of the absorbed chain.
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        old = {name: digest for _n, name, digest in record["absorbed"]}["schema.sql"]
        conn.execute("DELETE FROM database_migration WHERE migration_name <> 'schema.sql'")
        conn.execute("UPDATE database_migration SET sha256 = ? "
                     "WHERE migration_name = 'schema.sql'", (old,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseMigrationError, match="checksum changed"):
        EngineDatabase(path).connect()


def test_an_unknown_digest_is_still_refused(pre_squash_database):
    """It accepts ONE digest — the one the record says the replaced baseline had — and
    not any digest that happens to differ."""
    conn = sqlite3.connect(str(pre_squash_database))
    try:
        conn.execute("UPDATE database_migration SET sha256 = ? "
                     "WHERE migration_name = 'schema.sql'", ("0" * 64,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseMigrationError, match="checksum changed"):
        EngineDatabase(pre_squash_database).connect()


def test_a_database_below_the_baseline_is_refused_and_not_replayed(
        pre_squash_chain, tmp_path, monkeypatch):
    """`R-84`'s consequence, and the refusal has to say what to do instead.

    The database is left exactly as it was: the whole point is that the alternative
    was a crash after a 2 GB backup on every launch.
    """
    if pre_squash_chain is None:
        pytest.skip("origin/main's pre-squash chain is not reachable in this checkout")
    baseline, migrations = pre_squash_chain
    path = tmp_path / "behind.db"
    monkeypatch.setattr(dbmod, "SCHEMA_FILE", baseline)
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", migrations)
    behind = EngineDatabase(path)
    whole = tuple(Migration(n, p) for n, p in dbmod._migration_files())
    stop = max(2, len(whole) // 2)
    behind._migrations = whole[:stop]
    behind.initialize()
    monkeypatch.undo()

    conn = sqlite3.connect(str(path))
    try:
        was = int(conn.execute("PRAGMA user_version").fetchone()[0])
        objects = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert was == whole[stop - 1].number

    with pytest.raises(DatabaseMigrationError, match="no upgrade path"):
        EngineDatabase(path).initialize()

    conn = sqlite3.connect(str(path))
    try:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == was, (
            "the refused database's version moved")
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchone()[0] == objects, "the refused database's schema was touched"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_the_refusal_says_what_to_do_and_names_no_terminal_command(
        pre_squash_chain, tmp_path, monkeypatch):
    """`R-81`: a surface that prints a runnable command is answering a machine he does
    not sit at. The message names the ACTIONS — an older release, or carrying the rows
    across — and no command line."""
    if pre_squash_chain is None:
        pytest.skip("origin/main's pre-squash chain is not reachable in this checkout")
    baseline, migrations = pre_squash_chain
    path = tmp_path / "behind.db"
    monkeypatch.setattr(dbmod, "SCHEMA_FILE", baseline)
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", migrations)
    behind = EngineDatabase(path)
    whole = tuple(Migration(n, p) for n, p in dbmod._migration_files())
    behind._migrations = whole[:max(2, len(whole) // 2)]
    behind.initialize()
    monkeypatch.undo()

    with pytest.raises(DatabaseMigrationError) as raised:
        EngineDatabase(path).initialize()
    message = str(raised.value)

    assert "R-84" in message, "the refusal does not name the ruling behind it"
    assert "Nothing has been changed" in message, (
        "the refusal does not say the database is untouched, which is the first "
        "thing its reader needs to know")
    for command in ("scrapex ", "python -m", "init-db"):
        assert command not in message, (
            f"the refusal names {command!r}, a command line — R-81")
