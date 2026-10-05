"""The grid asks the engine its host names, and the engine's own page names none (#1198).

The extension's Data page is to run THIS grid.js, from `chrome-extension://…`, where a
root-relative `/api/table/…` would ask the extension instead of the engine. So the grid
takes two things from a host page, `window.ScrapeXGridHost`, and nothing else:

- `base`, which goes in front of every engine address it writes: nine fetches, the
  Excel download and the Full record link;
- `loadTable`, which fetches the table, so the extension can send it through its own
  guarded request path (the backend-generation guard, the deadline, `site_key`, the
  activity filter).

The engine's page sets no host, so every address stays root-relative and the table is
fetched exactly as before. That is the property the grid's other 25 browser tests
already stand on, and the first test here states it outright.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright

import grid_harness as harness  # noqa: E402

GRID = ROOT / "scrapex" / "webui" / "static" / "grid.js"

#: An engine address nothing listens on. Every fetch is answered by the harness's stub,
#: and the one navigation (Excel) is aborted by the browser context before it leaves.
ENGINE = "http://127.0.0.1:9"


def _payload() -> dict:
    def row(name, price, offer_id):
        return {"product_name": name, "price": price, "currency": "SAR",
                "offer_id": offer_id, "tax_ref": 0, "product_link": "",
                "availability": "in_stock"}
    return {
        "source_key": "TESTSRC",
        "columns": [{"key": "product_name", "label": "Product name"},
                    {"key": "price", "label": "Price"}],
        "rows": [row("Alpha cement", 135.24, 1), row("Beta rebar", 0.81, 2),
                 row("Zinc sheet", 9.66, 3)],
        "tax_states": [{"tax_short": "Incl. 15%", "tax": "Includes VAT"}],
        "total": 3, "returned": 3, "truncated": False, "tree": None,
        "bilingual": {}, "moved_to_details": [],
    }


FIELDS = {"fields": [{"field_key": "product_name", "display_name": "Product name",
                      "is_hidden": False},
                     {"field_key": "price", "display_name": "Price", "is_hidden": False}]}
PROMOTABLE = {"attributes": [{"attribute_code": "colour", "label": "Colour",
                              "products": 2, "of_products": 3, "promoted": False,
                              "by_the_site": False}]}
OFFER = {"periods": [], "changes": [], "observations": [], "attributes": []}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_grid(browser, tmp_path):
    contexts = []

    def opener(*, host_js=None, icon_sprite=None, expect_rows=True):
        target = harness.build_page(tmp_path, _payload(), fields=FIELDS,
                                    promotable=PROMOTABLE, offer=OFFER,
                                    host_js=host_js, icon_sprite=icon_sprite,
                                    name=f"grid{len(contexts)}.html")
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        contexts.append(context)
        context.route(f"{ENGINE}/**", lambda route: route.abort())
        page = context.new_page()
        page.navigations = []
        page.on("request", lambda r: page.navigations.append(r.url)
                if r.is_navigation_request() else None)
        # Before goto, so an error grid.js throws while it starts is on the record.
        page.errors = []
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        page.goto(f"{base}/{target.name}")
        if expect_rows:
            page.wait_for_function(
                "() => document.querySelectorAll('#grid .dg-body .dg-row').length > 0")
        return page

    # SERVED, because the grid's renderer is a module and file:// refuses modules.
    with harness.serve(tmp_path) as base:
        yield opener
        for context in contexts:
            context.close()


def _drive(page) -> dict:
    """Every action that writes an engine address, in the order he could press them:
    select one row (its offer, and the Full record link on its History view), then a
    second (an offer per selected card); open Choose Columns (fields and promotable),
    change a column (the fields POST) and promote a detail (the promotable POST).
    Excel goes last, because it leaves the page. The chooser stays open to the end:
    closing it after a change reloads the page, and the reload would take the log."""
    page.evaluate("""() => document.querySelector(
        '#grid .dg-body .dg-row[data-index="0"] .dg-select').click()""")
    page.click('#offer-panel [data-inspector-view="history"]')
    page.wait_for_selector("#offer-panel a.record-action", timeout=5000)
    links = page.eval_on_selector_all(
        "#offer-panel a.record-action", "links => links.map(a => a.getAttribute('href'))")
    page.evaluate("""() => document.querySelector(
        '#grid .dg-body .dg-row[data-index="1"] .dg-select').click()""")
    page.wait_for_function(
        "() => window.__requests.filter(r => r.path.includes('/api/offer/')).length >= 3")

    page.click("#grid-columns-button")
    page.wait_for_selector(".column-chooser-row", timeout=5000)
    page.wait_for_selector(".column-chooser-promote-row input", timeout=5000)
    page.evaluate("""() => {
        const box = document.querySelector(
          '.column-chooser-row:not(.column-chooser-promote-row) input[type=checkbox]');
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    page.click(".column-chooser-promote-row input")
    page.wait_for_function(
        "() => window.__posts.filter(p => p.path.includes('/api/')).length >= 2")
    seen = {"requests": page.evaluate("() => window.__requests"), "links": links}
    # The button's own click, because the open chooser's backdrop covers it.
    with page.expect_request(lambda r: "/export/" in r.url) as navigation:
        page.evaluate("() => document.querySelector('[data-split-action=\"xlsx\"]').click()")
    seen["excel"] = navigation.value.url
    return seen


def test_the_engines_own_page_names_no_host_and_every_address_stays_root_relative(
        open_grid):
    page = open_grid()
    origin = page.evaluate("() => location.origin")
    seen = _drive(page)

    paths = [request["path"] for request in seen["requests"]]
    assert paths[0] == "/api/table/TESTSRC", paths
    assert all(path.startswith("/api/") for path in paths), paths
    for needed in ("/api/fields/TESTSRC", "/api/promotable/TESTSRC",
                   "/api/offer/TESTSRC/1", "/api/offer/TESTSRC/2"):
        assert needed in paths, f"{needed} was never asked for: {paths}"
    assert {"POST /api/fields/TESTSRC", "POST /api/promotable/TESTSRC"} <= {
        f"{r['method']} {r['path']}" for r in seen["requests"]}
    assert "/source/TESTSRC/offer/1" in seen["links"], seen["links"]
    assert seen["excel"].endswith("/export/TESTSRC.xlsx")
    assert seen["excel"].startswith(origin + "/"), (
        f"the engine page's Excel left its own origin: {seen['excel']}")


def test_a_host_base_goes_in_front_of_every_engine_address(open_grid):
    seen = _drive(open_grid(host_js=f"window.ScrapeXGridHost = {{base: {json.dumps(ENGINE)}}};"))

    paths = [request["path"] for request in seen["requests"]]
    assert paths[0] == f"{ENGINE}/api/table/TESTSRC", paths
    strays = [path for path in paths if not path.startswith(f"{ENGINE}/api/")]
    assert not strays, f"these still asked the page's own origin: {strays}"
    for needed in ("/api/fields/TESTSRC", "/api/promotable/TESTSRC",
                   "/api/offer/TESTSRC/1", "/api/offer/TESTSRC/2"):
        assert f"{ENGINE}{needed}" in paths, f"{needed} was never asked for: {paths}"
    assert {f"POST {ENGINE}/api/fields/TESTSRC", f"POST {ENGINE}/api/promotable/TESTSRC"} <= {
        f"{r['method']} {r['path']}" for r in seen["requests"]}
    assert f"{ENGINE}/source/TESTSRC/offer/1" in seen["links"], seen["links"]
    assert seen["excel"] == f"{ENGINE}/export/TESTSRC.xlsx"


HOST_LOADER = """
window.__loaded = [];
window.ScrapeXGridHost = {
  loadTable: (path) => {
    window.__loaded.push(path);
    return Promise.resolve(Object.assign({}, window.__payload,
      {rows: window.__payload.rows.slice(0, 2), total: 2, returned: 2}));
  },
};
"""


def test_a_host_loader_is_asked_for_the_table_and_its_answer_is_drawn(open_grid):
    page = open_grid(host_js=HOST_LOADER)

    assert page.evaluate("() => window.__loaded") == ["/api/table/TESTSRC"]
    assert page.evaluate("() => ScrapeXDataGrid.find('#grid').getDataCount()") == 2, (
        "the grid drew something other than what the host's loader answered")
    tables = [r for r in page.evaluate("() => window.__requests")
              if "/api/table/" in r["path"]]
    assert not tables, f"the grid fetched the table itself as well: {tables}"


def test_a_host_that_names_both_gets_its_loader_for_the_table_and_its_base_for_the_rest(
        open_grid):
    """The configuration the extension's Data page ships: data.js loads the table
    through its own request path, and grid.js writes every other address to the
    engine. The loader is handed the path WITHOUT the base — it adds the engine
    itself — and the grid asks the engine for nothing it has already been given."""
    page = open_grid(host_js=HOST_LOADER.replace(
        "window.ScrapeXGridHost = {",
        f"window.ScrapeXGridHost = {{\n  base: {json.dumps(ENGINE)},"))

    assert page.evaluate("() => window.__loaded") == ["/api/table/TESTSRC"]
    page.evaluate("""() => document.querySelector(
        '#grid .dg-body .dg-row[data-index="0"] .dg-select').click()""")
    page.wait_for_function(
        "() => window.__requests.some(r => r.path.includes('/api/offer/'))")
    paths = [r["path"] for r in page.evaluate("() => window.__requests")]
    assert not [p for p in paths if "/api/table/" in p], (
        f"the grid fetched the table itself as well: {paths}")
    assert f"{ENGINE}/api/offer/TESTSRC/1" in paths, paths
    strays = [p for p in paths if not p.startswith(f"{ENGINE}/api/")]
    assert not strays, f"these still asked the page's own origin: {strays}"


def test_the_loader_is_handed_the_readers_fold_choice(open_grid):
    page = open_grid(host_js="localStorage.setItem('scrapex-fold-variants-TESTSRC', 'on');"
                             + HOST_LOADER)
    assert page.evaluate("() => window.__loaded") == ["/api/table/TESTSRC?fold=1"]


def test_a_loader_that_fails_is_said_on_the_page(open_grid):
    page = open_grid(host_js="window.ScrapeXGridHost = {loadTable: () => "
                             "Promise.reject(new Error('the engine did not answer'))};",
                     expect_rows=False)
    page.wait_for_function("() => !document.getElementById('grid-note').hidden")
    assert page.text_content("#grid-note") == (
        "Could not load the table: the engine did not answer")


@pytest.mark.parametrize("host_js", [
    "window.ScrapeXGridHost = {base: 42, loadTable: 'not a function',"
    " connect: 'not a function'};",
    "window.ScrapeXGridHost = {};",
    # An element whose id is the name: `window.ScrapeXGridHost` is then that element.
    "document.body.insertAdjacentHTML('beforeend', '<div id=\"ScrapeXGridHost\"></div>');",
], ids=["wrong-types", "empty", "clobbered-by-an-element"])
def test_a_host_that_names_nothing_usable_is_the_engines_page(open_grid, host_js):
    """If this fails, a host whose `connect` is not a function breaks the page with an
    uncaught TypeError as the grid starts: the string is called instead of ignored."""
    page = open_grid(host_js=host_js)
    paths = [request["path"] for request in page.evaluate("() => window.__requests")]
    assert paths == ["/api/table/TESTSRC"], paths
    assert page.errors == []


@pytest.mark.parametrize("sprite,href", [
    (None, "/static/material-icons/material-icons.svg?v=design-system-3#close"),
    ("icons/material-icons.svg", "icons/material-icons.svg#close"),
    ("", "#close"),
], ids=["the-engine-page", "a-host-sprite", "inline-symbols"])
def test_ui_takes_its_sprite_from_its_own_tag(open_grid, sprite, href):
    page = open_grid(icon_sprite=sprite)
    assert f'href="{href}"' in page.evaluate("() => window.ScrapeXUI.icon('close')")


def test_no_engine_address_in_the_grid_is_written_without_the_base():
    """The one address no action reaches is `remember()`'s, whose only caller is the
    dead `hide()`. This holds it, and any address added later, to the same rule."""
    source = GRID.read_text(encoding="utf-8")
    written = re.findall(r'(.{0,24})"/(?:api|export|source)/', source)
    unprefixed = [before for before in written
                  if not before.endswith("BASE + ") and not before.endswith("loadTable(")]
    assert not unprefixed, f"engine addresses written without BASE: {unprefixed}"
    assert sum(before.endswith("BASE + ") for before in written) == 10, written
