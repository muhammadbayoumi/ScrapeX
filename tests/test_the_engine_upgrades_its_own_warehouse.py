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
        # BEFORE THE UPGRADE IT REPORTS THE CURRENT STATE, AFTER IT REPORTS THE NEW ONE,
        # which is what a real registry does and what this fake did not. It returned
        # `after` unconditionally, so a caller that READS the report first -- as
        # `native.upgrade_database` must, since the rule is decided on it -- saw a healthy
        # database and did nothing. The tests above pass their report in explicitly and
        # never noticed.
        states = (self._after if self._after is not None and self.initialized
                  else self._states)
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


# ---- the same four, for the door he actually presses (OP-127) ---------------
#
# `native.upgrade_database` is the panel's «Upgrade database» button. Until 2026-09-03 it
# called `DatabaseRegistry.defaults().initialize()` bare -- no backup, no BEHIND check, no
# refusal over damage, nothing said -- while every test above proved the protections for
# the command line. `R-81`: the panel is the only interface, so the surface with no safety
# was the only one he could reach.


def _panel(monkeypatch, states, after=None):
    """Drive the button with a registry that reports `states`, and return its reply."""
    from scrapex import databases, native

    registry = _FakeRegistry(states, after=after)
    monkeypatch.setattr(databases.DatabaseRegistry, "defaults",
                        classmethod(lambda cls: registry))
    monkeypatch.setattr(native, "_database_report", lambda: (states, None))
    return registry, native.upgrade_database()


def test_the_panel_button_backs_up_before_it_migrates(warehouse, monkeypatch):
    """A BACKUP FIRST, WITHOUT EXCEPTION — on the surface that had none.

    His warehouse is 1.4 GB and `job_capacity` is not the only setting that differs from
    the shipped default. There is no path through this button that advances a schema
    without a restorable copy beside it.
    """
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs upgrade")}
    healthy = {k: dict(v, ok=True, status="Healthy") for k, v in states.items()}

    registry, reply = _panel(monkeypatch, states, after=healthy)

    assert reply["ok"] is True, reply
    assert registry.initialized, "the button did not migrate at all"
    copies = list(warehouse.parent.glob("marketlens.pre-upgrade-*.backup.db"))
    assert len(copies) == 1, (
        "the panel migrated an existing warehouse with no backup beside it, which is what "
        f"`registry.ensure_ready`'s docstring forbids in terms: {copies}")
    assert copies[0].stat().st_size > 0


def test_the_panel_reply_names_the_backup_by_path(warehouse, monkeypatch):
    """SAID OUT LOUD — the fourth protection, arriving here for the first time.

    The old reply could only say how many migrations were applied, because there was no
    backup to name. A copy the owner cannot find is not a copy he can restore, and this is
    the only surface he sees.
    """
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs upgrade")}
    healthy = {k: dict(v, ok=True, status="Healthy") for k, v in states.items()}

    _registry, reply = _panel(monkeypatch, states, after=healthy)

    assert reply["backups"], f"the reply names no backup: {reply}"
    named = reply["backups"][0]["path"]
    assert pathlib.Path(named).is_file(), f"the reply names a path that is not there: {named}"
    assert "backed up" in reply["message"], (
        f"the sentence the panel shows does not mention the backup: {reply['message']!r}")
    assert named in reply["message"], (
        "the message says a backup was made and does not say where, so he cannot find it")


def test_the_panel_button_migrates_nothing_when_the_backup_cannot_be_made(tmp_path,
                                                                          monkeypatch):
    """IF THE COPY CANNOT BE MADE, NOTHING IS MIGRATED. The button reports the reason
    rather than proceeding, and rather than crashing — a button that reports nothing is
    the failure `R-81` is about."""
    missing = tmp_path / "not-there.db"
    states = {"marketlens": _state("marketlens", missing, False, "Needs upgrade")}

    registry, reply = _panel(monkeypatch, states)

    assert not registry.initialized, (
        "the backup failed and the button migrated anyway")
    assert reply["ok"] is False
    assert "could not be backed up" in reply["detail"], reply


def test_the_panel_button_never_touches_a_database_that_is_not_merely_behind(warehouse,
                                                                            monkeypatch):
    """ONLY WHEN NOTHING ELSE IS WRONG. Migrating damage is how a small corruption becomes
    an unrecoverable one — and `EngineDatabase.initialize()` migrates BEFORE it verifies,
    so the bare call the button used to make did exactly that."""
    states = {"marketlens": _state("marketlens", warehouse, False, "Needs upgrade"),
              "general": _state("general", warehouse, False, "Integrity check failed")}

    registry, reply = _panel(monkeypatch, states)

    assert not registry.initialized, (
        "one database was behind and another was damaged, and the button migrated")
    assert reply["ok"] is False
    assert "Integrity check failed" in reply["detail"], (
        f"the refusal does not name what was actually wrong: {reply}")
    assert not list(warehouse.parent.glob("*.pre-upgrade-*.backup.db")), (
        "it took a backup for an upgrade it then refused, which is copies piling up for "
        "nothing")


def test_a_healthy_warehouse_is_left_alone_by_the_button(warehouse, monkeypatch):
    """Nothing to do is not a failure, and it must not read as one."""
    states = {"marketlens": _state("marketlens", warehouse, True, "Healthy")}

    registry, reply = _panel(monkeypatch, states)

    assert reply["ok"] is True, reply
    assert not registry.initialized
    assert not list(warehouse.parent.glob("*.pre-upgrade-*.backup.db"))


def test_both_front_doors_hold_ONE_copy_of_the_rule():
    """THE DIVERGENCE ITSELF, and the reason it lasted.

    The protections lived inside a function that PRINTS, and `native.serve` writes framed
    messages to `sys.stdout.buffer` — so a `print` reached from a native command corrupts
    the protocol stream and the rule could not be called from there. Whoever wrote the
    escape hatch wrote a second, bare path instead.

    So the rule returns its outcome now and each caller renders it. This asserts there is
    no second copy: neither front door takes a backup of its own, and neither spells
    `BEHIND` again. Read as source, because two copies that happen to agree today would
    pass every behavioural assertion above.
    """
    from scrapex import cli, dbupgrade, native

    for module in (cli, native):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert "backup_database(" not in source or module is cli, (
            f"{module.__name__} takes its own backup instead of going through "
            "`dbupgrade.upgrade_what_is_only_behind`")
        assert 'BEHIND = ' not in source, (
            f"{module.__name__} spells BEHIND again; two spellings is a check that "
            "silently stops matching")

    # AND THE PRINTS STAY OUT OF THE NATIVE PATH, which is why the rule returns rather
    # than says. A `print` here is unframed bytes in the protocol stream.
    rule = pathlib.Path(dbupgrade.__file__).read_text(encoding="utf-8")
    assert "print(" not in rule, (
        "`dbupgrade` prints, so the native host cannot call it without corrupting its "
        "own stdout -- which is the divergence this module exists to end")
