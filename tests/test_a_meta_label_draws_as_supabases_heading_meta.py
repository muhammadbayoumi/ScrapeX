"""The meta labels draw as Supabase's heading-meta in a browser, on both surfaces (#713).

heading-meta (packages/config/typography.css@86c813ec:22-24) is 12px Source Code Pro at 500,
tracking-wider (0.05em, 0.6px at 12px), uppercase; composed with `.muted`, it draws in
--muted, Studio's foreground-light. A menu's group heading is CommandGroup's: the same at
normal weight in --text-subtle. The static half is tests/test_a_meta_label_is_supabases_heading_meta.py.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from tests.test_panel_dom import browser, open_panel  # noqa: E402,F401  (the fixtures)
from tests.test_tab_page_dom import open_data  # noqa: E402,F401  (the fixture)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, PAGES, webui  # noqa: E402,F401
from tools import tabpage_harness  # noqa: E402

# Guards the extension's pages; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

READ = """(selector) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  const probe = document.createElement('span'); document.body.append(probe);
  const colour = (v) => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const s = getComputedStyle(el);
  const read = {family: s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), size: s.fontSize,
                weight: s.fontWeight, spacing: s.letterSpacing, transform: s.textTransform, color: s.color,
                muted: colour('var(--muted)'), subtle: colour('var(--text-subtle)')};
  probe.remove();
  return read;
}"""
#: Every label in the page, closed menus and hidden views too, for a rule no static read parses.
SWEEP = """() => {
  const probe = document.body.appendChild(document.createElement('span'));
  const colour = (v) => { probe.style.color = v; return getComputedStyle(probe).color; };
  const muted = colour('var(--muted)'), subtle = colour('var(--text-subtle)');
  probe.remove();
  return [...document.querySelectorAll('.heading-meta')].map((el) => { const s = getComputedStyle(el);
    return {text: el.textContent.trim().slice(0, 30), group: el.classList.contains('grid-feature-section'),
            family: s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), size: s.fontSize, line: s.lineHeight,
            weight: s.fontWeight, spacing: s.letterSpacing, transform: s.textTransform, opacity: s.opacity,
            color: s.color, muted, subtle}; });
}"""
SCHEME = """(scheme) => window.ScrapeXAppearance && window.ScrapeXAppearance.set({mode: 'manual', scheme, palette: 'supabase'})"""


def _is_heading_meta(read):
    return (read is not None and read["family"] == "Source Code Pro" and read["size"] == "12px"
            and read["weight"] == "500" and read["spacing"] == "0.6px" and read["transform"] == "uppercase"
            and read["color"] == read["muted"])


def _off(reads):
    """The labels that do not draw heading-meta: a group heading is at 400 in --text-subtle."""
    return [r for r in reads if not (
        r["family"] == "Source Code Pro" and r["size"] == "12px" and r["line"] == "16px" and r["spacing"] == "0.6px"
        and r["transform"] == "uppercase" and r["opacity"] == "1" and r["weight"] == ("400" if r["group"] else "500")
        and r["color"] == (r["subtle"] if r["group"] else r["muted"]))]


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_label_on_the_web_ui_draws_heading_meta(webui, scheme):
    reads, wrong = 0, {}
    for path in (*PAGES, "/data/google-finance"):
        webui.goto(ORIGIN + path)
        webui.wait_for_load_state("networkidle")
        webui.evaluate(SCHEME, scheme)
        found = webui.evaluate(SWEEP)
        reads += len(found)
        wrong[path] = _off(found)
    # The inspector's label is built when a table opens.
    webui.goto(ORIGIN + "/data-model")
    webui.wait_for_load_state("networkidle")
    webui.evaluate(SCHEME, scheme)
    webui.click(".model-table")
    webui.wait_for_selector(".model-inspector-header .heading-meta")
    wrong["the inspector"] = _off(webui.evaluate(SWEEP))
    assert reads >= 40, reads
    assert not any(wrong.values()), wrong


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_label_on_the_panel_and_the_data_page_draws_heading_meta(open_panel, open_data, scheme):
    panel, data = open_panel(), open_data()
    wrong = {}
    for name, page, floor in (("panel", panel, 3), ("data", data, 3)):
        page.evaluate(SCHEME, scheme)
        found = page.evaluate(SWEEP)
        assert len(found) >= floor, (name, found)
        wrong[name] = _off(found)
    assert not any(wrong.values()), wrong


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_label_on_the_enrichment_page_draws_heading_meta(browser, scheme):  # noqa: F811
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
        try:
            page.goto(f"{base}/enrichment.html")
            page.wait_for_load_state("networkidle")
            found = page.evaluate(SWEEP)
        finally:
            page.close()
    assert len(found) == 10, found
    assert not _off(found), _off(found)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_panel_label_draws_heading_meta(open_panel, scheme):
    page = open_panel(view="finance")
    page.evaluate(SCHEME, scheme)
    page.evaluate("() => document.fonts.ready")
    read = page.evaluate(READ, "#view-finance .heading-meta")
    assert _is_heading_meta(read), read


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_data_page_labels_draw_heading_meta(open_data, scheme):
    page = open_data()
    page.evaluate(SCHEME, scheme)
    page.evaluate("() => document.fonts.ready")
    read = page.evaluate(READ, ".data-grid-eyebrow")
    assert _is_heading_meta(read), read
    group = page.evaluate(READ, ".grid-feature-section")
    assert group and group["family"] == "Source Code Pro" and group["weight"] == "400" \
        and group["color"] == group["subtle"] and group["transform"] == "uppercase", group
    toggle = page.evaluate(READ, ".grid-lang-option")
    assert toggle and toggle["weight"] == "500", toggle


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_web_ui_labels_draw_heading_meta(webui, scheme):
    for path in ("/jobs", "/data-model"):
        webui.goto(ORIGIN + path)
        webui.wait_for_load_state("networkidle")
        webui.evaluate(SCHEME, scheme)
        webui.evaluate("() => document.fonts.ready")
        read = webui.evaluate(READ, ".page-eyebrow")
        assert _is_heading_meta(read), (path, read)
    webui.goto(ORIGIN + "/source/ELSEWEDYSHOP")
    webui.wait_for_load_state("networkidle")
    link = webui.evaluate(READ, ".dataset-site-link")
    assert link and link["weight"] == "450", link
