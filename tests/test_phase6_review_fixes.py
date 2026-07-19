"""Regressions for the defects an adversarial review found in Phase 6.

Each test names the wrong outcome it prevents. They are gathered in one file
because they share a story: the storage and retention code was correct in the
happy path and wrong in every way a real machine actually behaves — an open file
handle, a lost pointer, a crash between two steps, a stale bookmark.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from scrapex import compaction, db as dbmod, retention, settings, storage
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row

SOURCE = "ELSEWEDYSHOP"
TODAY = "2026-07-19"
HISTORY = [("2026-01-05", "100.00"), ("2026-02-05", "40.00"),
           ("2026-04-05", "900.00"), ("2026-07-05", "140.00")]


@pytest.fixture(autouse=True)
def isolated_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "home" / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    entry = make_entry()
    for date, price in HISTORY:
        ingest_payloads(conn, entry, [make_payload(
            [one_row(effective_price=price)], scraped_at=f"{date}T10:00:00Z")])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def conn(db_path):
    c = dbmod.connect(db_path)
    try:
        yield c
    finally:
        try:
            c.close()
        except sqlite3.ProgrammingError:
            pass


def aggressive(conn) -> str:
    retention.save_policy(conn, SOURCE, detail_days=30,
                          older_than_action=retention.ARCHIVE_ONLY)
    conn.commit()
    return retention.policy_digest(retention.get_policies(conn))


# ---- CRITICAL: a lost pointer must not resurrect a superseded database -------

def test_a_superseded_database_refuses_to_be_opened_as_live(conn, db_path, monkeypatch):
    """The reviewed failure, end to end.

    The caller holds the database open (the API route does), so on Windows the
    cosmetic rename fails and the predecessor keeps the name harvest.db — which
    is the DEFAULT path. Lose location.json and the fallback used to open the
    PRE-compaction archive as live: everything crawled since becomes invisible
    and the next crawl appends into the archive.
    """
    monkeypatch.setattr(dbmod, "DEFAULT_DB_PATH", db_path)
    digest = aggressive(conn)
    compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)

    storage.clear_pointer()
    with pytest.raises(storage.StorageUnavailableError, match="superseded"):
        storage.resolve_db_path()


def test_the_seal_is_recorded_inside_the_file_not_only_in_its_name(conn, db_path):
    digest = aggressive(conn)
    result = compaction.compact_warehouse(conn, db_path, today=TODAY,
                                          expected_digest=digest)
    assert storage.sealed_at(result.sealed_path), "the predecessor carries no seal"
    assert not storage.sealed_at(result.built_path), "the live database must not be sealed"


def test_undoing_a_compaction_makes_the_archive_live_again(conn, db_path):
    digest = aggressive(conn)
    result = compaction.compact_warehouse(conn, db_path, today=TODAY,
                                          expected_digest=digest)
    compaction.undo_compaction(result.sealed_path)
    assert not storage.sealed_at(result.sealed_path), \
        "an unsealed archive is live again and must not refuse to open"


def test_after_a_move_a_lost_pointer_says_where_the_warehouse_went(conn, db_path,
                                                                   tmp_path, monkeypatch):
    """With the file closed the rename succeeds, so nothing is left at the
    default path. Starting a fresh empty warehouse there would leave the real
    history somewhere the owner is never told about — so the retired sibling is
    read for the forwarding address instead."""
    conn.close()
    monkeypatch.setattr(dbmod, "DEFAULT_DB_PATH", db_path)
    storage.migrate_location(db_path, tmp_path / "newhome")
    storage.clear_pointer()
    with pytest.raises(storage.StorageUnavailableError) as raised:
        storage.resolve_db_path()
    assert str(tmp_path / "newhome" / "harvest.db") in str(raised.value)


# ---- CRITICAL: the worker must follow the warehouse -------------------------

def test_the_job_worker_reopens_when_the_database_moves(db_path, tmp_path):
    """A worker holding the old file kept crawling into a database nothing else
    reads, so every observation it gathered was invisible."""
    from scrapex.jobs import JobRunner

    moved = tmp_path / "elsewhere" / "harvest.db"
    moved.parent.mkdir(parents=True)
    shutil.copy(db_path, moved)

    where = [str(db_path)]
    runner = JobRunner(str(db_path), lambda: None, path_provider=lambda: where[0])
    conn = dbmod.connect(db_path)
    try:
        same = runner._follow_the_warehouse(conn)
        assert same is conn, "an unchanged path must not churn the connection"
        where[0] = str(moved)
        reopened = runner._follow_the_warehouse(conn)
        assert reopened is not conn
        assert reopened.execute(
            "SELECT COUNT(*) FROM price_observation").fetchone()[0] == len(HISTORY)
        reopened.close()
    finally:
        try:
            conn.close()
        except sqlite3.ProgrammingError:
            pass


# ---- CRITICAL: restore must not install just any database -------------------

def test_restore_refuses_a_database_that_is_not_a_warehouse(db_path, tmp_path):
    stranger = tmp_path / "stranger.backup.db"
    other = sqlite3.connect(str(stranger))
    other.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT)")
    other.commit()
    other.close()
    with pytest.raises(storage.StorageRefused, match="not a ScrapeX warehouse"):
        storage.restore(db_path, stranger)


def test_restore_refuses_a_warehouse_without_the_append_only_triggers(db_path, tmp_path):
    """A database whose price history can be edited would silently end the one
    guarantee the product rests on."""
    tampered = tmp_path / "tampered.backup.db"
    shutil.copy(db_path, tampered)
    conn = sqlite3.connect(str(tampered))
    conn.execute("DROP TRIGGER trg_price_obs_no_delete")
    conn.commit()
    conn.close()
    with pytest.raises(storage.StorageRefused, match="not append-only"):
        storage.restore(db_path, tampered)


def test_an_empty_file_is_not_reported_as_healthy(tmp_path):
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    verdict = storage.health(empty)
    assert verdict["ok"] is False and verdict["status"] == "empty"


# ---- HIGH: a stale pin must not block every future compaction ---------------

def test_a_pin_pointing_at_nothing_does_not_block_compaction(conn, db_path):
    """A pin is a bookmark. One that matches no observation used to make
    verification demand a row nobody could supply, and every compaction from
    then on was refused with a message that read like data loss."""
    offer = conn.execute("SELECT offer_id FROM price_observation LIMIT 1").fetchone()[0]
    retention.pin(conn, offer, "1999-01-01", "a-hash-that-matches-nothing")
    conn.commit()
    digest = aggressive(conn)

    result = compaction.compact_warehouse(conn, db_path, today=TODAY,
                                          expected_digest=digest)
    assert result.ok
    # ...and the pin itself is untouched: ScrapeX does not delete the owner's marks.
    live = dbmod.connect(Path(result.built_path))
    try:
        assert live.execute("SELECT COUNT(*) FROM retention_pin").fetchone()[0] == 1
    finally:
        live.close()


def test_a_pin_that_does_match_is_still_protected(conn, db_path):
    row = conn.execute("SELECT offer_id, business_date, record_hash FROM price_observation "
                       "WHERE effective_price = 100.0").fetchone()
    retention.pin(conn, row[0], row[1], row[2])
    conn.commit()
    assert (row[0], row[1], row[2]) in retention.protected_keys(conn)
    assert (row[0], row[1], row[2]) in retention.protected_keys_independently(conn)


# ---- HIGH: Repair must not permanently block compaction ---------------------

def test_repair_does_not_block_every_future_compaction(conn, db_path):
    """PRAGMA optimize creates sqlite_stat1. Counting SQLite's own tables meant
    one press of Repair made source and successor differ forever."""
    conn.close()
    storage.repair(db_path)

    again = dbmod.connect(db_path)
    try:
        assert again.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_stat1'").fetchone()[0] == 1
        digest = aggressive(again)
        result = compaction.compact_warehouse(again, db_path, today=TODAY,
                                              expected_digest=digest)
        assert result.ok, result.problems
    finally:
        again.close()


# ---- HIGH: backups must not vanish after a compaction -----------------------

def test_backups_are_still_listed_after_a_compaction(conn, db_path):
    """Globbing on the LIVE file's stem lost every backup at exactly the moment
    the owner would most want one."""
    storage.backup_now(conn, db_path)
    conn.commit()
    digest = aggressive(conn)
    result = compaction.compact_warehouse(conn, db_path, today=TODAY,
                                          expected_digest=digest)

    live = dbmod.connect(Path(result.built_path))
    try:
        assert storage.list_backups(result.built_path,
                                    storage.backup_folder(live, result.built_path))
    finally:
        live.close()


def test_the_original_warehouse_name_survives_every_lineage_suffix():
    for name in ("harvest.db", "harvest.compact-20260719T101010Z.db",
                 "harvest.sealed-20260719T101010Z.db",
                 "harvest.moved-20260719T101010Z.db"):
        assert storage.base_stem(Path("/x") / name) == "harvest"


# ---- HIGH: an interrupted move must be completable --------------------------

def test_an_interrupted_move_can_be_finished_rather_than_blocked(conn, db_path, tmp_path):
    """A crash between the copy landing and the pointer write left a complete
    copy in place. Refusing it outright blocked the retry permanently."""
    conn.close()
    destination = tmp_path / "newhome"
    destination.mkdir()
    shutil.copy(db_path, destination / "harvest.db")   # the stranded copy

    check = storage.check_move(db_path, destination)
    assert check.ok and check.resumable
    assert "interrupted move" in check.warning

    result = storage.migrate_location(db_path, destination)
    assert result.ok and "Finished an interrupted move" in result.detail
    assert storage.read_pointer() == destination / "harvest.db"


def test_someone_elses_database_is_still_refused(conn, db_path, tmp_path):
    """Resuming must be judged on CONTENT. A different database that happens to
    sit at the destination is not our stranded copy."""
    conn.close()
    destination = tmp_path / "newhome"
    destination.mkdir()
    other = sqlite3.connect(str(destination / "harvest.db"))
    other.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY)")
    other.commit()
    other.close()

    check = storage.check_move(db_path, destination)
    assert check.ok is False and "will not overwrite" in check.reason


# ---- MEDIUM/LOW ------------------------------------------------------------

def test_a_failed_compaction_leaves_nothing_that_looks_promotable(conn, db_path, monkeypatch):
    """A half-built file must never be mistakable for a verified successor."""
    digest = aggressive(conn)
    monkeypatch.setattr(compaction, "verify_successor", lambda a, b: ["invented"])
    with pytest.raises(compaction.CompactionAborted):
        compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    assert not list(db_path.parent.glob("*.compact-*"))
    assert not list(db_path.parent.glob("*.building-*"))


def test_a_compaction_refuses_when_the_disk_is_too_full(conn, db_path, monkeypatch):
    monkeypatch.setattr(storage, "free_space", lambda folder: 1)
    digest = aggressive(conn)
    with pytest.raises(compaction.CompactionAborted, match="needs about"):
        compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    assert db_path.exists() and storage.read_pointer() is None


def test_two_previews_do_not_share_a_trial_filename(conn, db_path, monkeypatch):
    names = []
    real_build = compaction.build_successor

    def record(src, out, **kwargs):
        names.append(Path(out).name)
        return real_build(src, out, **kwargs)

    monkeypatch.setattr(compaction, "build_successor", record)
    aggressive(conn)
    compaction.preview(conn, db_path, today=TODAY)
    monkeypatch.setattr(settings, "utc_now", lambda: "2030-01-01T00:00:01Z")
    compaction.preview(conn, db_path, today=TODAY)
    assert len(set(names)) == 2, "two previews collided on one trial file"


def test_a_global_exclusion_is_inherited_by_every_dataset(conn):
    retention.save_policy(conn, retention.DEFAULT_KEY, detail_days=30,
                          older_than_action=retention.ARCHIVE_ONLY, excluded=True)
    conn.commit()
    assert retention.policy_for(conn, SOURCE).excluded is True
    assert retention.policy_for(conn, SOURCE).is_noop is True


def test_a_zero_request_interval_is_honoured_not_silently_replaced():
    """A setting the owner changed must take effect, or the field is a lie."""
    from scrapex.connectors.base import resolve_fetcher

    fetcher = resolve_fetcher(make_entry(), {"min_interval_s": 0, "timeout_s": 5})
    assert fetcher._min_interval_s == 0
    assert fetcher._client.timeout.read == 5
    fetcher.close()


def test_compacting_reports_the_size_after_the_wal_is_merged(conn, db_path):
    """Under WAL the main file lags behind, so measuring it first could report
    a real reduction as growth."""
    result = storage.compact(conn, db_path)
    assert result.ok
    assert "-wal" not in result.detail
    assert db_path.with_name(db_path.name + "-wal").stat().st_size == 0 \
        if db_path.with_name(db_path.name + "-wal").exists() else True
