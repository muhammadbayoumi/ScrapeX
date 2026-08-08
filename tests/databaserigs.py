"""Stand-ins the database tests used to get for free from two real classes.

Until M5 there were two database types, and tests borrowed them for two jobs
neither was meant for:

  · a BASE TO SUBCLASS, when a test needed a database whose migration stream it
    could replace with one synthetic file — checksum handling, line endings, a
    migration that fails halfway.
  · a FOREIGN DATABASE, when a test needed a real, healthy ScrapeX file that the
    database under test must refuse.

M5 left one type, so both jobs need saying out loud instead of being a side
effect of there having been a spare class lying around. That is an improvement:
`rig()` says "a database whose stream is this and nothing else", and
`foreign_database()` says "a file that is not ours", neither of which was
readable when the answer was "use GeneralDatabase".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scrapex.databases.domain import DomainDatabase, Migration

#: The id the existing rig fixtures' SQL actually writes. These fixtures were
#: authored against the retired generic database and their migration scripts set
#: its pragma, so the rig has to EXPECT what its own migration writes — a rig
#: that imposed a different id would refuse the file it just built. Callers with
#: their own SQL pass their own id.
RIG_APPLICATION_ID = 0x5358474E  # what the shipped rig fixtures set

#: What a foreign file claims to be. Any id that is not the engine's will do —
#: this one is the retired price database's, so the refusal is exercised against
#: the exact value that used to be a real, valid neighbour.
FOREIGN_APPLICATION_ID = 0x53584D4C  # "SXML", the retired price database


def rig(path: Path, *migrations: Migration, kind: str = "general",
        application_id: int = RIG_APPLICATION_ID) -> DomainDatabase:
    """A database whose whole migration stream is the files given.

    The point is control: a test that needs a migration with CRLF endings, or one
    that fails on its third statement, cannot get that from a real stream and
    should not try. Everything else — the ledger, the checksum, the version
    stamping — is the real machinery, which is what is under test.

    THE KIND AND THE ID BOTH DEFAULT TO WHAT THE SHIPPED FIXTURES WRITE, and
    that is not laziness: a rig must expect exactly what its own migration
    stamps, or it refuses the file it has just built. Callers with their own SQL
    pass their own.
    """

    class _Rig(DomainDatabase):
        pass

    _Rig.kind = kind
    _Rig.application_id = application_id
    return _Rig(path, tuple(migrations))


def foreign_database(path: Path) -> Path:
    """A real SQLite file that is not an engine database, and says so.

    Written by hand rather than by another product class, because there is no
    other product class any more. It carries the retired price database's
    application id: the strongest version of the test, since that id belonged to
    a file that WAS valid here until M5 and would be the most plausible thing to
    find sitting in the wrong place.

    `scrapex_meta` is present and populated, so the refusal cannot come from the
    file being empty or unreadable — it has to come from the identity.
    """
    con = sqlite3.connect(path)
    try:
        con.execute(f"PRAGMA application_id = {FOREIGN_APPLICATION_ID}")
        con.execute("PRAGMA user_version = 13")
        con.execute("CREATE TABLE scrapex_meta (key TEXT PRIMARY KEY, value TEXT)")
        con.executemany("INSERT INTO scrapex_meta VALUES (?,?)",
                        [("database_kind", "marketlens"),
                         ("migration_stream", "marketlens")])
        con.commit()
    finally:
        con.close()
    return path
