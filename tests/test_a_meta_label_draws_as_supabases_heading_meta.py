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
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, webui  # noqa: E402,F401

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
SCHEME = """(scheme) => window.ScrapeXAppearance && window.ScrapeXAppearance.set({mode: 'manual', scheme, palette: 'supabase'})"""


def _is_heading_meta(read):
    return (read is not None and read["family"] == "Source Code Pro" and read["size"] == "12px"
            and read["weight"] == "500" and read["spacing"] == "0.6px" and read["transform"] == "uppercase"
            and read["color"] == read["muted"])


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
