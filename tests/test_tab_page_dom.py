"""The Data page, RENDERED — the only kind of test that could have caught it.

THE DEFECT THIS FILE EXISTS FOR. The page read the backend generation before
`backendBase()` had resolved the address; resolving it bumped the generation;
the freshness guard then decided a different engine was authoritative and
returned without painting. EVERY FIRST LOAD did that — "Reading…" for ever, in
production, for everyone.

2,460 engine tests and 398 extension tests were green on it. They could not have
been otherwise: every one of them is static, or drives a pure function. Nothing
had ever put the page in a browser and looked.

WHAT THESE TESTS ARE FOR, so the file does not sprawl. They assert what only a
rendered page can settle: that it paints at all, that the ordering of its awaits
is right, and that its own sentences reach the screen. Column labels, formatting
and the payload's arithmetic are covered where they belong — pure, and without a
browser, in extension/tests/datatable.test.mjs.
"""
from __future__ import annotations

import inspect
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# Guards the extension: this file reads extension/ sources, so a change there
# must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

pytest.importorskip("playwright", reason="needs the browser extra")
from playwright.sync_api import sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tabpage_harness as harness  # noqa: E402

#: Shaped like `/api/table`'s real answer, small enough to read. The columns and
#: their order are the payload's, which is the contract this page relies on.
PAYLOAD = {
    "source_key": "SAMEHGABRIEL",
    "columns": [{"key": "product_name_ar", "label": "Product name (AR)"},
                {"key": "price", "label": "Price"},
                {"key": "currency", "label": "Currency"}],
    "rows": [{"offer_id": 1, "product_name_ar": "سلك نحاس شعر 1 مم",
              "price": "120.00", "currency": "EGP"},
             {"offer_id": 2, "product_name_ar": "كابل مسلح", "price": "340.50",
              "currency": "EGP"}],
    "total": 2, "returned": 2, "truncated": False,
    "folded": False, "foldable": True, "bilingual": True,
    "tax_states": {}, "tree": {}, "moved_to_details": [],
}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


#: What a page looks like once its first load has come to something.
SETTLED = """() => {
  const note = document.getElementById('grid-note');
  return document.querySelector('.tabulator-row')
    || document.getElementById('data-blocked').textContent.trim()
    || (note && !note.hidden && !/Loading/.test(note.textContent));
}"""


@pytest.fixture()
def open_data(browser, tmp_path):
    """Open the Data page against a stubbed engine and return the live page."""
    pages = []

    def opener(payload=None, *, source="SAMEHGABRIEL", query="", before="", **stub_kwargs):
        # `before` runs after the stub and before any of the page's scripts.
        page_file = harness.build_data_page(
            tmp_path,
            harness.stub(PAYLOAD if payload is None else payload, **stub_kwargs) + before,
            name=f"data{len(pages)}.html")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # THE FENCE (#1264). The stub answers `fetch` alone. Anything else that
        # leaves the built page (a navigation, a link, an image) is aborted here
        # and recorded, so no test can reach an engine running on this machine.
        fenced: list[str] = []

        def fence(route):
            if route.request.url.startswith("file:"):
                route.continue_()
            else:
                fenced.append(route.request.url)
                route.abort()

        page.route("**/*", fence)
        # The source rides in the address, exactly as it does when the panel
        # opens this page. A file:// URL carries a query string fine.
        page.goto(page_file.as_uri() + (f"?source={source}" if source else "") + query)
        # SETTLED, NOT TIMED: a drawn row, the page's own red line, or the grid's
        # note once it says more than that it is loading. The taxonomy is asked
        # beside the table, so its answer is given the same chance to land.
        page.wait_for_function(SETTLED, timeout=10_000)
        page.wait_for_timeout(100)
        page.js_errors = errors
        page.fenced = fenced
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def test_the_first_load_paints(open_data):
    """THE REGRESSION. It failed exactly here, and silently: no exception, no
    console error, nothing in the DOM but the word "Reading…".

    A page that reports its own staleness before it has any state to be stale
    against will always abort itself, and only a rendered page can tell."""
    page = open_data()

    assert page.locator(".tabulator-row").count() == 2, (
        "the page never got past its own freshness guard — this is the defect "
        "of 2026-08-15, where the generation was read before backendBase() had "
        "resolved the address that creates it")
    assert page.locator("#data-blocked").inner_text() == ""
    assert page.js_errors == [], f"the page threw: {page.js_errors}"


def test_it_draws_the_payload_it_was_given(open_data):
    page = open_data()

    assert page.locator("#data-source").inner_text() == "SAMEHGABRIEL"
    assert page.title() == "SAMEHGABRIEL — ScrapeX"
    # Inside the closed Grid Features menu, so read as text rather than as seen.
    assert page.locator("#data-features-scope").text_content() == "Saved for SAMEHGABRIEL"
    # The grid's own row-selection column comes first, and has no title.
    assert [h.strip() for h in page.locator(".tabulator-col-title").all_inner_texts()] \
        == ["", "Product name (AR)", "Price", "Currency"]
    # Nothing narrowed this table, so the status line has nothing to say; the row
    # count is in the grid's own footer.
    assert page.locator("#data-summary").inner_text() == ""


#: What `/api/table/contractors` really answers, trimmed to three columns. Taken
#: from a live payload, and the two differences from a price payload are the whole
#: reason this test exists: no `offer_id` on a row, and `bilingual` is a MAP of
#: field pairs rather than `true`.
DATASET_PAYLOAD = {
    "source_key": "contractors",
    "columns": [{"key": "contractor_id", "label": "Contractor id"},
                {"key": "company_name", "label": "Company name"},
                {"key": "membership_level", "label": "Membership level"}],
    "rows": [{"contractor_id": "17304", "company_name": "شركة المقاولات",
              "membership_level": "الدرجة الأولى"},
             {"contractor_id": "17305", "company_name": "Second Contracting Co",
              "membership_level": "Grade one"}],
    "total": 2, "returned": 2, "truncated": False,
    "folded": False, "foldable": False, "bilingual": {},
    "tax_states": {}, "tree": {}, "moved_to_details": [],
}


def test_it_draws_a_dataset_and_not_only_a_price_table(open_data):
    """THE DESTINATION OF THE ONE ACTION A DATASET CARD OFFERS.

    `Open the data table` is the single entry on a contractor card's menu, and it
    is there because `/api/table/{key}` resolves a dataset key — measured in
    `tests/test_a_dataset_card_offers_what_works.py`. That proves the ROUTE. This
    proves the PAGE, which is a different claim and the one that decides whether
    the menu entry is honest: a 200 that renders an empty grid is the same dead end
    as a 404, one step further along.

    THE ROW SHAPE IS THE RISK, and it is why a price payload could not have caught
    this. `data.js` hands Tabulator `index: "offer_id"`, and a dataset row has no
    `offer_id` at all — every row would share the same undefined index. It draws,
    measured; if a future grid option starts requiring that index, this is where it
    goes red instead of on his screen.
    """
    page = open_data(DATASET_PAYLOAD, source="contractors")

    assert page.js_errors == [], f"the page threw on a dataset: {page.js_errors}"
    assert page.locator("#data-source").inner_text() == "contractors"
    assert page.locator(".tabulator-row").count() == 2, (
        "the dataset's rows did not reach the grid")
    assert [h.strip() for h in page.locator(".tabulator-col-title").all_inner_texts()] \
        == ["", "Contractor id", "Company name", "Membership level"]
    # The Arabic value arrives as text, in a grid whose column labels are English.
    names = page.locator(".tabulator-cell[tabulator-field=company_name]").all_inner_texts()
    assert "شركة المقاولات" in names[0], names


def test_scraped_text_reaches_the_screen_as_TEXT(open_data):
    """Every value here came off somebody else's website. A name that arrived as
    markup and left as markup is the whole reason the formatter is plaintext."""
    hostile = {**PAYLOAD, "rows": [
        {"offer_id": 1, "product_name_ar": "<img src=x onerror=alert(1)>",
         "price": "1", "currency": "EGP"}]}
    page = open_data(hostile)
    cell = page.locator(".tabulator-cell[tabulator-field=product_name_ar]").first

    assert cell.locator("img").count() == 0, (
        "a product name became an element — the grid is interpreting markup")
    assert "<img" in cell.inner_text()
    assert page.js_errors == [], page.js_errors


def test_arabic_keeps_its_own_direction(open_data):
    """An Arabic name in a left-to-right table drags the punctuation around it
    unless the cell is isolated. The rule is stated in CSS; this is what proves
    it reaches the rendered cell."""
    page = open_data(DATASET_PAYLOAD, source="contractors")
    direction = page.evaluate(
        "getComputedStyle(document.querySelector('.tabulator-cell[tabulator-field=company_name]'))"
        ".unicodeBidi")
    assert direction == "plaintext", f"cells render as {direction!r}"


def test_a_prefix_says_it_is_one(open_data):
    """The bound exists so a partial table is never read as a whole one."""
    page = open_data({**PAYLOAD, "total": 91234, "returned": 2, "truncated": True})

    note = page.locator("#grid-note")
    assert note.is_visible(), "a prefix was drawn with nothing saying it is one"
    assert "Loaded 2 of 91,234" in note.inner_text(), note.inner_text()


def test_the_fold_switch_is_the_grids_and_only_where_there_is_something_to_fold(open_data):
    """One control decides one question: the grid's ALL|ONE, as on the engine's page,
    drawn only for a source whose variants share a price."""
    assert open_data({**PAYLOAD, "foldable": False}).locator("#grid-fold-toggle").count() == 0
    assert open_data({**PAYLOAD, "foldable": True}).locator("#grid-fold-toggle").count() == 1


def test_a_stopped_engine_is_named_rather_than_left_blank(open_data):
    """The failure an owner actually meets. A page that shows nothing and says
    nothing sends them looking at the data for a fault that is in the engine."""
    page = open_data(fail="Failed to fetch")

    note = page.locator("#grid-note")
    assert note.is_visible()
    assert note.inner_text().startswith(
        "Could not load the table: The engine did not answer: Failed to fetch."), note.inner_text()
    assert "Run screen" in note.inner_text()
    # ONE RED LINE, not two: the page's own stays for faults the grid cannot report.
    assert page.locator("#data-blocked").inner_text() == ""


def test_a_table_the_engine_does_not_have_is_not_called_a_stopped_engine(open_data):
    """A 404 is an answer. Telling him to start an engine that answered sends him to
    restart something that is running perfectly well."""
    page = open_data(status=404, source="NOSUCH")

    said = page.locator("#grid-note").inner_text()
    assert said == "Could not load the table: The engine has no table named NOSUCH.", said


#: `/api/taxonomy/{key}` as the engine really answers it, cut down to what a reader
#: can hold. The numbers are his: `Specialized` 6,564 and `Buildings` 7,634 of 17,811
#: contractors, and the undeclared node at 9,001 -- larger than either.
TAXONOMY = {
    "dataset_key": "contractor_profiles",
    "groups": [{
        "group_key": "interests",
        "scheme": {"scheme_id": 1, "name": "Interests", "name_ar": "الأنشطة"},
        "undeclared": {"node_id": 111, "level": 1, "name": "No Data",
                       "name_ar": "لا يوجد بيانات", "held": 9001},
        "nodes": [
            {"node_id": 1, "parent_node_id": None, "level": 1,
             "name": "Buildings", "name_ar": "تشييد المباني", "held": 7634},
            {"node_id": 11, "parent_node_id": None, "level": 1,
             "name": "Specialized", "name_ar": "أنشطة التشييد المتخصصة", "held": 6564},
            {"node_id": 14, "parent_node_id": 11, "level": 2,
             "name": "Electrical", "name_ar": "التركيبات الكهربائية", "held": 4578},
        ],
    }],
}


def test_the_activity_filter_draws_the_tree_it_was_served(open_data):
    """ISSUE 543, AND THE FIRST SURFACE THAT READS 398,933 STORED MEMBERSHIPS.

    `taxonomy.memberships` had no caller in `scrapex/` outside its own tests, so a
    contractor's 22.9 activities were invisible on every screen he has.
    """
    page = open_data(taxonomy=TAXONOMY)

    assert page.locator("#data-activities").is_visible(), (
        "the filter did not appear for a dataset the engine says has a vocabulary")
    assert page.locator("#data-activities-toggle").inner_text() == "الأنشطة", (
        "the control is not named by the scheme the site publishes")
    # THE TREE IS BEHIND ONE CLICK, DELIBERATELY. 214 nodes three levels deep is
    # taller than the screen, and the page's job is the table; what he sees closed is
    # the scheme's own name and the undeclared line. So the guard opens it, which also
    # proves the toggle works rather than assuming it.
    assert page.locator("#data-activities-tree").is_visible() is False
    page.locator("#data-activities-toggle").click()
    assert page.locator("#data-activities-toggle").get_attribute("aria-expanded") == "true"
    boxes = page.locator("#data-activities-tree input[type=checkbox]")
    assert boxes.count() == 3, f"{boxes.count()} node(s) drawn of 3"
    # BIGGEST REAL CATEGORY FIRST, and the undeclared one is not a category at all.
    first = page.locator("#data-activities-tree > ul > li").first
    assert "تشييد المباني" in first.inner_text()
    assert "7,634" in first.inner_text(), (
        "the held count is missing, which is the whole point of the list")
    assert page.js_errors == [], f"the page threw: {page.js_errors}"


def test_the_undeclared_node_is_a_line_and_never_a_category(open_data):
    """HIS RULING, 2026-09-08. The site publishes `No Data` as a level-1 node held by
    9,001 contractors -- larger than its largest real category -- and a filter whose
    biggest entry is a fake category answers a question nobody asked. Kept as a state,
    said in a line, and NOT deleted: 9,001 contractors having declared nothing is a
    fact about them."""
    page = open_data(taxonomy=TAXONOMY)

    said = page.locator("#data-undeclared").inner_text()
    assert "9,001" in said, f"the undeclared count is not on the page: {said!r}"
    tree = page.locator("#data-activities-tree").inner_text()
    assert "No Data" not in tree and "لا يوجد بيانات" not in tree, (
        f"the undeclared node reached the tree as a category: {tree!r}")


def test_ticking_a_node_asks_the_engine_to_narrow_and_says_which_way(open_data):
    """THE SELECTION NARROWS IN SQL. 407,384 memberships beside a 17,811-row table
    would be several times the table itself, so the grid cannot be the filter."""
    page = open_data(taxonomy=TAXONOMY)
    page.locator("#data-activities-toggle").click()
    page.locator("#data-activities-tree input[value='11']").check()
    page.wait_for_function("window.__ASKED__.some((url) => url.includes('nodes=11'))",
                           timeout=5_000)

    asked = page.evaluate("window.__ASKED__")
    narrowed = [one for one in asked if "nodes=11" in one]
    assert narrowed, f"ticking a node asked for nothing narrower: {asked}"
    assert "nodes_mode=any" in narrowed[-1], (
        f"the request does not say which way it combines: {narrowed[-1]}")
    assert page.locator("#data-activities-clear").is_visible(), (
        "a selection is on and there is no way to take it off")
    assert "ANY" in page.locator("#data-activities-mode-label").inner_text(), (
        "the toggle does not say in words what it is doing")


def test_a_source_with_no_vocabulary_is_drawn_no_control(open_data):
    """A button that cannot work is worse than no button. A price source has no
    memberships at all, and the engine answers `groups: []` rather than 404."""
    page = open_data()          # the harness answers `{"groups": []}` by default

    assert not page.locator("#data-activities").is_visible(), (
        "a price table was given an activity filter it can never fill")


def test_a_page_opened_with_no_source_asks_for_one(open_data):
    """It must not ask the engine for `/api/table/` and report the 404 as if the
    engine were down — that sends the owner to restart something that is running
    perfectly well."""
    page = open_data(source="")

    assert "needs a source" in page.locator("#data-blocked").inner_text()
    assert page.evaluate("window.__ASKED__.length") == 0, (
        "the page asked the engine for a table with no source key")
    # Nor does it leave an empty frame, or a "Loading the table…" that never ends.
    assert not page.locator("#data-frame").is_visible()
    assert not page.locator("#grid-note").is_visible()


def test_the_page_asks_for_the_source_it_was_opened_for(open_data):
    page = open_data(source="ALSWEED")
    asked = page.evaluate("window.__ASKED__")

    assert any("/api/table/ALSWEED" in url for url in asked), asked


# ---- the page as the grid's host (#1198) ---------------------------------------
#
# grid.js draws the table; data.js tells it where the engine is, loads the table
# for it with the page's site and activity selection, and asks it to refresh when
# the selection changes. These hold data.js to that.

def _table_asks(page) -> list[str]:
    return [url for url in page.evaluate("window.__ASKED__") if "/api/table/" in url]


_TABLE_ASKS_JS = "window.__ASKED__.filter((url) => url.includes('/api/table/')).length"


def _asks_within(page, action_js: str, ms: int) -> int:
    """Table requests made within `ms` of `action_js`. Kept under the 250 ms settle pause,
    it tells "at once" from "after the pause"."""
    return page.evaluate(f"""async () => {{
        const before = {_TABLE_ASKS_JS};
        {action_js};
        await new Promise((resolve) => setTimeout(resolve, {ms}));
        return {_TABLE_ASKS_JS} - before;
    }}""")


_SET_ALL = ("const s = document.getElementById('data-activities-mode'); s.value = 'all';"
            " s.dispatchEvent(new Event('change'))")


def test_a_selection_in_the_address_is_the_first_table_asked(open_data):
    """If this fails, a reload the grid starts (after Columns, Reset columns or a fold
    change) would drop the activities he had ticked, because a reload keeps only the
    address."""
    page = open_data(taxonomy=TAXONOMY, query="&nodes=11,14&nodes_mode=all")

    first = _table_asks(page)[0]
    assert first.endswith("?nodes=11,14&nodes_mode=all"), first
    assert page.locator("#data-activities-tree").is_visible(), (
        "the tree stayed closed over a selection the address carries")
    assert page.locator("#data-activities-tree input[value='11']").is_checked()
    assert page.locator("#data-activities-tree input[value='14']").is_checked()
    assert page.locator("#data-activities-mode").input_value() == "all"
    assert "ALL" in page.locator("#data-activities-mode-label").inner_text()
    assert page.locator("#data-activities-clear").is_visible()


def test_a_tick_writes_the_address_and_adds_no_back_entry(open_data):
    """If this fails, either the selection would not survive the grid's own reloads,
    or every tick would leave one more page for Back to walk through."""
    page = open_data(taxonomy=TAXONOMY)
    before = page.evaluate("history.length")
    page.locator("#data-activities-toggle").click()
    page.locator("#data-activities-tree input[value='11']").check()

    search = page.evaluate("location.search")
    assert "source=SAMEHGABRIEL" in search and "nodes=11&nodes_mode=any" in search, search
    assert page.evaluate("history.length") == before


def test_quick_ticks_settle_into_one_table_request(open_data):
    """If this fails, four ticks in a row cost four table requests, each redrawing the
    grid, against a table the study measured at up to 2.61 s to its first byte."""
    page = open_data(taxonomy=TAXONOMY)
    page.locator("#data-activities-toggle").click()
    for node in ("1", "11", "14"):
        page.locator(f"#data-activities-tree input[value='{node}']").check()
    page.wait_for_function("window.__ASKED__.some((url) => url.includes('nodes='))",
                           timeout=5_000)
    page.wait_for_timeout(500)

    narrowed = [url for url in _table_asks(page) if "nodes=" in url]
    assert narrowed == [narrowed[0]] and narrowed[0].endswith("?nodes=1,11,14&nodes_mode=any"), (
        _table_asks(page))


def test_the_status_line_says_what_the_filter_left(open_data):
    """If this fails, the rows change under him and nothing says by how much, which is
    how he once read a narrowed table as a dataset that had lost its rows."""
    narrowed = {**DATASET_PAYLOAD, "population": 17811,
                "filtered_by": {"nodes": [11], "mode": "any"}}
    page = open_data(narrowed, source="contractors", taxonomy=TAXONOMY)
    page.locator("#data-activities-toggle").click()
    page.locator("#data-activities-tree input[value='11']").check()
    page.wait_for_function(
        "document.getElementById('data-summary').textContent.includes('of 17,811 rows')",
        timeout=5_000)

    assert page.locator("#data-summary").inner_text() == (
        "2 of 17,811 rows · 1 activity chosen, matching any of them")
    assert page.locator("[data-grid-viewport]").get_attribute("aria-busy") is None


def test_a_refresh_that_fails_keeps_the_rows_and_says_so(open_data):
    """If this fails, a filter the engine could not answer would empty the table, or
    leave the old rows looking like the answer."""
    page = open_data(taxonomy=TAXONOMY, fail_when="nodes=")
    page.locator("#data-activities-toggle").click()
    page.locator("#data-activities-tree input[value='11']").check()
    page.wait_for_function(
        "document.getElementById('data-summary').textContent.startsWith('Could not filter')",
        timeout=5_000)

    said = page.locator("#data-summary").inner_text()
    assert said.startswith("Could not filter: The engine did not answer"), said
    assert said.endswith("The rows below are the last answer drawn."), said
    assert page.locator(".tabulator-row").count() == 2, "the failed refresh emptied the table"
    assert page.js_errors == [], page.js_errors


def test_clear_asks_at_once_and_takes_the_selection_out_of_the_address(open_data):
    """If this fails, Clear would wait out the tick pause, or leave a selection in the
    address that the next reload would put back."""
    page = open_data(taxonomy=TAXONOMY, query="&nodes=11&nodes_mode=any")

    assert _asks_within(page, "document.getElementById('data-activities-clear').click()", 100) == 1
    assert _table_asks(page)[-1].endswith("/api/table/SAMEHGABRIEL"), _table_asks(page)
    assert "nodes" not in page.evaluate("location.search")
    assert not page.locator("#data-activities-clear").is_visible()


def test_reload_asks_the_engine_again_in_place(open_data):
    """If this fails, the one control that shows a crawl's new rows without leaving the
    tab does nothing."""
    page = open_data()
    asked = len(_table_asks(page))
    page.locator("#data-reload").click()

    page.wait_for_function(f"window.__ASKED__.filter((url) => url.includes('/api/table/')).length > {asked}",
                           timeout=2_000)
    page.wait_for_function("!document.querySelector('[data-grid-viewport]').hasAttribute('aria-busy')",
                           timeout=2_000)
    assert page.locator(".tabulator-row").count() == 2
    assert page.locator("#data-summary").inner_text() == ""


def test_excel_goes_to_the_engine_the_page_was_given(open_data):
    """If this fails, the export would ask the extension for /export/…, which it does
    not have, instead of the engine."""
    page = open_data()
    page.locator("[data-split-action=xlsx]").click()
    page.wait_for_timeout(500)

    assert page.fenced == [harness.BACKEND + "/export/SAMEHGABRIEL.xlsx"], page.fenced


def test_a_missing_piece_of_the_grid_is_named_on_the_page(open_data):
    """If this fails, a page whose split button, time zone, icons or library did not
    load would draw no table and say nothing: grid.js returns silently or throws on
    its first line."""
    lose = ("Object.defineProperty(window, 'ScrapeXSplitButton', "
            "{get() { return undefined; }, set() {}, configurable: true});")
    page = open_data(before=lose)

    said = page.locator("#data-blocked").inner_text()
    assert said.startswith("The table cannot start: ScrapeXSplitButton did not load."), said
    assert not _table_asks(page), "a table was asked for a grid that cannot start"
    assert not page.locator("#grid-note").is_visible()

def test_all_with_two_activities_asks_at_once_and_writes_the_address(open_data):
    """If this fails, flipping Any to All would leave the rows matching ANY under a
    label that says ALL, or wait out the tick pause for one decision."""
    page = open_data(taxonomy=TAXONOMY, query="&nodes=1,11&nodes_mode=any")

    assert _asks_within(page, _SET_ALL, 100) == 1
    assert _table_asks(page)[-1].endswith("?nodes=1,11&nodes_mode=all"), _table_asks(page)
    assert "nodes_mode=all" in page.evaluate("location.search")


def test_all_with_one_activity_writes_the_address_and_asks_nothing(open_data):
    """If this fails, flipping Any/All over one activity, the same question either way,
    would spend a table request on an identical answer."""
    page = open_data(taxonomy=TAXONOMY, query="&nodes=11&nodes_mode=any")

    assert _asks_within(page, _SET_ALL, 500) == 0
    assert "nodes_mode=all" in page.evaluate("location.search")


def test_a_selection_in_the_address_says_what_it_left(open_data):
    """If this fails, every reload the grid starts (Columns, Reset columns, fold) would
    land on a narrowed table with nothing saying by how much."""
    narrowed = {**DATASET_PAYLOAD, "population": 17811,
                "filtered_by": {"nodes": [11], "mode": "any"}}
    page = open_data(narrowed, source="contractors", taxonomy=TAXONOMY,
                     query="&nodes=11&nodes_mode=any")

    assert page.locator("#data-summary").inner_text() == (
        "2 of 17,811 rows · 1 activity chosen, matching any of them")


def test_opening_the_page_asks_for_one_table(open_data):
    """If this fails, every first open costs two table requests: connect() asked for a
    refresh that the first load already made. On contractors each is seconds."""
    page = open_data()
    page.wait_for_timeout(500)

    assert len(_table_asks(page)) == 1, _table_asks(page)


#: Every table request after the first answers 400 ms late.
_SLOW_AFTER_FIRST = """(() => {
  const inner = window.fetch;
  let tables = 0;
  window.fetch = async (input, options) => {
    const url = String(input && input.url ? input.url : input);
    if (url.includes('/api/table/') && ++tables > 1) {
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    return inner(input, options);
  };
})();"""


def test_a_superseded_refresh_says_nothing(open_data):
    """If this fails, an ask a newer one overtook blanks the status line while the newer
    one is still on its way."""
    page = open_data(before=_SLOW_AFTER_FIRST)
    said = page.evaluate("""async () => {
        const reload = document.getElementById('data-reload');
        reload.click();
        reload.click();
        await new Promise((resolve) => setTimeout(resolve, 100));
        return document.getElementById('data-summary').textContent;
    }""")

    assert said == "Asking the engine again…", said


#: The first table (the address's selection) answers a second late, and narrowed; Clear,
#: pressed meanwhile, is answered at once and unnarrowed.
_OVERTAKEN_FIRST = """(() => {
  const inner = window.fetch;
  let tables = 0;
  window.fetch = async (input, options) => {
    const url = String(input && input.url ? input.url : input);
    if (!url.includes('/api/table/')) return inner(input, options);
    if (++tables === 1) {
      setTimeout(() => document.getElementById('data-activities-clear').click(), 50);
      await new Promise((resolve) => setTimeout(resolve, 1000));
      return inner(input, options);
    }
    const reply = await inner(input, options);
    const body = await reply.json();
    delete body.filtered_by;
    return new Response(JSON.stringify(body), {status: 200,
      headers: {'Content-Type': 'application/json'}});
  };
})();"""


def test_a_first_table_a_refresh_overtook_does_not_write_the_line(open_data):
    """If this fails, a slow first answer lands after Clear's and writes a narrowed
    count over a table that is no longer narrowed, and it stays there."""
    narrowed = {**DATASET_PAYLOAD, "population": 17811,
                "filtered_by": {"nodes": [11], "mode": "any"}}
    page = open_data(narrowed, source="contractors", taxonomy=TAXONOMY,
                     query="&nodes=11&nodes_mode=any", before=_OVERTAKEN_FIRST)
    page.wait_for_timeout(1500)

    assert len(_table_asks(page)) == 2, _table_asks(page)
    assert page.locator("#data-summary").inner_text() == "", (
        page.locator("#data-summary").inner_text())


def test_a_refresh_with_no_table_on_screen_claims_no_rows(open_data):
    """If this fails, a Reload over a failed first load says "The rows below are the last
    answer drawn" over no rows, and the fault is stated twice."""
    page = open_data(fail="Failed to fetch")
    page.locator("#data-reload").click()
    page.wait_for_function(
        "!document.querySelector('[data-grid-viewport]').hasAttribute('aria-busy')", timeout=5_000)

    assert page.locator(".tabulator-row").count() == 0
    assert page.locator("#data-summary").inner_text() == "", (
        page.locator("#data-summary").inner_text())
    assert page.locator("#grid-note").inner_text().startswith("Could not load the table: ")


def test_a_selection_whose_list_cannot_be_read_can_still_be_cleared(open_data):
    """If this fails, an address's selection narrows the table while the activity list
    fails to load, and the page has no control to take it off and says nothing."""
    page = open_data(taxonomy=TAXONOMY, query="&nodes=11&nodes_mode=any",
                     fail_when="/api/taxonomy/")

    assert page.locator("#data-activities").is_visible()
    assert page.locator("#data-activities-clear").is_visible()
    assert not page.locator("#data-activities-toggle").is_visible()
    said = page.locator("#data-undeclared").inner_text()
    assert "could not be read" in said and "1 chosen" in said, said
    assert _asks_within(page, "document.getElementById('data-activities-clear').click()", 100) == 1
    assert _table_asks(page)[-1].endswith("/api/table/SAMEHGABRIEL"), _table_asks(page)


#: grid.js's script tag, pointed at a file the page does not carry.
_LOSE_GRID = r"""(() => {
  const append = Element.prototype.append;
  Element.prototype.append = function (...nodes) {
    for (const node of nodes) {
      if (node instanceof HTMLScriptElement && /\/grid\.js$/.test(node.src)) node.src = 'no-such-grid.js';
    }
    return append.apply(this, nodes);
  };
})();"""


def test_a_grid_script_that_does_not_load_is_named(open_data):
    """If this fails, a page whose grid.js is missing says "Loading the table…" for ever,
    the same silent first load #194 was."""
    page = open_data(before=_LOSE_GRID)

    assert page.locator("#data-blocked").inner_text() == (
        "The table's script did not load. Reload the page; if it stays, reinstall the extension.")
    assert not page.locator("#grid-note").is_visible()


def test_a_grid_that_runs_without_starting_is_named(open_data):
    """If this fails, a grid.js that returns before it starts (it does so silently when
    it finds no Tabulator it can call) leaves the page saying nothing."""
    not_a_function = ("Object.defineProperty(window, 'Tabulator', "
                      "{get() { return {}; }, set() {}, configurable: true});")
    page = open_data(before=not_a_function)

    assert page.locator("#data-blocked").inner_text() == (
        "The table's script ran but the grid did not start.")


#: chrome.storage answering 300 ms late, as it may in the real extension.
_SLOW_STORAGE = """(() => {
  const get = window.chrome.storage.local.get;
  window.chrome.storage.local.get = async (...args) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    return get(...args);
  };
})();"""


def test_the_first_load_paints_when_storage_answers_slowly(open_data):
    """THE #194 ORDER, HELD ON PURPOSE. The harness's storage answers in a microtask, so
    the taxonomy request activates the backend before grid.js loads and the order of
    `await backendBase()` in start() stops mattering. With storage slow, that order is
    the only thing between the first load and "the engine's address changed"."""
    page = open_data(before=_SLOW_STORAGE)

    assert page.locator(".tabulator-row").count() == 2, page.locator("#grid-note").inner_text()
    assert page.locator("#data-blocked").inner_text() == ""


def test_selecting_a_row_opens_its_record_from_the_engine(open_data):
    """If this fails, the record panel, which grid.js skips without a word when its
    markup is missing, is gone from the Data page."""
    page = open_data(offer={"offer_id": 1, "product_name_ar": "سلك"})
    page.locator(".tabulator-row").first.locator("input[type=checkbox]").check()
    page.wait_for_function("!document.getElementById('offer-panel').hidden", timeout=5_000)

    assert harness.BACKEND + "/api/offer/SAMEHGABRIEL/1" in page.evaluate("window.__ASKED__")


# ---- data.html's copy of the engine page's grid frame ---------------------------
#
# The frame is written twice, in source.html and here, and both change for one reason:
# grid.js gaining or losing a control. grid.js skips a control whose markup is missing
# without a word, so these hold the copy to grid.js and to the engine page.

_ROOT = Path(__file__).resolve().parent.parent
_GRID_JS = (_ROOT / "design" / "grid.js").read_text(encoding="utf-8")
_SOURCE_HTML = (_ROOT / "scrapex" / "webui" / "templates" / "source.html").read_text(encoding="utf-8")
_DATA_HTML = (harness.EXT / "data.html").read_text(encoding="utf-8")


def test_data_html_carries_every_element_grid_js_looks_up():
    """If this fails, grid.js looks for an element the Data page does not have, and the
    control it belongs to is missing there while the engine page keeps it."""
    wanted = set(re.findall(r'getElementById\("([^"]+)"\)', _GRID_JS))
    made_by_the_grid = set(re.findall(r'\.id\s*=\s*"([^"]+)"', _GRID_JS))
    assert len(wanted) >= 9, f"the lookup pattern found only {sorted(wanted)}"
    missing = sorted(i for i in wanted - made_by_the_grid if f'id="{i}"' not in _DATA_HTML)
    assert missing == [], missing


def test_data_html_offers_the_engine_pages_switches_and_planned_list():
    """If this fails, the Data page's Grid Features menu offers a different set of
    switches or planned items from the engine page's, for the same grid."""
    defaults = re.search(r"DEFAULT_FEATURES\s*=\s*\{([^}]*)\}", _GRID_JS).group(1)
    features = set(re.findall(r"(\w+)\s*:", defaults))
    assert features, "DEFAULT_FEATURES was not found in design/grid.js"
    assert set(re.findall(r'data-feature="(\w+)"', _DATA_HTML)) == features
    assert set(re.findall(r'data-feature="(\w+)"', _SOURCE_HTML)) == features

    loop = re.search(r"\{%\s*for feature in \[(.*?)\]\s*%\}", _SOURCE_HTML, re.DOTALL).group(1)
    planned = re.findall(r'"([^"]+)"', loop)
    ours = re.findall(r'<input type="checkbox" disabled> ([^<]+?) <small>Planned</small>', _DATA_HTML)
    assert planned and ours == planned, (ours, planned)


def test_the_stylesheets_load_in_the_engine_pages_order():
    """If this fails, the grid's theme may load before the library it overrides, or the
    page shell after the grid's sheets, and the table stops looking like the engine's."""
    def order(html):
        return [Path(href).name for href in re.findall(r'<link\s+rel="stylesheet"\s+href="([^"?]+)', html)]

    engine = order((_ROOT / "scrapex" / "webui" / "templates" / "base.html").read_text(encoding="utf-8")
                   + _SOURCE_HTML)
    # data.css stands where the engine page loads webui.css.
    ours = ["webui.css" if name == "data.css" else name for name in order(_DATA_HTML)]
    shared = [name for name in engine if name in ours]
    assert len(shared) >= 7, shared
    assert [name for name in ours if name in shared] == shared, (ours, engine)

#: Every table request after the first answers 600 ms late, each answer names the
#: selection it was asked for, and the page records how many requests are open at once
#: and every sentence the status line shows.
_SLOW_AND_COUNTED = """(() => {
  const inner = window.fetch;
  let tables = 0;
  window.__OPEN__ = 0;
  window.__MOST_OPEN__ = 0;
  window.__SAID__ = [];
  new MutationObserver(() => {
    const line = document.getElementById('data-summary');
    if (line) window.__SAID__.push(line.textContent);
  }).observe(document, {subtree: true, childList: true, characterData: true});
  window.fetch = async (input, options) => {
    const url = String(input && input.url ? input.url : input);
    if (!url.includes('/api/table/')) return inner(input, options);
    const later = ++tables > 1;
    if (later) {
      window.__OPEN__ += 1;
      window.__MOST_OPEN__ = Math.max(window.__MOST_OPEN__, window.__OPEN__);
    }
    try {
      if (later) await new Promise((resolve) => setTimeout(resolve, 600));
      const reply = await inner(input, options);
      const body = await reply.json();
      const nodes = new URL(url).searchParams.get('nodes');
      if (nodes) {
        body.filtered_by = {nodes: nodes.split(',').map(Number), mode: 'any'};
        body.population = 17811;
      }
      return new Response(JSON.stringify(body), {status: reply.status,
        headers: {'Content-Type': 'application/json'}});
    } finally {
      if (later) window.__OPEN__ -= 1;
    }
  };
})();"""


def test_ticks_slower_than_the_pause_ask_one_table_at_a_time(open_data):
    """If this fails, ticks more than 250 ms apart each start a whole table while the
    engine still computes the last (#1305). Measured on 17,811 contractors, the newest
    then missed its 5 s deadline behind requests the page had already thrown away."""
    page = open_data(taxonomy=TAXONOMY, before=_SLOW_AND_COUNTED)
    page.locator("#data-activities-toggle").click()
    for node in ("1", "11", "14"):
        page.locator(f"#data-activities-tree input[value='{node}']").check()
        page.wait_for_timeout(350)
    page.wait_for_function("window.__OPEN__ === 0", timeout=5_000)
    page.wait_for_timeout(400)
    page.wait_for_function("window.__OPEN__ === 0", timeout=5_000)

    narrowed = [url for url in _table_asks(page) if "nodes=" in url]
    assert page.evaluate("window.__MOST_OPEN__") == 1, page.evaluate("window.__MOST_OPEN__")
    assert len(narrowed) == 2, narrowed
    assert narrowed[-1].endswith("?nodes=1,11,14&nodes_mode=any"), narrowed
    said = page.evaluate("window.__SAID__")
    assert said[-1] == "2 of 17,811 rows · 3 activities chosen, matching any of them", said
    # The first answer arrived after the third tick, out of date, and said nothing:
    # no line after the third tick names fewer activities.
    third = max(i for i, line in enumerate(said) if "by 3 activities" in line)
    stale = [line for line in said[third:] if "1 activity" in line or "2 activities" in line]
    assert stale == [], said


def test_a_choice_made_while_a_table_is_on_its_way_is_asked_for_when_it_lands(open_data):
    """If this fails, a tick whose pause ends while a table is still on its way is
    dropped: the grid keeps the rows of the earlier choice under a line that names the
    newer one, and nothing asks again."""
    page = open_data(taxonomy=TAXONOMY, before=_SLOW_AND_COUNTED)
    page.locator("#data-activities-toggle").click()
    page.locator("#data-activities-tree input[value='1']").check()
    page.wait_for_timeout(350)
    page.locator("#data-activities-tree input[value='11']").check()
    page.wait_for_timeout(1800)
    page.wait_for_function("window.__OPEN__ === 0", timeout=5_000)

    narrowed = [url for url in _table_asks(page) if "nodes=" in url]
    assert len(narrowed) == 2 and narrowed[-1].endswith("?nodes=1,11&nodes_mode=any"), narrowed
    assert page.evaluate("window.__MOST_OPEN__") == 1
    assert page.locator("#data-summary").inner_text() == (
        "2 of 17,811 rows · 2 activities chosen, matching any of them")

# ---- the harness itself (#1198) ---------------------------------------------------------
#
# The Data page is about to run the engine's own grid, which loads stylesheets and
# scripts this page does not load today. A harness that injected its own list would test
# a page nobody ships, so it builds the page from data.html's tags and answers only the
# engine. These hold it to that.

def _linked_sheets() -> list[str]:
    html = (harness.EXT / "data.html").read_text(encoding="utf-8")
    return harness._SHEET.findall(html)


#: One effect per stylesheet data.html links: a computed style that sheet sets and no
#: other does, each measured by building the page without it. The keys must equal the
#: page's links, so a sheet the page stops linking, or one it starts linking with no
#: effect named here, fails.
SHEET_EFFECTS = {
    "tokens.css":
        "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() !== ''",
    "components.css":
        "getComputedStyle(document.getElementById('data-blocked')).display === 'none'",
    "data.css":
        "getComputedStyle(document.querySelector('.tabulator-cell')).unicodeBidi === 'plaintext'",
    "table-theme.css":
        "getComputedStyle(document.documentElement).getPropertyValue('--table-radius').trim() !== ''",
    "vendor/tabulator.min.css":
        "getComputedStyle(document.querySelector('.tabulator')).position === 'relative'",
    "grid-theme.css":
        "getComputedStyle(document.querySelector('.data-grid-frame'))"
        ".getPropertyValue('--data-grid-height').trim() !== ''",
    "data-workspace.css":
        "getComputedStyle(document.querySelector('.data-workspace'))"
        ".getPropertyValue('--data-canvas-width').trim() !== ''",
}


def test_the_page_is_built_from_its_own_tags(open_data):
    """If this fails, the harness is loading a list of its own again or failed to deliver
    a file the page names, and a Data page that stopped linking a stylesheet (or
    appearance.js) would still pass every test."""
    page = open_data()

    assert page.evaluate("window.__LOAD_FAILURES__") == [], (
        "a file data.html loads did not reach the built page")
    expected = _linked_sheets()
    assert sorted(expected) == sorted(SHEET_EFFECTS), (
        f"data.html links {expected}; name an effect for each sheet it links, "
        "and drop the effect of a sheet it no longer links")
    loaded = page.evaluate("""() => [...document.styleSheets]
        .map((sheet) => sheet.href).filter(Boolean)""")
    assert len(loaded) == len(expected), (loaded, expected)
    for relative in expected:
        assert any(url.endswith("/" + relative) for url in loaded), (
            f"data.html links {relative}, and the built page did not load it: {loaded}")
        assert page.evaluate(f"() => {SHEET_EFFECTS[relative]}"), (
            f"{relative}, which data.html links, did not reach the page")
    assert page.evaluate("() => document.documentElement.dataset.appearance"), (
        "appearance.js, which data.html loads first, never ran")


def test_the_stub_answers_only_the_engine(open_data):
    """If this fails, a page that asked its own origin or the internet for data would be
    handed the table anyway, and the defect would pass as a working page."""
    page = open_data(fields={"fields": [{"field_key": "price"}]},
                     promotable={"attributes": [{"key": "brand"}]},
                     offer={"offer_id": 7})
    seen = page.evaluate("""async (base) => {
        const out = {};
        try { await fetch("https://example.com/api/table/X"); out.off = "answered"; }
        catch (err) { out.off = String(err.message); }
        try { await fetch("/api/table/X"); out.own = "answered"; }
        catch (err) { out.own = String(err.message); }
        out.unknown = (await fetch(base + "/api/nothing/X")).status;
        for (const [name, path] of [["fields", "/api/fields/X"],
                                    ["promotable", "/api/promotable/X"],
                                    ["offer", "/api/offer/X/1"]]) {
            const reply = await fetch(base + path);
            out[name] = [reply.status, await reply.json()];
        }
        return out;
    }""", harness.BACKEND)
    assert seen["off"].startswith("the harness refuses a request that is not to the engine")
    assert seen["own"].startswith("the harness refuses a request that is not to the engine")
    assert seen["unknown"] == 404
    assert seen["fields"] == [200, {"fields": [{"field_key": "price"}]}]
    assert seen["promotable"] == [200, {"attributes": [{"key": "brand"}]}]
    assert seen["offer"] == [200, {"offer_id": 7}]


def test_a_route_left_unset_answers_its_own_empty_shape(open_data):
    """If this fails, a route the test did not set is handed something else, such as the
    table, and a control that reads it hides itself while its guards pass against a
    control that was never drawn."""
    page = open_data()
    seen = page.evaluate("""async (base) => {
        const out = {};
        for (const [name, path] of [["taxonomy", "/api/taxonomy/X"],
                                    ["fields", "/api/fields/X"],
                                    ["promotable", "/api/promotable/X"],
                                    ["offer", "/api/offer/X/1"]]) {
            const reply = await fetch(base + path);
            out[name] = [reply.status, await reply.json()];
        }
        return out;
    }""", harness.BACKEND)
    assert seen == {"taxonomy": [200, {"groups": []}], "fields": [200, {"fields": []}],
                    "promotable": [200, {"attributes": []}], "offer": [200, {}]}, seen


def test_the_request_log_survives_a_reload(open_data):
    """If this fails, a test that saves a column (after which the grid reloads the page)
    could no longer read what was posted before the reload."""
    page = open_data()
    page.evaluate("""(base) => fetch(base + "/api/fields/SAMEHGABRIEL",
        {method: "POST", body: JSON.stringify({field_key: "price", hidden: true})})""",
                  harness.BACKEND)
    page.reload()
    page.wait_for_timeout(600)
    posted = [r for r in page.evaluate("window.__REQUESTS__") if r["method"] == "POST"]
    assert posted == [{"method": "POST",
                       "url": harness.BACKEND + "/api/fields/SAMEHGABRIEL",
                       "body": '{"field_key":"price","hidden":true}'}], posted


def test_nothing_but_a_fetch_leaves_the_page(open_data):
    """If this fails, a test that clicks Excel or a record's link, or draws a picture,
    would send that request to whatever listens on the harness's engine address.

    The page aims at a listener this test opens, so what it proves is that the request
    never arrived, not only that the fence saw it."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    # Never blocking: the fence is a route handler, and Playwright runs it only while
    # this thread is inside a Playwright call, so a blocking accept would hold every
    # request unanswered and prove nothing.
    listener.setblocking(False)
    target = f"http://127.0.0.1:{listener.getsockname()[1]}"
    picture, export = target + "/picture.png", target + "/export/SAMEHGABRIEL.xlsx"
    reached = False
    try:
        page = open_data()
        page.evaluate("""(url) => {
            const img = document.createElement("img");
            img.src = url;
            document.body.append(img);
        }""", picture)
        page.evaluate("(url) => { window.location = url; }", export)
        for _ in range(20):
            page.wait_for_timeout(100)
            try:
                connection, _ = listener.accept()
            except BlockingIOError:
                continue
            reached = True
            connection.close()
            break
    finally:
        listener.close()
    assert not reached, "a request left the page and reached the listener"
    assert picture in page.fenced, page.fenced
    assert export in page.fenced, page.fenced


def test_nothing_listens_at_the_harness_engine_address():
    """If this fails, the stub's default engine address is one something answers on
    (before #1264 it was the owner's own engine), so a request the fence misses would
    reach it."""
    address = urlsplit(harness.BACKEND)
    assert inspect.signature(harness.stub).parameters["backend"].default == harness.BACKEND
    with socket.socket() as probe:
        probe.settimeout(2)
        assert probe.connect_ex((address.hostname, address.port)) != 0, (
            f"something answers at {harness.BACKEND}")


def _fake_extension(root: Path, *, data_js: str = "", extra_head: str = "") -> Path:
    root.mkdir()
    (root / "data.html").write_text(
        "<!doctype html><html><head>" + extra_head + "</head><body>"
        '<script type="module" src="data.js"></script></body></html>', encoding="utf-8")
    for module in harness.DATA_PAGE_MODULES:
        (root / module).write_text(data_js if module == "data.js" else "", encoding="utf-8")
    return root


def test_a_file_the_page_loads_that_does_not_exist_fails_the_build(tmp_path):
    """If this fails, a page that names a file the extension does not carry would be
    built without it, and render the way it renders when that file is lost."""
    ext = _fake_extension(tmp_path / "ext",
                          extra_head='<link rel="stylesheet" href="gone.css">')
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileNotFoundError, match=r"gone\.css"):
        harness.build_data_page(out, "", ext=ext)


def test_a_script_the_page_adds_to_itself_is_carried(tmp_path):
    """If this fails, the grid.js that the Data page adds to itself at run time would be
    missing from the built page, and the page would silently draw no table."""
    ext = _fake_extension(tmp_path / "ext",
                          data_js='const s = document.createElement("script");\n'
                                  's.src = "grid.js";\n')
    (ext / "grid.js").write_text("window.__carried = true;", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    harness.build_data_page(out, "", ext=ext)
    assert (out / "grid.js").read_text(encoding="utf-8") == "window.__carried = true;"
