"""Spec 17: where the warehouse lives, and keeping it healthy.

Every test redirects POINTER_FILE and works on a temp database. A test that
touched the real pointer would move the machine's actual warehouse.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex import settings, storage
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row


@pytest.fixture(autouse=True)
def isolated_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "home" / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def conn(db_path):
    c = dbmod.connect(db_path)
    try:
        yield c
    finally:
        c.close()


# ---- the pointer, and refusing to invent a warehouse -------------------------

def test_without_a_pointer_the_default_location_is_used():
    assert storage.current_location() == dbmod.DEFAULT_DB_PATH


def test_the_pointer_is_written_atomically_and_read_back(tmp_path):
    storage.write_pointer(tmp_path / "elsewhere" / "harvest.db")
    assert storage.read_pointer() == tmp_path / "elsewhere" / "harvest.db"
    assert not (storage.POINTER_FILE.with_suffix(".json.tmp")).exists()


def test_a_recorded_database_that_vanished_is_an_error_not_a_fresh_start(tmp_path):
    """The hazard this guards: a pointer at an unplugged drive would otherwise
    let db.connect mint an empty warehouse, and the next crawl would fork into
    it while five years of history sat unreachable on the disconnected disk."""
    storage.write_pointer(tmp_path / "unplugged" / "harvest.db")
    with pytest.raises(storage.StorageUnavailableError, match="not there"):
        storage.resolve_db_path()


def test_a_missing_default_path_is_a_normal_first_run(tmp_path, monkeypatch):
    """Only a POINTER makes a location 'recorded'. A default that does not exist
    yet must still start cleanly, or a new install cannot begin."""
    monkeypatch.setattr(dbmod, "DEFAULT_DB_PATH", tmp_path / "new" / "harvest.db")
    assert storage.resolve_db_path() == tmp_path / "new" / "harvest.db"


def test_a_corrupt_pointer_falls_back_instead_of_crashing(tmp_path):
    storage.POINTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    storage.POINTER_FILE.write_text("{not json", encoding="utf-8")
    assert storage.read_pointer() is None


# ---- measuring and health ----------------------------------------------------

def test_size_and_health_report_a_real_database(db_path):
    sizes = storage.measure(db_path)
    assert sizes["db_bytes"] > 0 and sizes["total_bytes"] >= sizes["db_bytes"]
    verdict = storage.health(db_path)
    assert verdict["status"] == "healthy" and verdict["ok"] is True


def test_health_names_a_missing_database_without_creating_one(tmp_path):
    absent = tmp_path / "nothing.db"
    assert storage.health(absent)["status"] == "missing"
    assert not absent.exists(), "checking health must never create a database"


def test_health_reports_an_unreadable_file_as_a_word_not_a_crash(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is definitely not a sqlite database" * 20)
    verdict = storage.health(junk)
    assert verdict["ok"] is False and verdict["status"] == "unreadable"


def test_health_refuses_an_empty_sqlite_file(tmp_path):
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    verdict = storage.health(empty)
    assert verdict["ok"] is False and verdict["status"] == "not_scrapex"
    assert "empty" in verdict["detail"].lower()


def test_health_distinguishes_foreign_sqlite_from_a_scrapex_warehouse(tmp_path):
    foreign = tmp_path / "foreign.db"
    conn = sqlite3.connect(str(foreign))
    try:
        conn.execute("CREATE TABLE contacts(name TEXT)")
        conn.commit()
    finally:
        conn.close()
    verdict = storage.health(foreign)
    assert verdict["ok"] is False and verdict["status"] == "not_scrapex"
    assert "not a ScrapeX warehouse" in verdict["detail"]


def test_repair_refuses_a_foreign_sqlite_database(tmp_path):
    foreign = tmp_path / "foreign.db"
    conn = sqlite3.connect(str(foreign))
    conn.execute("CREATE TABLE contacts(name TEXT)")
    conn.execute("INSERT INTO contacts VALUES ('Ada')")
    conn.commit()
    conn.close()

    with pytest.raises(storage.StorageRefused, match="Refusing to repair"):
        storage.repair(foreign)

    check = sqlite3.connect(str(foreign))
    try:
        assert check.execute("SELECT name FROM contacts").fetchall() == [("Ada",)]
    finally:
        check.close()


def test_health_accepts_a_legacy_v1_scrapex_warehouse_for_migration(tmp_path):
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(legacy))
    try:
        conn.executescript(dbmod.SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    verdict = storage.health(legacy)
    assert verdict["ok"] is True and verdict["status"] == "healthy"


def test_health_refuses_a_warehouse_from_a_newer_engine(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
    finally:
        conn.close()
    verdict = storage.health(db_path)
    assert verdict["ok"] is False and verdict["status"] == "incompatible"
    assert "Update ScrapeX" in verdict["detail"]


# ---- backups -----------------------------------------------------------------

def test_a_backup_is_a_usable_database_not_a_torn_copy(conn, db_path):
    result = storage.backup_now(conn, db_path)
    assert result.ok
    assert storage.health(result.location)["ok"] is True


def test_a_backup_beside_the_database_says_so(conn, db_path):
    """An owner who reads 'backed up' and loses the drive has been misled."""
    assert "does not survive that drive failing" in storage.backup_now(conn, db_path).detail


def test_a_backup_folder_on_another_disk_is_honoured(conn, db_path, tmp_path):
    settings.save(conn, {"backup_folder": str(tmp_path / "elsewhere")})
    result = storage.backup_now(conn, db_path)
    assert str(tmp_path / "elsewhere") in result.location
    assert storage.list_backups(db_path, tmp_path / "elsewhere")


def test_backing_up_nothing_is_refused(conn, tmp_path):
    with pytest.raises(storage.StorageRefused, match="no database"):
        storage.backup_now(conn, tmp_path / "absent.db")


# ---- restore -----------------------------------------------------------------

def test_a_restore_moves_the_current_database_aside_rather_than_overwriting(conn, db_path):
    backup = Path(storage.backup_now(conn, db_path).location)
    conn.close()
    result = storage.restore(db_path, backup)
    assert result.ok and "still on disk as" in result.detail
    displaced = list(db_path.parent.glob("harvest.replaced-*.db"))
    assert displaced, "the database that was replaced must still exist"


def test_an_unhealthy_backup_is_never_put_in_place(db_path, tmp_path):
    junk = tmp_path / "bad.backup.db"
    junk.write_bytes(b"corrupt" * 100)
    with pytest.raises(storage.StorageRefused, match="health check"):
        storage.restore(db_path, junk)
    assert storage.health(db_path)["ok"], "the live database must be untouched"


def test_a_foreign_but_healthy_sqlite_file_is_never_restored(db_path, tmp_path):
    foreign = tmp_path / "someone-elses.db"
    conn = sqlite3.connect(str(foreign))
    try:
        conn.execute("CREATE TABLE contacts(name TEXT)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(storage.StorageRefused, match="health check"):
        storage.restore(db_path, foreign)

    assert storage.health(db_path)["ok"], "the live warehouse must remain in place"
    conn = sqlite3.connect(str(db_path))
    try:
        triggers = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    finally:
        conn.close()
    assert "trg_price_obs_no_update" in triggers


def test_restore_validates_the_copy_before_moving_the_live_database(conn, db_path,
                                                                    tmp_path, monkeypatch):
    backup = Path(storage.backup_now(conn, db_path).location)
    conn.close()
    real_copy = storage.shutil.copy2

    def corrupt_copy(source, destination):
        real_copy(source, destination)
        Path(destination).write_bytes(b"copy failed partway")

    monkeypatch.setattr(storage.shutil, "copy2", corrupt_copy)
    with pytest.raises(storage.StorageRefused, match="copied backup"):
        storage.restore(db_path, backup)

    assert storage.health(db_path)["ok"], "validation happens before the live switch"
    assert not db_path.with_name(db_path.name + ".restore-incoming").exists()


def test_copy_verification_includes_generic_catalogue_tables(db_path, tmp_path):
    source = db_path
    copied = tmp_path / "copied.db"
    source_conn = dbmod.connect(source)
    try:
        source_conn.execute(
            "INSERT INTO site_profile (site_key, display_name, base_url) VALUES (?,?,?)",
            ("example_site", "Example", "https://example.com/"),
        )
        source_conn.commit()
        destination_conn = sqlite3.connect(str(copied))
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
    finally:
        source_conn.close()

    assert storage._same_contents(source, copied) is True
    copied_conn = sqlite3.connect(str(copied))
    try:
        copied_conn.execute("DELETE FROM site_profile")
        copied_conn.commit()
    finally:
        copied_conn.close()
    assert storage._same_contents(source, copied) is False


# ---- maintenance -------------------------------------------------------------

def test_compacting_keeps_every_row(conn, db_path):
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    storage.compact(conn, db_path)
    after = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    assert after == before > 0


def test_repair_on_a_healthy_database_says_it_was_already_healthy(db_path):
    assert "already healthy" in storage.repair(db_path).detail


def test_repair_refuses_to_claim_it_fixed_real_damage(tmp_path, monkeypatch):
    """An index rebuild cannot recover damaged pages, and must not imply it did."""
    monkeypatch.setattr(storage, "health", lambda p: {
        "ok": False, "status": "damaged", "problems": ["page 4 is broken"], "detail": "x"})
    path = tmp_path / "h.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    result = storage.repair(path)
    assert result.ok is False and "Restore from a backup" in result.detail


def test_export_puts_a_consistent_copy_where_asked(conn, db_path, tmp_path):
    result = storage.export_database(conn, db_path, tmp_path / "usb")
    assert result.ok and storage.health(result.location)["ok"]


# ---- moving the warehouse ----------------------------------------------------

def test_a_move_never_overwrites_a_database_already_there(db_path, tmp_path):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "harvest.db").write_bytes(b"someone else's data")
    check = storage.check_move(db_path, occupied)
    assert check.ok is False and "will not overwrite" in check.reason


def test_a_move_refuses_a_folder_it_cannot_write_to(db_path, tmp_path, monkeypatch):
    def refuse(*_a, **_k):
        raise OSError("permission denied")
    monkeypatch.setattr(Path, "write_bytes", refuse)
    check = storage.check_move(db_path, tmp_path / "locked")
    assert check.ok is False and "cannot write" in check.reason


def test_a_move_warns_about_a_removable_drive_but_still_allows_it(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "drive_kind", lambda p: "removable")
    check = storage.check_move(db_path, tmp_path / "usb")
    assert check.ok is True
    assert "removable drive" in check.warning and "crawl in progress will fail" in check.warning


def test_moving_carries_every_observation_and_leaves_the_original_on_disk(conn, db_path, tmp_path):
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    conn.close()

    result = storage.migrate_location(db_path, tmp_path / "newhome")
    assert result.ok

    moved = tmp_path / "newhome" / "harvest.db"
    assert storage.read_pointer() == moved, "the pointer is the commit point"
    check = dbmod.connect(moved)
    try:
        assert check.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == before
    finally:
        check.close()
    assert list(db_path.parent.glob("harvest.moved-*.db")), "the original is kept, not deleted"


def test_a_failed_copy_leaves_the_database_exactly_where_it_was(conn, db_path, tmp_path, monkeypatch):
    """Everything before the pointer write must be undone by deleting a file we
    created — the warehouse never stops being at the old path."""
    conn.close()

    # sqlite3.Connection is immutable, so the failure is injected by arming a
    # dying connect() only AFTER the rollback backup has been taken for real —
    # otherwise the move aborts one step earlier and this proves nothing about
    # the copy step it is meant to cover.
    armed = []
    real_connect = sqlite3.connect
    real_backup_database = storage.backup_database

    class DyingConnection:
        """A real connection whose online backup fails partway, as a full disk
        or a drive pulled mid-write would."""

        def __init__(self, real):
            self._real = real

        def backup(self, *_a, **_k):
            raise sqlite3.OperationalError("disk gave up")

        def __enter__(self):
            return self._real.__enter__()

        def __exit__(self, *exc):
            return self._real.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._real, name)

    def take_backup_then_arm(*a, **k):
        made = real_backup_database(*a, **k)
        armed.append(True)
        return made

    monkeypatch.setattr(storage, "backup_database", take_backup_then_arm)
    monkeypatch.setattr(storage.sqlite3, "connect", lambda *a, **k: (
        DyingConnection(real_connect(*a, **k)) if armed else real_connect(*a, **k)))

    with pytest.raises(sqlite3.OperationalError):
        storage.migrate_location(db_path, tmp_path / "newhome")

    monkeypatch.setattr(storage.sqlite3, "connect", real_connect)
    assert db_path.exists() and storage.health(db_path)["ok"]
    assert storage.read_pointer() is None, "nothing committed, so nothing points away"
    assert not (tmp_path / "newhome" / "harvest.db.incoming").exists()


def test_a_copy_that_does_not_match_is_refused_before_the_switch(conn, db_path, tmp_path, monkeypatch):
    conn.close()
    monkeypatch.setattr(storage, "_same_contents", lambda a, b: False)
    with pytest.raises(storage.StorageRefused, match="did not match"):
        storage.migrate_location(db_path, tmp_path / "newhome")
    assert storage.read_pointer() is None
    assert db_path.exists()


# ---- the status the interface renders ----------------------------------------

def test_status_carries_everything_a_screen_needs(conn, db_path):
    status = storage.storage_status(conn, db_path)
    for key in ("path", "folder", "sizes", "health", "backups", "backup_folder",
                "drive_kind", "ready", "blocker"):
        assert key in status, f"storage_status is missing {key}"
    assert status["ready"] is True and status["blocker"] == ""
