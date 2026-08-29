"""One file, under the engine's own name, that refuses to be mistaken for another.

M5b. `scrapex-engine.exe` is paired with `scrapex-engine.db` — the owner's own
instruction — and it holds what the two databases before it held.

WHAT THESE TESTS ARE ACTUALLY GUARDING. The dangerous failures around a database
file are not crashes; they are a file being used as something it is not. A backup
restored into the wrong path, a copy carried between machines, one letter wrong
in a setting. In every one of those the file opens, the tables are there or not,
and the damage is done by the first write. So the identity is checked before the
contents are trusted, and that is what is asserted here.
"""

from __future__ import annotations

import sqlite3

import pytest

from scrapex.database_ids import ENGINE_APPLICATION_ID, ENGINE_DATABASE_KIND
from scrapex.databases.domain import (
    DatabaseKindError,
    DatabaseMigrationError,
    EngineDatabase,
)
from tests.databaserigs import foreign_database


@pytest.fixture
def engine(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    return db


def test_it_creates_one_file_that_says_what_it_is(engine):
    """The application id is in the SQLite header, so the answer survives being
    renamed, copied, or restored somewhere unexpected."""
    con = sqlite3.connect(f"file:{engine.path}?mode=ro", uri=True)
    try:
        assert con.execute("PRAGMA application_id").fetchone()[0] == ENGINE_APPLICATION_ID
        # THE HEAD, not the literal 1: adding migration 0002 broke this, and a
        # test that has to be edited every time the stream grows is a test that
        # will one day be edited without being read.
        assert (con.execute("PRAGMA user_version").fetchone()[0]
                == engine.latest_schema_version)
        meta = dict(con.execute("SELECT key, value FROM scrapex_meta"))
    finally:
        con.close()

    assert meta["database_kind"] == ENGINE_DATABASE_KIND
    assert meta["migration_stream"] == ENGINE_DATABASE_KIND


def test_it_holds_both_halves_of_what_it_replaced(engine):
    """The whole point of the collapse: priced offers and generic records in one
    file. Two databases meant two backups, two restores and two ways to be half
    recovered."""
    con = sqlite3.connect(f"file:{engine.path}?mode=ro", uri=True)
    try:
        names = {n for (n,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()

    assert {"price_observation", "source_offer", "crawl_run"} <= names
    assert {"generic_record", "source_site", "dataset_definition"} <= names


def test_the_payload_contract_is_stamped_and_then_required(engine, tmp_path):
    """KEPT FROM THE PRICE DATABASE RATHER THAN LOST IN THE MOVE.

    The marker records which payload generation this warehouse was built for. A
    warehouse that has drifted from the contract the code speaks does not fail
    loudly on its own — it returns rows that are quietly wrong — so drift is
    made into a refusal.
    """
    from scrapex.contract import CONTRACT_VERSION, stored_contract_version

    con = sqlite3.connect(engine.path)
    try:
        assert stored_contract_version(con) == CONTRACT_VERSION
        with con:
            con.execute("UPDATE scrapex_meta SET value='0' WHERE key='contract_version'")
    finally:
        con.close()

    # `connect()` IS the gate: it verifies before handing back a connection, so
    # nothing can hold a handle to a database that failed its own check.
    with pytest.raises(DatabaseMigrationError, match="contract marker"):
        EngineDatabase(engine.path).connect()

    assert not EngineDatabase(engine.path).health().ok


def test_it_refuses_a_file_belonging_to_either_database_it_replaces(tmp_path):
    """THE CASE A NAME CANNOT PROTECT AGAINST. Both of these are real ScrapeX
    databases, both open cleanly, and both have a `scrapex_meta`. Only the
    identity tells them apart — and using one as the other would write price
    rows into a file that has no price tables, or the reverse."""
    path = foreign_database(tmp_path / "someone-elses.db")
    name = "retired price"
    if True:
        # DatabaseKindError SPECIFICALLY, and not merely "some exception".
        # Accepting DatabaseMigrationError too made this pass for the wrong
        # reason — caught by mutation: giving EngineDatabase the price
        # database's own identity still refused a price file, on its migration
        # number, and the test noticed nothing. A refusal on the wrong grounds
        # is a refusal that stops happening the moment the versions line up.
        with pytest.raises(DatabaseKindError) as refusal:
            EngineDatabase(path).connect()
        assert "application id" in str(refusal.value), (
            f"a {name} database was refused, but not for being the wrong kind: "
            f"{refusal.value}")

        assert not EngineDatabase(path).health().ok, (
            f"a {name} database reports itself healthy as an engine database")


def test_an_empty_file_is_not_mistaken_for_a_warehouse(tmp_path):
    """A zero-byte file is what a failed copy leaves behind. It must not be
    adopted as an engine database that simply has no rows yet."""
    blank = tmp_path / "scrapex-engine.db"
    blank.touch()

    with pytest.raises((DatabaseKindError, DatabaseMigrationError, RuntimeError)):
        EngineDatabase(blank).connect()

    assert not EngineDatabase(blank).health().ok


def test_initialising_twice_applies_nothing_the_second_time(tmp_path):
    """`init-db` is part of the merge procedure and gets run by hand, often
    twice. The second run must be a no-op, not a re-application."""
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    assert db.initialize() == list(range(1, db.latest_schema_version + 1))
    assert db.initialize() == [], "the second run re-applied migrations"
    assert db.health().ok
