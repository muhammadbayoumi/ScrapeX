"""Phase 0 of the Drive plan: the three places a backup was trusted unchecked.

`R-43` made Drive the single source of truth for DATA, which puts the whole of
his warehouse on a round trip through a bundle, an upload, a download and a
merge. Everything in this file is a step on that road that reported success
without having established it — measured, not suspected:

  1. `bundle.build` copied the warehouse and hashed the copy. A checksum of a
     corrupt database matches its corrupt self perfectly, so the strongest claim
     a bundle could make about `warehouse.db` was "these are the bytes we
     copied". Now `PRAGMA quick_check` runs before anything is written around it.

  2. `init-db` migrated an EXISTING warehouse with no backup, while
     `cli._upgrade_what_is_only_behind` promised "A BACKUP FIRST, ALWAYS" and
     `registry.ensure_ready` promised "Nothing else in the codebase may migrate
     an existing file". Both sentences were false, and `init-db` is the command
     the product's own refusals send people to — `databases/domain.py`'s
     `Needs upgrade` action names it, and so does
     `warehousemerge._same_shape`. PROVEN on his live warehouse: engine
     migrations 0004…0009 are all stamped `2026-08-22T07:11:47Z` in
     `database_migration`, a v3→v9 upgrade of a 1.1 GB file, and no
     `pre-upgrade` backup exists beside it.

  3. `restore-database` took a path and displaced his only copy with no question
     asked, while `start-fresh` beside it made him type a phrase. The panel's
     `drive-restore` button — which `docs/STATE.md` warned about in capitals —
     turned out not to be destructive at all.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import bundle, cli
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.databases.domain import DomainDatabase, _engine_plan


def _warehouse(path: Path) -> Path:
    """A real engine database at the current schema, through the real stream."""
    EngineDatabase(path).initialize()
    return path


def _behind(path: Path, versions_short: int = 2) -> Path:
    """A real engine database stopped a few migrations early.

    THE REAL MIGRATION FILES, TRUNCATED — not a hand-made schema and not a
    rewritten `user_version`. Lowering the pragma by hand leaves a ledger that
    disagrees with it, and then the thing under test is the disagreement rather
    than the upgrade. A prefix of the stream is exactly what his own v3 warehouse
    was.
    """
    plan = _engine_plan()
    assert versions_short < len(plan)

    class _Earlier(EngineDatabase):
        def __init__(self, where: Path) -> None:
            DomainDatabase.__init__(self, where, plan[:-versions_short])

    _Earlier(path).initialize()
    version = sqlite3.connect(f"file:{path}?mode=ro", uri=True).execute(
        "PRAGMA user_version").fetchone()[0]
    assert version == len(plan) - versions_short, version
    return path


def _damage(path: Path) -> Path:
    """Overwrite one interior page, leaving page 1 — the header and the schema.

    THE FILE MUST STILL OPEN, or the test proves nothing about `quick_check`: a
    database SQLite cannot open at all is refused several layers earlier by the
    backup API. This is the dangerous shape — a warehouse that opens, lists its
    tables, answers simple queries, and has lost a b-tree page.
    """
    conn = sqlite3.connect(path)
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
    finally:
        conn.close()
    raw = bytearray(path.read_bytes())
    at = page_size * (pages // 2)
    raw[at:at + page_size] = b"\xa5" * page_size
    path.write_bytes(bytes(raw))

    check = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        assert check.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] > 0, \
            "the damage went too far — this file no longer opens, so the test " \
            "below would pass for the wrong reason"
        # THE PRECONDITION, ASSERTED RATHER THAN ASSUMED. Which page sits in the
        # middle of the file is a property of the schema and of SQLite's layout,
        # and a future version could put a freelist page there — harmless, and
        # `quick_check` would rightly answer "ok". Then the tests below would fail
        # for a reason that has nothing to do with the guard, and the message
        # would send someone into `bundle.py`. It belongs here instead: widen the
        # damage, do not loosen the guard.
        assert check.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok", \
            "the overwritten page was not one SQLite checks, so this file is not " \
            "damaged in any way `quick_check` can see. Widen the damage in _damage()."
    finally:
        check.close()
    return path


# ---- 1 · a bundle is not built from a damaged warehouse ----------------------

def test_a_damaged_warehouse_is_refused_before_a_bundle_is_written(tmp_path):
    """And nothing is left behind that a caller could mistake for a bundle."""
    source = _damage(_warehouse(tmp_path / "scrapex-engine.db"))
    out = tmp_path / "bundle"

    with pytest.raises(ValueError) as raised:
        bundle.build(source, out)

    assert "damaged" in str(raised.value)
    assert not (out / "manifest.json").is_file(), (
        "a manifest was written for a warehouse SQLite refuses to read, and "
        "`latest.json` may only ever name a bundle that verified")


def test_the_check_refuses_a_damaged_file_when_called_on_its_own(tmp_path):
    """The guard is a function with its own refusal, not a line inside `build`.

    AND WHAT THIS DELIBERATELY DOES NOT CLAIM. `build` checks the COPY rather than
    the source, which catches a source that was already damaged *and* a backup
    torn on the way out. That choice is not observable from outside: the copy is
    made from the source, so no test can hand `build` a healthy source and a
    damaged copy. The distinction is argued in the docstring and asserted only as
    far as it can be — the function refuses damage, and `build` calls it.
    """
    copy = _damage(_warehouse(tmp_path / "warehouse.db"))
    with pytest.raises(ValueError):
        bundle.refuse_a_damaged_warehouse(copy)


def test_a_healthy_warehouse_is_not_refused(tmp_path):
    """The other half of the guard, without which "always raise" would pass."""
    good = _warehouse(tmp_path / "scrapex-engine.db")
    bundle.refuse_a_damaged_warehouse(good)          # must not raise

    report = bundle.build(good, tmp_path / "bundle")
    assert report.ok, [f"{f.path}: {f.problem}" for f in report.faults]
    assert (tmp_path / "bundle" / "warehouse.db").is_file()


# ---- 2 · init-db does not advance a schema without a copy --------------------

def test_init_db_backs_up_a_warehouse_before_it_upgrades_it(tmp_path, capsys):
    path = _behind(tmp_path / "scrapex-engine.db")
    registry = DatabaseRegistry(EngineDatabase(path),
                               pointer_file=tmp_path / "databases.json")

    assert cli._back_up_before_init_db_advances_a_schema(registry) == 0
    copies = sorted(tmp_path.glob("scrapex-engine.pre-upgrade-*.backup.db"))
    assert len(copies) == 1, [p.name for p in tmp_path.iterdir()]
    assert "backed up" in capsys.readouterr().out

    # A COPY THAT OPENS, and at the version it was taken from. `backup_database`
    # once produced an empty database for a missing source and reported success;
    # a backup nobody read back is the same failure wearing a filename.
    conn = sqlite3.connect(f"file:{copies[0]}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA quick_check(1)").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == \
            len(_engine_plan()) - 2
    finally:
        conn.close()


def test_init_db_copies_nothing_when_the_schema_is_already_current(tmp_path):
    """Otherwise every run duplicates a 1.1 GB file for no upgrade at all."""
    path = _warehouse(tmp_path / "scrapex-engine.db")
    registry = DatabaseRegistry(EngineDatabase(path),
                               pointer_file=tmp_path / "databases.json")

    assert cli._back_up_before_init_db_advances_a_schema(registry) == 0
    assert not list(tmp_path.glob("*.backup.db")), \
        "a healthy database applies no migration, so there is nothing to protect"


def test_init_db_refuses_to_advance_a_schema_it_could_not_back_up(
        tmp_path, monkeypatch, capsys):
    """The protection `_upgrade_what_is_only_behind` names, on this path too:
    if the copy cannot be made, nothing is migrated."""
    path = _behind(tmp_path / "scrapex-engine.db")
    was = sqlite3.connect(f"file:{path}?mode=ro", uri=True).execute(
        "PRAGMA user_version").fetchone()[0]
    registry = DatabaseRegistry(EngineDatabase(path),
                               pointer_file=tmp_path / "databases.json")
    monkeypatch.setattr("scrapex.cli.DatabaseRegistry",
                        type("_Fixed", (), {"defaults": staticmethod(lambda: registry)}))
    monkeypatch.setattr("scrapex.archive.backup_database",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no space")))

    assert cli.main(["init-db"]) == 1
    assert "not" in capsys.readouterr().err.lower()

    now = sqlite3.connect(f"file:{path}?mode=ro", uri=True).execute(
        "PRAGMA user_version").fetchone()[0]
    assert now == was, \
        "the schema moved even though the backup failed — the exact trade " \
        "`_upgrade_what_is_only_behind` refuses to make"


def test_init_db_refuses_a_health_report_that_skipped_the_integrity_scan(
        tmp_path, capsys):
    """#251 gave `health()` an `integrity=False` mode for the panel's timed poll —
    measured, and right: `quick_check(1)` and the foreign-key check are O(file
    size) and pushed `/api/health` past the panel's 2.5 s deadline on a 1,067 MB
    warehouse.

    IT ALSO MADE "DAMAGED FILES ARE LEFT ALONE" CONDITIONAL. That claim holds only
    if something looked, so this caller asks for the scan and then checks it
    happened. A report without one cannot tell `Needs upgrade` from damage, and
    acting on it is how a guard becomes the thing it refuses.
    """
    path = _behind(tmp_path / "scrapex-engine.db")
    registry = DatabaseRegistry(EngineDatabase(path),
                               pointer_file=tmp_path / "databases.json")

    class _Unscanned:
        engine = registry.engine

        @staticmethod
        def health(**_kwargs):
            report = registry.health(integrity=True)
            for state in report.values():
                state["integrity_checked"] = False
            return report

    assert cli._back_up_before_init_db_advances_a_schema(_Unscanned) == 1
    assert "integrity" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.backup.db")), \
        "a copy was taken on the strength of a report that never looked at the file"


def test_init_db_asks_for_the_integrity_scan_by_name(tmp_path):
    """The flag is passed rather than left to the default, so a change to the
    default cannot silently widen what this guard will migrate."""
    path = _behind(tmp_path / "scrapex-engine.db")
    asked = {}

    class _Watching:
        engine = EngineDatabase(path)

        @staticmethod
        def health(*, integrity=False):
            asked["integrity"] = integrity
            return DatabaseRegistry(
                EngineDatabase(path), pointer_file=tmp_path / "p.json"
            ).health(integrity=integrity)

    cli._back_up_before_init_db_advances_a_schema(_Watching)
    assert asked == {"integrity": True}, \
        "the scan was left to whatever the default happens to be today"


def test_init_db_upgrades_after_taking_the_copy(tmp_path, monkeypatch):
    """The whole command, end to end: a backup appears AND the schema moves."""
    path = _behind(tmp_path / "scrapex-engine.db")
    registry = DatabaseRegistry(EngineDatabase(path),
                               pointer_file=tmp_path / "databases.json")
    monkeypatch.setattr("scrapex.cli.DatabaseRegistry",
                        type("_Fixed", (), {"defaults": staticmethod(lambda: registry)}))

    assert cli.main(["init-db"]) == 0
    assert len(list(tmp_path.glob("scrapex-engine.pre-upgrade-*.backup.db"))) == 1
    assert EngineDatabase(path).health().ok


# ---- 3 · the destructive restore asks first ---------------------------------

@pytest.fixture()
def restorable(tmp_path):
    """A live warehouse, a pointer at it, and a backup to put in its place."""
    live = _warehouse(tmp_path / "scrapex-engine.db")
    backup = _warehouse(tmp_path / "from-drive.db")
    pointer = tmp_path / "databases.json"
    pointer.write_text(json.dumps({
        "format_version": 2, "mode": "single", "engine_path": str(live),
    }), encoding="utf-8")
    return live, backup, pointer


@pytest.mark.parametrize("given", ["", "yes", "y", "replace", "replace my",
                                   "replace my warehouse please", "REPLACE MY WAREHOUSE"])
def test_restore_database_refuses_anything_but_the_phrase(restorable, given, capsys):
    """A PREFIX AND A SUPERSET ARE BOTH REFUSED, and the wrong case with them.

    `--confirm replace` passing would make the guard a formality, and it is the
    shape a person types when a command has just refused them once.
    """
    live, backup, pointer = restorable
    before = live.read_bytes()

    code = cli.main(["restore-database", str(backup),
                     "--registry", str(pointer), "--confirm", given])

    assert code == 2, f"--confirm {given!r} was accepted"
    assert live.read_bytes() == before, "the live warehouse was displaced anyway"
    said = capsys.readouterr().err
    assert cli.RESTORE_PHRASE in said, "the refusal did not say what to type"
    assert "merge-warehouse" in said, (
        "the refusal did not name the non-destructive alternative, which is the "
        "whole of R-43 — restore replaces, merge adds")


def test_restore_database_proceeds_once_the_phrase_is_typed(restorable, capsys):
    live, backup, pointer = restorable

    code = cli.main(["restore-database", str(backup),
                     "--registry", str(pointer),
                     "--confirm", cli.RESTORE_PHRASE])

    assert code == 0, capsys.readouterr()
    assert live.is_file()
    displaced = list(live.parent.glob("scrapex-engine.replaced-*.db"))
    assert len(displaced) == 1, "the previous warehouse was not kept aside"


def test_the_phrase_survives_surrounding_whitespace(restorable):
    """A shell and a copy-paste both add spaces; neither is a different answer."""
    live, backup, pointer = restorable
    assert cli.main(["restore-database", str(backup), "--registry", str(pointer),
                     "--confirm", f"  {cli.RESTORE_PHRASE}  "]) == 0
