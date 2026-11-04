"""--surface-subtle, --chip and --line are Supabase's alpha overlays, and the grid header stays opaque (#634).

Their --muted, --accent and --border are --foreground at an alpha the theme's scalars compute
(semantic.css@86c813ec; light.css and dark.css hold the scalars). This repo flattened each over
--card, which is the right colour on --card and the wrong one everywhere else: over --bg, over
a raised menu, or stacked on another fill. They are evaluated here to four decimals, which give
the same 8-bit alpha as the full expressions.

A header 4% opaque shows the rows scrolling under it, so the grid header keeps an opaque base,
with its tint as an image layer: the pattern the body's pinned cells already use, and
table.tsx@86c813ec:31.
"""
from __future__ import annotations

import pytest

from tests.test_the_status_ramps_are_supabases import _declared
from tests.test_the_provenance_markers_say_who_owns_each_value import _blocks

pytest.importorskip("playwright")
pytest.importorskip("fastapi")

from tests.test_panel_dom import ACCOUNT, _NO_TRANSITIONS, _alpha, _channels, _over, browser, open_panel  # noqa: E402,F401
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, webui_page  # noqa: E402

OVERLAYS = {
    "light": {"--surface-subtle": "rgb(3 3 3 / 0.0268)", "--chip": "rgb(3 3 3 / 0.0402)", "--line": "rgb(3 3 3 / 0.0813)"},
    "dark": {"--surface-subtle": "rgb(237 239 238 / 0.0329)", "--chip": "rgb(237 239 238 / 0.0493)",
             "--line": "rgb(238 239 238 / 0.0751)"},
}
#: What Supabase's own CSS draws for each over --card, read from its pixels at the pin. Written
#: out, not computed from the values above: they are what those values have to come to.
OVER_THE_CARD = {
    "light": {"--surface-subtle": (248, 248, 248), "--chip": (245, 245, 245), "--line": (234, 234, 234)},
    "dark": {"--surface-subtle": (30, 32, 31), "--chip": (34, 36, 35), "--line": (40, 42, 41)},
}


@pytest.mark.parametrize("index", range(3), ids=["light", "dark", "device-dark"])
@pytest.mark.parametrize("name", ["--surface-subtle", "--chip", "--line"])
def test_each_overlay_is_declared_at_its_alpha_in_every_block(index, name):
    theme, block = _blocks()[index]
    assert _declared(block).get(name) == OVERLAYS[theme][name], (theme, name)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("name", ["--surface-subtle", "--chip", "--line"])
def test_each_overlay_draws_supabases_own_colour_over_the_card(open_panel, scheme, name):  # noqa: F811
    page = open_panel(signed_in=ACCOUNT)
    page.add_style_tag(content=_NO_TRANSITIONS)
    page.evaluate("(s) => window.ScrapeXAppearance.set({mode: 'manual', scheme: s, palette: 'supabase', deviceColors: false})", scheme)
    fill, card = page.evaluate("""(name) => { const probe = document.body.appendChild(document.createElement('i'));
        const read = (token) => { probe.style.background = `var(${token})`; return getComputedStyle(probe).backgroundColor; };
        const out = [read(name), read('--surface')]; probe.remove(); return out; }""", name)
    assert _alpha(fill) < 1, f"{name} is opaque ({fill}), so it draws the same over everything"
    drawn = [channel * 255 for channel in _channels(_over(fill, card))]
    assert drawn == pytest.approx(OVER_THE_CARD[scheme][name], abs=1), (scheme, name, fill, drawn)


@pytest.fixture(params=["light", "dark"])
def grid(browser, tmp_path, request):  # noqa: F811
    with webui_page(browser, tmp_path, viewport={"width": 1280, "height": 900}, color_scheme=request.param) as page:
        page.goto(ORIGIN + "/source/ELSEWEDYSHOP")
        page.wait_for_selector(".dg-header .dg-col")
        page.add_style_tag(content=_NO_TRANSITIONS)
        yield page


@pytest.mark.parametrize("selector", [".dg-header", ".dg-header .dg-col:not(.dg-pinned)", ".dg-header .dg-pinned"])
def test_the_grid_header_is_opaque_with_its_tint_as_a_layer(grid, selector):
    """It is sticky: whatever scrolls under a translucent header shows through it."""
    paint = grid.evaluate("""(selector) => { const el = document.querySelector(selector); if (!el) return null;
        const cs = getComputedStyle(el); return [cs.backgroundColor, cs.backgroundImage]; }""", selector)
    assert paint is not None, f"nothing drew {selector}, so this measured nothing"
    assert _alpha(paint[0]) == 1, (selector, paint)
    assert paint[1].startswith("linear-gradient"), (selector, paint)


def test_a_hovered_grid_column_stays_opaque(grid):
    """A `background` shorthand on the hover rule would reset the base and let the rows through."""
    column = grid.locator(".dg-header .dg-col.dg-sortable:not(.dg-pinned)").first
    rest = column.evaluate("(el) => getComputedStyle(el).backgroundImage")
    column.hover()
    color, image = column.evaluate("(el) => { const cs = getComputedStyle(el); return [cs.backgroundColor, cs.backgroundImage]; }")
    assert _alpha(color) == 1, color
    assert image != rest, "hovering a sortable column no longer changes its tint"


def test_the_header_tint_does_not_stack_through_its_layers(grid):
    """The row, its cells and the pinned cells are nested. Each has an opaque base, so what the
    eye gets is one layer of the tint, not three (by computation 243 would go to 226 in light)."""
    seen = grid.evaluate("""() => { const read = (el) => { const cs = getComputedStyle(el);
          return [cs.backgroundColor, cs.backgroundImage]; };
        return [read(document.querySelector('.dg-header')), read(document.querySelector('.dg-header .dg-col:not(.dg-pinned)'))]; }""")
    assert seen[0] == seen[1], "a column does not draw what the header draws, so the tint is not one layer"
