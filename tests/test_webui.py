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


def test_overview_summarizes_the_workspace_and_data_uses_one_dropdown(client):
    overview = client.get("/").text
    landing = client.get("/data").text
    selected = client.get("/source/ELSEWEDYSHOP").text

    assert 'class="overview-page"' in overview
    assert "Your data pipeline" in overview
    assert "From source to delivery" in overview
    assert "Needs your attention" in overview
    assert overview.count("data-overview-stage=") == 5
    for stage in ("sources", "run", "data", "changes", "deliver"):
        assert f'data-overview-stage="{stage}"' in overview
    assert 'href="/" title="Overview" aria-current="page"' in overview
    assert "Data rows" in overview
    assert 'data-overview-source="ELSEWEDYSHOP"' in overview
    assert overview.count("data-overview-source=") <= 6
    assert "more datasets" in overview
    assert 'class="data-workspace"' in landing
    assert 'class="dataset-menu data-landing-dataset-menu"' in landing
    assert 'class="dataset-menu-popover"' in landing
    assert 'data-dataset-choice' in landing
    assert 'data-dataset-toggle' not in landing
    assert '/static/datasets-browser.js' in landing
    assert 'aria-current="page"' in selected
    assert 'aria-label="Selected dataset"' in selected
    assert 'class="wrap wrap-wide"' in selected
    assert '/static/datasets-browser.js' in selected
    assert 'data-grid-datasets-toggle' not in selected
    assert '<span>Datasets</span>' in selected
    assert selected.index('class="dataset-menu"') < selected.index('id="grid-features"')
    for region in ("data-source-overview", "data-records"):
        assert f'class="{region}"' in selected
    assert "Workspace tools" not in selected
    assert 'class="data-controls"' not in selected
    assert 'class="data-grid-frame-head"' in selected
    assert 'class="data-grid-count"' not in selected
    assert 'class="data-grid-exportbar"' in selected
    assert 'class="dataset-run-footer"' in selected
    assert selected.index('class="data-grid-exportbar"') < selected.index(
        'class="dataset-run-footer"')
    assert 'class="workspace-footer"' in selected
    assert 'class="data-control-primary"' not in selected
    assert '<form class="filters"' not in selected


def test_data_canvas_stays_centered_and_the_dataset_menu_is_a_popover():
    styles = (Path(__file__).parents[1] / "scrapex" / "webui" / "static" /
              "pages" / "data-workspace.css").read_text(encoding="utf-8")

    assert "--data-canvas-width:82rem" in styles
    assert "width:min(100%,var(--data-canvas-width))" in styles
    assert ".dataset-menu-popover{position:absolute" in styles
    assert "datasets-collapsed" not in styles
    assert "grid-template-columns:15.25rem" not in styles
    assert styles.count("var(--data-canvas-width)") >= 1


def test_dataset_identity_leads_with_the_domain_and_links_the_website(client):
    """The domain is the stable human-scannable identity. Names follow it,
    while the key remains visible as the URL and API identifier."""
    selected = client.get("/source/ELSEWEDYSHOP").text

    domain = selected.index("elsewedyshop.com")
    name = selected.index("السويدي شوب")
    key = selected.index("ELSEWEDYSHOP", name)
    assert domain < name < key
    assert 'class="source-identity-key"' in selected
    assert 'class="dataset-site-link" href="https://elsewedyshop.com"' in selected
    assert 'target="_blank"' in selected and 'rel="noopener noreferrer"' in selected


def test_the_heading_and_the_listing_carry_the_english_name_too(tmp_path: Path):
    """The domain leads, followed by English · local name, then the key."""
    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(source_name_en="Elsewedy Shop"),
                    [make_payload([one_row()])])
    conn.commit()
    conn.close()

    page = TestClient(create_app(db_path)).get("/source/ELSEWEDYSHOP").text

    # The heading block follows the one canonical source order.
    english = '<span class="source-identity-name-en" dir="ltr">Elsewedy Shop</span>'
    assert english in page
    assert (page.index("elsewedyshop.com") < page.index(english)
            < page.index("السويدي شوب")
            < page.index('<code class="source-identity-key">ELSEWEDYSHOP</code>'))
    # The same rule inside the dataset popover — for the source with data, and
    # for one that is only configured, whose names come from the manifest.
    assert '<span class="source-identity-name-en" dir="ltr">Elsewedy Shop</span>' in page
    assert '<span class="source-identity-name-en" dir="ltr">Global Petrol Prices</span>' in page
    # And a search over the list answers to either name, not the Arabic one only.
    assert 'data-search="السويدي شوب elsewedy shop elsewedyshop"' in page


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


def test_the_excel_export_carries_every_sheet_not_just_the_grid(client):
    """The owner exported to Excel and got the price table alone.

    Two failures in one button: the workbook the browser could build holds only
    what is in the grid, and the button called Tabulator's xlsx writer, which
    needs a SheetJS library this project has never vendored — so it produced no
    file at all. The download now comes from the server with every sheet.
    """
    openpyxl = pytest.importorskip("openpyxl")
    from io import BytesIO

    r = client.get("/export/ELSEWEDYSHOP.xlsx")

    assert r.status_code == 200
    assert r.headers["content-type"].endswith("spreadsheetml.sheet")
    assert 'attachment; filename="ELSEWEDYSHOP-' in r.headers["content-disposition"]
    book = openpyxl.load_workbook(BytesIO(r.content))
    assert book.sheetnames[0] == "ELSEWEDYSHOP"
    # The provenance sheet always rides along: a workbook outlives the screen it
    # came from, and a price with no source, date or tax statement is a number.
    about = [s for s in book.sheetnames if s.endswith("about")]
    assert about, f"no provenance sheet in {book.sheetnames}"
    facts = {row[0].value: row[1].value for row in book[about[0]].iter_rows(min_row=2)}
    assert facts["source_key"] == "ELSEWEDYSHOP"
    assert facts["products"] == 2
    prices = book["ELSEWEDYSHOP"]
    assert prices.max_row == 3          # header + the two ingested rows
    assert prices.freeze_panes == "A2"


def test_exporting_a_source_with_nothing_ingested_says_so(client):
    r = client.get("/export/NOSUCHSOURCE.xlsx")
    assert r.status_code == 404
    assert "crawl" in r.json()["detail"]


def test_the_schema_page_is_derived_not_written(client):
    """The owner asked for a page he can read and review with me. Written by
    hand it would be wrong within a week, so it is derived: the columns come
    from the same lists the table and the export are built from, and who fills
    them is counted from the warehouse. This pins that it is derived - a column
    the fixture's source populates must appear WITH that source's name."""
    r = client.get("/schema")

    assert r.status_code == 200
    assert "ELSEWEDYSHOP" in r.text, "the page never asked the warehouse"
    assert "<code>effective_price</code>" in r.text
    assert "What one price BUYS" in r.text, "the meaning of a column is missing"
    # The rules the whole schema follows are stated on it, not left implicit.
    assert "states the language of its content" in r.text
    assert "Nothing is computed into a price" in r.text


def test_the_schema_page_never_reads_a_plan_as_a_fact(client):
    """The owner read the first version of this page, saw product_name described
    as "the product's name, in English" while it holds Arabic, and asked why the
    agreed vocabulary had been reversed. It had not: the rename has not run yet,
    and the page had written the plan's meaning onto today's columns.

    A page whose whole claim is that it cannot drift from the product must
    describe the product AS IT IS, and say plainly where it is going."""
    body = client.get("/schema").text

    assert "Arabic on every bilingual source today" in body, \
        "product_name is described as English while it holds Arabic"
    assert "It has not been applied yet" in body, \
        "the page presents the pending vocabulary as if it were live"
    # Current name and future name, side by side, for every column that moves.
    assert "<code>product_name_ar</code>" in body
    assert "Becomes" in body


def test_the_schema_page_shows_the_whole_warehouse(client):
    """The owner opened this page to review the data model and found one table
    on it — the Data page's columns. What he asked for is the warehouse: every
    table, and what each one is FOR."""
    body = client.get("/schema").text

    for table in ("source_site", "source_product", "source_variant",
                  "source_offer", "price_observation", "price_period",
                  "change_event", "crawl_run", "dataset_field"):
        assert f"<code>{table}</code>" in body, f"{table} is missing from the schema page"
    # Grouped in the order the data moves, not alphabetically.
    assert body.index("What the source said") < body.index("What it costs")
    assert body.index("What it costs") < body.index("Your unified layer")
    # And the purposes are there, not just the names.
    assert "append-only" in body or "never edited" in body


def test_every_column_says_which_table_it_came_from(client):
    """The owner, reviewing the schema: "put the table name beside each column
    so I know which table it came from."

    Read from the query's own SQL wherever there is one, so a column that moves
    tables cannot keep a stale note. What is computed says COMPUTED instead of
    naming a table it does not live in."""
    body = client.get("/schema").text

    assert "Comes from" in body
    assert "<code>source_product.source_name</code>" in body
    assert "<code>source_offer.region</code>" in body
    assert "<code>price_observation.effective_price</code>" in body
    assert "computed: price_observation.regular_price" in body, \
        "a discount is not stored anywhere; saying it is would be a lie"


def test_the_data_model_page_draws_the_live_relational_model(client):
    """The model is a view of SQLite, not a hand-maintained architecture image:
    real table cards, key fields and foreign keys all reach the page."""
    response = client.get("/data-model")

    assert response.status_code == 200
    body = response.text
    assert "<h1>Data Model</h1>" in body
    for table in ("source_site", "source_product", "source_variant",
                  "source_offer", "price_observation", "crawl_run"):
        assert f'data-table="{table}"' in body
    assert "<span class=\"key-badge pk\">PK</span>" in body
    assert "<span class=\"key-badge fk\">FK</span>" in body
    assert '"from_table": "source_product"' in body
    assert '"to_table": "source_site"' in body
    assert "How ScrapeX works" in body
    assert "Every answer keeps lineage" in body


def test_data_model_is_a_first_class_workspace_destination(client):
    response = client.get("/data-model")

    assert 'href="/data-model"' in response.text
    assert 'aria-current="page"' in response.text
    assert "/static/pages/data-model.css" in response.text
    assert "/static/pages/data-model.js" in response.text
