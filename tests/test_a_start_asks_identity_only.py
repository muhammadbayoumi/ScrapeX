"""A start asks the warehouse what it is, not whether every page is sound (#1713, #1747).

A Restart from the panel ran three corruption scans before the engine answered: the
native host's `startup_check` before the spawn, then `cli._cmd_ui`'s `ensure_ready`,
then `create_app`'s `verify`. Each is `PRAGMA quick_check(1)` plus
`pragma_foreign_key_check`, O(file size). Measured on a copy of his 2,475,536,384-byte
warehouse on 2026-10-24, in a fresh process: `startup_check` 23.5 s and `_cmd_ui` up to
serving 65.1 s. His engine took about 50 s to answer after a Restart that day.

What a start needs is identity: is the file readable, at the version this build
expects, and the right kind. The Database page's Check integrity still scans, and so
does the Upgrade database path. These tests count the statements, not the seconds,
because a fixture's file scans in no time at all.
"""
from __future__ import annotations

import argparse
import re
import sqlite3

import pytest

from scrapex.databases import DatabaseRegistry
from scrapex.databases.domain import EngineDatabase

#: Every spelling of a full-file check SQLite has, so a scan that comes back by
#: another route fails here too.
SCAN = re.compile(r"quick_check|integrity_check|foreign_key_check", re.IGNORECASE)


@pytest.fixture()
def registry(tmp_path, monkeypatch) -> DatabaseRegistry:
    """An existing, healthy warehouse, which is what an ordinary Restart finds."""
    reg = DatabaseRegistry(EngineDatabase(tmp_path / "engine" / "scrapex-engine.db"),
                           pointer_file=tmp_path / "databases.json")
    reg.initialize()
    monkeypatch.setattr(DatabaseRegistry, "defaults", classmethod(lambda cls, **kw: reg))
    return reg


@pytest.fixture()
def statements(monkeypatch) -> list[str]:
    """Every statement any connection opened from here on runs, whoever opens it."""
    seen: list[str] = []
    real = sqlite3.connect

    def connect(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.set_trace_callback(seen.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    return seen


@pytest.fixture()
def served(monkeypatch) -> list:
    """`_cmd_ui` runs to `uvicorn.run` and stops there: nothing listens, and the job
    worker is never started, so no thread outlives the test."""
    import uvicorn

    import scrapex.cli as cli
    from scrapex.jobs import JobRunner

    apps: list = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: apps.append(app))
    monkeypatch.setattr(JobRunner, "start", lambda self: None)
    monkeypatch.setattr(cli, "_bind_log_streams", lambda: None)
    return apps


def _ui() -> argparse.Namespace:
    return argparse.Namespace(db=None, host="127.0.0.1", port=8199, no_open=True)


def _scans(statements: list[str]) -> list[str]:
    return [s for s in statements if SCAN.search(s)]


def test_the_engine_start_runs_no_corruption_scan(registry, statements, served):
    import scrapex.cli as cli

    assert cli._cmd_ui(_ui()) == 0
    assert len(served) == 1, "the start never reached the server, so it proves nothing"
    assert statements, "the trace saw no statement, so it proves nothing"
    assert _scans(statements) == [], (
        "the engine's start scanned the whole file before serving: 65 s on a copy of "
        f"his warehouse, for a question identity answers ({_scans(statements)[:3]})")


def test_the_hosts_startup_check_runs_no_corruption_scan(registry, statements):
    import scrapex.native as native

    result = native.startup_check()

    assert result["ok"] is True, result
    assert statements, "the trace saw no statement, so it proves nothing"
    assert _scans(statements) == [], (
        "CHECK_STARTUP, which Start and Restart wait for, scanned the whole file: "
        f"23.5 s on a copy of his warehouse ({_scans(statements)[:3]})")


def test_the_app_built_from_the_default_registry_runs_no_corruption_scan(
        registry, statements):
    """`create_app()` with no database verifies the default registry twice: once
    where it builds it and once where it reads it. Neither may scan."""
    from scrapex.webui.app import create_app

    create_app()

    assert statements, "the trace saw no statement, so it proves nothing"
    assert _scans(statements) == [], _scans(statements)[:3]


@pytest.mark.parametrize("ahead", [1, 5])
def test_a_start_still_refuses_a_database_from_a_newer_build(registry, served, ahead):
    """Identity is still asked: skipping the scan must not skip the question."""
    import scrapex.cli as cli
    import scrapex.native as native

    conn = sqlite3.connect(str(registry.engine.path))
    try:
        conn.execute(f"PRAGMA user_version = {registry.engine.latest_schema_version + ahead}")
        conn.commit()
    finally:
        conn.close()

    check = native.startup_check()
    assert check["ok"] is False and check["error"] == "startup_blocked", check
    assert "Needs a newer ScrapeX" in check["detail"], check["detail"]

    assert cli._cmd_ui(_ui()) == 1
    assert served == [], "the engine served a database a newer build wrote"


def test_upgrade_database_and_the_defaults_still_scan(registry, statements):
    """The scan moved off the way up, not out of the product. Upgrade database
    decides on a report that must have looked for damage, because migrating a
    damaged file is how a small corruption becomes an unrecoverable one
    (`dbupgrade.upgrade_what_is_only_behind`)."""
    import scrapex.native as native

    assert native.upgrade_database()["ok"] is True
    assert _scans(statements), "Upgrade database no longer looks for damage"

    statements.clear()
    registry.verify()
    assert _scans(statements), "verify() with no argument no longer scans"

    statements.clear()
    registry.ensure_ready()
    assert _scans(statements), "ensure_ready() with no argument no longer scans"
