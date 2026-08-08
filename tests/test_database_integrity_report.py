"""A checksum mismatch must say what it is, and must not name a command that fails.

The report for it used to read "This database is at schema v51 and this build
expects v51. Run 'python -m scrapex.cli init-db' to upgrade it, then retry."
Every clause is wrong: the versions are equal, it is not an upgrade, and init-db
raises the identical checksum error. `health()` caught DatabaseMigrationError,
dropped `exc`, and answered with the version branch — so the one component that
knew the answer was the one whose words were discarded.
"""
from __future__ import annotations

import pytest

from scrapex.databases.domain import DatabaseMigrationError, EngineDatabase


def _db_at_head(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    return db


def test_an_edited_applied_migration_is_reported_as_what_it_is(tmp_path, monkeypatch):
    db = _db_at_head(tmp_path)
    assert db.health().ok, "the fresh database was not healthy to begin with"

    # Edit an applied migration the only way that matters: its bytes. Both the
    # canonical (newline-normalised) digest and the legacy raw-bytes digest are
    # derived from those bytes, so a real edit moves BOTH — patching only one
    # leaves the health check a matching digest to accept, and on an LF checkout
    # (CI) the raw and normalised hashes are equal, so the unpatched one is the
    # stored value itself. Simulate the byte change at both derivations.
    target = db._migrations[-1]
    monkeypatch.setattr(type(target), "sha256",
                        property(lambda self: "0" * 64))
    monkeypatch.setattr(type(target), "legacy_sha256",
                        property(lambda self: "0" * 64))

    report = db.health()

    assert report.ok is False
    assert report.status == "Integrity check failed", report.status
    # The words the owner actually needs, carried through from the exception.
    assert "checksum changed" in report.action, report.action
    assert "restore the original migration file" in report.action, report.action
    # And the two sentences that sent a whole session looking in the wrong place.
    assert "expects" not in report.action, "the version branch answered a non-version fault"
    assert "init-db" not in report.action, \
        "the report still names a command that raises this very error"


def test_a_genuinely_behind_database_still_says_upgrade(tmp_path):
    """The guard must narrow to the equal-version case, not swallow the real one."""
    db = _db_at_head(tmp_path)
    with db.connect() as conn:
        conn.execute(f"PRAGMA user_version = {db.latest_schema_version - 1}")
        conn.commit()

    report = db.health()
    assert report.ok is False
    assert report.status == "Needs upgrade", report.status
    assert "init-db" in report.action
