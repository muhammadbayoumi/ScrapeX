"""Every duration and easing curve in a stylesheet here is a motion token, or an exception
this file names with its reason (#718).

The audit counted 9 distinct durations and 7 distinct curves shipped where the system
named 3 and 2. The #699 guard (tests/test_every_value_is_one_supabase_uses.py) cannot
hold this: it allows any literal Supabase uses, so `200ms` passes it, and it reads no
keyword, so a bare `ease` passes it too. This one asks for the token itself.

THE TOKENS ARE THE PIN'S VALUES. --ease and --ease-travel are the two curves in
packages/config/css/animations.css@86c813ec (:17-21, :29); --dur-fast, --dur and
--dur-slow are durations it uses. #1040's roadmap adds the Button's rung, `ease-out
duration-200` (packages/ui/src/components/Button/Button.tsx@86c813ec:20-21), as
--dur-200 and --ease-out, ease-out being Tailwind's (theme.css@v4.2.4:435). A third,
--ease-in-out, is the curve every `transition-*` utility of theirs draws when it names
none (--default-transition-timing-function, theme.css@v4.2.4:493): it is what a bare
`ease` here becomes, and what their disclosure chevron draws
(packages/ui/src/components/shadcn/ui/accordion.tsx@86c813ec:47, `transition-transform
duration-200`).

WHAT IS NOT JUDGED. Zero (`0s`) takes no time, so there is no step of a scale to name.
The curve of an item whose duration is zero is never drawn (`visibility 0s linear
var(--dur)` flips at the end of its delay). A transition that names no curve draws CSS's
`ease` implicitly; the audit did not count those and this guard does not read an absence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.value_literals import (
    SUPABASE,
    _split,
    _without_tokens,
    allowances,
    authored,
    declarations,
)

# Guards stylesheets the extension ships; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"
READING = json.loads(SUPABASE.read_text(encoding="utf-8"))

MOTION = re.compile(r"(?:transition|animation)(?:-(?:duration|delay|timing-function))?")
TIME = re.compile(r"-?\d*\.?\d+(?:ms|s)", re.IGNORECASE)
CURVE = re.compile(r"(?:cubic-bezier|steps|linear)\(.*\)|ease-in-out|ease-in|ease-out|ease|linear|step-start|step-end",
                   re.IGNORECASE)
TOKEN = re.compile(r"var\(\s*(--[\w-]+)", re.IGNORECASE)
VAR = re.compile(r"(?<![\w-])var\(", re.IGNORECASE)
MATH = re.compile(r"(?:calc|min|max|clamp)\(", re.IGNORECASE)
INSIDE = re.compile(r"(?<![\w.#-])-?\d*\.?\d+(?:ms|s)(?![\w-])", re.IGNORECASE)

#: Rules this change leaves to the item that rebuilds them, each named. An entry that
#: excuses nothing any more must go: the item it waited for has landed.
LEFT_TO = {
    r"\.m3-switch": "#738 rebuilds the switch",
    r"\.schedule-switch": "#738 rebuilds the switch",
    r"\.rail-indicator": "#1062 rebuilds the rail as Supabase's Sidebar (sidebar.tsx@86c813ec:236)",
    r"\.bar-fill": "#720 rebuilds the bars as progress.tsx and lineLoading (animations.css@86c813ec:44)",
    r"\.checking-bar": "#720 merges the second indeterminate bar into the first",
    r"\.skeleton": "#720 rebuilds it as Supabase's Skeleton (skeleton.tsx@86c813ec:4, animate-pulse)",
}

#: Literals that stay, each with why: (sheet, selector, property, value).
EXCEPTIONS = {
    ("design/components.css", "*, *::before, *::after", "animation-duration", "0.01ms !important"):
        "the reduced-motion reset collapses every animation; a switch, not a step of the scale",
    ("design/components.css", "*, *::before, *::after", "transition-duration", "0.01ms !important"):
        "the reduced-motion reset collapses every transition; a switch, not a step of the scale",
}


def _zero(literal: str) -> bool:
    return float(re.match(r"-?\d*\.?\d+", literal).group(0)) == 0


def judge(prop: str, value: str) -> list[str]:
    """What one motion declaration states that is not a motion token. A token is read
    whole, fallback and all, as the #699 scan reads it; a calc() states the literals
    written beside its tokens."""
    if not MOTION.fullmatch(prop):
        return []
    wrong = []
    for _separator, item in _split(value.replace("!important", ""), ","):
        if item.lower() == "none":
            continue
        parts = [piece for _before, piece in _split(item, " \t\n")]
        # The first time an item states is its duration: a literal, a token or a calc().
        durations = [part for part in parts if TIME.fullmatch(part) or MATH.match(part)
                     or (TOKEN.match(part) and TOKEN.match(part).group(1).startswith("--dur"))]
        still = bool(durations) and TIME.fullmatch(durations[0]) is not None and _zero(durations[0])
        for part in parts:
            tokens: list[str] = []
            rest = _without_tokens(part, VAR, removed=tokens)
            wrong += [f"{token} is not a motion token" for token in tokens
                      if not TOKEN.match(token).group(1).startswith(("--dur", "--ease"))]
            if MATH.match(part) or TIME.fullmatch(part):
                wrong += [f"duration {literal}" for literal in INSIDE.findall(rest) if not _zero(literal)]
            elif CURVE.fullmatch(part) and not still:
                wrong.append(f"curve {part}")
    return wrong


def _motion() -> list[tuple[str, str, str, str, int, list[str]]]:
    """(sheet, selector, property, value, line, what is wrong) for every motion declaration."""
    found = []
    for sheet in authored():
        name = sheet.relative_to(ROOT).as_posix()
        for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8")):
            if MOTION.fullmatch(prop):
                found.append((name, selector, prop, value, line, judge(prop, value)))
    return found


def _left(selector: str) -> bool:
    return any(re.search(pattern, selector) for pattern in LEFT_TO)


def test_every_duration_and_curve_in_a_stylesheet_is_a_token():
    found = _motion()
    assert len(found) > 75, f"only {len(found)} motion declarations were read"
    wrong = [f"{name}:{line} {selector} {{ {prop}: {value} }} -- {', '.join(what)}"
             for name, selector, prop, value, line, what in found
             if what and not _left(selector) and (name, selector, prop, value) not in EXCEPTIONS]
    assert not wrong, ("motion written as a literal; read --dur-fast, --dur, --dur-200 or --dur-slow, "
                       "and --ease, --ease-travel, --ease-out or --ease-in-out:\n  " + "\n  ".join(wrong))


def test_every_rule_left_to_another_item_still_needs_it():
    found = _motion()
    idle = [f"{pattern} ({reason})" for pattern, reason in LEFT_TO.items()
            if not any(what and re.search(pattern, selector) for _n, selector, _p, _v, _l, what in found)]
    assert not idle, f"left to another item and excusing nothing, so drop them from LEFT_TO: {idle}"


def _reduced_motion_blocks(css: str) -> str:
    """The inside of every `@media (prefers-reduced-motion: reduce)` block."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    inside = []
    for found in re.finditer(r"@media[^{]*prefers-reduced-motion\s*:\s*reduce[^{]*\{", css):
        depth, end = 1, found.end()
        while end < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        inside.append(css[found.end():end - 1])
    return "\n".join(inside)


def test_every_exception_is_still_there_and_only_under_reduced_motion():
    """The sentinel is allowed because it switches motion off for a reader who asked for
    that; the same literal outside the reduced-motion block would be a duration."""
    for (sheet, selector, prop, value), reason in EXCEPTIONS.items():
        css = (ROOT / sheet).read_text(encoding="utf-8")
        assert (selector, prop, value) in {(s, p, v) for s, p, v, _l in declarations(css)}, (
            f"{sheet} no longer has {selector} {{ {prop}: {value} }} ({reason}); drop it from EXCEPTIONS")
        assert (selector, prop, value) in {(s, p, v) for s, p, v, _l in declarations(_reduced_motion_blocks(css))}, (
            f"{sheet} {selector} {{ {prop}: {value} }} is excused as {reason!r} and is not under "
            "@media (prefers-reduced-motion: reduce)")


def _declared() -> dict[str, list[str]]:
    code = re.sub(r"/\*.*?\*/", "", TOKENS.read_text(encoding="utf-8"), flags=re.DOTALL)
    declared: dict[str, list[str]] = {}
    for name, value in re.findall(r"(--(?:dur|ease)[\w-]*)\s*:\s*([^;]+);", code):
        declared.setdefault(name, []).append(" ".join(value.split()))
    return declared


def test_the_motion_tokens_are_the_values_supabase_renders():
    declared = _declared()
    assert declared == {
        "--dur-fast": ["0.1s"], "--dur": ["0.15s"], "--dur-200": ["200ms"], "--dur-slow": ["0.25s"],
        # animations.css@86c813ec:17-21 (things that appear) and :29 (things that travel).
        "--ease": ["cubic-bezier(0.16, 1, 0.3, 1)"], "--ease-travel": ["cubic-bezier(0.87, 0, 0.13, 1)"],
        # Tailwind's, theme.css@v4.2.4:435 and :436 (= :493, the default transition curve).
        "--ease-out": ["cubic-bezier(0, 0, 0.2, 1)"], "--ease-in-out": ["cubic-bezier(0.4, 0, 0.2, 1)"],
    }, declared
    curves = READING["axes"]["easing"]["declared"]
    assert declared["--ease-out"] == [curves["--ease-out"]] and declared["--ease-in-out"] == [curves["--ease-in-out"]]
    # The Button's rung is the duration their components render most.
    atoms = READING["atoms"]["duration"]
    assert max(atoms, key=lambda value: atoms[value]["count"]) == "200ms", atoms
    assert atoms["200ms"]["first"] == "packages/ui/src/components/Button/Button.tsx:21"


def test_every_motion_token_is_a_value_supabase_uses():
    rules = allowances(READING)
    for name, (value,) in _declared().items():
        if name.startswith("--dur"):
            ms = float(value.removesuffix("ms")) if value.endswith("ms") else float(value.removesuffix("s")) * 1000
            assert round(ms, 4) in rules["duration"], f"{name}: {value} is no duration Supabase uses"
        else:
            assert value in rules["easing"], f"{name}: {value} is no curve Supabase uses"


def test_the_notice_names_every_curve_and_duration_the_tokens_ship():
    """design/supabase.NOTICE.txt item 4 accounts for the motion values; a token added
    without it makes the statement of changes describe less than ships."""
    notice = " ".join(NOTICE.read_text(encoding="utf-8").split())
    for name, (value,) in _declared().items():
        assert value in notice, f"{name}: {value} ships in design/tokens.css and the notice does not name it"


@pytest.mark.parametrize("prop,value,expected", [
    # The issue's own break: the chevron's literal duration and its bare curve.
    ("transition", "transform 200ms ease", ["duration 200ms", "curve ease"]),
    ("transition", "transform var(--dur-200) var(--ease-in-out)", []),
    ("transition", "opacity var(--dur) var(--ease), width .12s var(--ease)", ["duration .12s"]),
    ("transition", "border-color var(--dur-fast) EASE", ["curve EASE"]),
    ("transition", "none", []),
    ("transition", "opacity var(--dur) var(--ease) !important", []),
    # Zero takes no time; the curve of a zero-length item is never drawn.
    ("transition-delay", "0s", []),
    ("transition", "visibility 0s linear var(--dur-slow)", []),
    ("transition", "visibility 0s linear .2s", ["duration .2s"]),
    # A curve after a token duration is drawn, whatever the delay.
    ("transition", "visibility var(--dur) linear 0s", ["curve linear"]),
    ("transition", "opacity var(--dur) ease-in-out, transform var(--dur) ease-out",
     ["curve ease-in-out", "curve ease-out"]),
    ("transition-timing-function", "ease-in", ["curve ease-in"]),
    ("transition-timing-function", "steps(4, end)", ["curve steps(4, end)"]),
    ("transition-timing-function", "cubic-bezier(.2, 0, 0, 1)", ["curve cubic-bezier(.2, 0, 0, 1)"]),
    ("animation-timing-function", "linear(0, 0.5 50%, 1)", ["curve linear(0, 0.5 50%, 1)"]),
    ("animation", "pulse 1.4s ease-in-out infinite", ["duration 1.4s", "curve ease-in-out"]),
    ("animation", "spin var(--dur) linear infinite", ["curve linear"]),
    # A keyword inside an animation's name is not a curve.
    ("animation", "ease-pulse var(--dur-slow) var(--ease) infinite", []),
    ("animation-delay", "-250ms", ["duration -250ms"]),
    ("animation-duration", "0.01ms", ["duration 0.01ms"]),
    # A token is read whole, fallback and all, but it must be a motion token.
    ("transition", "opacity var(--dur, 200ms) var(--ease)", []),
    ("transition", "opacity var(--sp-2) var(--ease)", ["var(--sp-2) is not a motion token"]),
    # A calc() states the literals beside its tokens, and the tokens it reads.
    ("transition", "opacity calc(var(--dur) * 2) var(--ease)", []),
    ("transition", "opacity calc(100ms + var(--dur)) var(--ease)", ["duration 100ms"]),
    ("transition-delay", "calc(var(--gap) * 1s)", ["var(--gap) is not a motion token", "duration 1s"]),
    # A calc() in the duration's place is a duration, so the curve after it is drawn.
    ("transition", "visibility calc(0s + var(--dur)) linear 0s", ["curve linear"]),
    # Not a motion property.
    ("transform", "rotate(180deg)", []),
], ids=lambda value: value if isinstance(value, str) else None)
def test_each_motion_value_is_judged(prop, value, expected):
    assert judge(prop, value) == expected
