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

import sys
from pathlib import Path

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


@pytest.fixture()
def open_data(browser, tmp_path):
    """Open the Data page against a stubbed engine and return the live page."""
    pages = []

    def opener(payload=None, *, source="SAMEHGABRIEL", **stub_kwargs):
        page_file = harness.build_data_page(
            tmp_path,
            harness.stub(PAYLOAD if payload is None else payload, **stub_kwargs),
            name=f"data{len(pages)}.html")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # The source rides in the address, exactly as it does when the panel
        # opens this page. A file:// URL carries a query string fine.
        page.goto(page_file.as_uri() + (f"?source={source}" if source else ""))
        page.wait_for_timeout(600)
        page.js_errors = errors
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

    assert page.locator("#data-summary").inner_text() != "Reading…", (
        "the page never got past its own freshness guard — this is the defect "
        "of 2026-08-15, where the generation was read before backendBase() had "
        "resolved the address that creates it")
    assert page.locator(".tabulator-row").count() == 2
    assert page.js_errors == [], f"the page threw: {page.js_errors}"


def test_it_draws_the_payload_it_was_given(open_data):
    page = open_data()

    assert page.locator("#data-source").inner_text() == "SAMEHGABRIEL"
    assert page.locator("#data-summary").inner_text() == "2 rows · bilingual"
    assert [h.strip() for h in page.locator(".tabulator-col-title").all_inner_texts()] \
        == ["Product name (AR)", "Price", "Currency"]


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
    assert page.locator("#data-summary").inner_text() != "Reading…"
    assert page.locator(".tabulator-row").count() == 2, (
        "the dataset's rows did not reach the grid")
    assert [h.strip() for h in page.locator(".tabulator-col-title").all_inner_texts()] \
        == ["Contractor id", "Company name", "Membership level"]
    # The Arabic value arrives as text, in a grid whose column labels are English.
    assert "شركة المقاولات" in page.locator(".tabulator-cell").all_inner_texts()[1]


def test_scraped_text_reaches_the_screen_as_TEXT(open_data):
    """Every value here came off somebody else's website. A name that arrived as
    markup and left as markup is the whole reason the formatter is plaintext."""
    hostile = {**PAYLOAD, "rows": [
        {"offer_id": 1, "product_name_ar": "<img src=x onerror=alert(1)>",
         "price": "1", "currency": "EGP"}]}
    page = open_data(hostile)

    assert page.locator("#data-grid img").count() == 0, (
        "a product name became an element — the grid is interpreting markup")
    assert "<img" in page.locator(".tabulator-cell").first.inner_text()


def test_arabic_keeps_its_own_direction(open_data):
    """An Arabic name in a left-to-right table drags the punctuation around it
    unless the cell is isolated. The rule is stated in CSS; this is what proves
    it reaches the rendered cell."""
    page = open_data()
    direction = page.evaluate(
        "getComputedStyle(document.querySelector('.tabulator-cell')).unicodeBidi")
    assert direction == "plaintext", f"cells render as {direction!r}"


def test_a_prefix_says_it_is_one(open_data):
    """The bound exists so a partial table is never read as a whole one."""
    page = open_data({**PAYLOAD, "total": 91234, "returned": 2, "truncated": True})

    assert page.locator("#data-summary").inner_text().startswith("2 of 91234")
    notice = page.locator("#data-truncated")
    assert "PREFIX" in notice.inner_text()
    assert "hidden" not in (notice.get_attribute("class") or "")


def test_a_source_with_nothing_to_fold_gets_a_switch_it_cannot_press(open_data):
    page = open_data({**PAYLOAD, "foldable": False})

    assert page.locator("#data-fold").is_disabled()
    assert page.locator("#data-fold-label").inner_text() == \
        "This source has no variants to fold"


def test_a_stopped_engine_is_named_rather_than_left_blank(open_data):
    """The failure an owner actually meets. A page that shows nothing and says
    nothing sends them looking at the data for a fault that is in the engine."""
    page = open_data(fail="Failed to fetch")

    blocked = page.locator("#data-blocked")
    assert "hidden" not in (blocked.get_attribute("class") or "")
    assert "engine" in blocked.inner_text().lower()
    assert page.locator("#data-summary").inner_text() == ""


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
    page.wait_for_timeout(300)

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


def test_the_page_asks_for_the_source_it_was_opened_for(open_data):
    page = open_data(source="ALSWEED")
    asked = page.evaluate("window.__ASKED__")

    assert any("/api/table/ALSWEED" in url for url in asked), asked
