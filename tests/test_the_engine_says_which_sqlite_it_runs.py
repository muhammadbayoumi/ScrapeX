"""The engine says which SQLite it loaded, and whether it carries the WAL-reset fix (#1207).

SQLite's WAL-reset bug (https://www.sqlite.org/wal.html#the_wal_reset_bug) can corrupt a
WAL database when two connections in separate threads or processes write or checkpoint
at the same instant, and the engine holds several connections from several threads. It
is present from 3.7.0 through 3.51.2, fixed in 3.51.3, and backported to 3.50.7 and
3.44.6. On 2026-09-27 his machine's engine ran 3.50.4 and the downloadable one 3.49.1 —
both affected, and nothing on any screen said so.

The version belongs to the interpreter, not to ScrapeX, so the engine reports it and
never refuses to start. His ruling of 2026-09-27 on #1207 was «اعرضه الأول»: report first.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex.config import MANIFEST_FILE
from scrapex.webui.app import create_app

# Every boundary of the rule, each against what SQLite's own page says of it.
CASES = [
    ((3, 7, 0), "affected"),      # the first release with WAL
    ((3, 44, 5), "affected"),
    ((3, 44, 6), "fixed"),        # the 3.44 backport
    ((3, 44, 9), "fixed"),
    ((3, 45, 0), "affected"),     # past the 3.44 branch, which is where the backport stops
    ((3, 49, 1), "affected"),     # the frozen engine's, 2026-09-27
    ((3, 50, 4), "affected"),     # his machine's engine, 2026-09-27
    ((3, 50, 6), "affected"),
    ((3, 50, 7), "fixed"),        # the 3.50 backport
    ((3, 50, 9), "fixed"),
    ((3, 51, 0), "affected"),     # past the 3.50 branch
    ((3, 51, 2), "affected"),     # the last affected release
    ((3, 51, 3), "fixed"),        # the fix
    ((3, 52, 0), "fixed"),        # withdrawn, but after the fix: its src/wal.c is 3.51.3's
    ((3, 53, 0), "fixed"),
    ((3, 53, 4), "fixed"),        # what Python 3.15 bundles
    ((4, 0, 0), "fixed"),
]


@pytest.mark.parametrize(("version", "expected"), CASES,
                         ids=[".".join(map(str, v)) for v, _ in CASES])
def test_the_rule_matches_sqlites_own_page(version, expected):
    assert dbmod.wal_reset_bug(version) == expected


def test_with_no_version_it_judges_the_sqlite_this_process_loaded(monkeypatch):
    assert dbmod.wal_reset_bug() == dbmod.wal_reset_bug(sqlite3.sqlite_version_info)
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 4))
    assert dbmod.wal_reset_bug() == "affected", "the default was read once and kept"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(path, manifest_path=manifest))


def test_the_health_poll_carries_the_version_and_the_verdict(client):
    body = client.get("/api/health").json()
    assert body["sqlite"] == {
        "version": sqlite3.sqlite_version,
        "wal_reset_bug": dbmod.wal_reset_bug(sqlite3.sqlite_version_info)}


def test_the_verdict_is_the_engines_rule_at_the_moment_it_is_asked(client, monkeypatch):
    """Not a string written into the route: an affected build must SAY affected."""
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 4))
    assert client.get("/api/health").json()["sqlite"]["wal_reset_bug"] == "affected"
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 51, 3))
    assert client.get("/api/health").json()["sqlite"]["wal_reset_bug"] == "fixed"


def test_it_answers_when_the_database_cannot_be_read(client, tmp_path):
    """Health must survive the thing it reports on, and this fact needs no database."""
    for leftover in tmp_path.glob("harvest.db*"):
        leftover.write_bytes(b"not a database")
    response = client.get("/api/health")
    assert response.status_code == 200, response.text
    assert response.json()["sqlite"] == {
        "version": sqlite3.sqlite_version,
        "wal_reset_bug": dbmod.wal_reset_bug(sqlite3.sqlite_version_info)}, (
        "the verdict, which is what the badge reads, depended on the database")
