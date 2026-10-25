"""Neither Upgrade database nor Restart could move him forward (2026-10-24).

His engine started on v25 code; `0026_tender_history_kept_as_jsonb.sql` then reached
the disk. The Database page, which reads the plan from disk, said "v25 of v26". Upgrade
database went to the running engine, whose plan was read once at its start, and it
answered "already up to date". Restart asked the native host first, a fresh process on
the new code, which refused a database that is behind -- although the engine's own
start backs it up and upgrades it. Every test here runs the REAL migration stream, with
its newest file held back until the test lets it land.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex.databases import DatabaseRegistry
from scrapex.databases.domain import EngineDatabase
from scrapex.dbupgrade import BEHIND


@pytest.fixture()
def stream(tmp_path, monkeypatch):
    """The real migration stream, with its newest file held back until `land()`."""
    real = sorted(dbmod.MIGRATIONS_DIR.glob("*.sql"))
    assert real, ("the real stream has no migration above the baseline, so 'a "
                  "migration landed after the engine started' cannot be staged")
    folder = tmp_path / "migrations"
    folder.mkdir()
    for file in real[:-1]:
        shutil.copy2(file, folder / file.name)
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", folder)

    class Stream:
        newest = real[-1]
        held = folder

        @staticmethod
        def land():
            shutil.copy2(real[-1], folder / real[-1].name)

    return Stream


def _version(path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def _backups(path) -> list[str]:
    return sorted(p.name for p in path.parent.glob("*pre-upgrade*"))


def _registry(tmp_path) -> DatabaseRegistry:
    return DatabaseRegistry(EngineDatabase(tmp_path / "engine" / "scrapex-engine.db"),
                            pointer_file=tmp_path / "databases.json")


def test_an_engine_older_than_the_disk_refuses_and_names_restart(tmp_path, stream):
    """The first half of the deadlock, as he met it: `v25 of v26` on the page, and
    the button under it answering "already up to date"."""
    from scrapex.webui.app import create_app

    registry = _registry(tmp_path)
    registry.initialize()
    before = _version(registry.engine.path)
    client = TestClient(create_app(databases=registry))
    stream.land()

    schema = client.get("/api/storage").json()["schema"]
    assert (schema["version"], schema["expected"]) == (before, before + 1), schema
    assert schema["pending"] == [stream.newest.name]

    answer = client.post("/api/databases/upgrade")

    assert answer.status_code == 409, (
        f"an engine started before {stream.newest.name} answered {answer.status_code} "
        f"{answer.json()} under a page reading v{before} of v{before + 1}")
    said = answer.json()["detail"]
    assert f"v{before + 1}" in said and f"v{before}." in said, (
        f"the refusal does not name both versions: {said!r}")
    assert "Restart engine" in said, f"the refusal names no control: {said!r}"
    for command in ("scrapex ", "python -m", "init-db"):
        assert command not in said, f"the refusal names {command!r}, a command line"
    assert _version(registry.engine.path) == before, "the refusal changed the database"
    assert _backups(registry.engine.path) == [], "the refusal copied the database"


def test_an_engine_level_with_the_disk_still_upgrades_behind_a_backup(tmp_path, stream):
    """The other direction: a fresh engine on a database that is behind its plan is
    the ordinary case, and the refusal above must not take it away. Mounted on a bare
    app: `create_app` verifies the warehouse, and a behind one is refused there."""
    from fastapi import FastAPI

    from scrapex.webui.database_api import create_database_router

    behind = _registry(tmp_path)
    behind.initialize()
    before = _version(behind.engine.path)
    stream.land()
    registry = _registry(tmp_path)
    app = FastAPI()
    app.include_router(create_database_router(lambda: registry))
    answer = TestClient(app).post("/api/databases/upgrade")

    assert answer.status_code == 200, answer.json()
    assert answer.json()["applied"] == {"engine": [before + 1]}, answer.json()
    assert _version(registry.engine.path) == before + 1
    assert len(_backups(registry.engine.path)) == 1, "it upgraded without a backup"


def test_unreadable_migration_files_refuse_in_words_and_change_nothing(tmp_path, stream):
    """The refusal reads the plan on disk, so a folder that cannot be read is its own
    answer, in words, rather than a 500 the panel can only call "HTTP 500"."""
    from scrapex.webui.app import create_app

    registry = _registry(tmp_path)
    registry.initialize()
    before = _version(registry.engine.path)
    client = TestClient(create_app(databases=registry))
    (stream.held / "0099 a misnamed file.sql").write_text("SELECT 1;", encoding="utf-8")

    answer = client.post("/api/databases/upgrade")

    assert answer.status_code == 409, (answer.status_code, answer.text)
    said = answer.json()["detail"]
    assert "could not be read" in said and "0099 a misnamed file.sql" in said, said
    assert "Nothing was changed" in said, said
    assert _version(registry.engine.path) == before
    assert _backups(registry.engine.path) == []


def test_why_the_stale_engine_refuses_rather_than_applies(tmp_path, stream):
    """THE MEASUREMENT BEHIND THE REFUSAL. Once a newer plan is applied under it, the
    running engine's own plan calls its warehouse newer than itself -- so an engine
    that applied the migration it was not started with refuses its own file next."""
    registry = _registry(tmp_path)
    registry.initialize()
    stream.land()
    _registry(tmp_path).initialize()

    state = registry.engine.health(integrity=False)

    assert not state.ok and "newer" in state.status.lower(), (state.status, state.action)


def test_a_start_is_not_refused_for_a_database_that_is_only_behind(
        tmp_path, stream, monkeypatch):
    """The second half: the pre-check passes exactly what the engine's start upgrades.

    Both halves are asserted, because passing a database the start then refuses would
    only move the failure past the press: the pre-check says yes, and then the start
    this lets through backs the file up, upgrades it and serves.
    """
    import uvicorn

    import scrapex.cli as cli
    from scrapex import native
    from scrapex.jobs import JobRunner

    path = tmp_path / "engine" / "scrapex-engine.db"
    pointer = tmp_path / "databases.json"
    DatabaseRegistry(EngineDatabase(path), pointer_file=pointer).initialize()
    before = _version(path)
    stream.land()
    # A FRESH PROCESS PER COMMAND, as Chrome starts the host: the plan is read from
    # disk at each call.
    monkeypatch.setattr(DatabaseRegistry, "defaults", classmethod(
        lambda cls, **kw: cls(EngineDatabase(path), pointer_file=pointer)))

    check = native.startup_check()

    assert check["ok"] is True, (
        f"the pre-check refused a database whose only fault is being behind: {check}")
    assert check["databases"]["engine"]["status"] == BEHIND, check
    spawned: list = []
    monkeypatch.setattr(native, "_engine_answering", lambda *a, **k: None)
    monkeypatch.setattr(native, "_spawn_engine", spawned.append)
    native.start_engine({"port": 8199})
    assert spawned == [8199], "Start did not start the engine"

    served: list = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.append(app))
    monkeypatch.setattr(JobRunner, "start", lambda self: None)
    monkeypatch.setattr(cli, "_bind_log_streams", lambda: None)
    cli._cmd_ui(argparse.Namespace(db=None, host="127.0.0.1", port=8199, no_open=True))

    assert len(served) == 1, "the start the pre-check passed did not serve"
    assert _version(path) == before + 1, "the start did not upgrade the database"
    assert len(_backups(path)) == 1, "the start upgraded without a backup"


def test_a_database_from_a_newer_build_still_blocks_a_start(tmp_path, monkeypatch):
    """Only BEHIND passes. A database written by a newer build is the one the new
    engine refuses, so the pre-check must still refuse it, by name."""
    from scrapex import native

    registry = _registry(tmp_path)
    registry.initialize()
    conn = sqlite3.connect(str(registry.engine.path))
    try:
        conn.execute(f"PRAGMA user_version = {registry.engine.latest_schema_version + 5}")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(DatabaseRegistry, "defaults",
                        classmethod(lambda cls, **kw: registry))

    check = native.startup_check()

    assert check["ok"] is False and check["error"] == "startup_blocked", check
    assert check["action"] == "check_storage", check
