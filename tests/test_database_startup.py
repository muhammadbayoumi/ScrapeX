"""Starting the engine is the whole setup, and status is never silent.

Two owner requests drove this file:

  1. "can the extension create the databases?" — it cannot, and it must not: the
     local runtime owns both files (spec 5). What the owner actually needed was
     to stop running a command by hand, so the runtime creates them on the way
     up. These tests hold that line: created when absent, NEVER migrated behind
     the owner's back when present.

  2. "add a notification showing database status" — so the status has to be
     reachable from the page and from the panel's poll, and it has to name the
     database, the state and the action.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex.databases import DatabaseRegistry
from scrapex.databases.domain import GeneralDatabase, MarketLensDatabase


@pytest.fixture()
def registry(tmp_path) -> DatabaseRegistry:
    return DatabaseRegistry(
        GeneralDatabase(tmp_path / "general" / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens" / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )


# ---- creating what is not there ---------------------------------------------

def test_a_first_run_creates_both_databases_without_being_asked(registry):
    report = registry.ensure_ready()
    assert report["ok"], report
    assert sorted(report["created"]) == ["general", "marketlens"]
    assert registry.general.path.is_file()
    assert registry.marketlens.path.is_file()


def test_the_pointer_records_the_pair_that_was_created(registry):
    registry.ensure_ready()
    assert registry.pointer_file.is_file(), \
        "without the pointer the next start would not find these databases"


def test_starting_again_creates_nothing_and_stays_ok(registry):
    registry.ensure_ready()
    again = registry.ensure_ready()
    assert again["created"] == [], "a second start must not re-create anything"
    assert again["ok"]


def test_only_the_missing_half_is_created(registry):
    registry.general.initialize()
    report = registry.ensure_ready()
    assert report["created"] == ["marketlens"], \
        "an existing database must not be touched to create its neighbour"


# ---- refusing to migrate the owner's data behind their back ------------------

def _rewind_schema(database, version: int) -> None:
    """Leave a real, healthy database sitting at an older schema version."""
    conn = sqlite3.connect(str(database.path))
    try:
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    finally:
        conn.close()


def test_an_existing_database_that_is_behind_is_reported_not_upgraded(registry):
    """Advancing the schema of a file that already holds data is the owner's
    decision (spec 40). Doing it silently on start is exactly the surprise the
    separation rules exist to prevent."""
    registry.ensure_ready()
    behind = registry.marketlens.latest_schema_version - 1
    _rewind_schema(registry.marketlens, behind)

    report = registry.ensure_ready()

    assert not report["ok"], "an unusable database must not report ok"
    assert report["created"] == []
    conn = sqlite3.connect(str(registry.marketlens.path))
    try:
        still = int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()
    assert still == behind, "ensure_ready migrated a database it was not asked to"


def test_a_database_that_is_behind_is_called_upgradeable_not_broken(registry):
    """"Failed — restore a verified backup" sends the owner to destroy good data
    over a one-command upgrade."""
    registry.ensure_ready()
    _rewind_schema(registry.marketlens, registry.marketlens.latest_schema_version - 1)

    state = registry.marketlens.health()

    assert state.status == "Needs upgrade"
    assert "init-db" in state.action, "the fix must be named, not implied"
    assert "backup" not in state.action.lower(), \
        "restoring a backup is the wrong instruction for a database that is behind"


def test_a_database_from_a_future_build_says_update_scrapex(registry):
    """The opposite direction has the opposite fix, and downgrading would lose
    whatever the newer build wrote."""
    registry.ensure_ready()
    _rewind_schema(registry.general, registry.general.latest_schema_version + 5)

    state = registry.general.health()

    assert state.status == "Needs a newer ScrapeX"
    assert "do not downgrade" in state.action.lower()


def test_a_broken_pair_is_not_recorded_as_the_live_one(registry):
    registry.general.initialize()
    _rewind_schema(registry.general, registry.general.latest_schema_version - 1)

    report = registry.ensure_ready()

    assert not report["ok"]
    assert not registry.pointer_file.is_file(), \
        "the pointer named a pair the engine cannot use"


# ---- the notification --------------------------------------------------------

def test_a_healthy_database_still_reports_a_status(registry):
    """Status only shown on failure is status the owner cannot trust."""
    registry.ensure_ready()
    states = registry.health()
    assert set(states) == {"general", "marketlens"}
    assert all(item["ok"] and item["status"] == "Healthy" for item in states.values())
