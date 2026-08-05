"""The engine refused to start, said exactly how to fix it, and nobody read it.

Migration 0061 merged on 2026-08-04 and was never applied to the owner's live
warehouse. The next time the engine started it refused — correctly, and with the
command to run — and what he saw was a dead engine. The rule protected his data
and cost him the product, because the one person a refusal on stderr speaks to
is the one who does not read logs.

He asked for the upgrade to become part of the procedure. That reverses what
registry.ensure_ready has said in writing since spec 40 — "advancing the schema
of a file that already holds the owner's data is their decision" — and that
sentence is still true of ensure_ready. The decision moved to its caller, which
is where its own docstring always said the decision lived.

EVERYTHING SPEC 40 WAS PROTECTING IS KEPT, and every one of those is a test
below: a backup first without exception, forward only, never over damage, and
said out loud.
"""

from __future__ import annotations

import pathlib

import pytest

from scrapex import cli


class _FakeRegistry:
    """A registry that reports what the test wants and records what was asked of it."""

    def __init__(self, states: dict, after: dict | None = None):
        self._states = states
        self._after = after
        self.initialized = False

    def initialize(self):
        self.initialized = True
        return {"marketlens": [59], "general": []}

    def ensure_ready(self):
        states = self._after if self._after is not None else self._states
        return {"ok": all(s["ok"] for s in states.values()),
                "created": [], "databases": states}


def _state(kind: str, path, ok: bool, status: str) -> dict:
    return {"kind": kind, "path": str(path), "ok": ok, "status": status,
            "action": "", "schema_version": 58, "application_id": None}


@pytest.fixture()
def warehouse(tmp_path):
    """A real SQLite file, because the backup is a real sqlite3 backup."""
    import sqlite3
    path = tmp_path / "marketlens.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    return path


def _report(states):
    return {"ok": all(s["ok"] for s in states.values()), "created": [],
            "databases": states}


def test_a_warehouse_that_is_only_behind_is_backed_up_and_upgraded(warehouse, capsys):
    """The case that cost the owner his engine."""
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs upgrade"),
              "general": _state("general", warehouse, True, "Healthy")}
    healthy = {k: dict(v, ok=True, status="Healthy") for k, v in states.items()}
    registry = _FakeRegistry(states, after=healthy)

    result = cli._upgrade_what_is_only_behind(registry, _report(states))

    assert registry.initialized
    assert result["ok"]
    said = capsys.readouterr().out
    assert "backed up" in said and "upgraded" in said, (
        "the upgrade happened in silence; silent is the real breach")


def test_the_backup_exists_before_anything_is_migrated(warehouse):
    """A BACKUP FIRST, WITHOUT EXCEPTION. There is no path through here that
    advances a schema without a restorable copy beside it."""
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs upgrade")}
    registry = _FakeRegistry(states, after={k: dict(v, ok=True, status="Healthy")
                                            for k, v in states.items()})

    cli._upgrade_what_is_only_behind(registry, _report(states))

    copies = list(warehouse.parent.glob("marketlens.pre-upgrade-*.backup.db"))
    assert len(copies) == 1
    assert copies[0].stat().st_size > 0


def test_nothing_is_migrated_when_the_backup_cannot_be_made(tmp_path, capsys):
    """If the copy fails the engine refuses exactly as it did before. An upgrade
    with no way back is the one thing spec 40 was written to prevent."""
    missing = tmp_path / "not-there.db"
    states = {"marketlens": _state("marketlens", missing, False, "Needs upgrade")}
    registry = _FakeRegistry(states)

    result = cli._upgrade_what_is_only_behind(registry, _report(states))

    assert not registry.initialized, "it migrated a database it could not back up"
    assert not result["ok"]
    assert "could not be backed up" in capsys.readouterr().err


def test_a_database_from_a_newer_build_is_never_touched(warehouse):
    """FORWARD ONLY. Downgrading is how a warehouse dies, and a file written by
    a later ScrapeX reports its own status precisely so this can refuse it."""
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs a newer ScrapeX")}
    registry = _FakeRegistry(states)

    cli._upgrade_what_is_only_behind(registry, _report(states))

    assert not registry.initialized
    assert not list(warehouse.parent.glob("*pre-upgrade*"))


def test_a_damaged_database_is_never_migrated(warehouse):
    """NEVER OVER DAMAGE. Migrating a corrupt file is how a small corruption
    becomes an unrecoverable one."""
    for status in ("Integrity check failed", "Failed"):
        states = {"marketlens": _state("marketlens", warehouse, False, status)}
        registry = _FakeRegistry(states)

        cli._upgrade_what_is_only_behind(registry, _report(states))

        assert not registry.initialized, f"it migrated a database reported as {status!r}"


def test_one_behind_beside_one_damaged_upgrades_neither(warehouse):
    """THE MIXED CASE. Two databases, one merely behind and one damaged: the
    run is not partly safe, so nothing is touched and the engine reports as
    before. Upgrading the healthy half would leave a pair that has never
    existed together."""
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs upgrade"),
              "general": _state("general", warehouse, False, "Integrity check failed")}
    registry = _FakeRegistry(states)

    result = cli._upgrade_what_is_only_behind(registry, _report(states))

    assert not registry.initialized
    assert not result["ok"]


def test_a_healthy_pair_is_left_entirely_alone(warehouse):
    """The overwhelmingly common start. Nothing is copied, nothing is migrated,
    and no disk is spent saying so."""
    states = {"marketlens": _state("marketlens", warehouse, True, "Healthy"),
              "general": _state("general", warehouse, True, "Healthy")}
    registry = _FakeRegistry(states)

    cli._upgrade_what_is_only_behind(registry, _report(states))

    assert not registry.initialized
    assert not list(warehouse.parent.glob("*pre-upgrade*"))


def test_the_reversal_is_recorded_where_the_rule_was_written():
    """spec 40 has no document — the citation in registry.py IS the record. A
    rule reversed without amending the place it was stated is a rule two people
    can still read opposite ways."""
    source = pathlib.Path(
        __import__("scrapex.databases.registry", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")

    assert "spec 40" in source, "the rule's own citation has gone"
    assert "_upgrade_what_is_only_behind" in source, (
        "ensure_ready still reads as though nothing may ever upgrade an "
        "existing database, and one caller now does")
