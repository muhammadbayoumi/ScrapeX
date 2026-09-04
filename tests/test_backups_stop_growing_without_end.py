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
    """WHY A SECOND ENTRY POINT EXISTS AT ALL. The path that reliably makes copies
    is the guarded upgrade, and it runs while the database is at a schema this build
    does not read — below the baseline (`R-84`) it cannot be opened at all, which is
    the state that was making one full copy per engine launch. `prune_backups(conn,
    ...)` cannot be called from there, and that is the whole reason 963,768,320 bytes
    of pre-upgrade copies accumulated beside a 316 MB warehouse while a policy that
    already recognised them sat one caller away.
    """
    _conn, db = warehouse
    for i in range(5):
        _make(db, f"scrapex-engine.pre-upgrade-2026010{i}T000000Z.backup.db", i + 1)
    assert storage.backup_tag(
        db.with_name("scrapex-engine.pre-upgrade-20260101T000000Z.backup.db"),
        db) == "pre-upgrade", "the policy does not recognise its own file name"

    freed, removed = storage.prune_backups_at(db, keep=2)

    assert len(removed) == 3, removed
    assert freed > 0
    left = sorted(p.name for p in db.parent.glob("*pre-upgrade*"))
    assert left == ["scrapex-engine.pre-upgrade-20260103T000000Z.backup.db",
                    "scrapex-engine.pre-upgrade-20260104T000000Z.backup.db"], left
    assert db.is_file(), "the live database was removed"


def test_a_pruned_copy_takes_its_journal_files_with_it(warehouse):
    """A `-wal` without the file it journalled is meaningless, and `list_backups`
    already refuses to offer one as restorable. Three orphan pairs sit beside the
    owner's warehouse today, left where a copy's `.db` went and its sidecars did
    not."""
    _conn, db = warehouse
    for i in range(2):
        copy = _make(db, f"scrapex-engine.pre-upgrade-2026010{i}T000000Z.backup.db", i + 1)
        for suffix in ("-wal", "-shm"):
            pathlib.Path(f"{copy}{suffix}").write_bytes(b"journal")

    storage.prune_backups_at(db, keep=1)

    assert not list(db.parent.glob("*20260100*")), \
        "the pruned copy left its journal files behind"
    assert pathlib.Path(f"{db.with_name('scrapex-engine.pre-upgrade-20260101T000000Z.backup.db')}-wal") \
        .is_file(), "the surviving copy lost its journal"


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
