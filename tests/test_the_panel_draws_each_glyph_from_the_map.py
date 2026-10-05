"""The panel draws each destination's glyph from the one map, whatever the engine sends (#1056).

The engine and the extension install separately, so the panel meets engines
older and newer than itself. Before the map it drew the `icon` each engine sent
against its OWN sprite, and a <use> pointing at an id that sprite lacks draws
nothing and throws nothing: a renamed glyph on either side was a blank row on
the other. The engine still sends that field, frozen, for panels released before
the map (scrapex/ui_manifest.py). This panel must not read it.

The static half of the guard is tests/test_each_destination_draws_one_declared_glyph.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")

from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402
from scrapex.ui_manifest import ui_manifest  # noqa: E402

GLYPHS = json.loads((ROOT / "design" / "glyph-map.json").read_text(encoding="utf-8"))
# The panel's own pages, which its menu leaves out (extension/app.js PANEL_DESTINATIONS).
PANEL_DESTINATIONS = {"data", "settings"}

#: What every <use> inside one element points at, and whether that symbol draws
#: anything. A <use> at a missing id is the failure: it renders an empty box.
DRAWN = """(root) => [...root.querySelectorAll('svg use')].map((use) => {
  const href = use.getAttribute('href') || '';
  const symbol = href.startsWith('#') ? document.getElementById(href.slice(1)) : null;
  return {href, draws: !!(symbol && symbol.tagName.toLowerCase() === 'symbol'
                          && symbol.querySelector('path'))};
})"""


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
    pages = []

    def opener(*, view=None, **stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"glyphs{len(pages)}.html")
        page = browser.new_page(viewport={"width": 360, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        # Idle, not settled: /api/ui is adopted in the deferred phase.
        harness.wait_until_idle_work_done(page)
        if view is not None:
            page.click(f'nav.side-rail button[data-view="{view}"]')
            page.wait_for_selector(f"#view-{view}", state="visible")
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def _menu_glyphs(page) -> dict[str, dict]:
    """{destination key: its leading glyph} for every row of the Workspace menu."""
    rows = page.eval_on_selector_all(
        "#workspace-links [data-workspace-key]",
        f"rows => rows.map((row) => [row.dataset.workspaceKey, ({DRAWN})(row)[0]])")
    return dict(rows)


def _an_engine_whose_icons_are_all_wrong() -> dict:
    """The real /api/ui, with every legacy `icon` pointed at nothing the sprite has
    and one destination the map has never heard of: a newer engine, as this panel
    will meet it."""
    manifest = ui_manifest()
    for destination in manifest["navigation"]:
        destination["icon"] = "not-a-glyph-any-sprite-has"
    # `constructor` is a key every object answers to; the map must not.
    for key in ("added-by-a-newer-engine", "constructor"):
        manifest["navigation"].append({
            "key": key, "label": f"Added later: {key}", "path": f"/{key}",
            "description": "Not in this panel's map.", "group": "System",
            "icon": "not-a-glyph-any-sprite-has"})
    return manifest


def test_each_destination_draws_the_maps_glyph_whatever_the_engine_sends(open_panel):
    page = open_panel(ui=_an_engine_whose_icons_are_all_wrong())
    drawn = _menu_glyphs(page)
    assert "added-by-a-newer-engine" in drawn, "the panel did not adopt the engine's navigation"
    expected = {key: f"#icon-{glyph}" for key, glyph in GLYPHS["destinations"].items()
                if key not in PANEL_DESTINATIONS}
    expected["added-by-a-newer-engine"] = f"#icon-{GLYPHS['fallback']}"
    expected["constructor"] = f"#icon-{GLYPHS['fallback']}"
    assert {key: use["href"] for key, use in drawn.items()} == expected
    assert [key for key, use in drawn.items() if not use["draws"]] == [], (
        "these rows draw an empty <use>")
    assert page.js_errors == []


def test_the_offline_menu_draws_the_maps_glyphs(open_panel):
    """No /api/ui at all (the harness answers 404): the panel's own list stands,
    and it names no glyph of its own."""
    page = open_panel()
    drawn = _menu_glyphs(page)
    assert {key: use["href"] for key, use in drawn.items()} == {
        key: f"#icon-{glyph}" for key, glyph in GLYPHS["destinations"].items()
        if key not in PANEL_DESTINATIONS}
    assert all(use["draws"] for use in drawn.values())


def test_each_candidate_engine_draws_the_maps_glyph(open_panel):
    page = open_panel(view="engines")
    rows = dict(page.eval_on_selector_all(
        "#engine-candidates [data-engine-id]",
        f"rows => rows.map((row) => [row.dataset.engineId, ({DRAWN})(row)[0]])"))
    assert {key: use["href"] for key, use in rows.items()} == {
        key: f"#icon-{glyph}" for key, glyph in GLYPHS["engines"].items()}
    assert all(use["draws"] for use in rows.values())
