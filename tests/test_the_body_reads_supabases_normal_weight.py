"""Body text draws at Supabase's normal weight, 450, and their mono context at 400 (#752).

WHERE THE VALUES COME FROM. apps/design-system/styles/globals.css@86c813ec:35 declares
`--font-weight-normal: 450` in its @theme block, and :61-64 puts `font-normal` and
`font-synthesis-weight: none` on body. The same file then names its mono context, `code,
.code-content, pre, kbd, samp, .font-mono` (:70-75), and resets `--font-weight-normal: 400`
inside it (:89).

WHAT WAS TRUE BEFORE. --fw-regular was 450 and body declared no weight, so every unstyled
run drew at the browser's 400 and the token was only ever used to knock a bold run back
down. Mono drew at 400 by the same accident, and at 450 wherever it sat inside one of
those knock-backs (.source-identity-meta, .build-sheet).

HOW THE RESET IS PORTED. Their mono family arrives through one class, `.font-mono`, so their
reset reaches every mono run through one selector. Here the family arrives through
`font-family: var(--font-mono)` in 34 rules across 11 sheets, and no selector of ours reaches
them all. So design/components.css carries their selector with this product's classes in it
(.tech and .code are what this product writes where they write .font-mono and
.code-content), and every other rule that sets the mono family states the mono weight itself.
A rule that sets the family and neither is reached nor states a weight fails here, by file
and line.

ONE DIFFERENCE OF SHAPE, measured in Chromium against their rules as Tailwind 4.2.4 compiles
them. Their reset re-declares the token, which moves only a run that asks for `font-normal`,
so a bare `<code>` or `.font-mono` run of theirs inherits body's 450. Here every mono run that
states no weight draws 400, which is what #752's approved acceptance asks. Which of the two
he wants is his decision, asked on the PR that added this file.

`strong` and `b` are left out of the reset, and a rule styling one may state no weight. Their
weight is the emphasis they mark up, and Supabase's reset moves only the NORMAL weight: a
`<strong class="font-mono">` of theirs stays emphasised. Headings and `th` are the same.

That the weights COMPUTE, and that 450 is drawn by the variable face rather than rounded to
400, is measured in a browser by tests/test_the_normal_weight_draws_on_both_surfaces.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from tools.value_literals import _split, authored, declarations

# Reads design/ sheets copied into extension/, and extension/ sheets; see
# tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
COMPONENTS = ROOT / "design" / "components.css"

#: Their mono context (globals.css@86c813ec:70-75), with this product's classes for theirs:
#: .tech for .font-mono and .code for .code-content.
RESET = "code, pre, kbd, samp, .tech:not(strong, b), .code:not(strong, b)"
MONO_WEIGHT = "var(--fw-regular-mono)"
SANS_WEIGHT = "var(--fw-regular)"

#: The elements whose weight is the emphasis they mark up, which the reset does not move.
EMPHASIS = {"strong", "b", "th", "h1", "h2", "h3", "h4", "h5", "h6"}

#: The values that leave the weight to the parent rather than state one.
INHERITING = {"inherit", "unset", "revert", "revert-layer"}


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


def _compound(compound: str) -> tuple[str, set[str]]:
    """A compound selector's type and its classes, outside any :not() or :has()."""
    plain = re.sub(r":(not|has)\((?:[^()]|\([^()]*\))*\)", "", compound)
    plain = re.sub(r"\[[^\]]*\]", "", plain)
    found = re.match(r"[a-zA-Z][\w-]*", plain)
    return (found.group(0).lower() if found else ""), set(re.findall(r"\.([\w-]+)", plain))


def _reset_reaches(compound: str) -> bool:
    """Whether RESET matches the element this compound selects."""
    kind, classes = _compound(compound)
    return kind in {"code", "pre", "kbd", "samp"} or (
        bool(classes & {"tech", "code"}) and kind not in {"strong", "b"})


def reached(selectors: str) -> bool:
    """Whether every selector in the list styles an element the reset reaches: the element
    itself, or one it sits inside (` ` or `>`), so it inherits the reset's 400. A sibling
    reached through `+` or `~` is beside the element, not around it."""
    for _before, selector in _split(selectors, ","):
        compounds = _split(selector, " >+~\t\n")
        if _reset_reaches(compounds[-1][1]):
            continue
        if not any(_reset_reaches(compounds[index - 1][1])
                   for index in range(len(compounds) - 1, 0, -1)
                   if compounds[index][0] in (" ", ">")):
            return False
    return True


def emphasis(selectors: str) -> bool:
    """Whether every selector in the list styles strong, b, th or a heading."""
    return all(_compound(_split(selector, " >+~\t\n")[-1][1])[0] in EMPHASIS
               for _before, selector in _split(selectors, ","))


def uncovered(path: Path) -> list[str]:
    """The rules in one sheet that set the mono family and leave its weight to the sans
    normal: neither stating a weight of their own nor reached by the reset."""
    found = []
    for selector, props in _rules(path).items():
        mono = [line for prop, value, line in props if _sets_mono(prop, value)]
        if not mono:
            continue
        # A keyword that inherits states no weight: the run takes its parent's, 450 in text.
        stated = [value.replace("!important", "").strip() for prop, value, _line in props
                  if prop in ("font-weight", "font")]
        stated = [value for value in stated if value not in INHERITING]
        name = f"{path.relative_to(ROOT).as_posix()}:{mono[0]} {selector}"
        if SANS_WEIGHT in stated:
            found.append(f"{name} -- states var(--fw-regular), the SANS normal, 450")
        # The shorthand states a weight even when it writes none: it resets it to normal.
        elif not (stated or reached(selector) or emphasis(selector)):
            found.append(name)
    return found


def test_the_body_draws_at_their_normal_weight():
    body = _rules(COMPONENTS)["body"]
    stated = {prop: value for prop, value, _line in body}
    assert stated.get("font-weight") == SANS_WEIGHT, (
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
        "selector with this product's classes in it, and :89 resets the normal weight there.")
    assert [(prop, value) for prop, value, _line in rules[RESET]] == [("font-weight", MONO_WEIGHT)]


def test_every_rule_that_sets_the_mono_family_draws_at_the_mono_weight():
    sheets = authored()
    rules = sum(1 for sheet in sheets for props in _rules(sheet).values()
                if any(_sets_mono(prop, value) for prop, value, _line in props))
    # Not vacuous: 34 rules set the mono family when this was written.
    assert rules >= 30, rules
    found = [name for sheet in sheets for name in uncovered(sheet)]
    assert not found, (
        "rules that set var(--font-mono) and leave the weight to the sans normal, so the mono "
        "run draws at 450 where Supabase's mono context draws at 400:\n  " + "\n  ".join(found)
        + f"\nState `font-weight: {MONO_WEIGHT}` in the rule, or a weight of its own.")


@pytest.mark.parametrize("selector,expected", [
    ("code", True), ("pre", True), ("kbd", True), ("samp", True),
    (".tech", True), (".code", True), ("span.tech", True), ("td.code", True),
    (".dblist .tech", True), (".x > code", True), ("code .x", True), ("pre > span", True),
    ("strong.tech", False), ("b.code", False), ("strong.tech .x", False),
    (".tech-label", False), (".codes", False), (".x code-block", False),
    ("code + .x", False), ("code ~ .x", False),
    (".x:not(.tech)", False), (".row:has(.code)", False), ("[data-x='.tech']", False),
    ("code, .x", False), ("code, .tech", True),
])
def test_the_reset_reaches_what_its_selector_matches(selector, expected):
    assert reached(selector) is expected


@pytest.mark.parametrize("selector,expected", [
    ("strong", True), (".model-table-head strong", True), (".model-legend b:not(.key-badge)", True),
    (".model-inspector-header h3", True), ("th", True), ("strong.tech", True),
    (".x", False), ("strong .x", False), ("strong, .x", False), (".strong", False),
])
def test_emphasis_is_the_element_not_its_context(selector, expected):
    assert emphasis(selector) is expected


@pytest.mark.parametrize("css,expected", [
    (".x { font-family: var(--font-mono); }", [":1 .x"]),
    (".x { font-family: var(--font-mono); font-weight: var(--fw-regular-mono); }", []),
    (".x { font-family: var(--font-mono); font-weight: var(--fw-bold); }", []),
    (".x { font-family: var(--font-mono); font-weight: var(--fw-regular); }",
     [":1 .x -- states var(--fw-regular), the SANS normal, 450"]),
    (".x { font: var(--fs-sm) var(--font-mono); }", []),
    (".x { font: inherit; font-family: var(--font-mono); }", [":1 .x"]),
    (".x { font-family: var(--font-mono); font-weight: inherit; }", [":1 .x"]),
    (".x { font-family: var(--font-mono); font-weight: unset; }", [":1 .x"]),
    (".x { font-family: var(--font-mono); font-weight: var(--fw-regular) !important; }",
     [":1 .x -- states var(--fw-regular), the SANS normal, 450"]),
    (".x { font-family: var(--font-mono); font-weight: var(--fw-regular-mono) !important; }", []),
    (".x { font-family: var(--font); }", []),
    (".x .tech { font-family: var(--font-mono); }", []),
    (".x strong { font-family: var(--font-mono); }", []),
    (".x,\n.y { font-size: 1px; font-family: var(--font-mono); }", [":2 .x, .y"]),
    ("@media (min-width: 1px) { .x { font-family: var(--font-mono); } }", [":1 .x"]),
])
def test_a_mono_rule_is_judged_by_its_own_declarations(tmp_path, css, expected, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    sheet = tmp_path / "a.css"
    sheet.write_text(css, encoding="utf-8")
    assert [name.removeprefix("a.css") for name in uncovered(sheet)] == expected
