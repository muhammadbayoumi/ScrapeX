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
from scrapex.databases.domain import EngineDatabase


@pytest.fixture()
def registry(tmp_path) -> DatabaseRegistry:
    return DatabaseRegistry(
        EngineDatabase(tmp_path / "marketlens" / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json",
    )


# ---- creating what is not there ---------------------------------------------

def test_a_first_run_creates_the_database_without_being_asked(registry):
    """Starting the engine is the only thing the owner has to do. A database
    that does not exist holds nothing to lose, so creating it needs no
    permission and no warning."""
    report = registry.ensure_ready()
    assert report["ok"], report
    assert report["created"] == ["engine"]
    assert registry.engine.path.is_file()


def test_the_pointer_records_the_database_that_was_created(registry):
    registry.ensure_ready()
    assert registry.pointer_file.is_file(), \
        "without the pointer the next start would not find these databases"


def test_starting_again_creates_nothing_and_stays_ok(registry):
    registry.ensure_ready()
    again = registry.ensure_ready()
    assert again["created"] == [], "a second start must not re-create anything"
    assert again["ok"]


def test_an_existing_database_is_not_created_over(registry):
    """REPLACES test_only_the_missing_half_is_created. There is no other half to
    be missing, but the guarantee underneath it survives and matters more now
    that one file holds everything: `ensure_ready` must never re-initialise a
    database that is already there."""
    registry.engine.initialize()
    report = registry.ensure_ready()
    assert report["created"] == [], (
        "an existing database was created over, which would erase it")
    assert report["ok"]


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
    behind = registry.engine.latest_schema_version - 1
    _rewind_schema(registry.engine, behind)

    report = registry.ensure_ready()

    assert not report["ok"], "an unusable database must not report ok"
    assert report["created"] == []
    conn = sqlite3.connect(str(registry.engine.path))
    try:
        still = int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()
    assert still == behind, "ensure_ready migrated a database it was not asked to"


def test_a_database_that_is_behind_is_called_upgradeable_not_broken(
        tmp_path, one_migration_above_the_baseline):
    """"Failed — restore a verified backup" sends the owner to destroy good data
    over an upgrade he can press a button for.

    IT REWOUND BY ONE, AND THAT STOPPED MEANING "BEHIND". After `R-84`'s squash
    `latest - 1` is BELOW the baseline, so this test was reading the refusal branch
    while asserting the upgrade one — and what it asserted about the action was that
    it named `init-db`, which is the defect rather than the fix (`R-81`: the owner
    has no terminal, so a command is a dead end printed inside a live failure).
    """
    database = EngineDatabase(tmp_path / "engine" / "scrapex-engine.db")
    database.initialize()
    _rewind_schema(database, one_migration_above_the_baseline - 1)

    state = database.health()

    assert state.status == "Needs upgrade", state.status
    assert "Upgrade database" in state.action and "Settings" in state.action, \
        "the fix must be named as the button it is, and the screen it is on"
    for command in ("scrapex ", "python -m", "init-db"):
        assert command not in state.action, \
            f"the action names {command!r}, a command line — R-81"
    assert "backup" not in state.action.lower(), \
        "restoring a backup is the wrong instruction for a database that is behind"


def test_a_database_below_the_baseline_is_not_called_upgradeable(registry):
    """`R-84`: below the baseline there is no upgrade path, so calling it "Needs
    upgrade" offers a repair that cannot exist.

    THIS IS THE BRANCH A REAL ENGINE DATABASE REACHES TODAY, measured: the plan is
    one file, so every version between 1 and the head is below the baseline. What it
    cost while it answered "Needs upgrade" is two things at once — `startup_check`
    offered the panel's "Upgrade database" button, and pressing it copied the whole
    warehouse (316,760,064 bytes, measured on his) before failing and changing
    nothing.
    """
    registry.ensure_ready()
    _rewind_schema(registry.engine, registry.engine.latest_schema_version - 1)

    state = registry.engine.health()

    assert state.status == "Older than the schema baseline", state.status
    assert "R-84" in state.action, "the refusal does not name the ruling behind it"
    assert "Nothing has been changed" in state.action, (
        "the action does not say the database is untouched, which is the first "
        "thing its reader needs to know")
    for command in ("scrapex ", "python -m", "init-db"):
        assert command not in state.action, \
            f"the action names {command!r}, a command line — R-81"


def test_no_database_status_ever_answers_with_a_command_line(
        tmp_path, one_migration_above_the_baseline):
    """THE GUARD THAT WAS MISSING, and its absence is why one command shipped on
    three surfaces at once.

    `test_the_refusal_says_what_to_do_and_names_no_terminal_command` asserts this of
    the EXCEPTION `_migrate` raises. Nothing asserted it of `DatabaseHealth.action`
    — which the side panel renders (`native.startup_check`), the engine's own pages
    print (`base.html`), and `/api/health` carries — so "Run 'python -m scrapex.cli
    init-db'" reached all three from one line, with a green suite and two tests
    DEMANDING it.

    Every state that carries an action is swept, not the one that happened to be
    wrong. A new status is a new row here.
    """
    head = one_migration_above_the_baseline
    database = EngineDatabase(tmp_path / "engine" / "scrapex-engine.db")

    states = {"Missing": database.health()}
    database.initialize()
    states["Healthy"] = database.health()
    for version, case in ((head - 1, "behind"),
                          (head - 2, "below the baseline"),
                          (head + 5, "from a newer build")):
        _rewind_schema(database, version)
        state = database.health()
        assert state.status not in states, f"{case} reported {state.status!r} twice"
        states[state.status] = state

    # AND THE BRANCH REACHED BY SOMETHING OTHER THAN A VERSION, which is where the
    # SECOND command was hiding: `health()` interpolates the exception verbatim, and
    # `_verify`'s contract-marker refusal named `scrapex init-db` long after the
    # version branch had stopped naming anything. A sweep that only rewinds versions
    # cannot see it — five statuses looked like all of them.
    _rewind_schema(database, head)
    conn = sqlite3.connect(str(database.path))
    try:
        # A NUMBER, and a wrong one. `'wrong'` reaches `int()` in
        # `contract.stored_contract_version` and raises `ValueError`, which
        # `health()` does not catch at all -- so a corrupt marker takes down the
        # surface that exists to report corruption. Recorded in `OP-135`; this test
        # is about the ACTION's words, so it takes the path that reports.
        conn.execute("UPDATE scrapex_meta SET value = '999' "
                     "WHERE key = 'contract_version'")
        conn.commit()
    finally:
        conn.close()
    broken = database.health()
    assert broken.status == "Integrity check failed", broken.status
    states[broken.status] = broken

    assert len(states) == 6, f"a state was not reached: {sorted(states)}"
    for status, state in states.items():
        for command in ("scrapex ", "python -m", "init-db", "pip install"):
            assert command not in state.action, (
                f"{status!r} answers with {command!r}, a command line — R-81. "
                f"Its action reads: {state.action}")


def test_a_database_from_a_future_build_says_update_scrapex(registry):
    """The opposite direction has the opposite fix, and downgrading would lose
    whatever the newer build wrote."""
    registry.ensure_ready()
    _rewind_schema(registry.engine, registry.engine.latest_schema_version + 5)

    state = registry.engine.health()

    assert state.status == "Needs a newer ScrapeX"
    assert "do not downgrade" in state.action.lower()


def test_a_broken_pair_is_not_recorded_as_the_live_one(registry):
    registry.engine.initialize()
    _rewind_schema(registry.engine, registry.engine.latest_schema_version - 1)

    report = registry.ensure_ready()

    assert not report["ok"]
    assert not registry.pointer_file.is_file(), \
        "the pointer named a pair the engine cannot use"


# ---- the notification --------------------------------------------------------

def test_a_healthy_database_still_reports_a_status(registry):
    """Status only shown on failure is status the owner cannot trust."""
    registry.ensure_ready()
    states = registry.health()
    assert set(states) == {"engine"}
    assert all(item["ok"] and item["status"] == "Healthy" for item in states.values())
