r"""A migration's identity is its SQL, not its platform's newlines.

Hashing raw bytes made the tamper guard platform-dependent. `.gitattributes`
says `* text=auto` and core.autocrlf is on, so the repo stores LF and a Windows
checkout gets CRLF — the same committed migration hashes one way on the machine
that stamped the ledger and another on the machine that reads it.

It fired for real. `general` migration 0003_field_paging_index.sql was stamped
f57f56a4 (1,042 bytes, 23 LF) and read back ba24e532 (1,065 bytes, 23 CRLF),
identical SQL, and refused every `scrapex ingest` and `scrapex backup-databases`
on Windows with "checksum changed; restore the original migration file". The
file was never edited: it is byte-identical to its only commit, `d9dab1b`.

Measured across both live databases before the fix: 57 of 57 migrations matched
one form or the other and NOT ONE was genuinely edited — 41 stamped from LF
content, 16 from CRLF. So re-stamping to CRLF would only have moved the failure
to Linux and CI, and 40 MarketLens rows were already latently broken behind a
connect() path that does not verify checksums.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex.databases.domain import (
    DatabaseMigrationError, Migration,
)

_SQL_LF = (
    b"PRAGMA application_id = 1398294350;\n"
    b"CREATE TABLE thing (id INTEGER PRIMARY KEY);\n"
    b"CREATE TABLE scrapex_meta (key TEXT PRIMARY KEY, value TEXT);\n"
    b"INSERT INTO scrapex_meta VALUES ('database_kind', 'general');\n"
    b"CREATE TABLE database_migration (\n"
    b"  migration_number INTEGER PRIMARY KEY, migration_name TEXT NOT NULL,\n"
    b"  sha256 TEXT NOT NULL,\n"
    b"  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));\n"
    b"PRAGMA user_version = 1;\n"
)


def _rig(path, migration_path):
    from tests.databaserigs import rig
    return rig(path, Migration(1, migration_path))


def _stored(db_path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT sha256 FROM database_migration WHERE migration_number = 1"
        ).fetchone()[0]
    finally:
        conn.close()


def test_the_same_sql_hashes_the_same_through_lf_and_crlf(tmp_path):
    """The defect, at its root. Two checkouts of ONE commit must agree."""
    lf, crlf = tmp_path / "lf.sql", tmp_path / "crlf.sql"
    lf.write_bytes(_SQL_LF)
    crlf.write_bytes(_SQL_LF.replace(b"\n", b"\r\n"))
    assert lf.read_bytes() != crlf.read_bytes(), "the fixture must differ in bytes"
    assert Migration(1, lf).sha256 == Migration(1, crlf).sha256
    # And the raw hashes really do disagree — that is what broke.
    assert Migration(1, lf).legacy_sha256 != Migration(1, crlf).legacy_sha256


def test_a_lone_cr_folds_too(tmp_path):
    """Old Mac-style endings are the third convention, folded for the same reason."""
    cr = tmp_path / "cr.sql"
    cr.write_bytes(_SQL_LF.replace(b"\n", b"\r"))
    lf = tmp_path / "lf.sql"
    lf.write_bytes(_SQL_LF)
    assert Migration(1, cr).sha256 == Migration(1, lf).sha256


def test_a_ledger_stamped_from_raw_bytes_still_verifies(tmp_path):
    """THE LIVE CONDITION. An existing warehouse must keep opening.

    Both live databases carried a MIXTURE of raw and normalised digests, so a
    reader that accepted only the new form would have locked the owner out of
    the very databases the fix is meant to unblock.
    """
    sql = tmp_path / "0001_base.sql"
    sql.write_bytes(_SQL_LF.replace(b"\n", b"\r\n"))   # a Windows checkout
    db = tmp_path / "rig.db"
    _rig(db, sql).initialize()

    # Rewind the ledger to the digest a pre-normalisation build stamped.
    legacy = Migration(1, sql).legacy_sha256
    conn = sqlite3.connect(db)
    conn.execute("UPDATE database_migration SET sha256 = ?", (legacy,))
    conn.commit()
    conn.close()
    assert _stored(db) == legacy

    # It must open, and not raise the false alarm.
    _rig(db, sql).connect().close()


def test_stamping_upgrades_a_legacy_digest_in_place(tmp_path):
    """The mixed state converges instead of every reader knowing both forms."""
    sql = tmp_path / "0001_base.sql"
    sql.write_bytes(_SQL_LF.replace(b"\n", b"\r\n"))
    db = tmp_path / "rig.db"
    _rig(db, sql).initialize()

    legacy = Migration(1, sql).legacy_sha256
    canonical = Migration(1, sql).sha256
    assert legacy != canonical
    conn = sqlite3.connect(db)
    conn.execute("UPDATE database_migration SET sha256 = ?", (legacy,))
    conn.commit()
    conn.close()

    rig = _rig(db, sql)
    conn = sqlite3.connect(db)
    try:
        rig._stamp_and_verify_checksums(conn)   # noqa: SLF001 — the unit under test
    finally:
        conn.close()
    assert _stored(db) == canonical, "the legacy digest was not upgraded"


def test_a_real_edit_still_fails_loudly(tmp_path):
    """Normalising must cost NO detection. Only a newline is forgiven."""
    sql = tmp_path / "0001_base.sql"
    sql.write_bytes(_SQL_LF)
    db = tmp_path / "rig.db"
    _rig(db, sql).initialize()

    # Same line count, one identifier changed.
    sql.write_bytes(_SQL_LF.replace(b"CREATE TABLE thing", b"CREATE TABLE other"))
    with pytest.raises(DatabaseMigrationError, match="checksum changed"):
        _rig(db, sql).connect()


def test_whitespace_inside_a_line_is_not_a_line_ending(tmp_path):
    """The narrowest possible edit still fails: folding newlines must not turn
    into folding whitespace generally."""
    sql = tmp_path / "0001_base.sql"
    sql.write_bytes(_SQL_LF)
    db = tmp_path / "rig.db"
    _rig(db, sql).initialize()

    sql.write_bytes(_SQL_LF.replace(b"CREATE TABLE thing", b"CREATE  TABLE thing"))
    with pytest.raises(DatabaseMigrationError, match="checksum changed"):
        _rig(db, sql).connect()


def test_every_shipped_migration_hashes_the_same_on_either_platform(tmp_path):
    """The regression guard over the REAL 57 migrations.

    Each shipped file is rewritten into both conventions and re-hashed: the
    digest may not depend on which one a checkout produced. This is the property
    the live databases needed and did not have — CI runs on Linux (LF) and the
    owner develops on Windows (CRLF), and before the fix those two disagreed
    about every multi-line migration in the repo.
    """
    from scrapex.databases import domain

    # ONE STREAM SINCE M5. It was two, and iterating both was how every shipped
    # migration got covered; the engine's plan is now the whole of what ships.
    plans = (domain._engine_plan(),)  # noqa: SLF001
    seen = 0
    for plan in plans:
        for migration in plan:
            body = migration.path.read_bytes().replace(b"\r\n", b"\n")
            as_lf, as_crlf = tmp_path / "lf.sql", tmp_path / "crlf.sql"
            as_lf.write_bytes(body)
            as_crlf.write_bytes(body.replace(b"\n", b"\r\n"))
            assert Migration(1, as_lf).sha256 == Migration(1, as_crlf).sha256, (
                f"{migration.name} hashes differently per line ending")
            # And the shipped file agrees with its own normalised form.
            assert migration.sha256 == Migration(1, as_lf).sha256, migration.name
            seen += 1
    # A COUNT, NOT A MINIMUM. `seen >= 50` guarded against the loop silently
    # walking nothing back when there were two streams of sixty-odd files. M5
    # left one stream of one, so a floor of fifty would fail forever while a
    # floor of one would stop noticing an empty plan. Comparing against the plan
    # itself keeps the guard exact at any length.
    assert seen == sum(len(plan) for plan in plans) > 0, (
        f"walked {seen} of {sum(len(p) for p in plans)} shipped migrations")
