"""The words on a fill, scored over what is really under them, on both surfaces (#1839, #634).

tests/test_panel_dom.py scores token against token, over the backdrops _SITS_ON names for the
panel. The web UI draws the same tokens on backdrops the panel does not have: a selected
choice's --accent-weak, a chip inside a chip, a card at 88% surface, a 96% mix of surface and
bg. So this reads the page and not a list. Each rule that paints --surface-subtle, --chip or
--control-hover, through an alias, a color-mix or a gradient too, is composited over the
backgrounds under each element it matches, and every word on it is scored in its own colour.

Today those fills are opaque and what is under them changes nothing. #634 makes them Supabase's
alpha values, and then every one of these is a stack of layers.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")

from tests.test_panel_dom import (  # noqa: E402,F401  (browser and open_panel are the fixtures)
    _FILLS_DRAWN_JS,
    _NO_TRANSITIONS,
    _SITS_ON,
    _THEME_COLOURS_JS,
    ACCOUNT,
    _alpha,
    _contrast,
    _over,
    _registered_palette_ids,
    browser,
    open_panel,
)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, PAGES, webui_page  # noqa: E402

#: WCAG 2.2 SC 1.4.3.
_AA = 4.5

#: Below AA today, each pinned under its own measured light ratio, so it cannot drift further
#: and a move upward passes (#1859): --amber is a fill's colour, and these write words in it.
#: Both measure 2.716, one on --surface-subtle and one on the lowest stop of the hero's gradient.
_PINNED = {("overview-warning-text", "amber"): 2.7, ("overview-stage-state", "amber"): 2.7}


def _seen_over(top: str, layers: list[str]) -> str:
    """`top` as it is seen over the backgrounds under it, nearest first, down to the first
    opaque one. With nothing opaque under it there is nothing to score it against, and that
    is a failure, not a pass."""
    stack = [top, *layers]
    opaque = next((index for index, colour in enumerate(stack) if _alpha(colour) == 1), None)
    assert opaque is not None, f"nothing opaque under {top}: {layers}"
    seen = stack[opaque]
    for layer in reversed(stack[:opaque]):
        seen = _over(layer, seen)
    return seen


def _floor(text: dict, values: dict) -> float:
    return next((floor for (holder, ink), floor in _PINNED.items()
                 if holder in text["classes"] and text["colour"] == values[ink]), _AA)


def _too_faint(drawn: list[dict], values: dict, where: str) -> list[str]:
    """Every word on a fill under its floor, named by where it is."""
    faint = []
    for one in drawn:
        for paint in one["paints"]:
            seen = _seen_over(paint, one["layers"])
            for text in one["texts"]:
                ratio = _contrast(_over(text["colour"], seen), seen)
                if ratio < _floor(text, values):
                    faint.append(f"{where} {one['selector']} «{text['sample']}» {text['colour']} on {paint}: {ratio:.3f}")
    return sorted(set(faint))


# ---- the sweeps: every page, in both schemes ---------------------------------------------


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_word_on_a_fill_in_the_web_ui_is_legible(browser, tmp_path, scheme):  # noqa: F811
    faint, scored, painted_by_a_mix = [], set(), 0
    with webui_page(browser, tmp_path, viewport={"width": 1280, "height": 900}, color_scheme=scheme) as page:
        for path in PAGES:
            response = page.goto(ORIGIN + path)
            assert response is not None and response.status == 200, (path, response and response.status)
            page.wait_for_load_state("networkidle")
            page.add_style_tag(content=_NO_TRANSITIONS)
            assert page.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches") == (scheme == "dark")
            drawn = page.evaluate(_FILLS_DRAWN_JS)
            faint += _too_faint(drawn, page.evaluate(_THEME_COLOURS_JS), path)
            scored |= {one["fill"] for one in drawn if one["texts"]}
            painted_by_a_mix += sum(1 for one in drawn if one["fill"] is None and one["texts"])
    assert not faint, f"{scheme}: words under their floor: {faint}"
    assert set(_SITS_ON) <= scored, f"a fill was scored nowhere: {scored}"
    assert painted_by_a_mix, "no gradient or color-mix of a fill was scored, so the walk stopped seeing them"


@pytest.mark.parametrize("palette", _registered_palette_ids())
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_word_on_a_fill_in_the_panel_is_legible(open_panel, palette, scheme):  # noqa: F811
    page = open_panel(signed_in=ACCOUNT)
    page.add_style_tag(content=_NO_TRANSITIONS)
    page.evaluate("""([palette, scheme]) => window.ScrapeXAppearance.set(
        {mode: "manual", scheme, palette, deviceColors: false})""", [palette, scheme])
    drawn = page.evaluate(_FILLS_DRAWN_JS)
    faint = _too_faint(drawn, page.evaluate(_THEME_COLOURS_JS), "panel")
    assert not faint, f"{palette} {scheme}: words under their floor: {faint}"
    scored = {one["fill"] for one in drawn if one["texts"]}
    assert set(_SITS_ON) <= scored, f"a fill was scored nowhere: {scored}"


# ---- the walk, on a page small enough to read --------------------------------------------


TOKENS = (":root { --surface-subtle: rgb(238, 238, 238); --chip: rgb(0 0 0 / 0.5); --control-hover: var(--chip); }"
          " body { background: rgb(255, 255, 255); color: rgb(0, 0, 0); } button { background: none; }")
HALF_BLACK = "rgba(0, 0, 0, 0.5)"


@pytest.fixture()
def walk(browser):  # noqa: F811
    pages = []

    def read(css: str, body: str) -> list[dict]:
        page = browser.new_page()
        pages.append(page)
        page.set_content(f"<!doctype html><style>{TOKENS} {css}</style><body>{body}</body>")
        return page.evaluate(_FILLS_DRAWN_JS)

    yield read
    for page in pages:
        page.close()


def test_a_rule_that_paints_no_fill_is_not_read(walk):
    assert walk(".x { background: rgb(1, 2, 3); }", "<p class=x>words</p>") == []


def test_an_alias_of_a_fill_keeps_its_name_however_far_it_is_followed(walk):
    [one] = walk(":root { --a: var(--chip); --b: var(--a); } .x { background: var(--b); }", "<p class=x>words</p>")
    assert (one["fill"], one["paints"]) == ("chip", [HALF_BLACK])


def test_a_background_color_is_read_like_a_background(walk):
    [one] = walk(".x { background-color: var(--surface-subtle); }", "<p class=x>words</p>")
    assert (one["fill"], one["paints"]) == ("surfaceSubtle", ["rgb(238, 238, 238)"])


def test_a_mix_of_a_fill_is_read_resolved_and_has_no_name(walk):
    [one] = walk(":root { --m: color-mix(in srgb, var(--surface-subtle) 50%, rgb(0, 0, 0)); } .x { background: var(--m); }",
                 "<p class=x>words</p>")
    assert one["fill"] is None
    assert one["paints"][0].startswith("color(srgb 0.46"), one["paints"]


def test_a_gradient_of_a_fill_is_scored_over_each_fill_it_names(walk):
    [one] = walk(".x { background: linear-gradient(90deg, rgb(255, 255, 255), var(--surface-subtle), var(--chip)); }",
                 "<p class=x>words</p>")
    assert one["fill"] is None
    assert one["paints"] == ["rgb(238, 238, 238)", HALF_BLACK]


def test_a_hover_rule_finds_what_it_hovers_and_writes_its_own_colour(walk):
    [one] = walk(".x { color: rgb(9, 9, 9); } .x:hover { background: var(--control-hover); color: rgb(200, 0, 0); }",
                 "<p class=x>words <span>inherited</span> <span style='color: rgb(0, 0, 200)'>its own</span></p>")
    assert one["fill"] == "controlHover" and one["writes"] == "rgb(200, 0, 0)"
    assert [(text["sample"], text["colour"]) for text in one["texts"]] == [
        ("words", "rgb(200, 0, 0)"), ("inherited", "rgb(200, 0, 0)"), ("its own", "rgb(0, 0, 200)")]


def test_a_rule_that_writes_no_colour_scores_the_words_as_they_are(walk):
    [one] = walk(".x { color: rgb(9, 9, 9); } .y { background: var(--chip); }", "<p class='x y'>words</p>")
    assert one["writes"] is None and one["texts"][0]["colour"] == "rgb(9, 9, 9)"


def test_the_backgrounds_under_a_fill_are_read_nearest_first(walk):
    [one] = walk(".x { background: var(--chip); } .card { background: rgb(1 2 3 / 0.5); }",
                 "<div class=card><p class=x>words</p></div>")
    assert one["layers"][:2] == ["rgba(1, 2, 3, 0.5)", "rgb(255, 255, 255)"]


def test_words_on_a_background_of_their_own_are_not_on_the_fill(walk):
    [one] = walk(".x { background: var(--surface-subtle); }",
                 "<div class=x>on it <b style='background: rgb(0, 0, 0)'><i>on the b</i></b></div>")
    assert [text["sample"] for text in one["texts"]] == ["on it"]


def test_words_nobody_reads_are_not_scored(walk):
    [one] = walk(".x { background: var(--surface-subtle); }",
                 "<div class=x><span aria-hidden=true>[</span><button disabled>off</button>"
                 "<span aria-disabled=true>off too</span><script>var a</script>read</div>")
    assert [text["sample"] for text in one["texts"]] == ["read"]


def test_a_closed_menu_is_still_read(walk):
    """A closed menu is aria-hidden on its container, and it opens: what hides the words from
    the walk is the word's own aria-hidden, the way the brackets mark themselves decoration."""
    [one] = walk(".x { background: var(--surface-subtle); }", "<div aria-hidden=true><div class=x>in a menu</div></div>")
    assert [text["sample"] for text in one["texts"]] == ["in a menu"]


def test_a_pressed_option_sits_on_its_thumb_and_the_other_on_the_fill(walk):
    [one] = walk(".x { background: var(--chip); }",
                 "<div class=x><button class=grid-lang-option aria-pressed=true>EN</button>"
                 "<button class=grid-lang-option aria-pressed=false>AR</button></div>")
    assert [text["sample"] for text in one["texts"]] == ["AR"]


def test_the_walk_leaves_nothing_behind(browser):  # noqa: F811
    page = browser.new_page()
    try:
        page.set_content(f"<!doctype html><style>{TOKENS} .x {{ background: var(--chip); }}</style><body><p class=x>w</p></body>")
        before = page.content()
        page.evaluate(_FILLS_DRAWN_JS)
        assert page.content() == before
    finally:
        page.close()


# ---- the score ----------------------------------------------------------------------------


@pytest.mark.parametrize("top,layers,seen", [
    ("rgb(9, 9, 9)", [], 9.0),  # opaque: nothing under it matters, and nothing has to be
    ("rgb(9, 9, 9)", ["rgb(200, 200, 200)"], 9.0),
    ("rgb(0 0 0 / 0.5)", ["rgb(200, 200, 200)"], 100.0),
    ("rgb(0 0 0 / 0.5)", ["rgba(0, 0, 0, 0)", "rgb(200, 200, 200)"], 100.0),  # a clear layer is no layer
    ("rgb(0 0 0 / 0.5)", ["rgb(0 0 0 / 0.5)", "rgb(200, 200, 200)"], 50.0),  # a chip in a chip
    ("rgb(0 0 0 / 0.5)", ["color(srgb 1 1 1 / 0.5)", "rgb(0, 0, 0)"], 63.75),  # a card at 50%, over the page
    ("rgb(0 0 0 / 0.5)", ["rgb(200, 200, 200)", "rgb(0, 0, 0)"], 100.0),  # nothing below the first opaque counts
    ("rgba(0, 0, 0, 0)", ["rgb(200, 200, 200)"], 200.0),  # a gradient's clear stop
])
def test_a_fill_is_seen_over_its_layers_down_to_the_first_opaque_one(top, layers, seen):
    value = _seen_over(top, layers)
    channel = float(value[value.index("(") + 1:value.index(",")])
    assert channel == pytest.approx(seen, abs=0.01), value


def test_a_fill_with_nothing_opaque_under_it_fails_loudly():
    with pytest.raises(AssertionError, match="nothing opaque under"):
        _seen_over("rgb(0 0 0 / 0.5)", ["rgb(0 0 0 / 0.5)", "rgba(0, 0, 0, 0)"])


AMBER = "rgb(202, 138, 16)"
GREEN = "rgb(9, 124, 79)"


def _word(colour: str, *classes: str) -> dict:
    return {"colour": colour, "classes": list(classes), "sample": "words"}


def _placement(*texts: dict, paint: str = "rgb(246, 246, 246)") -> dict:
    return {"selector": ".x", "paints": [paint], "layers": ["rgb(255, 255, 255)"], "texts": list(texts)}


def test_faint_words_are_named_with_where_they_are_and_their_ratio():
    [faint] = _too_faint([_placement(_word("rgb(170, 170, 170)", "y"))], {"amber": AMBER}, "/page")
    assert faint.startswith("/page .x «words» rgb(170, 170, 170) on rgb(246, 246, 246): 2.")


def test_words_at_the_floor_pass_and_words_just_under_it_fail():
    legible = "rgb(112, 112, 112)"
    assert _contrast(legible, "rgb(255, 255, 255)") > _AA
    assert not _too_faint([_placement(_word(legible), paint="rgb(255, 255, 255)")], {"amber": AMBER}, "/")
    assert _too_faint([_placement(_word("rgb(120, 120, 120)"), paint="rgb(255, 255, 255)")], {"amber": AMBER}, "/")


def test_a_translucent_fill_is_scored_on_what_it_composites_to():
    """Grey words clear AA on the white page and fail once half-black is under them: the
    score reads the stack, not the top layer's opaque ink and not the page."""
    grey = _word("rgb(112, 112, 112)")
    assert not _too_faint([_placement(grey, paint="rgb(255, 255, 255)")], {"amber": AMBER}, "/")
    assert _too_faint([_placement(grey, paint="rgb(0 0 0 / 0.5)")], {"amber": AMBER}, "/")


def test_every_stop_a_gradient_names_is_scored():
    """The words sit somewhere along the gradient and the walk cannot say where, so they must
    read on each fill it names; here the second is the one they fail on."""
    placement = {**_placement(_word("rgb(112, 112, 112)")), "paints": ["rgb(255, 255, 255)", "rgb(0 0 0 / 0.5)"]}
    assert _too_faint([placement], {"amber": AMBER}, "/")


def test_a_pin_holds_its_own_colour_on_its_own_class_and_nothing_else():
    values = {"amber": AMBER}
    pinned = _word(AMBER, "overview-stage-state")
    assert _floor(pinned, values) == 2.7 and not _too_faint([_placement(pinned)], values, "/")
    # The same class in the colour it is meant to have is held to AA, not to the pin.
    assert _floor(_word(GREEN, "overview-stage-state"), values) == _AA
    # The same colour on any other class is held to AA too, and fails.
    assert _too_faint([_placement(_word(AMBER, "another"))], values, "/")


def test_a_pinned_word_cannot_drift_below_its_pin():
    assert _too_faint([_placement(_word("rgb(225, 170, 60)", "overview-stage-state"))], {"amber": "rgb(225, 170, 60)"}, "/")
