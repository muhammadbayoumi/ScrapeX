"""The Datasets page's records, drawn by the grid's renderer in a real browser.

`/datasets` browses an approved dataset whose fields were DISCOVERED on a crawled page,
so both its column titles and its cells are strings a site controls. Its grid is
datagrid.js, imported as a module when the page loads; nothing else drives this page in a
browser, so a regression in how it draws, sorts, filters, pages or fails to load the
renderer would ship unseen.

The page is the engine's own app, served through its TestClient with Chromium's requests
routed to it (as tests/test_the_focus_ring_draws_in_the_web_ui.py does), over a warehouse
built from the real db/engine/schema.sql by DatabaseRegistry. The dataset is approved the
way tests/test_extract_api.py approves one: save the HTML, detect its table, approve it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.webui.app import create_app
from tests.test_panel_dom import browser  # the fixture, one Chromium per module

ORIGIN = "http://webui.test"
# A column title and a cell value a hostile site could publish. Either one written
# through innerHTML would draw an <img> and run its handler.
HOSTILE_HEADER = "<img src=x onerror=window.__pwned=1>"
HOSTILE_CELL = "<img src=x onerror=window.__pwned=2>"
ROWS = 60  # the records API pages by 50, so this is two pages: 50 and 10


def _html() -> str:
    cells = "".join(
        f"<tr><td>R{i}</td>"
        f"<td>{'&lt;img src=x onerror=window.__pwned=2&gt;' if i == 0 else f'الرياض {i}'}</td>"
        f"<td>{i * 7}</td></tr>"
        for i in range(ROWS))
    return ("<table><caption>Offices</caption>"
            "<tr><th>Office code</th><th>Office name</th><th>Employees</th></tr>"
            f"{cells}</table>")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("datasets")
    registry = DatabaseRegistry(EngineDatabase(tmp / "scrapex-engine.db"),
                                pointer_file=tmp / "databases.json")
    registry.initialize()
    with TestClient(create_app(databases=registry)) as client:
        saved = client.post("/api/general/extract/snapshots", json={
            "source_url": "https://example.com/offices", "html_content": _html()})
        assert saved.status_code == 201, saved.text
        snapshot_id = saved.json()["page_snapshot_id"]
        found = client.get(f"/api/general/extract/snapshots/{snapshot_id}/candidates")
        assert found.status_code == 200, found.text
        candidate = found.json()["candidates"][0]
        identity = set(candidate["candidate_identity_fields"])
        fields = [{
            "field_key": field["field_key"],
            # The second column's title is the hostile one.
            "display_name": HOSTILE_HEADER if index == 1 else field["display_name"],
            "data_type": field["data_type"],
            "identity": field["field_key"] in identity,
        } for index, field in enumerate(candidate["fields"])]
        approved = client.post(f"/api/general/extract/snapshots/{snapshot_id}/approve", json={
            "table_index": candidate["table_index"], "site_key": "example_site",
            "site_display_name": "Example site", "dataset_key": "offices",
            "dataset_name": "Offices", "fields": fields})
        assert approved.status_code == 201, approved.text
        yield client


def _open(browser, client, *, break_renderer=False):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def serve(route):
        request = route.request
        answer = client.request(request.method, request.url[len(ORIGIN):],
                                content=request.post_data_buffer,
                                headers={"content-type": request.headers.get("content-type", "")})
        route.fulfill(status=answer.status_code, body=answer.content,
                      headers={"content-type": answer.headers.get("content-type", "text/plain")})

    page.route("**/*", lambda route: route.abort())  # nothing leaves the machine
    page.route(f"{ORIGIN}/**", serve)
    if break_renderer:
        # Registered last, so it is asked first: the renderer module answers 404.
        page.route(f"{ORIGIN}/static/datagrid.js*",
                   lambda route: route.fulfill(status=404, body="not found"))
    response = page.goto(ORIGIN + "/datasets")
    assert response is not None and response.status == 200
    page.wait_for_selector("#dataset-list .dataset-item button")
    page.click("#dataset-list .dataset-item button")
    page.wait_for_function(
        "() => /^(Success|Failure|Empty):/.test(document.querySelector('#records-state').textContent)")
    return page, errors


@pytest.fixture()
def records(browser, client):
    page, errors = _open(browser, client)
    try:
        yield page, errors
    finally:
        page.close()


def _first_cells(page):
    """The first cell of every drawn body row, in data order."""
    return page.evaluate("""() => [...document.querySelectorAll('#records-table .dg-body .dg-row')]
        .sort((a, b) => a.dataset.index - b.dataset.index)
        .map(row => row.querySelector('.dg-cell').textContent)""")


def _header(page, title):
    return page.locator("#records-table .dg-col", has_text=title)


def test_the_records_draw_through_the_grid_and_hostile_strings_stay_text(records):
    page, errors = records
    state = page.locator("#records-state").text_content()
    assert state.startswith("Success: 50 records are displayed"), state
    assert page.locator(".dg").count() == 1
    assert page.locator("#records-table.dg").count() == 1, "the grid is not in the records' place"
    assert len(_first_cells(page)) > 1
    titles = page.evaluate("""() => [...document.querySelectorAll('#records-table .dg-col')]
        .map(c => c.querySelector('.dg-col-content').textContent)""")
    assert any(HOSTILE_HEADER in title for title in titles), titles
    cells = page.evaluate(
        "() => [...document.querySelectorAll('#records-table .dg-body .dg-cell')].map(c => c.textContent)")
    assert HOSTILE_CELL in cells, "the hostile cell should show as its own text"
    assert page.evaluate("() => document.querySelectorAll('#records-table img').length") == 0
    assert page.evaluate("() => window.__pwned") is None, "scraped markup ran"
    assert not errors, errors


def test_a_header_click_sorts_and_shows_the_sort_arrow(records):
    page, _ = records
    employees = _header(page, "Employees")
    assert employees.get_attribute("aria-sort") == "none"
    arrow = employees.locator(".dg-sort svg.material-sort-icon")
    assert arrow.count() == 1, "the sortable header carries no arrow icon"

    employees.locator(".dg-col-content").click()
    page.wait_for_function(
        "() => [...document.querySelectorAll('#records-table .dg-col')]"
        "  .some(c => /Employees/.test(c.textContent) && c.getAttribute('aria-sort') === 'ascending')")
    assert _first_cells(page)[:3] == ["R0", "R1", "R2"]
    assert _header(page, "Employees").locator(".dg-sort svg.material-sort-icon").is_visible()

    _header(page, "Employees").locator(".dg-col-content").click()
    page.wait_for_function(
        "() => [...document.querySelectorAll('#records-table .dg-col')]"
        "  .some(c => /Employees/.test(c.textContent) && c.getAttribute('aria-sort') === 'descending')")
    # Numbers, not text: 343 (R49) leads, not 98 (R14) as "98" > "343" would put it.
    assert _first_cells(page)[:3] == ["R49", "R48", "R47"]


def test_the_header_filter_narrows_the_rows(records):
    page, _ = records
    before = len(_first_cells(page))
    assert before > 1
    _header(page, "Office code").locator("input.dg-header-input").fill("R5")
    page.wait_for_function(
        "() => document.querySelectorAll('#records-table .dg-body .dg-row').length === 1")
    assert _first_cells(page) == ["R5"]
    _header(page, "Office code").locator("input.dg-header-input").fill("")
    page.wait_for_function(
        f"() => document.querySelectorAll('#records-table .dg-body .dg-row').length === {before}")


def _one_grid(page):
    """One grid, drawn once: the mount carries `.dg`, and a grid built over another
    without destroying it would leave a second header and body inside it."""
    assert page.locator(".dg").count() == 1, "a second grid was drawn beside the first"
    assert page.locator("#records-table .dg-header-row").count() == 1
    assert page.locator("#records-table .dg-body").count() == 1


def test_the_next_page_replaces_the_grid_rather_than_adding_one(records):
    page, errors = records
    _one_grid(page)
    page.click("#next-records")
    page.wait_for_function(
        "() => /^Success: 10 records/.test(document.querySelector('#records-state').textContent)")
    _one_grid(page)
    assert _first_cells(page) == [f"R{i}" for i in range(50, ROWS)]
    page.click("#previous-records")
    page.wait_for_function(
        "() => /^Success: 50 records/.test(document.querySelector('#records-state').textContent)")
    _one_grid(page)
    assert not errors, errors


def test_a_renderer_that_does_not_load_is_said_in_the_records_state(browser, client):
    page, _ = _open(browser, client, break_renderer=True)
    try:
        state = page.locator("#records-state")
        assert state.is_visible()
        text = state.text_content()
        assert text.startswith("Failure: The grid's library did not load"), text
        assert "Reload the page." in text, text
        assert page.locator(".dg, .dg-row").count() == 0, "a grid was drawn without its renderer"
    finally:
        page.close()
