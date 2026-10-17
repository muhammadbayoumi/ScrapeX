"""The grid refreshes in place when its host asks, and only the newest answer paints (#1198).

The extension's Data page narrows a contractor table by activity. Each tick asks the
engine again, and the answer has to land in the grid the reader is already using: his
sort, his filters, his pins, his widths and his grouping kept, the old rows on screen,
dimmed, until the new ones are drawn. So the grid hands its host exactly one thing,
`connect(grid)` with a frozen `{refresh}`, and the engine's own page, which names no
`connect`, gets no refresh at all.

A refresh is the first load run again with a table on screen. The answer replaces the
payload WHOLE (the tax column, the filter popups, the truncation note and nesting all
read it), `build()` draws it, and only the newest ask paints: an ask a newer one
overtakes settles at once as superseded, so a slow answer can never put an older
selection on screen.

Every race below is made deterministic by the host itself. The DEFERRED host parks each
`loadTable` call in `window.__asks` and the test answers it by hand, in whatever order the
race needs; the INSTANT host answers `window.__next` at once, for the races that live
inside the grid's own build.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright

import grid_harness as harness  # noqa: E402

#: An engine address nothing listens on. Every fetch is answered by the harness's stub, and
#: the browser context aborts anything that would still leave for it.
ENGINE = "http://127.0.0.1:9"
#: How long a wait may take before the test says what it was waiting for.
WAIT = 10_000

# ---- the answers the host hands the grid --------------------------------------------

COLUMNS = [
    {"key": "product_name", "label": "Product name"},
    {"key": "product_name_ar", "label": "Product name (AR)"},
    {"key": "brand", "label": "Brand"},
    {"key": "price", "label": "Price"},
    {"key": "code", "label": "Code"},
    {"key": "tax", "label": "Tax"},
]


def _row(offer_id, brand, price, code=""):
    return {"offer_id": offer_id, "product_name": f"Item {offer_id}",
            "product_name_ar": f"صنف {offer_id}", "brand": brand, "price": price,
            "code": code, "currency": "SAR", "tax_ref": 0, "product_link": "",
            "availability": "in_stock"}


def _table(rows, *, tax="Incl. 15%", nodes=(), total=None, population=None):
    """A products answer as the engine shapes one, with the selection it was asked for."""
    total = len(rows) if total is None else total
    return {
        "source_key": "TESTSRC",
        "columns": copy.deepcopy(COLUMNS),
        "rows": rows,
        "tax_states": [{"tax_short": tax, "tax": tax}],
        "total": total, "returned": len(rows), "truncated": total > len(rows),
        "population": total if population is None else population,
        "tree": None, "bilingual": {"product_name_ar": "product_name"},
        "moved_to_details": [],
        "filtered_by": {"nodes": list(nodes), "mode": "any"},
    }


A = _table([_row(1, "AKS", 30.5, "10"), _row(2, "3M", 12.25, "2"),
            _row(3, "AKS", 7.0, "1")])
#: A' — the same shape as A, other rows, other brands.
A2 = _table([_row(7, "Makita", 11.0), _row(8, "Hilti", 22.0), _row(9, "Makita", 33.0)])
B = _table([_row(4, "Sika", 45.0), _row(5, "Bosch", 9.5)], tax="Excl. VAT",
           nodes=[7], total=9)
C = _table([_row(6, "Hilti", 14.0)], nodes=[8])
#: A selection that matches nothing: a built grid showing its own empty row.
EMPTY_FILTERED = _table([], nodes=[7], population=3)
#: A source with nothing stored, answered with the selection keys a producer sends.
EMPTY_UNFILTERED = _table([])
#: A source with nothing stored, from a producer that sends no selection at all.
EMPTY_BARE = {key: value for key, value in _table([]).items() if key != "filtered_by"}


def _dataset(first_id):
    """A contractor answer: rows carry their record id and no offer, tax_states is {}."""
    rows = [{"observed_record_id": first_id + n, "contractor_id": str(1000 + first_id + n),
             "company_name": f"Company {first_id + n}"} for n in range(3)]
    return {
        "source_key": "TESTSRC",
        "columns": [{"key": "contractor_id", "label": "Contractor id"},
                    {"key": "company_name", "label": "Company name"}],
        "rows": rows, "total": 3, "returned": 3, "truncated": False, "population": 3,
        "filtered_by": {"nodes": [], "mode": "any"}, "folded": False,
        "fold_variants": False, "foldable": False, "tree": {}, "bilingual": {},
        "tax_states": {}, "moved_to_details": [],
    }


FIELDS = {"fields": [{"field_key": column["key"], "display_name": column["label"],
                      "is_hidden": False} for column in COLUMNS]}
PROMOTABLE = {"attributes": []}
OFFER = {"periods": [], "changes": [], "observations": [], "attributes": []}

# ---- host_js layers ------------------------------------------------------------------

#: Runs before every other layer: counts, records, and one focusable control of the host's.
INSTRUMENT = r"""
(function () {
  window.__uncaught = [];
  window.addEventListener('error', (event) => { window.__uncaught.push(String(event.message)); });
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    window.__uncaught.push(reason instanceof Error ? reason.message : String(reason));
  });

  // Every table grid.js constructs, counted, and whether its build has been announced.
  // grid.js builds through window.ScrapeXDataGrid, which it sets once its renderer
  // module has loaded, so the handle is wrapped the moment it is set.
  window.__builds = 0;
  window.__tables = [];
  let renderer;
  Object.defineProperty(window, 'ScrapeXDataGrid', {
    configurable: true,
    get: () => renderer,
    set: (real) => {
      renderer = new Proxy(real, {
        construct(target, args) {
          window.__builds += 1;
          const instance = Reflect.construct(target, args);
          const entry = {built: false};
          window.__tables.push(entry);
          instance.on('tableBuilt', () => { entry.built = true; });
          return instance;
        },
      });
    },
  });

  // How many live ResizeObservers watch #grid or anything drawn inside it. Each built
  // table makes its own, and its destroy must release every one of them; a table that
  // leaked one would keep watching a grid that is gone.
  const watching = new Map();
  const inGrid = (target) => !!(target && target.closest && target.closest('#grid'));
  const RealObserver = window.ResizeObserver;
  window.ResizeObserver = class extends RealObserver {
    observe(target, options) {
      if (inGrid(target)) {
        if (!watching.has(this)) watching.set(this, new Set());
        watching.get(this).add(target);
      }
      return super.observe(target, options);
    }
    unobserve(target) {
      const watched = watching.get(this);
      if (watched) { watched.delete(target); if (!watched.size) watching.delete(this); }
      return super.unobserve(target);
    }
    disconnect() {
      watching.delete(this);
      return super.disconnect();
    }
  };
  Object.defineProperty(window, '__gridObservers', {get: () => watching.size});

  // The host's own control, standing in for the activity tick the reader just pressed.
  const tick = document.createElement('input');
  tick.type = 'checkbox';
  tick.id = 'activity-tick';
  document.body.append(tick);

  const busyHost = () => document.querySelector('[data-grid-viewport]')
    || document.getElementById('grid');
  const drawnNames = () => [...document.querySelectorAll(
    '#grid .dg-body .dg-row .dg-cell[data-field="product_name"]')]
    .map((cell) => cell.textContent);

  // One entry per refresh, written once, when it settles.
  window.__outcomes = [];
  window.__settles = [];
  window.__refresh = function () {
    const i = window.__outcomes.length;
    window.__outcomes.push(null);
    let result;
    try {
      result = window.__grid.refresh();
    } catch (error) {
      window.__outcomes[i] = {threw: String(error && error.message)};
      window.__settles[i] = Promise.resolve();
      return i;
    }
    const thenable = !!result && typeof result.then === 'function';
    window.__settles[i] = Promise.resolve(result).then((outcome) => {
      window.__outcomes[i] = {
        ok: outcome.state, rows: outcome.payload ? outcome.payload.rows.length : null,
        frozen: Object.isFrozen(outcome), busy: busyHost().getAttribute('aria-busy'),
        drawn: drawnNames(), thenable,
      };
    }, (error) => {
      window.__outcomes[i] = {
        err: error instanceof Error ? error.message : String(error),
        isError: error instanceof Error, busy: busyHost().getAttribute('aria-busy'),
        thenable,
      };
    });
    return i;
  };
})();
"""

#: The host answers each ask when the test says so: `window.__asks[i].resolve(payload)`.
DEFERRED = """
window.__asks = [];
window.__connects = 0;
window.ScrapeXGridHost = {
  loadTable: (path) => new Promise((resolve, reject) => {
    window.__asks.push({path, resolve, reject});
  }),
  connect: (grid) => {
    window.__connects += 1;
    window.__grid = grid;
    if (window.__onConnect) window.__onConnect(grid);
  },
};
"""

#: The host answers every ask at once with `window.__next`, or through `window.__loader`.
INSTANT = """
window.__next = window.__payload;
window.__loads = [];
window.__loader = null;
window.__connects = 0;
window.ScrapeXGridHost = {
  loadTable: (path) => {
    window.__loads.push(path);
    return window.__loader ? window.__loader(path) : Promise.resolve(window.__next);
  },
  connect: (grid) => {
    window.__connects += 1;
    window.__grid = grid;
    if (window.__onConnect) window.__onConnect(grid);
  },
};
"""

#: Holds every record the panel asks for until the test releases it.
HOLD_OFFERS = """
(function () {
  const answer = window.fetch;
  window.__held = [];
  window.fetch = function (url, options) {
    if (String(url).includes('/api/offer/')) {
      return new Promise((resolve) => {
        window.__held.push(() => resolve(answer(url, options)));
      });
    }
    return answer(url, options);
  };
  window.__release = () => {
    const held = window.__held.splice(0);
    held.forEach((go) => go());
    return held.length;
  };
})();
"""

#: Holds every animation frame. The grid's size observer redraws on one.
HOLD_FRAMES = """
window.__rafs = [];
window.requestAnimationFrame = (callback) => window.__rafs.push(callback);
"""


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

    def opener(payload, *, host_js=""):
        target = harness.build_page(tmp_path, payload, fields=FIELDS,
                                    promotable=PROMOTABLE, offer=OFFER,
                                    host_js=INSTRUMENT + host_js,
                                    name=f"grid{len(contexts)}.html")
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        contexts.append(context)
        context.route(f"{ENGINE}/**", lambda route: route.abort())
        page = context.new_page()
        # Before goto, so nothing the first load says is missed.
        page.logs = []
        page.errors = []
        page.on("console", lambda message: page.logs.append(message.text))
        page.on("pageerror", lambda error: page.errors.append(str(error)))
        page.goto(f"{base}/{target.name}")
        return page

    # SERVED, because the grid's renderer is a module and file:// refuses modules.
    with harness.serve(tmp_path) as base:
        yield opener
        for context in contexts:
            context.close()


# ---- driving the page ------------------------------------------------------------------

def _quiet(page):
    """Every table grid.js constructed has announced its build."""
    page.wait_for_function(
        "() => window.__tables.length > 0 && window.__tables.every((t) => t.built)",
        polling=50, timeout=WAIT)


def _landed(page):
    """The first answer has landed, WHICHEVER way: a table built, a sentence under it, or
    an error. Waiting for only the expected one turns every wrong way into a bare
    timeout; this lets the assertion that follows say which way it went."""
    page.wait_for_function(
        "() => window.__tables.some((t) => t.built)"
        "  || !document.getElementById('grid-note').hidden"
        "  || window.__uncaught.length > 0",
        polling=50, timeout=WAIT)
    page.wait_for_timeout(100)


def _resolve(page, ask, payload):
    page.wait_for_function("(i) => window.__asks.length > i", arg=ask, polling=50,
                           timeout=WAIT)
    page.evaluate("([i, p]) => window.__asks[i].resolve(p)", [ask, payload])


def _reject(page, ask, reason_js):
    page.wait_for_function("(i) => window.__asks.length > i", arg=ask, polling=50,
                           timeout=WAIT)
    page.evaluate(f"(i) => window.__asks[i].reject({reason_js})", ask)


def _shown(page, payload):
    """The DEFERRED host answers the first load, and the grid draws it."""
    _resolve(page, 0, payload)
    _quiet(page)


def _refresh(page) -> int:
    return page.evaluate("() => window.__refresh()")


def _outcome(page, index):
    page.wait_for_function("(i) => window.__outcomes[i] !== null", arg=index, polling=50,
                           timeout=WAIT)
    return page.evaluate("(i) => window.__outcomes[i]", index)


def _refresh_to(page, payload):
    """The INSTANT host answers `payload`, and the refresh settles."""
    return page.evaluate("""async (p) => {
        window.__next = p;
        const i = window.__refresh();
        await window.__settles[i];
        return window.__outcomes[i];
    }""", payload)


def _rebuild(page, action):
    """Run something that builds the table again, and wait for that build to finish."""
    before = page.evaluate("() => window.__tables.length")
    action()
    page.wait_for_function(
        "(n) => window.__tables.length > n && window.__tables.every((t) => t.built)",
        arg=before, polling=50, timeout=WAIT)
    page.wait_for_timeout(100)      # the post-build redraw


def _offers(page):
    return page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getData().map((row) => row.offer_id)")


def _names(page):
    return page.evaluate("""() => [...document.querySelectorAll(
        '#grid .dg-body .dg-row .dg-cell[data-field="product_name"]')]
        .map((cell) => cell.textContent)""")


def _note(page):
    return page.evaluate("""() => {
        const note = document.getElementById('grid-note');
        return {hidden: note.hidden, text: note.textContent};
    }""")


def _flip(page, feature):
    page.evaluate("""(name) => {
        const box = document.querySelector('[data-feature="' + name + '"]');
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', {bubbles: true}));
    }""", feature)


def _popup_values(page, field):
    """Open a column's filter popup and read the values it offers, (Select all) aside."""
    return page.evaluate("""(field) => {
        const column = document.querySelector(`#grid .dg-col[data-field="${field}"]`);
        column.querySelector('.material-filter-icon').parentElement.click();
        return [...document.querySelectorAll('.setfilter-row:not(.strong) span')]
          .map((span) => span.textContent);
    }""", field)


def _filter_to(page, field, value):
    """His way: untick (Select all), tick one value, Apply."""
    page.evaluate("""([field, value]) => {
        const column = document.querySelector(`#grid .dg-col[data-field="${field}"]`);
        column.querySelector('.material-filter-icon').parentElement.click();
        document.querySelector('.setfilter-row.strong input').click();
        const row = [...document.querySelectorAll('.setfilter-row:not(.strong)')]
          .find((r) => r.querySelector('span').textContent === value);
        row.querySelector('input').click();
        [...document.querySelectorAll('.setfilter-actions button')]
          .find((b) => b.textContent === 'Apply').click();
    }""", [field, value])


def _menu(page, field, *path):
    """Open a column's three-dot menu and press each item of `path` in turn."""
    page.evaluate("""([field, path]) => {
        const column = document.querySelector(`#grid .dg-col[data-field="${field}"]`);
        const button = column.querySelector('.material-menu-icon').parentElement;
        const r = button.getBoundingClientRect();
        const o = {bubbles: true, cancelable: true, button: 0, buttons: 1,
                   clientX: r.left + 3, clientY: r.top + 3, view: window};
        button.dispatchEvent(new MouseEvent('mousedown', o));
        button.dispatchEvent(new MouseEvent('mouseup', o));
        button.dispatchEvent(new MouseEvent('click', o));
        for (const label of path) {
          const menus = document.querySelectorAll('.dg-menu');
          const items = [...menus[menus.length - 1].querySelectorAll('.dg-menu-item')];
          const item = items.find((x) => x.textContent.trim() === label);
          if (!item) {
            throw new Error('no ' + label + ' in ' + items.map((x) => x.textContent.trim()));
          }
          item.click();
        }
    }""", [field, list(path)])


def _uncaught(page):
    return page.evaluate("() => window.__uncaught")


# ---- what a refresh draws ----------------------------------------------------------------

def test_a_refresh_draws_the_whole_new_answer_not_only_its_rows(open_grid):
    """If this fails, he ticks an activity and the new rows wear the old answer's tax
    verdict, the 'Loaded 2 of 9' warning never appears, and the Brand filter offers
    brands that are no longer in the table."""
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)

    index = _refresh(page)
    _resolve(page, 1, B)
    outcome = _outcome(page, index)

    assert (outcome["ok"], outcome["rows"]) == ("drawn", 2), outcome
    assert _offers(page) == [4, 5]
    assert page.evaluate("""() => document.querySelector(
        '#grid .dg-body .dg-row .dg-cell[data-field="tax"]').textContent""") == (
        "Excl. VAT"), "the tax cell still reads the previous answer's tax_states"
    assert _note(page) == {"hidden": False,
                           "text": "Loaded 2 of 9; filters search only what is loaded"}
    assert _popup_values(page, "brand") == ["Bosch", "Sika"], (
        "the filter popup lists the previous answer's values")


def test_a_refresh_keeps_the_readers_sort_column_filter_pin_width_and_grouping(open_grid):
    """If this fails, every activity he ticks throws away the table he arranged: the sort,
    the Brand filter, the pinned column, the width he fitted and the grouping all reset."""
    six = _table([_row(1, "AKS", 30.5), _row(2, "3M", 12.25), _row(3, "AKS", 7.0),
                  _row(4, "Bosch", 50.0), _row(5, "AKS", 18.75), _row(6, "3M", 3.1)])
    page = open_grid(six, host_js=DEFERRED)
    _shown(page, six)

    page.evaluate("() => ScrapeXDataGrid.find('#grid').setSort('price', 'desc')")
    _filter_to(page, "brand", "AKS")
    _rebuild(page, lambda: _menu(page, "brand", "Pin Column", "Pin Left"))
    _rebuild(page, lambda: _menu(page, "price", "Auto-fit column width"))
    width = page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getColumn('price').getWidth()")
    _rebuild(page, lambda: _menu(page, "brand", "Group by Brand"))

    read = """() => {
        const t = ScrapeXDataGrid.find('#grid');
        return {
          sorters: t.getSorters().map((s) => s.field + ':' + s.dir),
          active: t.getData('active').map((r) => [r.brand, r.price]),
          chips: document.getElementById('grid-chips').textContent,
          frozen: t.getColumn('brand').getDefinition().frozen === 'left',
          width: t.getColumn('price').getWidth(),
          groups: t.getGroups().map((g) => [g.getKey(),
                                             g.getRows().map((r) => r.getData().offer_id)]),
        };
    }"""
    before = page.evaluate(read)
    # The arrangement really is in place, or "kept" below would be about nothing.
    assert before["sorters"] == ["price:desc"], before
    assert before["active"] == [["AKS", 30.5], ["AKS", 18.75], ["AKS", 7.0]], before
    assert "Brand: is AKS" in before["chips"], before
    assert before["frozen"], before
    assert [key for key, _rows in before["groups"]] == ["AKS"], before

    fresh = _table([_row(11, "AKS", 5.5), _row(12, "AKS", 99.0), _row(13, "AKS", 42.0),
                    _row(14, "3M", 1.0), _row(15, "3M", 2.0),
                    _row(16, "Bosch", 60.0), _row(17, "Bosch", 70.0)])
    index = _refresh(page)
    _resolve(page, 1, fresh)
    assert _outcome(page, index)["ok"] == "drawn"
    _quiet(page)
    page.wait_for_timeout(100)
    after = page.evaluate(read)

    assert after["sorters"] == ["price:desc"], after
    assert {brand for brand, _price in after["active"]} == {"AKS"}, after
    prices = [price for _brand, price in after["active"]]
    assert prices == [99.0, 42.0, 5.5], f"not the new AKS rows, strictly descending: {after}"
    assert "Brand: is AKS" in after["chips"], after
    assert after["frozen"], "the pinned Brand column came back unpinned"
    assert abs(after["width"] - width) <= 1, (width, after["width"])
    assert [key for key, _rows in after["groups"]] == ["AKS"], after
    assert sorted(after["groups"][0][1]) == [11, 12, 13], after


def test_a_refresh_chooses_each_columns_sorter_again_from_the_new_rows(open_grid):
    """If this fails, a column that was all numbers before he ticked an activity keeps
    sorting as numbers after the new rows bring words into it, and the words land in
    whatever order they were stored."""
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)
    # A's codes are all numbers, so the column started on the number sorter: 10 after 9.
    assert page.evaluate("""() => {
        const t = ScrapeXDataGrid.find('#grid');
        t.setSort('code', 'asc');
        const order = t.getData('active').map((r) => r.code);
        t.setSort();
        return order;
    }""") == sorted(page.evaluate("() => window.__payload.rows.map((r) => r.code)"),
                    key=float), "A's code column should have started on the number sorter"

    words = _table([_row(21, "AKS", 1.0, "10"), _row(22, "AKS", 2.0, "2"),
                    _row(23, "AKS", 3.0, "1"), _row(24, "AKS", 4.0, "Beta"),
                    _row(25, "AKS", 5.0, "abc")])
    index = _refresh(page)
    _resolve(page, 1, words)
    assert _outcome(page, index)["ok"] == "drawn"

    order = page.evaluate("""() => {
        const t = ScrapeXDataGrid.find('#grid');
        t.setSort('code', 'asc');
        return t.getData('active').map((r) => r.code);
    }""")
    assert order == ["1", "2", "10", "abc", "Beta"], order


def test_a_refresh_can_turn_nesting_on_and_off(open_grid):
    """If this fails, a table nested by Brand never shows its branches when a narrower
    selection brings two rows of one brand together, or keeps a tree that no longer
    has anything to nest."""
    unique = _table([_row(1, "AKS", 1.0), _row(2, "3M", 2.0), _row(3, "Sika", 3.0)])
    page = open_grid(unique, host_js="localStorage.setItem('scrapex-treeby-v2-TESTSRC', "
                                     "'brand');" + INSTANT)
    _quiet(page)
    tree = """() => {
        const t = ScrapeXDataGrid.find('#grid');
        return {
          controls: document.querySelectorAll('#grid .dg-tree-toggle').length,
          count: t.getDataCount(),
          branches: t.getData().filter((r) => Array.isArray(r._children))
                      .map((r) => r._children.length),
        };
    }"""
    assert page.evaluate(tree) == {"controls": 0, "count": 3, "branches": []}

    shared = _table([_row(31, "AKS", 1.0), _row(32, "3M", 2.0), _row(33, "AKS", 3.0)])
    assert _refresh_to(page, shared)["ok"] == "drawn"
    nested = page.evaluate(tree)
    assert nested["controls"] >= 1, nested
    assert nested["branches"] == [2], nested
    assert nested["count"] == 2, nested

    apart = _table([_row(41, "Bosch", 1.0), _row(42, "Hilti", 2.0), _row(43, "Sika", 3.0)])
    assert _refresh_to(page, apart)["ok"] == "drawn"
    assert page.evaluate(tree) == {"controls": 0, "count": 3, "branches": []}


def test_one_feature_switch_after_a_refresh_builds_the_table_once(open_grid):
    """If this fails, every switch in Grid Features rebuilds the table once per answer the
    grid has drawn, so a page he has filtered ten times builds ten tables per click."""
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)
    index = _refresh(page)
    _resolve(page, 1, A2)
    assert _outcome(page, index)["ok"] == "drawn"

    page.evaluate("() => { window.__builds = 0; }")
    _flip(page, "stripe")
    page.wait_for_function(
        "() => document.getElementById('grid').classList.contains('striped')"
        "  && document.querySelectorAll('#grid .dg-body .dg-row').length > 0",
        polling=50, timeout=WAIT)
    page.wait_for_timeout(150)

    assert page.evaluate("() => window.__builds") == 1
    assert page.evaluate("() => document.getElementById('grid-features').dataset.wired") == "1"


@pytest.mark.parametrize("rebuild", ["engine-page-feature-switch", "host-refresh"])
def test_the_language_choice_survives_a_rebuild(open_grid, rebuild):
    """If this fails, he presses AR, then any rebuild (a feature switch on the engine's
    page, an activity tick on the extension's) shows the English and the Arabic name
    columns side by side while the switch still reads AR."""
    engine = rebuild == "engine-page-feature-switch"
    page = open_grid(A, host_js="" if engine else DEFERRED)
    if not engine:
        _resolve(page, 0, A)
    _quiet(page)
    page.wait_for_selector("#grid-lang-toggle", timeout=WAIT)
    page.click('#grid-lang-toggle .grid-lang-option[aria-label="Show Arabic fields"]')
    visible = """() => ScrapeXDataGrid.find('#grid').getColumns()
        .filter((c) => c.isVisible()).map((c) => c.getField())"""
    shown = page.evaluate(visible)
    assert "product_name_ar" in shown and "product_name" not in shown, shown

    if engine:
        _rebuild(page, lambda: _flip(page, "stripe"))
    else:
        index = _refresh(page)
        _resolve(page, 1, A2)
        assert _outcome(page, index)["ok"] == "drawn"

    shown = page.evaluate(visible)
    assert "product_name_ar" in shown, shown
    assert "product_name" not in shown, f"both name columns show after the rebuild: {shown}"
    assert page.evaluate(
        "() => document.querySelector('.grid-lang-segments').dataset.activeLang") == "ar"
    assert page.evaluate("""() => document.querySelector(
        '#grid-lang-toggle .grid-lang-option[aria-label="Show Arabic fields"]')
        .getAttribute('aria-pressed')""") == "true"


#: A bilingual answer whose English name he hid in Choose Columns: the pair is still
#: declared (both producers gate `bilingual` on the columns the source HAS), but only its
#: Arabic half is in `columns`.
ENGLISH_HIDDEN = dict(A, columns=[c for c in copy.deepcopy(COLUMNS) if c["key"] != "product_name"])


@pytest.mark.parametrize("rebuild", ["engine-page-feature-switch", "host-refresh"])
def test_a_rebuild_keeps_his_sort_on_a_pair_whose_other_half_he_hid(open_grid, rebuild):
    """If this fails, he hides the English name, sorts by the Arabic one, and the next
    grouping, pin, feature switch or activity tick silently throws his sort away: the
    AR|EN re-apply moved the sort to the English column, which is not in the table, and
    a sort on a missing column clears the sort."""
    engine = rebuild == "engine-page-feature-switch"
    page = open_grid(ENGLISH_HIDDEN, host_js="" if engine else DEFERRED)
    if not engine:
        _resolve(page, 0, ENGLISH_HIDDEN)
    _quiet(page)
    page.evaluate("() => ScrapeXDataGrid.find('#grid').setSort('product_name_ar', 'desc')")
    page.wait_for_timeout(150)
    order = """() => ScrapeXDataGrid.find('#grid').getData('active')
        .map((row) => row.offer_id)"""
    sorters = """() => ScrapeXDataGrid.find('#grid').getSorters()
        .map((s) => [s.field, s.dir])"""
    assert page.evaluate(order) == [3, 2, 1]

    if engine:
        _rebuild(page, lambda: _flip(page, "stripe"))
    else:
        index = _refresh(page)
        _resolve(page, 1, ENGLISH_HIDDEN)
        assert _outcome(page, index)["ok"] == "drawn"
        page.wait_for_timeout(150)

    assert page.evaluate(sorters) == [["product_name_ar", "desc"]], (
        "the rebuild cleared his sort")
    assert page.evaluate(order) == [3, 2, 1]
    assert page.errors == []


# ---- an answer with no rows ---------------------------------------------------------------

@pytest.mark.parametrize("case", [
    "first-filtered", "refresh-filtered", "refresh-unfiltered-over-a-table",
    "engine-unfiltered", "refresh-from-no-records",
])
def test_an_answer_with_no_rows(open_grid, case):
    """If this fails, a selection that matches nothing reads 'No records yet.' with every
    control gone, as if the source itself were empty; or an empty answer leaves the
    previous rows on screen; or a source that fills after an empty start has a dead
    Export button and Grid Features that build twice per click."""
    if case == "first-filtered":
        page = open_grid(EMPTY_FILTERED, host_js=INSTANT)
        _landed(page)
        assert _note(page)["text"] != "No records yet.", (
            "a selection that matched nothing read as a source with nothing stored")
        assert page.evaluate("() => (window.ScrapeXDataGrid && ScrapeXDataGrid.find('#grid') ? 1 : 0)") == 1
        page.wait_for_selector("#grid .dg-placeholder", timeout=WAIT)
        assert page.text_content("#grid .dg-placeholder").strip() == (
            "No rows match these filters.")
        assert page.evaluate(
            "() => document.querySelector('#grid-toolbar .split-button').dataset.splitWired"
        ) == "1"
        assert page.evaluate(
            "() => document.getElementById('grid-features').dataset.wired") == "1"
        assert page.evaluate("""() => document.querySelector(
            '#grid .grid-footer-stat .grid-footer-value').textContent""") == "0"
        page.click("#grid-columns-button")
        page.wait_for_selector(".column-chooser", timeout=WAIT)
        return

    if case == "engine-unfiltered":
        page = open_grid(EMPTY_BARE)
        _landed(page)
        assert _note(page) == {"hidden": False, "text": "No records yet."}
        assert page.evaluate("() => (window.ScrapeXDataGrid && ScrapeXDataGrid.find('#grid') ? 1 : 0)") == 0
        assert page.evaluate("() => window.__builds") == 0
        return

    if case == "refresh-from-no-records":
        page = open_grid(EMPTY_UNFILTERED, host_js=INSTANT)
        _landed(page)
        assert _note(page) == {"hidden": False, "text": "No records yet."}
        assert page.evaluate("() => (window.ScrapeXDataGrid && ScrapeXDataGrid.find('#grid') ? 1 : 0)") == 0

        assert _refresh_to(page, A)["ok"] == "drawn"
        assert _offers(page) == [1, 2, 3]
        assert len(_names(page)) == 3
        assert page.evaluate(
            "() => document.querySelector('#grid-toolbar .split-button').dataset.splitWired"
        ) == "1"
        assert page.evaluate(
            "() => document.getElementById('grid-features').dataset.wired") == "1"
        assert _note(page)["hidden"] is True, _note(page)
        builds = page.evaluate("() => window.__builds")
        _rebuild(page, lambda: _flip(page, "stripe"))
        page.wait_for_timeout(150)
        assert page.evaluate("() => window.__builds") == builds + 1
        return

    page = open_grid(A, host_js=INSTANT)
    _quiet(page)
    empty = EMPTY_FILTERED if case == "refresh-filtered" else EMPTY_UNFILTERED
    assert _refresh_to(page, empty)["ok"] == "drawn"
    assert page.evaluate("() => ScrapeXDataGrid.find('#grid').getDataCount()") == 0
    assert page.evaluate("() => document.querySelectorAll('#grid .dg-body .dg-row').length") == 0
    assert page.is_visible("#grid .dg-placeholder")
    assert _note(page)["text"] != "No records yet."


# ---- what a refresh closes -----------------------------------------------------------------

def test_a_refresh_closes_the_record_panel_and_drops_its_late_answer(open_grid):
    """If this fails, the record panel keeps describing a row that is no longer in the
    table, and a slow answer for that row paints into it after he has moved on."""
    page = open_grid(A, host_js=HOLD_OFFERS + DEFERRED)
    _shown(page, A)
    page.evaluate("""() => document.querySelector(
        '#grid .dg-body .dg-row[data-index="0"] .dg-select').click()""")
    page.wait_for_selector("#offer-panel:not([hidden])", timeout=WAIT)
    assert page.evaluate("() => window.__held.length") == 1

    index = _refresh(page)
    _resolve(page, 1, B)
    assert _outcome(page, index)["ok"] == "drawn"

    panel = """() => {
        const p = document.getElementById('offer-panel');
        return {hidden: p.hidden, text: p.textContent, children: p.childElementCount};
    }"""
    assert page.evaluate(panel) == {"hidden": True, "text": "", "children": 0}
    assert page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getSelectedRows().length") == 0
    assert page.evaluate(
        "() => document.querySelectorAll('#grid .grid-footer-stat')[1].hidden") is True

    assert page.evaluate("() => window.__release()") == 1
    page.wait_for_timeout(300)
    assert page.evaluate(panel) == {"hidden": True, "text": "", "children": 0}, (
        "the late record answer painted into a panel the refresh had closed")


def test_a_refresh_clears_a_dataset_tables_selection(open_grid):
    """If this fails, the footer of a contractor table still says 'Selected: 2' after an
    activity tick has replaced every row he had selected."""
    first = _dataset(1)
    page = open_grid(first, host_js=DEFERRED)
    _shown(page, first)
    page.evaluate("""() => ['0', '1'].forEach((i) => document.querySelector(
        `#grid .dg-body .dg-row[data-index="${i}"] .dg-select`).click())""")
    stat = """() => {
        const s = document.querySelectorAll('#grid .grid-footer-stat')[1];
        return {hidden: s.hidden,
                label: s.querySelector('.grid-footer-label').textContent,
                value: s.querySelector('.grid-footer-value').textContent};
    }"""
    assert page.evaluate(stat) == {"hidden": False, "label": "Selected:", "value": "2"}

    index = _refresh(page)
    _resolve(page, 1, _dataset(11))
    assert _outcome(page, index)["ok"] == "drawn"

    assert page.evaluate(stat)["hidden"] is True
    assert page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getSelectedRows().length") == 0


def test_a_narrowing_refresh_clears_a_dataset_selection_its_survivors_included(open_grid):
    """If this fails, a tick keeps rows he had selected because they are still in the
    narrowed answer, which his ruling on #1198 refused: a filter change clears the
    selection, as Unified Logs does, and re-selecting would also steal focus."""
    first = _dataset(1)
    page = open_grid(first, host_js=DEFERRED)
    _shown(page, first)
    page.evaluate("""() => ['0', '1'].forEach((i) => document.querySelector(
        `#grid .dg-body .dg-row[data-index="${i}"] .dg-select`).click())""")
    narrowed = dict(first, rows=first["rows"][1:], total=2, returned=2)
    index = _refresh(page)
    _resolve(page, 1, narrowed)
    assert _outcome(page, index)["ok"] == "drawn"
    page.wait_for_timeout(200)
    assert page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getSelectedRows().length") == 0
    assert page.evaluate(
        "() => document.querySelectorAll('#grid .grid-footer-stat')[1].hidden") is True


def test_a_narrowing_refresh_leaves_the_record_panel_closed(open_grid):
    """If this fails, the record he opened stays open after a tick that kept its row,
    describing a selection the table no longer holds."""
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)
    page.evaluate("""() => document.querySelector(
        '#grid .dg-body .dg-row[data-index="1"] .dg-select').click()""")
    page.wait_for_selector("#offer-panel:not([hidden])", timeout=WAIT)
    index = _refresh(page)
    _resolve(page, 1, _table(A["rows"][1:]))
    assert _outcome(page, index)["ok"] == "drawn"
    page.wait_for_timeout(300)
    assert page.evaluate("() => document.getElementById('offer-panel').hidden") is True
    assert page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getSelectedRows().length") == 0


def test_a_refresh_dismisses_an_open_header_popup(open_grid):
    """If this fails, a Brand filter popup opened before the tick stays on screen over the
    new rows, offering the old rows' values."""
    # THIS PINS THE BEHAVIOUR, AND NO LINE OF draw() DOES IT. The renderer closes its
    # popups when it is destroyed (datagrid.js, destroy), so build()'s destroy closes it.
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)
    assert _popup_values(page, "brand") == ["3M", "AKS"]
    page.wait_for_selector(".dg-popup", timeout=WAIT)

    index = _refresh(page)
    _resolve(page, 1, A2)
    assert _outcome(page, index)["ok"] == "drawn"

    assert page.evaluate(
        "() => document.querySelectorAll('.dg-popup').length") == 0
    assert _popup_values(page, "brand") == ["Hilti", "Makita"]


# ---- only the newest ask paints ---------------------------------------------------------------

@pytest.mark.parametrize("race", [
    "out-of-order", "stale-failure", "overtakes-first-load", "asked-inside-connect",
])
def test_the_newest_request_wins(open_grid, race):
    """If this fails, he ticks two activities quickly and the table ends on the FIRST
    tick's rows, or on the first load's, or says the table could not load while the
    rows of his newest choice are right there."""
    if race == "asked-inside-connect":
        page = open_grid(A, host_js=DEFERRED + "window.__onConnect = () => window.__refresh();")
        page.wait_for_function("() => window.__asks.length === 2", polling=50, timeout=WAIT)
        _resolve(page, 0, A)
        page.wait_for_timeout(300)
        assert page.evaluate("() => window.__builds") == 0, "the first answer was painted"
        _resolve(page, 1, B)
        outcome = _outcome(page, 0)
        assert outcome["ok"] == "drawn", outcome
        assert _offers(page) == [4, 5]
        assert page.evaluate("() => window.__builds") == 1
        assert page.errors == []
        assert _uncaught(page) == []
        return

    if race == "overtakes-first-load":
        page = open_grid(A, host_js=DEFERRED)
        page.wait_for_function("() => window.__asks.length === 1 && !!window.__grid",
                               polling=50, timeout=WAIT)
        index = _refresh(page)
        _resolve(page, 1, B)
        assert _outcome(page, index)["ok"] == "drawn"
        _resolve(page, 0, A)
        page.wait_for_timeout(300)
        assert _offers(page) == [4, 5], "the first load's late answer replaced the refresh"
        assert _names(page) == ["Item 4", "Item 5"]
        assert _note(page)["text"] == "Loaded 2 of 9; filters search only what is loaded"
        assert page.errors == []
        return

    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)
    first = _refresh(page)
    second = _refresh(page)
    # Read, not waited for: by the next evaluate the overtaken ask has settled, or it
    # has not settled at all.
    assert (page.evaluate("(i) => window.__outcomes[i]", first) or {}).get("ok") == (
        "superseded"), "the overtaken ask did not settle the moment the newer one started"
    _resolve(page, 2, C)
    newest = _outcome(page, second)
    if race == "out-of-order":
        _resolve(page, 1, B)
    else:
        _reject(page, 1, "'late'")
    page.wait_for_timeout(300)

    overtaken = _outcome(page, first)
    assert overtaken["ok"] == "superseded", overtaken
    assert overtaken["rows"] is None and overtaken["frozen"] is True, overtaken
    assert "err" not in overtaken, overtaken
    assert (newest["ok"], newest["rows"], newest["frozen"]) == ("drawn", 1, True), newest
    assert _offers(page) == [6]
    assert _names(page) == ["Item 6"]
    assert "Could not load" not in _note(page)["text"]
    assert page.errors == []
    assert _uncaught(page) == []


def test_a_first_load_that_fails_after_a_refresh_drew_paints_nothing(open_grid):
    """If this fails, the extension aborts the first load when he ticks (its loader may),
    the tick's rows are drawn, and then the aborted first load writes 'Could not load
    the table: aborted' over a table that loaded."""
    page = open_grid(A, host_js=DEFERRED)
    page.wait_for_function("() => window.__asks.length === 1 && !!window.__grid",
                           polling=50, timeout=WAIT)
    index = _refresh(page)
    _resolve(page, 1, B)
    assert _outcome(page, index)["ok"] == "drawn"
    _reject(page, 0, "new Error('aborted')")
    page.wait_for_timeout(300)
    assert _offers(page) == [4, 5]
    assert _note(page) == {"hidden": False,
                           "text": "Loaded 2 of 9; filters search only what is loaded"}
    assert page.errors == []
    assert _uncaught(page) == []


def test_an_answer_overtaken_inside_a_build_gap_paints_nothing(open_grid):
    """If this fails, an answer that arrived while the table was being rebuilt, and was
    then overtaken by a newer tick, still builds its rows once the build finishes."""
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)
    page.wait_for_timeout(300)
    seen = page.evaluate("""async (p) => {
        const box = document.querySelector('[data-feature="stripe"]');
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', {bubbles: true}));
        const first = window.__refresh();
        window.__asks[1].resolve(p);
        for (let k = 0; k < 30; k++) await Promise.resolve();
        const pendingBuild = !window.__tables[window.__tables.length - 1].built;
        const second = window.__refresh();
        return {first, second, pendingBuild, builds: window.__builds};
    }""", B)
    assert seen["pendingBuild"] is True, "the race did not happen inside the build gap"
    _quiet(page)
    page.wait_for_timeout(300)
    assert _outcome(page, seen["first"])["ok"] == "superseded"
    assert page.evaluate("() => window.__builds") == 2, (
        "the overtaken answer built a table of its own")
    assert _offers(page) == [1, 2, 3]
    assert page.errors == []


@pytest.mark.parametrize("stored,path", [
    (None, "/api/table/TESTSRC"),
    ("on", "/api/table/TESTSRC?fold=1"),
    ("off", "/api/table/TESTSRC?fold=0"),
], ids=["no-fold-choice", "fold-on", "fold-off"])
def test_a_refresh_asks_the_loader_at_once_for_the_first_loads_path(open_grid, stored, path):
    """If this fails, a tick asks the host for a different table than the page first
    loaded (his ALL/ONE choice lost), or asks only on a later turn, after the dim."""
    remember = ("" if stored is None else
                f"localStorage.setItem('scrapex-fold-variants-TESTSRC', '{stored}');")
    page = open_grid(A, host_js=remember + DEFERRED)
    _shown(page, A)

    same_turn = page.evaluate("""() => {
        const before = window.__asks.length;
        window.__refresh();
        return {asked: window.__asks.length - before,
                busy: document.querySelector('[data-grid-viewport]').getAttribute('aria-busy')};
    }""")

    assert same_turn == {"asked": 1, "busy": "true"}, same_turn
    assert page.evaluate("() => window.__asks.map((a) => a.path)") == [path, path]


# ---- a loader that cannot answer ---------------------------------------------------------------

NOT_A_TABLE = "Could not load the table: the answer is not a table"


@pytest.mark.parametrize("loader,note", [
    ("() => { throw new Error('the host broke'); }", "Could not load the table: the host broke"),
    ("() => 42", NOT_A_TABLE),
    ("() => window.__payload", None),
    ("() => Promise.resolve(undefined)", NOT_A_TABLE),
    ("() => Promise.resolve({rows: 'x', columns: []})", NOT_A_TABLE),
    ("() => Promise.resolve(Object.assign({}, window.__payload, {rows: [null]}))",
     NOT_A_TABLE),
    ("() => Promise.resolve(Object.assign({}, window.__payload,"
     " {columns: [{label: 'Price'}]}))", NOT_A_TABLE),
    # Every row and every column is read, not the first of each (gate pass 1 on #1240).
    ("() => Promise.resolve(Object.assign({}, window.__payload,"
     " {rows: window.__payload.rows.concat([null])}))", NOT_A_TABLE),
    ("() => Promise.resolve(Object.assign({}, window.__payload, {rows: [42]}))", NOT_A_TABLE),
    ("() => Promise.resolve(Object.assign({}, window.__payload, {columns: 'x'}))", NOT_A_TABLE),
    ("() => Promise.resolve(Object.assign({}, window.__payload,"
     " {columns: window.__payload.columns.concat([{label: 'x'}])}))", NOT_A_TABLE),
    ("() => Promise.resolve(Object.assign({}, window.__payload, {columns: [null]}))",
     NOT_A_TABLE),
    ("() => Promise.reject('offline')", "Could not load the table: offline"),
    ("() => Promise.reject()", "Could not load the table: the loader gave no reason"),
], ids=["throws", "answers-a-number", "answers-the-table-itself", "resolves-nothing",
        "rows-not-a-list", "a-row-that-is-null", "a-column-with-no-key",
        "a-null-row-after-good-ones", "a-row-that-is-a-number", "columns-not-a-list",
        "a-keyless-column-after-good-ones", "a-column-that-is-null",
        "rejects-a-string", "rejects-with-no-reason"])
def test_a_loader_that_cannot_answer_a_table_is_said_on_the_page(open_grid, loader, note):
    """If this fails, a host that breaks leaves him an empty page with no sentence, or a
    raw 'TypeError: ... is not a function', or 'Could not load the table: undefined'."""
    page = open_grid(A, host_js=f"window.ScrapeXGridHost = {{loadTable: {loader}}};")
    _landed(page)
    assert page.errors == []
    assert _uncaught(page) == []
    if note is None:
        page.wait_for_function(
            "() => document.querySelectorAll('#grid .dg-body .dg-row').length === 3",
            polling=50, timeout=WAIT)
        assert _offers(page) == [1, 2, 3]
        assert _note(page)["hidden"] is True
    else:
        assert _note(page) == {"hidden": False, "text": note}
        assert page.evaluate("() => (window.ScrapeXDataGrid && ScrapeXDataGrid.find('#grid') ? 1 : 0)") == 0


def test_a_refresh_whose_loader_throws_returns_a_rejected_promise(open_grid):
    """If this fails, a host whose loader throws on a tick either breaks the page with an
    uncaught error or leaves the grid dimmed for ever with the host never told."""
    page = open_grid(A, host_js=INSTANT)
    _quiet(page)
    page.evaluate("() => { window.__loader = () => { throw new Error('the host broke'); }; }")

    outcome = _outcome(page, _refresh(page))

    assert "threw" not in outcome, f"refresh() threw synchronously: {outcome}"
    assert outcome["thenable"] is True
    assert (outcome["err"], outcome["isError"], outcome["busy"]) == (
        "the host broke", True, None), outcome
    assert _offers(page) == [1, 2, 3]
    assert "Could not load" not in _note(page)["text"]
    assert page.evaluate(
        "() => document.querySelector('[data-grid-viewport]').hasAttribute('aria-busy')"
    ) is False
    assert page.errors == []
    assert _uncaught(page) == []


@pytest.mark.parametrize("failure,message", [
    ("rejects", "engine went away"),
    ("not-a-table", "the answer is not a table"),
    ("rejects-with-no-reason", "the loader gave no reason"),
], ids=["rejects", "not-a-table", "rejects-with-no-reason"])
def test_a_failed_refresh_keeps_the_rows_and_tells_only_the_host(open_grid, failure, message):
    """If this fails, one dropped request empties the rows he was reading, or writes an
    error under a table that is still perfectly good, or leaves the grid dimmed."""
    page = open_grid(A, host_js=DEFERRED)
    _shown(page, A)

    index = _refresh(page)
    if failure == "rejects":
        _reject(page, 1, "new Error('engine went away')")
    elif failure == "not-a-table":
        _resolve(page, 1, {"columns": A["columns"]})
    else:
        _reject(page, 1, "")
    outcome = _outcome(page, index)

    assert (outcome["err"], outcome["isError"], outcome["busy"]) == (message, True, None), (
        outcome)
    assert _offers(page) == [1, 2, 3]
    assert _names(page) == ["Item 1", "Item 2", "Item 3"]
    assert "Could not load" not in _note(page)["text"]
    assert _popup_values(page, "brand") == ["3M", "AKS"], (
        "the filter popup reads a payload the failed answer replaced")
    assert page.errors == []
    assert _uncaught(page) == []


def test_a_failed_refresh_with_no_table_says_so_on_the_page(open_grid):
    """If this fails, a source that read 'No records yet.' keeps saying so after the
    engine stopped answering, and he has no way to tell the two apart."""
    page = open_grid(EMPTY_UNFILTERED, host_js=INSTANT)
    _landed(page)
    assert _note(page) == {"hidden": False, "text": "No records yet."}
    page.evaluate(
        "() => { window.__loader = () => Promise.reject(new Error('engine went away')); }")

    outcome = _outcome(page, _refresh(page))

    assert outcome["err"] == "engine went away", outcome
    assert _note(page) == {"hidden": False,
                           "text": "Could not load the table: engine went away"}


# ---- the dim ------------------------------------------------------------------------------------

@pytest.mark.parametrize("layout", ["viewport", "no-viewport"])
def test_the_grid_is_dimmed_and_busy_until_the_newest_rows_are_drawn(open_grid, layout):
    """If this fails, the table looks finished while an answer is still coming, or goes
    back to full strength when the first of two ticks answers, or pulls the keyboard
    focus away from the activity he just ticked."""
    unmark = ("" if layout == "viewport" else
              "document.querySelector('[data-grid-viewport]')"
              ".removeAttribute('data-grid-viewport');")
    page = open_grid(A, host_js=unmark + DEFERRED)
    _shown(page, A)
    selector = "[data-grid-viewport]" if layout == "viewport" else "#grid"
    page.evaluate("() => document.getElementById('activity-tick').focus()")
    look = """(selector) => {
        const host = document.querySelector(selector);
        return {busy: host.getAttribute('aria-busy'), opacity: getComputedStyle(host).opacity,
                focus: document.activeElement && document.activeElement.id};
    }"""

    first = _refresh(page)
    assert page.evaluate(look, selector) == {"busy": "true", "opacity": "0.6",
                                             "focus": "activity-tick"}
    assert _names(page) == ["Item 1", "Item 2", "Item 3"], "the old rows left before the new"
    if layout == "viewport":
        assert page.evaluate("() => document.getElementById('grid').hasAttribute('aria-busy')"
                             ) is False, "the mark belongs on the viewport, not the grid's #grid"

    second = _refresh(page)
    _resolve(page, 1, B)
    page.wait_for_timeout(200)
    assert page.evaluate(look, selector) == {"busy": "true", "opacity": "0.6",
                                             "focus": "activity-tick"}
    overtaken = _outcome(page, first)
    assert (overtaken["ok"], overtaken["busy"]) == ("superseded", "true"), overtaken

    _resolve(page, 2, C)
    newest = _outcome(page, second)
    assert (newest["ok"], newest["busy"], newest["drawn"]) == ("drawn", None, ["Item 6"]), (
        newest)
    assert page.evaluate(look, selector) == {"busy": None, "opacity": "1",
                                             "focus": "activity-tick"}


# ---- the races inside the grid's own build ---------------------------------------------------------

def test_a_refresh_waits_for_a_table_still_being_built(open_grid):
    """If this fails, a tick that lands while a feature switch is still building the table
    loses his sort and leaves an orphan table watching #grid for ever (one more per
    collision, each redrawing on every resize)."""
    page = open_grid(A, host_js=INSTANT)
    _quiet(page)
    page.wait_for_timeout(300)      # past the size observer's first redraw
    observers = page.evaluate("() => window.__gridObservers")
    assert observers >= 1, "the grid watches its own size, so one observer at least"
    page.evaluate("() => ScrapeXDataGrid.find('#grid').setSort('price', 'desc')")

    state = page.evaluate("""async (next) => {
        const box = document.querySelector('[data-feature="stripe"]');
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', {bubbles: true}));
        window.__next = next;
        const outcome = await window.__grid.refresh();
        return outcome.state;
    }""", A2)
    _quiet(page)
    page.wait_for_timeout(150)

    assert state == "drawn"
    assert page.evaluate(
        "() => ScrapeXDataGrid.find('#grid').getSorters().map((s) => s.field + ':' + s.dir)"
    ) == ["price:desc"]
    assert _offers(page) == [7, 8, 9]
    assert page.evaluate("() => window.__gridObservers") == observers, (
        "a replaced table left an observer watching a grid that is gone")
    assert page.errors == []
    assert _uncaught(page) == []


def test_a_rebuild_inside_a_refreshs_build_gap_is_drawn_before_the_refresh_resolves(open_grid):
    """If this fails, a feature switch pressed in the instant a tick is being drawn leaves
    the host told 'drawn' over an empty grid, or the replaced table filters the one that
    replaced it before it exists."""
    page = open_grid(A, host_js=INSTANT)
    _quiet(page)
    page.wait_for_timeout(300)      # past the size observer's first redraw

    seen = page.evaluate("""async (next) => {
        const mount = document.getElementById('grid');
        const box = document.querySelector('[data-feature="stripe"]');
        // The gap: the refresh's table is drawn and has not yet announced its build.
        const drawnAnew = (records) => records.some((record) => [...record.addedNodes]
          .some((node) => node.classList && node.classList.contains('dg-scroller')));
        const watcher = new MutationObserver((records) => {
          if (!drawnAnew(records)) return;
          watcher.disconnect();
          box.checked = !box.checked;
          box.dispatchEvent(new Event('change', {bubbles: true}));
        });
        watcher.observe(mount, {childList: true});
        window.__next = next;
        const outcome = await window.__grid.refresh();
        return {
          state: outcome.state,
          rows: document.querySelectorAll('#grid .dg-body .dg-row').length,
          striped: mount.classList.contains('striped'),
          tables: (window.ScrapeXDataGrid && ScrapeXDataGrid.find('#grid') ? 1 : 0),
          flipped: box.checked,
        };
    }""", A2)

    assert seen == {"state": "drawn", "rows": 3, "striped": True, "tables": 1,
                    "flipped": True}, seen
    assert page.errors == []


def test_a_redraw_queued_by_the_replaced_table_leaves_the_new_one_alone(open_grid):
    """If this fails, the table a tick replaced reaches into its replacement before that
    one is built: a redraw it queued runs against a grid that is no longer its own."""
    page = open_grid(A, host_js=HOLD_FRAMES + INSTANT)
    _quiet(page)
    page.wait_for_timeout(300)      # past the size observer's first redraw
    assert page.evaluate("() => window.__rafs.length") >= 1, (
        "the first table queued no frame, so there is nothing to race")

    seen = page.evaluate("""async (next) => {
        const mount = document.getElementById('grid');
        let flushed = 0;
        // The moment the replacement is drawn, the replaced table's frames run.
        const drawnAnew = (records) => records.some((record) => [...record.addedNodes]
          .some((node) => node.classList && node.classList.contains('dg-scroller')));
        const watcher = new MutationObserver((records) => {
          if (!drawnAnew(records)) return;
          watcher.disconnect();
          const queued = window.__rafs.splice(0);
          flushed = queued.length;
          queued.forEach((callback) => callback(performance.now()));
        });
        watcher.observe(mount, {childList: true});
        window.__next = next;
        const outcome = await window.__grid.refresh();
        return {state: outcome.state, flushed};
    }""", B)

    assert seen["state"] == "drawn", seen
    assert seen["flushed"] >= 1, seen
    assert _offers(page) == [4, 5]
    assert page.errors == []


# ---- who is handed a refresh -------------------------------------------------------------------------

#: Every place on window a refresh could hide: a property named so, or anything holding one.
#: timezone.js's `ScrapeXTime.refresh` (its pullRemote) is on the page before grid.js
#: runs, so the question is what grid.js ADDS, and the answer is compared with the
#: snapshot taken just before it, holder by holder and function by function.
LEAKS = """() => Object.getOwnPropertyNames(window).filter((name) => {
    if (name === 'refresh') return true;
    let value;
    try { value = window[name]; } catch (err) { return false; }
    return value !== null && (typeof value === 'object' || typeof value === 'function')
      && typeof value.refresh === 'function';
})"""
SNAPSHOT = f"""
window.__leaksBefore = ({LEAKS})();
window.__refreshesBefore = window.__leaksBefore.map((name) => window[name].refresh);
"""


@pytest.mark.parametrize("host_js", [
    INSTANT,
    "",
    f"window.ScrapeXGridHost = {{base: {json.dumps(ENGINE)}}};",
    "document.body.insertAdjacentHTML('beforeend', '<div id=\"ScrapeXGridHost\"></div>');",
], ids=["host-connect", "no-host", "base-only", "clobbered-by-an-element"])
def test_the_host_is_handed_one_frozen_refresh_and_the_engines_page_none(open_grid, host_js):
    """If this fails, the engine's own page grows a refresh any script can call, or the
    host is handed a handle it can rewrite, or is handed two."""
    page = open_grid(A, host_js=host_js + SNAPSHOT)
    page.wait_for_function("() => document.querySelectorAll('#grid .dg-body .dg-row').length",
                           polling=50, timeout=WAIT)
    page.wait_for_timeout(100)

    if host_js == INSTANT:
        assert page.evaluate("() => window.__connects") == 1
        assert page.evaluate("() => Object.keys(window.__grid)") == ["refresh"]
        assert page.evaluate("() => Object.isFrozen(window.__grid)") is True
        assert page.evaluate("() => window.__loads") == ["/api/table/TESTSRC"], (
            "connecting asked for the table again")
        return

    before = page.evaluate("() => window.__leaksBefore")
    assert page.evaluate(LEAKS) == before, "a refresh was put on window"
    assert page.evaluate("""() => window.__leaksBefore.every(
        (name, i) => window[name].refresh === window.__refreshesBefore[i])""") is True, (
        f"a refresh already on the page was replaced: {before}")
    tables = [r["path"] for r in page.evaluate("() => window.__requests")
              if "/api/table/" in r["path"]]
    assert len(tables) == 1, tables
    assert page.errors == []
