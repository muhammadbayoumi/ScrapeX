"""One database: what it refuses, what it survives, and what M5 removed.

THIS FILE USED TO GUARD THE OPPOSITE ARRANGEMENT. Until M5 it was
"DB1: physical General/MarketLens isolation, migration, and recovery" — two
files that had to be initialised together, split apart from a legacy warehouse,
rolled back as a pair, and kept from ever seeing each other's tables.

M5 collapsed them into one, so five of those tests now describe a shape that no
longer exists. They are recorded here rather than deleted in silence, because a
test disappearing without a reason is indistinguishable from a test lost:

  · fresh_registry_creates_two_typed_databases_without_domain_tables_crossing
        Two typed databases were the point; one is now. The guarantee it
        actually protected — a file being used as something it is not — moved
        to tests/test_the_engine_database.py, where it is checked against the
        engine's own identity.
  · split_preserves_price_history_and_moves_catalogue_to_general
  · failed_split_keeps_legacy_live_and_a_retry_recovers
  · rollback_switches_pointer_without_deleting_split_databases
        `scrapex split-databases` and `rollback-databases` are retired with
        scrapex/databases/split.py. There is nothing left to split.
  · workspace_uses_general_catalogue_across_restart_and_reports_both_health_states
        There are no longer "both" health states. The restart half survives
        below.

Everything that was still true was kept and moved onto the engine database. The
migration tests at the end are untouched: they exercise the migration framework
and the price stream, and both survive M5 exactly as they were.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import catalog
from scrapex import catalog_models as models
from scrapex import db as legacy_db
from scrapex.databases import (
    DatabaseKindError,
    DatabaseRegistry,
    EngineDatabase,
    GeneralDatabase,
    MarketLensDatabase,
)
from scrapex.webui.app import create_app

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def test_restore_refuses_the_wrong_kind_without_displacing_live_data(tmp_path: Path):
    """A RESTORE IS THE MOST DANGEROUS THING A USER CAN DO BY HAND, because it
    is the one operation whose whole purpose is to overwrite the live file.

    The refusal has to happen BEFORE anything moves. A check that ran after the
    displacement would leave the owner with neither the backup he wanted nor the
    database he had.
    """
    engine = EngineDatabase(tmp_path / "scrapex-engine.db")
    other = MarketLensDatabase(tmp_path / "marketlens.db")
    engine.initialize()
    other.initialize()
    original = engine.path.read_bytes()

    with pytest.raises(DatabaseKindError, match="expected a engine database"):
        engine.restore(other.path)

    assert engine.path.read_bytes() == original, "the live database was overwritten"
    assert not list(tmp_path.glob("scrapex-engine.replaced-*.db")), (
        "the live database was displaced before the backup was even checked")


def test_backup_then_restore_returns_the_database_to_the_backed_up_moment(tmp_path):
    """The pair only means anything together: a backup nobody can restore is a
    file, and a restore with nothing to restore from is a delete."""
    engine = EngineDatabase(tmp_path / "scrapex-engine.db")
    engine.initialize()
    engine.write(lambda conn: catalog.register_site(conn, models.SiteCreate(
        site_key="before_backup", display_name="Before",
        base_url="https://before.example")))
    backup = engine.backup(tmp_path / "backups")
    engine.write(lambda conn: catalog.register_site(conn, models.SiteCreate(
        site_key="after_backup", display_name="After",
        base_url="https://after.example")))

    # The write lock is the engine's, and it is still exactly one lock — which
    # is most of the point of one file.
    with legacy_db.write_lock(engine.path, timeout_s=0.1):
        pass

    displaced = engine.restore(backup)

    restored = engine.connect()
    try:
        keys = [row[0] for row in restored.execute(
            "SELECT site_key FROM site_profile ORDER BY site_profile_id LIMIT 10")]
    finally:
        restored.close()

    assert keys == ["before_backup"]
    assert displaced.is_file(), (
        "the replaced database was deleted rather than kept beside the new one")


def test_moving_the_workspace_moves_the_database_the_pointer_names(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The pointer is the answer to "which file is live", and a move that
    changed the file without changing the pointer would leave the next launch
    opening the old one."""
    from scrapex import storage

    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "legacy-location.json")
    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "engine" / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    client = TestClient(create_app(databases=registry))

    response = client.post("/api/storage/move", json={"folder": str(tmp_path / "moved")})

    assert response.status_code == 200, response.text
    followed = DatabaseRegistry.read(registry.pointer_file)
    assert followed.engine.path == tmp_path / "moved" / "scrapex-engine.db"
    assert followed.health()["engine"]["status"] == "Healthy"


def test_migration_18_survives_a_database_with_job_history(tmp_path):
    """The draft's blind spot, hit live on the owner's warehouse: every test
    database was FRESH, so the crawl_job rebuild always dropped a parent with
    no children. A real database has job_log_entry rows pointing at it — and
    PRAGMA foreign_keys is a silent no-op inside the runner's transaction, so
    the script's own OFF did nothing and init-db rolled back with
    'FOREIGN KEY constraint failed'. The runner now suspends enforcement
    around the script and foreign_key_check guards the commit."""
    from scrapex.databases.domain import MarketLensDatabase

    path = tmp_path / "marketlens.db"
    db = MarketLensDatabase(path)
    db.initialize()

    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, status, source_keys) "
            "VALUES ('job_x', 'update', 'completed', '[\"GPP_ENERGY\"]')")
        job_id = conn.execute("SELECT job_id FROM crawl_job").fetchone()[0]
        conn.execute(
            "INSERT INTO job_log_entry (job_id, level, message) "
            "VALUES (?, 'info', 'a line that must survive the rebuild')", (job_id,))
        conn.commit()
        # The new status is writable — the whole point of migration 18 — and
        # the child row still points at its job after the table rebuild.
        conn.execute("UPDATE crawl_job SET status='completed_with_errors' "
                     "WHERE job_id=?", (job_id,))
        conn.commit()
        kept = conn.execute(
            "SELECT COUNT(*) FROM job_log_entry l JOIN crawl_job j "
            "ON j.job_id = l.job_id").fetchone()[0]
        assert kept == 1
    finally:
        conn.close()


def test_a_migration_that_orphans_rows_is_rolled_back_not_committed(tmp_path):
    """Enforcement is suspended around migration scripts, so the compensator
    must have teeth: a rebuild that drops a parent WITHOUT restoring it may
    not commit, and the database must come back exactly as it was."""
    import pytest as _pytest

    from scrapex.databases.domain import (
        DatabaseMigrationError, GeneralDatabase, Migration,
    )

    good = tmp_path / "0001_base.sql"
    good.write_text(
        "PRAGMA application_id = 1398294350;\n"
        "CREATE TABLE parent (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id));\n"
        "INSERT INTO parent VALUES (1);\nINSERT INTO child VALUES (1);\n"
        "CREATE TABLE scrapex_meta (key TEXT PRIMARY KEY, value TEXT);\n"
        "INSERT INTO scrapex_meta VALUES ('database_kind', 'general');\n"
        # The runner's checksum audit writes here after every stream run.
        "CREATE TABLE database_migration (\n"
        "  migration_number INTEGER PRIMARY KEY, migration_name TEXT NOT NULL,\n"
        "  sha256 TEXT NOT NULL,\n"
        "  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));\n"
        "PRAGMA user_version = 1;\n", encoding="utf-8")
    bad = tmp_path / "0002_orphan.sql"
    bad.write_text("DROP TABLE parent;\nPRAGMA user_version = 2;\n", encoding="utf-8")

    class _Base(GeneralDatabase):
        def __init__(self, path):
            super().__init__(path)
            self._migrations = (Migration(1, good),)

    class _Rig(GeneralDatabase):
        def __init__(self, path):
            super().__init__(path)
            self._migrations = (Migration(1, good), Migration(2, bad))

    # The database must EXIST first: a brand-new file that fails mid-creation
    # is deliberately removed whole, which is a different (also correct)
    # answer. The dangerous case is an owner's existing database.
    _Base(tmp_path / "rig.db").initialize()

    with _pytest.raises(DatabaseMigrationError, match="pointing at nothing"):
        _Rig(tmp_path / "rig.db").initialize()

    import sqlite3
    conn = sqlite3.connect(tmp_path / "rig.db")
    assert conn.execute("SELECT COUNT(*) FROM parent").fetchone()[0] == 1, \
        "the orphaning migration committed anyway"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()


def test_a_missing_price_migration_is_named_not_a_nameerror():
    """Both guards in _marketlens_plan raised an exception class that did not
    exist, so a renamed price migration reported `NameError` and named nothing.
    The stop was never in doubt; the diagnosis was.
    """
    import pytest
    from scrapex.databases import domain

    original = domain._MARKETLENS_LEGACY_NUMBERS
    domain._MARKETLENS_LEGACY_NUMBERS = original + (9999,)
    try:
        with pytest.raises(domain.MigrationStreamError) as caught:
            domain._marketlens_plan()
    finally:
        domain._MARKETLENS_LEGACY_NUMBERS = original

    assert "9999" in str(caught.value)          # says WHICH migration is gone
    assert issubclass(domain.MigrationStreamError, RuntimeError)
