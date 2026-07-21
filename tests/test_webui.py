"""Web UI routes (FastAPI TestClient) against a real ingested DB. Skips cleanly
if the ui extra isn't installed."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1", product_name="LED Floodlight 400W"),
        one_row(external_product_id="2", external_variant_id="v2", product_name="Copper Wire",
                effective_price="50.00", availability="out_of_stock"),
    ])])
    conn.commit()
    conn.close()
    return TestClient(create_app(db_path))


def test_overview_lists_the_source(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ELSEWEDYSHOP" in r.text and "السويدي شوب" in r.text


def test_source_page_shows_products(client):
    r = client.get("/source/ELSEWEDYSHOP")
    assert r.status_code == 200
    assert "LED Floodlight 400W" in r.text
    assert "Copper Wire" in r.text


def test_jobs_page_can_start_the_same_run_modes_as_the_side_panel(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert 'id="job-form"' in r.text
    assert 'value="ELSEWEDYSHOP"' in r.text
    assert 'value="full_rebuild"' in r.text


def test_workspace_navigation_is_rendered_from_the_shared_manifest(client):
    r = client.get("/jobs")
    assert 'href="/changes"' in r.text
    assert 'href="/sync"' in r.text
    assert 'href="/settings"' in r.text


def test_search_filters_rows(client):
    r = client.get("/source/ELSEWEDYSHOP", params={"q": "Copper"})
    assert "Copper Wire" in r.text
    assert "LED Floodlight 400W" not in r.text


def test_availability_filter(client):
    r = client.get("/source/ELSEWEDYSHOP", params={"availability": "out_of_stock"})
    assert "Copper Wire" in r.text
    assert "LED Floodlight 400W" not in r.text


def test_unknown_source_returns_404(client):
    r = client.get("/source/NOPE")
    assert r.status_code == 404


def test_empty_db_overview_has_hint(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    conn.close()
    client = TestClient(create_app(db_path))
    r = client.get("/")
    assert r.status_code == 200 and "scrapex crawl" in r.text
