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
