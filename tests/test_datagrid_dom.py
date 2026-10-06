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

import json
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
.dg-header { position: sticky; top: 0; z-index: 2; background: #fff; user-select: none; }
.dg-row { display: flex; box-sizing: border-box; }
.dg-body { position: relative; }
.dg-body > .dg-row { position: absolute; top: 0; inset-inline-start: 0; }
.dg-col, .dg-cell { position: relative; flex: none; box-sizing: border-box;
  overflow: hidden; white-space: nowrap; padding: 4px 8px; }
.dg-body .dg-row { min-height: 30px; }
.dg-pinned { position: sticky; z-index: 1; background: #fff; }
.dg-placeholder[hidden] { display: none; }
.dg.wrap .dg-cell { white-space: normal; overflow-wrap: anywhere; }
.dg-col-content { display: flex; align-items: center; gap: 4px; }
.dg-resize-handle { position: absolute; top: 0; bottom: 0; inset-inline-end: 0; width: 8px; }
.dg-header-button { width: 20px; height: 20px; padding: 0; }
.dg-header-input { display: block; width: 90%; }
.dg-menu, .dg-popup { position: fixed; z-index: 10; background: #fff; border: 1px solid #888; }
.dg-menu-item { display: block; width: 100%; text-align: start; }
.dg-group-cell { display: flex; align-items: center; gap: 4px; padding: 4px 8px; }
.dg-group-toggle, .dg-tree-toggle { width: 16px; height: 16px; padding: 0; }
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
# Inert markup: parsed, it would make one `.probe` element, so a count of them
# says whether a string was parsed anywhere it lands.
PROBE = '<b class="probe">x</b>'


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


def test_a_title_a_title_formatter_and_the_placeholder_are_text_and_never_markup(page):
    """Scraped text reaches the header too: the Datasets page titles its records
    grid with each field's label, which a site's own name can fill. A title, a
    string a titleFormatter returns, and the placeholder are text."""
    build(page, f"""{{
      columns: [{{title: {PROBE!r}, field: "a"}},
                {{title: "B", field: "b", titleFormatter: () => {PROBE!r}}}],
      data: [],
      placeholder: {PROBE!r},
    }}""")
    assert page.locator("#mount .probe").count() == 0
    assert page.locator(header(page, "a")).inner_text() == PROBE
    assert page.locator(header(page, "b")).inner_text() == PROBE
    assert page.locator(".dg-placeholder").inner_text() == PROBE


def test_a_column_is_found_by_a_field_name_that_carries_selector_characters(page):
    """A field name is a catalog key or a source's own column, never a selector:
    a quote, a bracket or a backslash in it must not break the lookup."""
    field = 'a"] b\\c'
    build(page, f"""{{columns: [{{title: "Odd", field: {json.dumps(field)}}}], data: [{{}}]}}""")
    assert page.evaluate(
        "(f) => grid.getColumn(f).getElement() === document.querySelector('.dg-header .dg-col')",
        field,
    )
    assert page.errors == []


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


def test_the_options_and_handles_grid_js_relies_on_are_each_honoured(page):
    """grid.js builds its grid with columnDefaults (a minimum width and a title
    formatter), hozAlign, cssClass, a height and its own footer, reads every cell
    through its handle, and opens the offer panel from rowSelectionChanged's
    rows. Each is part of the renderer's contract, so each is asserted."""
    page.evaluate("""() => {
      window.__cells = [];
      window.__chosen = [];
      window.__footer = Object.assign(document.createElement("div"),
                                      {className: "host-footer", textContent: "footer"});
    }""")
    build(page, """{
      columnDefaults: {minWidth: 70, titleFormatter: (cell) => Object.assign(
        document.createElement("span"), {className: "made-title", textContent: cell.getValue() + "!"})},
      columns: [
        {title: "Name", field: "name", cssClass: "host-class", formatter: (cell) => {
          const element = cell.getElement();
          window.__cells.push([cell.getValue(), cell.getField(),
                               element instanceof HTMLElement && element.classList.contains("dg-cell")]);
          return cell.getValue();
        }},
        {title: "Size", field: "size", hozAlign: "right", width: 50},
      ],
      data: [{name: "a", size: 1}, {name: "b", size: 2}],
      height: "200px",
      footerElement: window.__footer,
      selectableRows: true,
    }""")
    page.evaluate("""() => grid.on("rowSelectionChanged", (data, rows) => window.__chosen.push(
      [data.map((d) => d.name), rows.map((row) => [row.getData().name, row.isSelected()])]))""")

    assert page.locator(".dg-header .made-title").all_inner_texts() == ["Name!", "Size!"]
    assert page.evaluate("grid.getColumn('size').getWidth()") == 70, "the default minimum holds"
    assert "host-class" in page.locator(header(page, "name")).get_attribute("class")
    assert page.locator('.dg-body .dg-cell[data-field="name"].host-class').count() == 2
    assert page.locator('.dg-body .dg-cell[data-field="size"].dg-align-right').count() == 2
    assert page.evaluate("document.getElementById('mount').style.height") == "200px"
    assert page.evaluate("""() => {
      const mount = document.getElementById("mount");
      return mount.lastElementChild === window.__footer && window.__footer.classList.contains("dg-footer");
    }""")
    assert page.evaluate("window.__cells") == [["a", "name", True], ["b", "name", True]]
    page.locator('.dg-body .dg-row[data-index="1"] [data-field="name"]').click()
    assert page.evaluate("window.__chosen") == [[["b"], [["b", True]]]]


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


def test_many_wrapped_rows_leave_no_gap_and_no_overlap_between_any_two(page):
    """Measuring a wrapped row tells the virtualizer a size changed while the body
    is still being painted. The paint must run again for that, or the rows that
    come into reach once the first ones measure shorter than their estimate keep
    the places the estimate gave them. Four rows all fit the first paint; two
    hundred short ones, each under the estimate, do not."""
    # Read in the same task as the construction, before any frame can repaint
    # what the construction left, and again once the page has settled. The
    # paint is counted too: one that starts inside another is the recursion
    # the "finish, then run once more" loop exists to prevent.
    moments = page.evaluate("""async () => {
      const proto = DataGrid.prototype;
      const paint = proto._paintBody;
      let depth = 0, deepest = 0;
      proto._paintBody = function () {
        depth += 1; deepest = Math.max(deepest, depth);
        try { return paint.call(this); } finally { depth -= 1; }
      };
      try {
        const mount = document.getElementById("mount");
        mount.classList.add("wrap");
        if (window.grid) window.grid.destroy();
        window.grid = new DataGrid(mount, {
          columns: [{title: "Text", field: "t"}],
          data: Array.from({length: 200}, (_, i) => ({t: "row " + i})),
        });
        const placements = () => Array.from(document.querySelectorAll(".dg-body .dg-row"))
          .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
          .map((row) => ({index: Number(row.dataset.index),
                          top: new DOMMatrix(getComputedStyle(row).transform).m42,
                          height: row.getBoundingClientRect().height}));
        const atOnce = placements();
        await new Promise((resolve) => setTimeout(resolve, 300));
        return {"at once": atOnce, "settled": placements(), deepest};
      } finally {
        proto._paintBody = paint;
      }
    }""")
    assert moments.pop("deepest") == 1, "a paint started inside another"
    for moment, rows in moments.items():
        assert len(rows) > 12, (moment, rows)
        assert [row["index"] for row in rows] == list(range(rows[0]["index"], rows[0]["index"] + len(rows)))
        for above, below in zip(rows, rows[1:]):
            assert below["top"] == pytest.approx(above["top"] + above["height"], abs=1), (moment, above, below)


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


def test_like_is_case_blind_on_the_value_side_too(page):
    """The header search reaches scraped names, and those carry capitals."""
    build(page, """{columns: [{title: "Name", field: "name"}],
                    data: [{name: "GAMMA"}, {name: "Beta"}, {name: "alpha"}]}""")
    page.evaluate("() => grid.setFilter([{field: 'name', type: 'like', value: 'mm'}])")
    assert column_texts(page, "name") == ["GAMMA"]
    page.evaluate("() => grid.setFilter([{field: 'name', type: 'like', value: 'ETA'}])")
    assert column_texts(page, "name") == ["Beta"]


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
                {title: "D", field: "d", width: 90, frozen: "right"},
                {title: "E", field: "e", width: 70, frozen: "right"}],
      data: [{a: 1, b: 2, c: 3, d: 4, e: 5}],
    }""")
    for scope in (".dg-header .dg-col", ".dg-body .dg-cell"):
        place = page.evaluate("""(scope) => Object.fromEntries(
          Array.from(document.querySelectorAll(scope)).map((cell) => [cell.dataset.field, {
            classes: cell.className, start: cell.style.insetInlineStart, end: cell.style.insetInlineEnd}]))""",
                              scope)
        assert "dg-pinned-start" in place["a"]["classes"] and place["a"]["start"] == "0px"
        assert "dg-pinned-start" in place["b"]["classes"] and place["b"]["start"] == "100px"
        assert "dg-pinned" not in place["c"]["classes"]
        # Measured from the end edge: the last column sits on it, the one before after it.
        assert "dg-pinned-end" in place["e"]["classes"] and place["e"]["end"] == "0px"
        assert "dg-pinned-end" in place["d"]["classes"] and place["d"]["end"] == "70px"
    assert page.evaluate("grid.getColumns().map((c) => c.getField())") == ["a", "b", "c", "d", "e"]


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


def test_a_row_is_found_by_where_it_sits_not_by_a_class_a_cell_carries(page):
    """A formatter's node may carry any class, `dg-row` included. The row a click
    lands in is the body's own child that holds it."""
    build(page, """{
      columns: [{title: "Name", field: "name", formatter: (cell) => {
        const span = document.createElement("span");
        span.className = "dg-row";
        span.textContent = cell.getValue();
        return span; }}],
      data: [{name: "a"}, {name: "b"}],
      selectableRows: true,
    }""")
    page.locator('.dg-body .dg-row[data-index="1"] span.dg-row').click()
    assert page.evaluate("grid.getSelectedRows().map((r) => r.getData().name)") == ["b"]
    assert page.errors == []


def test_a_row_the_table_cannot_find_is_an_error_that_shows(page):
    """No silent failures: a drawn row whose id TanStack does not know is a
    defect, and the click says so instead of doing nothing."""
    build(page, NAMES.replace("data:", "selectableRows: true, data:"))
    page.evaluate("""() => {
      document.querySelector('.dg-body .dg-row[data-index="0"]').dataset.rowId = "nobody";
    }""")
    page.locator('.dg-body .dg-row[data-index="0"] [data-field="name"]').click()
    page.wait_for_timeout(50)
    assert len(page.errors) == 1, page.errors
    assert page.evaluate("grid.getSelectedRows().length") == 0


def test_a_change_is_drawn_once_so_the_rows_it_drew_stay(page):
    """A sort, a filter or a click is drawn at once, and the store's word that
    follows is about the same state. Drawing it again threw away every row and
    the header just drawn, and measured every row once more."""
    build(page, NAMES.replace("data:", "selectableRows: true, data:"))
    kept = page.evaluate("""async () => {
      const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
      const drawn = () => [document.querySelector('.dg-body .dg-row[data-index="0"]'),
                           document.querySelector(".dg-header .dg-col")];
      const kept = {};
      document.querySelector('.dg-body .dg-row[data-index="1"] [data-field="name"]').click();
      let nodes = drawn(); await settle(); kept.click = nodes.map((n) => n.isConnected);
      grid.setSort("size", "desc");
      nodes = drawn(); await settle(); kept.sort = nodes.map((n) => n.isConnected);
      grid.setFilter([{field: "name", test: (d) => d.name !== "gamma"}]);
      nodes = drawn(); await settle(); kept.filter = nodes.map((n) => n.isConnected);
      grid.getColumn("size").hide();  // drawn by redraw(), not _afterStateChange()
      nodes = drawn(); await settle(); kept.hide = nodes.map((n) => n.isConnected);
      return kept;
    }""")
    assert kept == {"click": [True, True], "sort": [True, True], "filter": [True, True],
                    "hide": [True, True]}


def test_a_change_made_another_way_is_still_drawn_and_heard(page):
    """The store's word is still the net for a change that is not drawn at once:
    part 3's header filter narrows the rows that way. The table is reached
    directly here only to make such a change."""
    build(page, NAMES)
    page.evaluate("""() => {
      window.__filtered = 0;
      grid.on("dataFiltered", () => { window.__filtered += 1; });
      grid._table.setColumnFilters([{id: "name", value: {test: (d) => d.name === "beta"}}]);
    }""")
    page.wait_for_function("window.__filtered === 1")
    assert column_texts(page, "name") == ["beta"]


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
    box = page.locator(".dg-header .dg-select")
    assert box.evaluate("(b) => [b.checked, b.indeterminate]") == [False, False], "nothing chosen"
    page.locator(".dg-header .dg-select").check()
    assert page.evaluate("grid.getSelectedRows().length") == 3
    assert page.locator(".dg-body .dg-select:checked").count() == 3
    assert box.evaluate("(b) => [b.checked, b.indeterminate]") == [True, False], "all chosen"
    page.locator('.dg-body .dg-row[data-index="1"] .dg-select').uncheck()
    assert page.evaluate("grid.getSelectedRows().map((r) => r.getData().name)") == ["a", "c"]
    assert box.evaluate("(b) => [b.checked, b.indeterminate]") == [False, True], "some chosen"


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


# ---- grouping -----------------------------------------------------------------

BRANDS = """[
  {name: "a", brand: "A", unit: "kg", size: 1},
  {name: "b", brand: "A", unit: "m", size: 2},
  {name: "c", brand: " ", unit: "kg", size: 3},
  {name: "d", brand: "", unit: "kg", size: 4},
  {name: "e", brand: "B", unit: "m", size: 5},
]"""


def bands(page) -> list[str]:
    return page.evaluate("""() => Array.from(document.querySelectorAll(".dg-body .dg-row.dg-group"))
      .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
      .map((row) => row.textContent)""")


def data_rows(page) -> list[str]:
    """The `name` of every data row on screen, top to bottom: bands left out."""
    return page.evaluate("""() => Array.from(document.querySelectorAll(".dg-body .dg-row:not(.dg-group)"))
      .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
      .map((row) => row.querySelector('[data-field="name"]').textContent)""")


def test_rows_band_by_the_field_as_stored_and_each_band_counts_its_rows(page):
    """A band holds the rows whose FIELD is its value: a blank and a single space
    are two values, and folding them into one band nobody asked for is the
    defect the stored-field grouping fixed."""
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}, {{title: "Brand", field: "brand"}}],
      data: {BRANDS}, groupBy: ["brand"],
    }}""")
    assert page.evaluate("grid.getGroups().map((g) => [g.getKey(), g.getCount(), g.isOpen()])") == [
        ["A", 2, False], [" ", 1, False], ["", 1, False], ["B", 1, False]]
    assert bands(page) == ["A (2)", "  (1)", " (1)", "B (1)"]
    mount = page.locator("#mount")
    assert mount.get_attribute("role") == "treegrid"
    assert "dg-grouped" in mount.get_attribute("class")
    band = page.locator(".dg-body .dg-row.dg-group").first
    assert band.get_attribute("aria-expanded") == "false"
    assert band.get_attribute("aria-level") == "1"


def test_a_band_click_opens_one_level_and_open_all_reaches_every_level(page):
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}, {{title: "Brand", field: "brand"}},
                {{title: "Unit", field: "unit"}}],
      data: {BRANDS}, groupBy: ["brand", "unit"],
    }}""")
    page.locator(".dg-body .dg-row.dg-group").first.click()
    assert bands(page)[:3] == ["A (2)", "kg (1)", "m (1)"]
    assert page.locator(".dg-body .dg-row.dg-group").first.get_attribute("aria-expanded") == "true"
    assert data_rows(page) == []
    page.evaluate("() => grid.setAllGroupsOpen(true)")
    assert data_rows(page) == ["a", "b", "c", "d", "e"]
    inner = page.locator(".dg-body .dg-row.dg-group", has_text="kg (1)").first
    assert inner.get_attribute("aria-level") == "2"
    leaf = page.locator('.dg-body .dg-row:not(.dg-group)').first
    assert leaf.get_attribute("aria-level") == "3"
    page.evaluate("() => grid.setAllGroupsOpen(false)")
    assert bands(page) == ["A (2)", "  (1)", " (1)", "B (1)"]
    assert data_rows(page) == []


def test_a_function_groups_by_what_it_reads_and_its_column_is_never_drawn(page):
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}],
      data: {BRANDS},
      groupBy: [(row) => (row.size > 2 ? "big" : "small")],
      groupHeader: [(value, count) => Object.assign(document.createElement("strong"),
                                                    {{textContent: value + ": " + count}})],
    }}""")
    assert page.evaluate("grid.getGroups().map((g) => g.getKey())") == ["small", "big"]
    assert page.locator(".dg-group-cell strong").all_inner_texts() == ["small: 2", "big: 3"]
    assert page.locator('[data-field^="__group"]').count() == 0
    assert page.get_attribute("#mount", "aria-colcount") == "1"


def test_bands_are_never_selected_and_row_numbers_count_data_rows_only(page):
    build(page, f"""{{
      columns: [{{formatter: "rownum", headerSort: false}}, {{title: "Name", field: "name"}},
                {{title: "Brand", field: "brand"}}],
      data: {BRANDS}, groupBy: ["brand"], selectableRows: true,
    }}""")
    page.evaluate("() => grid.setAllGroupsOpen(true)")
    numbers = page.evaluate("""() => Array.from(document.querySelectorAll(".dg-body .dg-row:not(.dg-group)"))
      .sort((a, b) => Number(a.dataset.index) - Number(b.dataset.index))
      .map((row) => row.querySelector('[data-field="__rownum"]').textContent)""")
    assert numbers == ["1", "2", "3", "4", "5"], "a band takes no number"
    page.locator(".dg-body .dg-row.dg-group").first.click()
    assert page.evaluate("grid.getSelectedRows().length") == 0
    assert page.evaluate("grid.getGroups()[0].isOpen()") is False
    assert page.evaluate("grid.getGroups()[0].getRows().map((r) => r.getData().name)") == ["a", "b"]
    page.locator(".dg-body .dg-row:not(.dg-group)", has_text="c").first.click()
    assert page.evaluate("grid.getSelectedRows().map((r) => r.getData().name)") == ["c"]
    assert page.evaluate("grid.getData('active').map((d) => d.name)") == ["a", "b", "c", "d", "e"]


# ---- the tree -------------------------------------------------------------------

FAMILY = """[
  {name: "parent", kids: [{name: "kid one"}, {name: "kid two", kids: [{name: "grandkid"}]}]},
  {name: "single"},
]"""


def test_a_tree_opens_under_its_toggle_and_indents_each_level(page):
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}],
      data: {FAMILY}, dataTree: true, dataTreeChildField: "kids", selectableRows: true,
    }}""")
    assert data_rows(page) == ["parent", "single"]
    mount = page.locator("#mount")
    assert mount.get_attribute("role") == "treegrid"
    assert "dg-tree" in mount.get_attribute("class")
    toggle = page.locator(".dg-tree-toggle").first
    assert toggle.get_attribute("aria-expanded") == "false"
    assert toggle.get_attribute("aria-label") == "Expand"
    toggle.click()
    assert data_rows(page) == ["parent", "kid one", "kid two", "single"]
    assert page.evaluate("grid.getSelectedRows().length") == 0, "a toggle is not a row click"
    kid = page.locator(".dg-body .dg-row", has_text="kid one")
    assert kid.get_attribute("aria-level") == "2"
    indent = page.evaluate("""() => Array.from(document.querySelectorAll(".dg-tree-cell"))
      .map((cell) => parseFloat(getComputedStyle(cell).paddingInlineStart))""")
    assert indent[1] > indent[0], indent
    assert page.locator(".dg-tree-toggle").first.get_attribute("aria-label") == "Collapse"


def test_a_filter_keeps_a_parent_while_a_descendant_passes(page):
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}],
      data: {FAMILY}, dataTree: true, dataTreeChildField: "kids",
    }}""")
    page.evaluate("() => grid.setFilter([{field: 'name', type: 'like', value: 'grand'}])")
    assert data_rows(page) == ["parent"]
    page.locator(".dg-tree-toggle").first.click()
    assert data_rows(page) == ["parent", "kid two"]
    page.locator(".dg-body .dg-row", has_text="kid two").locator(".dg-tree-toggle").click()
    assert data_rows(page) == ["parent", "kid two", "grandkid"]


# ---- the header's tools -----------------------------------------------------------

def test_the_header_text_filter_narrows_as_one_types_and_keeps_the_cursor(page):
    """Typing redraws the header; the reader keeps typing where they were."""
    build(page, NAMES.replace('{title: "Name", field: "name"}',
                              '{title: "Name", field: "name", headerFilter: "input"}'))
    box = page.locator(".dg-header-input")
    assert box.get_attribute("aria-label") == "Filter Name"
    box.click()
    page.keyboard.type("al")
    assert column_texts(page, "name") == ["alpha"]
    state = page.evaluate("""() => [document.activeElement.className,
                                    document.activeElement.value,
                                    document.activeElement.selectionStart]""")
    assert state == ["dg-header-input", "al", 2]
    page.keyboard.press("Backspace")
    page.keyboard.press("Backspace")
    assert column_texts(page, "name") == ["beta", "gamma", "alpha"]


def test_each_header_control_answers_to_one_class(page):
    """The column's filter BUTTON and the text filter under a header once shared a
    class, so the theme's rule for one dressed the other too."""
    build(page, """{
      columns: [{title: "Name", field: "name", headerFilter: "input",
                 headerPopup: () => document.createElement("div"),
                 headerMenu: () => [{label: "x", action: () => {}}]}],
      data: [{name: "a"}],
    }""")
    tags = page.evaluate("""() => Object.fromEntries(
      ["dg-header-input", "dg-header-filter", "dg-header-menu"].map((name) =>
        [name, Array.from(document.getElementsByClassName(name)).map((el) => el.tagName)]))""")
    assert tags == {"dg-header-input": ["INPUT"], "dg-header-filter": ["BUTTON"],
                    "dg-header-menu": ["BUTTON"]}


MENU = """{
  columns: [
    {title: "Name", field: "name",
     headerMenuIcon: () => Object.assign(document.createElement("span"), {className: "menu-icon"}),
     headerMenu: () => [
       {label: "First", action: () => { window.__ran = "first"; }},
       {separator: true},
       {label: "Off", disabled: true, action: () => { window.__ran = "off"; }},
       {label: "Pin", menu: [{label: "Left", action: () => { window.__ran = "left"; }},
                             {label: "Right", action: () => { window.__ran = "right"; }}]},
     ]},
    {title: "Size", field: "size",
     headerMenu: () => [{label: "Other", action: () => {}}],
     headerPopup: () => {
       const box = document.createElement("div");
       box.append(Object.assign(document.createElement("input"), {className: "inside"}));
       return box;
     }},
  ],
  data: [{name: "a", size: 1}, {name: "b", size: 2}],
}"""


def test_a_header_menu_opens_runs_an_item_and_gives_the_focus_back(page):
    build(page, MENU)
    button = page.locator(f'{header(page, "name")} .dg-header-menu')
    assert button.get_attribute("aria-haspopup") == "menu"
    assert button.get_attribute("aria-label") == "Open menu for Name"
    assert button.locator(".menu-icon").count() == 1
    button.click()
    menu = page.locator(".dg-menu")
    assert menu.get_attribute("role") == "menu"
    assert menu.locator(".dg-menu-item").all_inner_texts() == ["First", "Off", "Pin"]
    assert menu.locator(".dg-menu-separator").count() == 1
    assert menu.locator(".dg-menu-item", has_text="Off").is_disabled()
    assert button.get_attribute("aria-expanded") == "true"
    assert page.evaluate("document.activeElement.textContent") == "First"
    assert page.locator(header(page, "name")).get_attribute("aria-sort") == "none", \
        "opening a menu is not a sort"
    menu.locator(".dg-menu-item", has_text="First").click()
    assert page.evaluate("window.__ran") == "first"
    assert page.locator(".dg-menu").count() == 0
    assert button.get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.classList.contains('dg-header-menu')")


def test_escape_closes_a_menu_the_instant_it_opens(page):
    build(page, MENU)
    state = page.evaluate("""() => {
      const button = document.querySelector('.dg-col[data-field="name"] .dg-header-menu');
      button.click();
      const opened = document.querySelectorAll(".dg-menu").length;
      document.activeElement.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
      return [opened, document.querySelectorAll(".dg-menu").length,
              button.getAttribute("aria-expanded"), document.activeElement === button];
    }""")
    assert state == [1, 0, "false", True]


def test_a_popup_takes_the_focus_and_only_a_click_outside_closes_it(page):
    build(page, MENU)
    button = page.locator(f'{header(page, "size")} .dg-header-filter')
    assert button.get_attribute("aria-haspopup") == "dialog"
    button.click()
    popup = page.locator(".dg-popup")
    assert popup.get_attribute("role") == "dialog"
    assert page.evaluate("document.activeElement.className") == "inside"
    popup.locator(".inside").click()
    assert page.locator(".dg-popup").count() == 1
    page.mouse.click(900, 700)
    assert page.locator(".dg-popup").count() == 0
    assert button.get_attribute("aria-expanded") == "false"


def test_one_surface_opens_at_a_time_and_its_button_closes_it_again(page):
    build(page, MENU)
    first = page.locator(f'{header(page, "name")} .dg-header-menu')
    second = page.locator(f'{header(page, "size")} .dg-header-menu')
    first.click()
    second.click()
    assert page.locator(".dg-menu").count() == 1
    assert page.locator(".dg-menu .dg-menu-item").all_inner_texts() == ["Other"]
    assert first.get_attribute("aria-expanded") == "false"
    second.click()
    assert page.locator(".dg-menu").count() == 0
    # Before the first has armed its outside click, which waits a turn.
    assert page.evaluate("""() => {
      document.querySelector('.dg-col[data-field="name"] .dg-header-menu').click();
      document.querySelector('.dg-col[data-field="size"] .dg-header-menu').click();
      return document.querySelectorAll(".dg-menu").length;
    }""") == 1


def test_the_arrow_keys_walk_a_menu_and_open_and_close_its_submenu(page):
    build(page, MENU)
    page.locator(f'{header(page, "name")} .dg-header-menu').click()
    focused = "document.activeElement.textContent"
    page.keyboard.press("ArrowDown")
    assert page.evaluate(focused) == "Pin", "a disabled item is passed over"
    page.keyboard.press("ArrowDown")
    assert page.evaluate(focused) == "First", "the walk wraps"
    page.keyboard.press("ArrowUp")
    assert page.evaluate(focused) == "Pin"
    page.keyboard.press("ArrowRight")
    sub = page.locator(".dg-submenu")
    assert sub.locator(".dg-menu-item").all_inner_texts() == ["Left", "Right"]
    assert page.evaluate(focused) == "Left"
    assert page.locator(".dg-menu-parent").get_attribute("aria-expanded") == "true"
    page.keyboard.press("ArrowLeft")
    assert page.locator(".dg-submenu").count() == 0
    assert page.evaluate(focused) == "Pin"
    assert page.locator(".dg-menu").count() == 1, "only the submenu closed"
    page.locator(".dg-menu-parent").hover()
    page.locator(".dg-submenu .dg-menu-item", has_text="Right").click()
    assert page.evaluate("window.__ran") == "right"
    assert page.locator(".dg-menu").count() == 0


def test_scrolling_or_destroying_the_grid_closes_what_a_column_opened(page):
    build(page, MENU.replace('data: [{name: "a", size: 1}, {name: "b", size: 2}]',
                             'data: Array.from({length: 200}, (_, i) => ({name: "n" + i, size: i}))'))
    page.locator(f'{header(page, "name")} .dg-header-menu').click()
    assert page.locator(".dg-menu").count() == 1
    page.evaluate("document.querySelector('.dg-scroller').scrollTop = 400")
    page.wait_for_function("document.querySelectorAll('.dg-menu').length === 0")
    page.locator(f'{header(page, "name")} .dg-header-menu').click()
    page.evaluate("() => grid.destroy()")
    assert page.locator(".dg-menu").count() == 0


# ---- resizing, moving, measuring ------------------------------------------------

def drag(page, selector: str, dx: float, *, check_midway=None) -> None:
    box = page.locator(selector).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y, steps=4)
    if check_midway:
        check_midway()
    page.mouse.move(x + dx, y, steps=4)
    page.mouse.up()


RESIZE = """{
  columns: [{title: "A", field: "a", minWidth: 60}, {title: "B", field: "b"}, {title: "C", field: "c"}],
  data: [{a: 1, b: 2, c: 3}],
}"""


def test_dragging_a_resize_handle_sets_the_width_and_says_so(page):
    build(page, RESIZE)
    page.evaluate("""() => { window.__resized = [];
      grid.on("columnResized", (column) => window.__resized.push(column.getField())); }""")
    before = page.evaluate("grid.getColumn('a').getWidth()")
    handle = f'{header(page, "a")} .dg-resize-handle'

    def lit():
        assert "is-active" in page.locator(handle).get_attribute("class")

    drag(page, handle, 60, check_midway=lit)
    assert page.evaluate("grid.getColumn('a').getWidth()") == pytest.approx(before + 60, abs=1)
    assert page.evaluate("window.__resized") == ["a"]
    assert "is-active" not in page.locator(handle).get_attribute("class")
    assert page.locator(header(page, "a")).get_attribute("aria-sort") == "none", \
        "letting go of a handle is not a sort"
    drag(page, handle, -500)
    assert page.evaluate("grid.getColumn('a').getWidth()") == 60, "never below the minimum"


def test_in_a_right_to_left_page_dragging_towards_the_start_widens(page):
    page.evaluate("document.getElementById('mount').dir = 'rtl'")
    build(page, RESIZE)
    before = page.evaluate("grid.getColumn('a').getWidth()")
    drag(page, f'{header(page, "a")} .dg-resize-handle', -40)
    assert page.evaluate("grid.getColumn('a').getWidth()") == pytest.approx(before + 40, abs=1)


def test_dragging_a_header_moves_its_column_and_the_drop_is_not_a_sort(page):
    build(page, """{
      columns: [{title: "P", field: "p", width: 80, frozen: "left"},
                {title: "A", field: "a", width: 120}, {title: "B", field: "b", width: 120},
                {title: "C", field: "c", width: 120}],
      data: [{p: 0, a: 1, b: 2, c: 3}],
      movableColumns: true,
    }""")
    page.evaluate("""() => { window.__moved = [];
      grid.on("columnMoved", (column) => window.__moved.push(column.getField())); }""")
    order = "grid.getColumns().map((c) => c.getField())"
    drag(page, header(page, "a"), 250)
    assert page.evaluate(order) == ["p", "b", "c", "a"]
    assert page.evaluate("window.__moved") == ["a"]
    assert page.locator(header(page, "a")).get_attribute("aria-sort") == "none"
    drag(page, header(page, "p"), 250)
    assert page.evaluate(order) == ["p", "b", "c", "a"], "a column moves within its own pinned band"
    assert page.evaluate("window.__moved") == ["a"], "and nothing that did not move says it did"
    # A drag that comes back to where it began moves nothing, redraws nothing,
    # and so is released on the very header it started on: still not a sort.
    box = page.locator(header(page, "b")).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 30, y, steps=3)
    # Short of its own middle, so the drop target is itself (at the middle exactly
    # it would be the next column, and that is a move).
    page.mouse.move(x - 10, y, steps=3)
    page.mouse.up()
    assert page.evaluate(order) == ["p", "b", "c", "a"]
    assert page.locator(header(page, "b")).get_attribute("aria-sort") == "none"


def test_a_column_measures_the_widest_of_its_header_and_its_cells(page):
    build(page, """{
      columns: [{title: "A", field: "a"}, {title: "B", field: "b"}, {title: "C", field: "c"}],
      data: [{a: "x".repeat(80), b: "y", c: "z"}],
    }""")
    measured = page.evaluate("grid.getColumn('a').measureContentWidth()")
    text = page.evaluate("""() => {
      const probe = document.createElement("span");
      probe.style.font = "14px/1.4 sans-serif"; probe.textContent = "x".repeat(80);
      document.body.append(probe); const w = probe.getBoundingClientRect().width; probe.remove();
      return w; }""")
    assert measured >= text
    assert measured > page.evaluate("grid.getColumn('a').getWidth()")
    assert page.evaluate("grid.getColumn('b').measureContentWidth()") >= 40


# ---- totals and export ------------------------------------------------------------

def test_the_totals_row_averages_without_blanks_and_counts_what_is_there(page):
    """Tabulator counted a blank as 0 in an average; the renderer leaves it out."""
    build(page, """{
      columns: [{title: "Price", field: "price", topCalc: "avg", topCalcParams: {precision: 1}},
                {title: "Name", field: "name", topCalc: "count"}],
      data: [{price: 1, name: "a"}, {price: "", name: ""}, {price: 4, name: "c"}, {price: null}],
    }""")
    calc = page.locator(".dg-header .dg-calcs")
    assert calc.get_attribute("aria-rowindex") == "2"
    assert calc.locator(".dg-cell").all_inner_texts() == ["2.5", "2"]
    assert page.get_attribute("#mount", "aria-rowcount") == "6"
    assert page.locator('.dg-body .dg-row[data-index="0"]').get_attribute("aria-rowindex") == "3"
    page.evaluate("() => grid.setFilter([{field: 'price', test: (row) => row.price >= 4}])")
    assert page.locator(".dg-calcs .dg-cell").all_inner_texts() == ["4", "1"]


def test_a_download_writes_the_rows_shown_in_order_and_leaves_built_ins_out(page):
    build(page, """{
      columns: [{formatter: "rowSelection", titleFormatter: "rowSelection", headerSort: false},
                {formatter: "rownum", headerSort: false},
                {title: "Name", field: "name"}, {title: "Note", field: "note"},
                {title: "Hidden", field: "h", visible: false},
                {title: "Internal", field: "i", download: false}],
      data: [{name: "b", note: {k: 1}, h: 1, i: 2}, {name: 'say "hi"', note: "x", h: 1, i: 2},
             {name: "gone", note: "", h: 1, i: 2}],
      selectableRows: true,
    }""")
    page.evaluate("""() => { grid.setSort("name", "desc");
      grid.setFilter([{field: "name", test: (row) => row.name !== "gone"}]); }""")
    csv = page.evaluate("grid.download('csv', 'rows.csv')")
    assert csv.split("\n") == ['"Name","Note"', '"say ""hi""","x"', '"b","{""k"":1}"']
    rows = page.evaluate("JSON.parse(grid.download('json', 'rows.json'))")
    assert rows == [{"Name": 'say "hi"', "Note": "x"}, {"Name": "b", "Note": {"k": 1}}]


def test_a_download_unrolls_bands_and_carries_a_trees_closed_children(page):
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}], data: {BRANDS}, groupBy: ["brand"],
    }}""")
    assert page.evaluate("grid.download('csv', 'g.csv')").split("\n") == [
        '"Name"', '"a"', '"b"', '"c"', '"d"', '"e"']
    build(page, f"""{{
      columns: [{{title: "Name", field: "name"}}], data: {FAMILY},
      dataTree: true, dataTreeChildField: "kids",
    }}""")
    assert page.evaluate("grid.download('csv', 't.csv')").split("\n") == [
        '"Name"', '"parent"', '"kid one"', '"kid two"', '"grandkid"', '"single"']
