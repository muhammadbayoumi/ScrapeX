"""Database status is visible from every page and from the panel's poll.

The owner asked for a notification showing database state. A status that only
appears on a page you have to go looking for is a status you learn about from a
failed query instead, so it rides in the topbar of every page, escalates to a
banner naming the fix when something is wrong, and travels on /api/health —
which is the only endpoint the side panel polls on a timer.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry
from scrapex.databases.domain import GeneralDatabase, MarketLensDatabase

pytest.importorskip("fastapi", reason="needs the ui extra")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex.webui.app import create_app  # noqa: E402


def make_registry(tmp_path: Path) -> DatabaseRegistry:
    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "marketlens" / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    return registry


def rewind(database, version: int) -> None:
    conn = sqlite3.connect(str(database.path))
    try:
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    finally:
        conn.close()


# ---- the workspace ----------------------------------------------------------

def test_every_page_states_the_database_status_when_all_is_well(tmp_path):
    client = TestClient(create_app(databases=make_registry(tmp_path)))
    for path in ("/", "/settings", "/jobs", "/exports"):
        body = client.get(path).text
        assert "Databases healthy" in body, f"{path} carried no database status"


def test_a_database_that_degrades_while_running_is_announced_with_its_fix(tmp_path):
    """The engine refuses to START on an unusable database, so the case the page
    has to catch is the one that appears AFTER it started: a drive unplugged, a
    file replaced, a schema no longer the one this build reads. Until now the
    workspace kept rendering as though nothing had changed."""
    registry = make_registry(tmp_path)
    client = TestClient(create_app(databases=registry))
    assert "Databases healthy" in client.get("/").text

    rewind(registry.engine, registry.engine.latest_schema_version - 1)

    body = client.get("/").text
    assert "Databases need attention" in body, "the status went stale"
    assert "Database attention needed" in body, "the banner must name the problem"
    assert "Needs upgrade" in body
    assert "init-db" in body, "a warning without the fix leaves the owner stuck"


def test_the_status_is_words_not_only_a_colour(tmp_path):
    """Spec: never rely on colour alone. The healthy and unhealthy pages must
    differ in TEXT, not only in which CSS class the chip carries."""
    registry = make_registry(tmp_path)
    client = TestClient(create_app(databases=registry))
    healthy = client.get("/").text

    rewind(registry.engine, registry.engine.latest_schema_version - 1)
    unhealthy = client.get("/").text

    assert "Databases healthy" in healthy and "Databases healthy" not in unhealthy
    # Anchored on the DATABASE chip's own words. "need attention" alone stopped
    # being a database sentence the day Overview started counting sources that
    # need attention — two true statements about different things, and a test
    # that reads the whole page cannot tell them apart.
    assert "Databases need attention" in unhealthy
    assert "Databases need attention" not in healthy


def test_one_app_never_reports_another_apps_databases(tmp_path):
    """The status is read from the request's own app. A template global would be
    module-level, and two apps in one process would overwrite each other."""
    good = TestClient(create_app(databases=make_registry(tmp_path / "good")))
    broken_registry = make_registry(tmp_path / "broken")
    broken = TestClient(create_app(databases=broken_registry))
    rewind(broken_registry.marketlens, 1)

    assert "need attention" in broken.get("/").text
    assert "Databases healthy" in good.get("/").text, \
        "the broken app's status leaked into the healthy one"


# ---- the side panel's poll ---------------------------------------------------

def test_health_carries_database_status_for_the_panel(tmp_path):
    client = TestClient(create_app(databases=make_registry(tmp_path)))
    body = client.get("/api/health").json()
    assert body["databases"] == {"ok": True, "detail": ""}


def test_a_reachable_engine_on_an_unusable_database_does_not_report_ok(tmp_path):
    """This is the case the panel could not see: the engine answers, so the dot
    goes green, while nothing it does can actually work."""
    registry = make_registry(tmp_path)
    client = TestClient(create_app(databases=registry))
    rewind(registry.engine, registry.engine.latest_schema_version - 1)

    body = client.get("/api/health").json()

    assert body["databases"]["ok"] is False
    assert "marketlens" in body["databases"]["detail"]
    assert "needs upgrade" in body["databases"]["detail"]


# ---- before the engine can start ---------------------------------------------

def test_the_engine_refuses_to_start_with_the_action_not_a_traceback(tmp_path, capsys):
    """A database the engine cannot use must stop it — half-serving is worse. But
    the owner has to be told what to run, and a stack trace does not tell them.

    THE FAULT THIS USES CHANGED ON 2026-08-05. It rewound the schema by one and
    asserted the refusal, because being behind was a fault the owner had to go
    and fix. It is not any more: `scrapex ui` now backs the file up and migrates
    it when behind is the ONLY thing wrong, and this test would have been
    asserting that the engine still refuses to do the thing it was just taught
    to do.

    So it uses a fault the engine still cannot fix and never will — a database
    written by a LATER build, where the way out is to update ScrapeX and never
    to touch the file. The rule under test is unchanged: stop, and say what to
    do. The behind-and-upgraded path is covered in
    test_the_engine_upgrades_its_own_warehouse.py, where it can be driven
    without starting a server that would then not stop."""
    from scrapex.cli import main

    registry = make_registry(tmp_path)
    rewind(registry.engine, registry.engine.latest_schema_version + 1)
    pointer = registry.pointer_file

    import scrapex.cli as cli
    original = cli.DatabaseRegistry.defaults
    cli.DatabaseRegistry.defaults = classmethod(
        lambda cls, **kw: DatabaseRegistry.read(pointer))
    try:
        code = main(["ui", "--no-open"])
    finally:
        cli.DatabaseRegistry.defaults = original

    assert code == 1, "the engine served requests against a database it cannot read"
    err = capsys.readouterr().err
    assert "needs a newer scrapex" in err.lower()
    assert "Update ScrapeX" in err, "the message named no way out"
    assert "Traceback" not in err, "it answered with a stack trace"
