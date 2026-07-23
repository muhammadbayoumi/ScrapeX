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


def test_data_landing_lists_the_source(client):
    r = client.get("/data")
    assert r.status_code == 200
    assert "ELSEWEDYSHOP" in r.text and "السويدي شوب" in r.text


def test_overview_summarizes_the_workspace_and_data_keeps_its_browser(client):
    overview = client.get("/").text
    landing = client.get("/data").text
    selected = client.get("/source/ELSEWEDYSHOP").text

    assert 'class="overview-page"' in overview
    assert "Everything at a glance" in overview
    assert 'href="/" title="Overview" aria-current="page"' in overview
    assert "Price observations" in overview
    assert 'data-overview-source="ELSEWEDYSHOP"' in overview
    assert overview.count("data-overview-source=") <= 6
    assert "more datasets" in overview
    assert 'class="data-workspace"' in landing
    assert 'class="dataset-browser"' in landing
    assert 'data-dataset-choice' in landing
    assert 'data-dataset-toggle' in landing
    assert '/static/datasets-browser.js' in landing
    assert 'aria-current="page"' in selected
    assert 'aria-label="Selected dataset"' in selected
    assert 'class="wrap wrap-wide"' in selected
    assert '/static/datasets-browser.js' in selected
    assert 'data-grid-datasets-toggle' in selected
    assert '<span>Datasets</span>' in selected
    assert selected.index('data-grid-datasets-toggle') < selected.index('id="grid-features"')
    for region in ("data-source-overview", "data-controls", "data-records"):
        assert f'class="{region}"' in selected
    assert "Workspace tools" in selected
    assert 'class="data-grid-frame-head"' in selected
    assert 'class="data-grid-count"' not in selected
    assert 'class="data-grid-exportbar"' in selected
    assert 'class="data-control-primary"' not in selected
    assert '<form class="filters"' not in selected


def test_data_canvas_stays_centered_without_overlapping_the_dataset_toggle():
    styles = (Path(__file__).parents[1] / "scrapex" / "webui" / "static" /
              "pages" / "data-workspace.css").read_text(encoding="utf-8")

    assert "--data-canvas-width:82rem" in styles
    assert "justify-self:safe center" in styles
    assert "grid-template-columns:3.25rem minmax(0,1fr) 3.25rem" in styles
    assert '.data-workspace.datasets-collapsed::after{content:"";grid-column:3}' in styles
    assert "translateX(-2.125rem)" not in styles
    assert "overflow-x:auto" in styles
    assert styles.count("var(--data-canvas-width)") >= 2


def test_dataset_identity_leads_with_english_and_links_the_website(client):
    selected = client.get("/source/ELSEWEDYSHOP").text

    english = selected.index("<h1>ELSEWEDYSHOP</h1>")
    arabic = selected.index("السويدي شوب", english)
    assert english < arabic
    assert 'class="dataset-local-name"' in selected
    assert 'class="dataset-site-link" href="https://elsewedyshop.com"' in selected
    assert 'target="_blank"' in selected and 'rel="noopener noreferrer"' in selected


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


def test_changes_page_offers_the_rebuild_control(client):
    """The repair path for a stranded derived layer must be reachable from the
    UI — offer.html's empty state sends the owner here to use it."""
    r = client.get("/changes?source_key=ELSEWEDYSHOP")
    assert r.status_code == 200
    assert "Rebuild price history" in r.text
    assert "/api/prices/rebuild" in r.text


def test_rebuild_endpoint_repairs_a_stranded_derived_layer(client):
    """End-to-end shape of the live incident: observations exist, offer_state
    and price_period do not. One POST puts the derived layer back."""
    # Strand the offer the way the incident did — evidence intact, layers gone.
    # Both layers are mutable BY DESIGN (they are rebuildable); the evidence
    # beneath them is trigger-protected and never touched.
    db_path = client.app.state.db_path
    conn = dbmod.connect(db_path)
    try:
        conn.execute("DELETE FROM price_period")
        conn.execute("DELETE FROM offer_state")
        conn.commit()
        offers = conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0]
        assert offers > 0
    finally:
        conn.close()

    r = client.post("/api/prices/rebuild", json={"source_key": "ELSEWEDYSHOP"})
    assert r.status_code == 200
    assert r.json()["offers"] == offers

    conn = dbmod.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM offer_state").fetchone()[0] == offers
        assert conn.execute(
            "SELECT COUNT(DISTINCT offer_id) FROM price_period").fetchone()[0] == offers
    finally:
        conn.close()


def test_empty_db_overview_has_hint(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    conn.close()
    client = TestClient(create_app(db_path))
    r = client.get("/data")
    assert r.status_code == 200
    # An empty warehouse no longer means an empty page: the configured sources
    # are listed as "never run", each with the command that would run it. The
    # command is spelled the way it actually works — `scrapex` alone is not on
    # PATH after a plain editable install.
    assert "python -m scrapex.cli crawl" in r.text
    assert "Never run" in r.text
