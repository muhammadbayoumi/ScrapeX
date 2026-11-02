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
from tools import grid_harness  # noqa: E402
from tests.test_console_dom import WORKBOOK  # noqa: E402
from tests.test_the_grid_asks_the_engine_its_host_names import FIELDS, PROMOTABLE, _payload  # noqa: E402

# Guards the extension's pages; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

#: Every h1-h6 in the page, as the browser computes it. Hidden ones too: a sheet, a dialog
#: or a view not yet opened still computes its face and weight, and a heading there is a
#: heading he will see (the schedule sheet's title drew 450 until #751).
HEADINGS = """(where) => [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')]
  .map(el => { const s = getComputedStyle(el);
    return {where, tag: el.tagName.toLowerCase(), id: el.id, text: el.textContent.trim().slice(0, 40),
            family: s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), weight: s.fontWeight,
            cls: el.className, size: parseFloat(s.fontSize), spacing: parseFloat(s.letterSpacing) || 0}; })"""

#: What a heading draws with no rule but the level's, in px: size, line-height, letter-spacing.
#: typography.css's sizes with Tailwind's pairs, written out rather than computed from the
#: tokens they guard: --fs-xl with --lh-2xl, --fs-lg with --lh-xl, and h1's -0.025em.
LEVELS = {"h1": (22, 29.33, -0.55), "h2": (18, 25.2, 0), "h3": (15, 22.5, 0),
          "h4": (13, 18.57, 0), "h5": (13, 18.57, 0), "h6": (12, 16, 0)}
#: A heading made for the measure, on the page's own sheets, with no class for a rule to find.
FRESH_LEVELS = """() => Object.fromEntries(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].map((tag) => {
    const el = document.body.appendChild(document.createElement(tag));
    el.textContent = 'x';
    const s = getComputedStyle(el);
    const drawn = [parseFloat(s.fontSize), parseFloat(s.lineHeight), parseFloat(s.letterSpacing) || 0];
    el.remove();
    return [tag, drawn]; }))"""
#: A heading marked mono, under a parent at the body's weight.
FRESH_MONO = """() => ['tech', 'code'].map((mark) => {
    const parent = document.body.appendChild(document.createElement('div'));
    parent.style.fontWeight = '450';
    const el = parent.appendChild(document.createElement('h3'));
    el.className = mark;
    el.textContent = 'x';
    const s = getComputedStyle(el);
    const drawn = [mark, s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), s.fontWeight];
    parent.remove();
    return drawn; })"""
#: The one h1 whose own rule sets its tracking (pages/data-model.css, .model-hero h1).
OWN_TRACKING = {"Data Model"}


def _wrong_face(headings):
    """Headings not in Supabase's face: Manrope 600, or Source Code Pro 450 in a mono context."""
    return [h for h in headings
            if not ((h["family"] == "Manrope" and h["weight"] == "600")
                    or (h["family"] == "Source Code Pro" and h["weight"] == "450"))]


def _not_tight(headings):
    """h1s not at tracking-tight, which is -0.025em of their own size (theme.css@v4.2.4:385)."""
    return [h for h in headings if h["tag"] == "h1" and h["text"] not in OWN_TRACKING
            and h["spacing"] != pytest.approx(-0.025 * h["size"], abs=0.01)]


def _wrong_levels(page, own=()):
    """The levels `page` draws otherwise than LEVELS, leaving out those its sheet rules itself."""
    drawn = page.evaluate(FRESH_LEVELS)
    return {tag: drawn[tag] for tag, want in LEVELS.items()
            if tag not in own and drawn[tag] != pytest.approx(want, abs=0.01)}


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
    assert not _not_tight(headings), _not_tight(headings)


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
    assert not _not_tight(headings), _not_tight(headings)


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
    assert not _not_tight(headings), _not_tight(headings)
    assert any(h["text"] in OWN_TRACKING and h["spacing"] < -0.025 * h["size"] for h in headings), \
        "the data model's hero no longer sets its own tracking, so OWN_TRACKING excuses nothing"


def test_every_heading_the_grid_builds_on_open_draws_in_the_heading_face(browser, tmp_path):  # noqa: F811
    """A row's card, its description and the column chooser exist only once he opens them, so
    a sweep of the page at load never reads them. #751 deleted the weights of these."""
    offer = {"periods": [], "changes": [], "observations": [], "attributes": [], "details": [
        {"group": "Description", "code": "full_description", "label": "Description",
         "value": "OVERVIEW\nA paragraph about it."},
        {"group": "Description", "code": "full_description_more", "label": "More about it", "value": "Another one."},
        {"group": "Description", "code": "keywords", "label": "Keywords", "value": "cement"}]}
    target = grid_harness.build_page(tmp_path, _payload(), fields=FIELDS, promotable=PROMOTABLE, offer=offer)
    with grid_harness.serve(tmp_path) as base:
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            page.goto(f"{base}/{target.name}")
            page.wait_for_function("() => document.querySelectorAll('#grid .dg-body .dg-row').length > 0")
            page.evaluate("""() => document.querySelector(
                '#grid .dg-body .dg-row[data-index="0"] .dg-select').click()""")
            page.click('#offer-panel [data-inspector-view="details"]')
            page.wait_for_selector("#offer-panel h5.record-prose-section-title")
            headings = page.evaluate(HEADINGS, "the record")
            page.click("#grid-columns-button")
            page.wait_for_selector(".column-chooser-zone > h3")
            headings += page.evaluate(HEADINGS, "the chooser")
        finally:
            page.close()
    reached = {(h["tag"], h["cls"]) for h in headings}
    for built in (("h3", "selected-product-name"), ("h3", "record-card-title"), ("h4", "record-prose-title"),
                  ("h5", "record-prose-section-title"), ("h4", "record-detail-subsection-title")):
        assert built in reached, f"{built} was not drawn, so it was not measured: {sorted(reached)}"
    assert any(h["id"] == "column-chooser-title" for h in headings), "the chooser's title was not drawn"
    wrong = _wrong_face(headings)
    assert not wrong, f"the grid's headings outside Manrope 600: {wrong}"


def test_a_heading_marked_mono_inherits_its_parents_weight(open_panel, webui):  # noqa: F811
    """Preflight's `inherit`, #752's ruling. The exclusion alone would leave the browser's bold."""
    page = open_panel()
    webui.goto(ORIGIN + "/jobs")
    for surface in (page, webui):
        assert surface.evaluate(FRESH_MONO) == [["tech", "Source Code Pro", "450"], ["code", "Source Code Pro", "450"]]


def test_every_level_draws_its_size_and_line_height_on_the_panel(open_panel):
    """The panel's bare h2 is its small section label (extension/app.css; phase 4, #731)."""
    assert not _wrong_levels(open_panel(), own={"h2"})


def test_every_level_draws_its_size_and_line_height_on_the_tab_pages(browser, open_data):  # noqa: F811
    """Enrichment and onboarding each give the bare h1 their own larger size."""
    wrong = {}
    with tabpage_harness.serve_extension() as base:
        for name, own in (("console", ()), ("enrichment", {"h1"}), ("onboarding", {"h1"})):
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                if name == "console":
                    page.add_init_script(tabpage_harness.console_stub(WORKBOOK))
                page.goto(f"{base}/{name}.html")
                page.wait_for_load_state("networkidle")
                wrong[name] = _wrong_levels(page, own)
            finally:
                page.close()
    wrong["data"] = _wrong_levels(open_data())
    assert not any(wrong.values()), wrong


def test_every_level_draws_its_size_and_line_height_on_the_web_ui(webui):  # noqa: F811
    """webui.css held a second copy of these until #751 (option B), and putting it back moves
    the line-height of 74 headings and nothing else."""
    wrong = {}
    for path in PAGES:
        webui.goto(ORIGIN + path)
        webui.wait_for_load_state("networkidle")
        wrong[path] = _wrong_levels(webui)
    assert not any(wrong.values()), wrong


def test_a_heading_with_no_size_rule_takes_supabases_per_level_size(browser, open_panel):  # noqa: F811
    """typography.css@86c813ec:53-74: h1 text-2xl, here --fs-xl 22px; h2 text-xl, --fs-lg
    18px; h3 text-base, --fs 15px."""
    page = open_panel(signed_in=None)
    welcome = page.evaluate("""() => { const s = getComputedStyle(document.querySelector('#welcome-signed-out h1'));
      return [parseFloat(s.fontSize), parseFloat(s.lineHeight), parseFloat(s.letterSpacing)]; }""")
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
    assert welcome == pytest.approx(LEVELS["h1"], abs=0.01), f"the signed-out welcome title: {welcome}"


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
