"""Every hard-coded size, weight, duration and layer in a stylesheet here is one Supabase
uses, or it is frozen where it stands today and may only go (#699).

Colour already had this guard (tests/test_vendor.py); these axes had none, and nothing
stopped the next PR adding `font-size: .73rem`. Supabase cannot write one: Tailwind
resolves every class at build time. This repository ships CSS with no build step, so a
test is the only place the rule can live.

What Supabase uses is read at the pin by tools/read_supabase_values.py. What this
repository hard-codes is read by tools/value_literals.py, and the literals Supabase does
not use today are frozen in tests/fixtures/value-literals-frozen.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.value_literals import FROZEN, SUPABASE, allowances, allowed, authored, declarations, literals, offenders

# Guards stylesheets the extension ships; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
READING = json.loads(SUPABASE.read_text(encoding="utf-8"))
RULES = allowances(READING)


def test_no_literal_arrives_that_supabase_does_not_use():
    now, frozen = offenders(READING), json.loads(FROZEN.read_text(encoding="utf-8"))
    grown = [f"{name}: {axis} {value} x{count}" for axis, files in now.items()
             for name, values in files.items() for value, count in values.items()
             if count > frozen.get(axis, {}).get(name, {}).get(value, 0)]
    assert not grown, (
        "hard-coded values Supabase does not use at the pin:\n  " + "\n  ".join(grown)
        + "\nUse the token, or a value tests/fixtures/supabase-value-axes.json holds.")


def test_the_frozen_list_only_shrinks():
    now, frozen = offenders(READING), json.loads(FROZEN.read_text(encoding="utf-8"))
    gone = [f"{name}: {axis} {value} x{count}" for axis, files in frozen.items()
            for name, values in files.items() for value, count in values.items()
            if now.get(axis, {}).get(name, {}).get(value, 0) < count]
    assert not gone, (
        "frozen literals that are no longer there:\n  " + "\n  ".join(gone)
        + "\nRun `python tools/value_literals.py --freeze` so the list cannot grow back.")


def test_the_reading_is_at_the_pin_and_whole():
    notice = (ROOT / "design" / "supabase.NOTICE.txt").read_text(encoding="utf-8")
    pin = re.search(r"^\s*Commit\s+([0-9a-f]{40})", notice, re.M).group(1)
    assert READING["commit"] == pin, (
        f"the value axes were read at {READING['commit'][:8]} and the notice pins {pin[:8]}; "
        "run tools/read_supabase_values.py")
    assert READING["tailwind"].startswith("4."), READING["tailwind"]
    assert READING["atoms_read"] >= 100, (
        f"only {READING['atoms_read']} of their component sources were read")
    empty = [axis for axis, values in READING["atoms"].items() if not values]
    assert not empty, f"their components render nothing on {empty}; the class pattern broke"


def test_the_scan_reads_the_authored_sheets_and_not_the_copies():
    names = {sheet.relative_to(ROOT).as_posix() for sheet in authored()}
    assert "design/components.css" in names and "extension/app.css" in names, names
    assert not names & {"extension/components.css", "scrapex/webui/static/components.css",
                        "design/tokens.css", "extension/tokens.css"}, names
    assert not any("vendor" in name for name in names), names


def _judge(css: str) -> list[tuple[str, str, bool]]:
    """(axis, literal, allowed) for every literal in a snippet of CSS."""
    return [(axis, literal, allowed(axis, selector, prop, literal, RULES))
            for selector, prop, value, _line in declarations(css)
            for axis in ("spacing", "radius", "font-size", "line-height", "font-weight",
                         "duration", "easing", "z-index", "focus")
            for literal in literals(axis, prop, value)]


@pytest.mark.parametrize("css,expected", [
    # #699's own two breaks: an off-step padding, and a size no ramp holds.
    (".a { padding: 7px; }", [("spacing", "7px", False)]),
    (".a { font-size: .73rem; }", [("font-size", ".73rem", False)]),
    # 0.875rem is their MONO text-sm, so it passes inside code and fails on a sans label.
    ("pre { font-size: 0.875rem; }", [("font-size", "0.875rem", True)]),
    (".font-mono .x { font-size: 0.875rem; }", [("font-size", "0.875rem", True)]),
    (".label { font-size: 0.875rem; }", [("font-size", "0.875rem", False)]),
    (".label { font-size: 0.8125rem; }", [("font-size", "0.8125rem", True)]),
    # A token is not a literal, and neither is zero; the literal beside a token is.
    (".a { padding: var(--sp-2) 7px 0; }", [("spacing", "7px", False)]),
    (".a { margin: 0; z-index: 0; }", []),
    # Their step is half of --spacing, magnitude alone.
    (".a { margin: -0.375rem 6px; }", [("spacing", "-0.375rem", True), ("spacing", "6px", True)]),
    # color-mix() percentages are proportions of a colour, not lengths.
    (".a:focus-visible { outline: 2px solid color-mix(in srgb, var(--accent) 70%, transparent); }",
     [("focus", "2px", True)]),
    (".a:focus-visible { outline-offset: 3px; }", [("focus", "3px", False)]),
    (".a { outline-offset: 3px; }", [("focus", "3px", True)]),
    # A comment is not a declaration.
    (".a { /* padding: 7px; */ gap: 8px; }", [("spacing", "8px", True)]),
    (".a { transition: opacity .15s cubic-bezier(0.16, 1, 0.3, 1); }",
     [("duration", ".15s", True), ("easing", "cubic-bezier(0.16, 1, 0.3, 1)", True)]),
    (".a { transition: opacity .12s cubic-bezier(0.2, 0, 0, 1); }",
     [("duration", ".12s", False), ("easing", "cubic-bezier(0.2, 0, 0, 1)", False)]),
    (".a { line-height: 1.4; font-weight: 450; }", [("line-height", "1.4", True), ("font-weight", "450", True)]),
    (".a { line-height: 1.35; font-weight: 750; }", [("line-height", "1.35", False), ("font-weight", "750", False)]),
    (".a { border-radius: 6px; z-index: 50; }", [("radius", "6px", True), ("z-index", "50", True)]),
    (".a { border-radius: 50%; z-index: 120; }", [("radius", "50%", False), ("z-index", "120", False)]),
], ids=lambda value: value if isinstance(value, str) else None)
def test_each_axis_is_judged_against_what_supabase_uses(css, expected):
    assert _judge(css) == expected


def test_a_declaration_keeps_its_own_line_and_selector():
    css = ".a {\n  color: red;\n}\n/* a\ncomment */\n@media (x) {\n  pre .b {\n    padding: 7px;\n  }\n}\n"
    assert [(s, p, line) for s, p, _v, line in declarations(css)] == [
        (".a", "color", 2), ("pre .b", "padding", 8)]


SCALES = {"spacing": 0.25, "radius": {"--radius": "0.25rem", "--radius-md": "0.375rem"},
          "font-size": {"--text-sm": "0.8125rem", "--text-xs": "0.75rem"},
          "line-height": {"--leading-tight": "1.25"},
          "font-weight": {"--font-weight-normal": "450", "--font-weight-medium": "500"}}


@pytest.mark.parametrize("axis,token,value", [
    ("spacing", "p-1.5", "0.375rem"),
    ("spacing", "px-[5.5px]", "5.5px"),
    ("spacing", "mt-px", "1px"),
    ("spacing", "gap-x-2", "0.5rem"),
    ("radius", "rounded", "0.25rem"),
    ("radius", "rounded-md", "0.375rem"),
    ("radius", "rounded-full", "full"),
    ("radius", "rounded-[calc(var(--radius)-5px)]", "calc(var(--radius)-5px)"),
    ("font-size", "text-sm", "0.8125rem"),
    ("font-size", "text-[11px]", "11px"),
    ("font-size", "text-foreground", None),
    ("line-height", "leading-5", "1.25rem"),
    ("line-height", "leading-none", "1"),
    ("font-weight", "font-normal", "450"),
    ("duration", "duration-200", "200ms"),
    ("z-index", "z-50", "50"),
    ("z-index", "-z-10", "-10"),
    ("z-index", "z-[60]", "60"),
])
def test_a_class_of_theirs_resolves_to_the_value_it_renders(axis, token, value):
    from tools.read_supabase_values import CLASS, _resolve

    if value is not None:
        assert CLASS[axis].fullmatch(token), f"{token} is not read as a {axis} class"
    resolved = _resolve(axis, token if axis == "z-index" else token.lstrip("-"), SCALES)
    assert resolved == value


def test_the_lockfile_names_the_tailwind_packages_ui_resolves():
    from tools.read_supabase_values import tailwind_version

    lock = ("importers:\n\n  apps/www:\n    dependencies:\n      tailwindcss:\n"
            "        specifier: ^3.4.1\n        version: 3.4.1\n\n  packages/ui:\n    dependencies:\n"
            "      react:\n        specifier: ^19\n        version: 19.2.6\n      tailwindcss:\n"
            "        specifier: 'catalog:'\n        version: 4.2.4\n\n  packages/ui-patterns:\n")
    assert tailwind_version(lock) == "4.2.4"
    with pytest.raises(SystemExit):
        tailwind_version(lock.replace("  packages/ui:", "  packages/other:"))


@pytest.mark.parametrize("css", [".a { padding: 7px; ", ".a { padding: 7px; } }"], ids=["unclosed", "overclosed"])
def test_a_sheet_whose_braces_do_not_balance_fails_the_read(css):
    """A brace the parse miscounts moves every later declaration into the wrong rule, and
    the mono context with it, so the read refuses rather than guesses."""
    with pytest.raises(ValueError):
        declarations(css)
