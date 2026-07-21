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


# The rows are rendered by the grid in the browser now, so asserting product
# names in the server's HTML would only prove the template still inlines them.
# The question these tests were really asking — does the page carry the right
# rows — is asked of the payload the grid is built from.

def test_the_page_delivers_this_sources_rows(client):
    assert client.get("/source/ELSEWEDYSHOP").status_code == 200

    payload = client.get("/api/table/ELSEWEDYSHOP").json()

    names = {row["product_name"] for row in payload["rows"]}
    assert "LED Floodlight 400W" in names
    assert "Copper Wire" in names


def test_the_payload_carries_what_a_filter_needs_to_work_on(client):
    """Filtering moved into the grid, which filters what it was sent. So the
    server's job is to send the fields the filters name — and to send every row,
    not the 50 that used to be a page."""
    payload = client.get("/api/table/ELSEWEDYSHOP").json()

    assert payload["returned"] == payload["total"], "the grid filters what it holds"
    assert {"product_name", "availability"} <= set(payload["rows"][0])
    assert {"out_of_stock", "in_stock"} & {r["availability"] for r in payload["rows"]}


def test_a_source_with_no_rows_says_so_rather_than_failing(client):
    payload = client.get("/api/table/NOPE").json()
    assert payload["rows"] == [] and payload["total"] == 0


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
    assert r.status_code == 200
    # An empty warehouse no longer means an empty page: the configured sources
    # are listed as "never run", each with the command that would run it. The
    # command is spelled the way it actually works — `scrapex` alone is not on
    # PATH after a plain editable install.
    assert "python -m scrapex.cli crawl" in r.text
    assert "Never run" in r.text
