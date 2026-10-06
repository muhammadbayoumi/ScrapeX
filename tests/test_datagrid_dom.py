"""datagrid.js, the grid's renderer, driven in a real browser on its own.

grid.js decides what a cell MEANS; datagrid.js draws it, on TanStack Table and
TanStack Virtual (#1342). These tests hold the renderer to its own contract —
the options and the handles its docstring names — without grid.js in front of
it, so a defect here is the renderer's and not a meaning one layer up.

The page is the shipped extension's copy of the renderer and its vendored
modules, served over loopback because a browser refuses module imports from
file://. Its stylesheet is the few structural rules the renderer depends on
(a scrolling frame, absolutely placed rows, cells that do not flex), not the
project's theme: what is under test is what the renderer does, not how it looks.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright

import tabpage_harness  # noqa: E402

# It reads the extension's copy of the renderer: a change there must run it.
pytestmark = pytest.mark.extension

EXT = ROOT / "extension"

STRUCTURE = """
html, body { margin: 0; font: 14px/1.4 sans-serif; }
#mount { width: 600px; height: 300px; }
.dg { display: flex; flex-direction: column; }
.dg-scroller { position: relative; flex: 1 1 auto; min-height: 0; overflow: auto;
  scrollbar-gutter: stable; }
.dg-header { position: sticky; top: 0; z-index: 2; background: #fff; }
.dg-row { display: flex; box-sizing: border-box; }
.dg-body { position: relative; }
.dg-body > .dg-row { position: absolute; top: 0; inset-inline-start: 0; }
.dg-col, .dg-cell { position: relative; flex: none; box-sizing: border-box;
  overflow: hidden; white-space: nowrap; padding: 4px 8px; }
.dg-body .dg-row { min-height: 30px; }
.dg-pinned { position: sticky; z-index: 1; background: #fff; }
.dg-placeholder[hidden] { display: none; }
.dg.wrap .dg-cell { white-space: normal; overflow-wrap: anywhere; }
"""

PAGE = (
    "<!doctype html><meta charset='utf-8'><title>datagrid</title>"
    f"<style>{STRUCTURE}</style>"
    "<div id='mount'></div>"
    # A dynamic import, so a renderer that does not load SAYS so: a static one
    # that fails leaves nothing to wait for but a timeout.
    "<script type='module'>"
    "import('./datagrid.js').then("
    "(module) => { window.DataGrid = module.DataGrid; window.__ready = true; },"
    "(error) => { window.__ready = 'the renderer did not load: ' + error; });"
    "</script>"
)

MARKUP = "<img src=x onerror=window.__pwned=1>"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("datagrid")
    shutil.copyfile(EXT / "datagrid.js", tmp / "datagrid.js")
    shutil.copytree(EXT / "vendor" / "tanstack", tmp / "vendor" / "tanstack")
    (tmp / "index.html").write_text(PAGE, encoding="utf-8")
    with tabpage_harness.serve(tmp) as url:
        yield url


@pytest.fixture
def page(browser, base):
    context = browser.new_context(viewport={"width": 1000, "height": 800})
    tab = context.new_page()
    tab.errors = []
    failed = []
    tab.on("pageerror", lambda error: tab.errors.append(str(error)))
    tab.on("requestfailed", lambda request: failed.append(f"{request.url}: {request.failure}"))
    tab.goto(f"{base}/index.html")
    tab.wait_for_function("window.__ready !== undefined")
    ready = tab.evaluate("window.__ready")
    assert ready is True, f"{ready}; requests that failed: {failed}"
    yield tab
    context.close()


def build(page, options: str) -> None:
    """Construct `window.grid` in #mount from `options`, a JavaScript object literal.

    Source rather than JSON, because formatters and sorters are functions.
    """
    page.evaluate(
        """(source) => {
          const options = new Function("return (" + source + ")")();
          if (window.grid) window.grid.destroy();
          window.grid = new DataGrid(document.getElementById("mount"), options);
        }""",
        options,
    )


def column_texts(page, field: str) -> list[str]:
    """The text of `field`'s cells in the rows on screen, top to bottom."""
    return page.evaluate(
        """(field) => Array.from(document.querySelectorAll(".dg-body .dg-row"))
            .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
            .map((row) => row.querySelector(`[data-field="${field}"]`).textContent)""",
        field,
    )


def header(page, field: str) -> str:
    return f'.dg-header .dg-col[data-field="{field}"]'


NAMES = """{
  columns: [{title: "Name", field: "name"}, {title: "Size", field: "size"}],
  data: [{name: "beta", size: 2}, {name: "gamma", size: 3}, {name: "alpha", size: 1}],
}"""


# ---- drawing ------------------------------------------------------------------

def test_it_draws_a_header_cell_per_column_and_a_row_per_record(page):
    build(page, NAMES)
    assert page.locator(".dg-header .dg-col").count() == 2
    assert page.locator(header(page, "name")).inner_text() == "Name"
    assert page.locator(".dg-body .dg-row").count() == 3
    assert column_texts(page, "name") == ["beta", "gamma", "alpha"]
    assert column_texts(page, "size") == ["2", "3", "1"]
    assert page.errors == []


def test_only_the_rows_near_the_screen_exist_and_the_last_is_reachable(page):
    """Virtualized: 10,000 records, a few dozen rows in the page. Scrolling to the
    end draws the last record, numbered for a screen reader as the last row."""
    build(page, """{
      columns: [{title: "Name", field: "name"}],
      data: Array.from({length: 10000}, (_, i) => ({name: "row " + i})),
    }""")
    drawn = page.locator(".dg-body .dg-row").count()
    assert 0 < drawn < 60, drawn
    assert page.get_attribute("#mount", "aria-rowcount") == "10001"
    page.evaluate("""() => {
      const scroller = document.querySelector(".dg-scroller");
      scroller.scrollTop = scroller.scrollHeight;
    }""")
    page.wait_for_function("""() => Array.from(document.querySelectorAll(".dg-body .dg-cell"))
      .some((cell) => cell.textContent === "row 9999")""")
    last = page.locator(".dg-body .dg-row", has_text="row 9999")
    assert last.get_attribute("aria-rowindex") == "10001"
    assert page.locator(".dg-body .dg-row").count() < 60


def test_the_placeholder_shows_only_when_no_row_does(page):
    build(page, """{columns: [{title: "Name", field: "name"}], data: [], placeholder: "Nothing here."}""")
    assert page.locator(".dg-placeholder").is_visible()
    assert page.locator(".dg-placeholder").inner_text() == "Nothing here."
    build(page, NAMES)
    assert not page.locator(".dg-placeholder").is_visible()
    page.evaluate("() => grid.setFilter([{field: 'name', test: () => false}])")
    assert page.locator(".dg-placeholder").is_visible()
    assert page.locator(".dg-body .dg-row").count() == 0


def test_a_string_a_formatter_returns_is_text_and_never_markup(page):
    """Scraped values reach these cells. A string — from the payload or from a
    formatter — is text; only a Node the host built is a node."""
    build(page, f"""{{
      columns: [
        {{title: "Raw", field: "name"}},
        {{title: "Formatted", field: "copy", formatter: (cell) => cell.getRow().getData().name}},
        {{title: "Node", field: "node", formatter: () => {{
          const b = document.createElement("b"); b.textContent = "bold"; return b; }}}},
      ],
      data: [{{name: {MARKUP!r}}}],
    }}""")
    page.wait_for_timeout(100)
    assert page.locator("#mount img").count() == 0
    assert page.evaluate("window.__pwned") is None
    assert column_texts(page, "name") == [MARKUP]
    assert column_texts(page, "copy") == [MARKUP]
    assert page.locator('.dg-cell[data-field="node"] b').inner_text() == "bold"


def test_a_header_icon_is_a_copied_node_a_made_one_or_nothing(page):
    """Icons arrive as nodes, never as markup: a node is copied into every header,
    a function is called for each, and a string is dropped rather than parsed."""
    build(page, """{
      columns: [{title: "A", field: "a"}, {title: "B", field: "b"}],
      data: [{a: 1, b: 2}],
      headerSortElement: Object.assign(document.createElement("span"), {className: "given"}),
    }""")
    assert page.locator(".dg-header .dg-sort .given").count() == 2
    assert page.evaluate("grid.options.headerSortElement.isConnected") is False
    build(page, """{
      columns: [{title: "A", field: "a"}, {title: "B", field: "b"}],
      data: [{a: 1, b: 2}],
      headerSortElement: () => Object.assign(document.createElement("span"), {className: "made"}),
    }""")
    assert page.locator(".dg-header .dg-sort .made").count() == 2
    build(page, """{
      columns: [{title: "A", field: "a"}], data: [{a: 1}], headerSortElement: "<b>x</b>",
    }""")
    assert page.locator(".dg-header b").count() == 0
    assert page.locator(".dg-header .dg-sort").inner_text() == ""


def test_a_row_number_counts_the_rows_in_the_order_shown(page):
    build(page, """{
      columns: [{formatter: "rownum", headerSort: false}, {title: "Name", field: "name"}],
      data: [{name: "b"}, {name: "c"}, {name: "a"}],
    }""")
    page.evaluate("() => grid.setSort('name', 'desc')")
    assert column_texts(page, "name") == ["c", "b", "a"]
    assert column_texts(page, "__rownum") == ["1", "2", "3"]


def test_wrapped_rows_are_placed_by_their_own_height_and_others_by_one(page):
    """One row is measured and the rest placed by it, unless long text wraps: a
    wrapped row is as tall as its text, so each is measured and none overlaps."""
    long = "word " * 60
    data = f'[{{t: "short"}}, {{t: "{long}"}}, {{t: "short"}}, {{t: "{long}{long}"}}]'

    def placements():
        return page.evaluate("""() => Array.from(document.querySelectorAll(".dg-body .dg-row"))
          .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
          .map((row) => ({top: new DOMMatrix(getComputedStyle(row).transform).m42,
                          height: row.getBoundingClientRect().height}))""")

    page.evaluate("document.getElementById('mount').classList.add('wrap')")
    build(page, f'{{columns: [{{title: "Text", field: "t"}}], data: {data}}}')
    page.wait_for_timeout(100)
    rows = placements()
    assert rows[1]["height"] > rows[0]["height"] * 2, rows
    for above, below in zip(rows, rows[1:]):
        assert below["top"] == pytest.approx(above["top"] + above["height"], abs=1), rows

    page.evaluate("grid.destroy(); document.getElementById('mount').classList.remove('wrap')")
    build(page, f'{{columns: [{{title: "Text", field: "t"}}], data: {data}}}')
    rows = placements()
    assert len({round(row["height"]) for row in rows}) == 1, rows
    assert [round(row["top"]) for row in rows] == [round(i * rows[0]["height"]) for i in range(4)]


# ---- sorting ------------------------------------------------------------------

def test_a_header_click_sorts_ascending_then_descending_then_back_to_the_payload(page):
    build(page, NAMES)
    name = page.locator(header(page, "name"))
    assert name.get_attribute("aria-sort") == "none"
    name.click()
    assert column_texts(page, "name") == ["alpha", "beta", "gamma"]
    assert name.get_attribute("aria-sort") == "ascending"
    name.click()
    assert column_texts(page, "name") == ["gamma", "beta", "alpha"]
    assert name.get_attribute("aria-sort") == "descending"
    name.click()
    assert column_texts(page, "name") == ["beta", "gamma", "alpha"]
    assert name.get_attribute("aria-sort") == "none"
    assert page.evaluate("grid.getSorters()") == []


def test_empty_sorts_last_in_both_directions(page):
    build(page, """{
      columns: [{title: "N", field: "n"}],
      data: [{n: 3}, {n: ""}, {n: 1}, {n: null}, {}],
    }""")
    page.evaluate("() => grid.setSort('n', 'asc')")
    assert column_texts(page, "n")[:2] == ["1", "3"]
    assert column_texts(page, "n")[2:] == ["", "", ""]
    page.evaluate("() => grid.setSort('n', 'desc')")
    assert column_texts(page, "n")[:2] == ["3", "1"]
    assert column_texts(page, "n")[2:] == ["", "", ""]


def test_a_sorter_orders_by_its_own_value_and_comparison(page):
    build(page, """{
      columns: [{title: "Word", field: "w",
                 sorter: {value: (row) => row.w.length, compare: (a, b) => a - b}}],
      data: [{w: "ccc"}, {w: "a"}, {w: "bb"}],
    }""")
    page.evaluate("() => grid.setSort('w', 'asc')")
    assert column_texts(page, "w") == ["a", "bb", "ccc"]


def test_a_column_that_does_not_sort_ignores_clicks_and_asks(page):
    build(page, """{
      columns: [{title: "Name", field: "name", headerSort: false}],
      data: [{name: "b"}, {name: "a"}],
      initialSort: [{column: "name", dir: "asc"}],
    }""")
    assert column_texts(page, "name") == ["b", "a"], "an initial sort on it is ignored"
    page.locator(header(page, "name")).click()
    page.evaluate("() => grid.setSort('name', 'asc')")
    assert column_texts(page, "name") == ["b", "a"]
    assert page.locator(header(page, "name")).get_attribute("aria-sort") == "none"
    assert page.locator(".dg-header .dg-sort").count() == 0


def test_the_initial_sort_and_the_sort_api_agree(page):
    build(page, NAMES.replace("data:", 'initialSort: [{column: "name", dir: "desc"}], data:'))
    assert column_texts(page, "name") == ["gamma", "beta", "alpha"]
    assert page.evaluate("grid.getSorters()") == [{"field": "name", "dir": "desc"}]
    assert page.evaluate("grid.getData().map((d) => d.name)") == ["beta", "gamma", "alpha"]
    assert page.evaluate("grid.getData('active').map((d) => d.name)") == ["gamma", "beta", "alpha"]
    page.evaluate("() => grid.setSort('nobody', 'asc')")
    assert page.evaluate("grid.getSorters()") == [], "an unknown column clears the sort"


# ---- filtering ----------------------------------------------------------------

def test_a_filter_narrows_the_rows_and_says_so_once_per_change(page):
    build(page, NAMES)
    page.evaluate("""() => {
      window.__filtered = 0;
      grid.on("dataFiltered", () => { window.__filtered += 1; });
    }""")
    page.evaluate("() => grid.setFilter([{field: 'name', test: (row) => row.name.startsWith('a')}])")
    page.wait_for_timeout(50)
    assert column_texts(page, "name") == ["alpha"]
    assert page.evaluate("grid.getDataCount('active')") == 1
    assert page.evaluate("grid.getDataCount()") == 3
    assert page.evaluate("window.__filtered") == 1
    page.evaluate("() => grid.setFilter([{field: 'name', type: 'like', value: 'MM'}])")
    page.wait_for_timeout(50)
    assert column_texts(page, "name") == ["gamma"], "like is a case-blind substring"
    assert page.evaluate("window.__filtered") == 2
    page.evaluate("() => grid.setSort('name', 'asc')")
    page.wait_for_timeout(50)
    assert page.evaluate("window.__filtered") == 2, "a sort is not a filter"
    page.evaluate("() => grid.setFilter([])")
    page.wait_for_timeout(50)
    assert column_texts(page, "name") == ["alpha", "beta", "gamma"]
    assert page.evaluate("window.__filtered") == 3


def test_a_filter_on_a_column_the_grid_does_not_have_is_dropped(page):
    build(page, NAMES)
    page.evaluate("() => grid.setFilter([{field: 'nobody', test: () => false}, null])")
    assert page.evaluate("grid.getDataCount('active')") == 3


# ---- columns ------------------------------------------------------------------

def test_a_hidden_column_is_not_drawn_and_comes_back_when_shown(page):
    build(page, """{
      columns: [{title: "Name", field: "name"}, {title: "Secret", field: "secret", visible: false}],
      data: [{name: "a", secret: "s"}],
    }""")
    assert page.locator('[data-field="secret"]').count() == 0
    assert page.get_attribute("#mount", "aria-colcount") == "1"
    assert page.evaluate("grid.getColumn('secret').isVisible()") is False
    page.evaluate("() => grid.getColumn('secret').show()")
    assert column_texts(page, "secret") == ["s"]
    assert page.get_attribute("#mount", "aria-colcount") == "2"
    page.evaluate("() => grid.getColumn('name').hide()")
    assert page.locator('[data-field="name"]').count() == 0
    assert [c for c in page.evaluate("grid.getColumns().map((c) => c.getField())")] == ["name", "secret"]
    assert page.evaluate("grid.getColumn('nobody')") is None


def test_columns_share_the_width_by_their_grow_and_a_fixed_one_keeps_its_own(page):
    build(page, """{
      columns: [{title: "A", field: "a"}, {title: "B", field: "b", widthGrow: 2},
                {title: "C", field: "c", width: 100}],
      data: [{a: 1, b: 2, c: 3}],
    }""")
    widths = page.evaluate("""() => Object.fromEntries(
      Array.from(document.querySelectorAll(".dg-header .dg-col"))
        .map((col) => [col.dataset.field, col.getBoundingClientRect().width]))""")
    frame = page.evaluate("document.querySelector('.dg-scroller').clientWidth")
    assert widths["c"] == 100
    assert sum(widths.values()) == pytest.approx(frame, abs=1)
    assert widths["b"] == pytest.approx(2 * widths["a"], abs=2)


def test_no_column_goes_below_its_minimum_and_the_table_scrolls_instead(page):
    build(page, """{
      columns: ["a", "b", "c", "d", "e"].map((f) => ({title: f, field: f, minWidth: 150})),
      data: [{a: 1}],
    }""")
    widths = page.evaluate("""() => Array.from(document.querySelectorAll(".dg-header .dg-col"))
      .map((col) => col.getBoundingClientRect().width)""")
    assert widths == [150] * 5
    assert page.evaluate("""() => {
      const s = document.querySelector(".dg-scroller"); return s.scrollWidth > s.clientWidth; }""")


def test_set_width_fixes_a_column_but_never_below_its_minimum(page):
    build(page, """{
      columns: [{title: "A", field: "a", minWidth: 60}, {title: "B", field: "b"}],
      data: [{a: 1, b: 2}],
    }""")
    page.evaluate("() => grid.getColumn('a').setWidth(10)")
    assert page.evaluate("grid.getColumn('a').getWidth()") == 60
    page.evaluate("() => grid.getColumn('a').setWidth(250)")
    assert page.locator(header(page, "a")).bounding_box()["width"] == 250
    assert page.locator('.dg-body .dg-cell[data-field="a"]').bounding_box()["width"] == 250


def test_a_frame_that_changes_width_refits_the_columns(page):
    build(page, NAMES)
    page.evaluate("document.getElementById('mount').style.width = '400px'")
    page.wait_for_function("""() => {
      const frame = document.querySelector(".dg-scroller").clientWidth;
      const used = Array.from(document.querySelectorAll(".dg-header .dg-col"))
        .reduce((sum, col) => sum + col.getBoundingClientRect().width, 0);
      return frame < 400 && Math.abs(used - frame) <= 1;
    }""")


def test_pinned_columns_stick_at_their_own_edge_after_those_before_them(page):
    build(page, """{
      columns: [{title: "A", field: "a", width: 100, frozen: "left"},
                {title: "B", field: "b", width: 80, frozen: "left"},
                {title: "C", field: "c", width: 400},
                {title: "D", field: "d", width: 90, frozen: "right"}],
      data: [{a: 1, b: 2, c: 3, d: 4}],
    }""")
    for scope in (".dg-header .dg-col", ".dg-body .dg-cell"):
        place = page.evaluate("""(scope) => Object.fromEntries(
          Array.from(document.querySelectorAll(scope)).map((cell) => [cell.dataset.field, {
            classes: cell.className, start: cell.style.insetInlineStart, end: cell.style.insetInlineEnd}]))""",
                              scope)
        assert "dg-pinned-start" in place["a"]["classes"] and place["a"]["start"] == "0px"
        assert "dg-pinned-start" in place["b"]["classes"] and place["b"]["start"] == "100px"
        assert "dg-pinned" not in place["c"]["classes"]
        assert "dg-pinned-end" in place["d"]["classes"] and place["d"]["end"] == "0px"
    assert page.evaluate("grid.getColumns().map((c) => c.getField())") == ["a", "b", "c", "d"]


# ---- selection ----------------------------------------------------------------

def test_a_row_click_selects_and_a_control_inside_the_row_does_not(page):
    build(page, """{
      columns: [{title: "Name", field: "name"},
                {title: "Link", field: "link", formatter: () => {
                  const a = document.createElement("a"); a.href = "#here"; a.textContent = "open";
                  return a; }}],
      data: [{name: "a"}, {name: "b"}],
      selectableRows: true,
    }""")
    page.evaluate("""() => {
      window.__selected = [];
      grid.on("rowSelectionChanged", (data) => window.__selected.push(data.map((d) => d.name)));
    }""")
    first = page.locator('.dg-body .dg-row[data-index="0"]')
    first.locator('[data-field="name"]').click()
    assert "dg-selected" in first.get_attribute("class")
    assert first.get_attribute("aria-selected") == "true"
    assert page.evaluate("window.__selected") == [["a"]]
    page.locator('.dg-body .dg-row[data-index="1"] a').click()
    assert page.evaluate("grid.getSelectedRows().map((r) => r.getData().name)") == ["a"]
    assert page.evaluate("window.__selected") == [["a"]]
    first = page.locator('.dg-body .dg-row[data-index="0"]')
    first.locator('[data-field="name"]').click()
    assert page.evaluate("grid.getSelectedRows().length") == 0
    assert page.evaluate("window.__selected") == [["a"], []]


def test_rows_do_not_select_unless_the_grid_is_selectable(page):
    build(page, NAMES)
    page.locator('.dg-body .dg-row[data-index="0"] [data-field="name"]').click()
    assert page.evaluate("grid.getSelectedRows().length") == 0
    assert page.get_attribute("#mount", "aria-multiselectable") is None
    assert page.locator(".dg-body .dg-row").first.get_attribute("aria-selected") is None


def test_the_select_all_box_selects_every_row_and_shows_a_partial_choice(page):
    build(page, """{
      columns: [{formatter: "rowSelection", titleFormatter: "rowSelection", headerSort: false},
                {title: "Name", field: "name"}],
      data: [{name: "a"}, {name: "b"}, {name: "c"}],
      selectableRows: true,
    }""")
    page.locator(".dg-header .dg-select").check()
    assert page.evaluate("grid.getSelectedRows().length") == 3
    assert page.locator(".dg-body .dg-select:checked").count() == 3
    page.locator('.dg-body .dg-row[data-index="1"] .dg-select').uncheck()
    assert page.evaluate("grid.getSelectedRows().map((r) => r.getData().name)") == ["a", "c"]
    box = page.locator(".dg-header .dg-select")
    assert box.evaluate("(b) => [b.checked, b.indeterminate]") == [False, True]


# ---- events, lifetime, accessibility ------------------------------------------

def test_table_built_is_heard_after_construction_even_by_a_grid_destroyed_at_once(page):
    page.evaluate("""() => {
      window.__built = 0;
      const g = new DataGrid(document.getElementById("mount"),
                             {columns: [{title: "A", field: "a"}], data: []});
      g.on("tableBuilt", () => { window.__built += 1; });
      g.destroy();
    }""")
    page.wait_for_function("window.__built === 1")


def test_one_listener_failing_neither_silences_the_others_nor_vanishes(page):
    build(page, NAMES)
    page.evaluate("""() => {
      window.__heard = 0;
      grid.on("dataFiltered", () => { throw new Error("listener broke"); });
      grid.on("dataFiltered", () => { window.__heard += 1; });
      grid.setFilter([{field: "name", test: () => true}]);
    }""")
    page.wait_for_function("window.__heard === 1")
    page.wait_for_timeout(50)
    assert any("listener broke" in error for error in page.errors), page.errors


def test_destroy_leaves_the_mount_as_it_found_it_and_find_forgets_it(page):
    build(page, NAMES.replace("data:", "selectableRows: true, data:"))
    assert page.evaluate("DataGrid.find('#mount') === grid")
    assert page.evaluate("DataGrid.find(document.getElementById('mount')) === grid")
    page.evaluate("() => grid.destroy()")
    state = page.evaluate("""() => {
      const m = document.getElementById("mount");
      return {children: m.children.length, classes: m.className,
              attrs: ["role", "aria-rowcount", "aria-colcount", "aria-multiselectable"]
                .filter((a) => m.hasAttribute(a))};
    }""")
    assert state == {"children": 0, "classes": "", "attrs": []}
    assert page.evaluate("DataGrid.find('#mount') === undefined")
    page.evaluate("() => grid.destroy()")  # a second destroy is harmless
    assert page.errors == []


def test_the_grid_names_its_rows_and_columns_for_a_screen_reader(page):
    build(page, NAMES.replace("data:", "selectableRows: true, data:"))
    mount = page.locator("#mount")
    assert mount.get_attribute("role") == "grid"
    assert mount.get_attribute("aria-colcount") == "2"
    assert mount.get_attribute("aria-rowcount") == "4"
    assert mount.get_attribute("aria-multiselectable") == "true"
    assert page.locator(".dg-header .dg-header-row").get_attribute("aria-rowindex") == "1"
    assert page.locator(".dg-header .dg-col").first.get_attribute("role") == "columnheader"
    assert page.locator('.dg-body .dg-row[data-index="0"]').get_attribute("aria-rowindex") == "2"
    assert page.locator(".dg-body .dg-cell").first.get_attribute("role") == "gridcell"


def test_a_grid_with_nowhere_to_draw_says_so(page):
    message = page.evaluate("""() => {
      try { new DataGrid(null, {columns: [], data: []}); return "constructed"; }
      catch (error) { return error.message; }
    }""")
    assert message == "DataGrid needs an element to draw into"
