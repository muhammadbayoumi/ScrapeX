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
from scrapex.dbupgrade import BEHIND, RESTART_UPGRADES


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
    assert f"v{before}," in said and f"v{before + 1} is now installed" in said, (
        f"the refusal does not name both versions: {said!r}")
    assert RESTART_UPGRADES[1:] in said, (
        f"the refusal does not name the control, its screen and what it does: {said!r}")
    for command in ("scrapex ", "python -m", "init-db"):
        assert command not in said, f"the refusal names {command!r}, a command line"
    assert _version(registry.engine.path) == before, "the refusal changed the database"
    assert _backups(registry.engine.path) == [], "the refusal copied the database"

    # AND THE RUN BANNER SAYS THE SAME THING. It printed "press Upgrade database"
    # from `/api/health` beside this refusal, which was #1634's trap itself.
    lag = client.get("/api/health").json()["schema_lag"]
    assert lag["pending"] == [stream.newest.name], lag
    assert lag["fix"] == RESTART_UPGRADES, lag
    assert "started before" in lag["message"], lag


def test_a_lag_on_an_engine_level_with_the_disk_still_names_upgrade(
        tmp_path, stream, monkeypatch):
    """The other branch of the banner's fix. Unreachable on a registry today, since
    `create_app` refuses a database behind its plan; staged by saying the plan on disk
    is not newer, so a fix that named Restart for every lag fails here."""
    import scrapex.dbupgrade as dbupgrade
    from scrapex.webui.app import create_app

    registry = _registry(tmp_path)
    registry.initialize()
    client = TestClient(create_app(databases=registry))
    stream.land()
    monkeypatch.setattr(dbupgrade, "newer_plan_on_disk", lambda engine: None)

    lag = client.get("/api/health").json()["schema_lag"]

    assert lag["fix"] == "press Upgrade database on the Database page", lag
    assert "will fail until they are applied" in lag["message"], lag


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
    """The refusal reads the plan on disk, so a folder that cannot be used is its own
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
    assert "could not be used" in said and "0099 a misnamed file.sql" in said, said
    assert "Nothing was changed" in said, said
    assert "corrected ScrapeX update" in said, said
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


@pytest.fixture()
def behind(tmp_path, stream, monkeypatch):
    """His warehouse on 2026-10-24: built on the old plan, and the new file on disk.

    A FRESH PROCESS PER COMMAND, as Chrome starts the host: the plan is read from disk
    at each call. Yields the file and the version it is at.
    """
    path = tmp_path / "engine" / "scrapex-engine.db"
    pointer = tmp_path / "databases.json"
    DatabaseRegistry(EngineDatabase(path), pointer_file=pointer).initialize()
    before = _version(path)
    stream.land()
    monkeypatch.setattr(DatabaseRegistry, "defaults", classmethod(
        lambda cls, **kw: cls(EngineDatabase(path), pointer_file=pointer)))
    return path, before


def _engine_on_the_port(monkeypatch, running: bool) -> None:
    """Said, never assumed: his own engine is usually listening on 8000."""
    from scrapex import native

    monkeypatch.setattr(native, "_engine_answering",
                        lambda *a, **k: {"app": "scrapex"} if running else None)


def _start_the_engine(monkeypatch) -> list:
    """`cli._cmd_ui` up to `uvicorn.run`, as Restart's replacement runs it."""
    import uvicorn

    import scrapex.cli as cli
    from scrapex.jobs import JobRunner

    served: list = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.append(app))
    monkeypatch.setattr(JobRunner, "start", lambda self: None)
    monkeypatch.setattr(cli, "_bind_log_streams", lambda: None)
    code = cli._cmd_ui(argparse.Namespace(db=None, host="127.0.0.1", port=8199,
                                          no_open=True))
    return served if code in (None, 0) else []


def test_restart_is_not_refused_for_a_database_that_is_only_behind(behind, monkeypatch):
    """The second half: with an engine running, the pre-check Restart asks passes a
    database whose only fault is being behind -- and the replacement it lets through
    backs the file up, upgrades it and serves. Passing a database the start then
    refuses would only move the failure past the press."""
    from scrapex import native

    path, before = behind
    _engine_on_the_port(monkeypatch, running=True)

    check = native.startup_check()

    assert check["ok"] is True, (
        f"Restart's pre-check refused a database whose only fault is being behind, "
        f"with an engine running that cannot upgrade it: {check}")
    assert check["databases"]["engine"]["status"] == BEHIND, check
    assert len(_start_the_engine(monkeypatch)) == 1, "the replacement did not serve"
    assert _version(path) == before + 1, "the replacement did not upgrade the database"
    assert len(_backups(path)) == 1, "the replacement upgraded without a backup"


def test_the_command_restart_sends_is_the_one_that_passes(behind, monkeypatch):
    """Through the host's own dispatch, as the panel's `checkStartup` sends it: with
    no port. The tests above call `startup_check` directly,
    so a dispatch that stopped looking for an engine -- `startup_check(None)`, the
    obvious edit when a port is threaded through for #1808 -- would bring #1634 back
    with every one of them green. Found by the third stage-5 review."""
    from scrapex import native

    _engine_on_the_port(monkeypatch, running=True)
    restart = native.handle(None, {"command": "CHECK_STARTUP", "request_id": "r"})
    assert restart["ok"] is True, f"Restart's pre-check refused, the deadlock: {restart}"

    _engine_on_the_port(monkeypatch, running=False)
    silent = native.handle(None, {"command": "CHECK_STARTUP", "request_id": "s"})
    assert silent["ok"] is False and silent["action"] == "upgrade_database", silent


def test_start_with_no_engine_still_sends_him_to_upgrade_database(behind, monkeypatch):
    """His ruling of 2026-10-25: Restart only. With no engine running, Upgrade database
    reaches the native host, which names a failure in words, so Start stops and offers
    it, as before, and spawns nothing that could race it."""
    from scrapex import native

    path, before = behind
    _engine_on_the_port(monkeypatch, running=False)
    spawned: list = []
    monkeypatch.setattr(native, "_spawn_engine", spawned.append)

    answer = native.start_engine({"port": 8199})

    assert answer["ok"] is False and answer["error"] == "startup_blocked", answer
    assert answer["action"] == "upgrade_database", answer
    assert spawned == [], "Start spawned an engine over a database that is behind"
    assert _version(path) == before and _backups(path) == []


def test_start_never_takes_restarts_pass(behind, monkeypatch):
    """An engine that misses Start's own probe and then answers -- or one on another
    port -- does not make a Start a Restart: the engine this Start would spawn
    upgrades the file under the running one. Reproduced by the stage-5 re-review
    with probes answering [None, engine]."""
    from scrapex import native

    path, before = behind
    answers = iter([None])
    monkeypatch.setattr(native, "_engine_answering",
                        lambda *a, **k: next(answers, {"app": "scrapex"}))
    spawned: list = []
    monkeypatch.setattr(native, "_spawn_engine", spawned.append)

    answer = native.start_engine({"port": native.DEFAULT_ENGINE_PORT})

    assert answer["ok"] is False and answer["action"] == "upgrade_database", answer
    assert spawned == [], "Start spawned an engine over one that answered late"
    assert _version(path) == before


def test_a_replacement_that_cannot_upgrade_leaves_a_button_that_says_why(
        behind, monkeypatch):
    """When Restart's replacement cannot upgrade, it exits and the reason is only in
    its log. The panel's check after a silent restart then finds no engine, so the
    database blocks again and offers Upgrade database -- and that button's answer
    names the failure in words, which is the protection a passing check must not take
    away."""
    import scrapex.archive as archive
    from scrapex import native

    path, before = behind

    def disk_full(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(archive, "backup_database", disk_full)
    _engine_on_the_port(monkeypatch, running=True)
    assert native.startup_check()["ok"] is True
    assert _start_the_engine(monkeypatch) == [], "a replacement served without upgrading"

    _engine_on_the_port(monkeypatch, running=False)
    check = native.startup_check()
    assert check["ok"] is False and check["action"] == "upgrade_database", check

    answer = native.upgrade_database()
    assert answer["ok"] is False and answer["error"] == "database_upgrade_failed", answer
    assert "could not be backed up" in answer["detail"], answer
    assert "No space left on device" in answer["detail"], answer
    assert _version(path) == before


def test_a_database_from_a_newer_build_still_blocks_a_start(tmp_path, monkeypatch):
    """Only BEHIND passes, and only with an engine running. A database written by a
    newer build is the one the new engine refuses, so the pre-check still refuses it,
    by name, engine or no engine."""
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
    _engine_on_the_port(monkeypatch, running=True)

    check = native.startup_check()

    assert check["ok"] is False and check["error"] == "startup_blocked", check
    assert check["action"] == "check_storage", check
