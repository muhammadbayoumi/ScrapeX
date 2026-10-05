"""Every focus indicator in a stylesheet here is one of Supabase's two recipes (#721).

Their `focus-ring` is a 2px ring at a 2px offset painted in the background, and their
`focus-inset` a 2px outline at minus its width, for a control flush inside a container
that clips (packages/config/css/utilities.css@86c813ec:196-208). Here the outline draws
the ring and a shadow, `--focus-ring-gap`, paints the offset; design/tokens.css holds
the colour, the gap and the two geometry tokens once, and every rule that draws focus
reads them. Before this, 72 declarations held 24 distinct values: widths of 2px and
3px, eleven colours, and offsets of 2px, 1px, -2px and -3px.

A focused field also moves its border, and only its colour: Supabase's Input paints
`focus:border-control-hover`, their neutral control border, beside the ring
(packages/ui/src/components/shadcn/ui/input.tsx@86c813ec:15). Here that is
--line-control-hover, and no focus rule paints a border in the brand or the ring (#748).
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
#: Every property that can change how a border looks, on any side and in either writing
#: mode: its colour, width and style, and a border image, so a focus rule cannot reach
#: the border through a shorthand, a longhand or one side. The radius is not read:
#: Supabase's focus-inset sets one (utilities.css@86c813ec:206).
BORDER = (r"border(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?(?:-(?:color|width|style))?"
          r"|border-image(?:-(?:source|slice|width|outset|repeat))?")
PROPERTIES = re.compile(rf"outline(?:-(?:width|offset|color|style))?|box-shadow|{BORDER}")

#: The two recipes, as the tokens spell them.
RECIPES = {
    "outline": {"var(--focus-ring-width) solid var(--focus-ring-color)"},
    # The ring sits at its offset; the inset at minus its width.
    "outline-offset": {"var(--focus-ring-offset)", "calc(-1 * var(--focus-ring-width))"},
    # The focused field's border, in colour only and in the neutral control border:
    # `focus:border-control-hover` (input.tsx@86c813ec:15). Any other border property
    # in a focus rule, a shorthand or one side, is outside the recipe.
    "border-color": {"var(--line-control-hover)"},
}

#: Rules this change leaves to the item that rebuilds or owns them, each named. An entry
#: that no longer matches anything must go: the item it waited for has landed.
LEFT_TO = {
    r"\.m3-switch": "#738 rebuilds the switch",
    r"\.appearance-switch": "#738 rebuilds the switch",
    r"\.split-button": "#1059 rebuilds the split button",
    r"\.finance-converter-select-trigger": "#729 rebuilds the select, whose trigger shares this rule",
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


def _insets(found) -> set[str]:
    """Rules that draw the inset form: the outline at minus its width."""
    return {selector for _where, selector, prop, value in found
            if prop == "outline-offset" and value == "calc(-1 * var(--focus-ring-width))"}


def _suppressed_under_a_ring(selector: str, wrappers: set[str]) -> bool:
    """An inner control may drop its own indicator only where its wrapper draws the ring."""
    parts = [part.strip() for part in selector.split(",")]
    return all((m := re.fullmatch(r"(.+?)\s+(?:input|select|textarea):focus", part))
               and m.group(1) in wrappers for part in parts)


#: The two rules that compose the gap with the 3px bar marking the current or checked
#: item; the outline they sit beside is the shared rule's or the card's.
COMPOSED = ('.dataset-items a[aria-current="page"]:focus-visible',
            ".exports-source-card:has(input:checked):has(input:focus-visible)")


def test_every_focus_indicator_is_one_of_the_two_recipes():
    found = _focus_declarations()
    assert len(found) > 50, f"only {len(found)} focus declarations were read"
    borders = [where for where, _selector, prop, _value in found if re.fullmatch(BORDER, prop)]
    assert len(borders) >= 10, f"only {len(borders)} focused borders were read: {borders}"
    wrappers = _ring_wrappers(found)
    insets = _insets(found)
    wrong = []
    for where, selector, prop, value in found:
        if any(re.search(pattern, selector) for pattern in LEFT_TO):
            continue
        if prop == "box-shadow":
            # The gap, and after it only the inset bar a composition adds: a glow or a
            # second ring after the gap is not the recipe.
            parts = [part.strip() for part in value.split(",")]
            ok = ((parts[0] == "var(--focus-ring-gap)" and all(part.startswith("inset ") for part in parts[1:]))
                  or (value == "none" and (selector in insets or _suppressed_under_a_ring(selector, wrappers))))
        elif prop == "outline" and value in ("0", "none"):
            ok = _suppressed_under_a_ring(selector, wrappers)
        else:
            ok = value in RECIPES.get(prop, set())
        if not ok:
            wrong.append(f"{where} {selector} {{ {prop}: {value} }}")
    assert not wrong, ("focus drawn outside the two recipes; draw the outline in --focus-ring-color "
                       "at --focus-ring-offset (with --focus-ring-gap), or at calc(-1 * "
                       "var(--focus-ring-width)) for the inset, and move a focused field's "
                       "border-color, and nothing else of its border, to "
                       "var(--line-control-hover):\n  " + "\n  ".join(wrong))


def test_every_rule_that_draws_the_ring_draws_all_of_it():
    """Each declaration being a recipe value is not enough: a rule with the outline and no
    offset draws neither form, and a rule painting the gap with no outline paints a band
    and no ring. So a rule that draws the outline also places it and says what it paints
    beside it, and a rule that paints the gap also draws the outline."""
    rules: dict[tuple[str, str], dict[str, str]] = {}
    for where, selector, prop, value in _focus_declarations():
        if not any(re.search(pattern, selector) for pattern in LEFT_TO):
            rules.setdefault((where.rsplit(":", 1)[0], selector), {})[prop] = value
    wrong = []
    for (sheet, selector), declared in rules.items():
        outline, offset, shadow = declared.get("outline"), declared.get("outline-offset"), declared.get("box-shadow")
        if outline in RECIPES["outline"]:
            if offset == "var(--focus-ring-offset)":
                ok = shadow is not None and shadow.startswith("var(--focus-ring-gap)")
            else:
                ok = offset == "calc(-1 * var(--focus-ring-width))" and shadow == "none"
        else:
            ok = not (shadow or "").startswith("var(--focus-ring-gap)") or selector in COMPOSED
        if not ok:
            wrong.append(f"{sheet} {selector} {declared}")
    assert len(rules) > 30, f"only {len(rules)} focus rules were read"
    assert not wrong, "focus rules that draw part of a recipe:\n  " + "\n  ".join(wrong)


def test_every_wrapper_takes_both_its_inner_controls_ring_and_gap():
    """A wrapper draws the ring for the field inside it, so the field drops its own ring
    AND the shared rule's gap: an outline left on it draws a second ring inside the
    wrapper's, and a gap left on it paints --bg over the wrapper's border."""
    found = _focus_declarations()
    wrappers = _ring_wrappers(found)
    assert len(wrappers) >= 8, sorted(wrappers)
    dropped: dict[str, dict[str, str]] = {}
    for _where, selector, prop, value in found:
        for part in (part.strip() for part in selector.split(",")):
            if (m := re.fullmatch(r"(.+?)\s+(?:input|select|textarea):focus", part)) and m.group(1) in wrappers:
                dropped.setdefault(m.group(1), {})[prop] = value
    wrong = {wrapper: dropped.get(wrapper, {}) for wrapper in sorted(wrappers)
             if dropped.get(wrapper, {}).get("outline") not in ("0", "none")
             or dropped.get(wrapper, {}).get("box-shadow") != "none"}
    assert not wrong, f"wrappers whose inner field keeps its ring or its gap: {wrong}"


def test_a_bare_focus_rule_never_draws():
    """`:focus` matches a mouse click too, so a ring drawn on it shows where Supabase's
    `focus-visible` draws none, and a ring cancelled on it is cancelled for the keyboard
    as well (#745, #747). A bare `:focus` may only drop an inner control's own indicator
    under a wrapper that draws the ring. The border is not a ring: Supabase's Input moves
    it on `focus:` itself (input.tsx@86c813ec:15), so a bare `:focus` may set the
    recipe's border-color, which the test above holds to the neutral control border."""
    found = _focus_declarations()
    wrappers = _ring_wrappers(found)
    bare = re.compile(r":focus(?![\w-])")
    wrong = [f"{where} {selector} {{ {prop}: {value} }}" for where, selector, prop, value in found
             if bare.search(selector) and not any(re.search(pattern, selector) for pattern in LEFT_TO)
             and not (value in ("0", "none") and _suppressed_under_a_ring(selector, wrappers))
             and not (prop == "border-color" and value in RECIPES["border-color"])]
    assert not wrong, ("a bare :focus rule draws or cancels a ring, or paints a border other than "
                       "the recipe's; use :focus-visible for a ring:\n  " + "\n  ".join(wrong))


def _token_declarations() -> list[tuple[str, str, str, str]]:
    """(design/tokens.css:line, selector, token, value) for every token tokens.css declares."""
    tokens = ROOT / "design" / "tokens.css"
    return [(f"design/tokens.css:{line}", selector, prop, value)
            for selector, prop, value, line in declarations(tokens.read_text(encoding="utf-8"))
            if prop.startswith("--")]


#: A theme's whole scope and nothing below it: `:root`, `:root[data-theme="dark"]`,
#: `:root:not([data-theme="light"])`. A prefix test let `:root .field:focus-within` and
#: `:root:has(.field:focus-within)` through, and each painted the brand (#1354's gate).
THEME_SCOPE = re.compile(r":root(?:\[[^\]]*\]|:not\(\[[^\]]*\]\))*")


def _at_root(selector: str) -> bool:
    """A theme's scope, every part of a list: the selector is the root and its attributes."""
    return all(THEME_SCOPE.fullmatch(part.strip()) for part in selector.split(","))


def _recipe_tokens() -> set[str]:
    """Every token the recipes read, and every token those read where tokens.css defines
    them for a whole theme. A declaration scoped to one control is not followed: the test
    below refuses it."""
    defined: dict[str, set[str]] = {}
    for _where, selector, token, value in _token_declarations():
        if _at_root(selector):
            defined.setdefault(token, set()).update(re.findall(r"var\((--[\w-]+)", value))
    pending = {name for values in RECIPES.values() for value in values
               for name in re.findall(r"var\((--[\w-]+)", value)} | {"--focus-ring-gap"}
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        seen.add(name)
        pending |= defined.get(name, set()) - seen
    return seen


def test_no_stylesheet_redeclares_a_token_the_recipes_read():
    """The recipe guard reads the declarations, so `border-color: var(--line-control-hover)`
    passes wherever it is written. A rule that also sets --line-control-hover to the brand,
    on the field or on any ancestor, would paint the brand through a declaration the guard
    accepts: rendered, the focused #schedule-search border went rgb(63,207,142) and every
    test stayed green (#1354's tests pass). These tokens are design/tokens.css's alone."""
    names = _recipe_tokens()
    assert {"--line-control-hover", "--focus", "--focus-ring-gap", "--bg"} <= names, names
    found = [f"{sheet.relative_to(ROOT).as_posix()}:{line} {selector} {{ {prop}: {value} }}"
             for sheet in authored()
             for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8"))
             if prop in names]
    assert not found, "a stylesheet redeclares a token the focus recipes read:\n  " + "\n  ".join(found)
    # tokens.css is not one of the authored sheets above, so a rule there could scope a
    # token to one control (`.schedule-search:focus-within { --line-control-hover: … }`)
    # and paint the brand the same way. There every one is declared for a whole theme.
    themes = [(where, selector) for where, selector, token, _value in _token_declarations() if token in names]
    assert len(themes) >= len(names), themes
    scoped = [f"{where} {selector}" for where, selector in themes if not _at_root(selector)]
    assert not scoped, "design/tokens.css scopes a focus-recipe token below a theme:\n  " + "\n  ".join(scoped)


def test_every_rule_left_to_another_item_is_still_there():
    selectors = {selector for _where, selector, _prop, _value in _focus_declarations()}
    gone = [f"{pattern} ({reason})" for pattern, reason in LEFT_TO.items()
            if not any(re.search(pattern, selector) for selector in selectors)]
    assert not gone, f"left to another item and no longer there, so drop them from LEFT_TO: {gone}"


def test_the_inset_form_paints_no_gap():
    """Supabase's focus-inset has no offset to paint, and the shared rule's gap would
    spread outside a control that sits flush in a container, so each inset rule clears it."""
    found = _focus_declarations()
    insets = _insets(found)
    assert len(insets) >= 16, sorted(insets)
    cleared = {selector for _where, selector, prop, value in found if prop == "box-shadow" and value == "none"}
    assert not insets - cleared, f"inset rules that leave the gap painted: {sorted(insets - cleared)}"


def test_a_ring_left_to_another_item_clears_the_gap_where_it_sits_inside():
    """A rule left to another item keeps its own ring, but the shared rule's gap reaches its
    control all the same. Where that ring sits inside the control, at a negative offset,
    nothing is drawn around the gap: it paints a --bg band over whatever the control sits
    flush against, as it did over the split button's border until its trigger cleared it.
    Only a rule that draws on the focused element itself counts; a ring drawn on a sibling
    (a switch's track after its hidden input) is not where the shared rule paints."""
    rules: dict[tuple[str, str], dict[str, str]] = {}
    for where, selector, prop, value in _focus_declarations():
        if any(re.search(pattern, selector) for pattern in LEFT_TO):
            rules.setdefault((where.rsplit(":", 1)[0], selector), {})[prop] = value
    inside = {(sheet, selector): declared for (sheet, selector), declared in rules.items()
              if selector.endswith(":focus-visible") and declared.get("outline-offset", "").startswith("-")}
    assert inside, ("no rule left to another item draws its ring inside any more; this test "
                    "held the split button's trigger (#1059) and can go")
    wrong = [f"{sheet} {selector} {declared}" for (sheet, selector), declared in inside.items()
             if declared.get("box-shadow") != "none"]
    assert not wrong, "rings left to another item that sit inside and leave the gap painted:\n  " + "\n  ".join(wrong)


def test_the_recipe_is_the_tokens_and_supabases_geometry():
    tokens = (ROOT / "design" / "tokens.css").read_text(encoding="utf-8")
    declared = dict(re.findall(r"^\s*(--focus-ring[\w-]*):\s*([^;]+);", tokens, re.M))
    assert declared["--focus-ring-width"] == "2px" and declared["--focus-ring-offset"] == "2px"
    # ring-offset-background: the gap between control and ring is painted in the page's.
    assert declared["--focus-ring-gap"] == "0 0 0 var(--focus-ring-offset) var(--bg)", declared
    # ring-ring: the token at full strength, with no opacity modifier (#746).
    assert declared["--focus-ring-color"] == "var(--focus)", declared


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
