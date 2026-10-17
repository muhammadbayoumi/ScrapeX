"""Every Button and text field the web UI draws is Supabase's size, read from the boxes in a
browser (#1430): the panel's sweep, `test_every_button_is_26px_and_every_field_34px_tall`, over
every page the engine serves.

The pages are the engine's own, through its TestClient, as the web UI's focus-ring sweep
serves them (tests/test_the_focus_ring_draws_in_the_web_ui.py). At 1280px wide each field is
past Tailwind's md, 48rem, so its text is Supabase's text-sm, 13px.
"""
from __future__ import annotations

from collections import Counter

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")

from tests.test_panel_dom import (  # noqa: E402,F401  (the fixture)
    _ICON_ONLY, _READ_SIZES, _SIZE, WEB_ALSO, browser)
from tests.test_the_focus_ring_draws_in_the_web_ui import (  # noqa: E402,F401  (the fixture)
    ORIGIN, PAGES, webui)

# The shared Button and Input rules are design/components.css, which the panel ships too.
pytestmark = pytest.mark.extension

#: Controls that are not at their SIZE height, each with why. THIS LIST ONLY SHRINKS, as the
#: panel's `_OFF_SIZE` does.
OFF_SIZE = {
    "button.data-grid-command": "the grid's command bar, its own size; #1367 rebuilds the grid",
    ".grid-lang-option": "the grid's language toggle, its own size; #1367 rebuilds the grid",
    ".settings-nav-item": "a Settings page's tab, a row of a lead and two lines of text",
    ".appearance-scheme-picker button": "a ToggleGroup item, h-10 (toggle.tsx@86c813ec:20)",
    ".appearance-palette-tile": "a palette's tile, which Supabase gives no control height",
    ".schedule-source-choice": "a row of a source's name and its schedule, a <button>",
    ".schedule-filter": "a filter in the Schedules page's 2x2 grid, at its own padding",
}

#: A COLUMN'S FILTER AND MENU ARE SUPABASE'S COLUMN MENU TRIGGER (his ruling on #1466): their
#: grid header's Button at padding 3px (ColumnMenu.tsx@86c813ec:225-234), 1 + 3 + 14 + 3 + 1
#: wide and tiny's 26px tall, as (width, height, icon).
_COLUMN_MENU = (22, 26, 14)


def test_every_button_is_26px_and_every_field_34px_tall_on_every_page(webui):
    controls: list[dict] = []
    for path in PAGES:
        response = webui.goto(ORIGIN + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        webui.wait_for_load_state("networkidle")
        if path == "/data":
            # The source list, and its icon link, are inside the dataset picker.
            webui.click("summary.dataset-menu-trigger")
            webui.wait_for_selector("a.dataset-icon-button", state="visible")
        if path == "/settings":
            # Each section is a closed <details>; the theme picker is in the first.
            webui.evaluate("() => document.querySelectorAll('details.sect').forEach((d) => { d.open = true; })")
            webui.wait_for_selector(".appearance-scheme-picker button", state="visible")
        controls += [{**control, "page": path}
                     for control in webui.evaluate(_READ_SIZES, ["body", list(OFF_SIZE), WEB_ALSO])]

    at_size = Counter(c["kind"] for c in controls if c["known"] is None)
    # 40 Buttons and 36 fields read at their size when #1430 measured; fewer means a page
    # did not draw.
    assert at_size["button"] >= 34 and at_size["field"] >= 30, dict(at_size)
    names = {c["name"] for c in controls}
    assert {"summary.dataset-menu-trigger.touch-reach", "a.dataset-icon-button.touch-reach",
            "#probe-url"} <= names, (
        "a control #1430 sized was not read")

    wrong = sorted({f"{c['page']} {c['name']} ({c['kind']}): {c['height']}px" for c in controls
                    if c["known"] is None and abs(c["height"] - _SIZE[c["kind"]]) > 0.01})
    assert not wrong, (
        f"Buttons not {_SIZE['button']}px or fields not {_SIZE['field']}px tall, named nowhere:"
        + "\n  ".join(["", *wrong]))
    padded = sorted({f"{c['page']} {c['name']}" for c in controls if c["select"] and c["padTop"]})
    assert not padded, f"a native <select> with block padding inside its 34px: {padded}"
    off = {c["known"] for c in controls if c["known"] is not None
           and abs(c["height"] - _SIZE[c["kind"]]) > 0.01}
    assert off == set(OFF_SIZE), (
        "named in OFF_SIZE and matching no control off its size, so take it out: "
        f"{sorted(set(OFF_SIZE) - off)}")

    # A column's filter and menu are Supabase's column menu trigger, 22x26 around its 14px
    # icon (his ruling on #1466; design/grid-theme.css), and on the source page there are some.
    header = [c for c in controls if c["name"].startswith("button.dg-header-button")]
    assert {c["page"] for c in header} == {"/source/ELSEWEDYSHOP"}, header
    assert {(c["width"], c["height"], c["icon"], c["iconOnly"]) for c in header} == {
        (*_COLUMN_MENU, True)}, header

    # Every other icon-only Button is Supabase's 36x26 around its 14px icon (#1430; his ruling
    # on #1457): the source list's icon link at this width.
    icon_only = [c for c in controls if c["iconOnly"] and c["known"] is None and c not in header]
    assert "a.dataset-icon-button.touch-reach" in {c["name"] for c in icon_only}, icon_only
    boxes = sorted({f"{c['page']} {c['name']}: {c['width']}x{c['height']}, its icon {c['icon']}px"
                    for c in icon_only if (c["width"], c["height"], c["icon"]) != _ICON_ONLY})
    assert not boxes, "icon-only Buttons not 36x26 around a 14px icon:\n  " + "\n  ".join(boxes)

    # Past md a field's text is text-sm, 13px, on leading-4's 16px line (constants.ts@86c813ec:48).
    response = webui.goto(ORIGIN + "/manage")
    assert response is not None and response.status == 200
    text = webui.evaluate("""() => {
      const s = getComputedStyle(document.querySelector('#probe-url'));
      return [s.fontSize, s.lineHeight];
    }""")
    assert text == ["13px", "16px"], text

    # On a phone the navigation is behind its toggle, an icon-only Button too.
    webui.set_viewport_size({"width": 360, "height": 800})
    response = webui.goto(ORIGIN + "/")
    assert response is not None and response.status == 200
    toggle = [c for c in webui.evaluate(_READ_SIZES, ["body", [], []])
              if c["name"] == "button.sidebar-toggle.workspace-menu-button.icon-button"]
    assert [(c["width"], c["height"], c["icon"], c["iconOnly"]) for c in toggle] == [
        (*_ICON_ONLY, True)], toggle
