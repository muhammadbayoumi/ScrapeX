"""Where the live warehouse is, recorded in one place or not at all.

Since the split there are TWO records of the location: storage's location.json,
and databases.json — the one the ENGINE reads at startup. Move and compact used
to write the first and leave the second to their caller, two web routes did that
reconciliation with the same eight copy-pasted lines, and undo_compaction did not
do it at all. These pin the rule at the commit point instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapex import storage
from scrapex.databases.domain import GeneralDatabase, MarketLensDatabase
from scrapex.databases.registry import DatabaseRegistry


@pytest.fixture()
def registry(tmp_path, monkeypatch) -> DatabaseRegistry:
    """A real registry of real databases, entirely inside tmp_path."""
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")
    pointer = tmp_path / "databases.json"
    monkeypatch.setattr("scrapex.databases.registry.REGISTRY_FILE", pointer)
    live = DatabaseRegistry(EngineDatabase(tmp_path / "marketlens.db"),
                            None, pointer)
    live.initialize()
    return live


def _recorded_marketlens(pointer: Path) -> Path:
    return Path(json.loads(pointer.read_text(encoding="utf-8"))["marketlens_path"])


def test_committing_a_new_location_moves_both_records_together(registry, tmp_path):
    moved = tmp_path / "elsewhere" / "marketlens.db"
    moved.parent.mkdir()
    MarketLensDatabase(moved).initialize()

    storage.commit_live_database(moved, previous=registry.engine.path)

    assert storage.read_pointer() == moved, "the pointer did not move"
    assert _recorded_marketlens(registry.pointer_file) == moved, \
        "the engine will still open the old file on its next start"


def test_the_registry_is_not_dragged_along_by_an_unrelated_database(registry, tmp_path):
    """The guard that makes this safe by construction rather than by care.

    Without it, any test that compacts a temporary database — or any tool that
    relocates a backup — would repoint the owner's real registry at whatever
    file it happened to be handling.
    """
    unrelated = tmp_path / "some-other.db"
    MarketLensDatabase(unrelated).initialize()
    somewhere = tmp_path / "third.db"

    storage.commit_live_database(somewhere, previous=unrelated)

    assert storage.read_pointer() == somewhere      # the pointer is ours to move
    assert _recorded_marketlens(registry.pointer_file) == registry.engine.path, \
        "the registry followed a database it was never pointing at"


def test_a_legacy_session_with_no_registry_still_commits(tmp_path, monkeypatch):
    """`--db` sessions have no registry, and that is not a failure."""
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")
    monkeypatch.setattr("scrapex.databases.registry.REGISTRY_FILE", tmp_path / "absent.json")

    storage.commit_live_database(tmp_path / "harvest.db", previous=tmp_path / "old.db")

    assert storage.read_pointer() == tmp_path / "harvest.db"


def test_an_unreadable_registry_is_left_alone_not_rebuilt(registry, tmp_path):
    """It names the General database too. Rebuilding it from a guess is how one
    would be lost — better to leave a broken file for the owner to restore."""
    registry.pointer_file.write_text("{ not json", encoding="utf-8")
    moved = tmp_path / "moved.db"

    storage.commit_live_database(moved, previous=registry.engine.path)

    assert storage.read_pointer() == moved
    assert registry.pointer_file.read_text(encoding="utf-8") == "{ not json"
