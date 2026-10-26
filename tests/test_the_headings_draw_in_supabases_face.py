"""Every heading draws Supabase's heading face at 600, measured in a browser (#751).

Supabase sets every h1-h6 that is not in a mono context to the heading face at
font-semibold (apps/design-system/styles/globals.css@86c813ec:120-133), at typography.css's
per-level sizes (packages/config/typography.css@86c813ec:53-74). Here that is one rule in
design/components.css. A heading whose own rule sets a size keeps it, as in Supabase, where
the sizes sit in @layer base under every utility. A mono heading inherits its parent's
weight (preflight's `inherit`, and #752's ruling), so it draws 450.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from tests.test_panel_dom import browser, open_panel  # noqa: E402,F401  (the fixtures)
from tests.test_tab_page_dom import open_data  # noqa: E402,F401  (the fixture)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, PAGES, webui  # noqa: E402,F401
from tools import tabpage_harness  # noqa: E402
from tests.test_console_dom import WORKBOOK  # noqa: E402

# Guards the extension's pages; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

#: Every h1-h6 in the page, as the browser computes it. Hidden ones too: a sheet, a dialog
#: or a view not yet opened still computes its face and weight, and a heading there is a
#: heading he will see (the schedule sheet's title drew 450 until #751).
HEADINGS = """(where) => [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')]
  .map(el => { const s = getComputedStyle(el);
    return {where, tag: el.tagName.toLowerCase(), id: el.id, text: el.textContent.trim().slice(0, 40),
            family: s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), weight: s.fontWeight,
            size: parseFloat(s.fontSize), spacing: s.letterSpacing}; })"""


def _wrong_face(headings):
    """Headings not in Supabase's face: Manrope 600, or Source Code Pro 450 in a mono context."""
    return [h for h in headings
            if not ((h["family"] == "Manrope" and h["weight"] == "600")
                    or (h["family"] == "Source Code Pro" and h["weight"] == "450"))]


def _panel_headings(page):
    found = []
    views = page.eval_on_selector_all("nav.side-rail button[data-view]", "buttons => buttons.map(b => b.dataset.view)")
    for view in views:
        page.evaluate("(v) => document.querySelector(`nav.side-rail button[data-view=\"${v}\"]`).click()", view)
        page.wait_for_timeout(150)
        found += page.evaluate(HEADINGS, view)
    return found


def test_every_panel_heading_draws_in_the_heading_face(open_panel):
    page = open_panel()
    page.evaluate("() => document.fonts.ready")
    headings = _panel_headings(page)
    assert len(headings) >= 40, len(headings)
    wrong = _wrong_face(headings)
    assert not wrong, f"panel headings outside Manrope 600: {wrong}"


def test_every_tab_page_heading_draws_in_the_heading_face(browser, open_data):  # noqa: F811
    headings = []
    with tabpage_harness.serve_extension() as base:
        for name in ("console", "enrichment", "onboarding"):
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                if name == "console":
                    page.add_init_script(tabpage_harness.console_stub(WORKBOOK))
                page.goto(f"{base}/{name}.html")
                page.wait_for_load_state("networkidle")
                page.evaluate("() => document.fonts.ready")
                headings += page.evaluate(HEADINGS, name)
            finally:
                page.close()
    data = open_data()
    headings += data.evaluate(HEADINGS, "data")
    # 14 when written: most of the Console's headings sit in views its rail has not opened.
    assert len(headings) >= 12, len(headings)
    wrong = _wrong_face(headings)
    assert not wrong, f"tab-page headings outside Manrope 600: {wrong}"


def test_every_web_ui_heading_draws_in_the_heading_face(webui):  # noqa: F811
    headings = []
    for path in PAGES:
        webui.goto(ORIGIN + path)
        webui.wait_for_load_state("networkidle")
        headings += webui.evaluate(HEADINGS, path)
    # The inspector's heading, the one mono heading here, exists once a table opens: last,
    # so the open inspector holds no page the loop goes to next.
    webui.goto(ORIGIN + "/data-model")
    webui.wait_for_load_state("networkidle")
    webui.click(".model-table")
    webui.wait_for_selector(".model-inspector-header h3")
    headings += webui.evaluate(HEADINGS, "/data-model, a table open")
    assert any(h["family"] == "Source Code Pro" for h in headings), "the data model's mono heading was not reached"
    assert len(headings) >= 60, len(headings)
    wrong = _wrong_face(headings)
    assert not wrong, f"web UI headings outside Manrope 600: {wrong}"


def test_a_heading_with_no_size_rule_takes_supabases_per_level_size(browser, open_panel):  # noqa: F811
    """typography.css@86c813ec:53-74: h1 text-2xl, here --fs-xl 22px; h2 text-xl, --fs-lg
    18px; h3 text-base, --fs 15px. Every h1 is tracking-tight (-0.025em)."""
    page = open_panel(signed_in=None)
    welcome = page.evaluate(HEADINGS, "welcome")
    with tabpage_harness.serve_extension() as base:
        console = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            console.add_init_script(tabpage_harness.console_stub(WORKBOOK))
            console.goto(f"{base}/console.html")
            console.wait_for_selector("#tables-list button.pair-row", state="attached", timeout=10_000)
            sizes = console.evaluate("""() => ({
              title: parseFloat(getComputedStyle(document.querySelector('#workbook-title')).fontSize),
              h1: Math.max(...[...document.querySelectorAll('h1')].map(e => parseFloat(getComputedStyle(e).fontSize))),
              h2: Math.max(...[...document.querySelectorAll('h2')].map(e => parseFloat(getComputedStyle(e).fontSize)))})""")
        finally:
            console.close()
    assert sizes["title"] == 18, sizes
    assert sizes["h1"] > sizes["h2"], f"the Console's page title is no larger than its card titles: {sizes}"
    h1s = [h for h in welcome if h["tag"] == "h1"]
    assert h1s and all(h["spacing"] != "normal" for h in h1s), h1s
    assert any(h["size"] == 22 for h in h1s), f"the signed-out welcome title is not 22px: {h1s}"


def test_a_heading_with_its_own_size_rule_keeps_it(open_panel):
    """The per-level sizes reach only a heading with no size rule: a view's title stays
    18px, and the panel's small section labels stay 12px (phase 4 decides those, #731)."""
    page = open_panel(view="settings")
    sizes = page.evaluate("""() => ({
      view: parseFloat(getComputedStyle(document.querySelector('.view-heading h1')).fontSize),
      label: [...document.querySelectorAll('main h2')].filter(e => e.getClientRects().length
               && getComputedStyle(e).textTransform === 'uppercase').map(e => parseFloat(getComputedStyle(e).fontSize))})""")
    assert sizes["view"] == 18, sizes
    assert sizes["label"] and set(sizes["label"]) == {12.0}, sizes
