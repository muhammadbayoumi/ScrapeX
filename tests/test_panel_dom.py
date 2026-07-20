"""The side panel, driven in a real browser and asserted on.

Fifteen panel capabilities were graded `partial` for one reason: no test of any
kind existed for any of them. Screenshots proved a layout, never a behaviour, and
they actively HID one blocker — every scenario clicked a nav button before
capturing, so the broken opening screen was never photographed.

These tests drive the panel's own HTML, CSS and JS through the same harness the
screenshots use, and assert what a person would see and do.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")
from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402

SOURCE_TAB = 'nav.tabs button[data-view="source"]'
RUN_TAB = 'nav.tabs button[data-view="run"]'


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_panel(browser, tmp_path):
    """Open the panel with a given stub and return the live page."""
    pages = []

    def opener(**stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"panel{len(pages)}.html")
        page = browser.new_page(viewport={"width": 360, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def text_of(page, selector: str) -> str:
    return (page.text_content(selector) or "").strip()


# ---- the opening screen ------------------------------------------------------

def test_the_panel_opens_on_source_with_the_active_tab_already_read(open_panel):
    """The blocker screenshots could not see: the opening view never ran its
    loader, so it sat at "Reading the active tab…" until you navigated away."""
    page = open_panel()
    assert page.is_visible("#view-source")
    assert text_of(page, "#cur-title") == harness.ACTIVE_TAB["title"]
    assert harness.ACTIVE_TAB["url"] in text_of(page, "#cur-url")
    assert not page.is_disabled("#cur-use")


def test_opening_the_panel_raises_no_script_errors(open_panel):
    page = open_panel()
    assert page.js_errors == [], f"the panel threw on load: {page.js_errors}"


def test_a_tab_that_is_not_a_website_is_refused_with_a_reason(open_panel):
    page = open_panel(tab={"url": "chrome://extensions", "title": "Extensions"})
    assert page.is_disabled("#cur-use"), "a chrome:// page cannot be crawled"
    assert "not a website" in text_of(page, "#cur-title")
    assert "Open a site in this tab" in text_of(page, "#cur-out")


def test_an_engine_failure_is_not_reported_as_a_browser_failure(open_panel):
    """Blaming the tab for an engine error sends the owner to the wrong place."""
    page = open_panel(fail_routes=["/api/resolve"])
    page.wait_for_timeout(400)
    assert text_of(page, "#cur-title") == harness.ACTIVE_TAB["title"], \
        "the tab WAS readable; only the engine failed"
    assert "engine" in text_of(page, "#cur-out").lower()


def test_an_already_registered_page_says_so_and_offers_no_duplicate_add(open_panel):
    page = open_panel(resolve={"matched": True, "source_name": "Example Store",
                               "source_key": "SHOP_EXAMPLE", "implemented": True})
    page.wait_for_timeout(300)
    assert "Already registered" in text_of(page, "#cur-out")
    assert "Add" not in page.text_content("#cur-use"), \
        "offering Add for a site that exists promises something that must fail"


# ---- Current Page, after the owner navigates --------------------------------

def test_current_page_re_reads_the_tab_rather_than_trusting_a_stale_read(open_panel):
    """The panel stays open while the owner browses. Acting on the address read
    minutes ago would register whichever site they have since left."""
    page = open_panel()
    page.evaluate("""() => {
        window.chrome.tabs.query = async () => [
            {url: "https://a-different-store.example/x", title: "A Different Store"}];
    }""")
    page.click('label[for="source-current"]')
    page.wait_for_timeout(300)
    assert "a-different-store.example" in text_of(page, "#cur-url"), \
        "Use this page would have registered the site the owner already left"


# ---- the URL batch -----------------------------------------------------------

def test_pasted_addresses_are_each_reported_with_what_was_detected(open_panel):
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://second.example.com")
    page.click("#urls-check")
    page.wait_for_timeout(900)
    rows = page.locator("#urls-results .srow")
    assert rows.count() == 2
    assert "shopify-json" in page.text_content("#urls-results")


def test_every_review_button_works_the_moment_it_is_visible(open_panel):
    """A row rendered clickable but bound only after the LAST address finished
    means an early click silently does nothing."""
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://second.example.com")
    page.click("#urls-check")
    page.wait_for_selector("#urls-results [data-pick]")
    page.click("#urls-results [data-pick]")     # click the first one immediately
    page.wait_for_timeout(600)
    assert page.is_visible("#source-detail"), \
        "clicking Review did nothing — it was rendered before it was bound"


def test_an_unreachable_address_is_not_dressed_up_as_a_detected_platform(open_panel):
    page = open_panel(fail_routes=["/api/probe"])
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://nothing-here.example")
    page.click("#urls-check")
    page.wait_for_timeout(700)
    body = page.text_content("#urls-results")
    assert "shopify" not in body.lower(), "a failed probe must not report a family"
    assert "Pick one to review" not in text_of(page, "#urls-out"), \
        "there is nothing to pick when every address failed"


def test_a_malformed_address_is_refused_before_any_request(open_panel):
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "not-a-url")
    page.click("#urls-check")
    page.wait_for_timeout(300)
    assert "Not a full address" in text_of(page, "#urls-out")
    calls = page.evaluate("() => window.__calls.filter(c => c.startsWith('/api/probe'))")
    assert calls == [], "a malformed address must not reach the network"


# ---- Add Site ----------------------------------------------------------------

def test_using_the_current_page_opens_the_add_site_choice_with_it_filled_in(open_panel):
    page = open_panel()
    page.click("#cur-use")
    page.wait_for_timeout(800)
    assert page.is_checked("#source-addsite"), \
        "the form lives in the Add Site panel, which must be the one that opens"
    assert harness.ACTIVE_TAB["url"] in page.input_value("#url")
    assert page.is_visible("#source-detail")


def test_a_probe_fills_the_form_from_what_was_detected(open_panel):
    page = open_panel()
    page.click("#cur-use")
    page.wait_for_timeout(900)
    assert page.input_value("#f-key") == "SHOP_EXAMPLE"
    assert page.input_value("#f-currency") == "SAR"
    assert "Shopify" in page.text_content("#probe-out") or \
        "shopify" in page.text_content("#probe-out")


def test_the_unbuilt_file_source_cannot_be_actioned(open_panel):
    page = open_panel()
    page.click('label[for="source-file"]')
    page.wait_for_timeout(300)
    assert page.is_disabled('[data-integration="file-upload"]')
    assert page.is_disabled('[data-integration="screenshot-capture"]')


# ---- the sites list (spec 10) ------------------------------------------------

def test_select_all_selects_only_what_the_search_is_showing(open_panel):
    """Select All ignored the active filter and took the whole catalogue, while
    the count then contradicted the visible list."""
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(400)
    page.fill("#site-search", "a.co")
    page.wait_for_timeout(300)
    page.click("#select-all")
    page.wait_for_timeout(300)
    assert text_of(page, "#sel-count") == "1 selected", \
        "Select all took sites the owner could not see"


def test_an_unsupported_site_cannot_be_selected(open_panel):
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(400)
    assert page.is_disabled('input[data-key="NOT_READY"]')
    assert "Not supported yet" in page.text_content("#sites")


def test_the_engine_being_down_is_stated_not_left_blank(open_panel):
    page = open_panel(engine_up=False)
    page.click(RUN_TAB)
    page.wait_for_timeout(500)
    assert "Start the engine" in page.text_content("#sites") or \
        "Couldn't reach" in page.text_content("#sites")


# ---- untrusted content (spec 34) --------------------------------------------

def test_a_scraped_name_containing_markup_cannot_inject_into_the_panel(open_panel):
    """Scraped values are untrusted. A site name is attacker-controlled text."""
    page = open_panel(sources=[{
        "source_key": "XSS", "base_url": "https://evil.example",
        "source_name": "<img src=x onerror=\"window.__owned=1\">",
        "family": "shopify-json", "active": True, "implemented": True,
        "observations": 1, "products": 1}])
    page.click(RUN_TAB)
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__owned") is None, "scraped markup executed"
    assert "<img" in page.text_content("#sites"), "it must render as visible text"


# ---- the last review minors --------------------------------------------------

def test_the_action_label_does_not_survive_onto_a_tab_it_cannot_apply_to(open_panel):
    """A stale "Open its dataset" on a chrome:// page promises something that
    page cannot do, even with the button disabled."""
    page = open_panel(resolve={"matched": True, "source_name": "Example Store",
                               "source_key": "SHOP_EXAMPLE", "implemented": True})
    page.wait_for_timeout(300)
    assert "Open its dataset" in page.text_content("#cur-use")

    page.evaluate("""() => {
        window.chrome.tabs.query = async () => [
            {url: "chrome://settings", title: "Settings"}];
    }""")
    page.click('label[for="source-current"]')
    page.wait_for_timeout(300)
    assert page.is_disabled("#cur-use")
    assert "Open its dataset" not in page.text_content("#cur-use")


def test_duplicate_pasted_addresses_do_not_stall_the_counter(open_panel):
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://shop.example.com")
    page.click("#urls-check")
    page.wait_for_timeout(900)
    assert page.locator("#urls-results .srow").count() == 2, \
        "both pasted lines must be reported, even when identical"
