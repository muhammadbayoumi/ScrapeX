"""Body text draws at Supabase's normal weight, 450, and their mono context re-declares that
weight as 400 for the runs that ask for it (#752).

WHERE THE VALUES COME FROM. apps/design-system/styles/globals.css@86c813ec:35 declares
`--font-weight-normal: 450` in its @theme block, and :61-64 puts `font-normal` and
`font-synthesis-weight: none` on body. The same file then names its mono context, `code,
.code-content, pre, kbd, samp, .font-mono` (:70-75), and re-declares `--font-weight-normal: 400`
inside it (:89).

WHAT THE RE-DECLARATION DOES, measured in Chromium against their rules as Tailwind 4.2.4
compiles them. It sets no weight. A run that asks for the normal weight reads the token, so
`.font-mono.font-normal`, and a `font-normal` run inside a `<code>`, compute 400. A bare
`<code>` or `.font-mono` run asks for nothing and inherits body's 450, and `<strong
class="font-mono">` stays at strong's 500. The owner ruled for this cascade on 2026-10-06:
https://github.com/muhammadbayoumi/ScrapeX/pull/1443#issuecomment-6010988915

WHAT WAS TRUE BEFORE. --fw-regular was 450 and body declared no weight, so every unstyled
run, mono or not, drew at the browser's 400, and the token was only ever used to knock a
bold run back down.

HOW IT IS PORTED. --fw-regular is their --font-weight-normal, and --fw-regular-mono holds
the 400 their mono context re-declares it to. Their mono family arrives through one class,
`.font-mono`, so every mono run of theirs is inside the context. Here the family arrives
through `font-family: var(--font-mono)` in 34 rules across 11 sheets. design/components.css
carries their selector with this product's classes in it -- tools/value_literals.py's MONO
says which classes those are, for this guard and for the value guard alike -- and every other
rule that sets the mono family re-declares the token itself. A rule that does neither fails
here, by file and line. So does a mono rule that sets the normal weight without reading the
token, and anything that reads --fw-regular-mono as a weight: each draws the same number
whether its run asks for the normal weight or not.

That the weights COMPUTE, and that 450 is drawn by the variable face rather than rounded to
400, is measured in a browser by tests/test_the_normal_weight_draws_on_both_surfaces.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from tools.value_literals import _font, _split, authored, declarations, is_mono

# Reads design/ sheets copied into extension/, and extension/ sheets; see
# tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
COMPONENTS = ROOT / "design" / "components.css"

#: Their mono context (globals.css@86c813ec:70-75), with this product's classes for theirs:
#: .tech for .font-mono and .code for .code-content.
RESET = "code, pre, kbd, samp, .tech, .code"
#: What their :89 is here: the normal weight, re-declared to the mono context's.
RE_DECLARED = ("--fw-regular", "var(--fw-regular-mono)")

#: The values that leave the weight to the parent rather than set one.
INHERITING = {"inherit", "unset", "revert", "revert-layer"}
#: The normal weight written without the token: the sans normal, the mono normal, and the
#: keyword, which is 400.
LITERAL_NORMAL = {"450", "400", "normal"}


def _root(css: str) -> str:
    return css.split(":root {", 1)[1].split("\n}", 1)[0]


def _rules(path: Path) -> dict[str, list[tuple[str, str, int]]]:
    """selector -> [(property, value, line)], for the sheet's rules in order."""
    rules: dict[str, list[tuple[str, str, int]]] = {}
    for selector, prop, value, line in declarations(path.read_text(encoding="utf-8")):
        rules.setdefault(selector, []).append((prop, value, line))
    return rules


def _sets_mono(prop: str, value: str) -> bool:
    return prop in ("font-family", "font") and "var(--font-mono)" in value


def _weight(prop: str, value: str) -> str | None:
    """What one declaration sets the weight to, or None when it sets no weight. The `font`
    shorthand sets one even when it writes none: it resets the weight to `normal`."""
    value = value.replace("!important", "").strip()
    if prop == "font-weight":
        return value
    if prop != "font":
        return None
    if value in INHERITING:
        return value
    token = re.search(r"var\(--fw-[\w-]+\)", value)
    if token:
        return token.group(0)
    if literal := _font(value)["font-weight"]:
        return literal[0]
    keyword = re.search(r"(?<![\w-])(bold|bolder|lighter)(?![\w-])", value)
    return keyword.group(1) if keyword else "normal"


def uncovered(path: Path) -> list[str]:
    """The rules in one sheet that set the mono family and are outside their mono context:
    neither reached by the reset nor re-declaring the normal weight themselves, or setting the
    normal weight as a literal, which reads no context at all."""
    found = []
    for selector, props in _rules(path).items():
        mono = [line for prop, value, line in props if _sets_mono(prop, value)]
        if not mono:
            continue
        name = f"{path.relative_to(ROOT).as_posix()}:{mono[0]} {selector}"
        weights = [weight for prop, value, _line in props
                   if (weight := _weight(prop, value)) is not None]
        if weights and weights[-1] in LITERAL_NORMAL:
            found.append(f"{name} -- sets the weight to {weights[-1]}, the normal weight "
                         "without the token; a run that asks for it reads var(--fw-regular)")
        elif not (is_mono(selector) or RE_DECLARED in [(prop, value) for prop, value, _ in props]):
            found.append(name)
    return found


def test_the_body_draws_at_their_normal_weight():
    body = _rules(COMPONENTS)["body"]
    stated = {prop: value for prop, value, _line in body}
    assert stated.get("font-weight") == "var(--fw-regular)", (
        f"design/components.css's body states font-weight {stated.get('font-weight')!r}. "
        "Supabase's body is font-normal (globals.css@86c813ec:62), --font-weight-normal 450 "
        "(:35); without it every unstyled run draws at the browser's 400.")
    assert stated.get("font-synthesis-weight") == "none", (
        "Supabase's body sets font-synthesis-weight: none (globals.css@86c813ec:64).")


def test_the_tokens_hold_both_normal_weights():
    root = _root(TOKENS.read_text(encoding="utf-8"))
    assert re.search(r"^\s*--fw-regular:\s*450;", root, re.M), "their --font-weight-normal (:35)"
    assert re.search(r"^\s*--fw-regular-mono:\s*400;", root, re.M), (
        "their --font-weight-normal inside the mono context (globals.css@86c813ec:89)")


def test_the_reset_is_their_mono_selector():
    rules = _rules(COMPONENTS)
    assert RESET in rules, (
        f"design/components.css has no `{RESET}` rule. It is globals.css@86c813ec:70-75's "
        "selector with this product's classes in it, and :89 re-declares the normal weight there.")
    assert [(prop, value) for prop, value, _line in rules[RESET]] == [RE_DECLARED], (
        f"`{RESET}` declares {rules[RESET]}. Their :89 re-declares the normal weight and sets "
        "no weight, so a bare <code> inherits body's 450 and only a run that asks for the "
        "normal weight draws 400.")
    # The guard below reads the reset's reach from tools/value_literals.py; the two agree.
    assert all(is_mono(piece) for _before, piece in _split(RESET, ",")), RESET


def test_the_mono_weight_is_read_only_where_the_normal_weight_is_re_declared():
    """--fw-regular-mono is the value their :89 writes, and nothing reads it as a weight:
    that would draw 400 whether the run asks for the normal weight or not."""
    found = [f"{sheet.relative_to(ROOT).as_posix()}:{line} {selector} {{ {prop}: {value} }}"
             for sheet in [*authored(), TOKENS]
             for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8"))
             if "--fw-regular-mono" in value and (prop, value) != RE_DECLARED]
    assert not found, (
        "var(--fw-regular-mono) read other than as `--fw-regular: var(--fw-regular-mono)`:\n  "
        + "\n  ".join(found))


def test_every_rule_that_sets_the_mono_family_is_in_their_mono_context():
    sheets = authored()
    rules = sum(1 for sheet in sheets for props in _rules(sheet).values()
                if any(_sets_mono(prop, value) for prop, value, _line in props))
    # Not vacuous: 34 rules set the mono family when this was written.
    assert rules >= 30, rules
    found = [name for sheet in sheets for name in uncovered(sheet)]
    assert not found, (
        "rules that set var(--font-mono) outside their mono context, so a run that asks for "
        "the normal weight draws 450 where Supabase's draws 400:\n  " + "\n  ".join(found)
        + f"\nRe-declare `{RE_DECLARED[0]}: {RE_DECLARED[1]};` in the rule.")


def test_no_sheet_writes_their_mono_class_names():
    """tools/value_literals.py reads .font-mono and .code-content as mono, for their ramp, but
    this product writes .tech and .code for them, and the reset carries only those. A rule
    on theirs would pass the guard above and sit outside the reset."""
    found = [f"{sheet.relative_to(ROOT).as_posix()}:{line} {selector}"
             for sheet in authored()
             for selector, _prop, _value, line in declarations(sheet.read_text(encoding="utf-8"))
             if re.search(r"\.(font-mono|code-content)(?![\w-])", selector)]
    assert not found, found


@pytest.mark.parametrize("selector,expected", [
    ("code", True), ("pre", True), ("kbd", True), ("samp", True),
    (".tech", True), (".code", True), ("span.tech", True), ("td.code", True),
    (".dblist .tech", True), (".x > code", True), ("code .x", True), ("pre > span", True),
    ("strong.tech", True), ("b.code", True), ("strong.tech .x", True),
    (".tech-label", False), (".codes", False), (".x code-block", False),
    ("code + .x", False), ("code ~ .x", False),
    (".x:not(.tech)", False), (".row:has(.code)", False), ("[data-x='.tech']", False),
    ("code, .x", False), ("code, .tech", True), (":is(code, .tech) .x", True),
])
def test_the_reset_reaches_what_its_selector_matches(selector, expected):
    assert is_mono(selector) is expected


@pytest.mark.parametrize("css,expected", [
    (".x { font-family: var(--font-mono); }", [":1 .x"]),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono); }", []),
    (".x { --fw-regular: var(--fw-regular-mono); font-family: var(--font-mono); }", []),
    (".x { font-family: var(--font-mono); --fw-regular: 400; }", [":1 .x"]),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular); }", [":1 .x"]),
    # A weight of its own does not put the rule in the context: a run inside it that asks
    # for the normal weight would still read 450.
    (".x { font-family: var(--font-mono); font-weight: var(--fw-bold); }", [":1 .x"]),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono);"
     " font-weight: var(--fw-regular); }", []),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono);"
     " font-weight: var(--fw-bold); }", []),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono);"
     " font-weight: inherit; }", []),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono);"
     " font-weight: 450; }",
     [":1 .x -- sets the weight to 450, the normal weight without the token; a run that asks "
      "for it reads var(--fw-regular)"]),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono);"
     " font-weight: 450 !important; }",
     [":1 .x -- sets the weight to 450, the normal weight without the token; a run that asks "
      "for it reads var(--fw-regular)"]),
    (".x { font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono);"
     " font-weight: 400; }",
     [":1 .x -- sets the weight to 400, the normal weight without the token; a run that asks "
      "for it reads var(--fw-regular)"]),
    (".x { font-family: var(--font-mono); font-weight: normal; }",
     [":1 .x -- sets the weight to normal, the normal weight without the token; a run that "
      "asks for it reads var(--fw-regular)"]),
    (".tech { font-family: var(--font-mono); font-weight: 450; }",
     [":1 .tech -- sets the weight to 450, the normal weight without the token; a run that "
      "asks for it reads var(--fw-regular)"]),
    # The shorthand: its weight, and the `normal` it resets the weight to when it writes none.
    (".x { --fw-regular: var(--fw-regular-mono); font: 450 var(--fs-sm) var(--font-mono); }",
     [":1 .x -- sets the weight to 450, the normal weight without the token; a run that asks "
      "for it reads var(--fw-regular)"]),
    (".x { --fw-regular: var(--fw-regular-mono); font: var(--fs-sm) var(--font-mono); }",
     [":1 .x -- sets the weight to normal, the normal weight without the token; a run that "
      "asks for it reads var(--fw-regular)"]),
    (".x { --fw-regular: var(--fw-regular-mono); font: var(--fs-sm) var(--font-mono);"
     " font-weight: var(--fw-regular); }", []),
    (".x { --fw-regular: var(--fw-regular-mono); font: var(--fw-regular) var(--fs-sm)/1.5"
     " var(--font-mono); }", []),
    (".x { --fw-regular: var(--fw-regular-mono); font: bold var(--fs-sm) var(--font-mono); }", []),
    (".x { --fw-regular: var(--fw-regular-mono); font: 600 var(--fs-sm) var(--font-mono); }", []),
    (".x { font: inherit; font-family: var(--font-mono); }", [":1 .x"]),
    (".x { font: inherit; font-family: var(--font-mono); --fw-regular: var(--fw-regular-mono); }",
     []),
    (".x { font-family: var(--font); }", []),
    (".x { font-family: var(--font); font-weight: 450; }", []),
    (".x .tech { font-family: var(--font-mono); }", []),
    ("strong.code { font-family: var(--font-mono); }", []),
    (".x strong { font-family: var(--font-mono); }", [":1 .x strong"]),
    (".x h3 { font-family: var(--font-mono); }", [":1 .x h3"]),
    (".x,\n.y { font-size: 1px; font-family: var(--font-mono); }", [":2 .x, .y"]),
    ("@media (min-width: 1px) { .x { font-family: var(--font-mono); } }", [":1 .x"]),
])
def test_a_mono_rule_is_judged_by_its_own_declarations(tmp_path, css, expected, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    sheet = tmp_path / "a.css"
    sheet.write_text(css, encoding="utf-8")
    assert [name.removeprefix("a.css") for name in uncovered(sheet)] == expected
