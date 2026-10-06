"""The panel draws each destination's glyph from the one map, whatever the engine sends (#1056).

The engine and the extension install separately, so the panel meets engines
older and newer than itself. Before the map it drew the `icon` each engine sent
against its OWN sprite, and a <use> pointing at an id that sprite lacks draws
nothing and throws nothing: a renamed glyph on either side was a blank row on
the other. The engine still sends that field, frozen, for panels released before
the map (scrapex/ui_manifest.py). This panel must not read it.

A key the map does not name draws NO glyph (the owner's ruling on #1435): no <use>
at all, so nothing points at an id the sprite lacks, and the row keeps its label.

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

    def opener(*, view=None, glyphs=None, **stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"glyphs{len(pages)}.html")
        if glyphs is not None:
            # A map other than the one synced into app.html. Every `<` is written
            # as JSON's \u003c, so the data block cannot end early whatever the map
            # holds; JSON.parse gives the panel the characters back.
            text = page_file.read_text(encoding="utf-8")
            block = '<script type="application/json" id="glyph-map">\n'
            start = text.index(block) + len(block)
            end = text.index("</script>", start)
            text = text[:start] + json.dumps(glyphs).replace("<", "\\u003c") + text[end:]
            page_file.write_text(text, encoding="utf-8")
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


#: The glyph ahead of a row's copy: what the map draws for the row, or nothing.
LEADING = f"""(row) => {{
  const before = row.querySelector('{{copy}}').previousElementSibling;
  return before ? ({DRAWN})(before) : [];
}}"""


def _rows(page, rows: str, key: str, copy: str) -> dict[str, dict]:
    """{key: {leading: the <use>s ahead of the row's copy, label, every <use>}}."""
    found = page.eval_on_selector_all(rows, f"""rows => rows.map((row) => [
        row.dataset.{key},
        {{leading: ({LEADING.replace('{copy}', copy)})(row),
          label: row.querySelector('{copy}').textContent,
          every: ({DRAWN})(row)}}])""")
    return dict(found)


def _menu_glyphs(page) -> dict[str, dict | None]:
    """{destination key: its leading glyph, or None} for every Workspace menu row.
    Every row keeps its label, and no <use> anywhere in a row draws nothing."""
    rows = _rows(page, "#workspace-links [data-workspace-key]", "workspaceKey",
                 ".workspace-destination-copy")
    _every_row_keeps_its_label_and_draws_every_use(rows)
    return {key: (row["leading"][0] if row["leading"] else None) for key, row in rows.items()}


def _every_row_keeps_its_label_and_draws_every_use(rows: dict) -> None:
    assert sorted(key for key, row in rows.items() if not row["label"].strip()) == [], (
        "these rows lost their label")
    assert sorted(key for key, row in rows.items() if len(row["leading"]) > 1) == []
    assert sorted(key for key, row in rows.items()
                  if not all(use["draws"] for use in row["every"])) == [], (
        "these rows carry a <use> at an id the sprite lacks")


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


def _hrefs(drawn: dict) -> dict:
    return {key: (use["href"] if use else None) for key, use in drawn.items()}


def _labels_share_one_column(page, rows: str, copy: str) -> None:
    """A row with no glyph keeps its label IN the label's column: the empty slot
    holds the glyph's place. Without it the label slides into the glyph's narrow
    column and wraps a word a line. Measured, so the menu is opened first."""
    if rows.startswith("#workspace-links"):
        page.click("#workspace-toggle")
        page.wait_for_selector("#workspace-menu.is-open")
        page.wait_for_timeout(400)  # the open transition moves every row
    lefts = dict(page.eval_on_selector_all(rows, f"""rows => rows.map((row) => [
        row.dataset.workspaceKey || row.dataset.engineId,
        Math.round(row.querySelector('{copy}').getBoundingClientRect().left)])"""))
    assert len(set(lefts.values())) == 1, f"labels start in different columns: {lefts}"


def test_each_destination_draws_the_maps_glyph_whatever_the_engine_sends(open_panel):
    """And a key the map has never heard of draws no glyph at all: the map's
    fallback is empty, so the row is its label and nothing points anywhere."""
    page = open_panel(ui=_an_engine_whose_icons_are_all_wrong())
    drawn = _menu_glyphs(page)
    assert "added-by-a-newer-engine" in drawn, "the panel did not adopt the engine's navigation"
    expected = {key: f"#{glyph}" for key, glyph in GLYPHS["destinations"].items()
                if key not in PANEL_DESTINATIONS}
    expected["added-by-a-newer-engine"] = None
    expected["constructor"] = None
    assert _hrefs(drawn) == expected
    assert all(use["draws"] for use in drawn.values() if use)
    _labels_share_one_column(page, "#workspace-links [data-workspace-key]",
                             ".workspace-destination-copy")
    assert page.js_errors == []


def test_the_offline_menu_draws_the_maps_glyphs(open_panel):
    """No /api/ui at all (the harness answers 404): the panel's own list stands,
    and it names no glyph of its own."""
    page = open_panel()
    drawn = _menu_glyphs(page)
    assert _hrefs(drawn) == {
        key: f"#{glyph}" for key, glyph in GLYPHS["destinations"].items()
        if key not in PANEL_DESTINATIONS}
    assert all(use and use["draws"] for use in drawn.values())


def test_the_offline_menu_draws_no_glyph_for_a_key_the_map_lost(open_panel):
    """The panel's own list against a map that does not name one of its keys:
    that row draws no glyph and keeps its label; every other row is unchanged."""
    lost = json.loads(json.dumps(GLYPHS))
    del lost["destinations"]["logs"]
    page = open_panel(glyphs=lost)
    drawn = _menu_glyphs(page)
    assert drawn["logs"] is None
    assert _hrefs(drawn) == {
        key: (None if key == "logs" else f"#{glyph}")
        for key, glyph in GLYPHS["destinations"].items() if key not in PANEL_DESTINATIONS}
    _labels_share_one_column(page, "#workspace-links [data-workspace-key]",
                             ".workspace-destination-copy")


def _candidates(page) -> dict[str, list[str]]:
    """{candidate id: the hrefs in its icon tile}, the tile being what sits ahead
    of the row's copy. Every row keeps its name and draws every <use>."""
    rows = _rows(page, "#engine-candidates [data-engine-id]", "engineId", ".engine-row-copy")
    _every_row_keeps_its_label_and_draws_every_use(rows)
    assert page.js_errors == []
    return {key: [use["href"] for use in row["leading"]] for key, row in rows.items()}


def test_each_candidate_engine_draws_the_maps_glyph(open_panel):
    assert _candidates(open_panel(view="engines")) == {
        key: [f"#{glyph}"] for key, glyph in GLYPHS["engines"].items()}


def test_a_candidate_the_map_does_not_name_draws_no_glyph(open_panel):
    """Its tile stays, empty, and the row keeps its name."""
    lost = json.loads(json.dumps(GLYPHS))
    del lost["engines"]["katana"]
    page = open_panel(view="engines", glyphs=lost)
    assert _candidates(page) == {
        key: ([] if key == "katana" else [f"#{glyph}"])
        for key, glyph in GLYPHS["engines"].items()}
    _labels_share_one_column(page, "#engine-candidates [data-engine-id]", ".engine-row-copy")


def test_the_rail_tab_of_each_panel_destination_draws_the_maps_glyph(open_panel):
    """Data and Settings are left out of the menu because the rail carries them;
    their rail tab draws the map's glyph for the destination, and it draws."""
    page = open_panel()
    drawn = {key: page.eval_on_selector(f"#tab-{key}", DRAWN) for key in PANEL_DESTINATIONS}
    assert drawn == {key: [{"href": f"#{GLYPHS['destinations'][key]}", "draws": True}]
                     for key in PANEL_DESTINATIONS}


#: Markup a glyph would become if it reached innerHTML unescaped: it closes the
#: <use> and the <svg> around it and opens an element of its own.
INJECTED = '"></use></svg><b id="glyph-injected"></b><svg><use href="#'


def test_a_glyph_is_text_and_never_becomes_markup(open_panel):
    """The map is read out of the DOM (app.html's data block), so the panel escapes
    each glyph where it meets markup, like every value it interpolates (app.js
    esc()). A glyph carrying markup stays one attribute value, on both lists."""
    hostile = json.loads(json.dumps(GLYPHS))
    hostile["destinations"]["overview"] = "material-dashboard" + INJECTED
    hostile["engines"]["scrapy"] = "material-dns" + INJECTED
    page = open_panel(view="engines", glyphs=hostile)
    assert page.evaluate("document.getElementById('glyph-injected') === null"), (
        "a glyph from the map became an element of the panel")
    menu = page.eval_on_selector('#workspace-links [data-workspace-key="overview"]', DRAWN)
    assert menu[0]["href"] == "#material-dashboard" + INJECTED
    engine = page.eval_on_selector('#engine-candidates [data-engine-id="scrapy"]', DRAWN)
    assert engine[0]["href"] == "#material-dns" + INJECTED
    assert page.js_errors == []
