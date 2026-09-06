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


def _pre_squash_commit(folder: Path) -> str | None:
    """The last commit of the era BEFORE the baseline was raised — with its chain.

    THIS USED TO READ `origin/main`, AND THAT IS WHY THESE TESTS STOPPED TESTING
    ANYTHING. `origin/main` names a MOVING state; "before the squash" names a
    MOMENT. The two agreed exactly until the squash merged, and from then on the
    fixture recovered the SQUASHED chain while still being called
    `pre_squash_chain` -- so the tests below built a database that was never below
    the baseline, asserted it would be refused, and passed because nothing
    contradicted them. They went red only when a new migration made the chain two
    long and `whole[:max(2, len(whole) // 2)]` selected all of it.

    THE PARENT, NOT THE COMMIT THAT TOUCHED THE FILE. The squash raised the
    baseline and deleted the chain in one commit, so the era that still HAS a
    chain is its parent -- and the parent does not appear in
    `rev-list -- db/engine/schema.sql` at all, because it never touched it. A
    first attempt walked only that list, found an ancestor whose baseline was
    lower but whose migrations directory was empty, and turned five failures into
    five SKIPS. That is the same silence in a quieter coat.

    Derived, never typed, and read with the engine's own
    `declared_schema_version` so there is no second parser to drift from it.
    """
    now = dbmod.declared_schema_version(dbmod.SCHEMA_FILE)
    probe = folder / "probe.sql"

    def era(ref: str) -> tuple[int, int] | None:
        """(baseline, migration count) at `ref`, or None if it has no schema."""
        try:
            probe.write_bytes(_git("show", f"{ref}:db/engine/schema.sql"))
            names = _git("ls-tree", "--name-only",
                         f"{ref}:db/engine/migrations").decode().split()
        except subprocess.CalledProcessError:
            return None
        try:
            return dbmod.declared_schema_version(probe), len(names)
        except ValueError:
            return None

    try:
        history = _git("rev-list", "origin/main", "--",
                       "db/engine/schema.sql").decode().split()
    except subprocess.CalledProcessError:
        return None            # no history reachable: a shallow or detached checkout
    if not history:
        return None

    for commit in history:
        parent = f"{commit}^"
        found = era(parent)
        if found and found[0] < now and found[1] > 0:
            return parent
    # The history IS reachable and no era below the current baseline carries a
    # chain. That is not a checkout problem and must not read as one.
    raise AssertionError(
        f"no commit before baseline {now} still carries a migration chain, so "
        "these tests have no pre-squash database to build. Either the history "
        "was rewritten or the derivation above no longer describes how the "
        "baseline moves -- do not turn this into a skip.")


@pytest.fixture(scope="module")
def pre_squash_chain(tmp_path_factory) -> tuple[Path, Path] | None:
    """A baseline and migrations from before the squash — or None if unavailable.

    A shallow clone or a detached CI checkout may not have the history. That is a
    reason to skip, not to invent a fixture: the point of these tests is a REAL
    pre-squash database.

    AND IT REFUSES TO RETURN THE WRONG ERA RATHER THAN RETURNING IT QUIETLY. Every
    exit below is a skip with a reason; none of them hands back a chain that is not
    older than the one shipping.
    """
    folder = tmp_path_factory.mktemp("chain")
    commit = _pre_squash_commit(folder)
    if commit is None:
        return None
    try:
        names = _git("ls-tree", "--name-only",
                     f"{commit}:db/engine/migrations").decode().split()
        baseline = folder / "schema.sql"
        baseline.write_bytes(_git("show", f"{commit}:db/engine/schema.sql"))
    except subprocess.CalledProcessError:
        return None
    # NOT A SKIP. `_pre_squash_commit` returns only an era that HAS a chain, so an
    # empty one here means the derivation and this reader disagree -- and a skip
    # would hide exactly the degradation this fixture was rewritten to stop
    # hiding. Measured by mutation: with the chain-length condition removed above,
    # a `return None` here turned three real failures into six silent skips.
    assert names, (
        f"{commit} was chosen as the pre-squash era and carries no migrations; "
        "the derivation and this reader no longer agree")
    migrations = folder / "migrations"
    migrations.mkdir()
    for name in names:
        (migrations / name).write_bytes(
            _git("show", f"{commit}:db/engine/migrations/{name}"))
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

    # THE REFUSAL THAT IS FORBIDDEN IS THE CHECKSUM ONE, not every refusal. This
    # asserted `connect()` outright, which held only while the pre-squash era's
    # head happened to equal the shipping head -- they were both v17 on the day
    # the squash landed, and the next migration to reach `main` made them 17 and
    # 18. A database with migrations pending is ENTITLED to be told so; what it
    # must never again be told is that its baseline's digest changed, which is
    # what the squash made every existing warehouse look like.
    try:
        db.connect().close()
    except DatabaseMigrationError as exc:
        assert "checksum" not in str(exc), (
            f"the squash reconciliation is gone: {exc}")
        assert "expected v" in str(exc), (
            f"refused for a reason that is neither checksum nor version: {exc}")

    db.initialize()

    # And after it, nothing downstream can tell a squash ever happened.
    assert db.initialize() == []
    db.connect().close()
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
    not any digest that happens to differ.

    BROUGHT TO HEAD FIRST, because the version check runs before the checksum one.
    Without this the database sits a migration behind whatever `main` ships and
    `connect()` refuses it for THAT, so the digest under test is never reached and
    the assertion below passes or fails on the wrong sentence. It held only while
    the pre-squash era's head equalled the shipping head.
    """
    EngineDatabase(pre_squash_database).initialize()

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
