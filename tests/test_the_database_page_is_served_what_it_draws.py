"""The Database page reads one route, and the route has to carry the schema.

WHAT WAS SPLIT, AND WHY IT MATTERED. `GET /api/storage` carried the path, the sizes, the
health verdict and the backups. The schema VERSION reached `_about`, which feeds the
ENGINE'S OWN WEB PAGE and nothing else -- so the panel could say "healthy" and could not
say which version, which is the one number that decides whether the owner has an upgrade
to press. `R-81`: a fact only the web page holds is a fact he does not have.

BOTH NUMBERS AND THE NAMES, NEVER A BOOLEAN. `version` and `expected` let the page say
`v17 of v18` -- how far behind and which way -- where a `behind: true` says neither and a
build somehow sitting BELOW its own file reads as ordinary. `pending` names the files
because the honest answer to "what would pressing Upgrade do" is their names.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod, storage

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(connection)
    try:
        yield connection
    finally:
        connection.close()


def test_the_route_states_the_version_this_build_expects(conn, tmp_path):
    """A fresh database is at the head of the stream, and the page must be able to say
    so rather than leaving the row empty."""
    facts = storage._schema_facts(conn)

    assert facts["version"] == dbmod.schema_version(conn)
    assert facts["expected"] == max(n for n, _p in dbmod._migration_files()), (
        "the expected version is not the head of the shipped stream, so the page would "
        "compare against the wrong number")
    assert facts["pending"] == [], (
        "a database the shipped build just migrated is reported as behind")


def test_a_database_behind_the_stream_names_what_is_waiting(conn):
    """THE NAMES, NOT A COUNT. `pending_migrations` is the same comparison
    `EngineDatabase` uses to decide whether to migrate, so the page reports what the
    upgrade would act on rather than a second opinion about it."""
    # BEHIND MEANS THE LEDGER HAS NO ROW FOR IT, and my first draft of this test
    # rewound `PRAGMA user_version` instead -- which changes nothing, because
    # `pending_migrations` says in terms: "THE LEDGER IS THE WHOLE ANSWER NOW. A
    # migration is pending when this database has no row for it." The rewind produced an
    # empty `pending` and the test was measuring its own wrong premise.
    newest = max(dbmod._migration_files(), key=lambda pair: pair[0])
    name = newest[1].name
    removed = conn.execute(
        "DELETE FROM database_migration WHERE migration_name = ?", (name,)).rowcount
    conn.commit()
    assert removed == 1, (
        f"{name} was not in the ledger to begin with, so this database was already "
        "behind and the test is not creating the state it claims to")

    facts = storage._schema_facts(conn)

    assert name in facts["pending"], (
        f"{name} is not in the ledger and the route reports nothing waiting: "
        f"{facts['pending']}")
    assert all(one.endswith(".sql") for one in facts["pending"]), (
        f"pending should name migration files: {facts['pending']}")
    assert facts["expected"] == newest[0], (
        "the expected version is not the head of the stream")


def test_storage_status_carries_the_schema_block(conn, tmp_path):
    """The page reads ONE route, so the block has to be in `storage_status`'s answer and
    not only in the helper beside it."""
    answer = storage.storage_status(conn, tmp_path / "harvest.db")

    assert "schema" in answer, (
        "GET /api/storage does not carry the schema, so the Database page has no version "
        "to state and falls back to 'unreadable' on a healthy warehouse")
    assert set(answer["schema"]) >= {"version", "expected", "pending"}, answer["schema"]


def test_an_unreadable_database_still_answers_with_a_size(tmp_path):
    """A FAULT IN ONE ROW IS NOT A FAULT IN THE PAGE.

    A storage page that 500s tells the owner less than one that shows a size and admits
    it could not read a version -- and `health` reports the fault in its own row, with
    its own detail, which is where it belongs.
    """
    broken = tmp_path / "not-a-database.db"
    broken.write_bytes(b"this is not sqlite")
    conn = sqlite3.connect(broken)
    try:
        facts = storage._schema_facts(conn)
    finally:
        conn.close()

    assert facts["version"] is None, (
        "it claimed to read a version out of a file that is not a database")
    assert facts["pending"] == []
    assert facts["expected"] == max(n for n, _p in dbmod._migration_files()), (
        "the build's own expected version is not a property of the file being read, so "
        "it must survive a file that cannot be read at all")
