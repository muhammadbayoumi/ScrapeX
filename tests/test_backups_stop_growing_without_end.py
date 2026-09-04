"""1.61 GB of backups against a 100 MB warehouse, because nothing removed one.

Measured on the owner's machine 2026-08-04: 37 database files beside a 100 MB
warehouse, 16x its size, the oldest three weeks old. The `rebuild` lineage
alone held 10 files and 491 MB — four of them taken within twenty minutes of
each other on 2026-07-23.

He asked for a policy rather than a one-off sweep, and the distinction matters:
a sweep leaves the next month to grow the same way.

THE SAFETY RULE IS THAT THE POLICY ONLY REMOVES WHAT THIS PRODUCT NAMED.
Three of his files — scrapex-engine.pre0056.backup.db and two like it — were named
by hand before a migration. They carry no stamp, so backup_tag returns "" and
they are never grouped and never pruned.
"""

from __future__ import annotations

import pathlib

import pytest

from scrapex import db as dbmod, storage


@pytest.fixture()
def warehouse(tmp_path):
    db = tmp_path / "scrapex-engine.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    conn.commit()
    return conn, db


def _make(db: pathlib.Path, name: str, order: int) -> pathlib.Path:
    """A file standing in for a backup, with a distinct modification time."""
    path = db.with_name(name)
    path.write_bytes(b"x" * (1024 * order))
    import os
    os.utime(path, (1_780_000_000 + order * 60, 1_780_000_000 + order * 60))
    return path


def test_a_backup_this_product_named_knows_its_lineage(warehouse):
    """Both spellings, because reset predates the shared helper and writes the
    same fact in a different order."""
    _conn, db = warehouse

    assert storage.backup_tag(db.with_name("scrapex-engine.rebuild-20260804T120539Z.backup.db"), db) == "rebuild"
    assert storage.backup_tag(db.with_name("scrapex-engine.reset-backup-20260722T050619Z.db"), db) == "reset"
    assert storage.backup_tag(
        db.with_name("scrapex-engine.pre-wipe-GPP_ENERGY-20260722T115752Z.backup.db"), db
    ) == "pre-wipe-GPP_ENERGY"


def test_a_file_a_person_named_has_no_lineage_and_is_never_pruned(warehouse):
    """THE SAFETY RULE. Three of the owner's files are hand-named copies taken
    before a migration. A policy that guessed at them would delete the only
    copy of a warehouse state nobody can reproduce."""
    _conn, db = warehouse
    for i in range(4):
        _make(db, f"scrapex-engine.pre005{i}.backup.db", i + 1)

    assert storage.backup_tag(db.with_name("scrapex-engine.pre0056.backup.db"), db) == ""
    assert storage.prunable_backups(db) == []


def test_only_the_newest_of_each_lineage_survives(warehouse):
    """Five rebuilds, keep two."""
    _conn, db = warehouse
    for i in range(1, 6):
        _make(db, f"scrapex-engine.rebuild-2026080{i}T120000Z.backup.db", i)

    doomed = {b["name"] for b in storage.prunable_backups(db, keep=2)}

    assert doomed == {"scrapex-engine.rebuild-20260801T120000Z.backup.db",
                      "scrapex-engine.rebuild-20260802T120000Z.backup.db",
                      "scrapex-engine.rebuild-20260803T120000Z.backup.db"}


def test_a_run_of_one_kind_never_evicts_the_only_copy_of_another(warehouse):
    """GROUPING BY LINEAGE IS THE POINT. On the owner's warehouse `rebuild`
    held 10 files while `pre-wipe-SIKAEGSHOP` held the ONLY copy of a source
    that was erased in July. A policy that kept "the newest N backups" would
    have deleted it to make room for a rebuild taken this morning."""
    _conn, db = warehouse
    for i in range(1, 8):
        _make(db, f"scrapex-engine.rebuild-2026080{i}T120000Z.backup.db", 10 + i)
    _make(db, "scrapex-engine.pre-wipe-SIKAEGSHOP-20260725T070151Z.backup.db", 1)

    doomed = {b["name"] for b in storage.prunable_backups(db, keep=3)}

    assert not any("SIKAEGSHOP" in name for name in doomed)
    assert len(doomed) == 4


def test_the_live_database_and_its_sidecars_are_not_backups(warehouse):
    """SQLite leaves -shm and -wal beside a database it has opened, and the
    glob was matching them: the Restore list offered a write-ahead log as
    something you could make live again. 71 entries where there were 25."""
    _conn, db = warehouse
    _make(db, "scrapex-engine.rebuild-20260804T120000Z.backup.db", 3)
    _make(db, "scrapex-engine.rebuild-20260804T120000Z.backup.db-wal", 1)
    _make(db, "scrapex-engine.rebuild-20260804T120000Z.backup.db-shm", 1)

    listed = {b["name"] for b in storage.list_backups(db)}

    assert listed == {"scrapex-engine.rebuild-20260804T120000Z.backup.db"}


def test_pruning_removes_them_and_says_what_it_freed(warehouse):
    """Reversible it is not, so it reports rather than working in silence."""
    conn, db = warehouse
    for i in range(1, 6):
        _make(db, f"scrapex-engine.rebuild-2026080{i}T120000Z.backup.db", i)

    result = storage.prune_backups(conn, db, keep=2)

    assert result.ok and result.rows == 3
    assert "freeing" in result.detail
    assert len(storage.list_backups(db)) == 2


def test_a_new_backup_prunes_after_itself_never_before(warehouse):
    """A policy that made room FIRST would, on the one run where the backup
    then failed, have deleted the old copies for nothing."""
    conn, db = warehouse
    for i in range(1, 5):
        _make(db, f"scrapex-engine.manual-2026080{i}T120000Z.backup.db", i)

    storage.backup_now(conn, db, tag="manual")

    kept = storage.list_backups(db)
    assert len(kept) == storage.backups_kept(conn)
    # The one just taken is among them: a policy that pruned first could have
    # left the newest copy missing.
    assert kept[0]["bytes"] > 0


def test_the_warehouse_says_what_the_policy_would_free(warehouse):
    """A number nobody can see is a number nobody acts on. It rides the verdict
    the Storage page already reads on every visit."""
    conn, db = warehouse
    for i in range(1, 6):
        _make(db, f"scrapex-engine.rebuild-2026080{i}T120000Z.backup.db", i)

    verdict = storage.health(db)

    assert verdict["prunable_backup_bytes"] > 0


# ---- the entry point for a caller with no database open ----------------------

def test_the_policy_runs_with_no_database_open(warehouse):
    """WHY A SECOND ENTRY POINT EXISTS AT ALL. The path that reliably makes copies is
    the guarded upgrade, and it runs while the database is at a schema this build does
    not read — below the baseline (`R-84`) it cannot be opened at all, which is the
    state that was making one full copy per engine launch. `prune_backups(conn, ...)`
    cannot be called from there, and that is the whole reason 963,768,320 bytes of
    pre-upgrade copies accumulated beside a 316 MB warehouse while a policy that
    already recognised them sat one caller away.
    """
    _conn, db = warehouse
    # REAL DATES. `20260100` is not one, and now that the order is read from the NAME
    # (`OP-141`) an unparseable stamp falls back to the file clock and sorts as the
    # NEWEST -- the fallback working correctly, and the old fixture being wrong.
    for i in range(1, 6):
        _make(db, f"scrapex-engine.pre-upgrade-2026010{i}T000000Z.backup.db", i)
    assert storage.backup_tag(
        db.with_name("scrapex-engine.pre-upgrade-20260101T000000Z.backup.db"),
        db) == "pre-upgrade", "the policy does not recognise its own file name"

    freed, removed = storage.prune_backups_at(db, keep=2)

    assert len(removed) == 3, removed
    assert freed > 0
    left = sorted(p.name for p in db.parent.glob("*pre-upgrade*"))
    assert left == ["scrapex-engine.pre-upgrade-20260104T000000Z.backup.db",
                    "scrapex-engine.pre-upgrade-20260105T000000Z.backup.db"], left
    assert db.is_file(), "the live database was removed"


def test_a_pruned_copy_takes_its_journal_files_with_it(warehouse):
    """A `-wal` without the file it journalled is meaningless, and `list_backups`
    already refuses to offer one as restorable. Three orphan pairs sit beside the
    owner's warehouse today, left where a copy's `.db` went and its sidecars did not."""
    _conn, db = warehouse
    for i in range(1, 3):
        copy = _make(db, f"scrapex-engine.pre-upgrade-2026010{i}T000000Z.backup.db", i)
        for suffix in ("-wal", "-shm"):
            pathlib.Path(f"{copy}{suffix}").write_bytes(b"journal")

    storage.prune_backups_at(db, keep=1)

    assert not list(db.parent.glob("*20260101*")), \
        "the pruned copy left its journal files behind"
    survivor = db.with_name("scrapex-engine.pre-upgrade-20260102T000000Z.backup.db")
    assert pathlib.Path(f"{survivor}-wal").is_file(), \
        "the surviving copy lost its journal"


def test_a_partial_copy_is_not_a_backup_the_policy_can_see(warehouse):
    """The other half of the atomicity fix, stated from the policy's side: a `.part`
    file is not a lineage member, is never offered for restore, is never pruned, and
    — the part that matters — does not occupy one of the kept slots."""
    _conn, db = warehouse
    for i in range(1, 4):
        _make(db, f"scrapex-engine.pre-upgrade-2026010{i}T000000Z.backup.db", i)
    torn = _make(db, "scrapex-engine.pre-upgrade-20260109T000000Z.backup.db.part", 9)

    assert storage.backup_tag(torn, db) == "", \
        "a partial file was classified as a member of a lineage"
    assert torn.name not in {b["name"] for b in storage.list_backups(db)}

    freed, removed = storage.prune_backups_at(db, keep=2)

    assert torn.is_file(), "the policy deleted a file it does not understand"
    assert len(removed) == 1 and "20260101" in removed[0], removed
    left = sorted(p.name for p in db.parent.glob("*.backup.db"))
    assert left == ["scrapex-engine.pre-upgrade-20260102T000000Z.backup.db",
                    "scrapex-engine.pre-upgrade-20260103T000000Z.backup.db"], left


# ---- OP-141: the deletion is ordered by the clock that wrote the name --------

def _at(db, name: str, mtime: int) -> pathlib.Path:
    """A backup with a chosen modification time, which is the whole subject here."""
    import os

    path = db.with_name(name)
    path.write_bytes(b"x" * 1024)
    os.utime(path, (mtime, mtime))
    return path


def test_a_reset_undo_reset_cycle_does_not_lose_todays_copy(warehouse):
    """THE MEASURED FAILURE. `start_fresh` does not copy the warehouse aside, it
    RENAMES it — and `os.replace` preserves the last-write time, so a `reset-backup`
    carries the WAREHOUSE's clock, not the reset's. `restore` then copies that same
    time back onto the live file with `shutil.copy2`. So every reset in a
    reset / undo / reset cycle produces a file with ONE shared mtime.

    Ordered by mtime, `sorted` is merely stable, so "the newest three" was whichever
    three the glob returned first: measured on four such files with names spanning
    2026-01-01 to 2026-09-04 and `keep=3`, the file deleted was **today's** — the only
    copy of everything the reset had just wiped — and the three kept were the oldest.
    """
    _conn, db = warehouse
    shared = 1_740_000_000                      # one warehouse last-write time
    for stamp in ("20260101T090000Z", "20260401T090000Z",
                  "20260701T090000Z", "20260904T090000Z"):
        _at(db, f"scrapex-engine.reset-backup-{stamp}.db", shared)

    freed, removed = storage.prune_backups_at(db, keep=3)

    assert removed == ["scrapex-engine.reset-backup-20260101T090000Z.db"], removed
    assert (db.parent / "scrapex-engine.reset-backup-20260904T090000Z.db").is_file(), \
        "the newest reset copy was deleted and older ones were kept"
    assert freed > 0


def test_a_copy_carried_in_with_an_older_clock_is_not_treated_as_older(warehouse):
    """`shutil.copy2` preserves the last-write time, so a backup restored from
    another disk arrives with a clock older than the day the product wrote its name.
    The name is the record of when the product acted; the file's clock is not."""
    _conn, db = warehouse
    old_clock = 1_600_000_000
    new_clock = 1_780_000_000
    _at(db, "scrapex-engine.rebuild-20260901T090000Z.backup.db", old_clock)
    _at(db, "scrapex-engine.rebuild-20260101T090000Z.backup.db", new_clock)

    _freed, removed = storage.prune_backups_at(db, keep=1)

    assert removed == ["scrapex-engine.rebuild-20260101T090000Z.backup.db"], removed


def test_the_three_stamp_spellings_order_against_each_other(warehouse):
    """`_STAMP` admits three forms and they do NOT sort as text: `-` is 0x2D and `T` is
    0x54, so `20260601-020000` sorts BELOW `20260101T010000Z`. Parsed and re-formatted,
    they order by the moment they name.

    THE THIRD SPELLING CANNOT BE A FILE ON THIS PLATFORM — NTFS refuses `:` in a name
    (`OSError: [Errno 22] Invalid argument`, measured while writing this) — so it is
    parsed as a string and the two writable ones are ordered as files. That is all the
    platform allows either half of this to be, and saying so is better than a test that
    silently only ever ran on POSIX.
    """
    _conn, db = warehouse
    assert storage.backup_taken_at(
        "scrapex-engine.reset-backup-2026-09-04T03:00:00Z.db", db) == "2026-09-04T03:00:00Z"

    shared = 1_740_000_000
    names = ["scrapex-engine.reset-backup-20260101T010000Z.db",
             "scrapex-engine.reset-backup-20260601-020000.db"]
    for name in names:
        _at(db, name, shared)

    order = [b["name"] for b in storage.list_backups(db)]

    assert order == list(reversed(names)), order
    assert [storage.backup_taken_at(n, db) for n in names] == [
        "2026-01-01T01:00:00Z", "2026-06-01T02:00:00Z"]


def test_a_hand_named_copy_still_falls_back_to_the_file_clock(warehouse):
    """No stamp, no lineage, never pruned — and it still has to take a place in the
    order, because `list_backups` is what the Restore picker renders."""
    _conn, db = warehouse
    _at(db, "scrapex-engine.pre0056.backup.db", 1_600_000_000)
    _at(db, "scrapex-engine.rebuild-20260101T090000Z.backup.db", 1_780_000_000)

    listed = storage.list_backups(db)

    assert [b["name"] for b in listed] == [
        "scrapex-engine.rebuild-20260101T090000Z.backup.db",
        "scrapex-engine.pre0056.backup.db"], [b["name"] for b in listed]
    assert storage.backup_taken_at("scrapex-engine.pre0056.backup.db", db) == ""
    assert storage.prunable_backups(db) == []


def test_the_restore_picker_names_when_the_copy_was_taken(warehouse):
    """The label says "Stored as", and for a `reset-backup` the file's clock is the
    WAREHOUSE's last-write time — a moment that can be months before the reset the file
    is a copy of. It shows `taken_at`, read from the stamp the product wrote."""
    from fastapi.testclient import TestClient

    from scrapex.webui.app import create_app

    conn, db = warehouse
    _at(db, "scrapex-engine.reset-backup-20260904T090000Z.db", 1_600_000_000)

    body = TestClient(create_app(db)).get("/settings").text

    assert "2026-09-04T09:00:00Z" in body, \
        "the picker does not name the moment the copy was taken"
    assert "2020-09-13" not in body, \
        "the picker still shows the file's own clock, which is the warehouse's"
