"""Every focus indicator in a stylesheet here is one of Supabase's two recipes (#721).

Their `focus-ring` is a 2px ring at a 2px offset painted in the background, and their
`focus-inset` a 2px outline at minus its width, for a control flush inside a container
that clips (packages/config/css/utilities.css@86c813ec:196-208). Here the outline draws
the ring and a shadow, `--focus-ring-gap`, paints the offset; design/tokens.css holds
the colour, the gap and the two geometry tokens once, and every rule that draws focus
reads them. Before this, 72 declarations held 24 distinct values: widths of 2px and
3px, eleven colours, and offsets of 2px, 1px, -2px and -3px.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.value_literals import authored, declarations

# Guards stylesheets the extension ships; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
FOCUS = re.compile(r":focus(?:-visible|-within)?(?![\w-])")
PROPERTIES = re.compile(r"outline(?:-(?:width|offset|color|style))?|box-shadow")

#: The two recipes, as the tokens spell them.
RECIPES = {
    "outline": {"var(--focus-ring-width) solid var(--focus-ring-color)"},
    # The ring sits at its offset; the inset at minus its width.
    "outline-offset": {"var(--focus-ring-offset)", "calc(-1 * var(--focus-ring-width))"},
}

#: Rules this change leaves to the item that rebuilds or owns them, each named. An entry
#: that no longer matches anything must go: the item it waited for has landed.
LEFT_TO = {
    r"\.m3-switch": "#738 rebuilds the switch",
    r"\.appearance-switch": "#738 rebuilds the switch",
    r"\.split-button": "#1059 rebuilds the split button",
    r"\.finance-converter-select-trigger": "#729 rebuilds the select, whose trigger shares this rule",
    r"^input:focus, select:focus$": "#745, extension/enrichment.css, which cancels the ring",
    r"^details\.sect>summary:focus$": "#747, the web UI's settings page, which removes it",
}


def _focus_declarations() -> list[tuple[str, str, str, str]]:
    """(file:line, selector, property, value) for every focus declaration."""
    found = []
    for sheet in authored():
        name = sheet.relative_to(ROOT).as_posix()
        for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8")):
            if FOCUS.search(selector) and PROPERTIES.fullmatch(prop):
                found.append((f"{name}:{line}", selector, prop, " ".join(value.split())))
    return found


def _ring_wrappers(found) -> set[str]:
    """Wrappers that draw the ring while a control inside them has focus."""
    return {selector.removesuffix(":focus-within") for _where, selector, prop, value in found
            if selector.endswith(":focus-within") and prop == "outline" and value in RECIPES["outline"]}


def _suppressed_under_a_ring(selector: str, wrappers: set[str]) -> bool:
    """An inner control may drop its own indicator only where its wrapper draws the ring."""
    parts = [part.strip() for part in selector.split(",")]
    return all((m := re.fullmatch(r"(.+?)\s+(?:input|select|textarea):focus", part))
               and m.group(1) in wrappers for part in parts)


def test_every_focus_indicator_is_one_of_the_two_recipes():
    found = _focus_declarations()
    assert len(found) > 50, f"only {len(found)} focus declarations were read"
    wrappers = _ring_wrappers(found)
    wrong = []
    for where, selector, prop, value in found:
        if any(re.search(pattern, selector) for pattern in LEFT_TO):
            continue
        if prop == "box-shadow":
            ok = (value.split(",")[0].strip() == "var(--focus-ring-gap)"
                  or (value == "none" and _suppressed_under_a_ring(selector, wrappers)))
        elif prop == "outline" and value in ("0", "none"):
            ok = _suppressed_under_a_ring(selector, wrappers)
        else:
            ok = value in RECIPES.get(prop, set())
        if not ok:
            wrong.append(f"{where} {selector} {{ {prop}: {value} }}")
    assert not wrong, ("focus drawn outside the two recipes; draw the outline in --focus-ring-color "
                       "at --focus-ring-offset (with --focus-ring-gap), or at calc(-1 * "
                       "var(--focus-ring-width)) for the inset:\n  " + "\n  ".join(wrong))


def test_every_rule_left_to_another_item_is_still_there():
    selectors = {selector for _where, selector, _prop, _value in _focus_declarations()}
    gone = [f"{pattern} ({reason})" for pattern, reason in LEFT_TO.items()
            if not any(re.search(pattern, selector) for selector in selectors)]
    assert not gone, f"left to another item and no longer there, so drop them from LEFT_TO: {gone}"


def test_the_recipe_is_the_tokens_and_supabases_geometry():
    tokens = (ROOT / "design" / "tokens.css").read_text(encoding="utf-8")
    declared = dict(re.findall(r"^\s*(--focus-ring[\w-]*):\s*([^;]+);", tokens, re.M))
    assert declared["--focus-ring-width"] == "2px" and declared["--focus-ring-offset"] == "2px"
    # ring-offset-background: the gap between control and ring is painted in the page's.
    assert declared["--focus-ring-gap"] == "0 0 0 var(--focus-ring-offset) var(--bg)", declared
    assert "var(--focus)" in declared["--focus-ring-color"], declared


@pytest.mark.parametrize("selector,expected", [
    (".engine-url-field input:focus", True),
    (".finance-converter-row input:focus, .finance-converter-row select:focus", True),
    (".nowhere input:focus", False),
    (".engine-url-field button:focus", False),
])
def test_an_inner_control_drops_its_ring_only_under_a_wrapper_that_draws_one(selector, expected):
    wrappers = _ring_wrappers(_focus_declarations())
    assert _suppressed_under_a_ring(selector, wrappers) is expected


@pytest.mark.parametrize("selector", [
    '.dataset-items a[aria-current="page"]:focus-visible',
    ".exports-source-card:has(input:checked):has(input:focus-visible)",
])
def test_a_ring_keeps_the_bar_that_marks_the_current_item(selector):
    """The gap is a shadow, so on an element whose resting shadow is the 3px bar that
    marks it current or checked, focus would erase the bar. These two compose it back."""
    composed = {sel: value for _where, sel, prop, value in _focus_declarations() if prop == "box-shadow"}
    assert composed.get(selector) == "var(--focus-ring-gap),inset 3px 0 var(--accent)", composed.get(selector)
