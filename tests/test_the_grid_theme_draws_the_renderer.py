"""The grid's theme over the TanStack renderer, read in a real browser (#1342, #1465).

tests/test_datagrid_dom.py holds the renderer to its contract under a few
structural rules of its own. This file loads the sheets the Data page links, in
its order, and reads what the theme draws on the renderer's DOM: the places a
rule elsewhere in the project, or a state's colour, changed what a reader sees.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright

import tabpage_harness  # noqa: E402

# It reads the extension's copies of the sheets and the renderer.
pytestmark = pytest.mark.extension

EXT = ROOT / "extension"

#: The Data page's sheets, in extension/data.html's order.
SHEETS = ["tokens.css", "components.css", "data.css", "table-theme.css",
          "vendor/tabulator.min.css", "grid-theme.css", "data-workspace.css"]

PAGE = (
    "<!doctype html><meta charset='utf-8'><title>grid theme</title>"
    + "".join(f"<link rel='stylesheet' href='{sheet}'>" for sheet in SHEETS)
    + "<style>#grid { width: 700px; height: 400px; }</style>"
    "<div id='grid'></div>"
    "<script type='module'>"
    "import('./datagrid.js').then("
    "(module) => { window.DataGrid = module.DataGrid; window.__ready = true; },"
    "(error) => { window.__ready = 'the renderer did not load: ' + error; });"
    "</script>"
)


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("gridtheme")
    for sheet in SHEETS:
        (tmp / sheet).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXT / sheet, tmp / sheet)
    shutil.copyfile(EXT / "datagrid.js", tmp / "datagrid.js")
    shutil.copytree(EXT / "vendor" / "tanstack", tmp / "vendor" / "tanstack")
    (tmp / "index.html").write_text(PAGE, encoding="utf-8")
    with tabpage_harness.serve(tmp) as url:
        yield url


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture(params=["light", "dark"])
def page(request, browser, base):
    context = browser.new_context(viewport={"width": 1000, "height": 700},
                                  color_scheme=request.param)
    tab = context.new_page()
    errors = []
    tab.on("pageerror", lambda error: errors.append(str(error)))
    tab.goto(f"{base}/index.html")
    tab.wait_for_function("window.__ready !== undefined")
    assert tab.evaluate("window.__ready") is True, tab.evaluate("window.__ready")
    yield tab
    assert errors == []
    context.close()


def build(page, options: str) -> None:
    page.evaluate("(source) => { window.grid = new DataGrid(document.getElementById('grid'),"
                  " new Function('return (' + source + ')')()); }", options)
    page.wait_for_timeout(100)


def alpha(color: str) -> float:
    """The alpha of a computed colour: `rgb(...)` is opaque; `rgba(..., a)` and
    `color(srgb r g b / a)` carry theirs."""
    found = re.search(r"/\s*([\d.]+)\s*\)$", color) or re.search(r"rgba\([^)]*,\s*([\d.]+)\)$", color)
    return float(found.group(1)) if found else 1.0


PINNED = """{
  columns: [{formatter: "rowSelection", titleFormatter: "rowSelection", width: 40,
             frozen: "left", headerSort: false},
            {title: "Name", field: "name", frozen: "left", width: 150, topCalc: "count"},
            {title: "Size", field: "size", width: 600}, {title: "More", field: "more", width: 400}],
  data: Array.from({length: 10}, (_, i) => ({name: "n" + i, size: i, more: "UNDERNEATH"})),
  selectableRows: true,
}"""


def test_a_tree_or_group_toggle_draws_its_triangle_and_not_a_bar(page):
    """components.css stretches every button::before over its positioned
    ancestor as a hit area. The toggle's triangle is a ::before too, and drew a
    bar down the whole cell until it said `position: static`."""
    build(page, """{columns: [{title: "Name", field: "name"}, {title: "Brand", field: "brand"}],
                    data: [{name: "a", brand: "X", kids: [{name: "b", brand: "X"}]}],
                    dataTree: true, dataTreeChildField: "kids"}""")
    box = page.evaluate("""() => { const s = getComputedStyle(document.querySelector(".dg-tree-toggle"), "::before");
      return [s.position, parseFloat(s.width), parseFloat(s.height)]; }""")
    assert box[0] == "static" and box[1] <= 10 and box[2] <= 12, box
    page.evaluate("grid.destroy()")
    build(page, """{columns: [{title: "Name", field: "name"}, {title: "Brand", field: "brand"}],
                    data: [{name: "a", brand: "X"}], groupBy: ["brand"]}""")
    box = page.evaluate("""() => { const s = getComputedStyle(document.querySelector(".dg-group-toggle"), "::before");
      return [s.position, parseFloat(s.width), parseFloat(s.height)]; }""")
    assert box[0] == "static" and box[1] <= 10 and box[2] <= 12, box


def test_a_pinned_cell_is_opaque_in_a_selected_or_hovered_row(page):
    """A pinned cell inherited its row's translucent tint, so the column
    scrolling underneath showed through it. It is the scroller's surface with
    the row's tint laid over, and the tint still shows."""
    build(page, PINNED)
    page.locator('.dg-body .dg-row[data-index="1"] [data-field="name"]').click()
    page.evaluate("document.querySelector('.dg-scroller').scrollLeft = 200")
    page.mouse.move(5, 650)
    selected = page.evaluate("""() => { const c = getComputedStyle(
        document.querySelector('.dg-body .dg-row.dg-selected .dg-pinned'));
      return [c.backgroundColor, c.backgroundImage]; }""")
    assert alpha(selected[0]) == 1.0, selected
    assert "gradient" in selected[1], selected
    page.hover('.dg-body .dg-row[data-index="3"] [data-field="size"]')
    hovered = page.evaluate("""() => { const c = getComputedStyle(
        document.querySelector('.dg-body .dg-row[data-index="3"] .dg-pinned'));
      return [c.backgroundColor, c.backgroundImage]; }""")
    assert alpha(hovered[0]) == 1.0, hovered
    assert "gradient" in hovered[1], hovered


def test_a_striped_even_row_still_shows_its_selection_and_its_hover(page):
    """The stripe's selector outranked the selected and hover rules, so an even
    row kept the stripe when it was selected or pointed at."""
    build(page, PINNED)
    page.evaluate("document.getElementById('grid').classList.add('striped')")
    page.mouse.move(5, 650)
    tint = "() => getComputedStyle(document.querySelector('.dg-body .dg-row[data-index=\"%s\"]')).backgroundColor"
    stripe = page.evaluate(tint % 0)
    page.hover('.dg-body .dg-row[data-index="0"] [data-field="size"]')
    hover = page.evaluate(tint % 0)
    page.hover('.dg-body .dg-row[data-index="1"] [data-field="size"]')
    assert hover == page.evaluate(tint % 1) != stripe, "an even row hovered looks like an odd one"
    page.locator('.dg-body .dg-row[data-index="0"] [data-field="name"]').click()
    page.mouse.move(5, 650)
    selected = page.evaluate(tint % 0)
    page.evaluate("document.getElementById('grid').classList.remove('striped')")
    assert selected == page.evaluate(tint % 0), "a striped row selected looks like any row selected"
    assert selected not in (stripe, hover)


def test_the_totals_rows_pinned_cells_keep_its_tint(page):
    """The header's pinned surface reached the totals row's pinned cells too,
    which read grey beside the row's green."""
    build(page, PINNED)
    cells = page.evaluate("""() => Array.from(document.querySelectorAll('.dg-header .dg-calcs .dg-cell'))
      .map((c) => { const s = getComputedStyle(c); return [c.classList.contains('dg-pinned'), s.backgroundImage]; })""")
    pinned = [image for is_pinned, image in cells if is_pinned]
    assert pinned and all("gradient" in image for image in pinned), cells


def computed(page, selector: str, props: list[str], pseudo: str | None = None) -> dict:
    return page.evaluate("""([sel, props, pseudo]) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const s = getComputedStyle(el, pseudo);
      return Object.fromEntries(props.map((p) => [p, s.getPropertyValue(p)])); }""",
                         [selector, props, pseudo])


def test_the_header_and_the_pinned_columns_stay_put_while_the_rest_scroll(page):
    build(page, PINNED)
    assert computed(page, ".dg-header", ["position"])["position"] == "sticky"
    assert computed(page, ".dg-body .dg-pinned", ["position"])["position"] == "sticky"
    page.evaluate("document.querySelector('.dg-scroller').scrollLeft = 300")
    page.wait_for_timeout(50)
    left = page.evaluate("""() => [document.querySelector('.dg-body .dg-row .dg-pinned').getBoundingClientRect().left,
      document.getElementById('grid').getBoundingClientRect().left]""")
    assert left[0] - left[1] < 4, left


def test_a_resize_handle_is_a_target_with_its_cursor(page):
    build(page, PINNED)
    handle = computed(page, ".dg-header .dg-resize-handle", ["width", "cursor"])
    assert float(handle["width"].rstrip("px")) >= 8 and handle["cursor"] == "col-resize", handle


def test_a_group_band_reads_as_a_band_and_its_toggle_turns_when_open(page):
    build(page, """{columns: [{title: "Name", field: "name"}, {title: "Brand", field: "brand"}],
                    data: [{name: "a", brand: "X"}, {name: "b", brand: "X"}], groupBy: ["brand"]}""")
    band = computed(page, ".dg-body .dg-row.dg-group", ["background-color", "font-weight"])
    assert alpha(band["background-color"]) > 0 and int(band["font-weight"]) >= 600, band
    assert computed(page, ".dg-group-cell", ["display"])["display"] == "flex"
    closed = computed(page, ".dg-group-toggle", ["transform"], "::before")["transform"]
    page.locator(".dg-body .dg-row.dg-group").click()
    page.wait_for_timeout(250)
    assert computed(page, ".dg-group-toggle", ["transform"], "::before")["transform"] != closed


def test_a_tree_leaf_is_indented_past_its_parents_toggle(page):
    build(page, """{columns: [{title: "Name", field: "name"}],
                    data: [{name: "a", kids: [{name: "b"}]}, {name: "c"}],
                    dataTree: true, dataTreeChildField: "kids"}""")
    page.click(".dg-tree-toggle")
    spacer = computed(page, ".dg-tree-spacer", ["display", "width"])
    assert spacer["display"] == "inline-block" and float(spacer["width"].rstrip("px")) > 0, spacer


def test_the_header_button_the_toggle_and_a_menu_item_ring_when_reached_by_keyboard(page):
    build(page, """{columns: [{title: "Name", field: "name", headerMenu: () => [{label: "One", action() {}}]}],
                    data: [{name: "a", kids: [{name: "b"}]}], dataTree: true, dataTreeChildField: "kids"}""")
    ring = ["outline-style", "outline-width"]
    for selector in (".dg-header .dg-header-button", ".dg-tree-toggle"):
        page.focus(selector)
        page.evaluate("(sel) => document.querySelector(sel).focus({focusVisible: true})", selector)
        style = page.evaluate("""(sel) => { const el = document.querySelector(sel);
          return [el.matches(':focus-visible'), getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]; }""", selector)
        assert style[0] and style[1] == "solid" and float(style[2].rstrip("px")) >= 1, (selector, style)
    page.evaluate("document.querySelector('.dg-header .dg-header-button').focus()")
    page.keyboard.press("Enter")
    page.wait_for_selector(".dg-menu .dg-menu-item")
    page.keyboard.press("ArrowDown")
    item = page.evaluate("""() => { const el = document.activeElement; const s = getComputedStyle(el);
      return [el.classList.contains('dg-menu-item'), el.matches(':focus-visible'), s.outlineStyle, s.backgroundColor]; }""")
    assert item[0] and item[1] and item[2] == "solid" and alpha(item[3]) > 0, item


def test_a_menu_floats_over_the_page_on_its_own_surface(page):
    build(page, """{columns: [{title: "Name", field: "name", headerMenu: () => [{label: "One", action() {}}]}],
                    data: [{name: "a"}]}""")
    page.click(".dg-header .dg-header-button")
    menu = computed(page, ".dg-menu", ["position", "z-index", "background-color", "border-top-style"])
    assert menu["position"] == "fixed" and int(menu["z-index"]) >= 1000, menu
    assert alpha(menu["background-color"]) == 1.0 and menu["border-top-style"] != "none", menu
    page.hover(".dg-menu .dg-menu-item")
    page.wait_for_timeout(400)
    assert alpha(computed(page, ".dg-menu .dg-menu-item", ["background-color"])["background-color"]) > 0


def test_the_totals_row_is_a_band_of_its_own(page):
    build(page, PINNED)
    calcs = computed(page, ".dg-header .dg-calcs", ["background-color"])
    assert alpha(calcs["background-color"]) > 0, calcs
