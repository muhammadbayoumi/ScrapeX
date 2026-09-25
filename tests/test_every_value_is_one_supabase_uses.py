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

from tools.sync_design_assets import ASSETS
from tools.value_literals import (FROZEN, SUPABASE, _without_tokens, allowances, allowed, authored,
                                  declarations, is_mono, literals, offenders)

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
    (".log pre { font-size: 0.875rem; }", [("font-size", "0.875rem", True)]),
    (".label, pre { font-size: 0.875rem; }", [("font-size", "0.875rem", False)]),
    (":is(.label, code) { font-size: 0.875rem; }", [("font-size", "0.875rem", False)]),
    ("pre + .caption { font-size: 0.875rem; }", [("font-size", "0.875rem", False)]),
    # A token is not a literal, and neither is zero; the literal beside a token is.
    (".a { padding: var(--sp-2) 7px 0; }", [("spacing", "7px", False)]),
    (".a { margin: 0; z-index: 0; }", []),
    # A negative margin is judged by its magnitude.
    (".a { margin: -0.375rem 6px; }", [("spacing", "-0.375rem", True), ("spacing", "6px", True)]),
    # 18px is in no scale and no atom of theirs; only the approved half step of --spacing
    # (2px) admits it. 7px sits on Tailwind's own quarter step, which the ruling does not.
    (".a { padding: 18px 7px; line-height: 18px; }",
     [("spacing", "18px", True), ("spacing", "7px", False), ("line-height", "18px", True)]),
    # The `font` shorthand states a weight, a size and a line height, and each is judged.
    (".a { font: 600 .73rem/1.35 sans-serif; }",
     [("font-size", ".73rem", False), ("line-height", "1.35", False), ("font-weight", "600", True)]),
    (".a { font: 0.8125rem/1.4 var(--font); }", [("font-size", "0.8125rem", True), ("line-height", "1.4", True)]),
    (".a { font: inherit; }", []),
    # A token size still marks where the size is, so the literals around it are read.
    (".a { font: 650 var(--fs)/1.37 var(--font); }", [("line-height", "1.37", False), ("font-weight", "650", False)]),
    (".a { font: 650 var(--fs) var(--font); }", [("font-weight", "650", False)]),
    (".a { font: 2vw/1.37 serif; }", [("font-size", "2vw", False), ("line-height", "1.37", False)]),
    # A var() goes whole, whatever its fallback holds.
    (".a { padding: var(--gap, calc(1px + 2px)) 7px; }", [("spacing", "7px", False)]),
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


@pytest.mark.parametrize("selector,mono", [
    ("pre", True), ("code", True), ("kbd", True), ("samp", True), (".font-mono", True),
    (".code-content", True), (".log pre", True), ("pre > .line", True), (":is(code) .x", True),
    ("pre, code", True), ("pre.script", True), ("pre::before", True), ("pre .a + .b", True),
    (":is(pre, code) .x", True), (":where(pre) .x", True), ('pre[data-x="a,b"]', True),
    (".label", False), (".label:not(code)", False), ("p:not(pre)", False), (".label, pre", False),
    (".precode", False), ("code-block", False),
    # The element styled is the last compound; only what it sits inside counts.
    (":is(.label, code)", False), (":where(pre, .label)", False), (".label:not(:is(code))", False),
    (".card:has(code)", False), ("pre + .caption", False), ("code ~ p", False), ('.x[title="code"]', False),
])
def test_the_mono_context_is_code_and_only_code(selector, mono):
    """Their mono ramp is defined on code, pre, kbd, samp, .code-content and .font-mono,
    and inherits inside them. A rule is mono only when every selector in its list is."""
    assert is_mono(selector) is mono


@pytest.mark.parametrize("value", ["var(--gap, calc(1px + 2px))", "var(--gap, max(4px, 1vw))",
                                   "var(--ring, color-mix(in srgb, red 50%, blue))", "var(--a, var(--b, 3px))",
                                   "var(--unclosed, calc(1px"])
def test_a_token_goes_whole_whatever_its_fallback_holds(value):
    assert _without_tokens(f"{value} 7px").strip() in ("7px", "")


def test_the_step_comes_from_the_reading_and_the_ruling():
    """Doubling --spacing in the reading doubles the step: 18px, allowed only by the step
    at 0.25rem, is refused at 0.5rem. The ruling's half is applied to what was read."""
    assert 18.0 not in RULES["spacing"], "18px is an atom now; pick a value only the step allows"
    assert RULES["spacing_step_px"] == READING["axes"]["spacing"]["spacing_rem"] * 16 / 2
    doubled = json.loads(json.dumps(READING))
    doubled["axes"]["spacing"]["spacing_rem"] *= 2
    assert allowed("spacing", ".a", "padding", "18px", allowances(doubled)) is False
    assert allowed("spacing", ".a", "padding", "18px", RULES) is True


def test_every_stylesheet_is_either_read_or_named_as_not_ours():
    """The frozen list is written by the scan it checks, so a scan narrowed and re-frozen
    would empty the guard. Every sheet in the three asset folders is read, or is a synced
    copy, a vendor file or design/tokens.css, each named for why."""
    copies = {copy.resolve() for destinations in ASSETS.values() for copy in destinations}
    read = {sheet.resolve() for sheet in authored()}
    unread = [sheet.relative_to(ROOT).as_posix()
              for folder in ("design", "extension", "scrapex/webui/static")
              for sheet in sorted((ROOT / folder).rglob("*.css"))
              if sheet.resolve() not in read | copies
              and "vendor" not in sheet.parts and sheet != ROOT / "design" / "tokens.css"]
    assert not unread, f"stylesheets the literal scan does not read: {unread}"
    assert all(declarations(sheet.read_text(encoding="utf-8")) for sheet in authored()), (
        "an authored sheet parses to no declarations")


PROBE = """
.a { padding: 7px 8px; margin-inline-start: 7px; gap: 9px !important; }
.a { font-size: .73rem; font-size: .73rem; font: 650 var(--fs)/1.37 var(--font); }
.a { border-radius: 7px; z-index: 777; transition: opacity .12s cubic-bezier(0.2, 0, 0, 1); }
.a { animation: spin 1.4s linear infinite; line-height: 1.33em; }
@media (min-width: 1px) { .a:focus-visible { outline: 3px solid; outline-offset: 5px; } }
pre { font-size: .875rem; }
"""
PROBED = {
    "duration": {"probe.css": {".12s": 1, "1.4s": 1}},
    "easing": {"probe.css": {"cubic-bezier(0.2, 0, 0, 1)": 1}},
    "focus": {"probe.css": {"3px": 1, "5px": 1}},
    "font-size": {"probe.css": {".73rem": 2}},
    "font-weight": {"probe.css": {"650": 1}},
    "line-height": {"probe.css": {"1.33em": 1, "1.37": 1}},
    "radius": {"probe.css": {"7px": 1}},
    "spacing": {"probe.css": {"7px": 2, "9px": 1}},
    "z-index": {"probe.css": {"777": 1}},
}


def test_the_scan_reports_every_axis_a_sheet_hard_codes(tmp_path):
    """One offender on every axis, in a longhand, a shorthand, a logical side, behind
    !important, twice, inside @media and in a :focus rule: the scan the frozen list is
    written from misses none, so narrowing it anywhere and re-freezing goes red here."""
    sheet = tmp_path / "probe.css"
    sheet.write_text(PROBE, encoding="utf-8")
    assert offenders(READING, [sheet]) == PROBED


def test_the_default_scan_reads_every_authored_sheet(monkeypatch):
    """The frozen list comes from offenders() with no sheets given, so that path is the
    one watched: it must parse every authored sheet, whole."""
    import tools.value_literals as scan

    read = []
    parse = scan.declarations
    monkeypatch.setattr(scan, "declarations", lambda css: read.append(css) or parse(css))
    offenders(READING)
    assert read == [sheet.read_text(encoding="utf-8") for sheet in authored()], (
        f"the default scan parsed {len(read)} sheets of {len(authored())}")


def test_the_reading_holds_what_the_roadmap_cites():
    """The values #1040's roadmap cites for this guard, each read from its file at the pin."""
    axes, atoms = READING["axes"], READING["atoms"]
    assert axes["spacing"]["spacing_rem"] == 0.25 and axes["spacing"]["tailwind_multiplier"] == 0.25
    assert axes["spacing"]["declared"]["--spacing-content"] == "21px"
    assert axes["spacing"]["declared"]["--spacing-scale"] == "2px"
    assert axes["radius"]["declared"]["--radius-panel"] == "6px"
    assert axes["radius"]["declared"]["--radius-4xl"] == "2rem"
    assert axes["font-size"]["sans"]["--text-xs"] == "0.75rem"
    assert axes["font-size"]["sans"]["--text-sm"] == "0.8125rem"
    assert axes["font-size"]["mono"]["--text-sm"] == "0.875rem"
    assert axes["font-weight"]["declared"]["--font-weight-normal (theirs)"] == "450"
    assert axes["font-weight"]["declared"]["--font-weight-normal (mono)"] == "400"
    assert axes["duration"]["declared"]["--default-transition-duration"] == "150ms"
    assert "cubic-bezier(0.16, 1, 0.3, 1)" in axes["easing"]["declared"].values()
    assert axes["focus"]["declared"] == {
        "focus-ring ring width": "2px", "focus-ring ring offset": "2px",
        "focus-inset outline-width": "2px", "focus-inset outline-offset": "-2px"}
    assert atoms["spacing"]["5.5px"]["first"] == "packages/ui/src/components/shadcn/ui/badge.tsx:7"
    assert "11px" in atoms["font-size"] and "50" in atoms["z-index"] and "200ms" in atoms["duration"]


def test_a_reading_that_finds_nothing_stops():
    from tools.read_supabase_values import _block, _one

    with pytest.raises(SystemExit):
        _one({}, "their spacing")
    with pytest.raises(SystemExit):
        _block(".a { }", "@theme")
