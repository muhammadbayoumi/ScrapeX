"""A warehouse that carried over another database's migration ledger still upgrades.

`OP-30`, found on the owner's LIVE warehouse on 2026-08-21 while upgrading it at his
instruction. `database_migration` is `migration_number INTEGER PRIMARY KEY` — **one
number space** — and a warehouse carried over from the price database holds two
streams in it: the engine's at 1-5, and the price stream's fifty rows at 6-55.

Engine migration `0006` was the first number this stream had ever wanted. Number 6
was already `0006_change_event.sql`, so verification compared the digests of two
unrelated files and reported

    engine migration 0006_a_row_says_when_it_was_last_proved_absent.sql
    checksum changed; restore the original migration file and retry

with no file having changed. The warehouse could not be opened by any build, on
`connect()` as well as on upgrade.

WHY THIS FILE IS THE POINT AND NOT THE FIX. **No existing test could have caught
it.** A fresh `init-db` writes only the engine's own rows, so the number space above
5 is empty and nothing collides — and **CI always starts from a fresh database**. 273
tracked test files and the `migration-authority` job, which runs the whole suite
against the real migration stream, all passed while the defect sat there. The
collision needs a warehouse that CARRIED OVER, and no fixture had one.

So this file builds that fixture: a real engine database with foreign rows planted in
its ledger at exactly the numbers the engine will want next. It is the same class of
gap as `R-24` — the upgrade path is exercised only by a real user's file — and the
answer is to make a test own that path.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.databases.domain import DatabaseMigrationError

#: Names taken from the real carried-over ledger, so the fixture is the shape that
#: actually occurred rather than an invented one.
FOREIGN = [
    (6, "0006_change_event.sql"),
    (7, "0007_identity_alias.sql"),
    (8, "0008_dataset_fields.sql"),
]


def warehouse(tmp_path: Path) -> DatabaseRegistry:
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    return registry


def plant_foreign_rows(path: Path) -> list[tuple[int, str]]:
    """Put another stream's rows in the ledger, at the numbers this one will want.

    THE ENGINE'S OWN ROWS ARE MOVED OUT OF THE WAY FIRST, exactly as the carry-over
    left them: the numbers the engine wants are occupied by names it does not know.
    """
    conn = sqlite3.connect(path)
    try:
        mine = conn.execute(
            "SELECT migration_number, migration_name FROM database_migration "
            " ORDER BY migration_number").fetchall()
        for number, name in FOREIGN:
            conn.execute(
                "DELETE FROM database_migration WHERE migration_number = ?", (number,))
            conn.execute(
                "INSERT INTO database_migration (migration_number, migration_name, "
                "  sha256) VALUES (?,?,?)", (number, name, "f" * 64))
        conn.commit()
        return mine
    finally:
        conn.close()


# ---- the defect, reproduced --------------------------------------------------

def test_a_foreign_row_at_the_number_we_want_does_not_break_the_ledger(tmp_path):
    """THE ORIGINAL FAILURE. Number 6 held by another stream's file must not be read
    as this stream's migration 6."""
    registry = warehouse(tmp_path)
    plant_foreign_rows(registry.engine.path)

    # THE ORDER IS THE REAL SEQUENCE, and getting it wrong first was instructive: a
    # carried-over warehouse is UPGRADED and then connected to. Connecting first
    # reports "ledger is incomplete", which is correct — our own rows for those
    # migrations were never stamped, because this stream had not reached them when
    # the carry-over happened.
    assert registry.engine.initialize() == []

    conn = registry.engine.connect()      # refused before the fix
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] > 0
    finally:
        conn.close()


def test_the_foreign_rows_are_left_exactly_as_they_were(tmp_path):
    """Not deleted, not renumbered, not re-stamped. This stream has no business
    touching another's records — `C4`: a record of what a database did is history."""
    registry = warehouse(tmp_path)
    plant_foreign_rows(registry.engine.path)

    registry.engine.initialize()

    conn = sqlite3.connect(registry.engine.path)
    try:
        for number, name in FOREIGN:
            row = conn.execute(
                "SELECT migration_name, sha256 FROM database_migration "
                " WHERE migration_number = ?", (number,)).fetchone()
            assert row == (name, "f" * 64), f"row {number} was touched"
    finally:
        conn.close()


def test_this_streams_own_rows_are_all_present_by_name(tmp_path):
    """The engine's ledger is complete under its own names, whatever the numbers."""
    registry = warehouse(tmp_path)
    plant_foreign_rows(registry.engine.path)
    registry.engine.initialize()

    conn = sqlite3.connect(registry.engine.path)
    try:
        stamped = {row[0] for row in conn.execute(
            "SELECT migration_name FROM database_migration")}
    finally:
        conn.close()

    expected = {"schema.sql"} | {
        p.name for p in (Path(__file__).resolve().parent.parent
                         / "db" / "engine" / "migrations").glob("*.sql")}
    assert expected <= stamped, f"missing: {sorted(expected - stamped)}"


def test_a_migration_whose_file_really_changed_is_still_refused(tmp_path):
    """THE GUARD THE FIX MUST NOT COST. Keying on the name makes foreign rows
    harmless; it must not make a genuinely altered file harmless too."""
    registry = warehouse(tmp_path)
    conn = sqlite3.connect(registry.engine.path)
    try:
        conn.execute("UPDATE database_migration SET sha256 = ? "
                     " WHERE migration_name = 'schema.sql'", ("0" * 64,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseMigrationError) as raised:
        registry.engine.connect()

    assert "checksum changed" in str(raised.value)
    assert "schema.sql" in str(raised.value)


def test_a_missing_row_for_our_own_migration_is_still_reported(tmp_path):
    """An incomplete ledger for THIS stream is a real fault and must still be named
    — otherwise the fix would have turned a detectable state into a silent one."""
    registry = warehouse(tmp_path)
    conn = sqlite3.connect(registry.engine.path)
    try:
        conn.execute("DELETE FROM database_migration WHERE migration_name = 'schema.sql'")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseMigrationError) as raised:
        registry.engine.connect()

    assert "ledger is incomplete" in str(raised.value)


def test_stamping_twice_adds_nothing(tmp_path):
    """Idempotent, or every `connect()` on a carried-over warehouse would grow the
    ledger by one row per migration."""
    registry = warehouse(tmp_path)
    plant_foreign_rows(registry.engine.path)
    registry.engine.initialize()

    conn = sqlite3.connect(registry.engine.path)
    try:
        before = conn.execute("SELECT COUNT(*) FROM database_migration").fetchone()[0]
    finally:
        conn.close()

    registry.engine.initialize()
    registry.engine.connect().close()

    conn = sqlite3.connect(registry.engine.path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM database_migration").fetchone()[0] == before
    finally:
        conn.close()


def test_a_new_row_takes_a_free_number_rather_than_a_taken_one(tmp_path):
    """`migration_number` is the primary key, so an insert must not reuse a number a
    foreign row holds — that INSERT is what would raise."""
    registry = warehouse(tmp_path)
    plant_foreign_rows(registry.engine.path)
    conn = sqlite3.connect(registry.engine.path)
    try:
        # Force a re-stamp of one of our own migrations at a number now taken.
        conn.execute("DELETE FROM database_migration "
                     " WHERE migration_name = 'schema.sql'")
        conn.commit()
    finally:
        conn.close()

    registry.engine.initialize()

    conn = sqlite3.connect(registry.engine.path)
    try:
        number = conn.execute(
            "SELECT migration_number FROM database_migration "
            " WHERE migration_name = 'schema.sql'").fetchone()[0]
        taken = {n for n, _ in FOREIGN}
    finally:
        conn.close()
    assert number not in taken
