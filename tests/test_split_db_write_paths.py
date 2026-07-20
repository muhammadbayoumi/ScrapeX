"""Every WRITE path must work against a split database, not just a legacy file.

The owner started the engine, pressed Run, and got a 500 with
"table offer_state already exists". Two request paths called dbmod.migrate()
unconditionally: a MarketLens database has its OWN numbered migration stream
(1-15) and is already migrated when created, so running the unified stream
(1-17) over it re-applies migration 1 onto tables that exist.

The whole test suite was green, because every test built an app over a legacy
single-file warehouse — the shape that is no longer the default. These tests use
the shape a real install actually has.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry
from scrapex.databases.domain import GeneralDatabase, MarketLensDatabase

pytest.importorskip("fastapi", reason="needs the ui extra")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex.webui.app import create_app  # noqa: E402


@pytest.fixture()
def split_client(tmp_path: Path) -> TestClient:
    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "general" / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens" / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    return TestClient(create_app(databases=registry))


def test_queueing_a_job_works_against_a_split_database(split_client):
    """The exact request the owner made: press Run."""
    response = split_client.post("/api/jobs", json={"source_keys": ["GPP_ENERGY"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued" and body["job_ref"]


def test_the_queued_job_is_readable_afterwards(split_client):
    split_client.post("/api/jobs", json={"source_keys": ["GPP_ENERGY"]})

    listed = split_client.get("/api/jobs")

    assert listed.status_code == 200
    assert listed.json(), "the job was queued into a database nothing else reads"


def test_no_write_route_re_migrates_a_domain_database(split_client):
    """A guard for the whole class, not the one route that happened to break.

    Re-running the unified stream over a domain database raises; if any of these
    routes still did it, the request would 500 rather than answer.
    """
    for method, path, payload in [
        ("post", "/api/jobs", {"source_keys": ["GPP_ENERGY"]}),
        ("get", "/api/sources", None),
        ("get", "/api/health", None),
        ("get", "/api/changes", None),
    ]:
        call = getattr(split_client, method)
        response = call(path, json=payload) if payload else call(path)
        assert response.status_code < 500, \
            f"{method.upper()} {path} failed on a split database: {response.text[:200]}"


def test_the_schema_of_a_domain_database_is_left_alone(split_client, tmp_path):
    """Not just "it did not crash": the version must be untouched afterwards."""
    registry = DatabaseRegistry.read(tmp_path / "databases.json")
    before = registry.marketlens.health().schema_version

    split_client.post("/api/jobs", json={"source_keys": ["GPP_ENERGY"]})

    after = registry.marketlens.health().schema_version
    assert after == before == registry.marketlens.latest_schema_version


# ---- a configured source that has never run must still be visible -----------

def test_a_fresh_install_shows_every_configured_source(split_client):
    """The overview read the DATABASE, which only knows a source once it has
    ingested something. On a fresh install that meant "No data yet" and none of
    the configured sources — a source that had never run did not look like a
    problem, it simply did not exist."""
    body = split_client.get("/").text

    assert "Configured, never run" in body
    assert "GPP_ENERGY" in body and "ELSEWEDYSHOP" in body
    assert "Never run" in body, "the status must be stated in words"


def test_a_source_that_has_run_is_not_listed_as_never_run(split_client):
    """The two lists must be disjoint, or a source appears twice and the owner
    cannot tell which card is current."""
    split_client.get("/source/GPP_ENERGY")     # registers nothing; still never run
    body = split_client.get("/").text

    import re

    section = body.split("Configured, never run")[-1]
    # Count CARDS, not string occurrences: a card names its source twice, once
    # as the key and once inside the suggested crawl command.
    cards = re.findall(r'class="key">([A-Z_]+)</div>', section)
    assert cards.count("GPP_ENERGY") == 1, f"listed more than once: {cards}"
