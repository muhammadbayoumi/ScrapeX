"""A control's reach past its box is Supabase's hit area, and the visible box stays its size
(#1051). This is the half a stylesheet can be read for, so it runs with no browser: what a hit
area is, where one is drawn, what each read of --touch-target is for, and where a stack of
tiny Buttons stands far enough apart for two reaches. The reach a tap actually has is measured
in tests/test_panel_dom.py (the panel) and tests/test_no_reach_takes_another_controls_tap.py
(the web UI and the action cells).

THE MECHANISM IS SUPABASE'S, declaration for declaration.
packages/config/tailwind-plugins/hit-area.css@86c813ec:31-49:

    @utility hit-area-* {
      position: relative;
      --hit-area-t: --spacing(--value(number) * -1);   (and -b, -l, -r)
      &::before {
        content: '';
        position: absolute;
        top: var(--hit-area-t, 0px);
        right: var(--hit-area-r, 0px);
        bottom: var(--hit-area-b, 0px);
        left: var(--hit-area-l, 0px);
        pointer-events: inherit;
      }
    }

Its size is set for one place only, a table's action cell: hit-area-2, 8px on each side
(apps/design-system/content/docs/components/table.mdx@86c813ec:197). Everywhere else Supabase
sets no touch size, so the 44px the coarse-pointer block gave every button stays, as the reach
(#1040 rule 2).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_the_shadows_are_what_supabases_atoms_render import _rules_around
from tools.value_literals import authored, declarations

# Reads design/ sources copied into extension/ and extension/app.css; see
# tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "design" / "components.css"
TOKENS = ROOT / "design" / "tokens.css"
C = "design/components.css"
APP = "extension/app.css"
PAGES = "scrapex/webui/static/pages"

#: hit-area.css@86c813ec:43-48, the ::before's geometry. Its `content: ''` (:42) is not here:
#: a ::before with no content is not generated, so `content` is what says where one is drawn.
SUPABASE_BEFORE = {
    "position": "absolute",
    "top": "var(--hit-area-t, 0px)",
    "right": "var(--hit-area-r, 0px)",
    "bottom": "var(--hit-area-b, 0px)",
    "left": "var(--hit-area-l, 0px)",
    "pointer-events": "inherit",
}
BEFORE = "button::before, .button::before, .hit-area-2::before"
COARSE = "@media (hover: none), (pointer: coarse)"

#: Every read of --touch-target in a sheet this repository authors, and what it is. A REACH is
#: a hit area's inset: the 48px is how far a tap reaches the control on a touch screen. A BOX
#: still sizes what is drawn. THE TWO ARE AN EQUALITY with the sheets, so a new read fails until
#: it is named here, and a box that becomes a reach moves from BOX to REACH.
REACH = {
    (APP, ".sx-select-trigger", "--hit-area-t"): "Supabase's SelectTrigger, small, 34px "
                                                 "(select.tsx@86c813ec:31-38), on a touch screen",
    (APP, ".sx-select-trigger", "--hit-area-b"): "the same",
}
ROW = "a heading or a status row, not a control: no hit area, and its 48px is layout (#1040 rule 2)"
WHOLE_ROW = ("a whole row a tap toggles or opens, a <label> or a <summary>, which Supabase gives no "
             "control height: its 48px box is its reach (#1040 rule 2)")
HIS = ("#1051, his to decide: a control whose Supabase component cannot be computed, so its "
       "48px box is not moved into a reach")
BOX = {
    (C, ".appearance-switch", "width"): "the switch's own invisible 48px target around its "
                                        "40x24 track, already a reach in all but name",
    (C, ".appearance-switch", "height"): "the same",
    (APP, ".sx-select-option", "min-height"): (
        "#1051, his to decide: Supabase's SelectItem has no height (select.tsx@86c813ec:159), "
        "and its options stand 2px apart, so a 48px reach would cover its neighbours' boxes"),
    (APP, ".data-view-heading, .source-manager-heading", "min-height"): ROW,
    (APP, ".source-manager-section-head", "min-height"): ROW,
    (APP, ".source-edit-summary", "min-height"): ROW,
    (APP, ".source-edit-switch", "min-height"): WHOLE_ROW,
    (APP, ".engine-runtime-status", "min-height"): ROW,
    (APP, ".engine-connection-heading", "min-height"): ROW,
    (APP, ".settings-group-head", "min-height"): ROW,
    (APP, ".rail-indicator", "height"): "the rail's indicator, as tall as the rail item it marks",
    (APP, ".side-rail .rail-item", "width"): HIS,
    (APP, ".side-rail .rail-item", "height"): HIS,
    (APP, ".side-rail .rail-item", "min-height"): HIS,
    (APP, ".appearance-page .appearance-scheme-picker button", "min-height"): HIS,
    # Two headings and one <summary> (extension/app.html, Finance's preferences disclosure).
    (APP, ".finance-section-heading", "min-height"): WHOLE_ROW,
    (APP, ".finance-setting-row", "min-height"): WHOLE_ROW,
    (APP, ".finance-rate-state", "min-height"): ROW,
    (APP, ".finance-currency-details summary", "min-height"): WHOLE_ROW,
    (APP, ".finance-saved-state", "min-height"): ROW,
    (APP, ".workspace-menu-head", "min-height"): ROW,
    (APP, ".engine-row", "min-height"): HIS,
    (APP, ".engine-action-row", "min-height"): HIS,
}

#: Every read of --touch-stack-gap, and the stack of tiny Buttons it spaces on a touch screen
#: (his ruling on #1457). AN EQUALITY with the sheets, as REACH | BOX is: a stack that starts
#: or stops reading it fails until it is named here or taken out.
STACK_GAP = {
    (APP, "#site-search + .toolbar-spaced", "margin-block"): (
        "Run's Select all and Clear, under the site search and over the site list"),
    (APP, ".engine-detail-actions", "row-gap"): "the Engine screen's Download and Check again",
    (f"{PAGES}/overview.css", ".overview-hero-actions", "row-gap"): "/'s two hero links",
    (f"{PAGES}/exports.css", ".exports-hero-actions", "row-gap"): (
        "/exports' hero link and Open folder"),
    (f"{PAGES}/sync.css", ".sync-hero-actions, .sync-actions", "row-gap"): (
        "/sync's two hero links and its rows of actions: Copy script and Show script, and "
        "Save connection, Generate token and Revoke token"),
}


def _declared(selector: str, css: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for sel, prop, value, _line in declarations(css):
        if sel == selector:
            found.setdefault(prop, []).append(value)
    return found


def _split(css: str, at_rule: str) -> tuple[str, str]:
    """(inside, outside): the text inside every `at_rule { ... }` in `css`, braces matched, and
    the rest of the sheet without them. Comments go first, so a brace in one counts for
    nothing."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    inside, outside, last = [], [], 0
    for match in re.finditer(re.escape(at_rule) + r"\s*\{", css):
        if match.start() < last:
            continue
        depth, start = 1, match.end()
        for at in range(start, len(css)):
            depth += {"{": 1, "}": -1}.get(css[at], 0)
            if depth == 0:
                inside.append(css[start:at])
                outside.append(css[last:match.start()])
                last = at + 1
                break
    outside.append(css[last:])
    return "\n".join(inside), "\n".join(outside)


def _token(name: str) -> str:
    values = re.findall(rf"^\s*{re.escape(name)}:\s*([^;]+);", TOKENS.read_text(encoding="utf-8"),
                        flags=re.M)
    assert len(values) == 1, f"{name} is declared {len(values)} times in design/tokens.css"
    return values[0].strip()


def test_a_hit_area_is_supabases_before():
    css = COMPONENTS.read_text(encoding="utf-8")
    found = _declared(BEFORE, css)
    assert found == {prop: [value] for prop, value in SUPABASE_BEFORE.items()}, (
        f"`{BEFORE}` in {C} is not hit-area.css@86c813ec:43-48: {found}")


def test_hit_area_2_reaches_8px_past_each_side_and_is_drawn_on_every_pointer():
    css = COMPONENTS.read_text(encoding="utf-8")
    assert _token("--sp-2") == "0.5rem", "hit-area-2 is two spacing steps, 0.5rem"
    found = _declared(".hit-area-2", _split(css, COARSE)[1])
    assert found == {"position": ["relative"],
                     **{f"--hit-area-{side}": ["calc(-1 * var(--sp-2))"] for side in "trbl"}}, found
    assert _declared(".hit-area-2::before", css) == {"content": ['""']}


def test_on_a_touch_screen_the_floor_is_a_buttons_reach_and_no_buttons_box():
    """The block lifted `button, .button, input, select` to `min-height: 2.75rem`. A button's
    44px is its hit area's reach now, centred, and only an input and a select, which draw no
    ::before, keep it on the box."""
    assert _token("--touch-floor") == "2.75rem"
    coarse = _split(COMPONENTS.read_text(encoding="utf-8"), COARSE)[0]
    assert coarse, f"{C} has no `{COARSE}` block"
    reach = "min(0px, (100% - var(--touch-floor)) / 2)"
    assert _declared("button, .button", coarse) == {
        "position": ["relative"], "--hit-area-t": [reach], "--hit-area-b": [reach]}
    assert _declared("button::before, .button::before", coarse) == {"content": ['""']}
    assert _declared("input, select", coarse) == {"min-height": ["var(--touch-floor)"]}
    lifted = [(sel, value) for sel, prop, value, _line in declarations(coarse)
              if prop in {"min-height", "height"} and re.search(r"(^|[\s,])\.?button\b", sel)]
    assert not lifted, f"the coarse-pointer block sizes a button's box again: {lifted}"


def test_the_select_triggers_48px_is_a_reach_only_on_a_touch_screen():
    coarse, unconditional_css = _split((ROOT / APP).read_text(encoding="utf-8"), COARSE)
    reach = "min(0px, (100% - var(--touch-target)) / 2)"
    assert _declared(".sx-select-trigger", coarse) == {
        "--hit-area-t": [reach], "--hit-area-b": [reach]}
    unconditional = _declared(".sx-select-trigger", unconditional_css)
    assert unconditional.get("height") == ["var(--control-height-small)"], unconditional
    assert not {"--hit-area-t", "--hit-area-b"} & set(unconditional), (
        "with a mouse the trigger's box is its reach, as Supabase's is")


def test_every_read_of_touch_target_is_named_a_reach_or_a_box():
    reads = {(sheet.relative_to(ROOT).as_posix(), sel, prop)
             for sheet in authored()
             for sel, prop, value, _line in declarations(sheet.read_text(encoding="utf-8"))
             if "--touch-target" in value}
    assert not set(REACH) & set(BOX), sorted(set(REACH) & set(BOX))
    named = set(REACH) | set(BOX)
    assert reads == named, (
        f"reads of --touch-target and REACH | BOX disagree.\n"
        f"  read, not named: {sorted(reads - named)}\n"
        f"  named, not read: {sorted(named - reads)}\n"
        f"Name a new read with what it is (#1051): a hit area's reach, or a box and why.")
    for where in REACH:
        assert where[2].startswith("--hit-area-"), (
            f"{where} is named a reach but sets {where[2]}, which is not a hit area's inset")


def test_a_stack_of_tiny_buttons_stands_two_reaches_apart_on_a_touch_screen():
    """His ruling on #1457: on a touch screen stacked 26px Buttons stand 18px apart. Each
    reaches the 44px floor 9px past each edge of its box, so two reaches meet at the midpoint
    of the gap and do not overlap, which is how Supabase spaces adjacent hit areas
    (apps/design-system/content/docs/components/table.mdx@86c813ec:197). The gap is the floor
    less the box, so a change to either is a change to his 18px, and fails here."""
    assert _token("--touch-stack-gap") == "calc(var(--touch-floor) - var(--control-height-tiny))"
    floor, box = _token("--touch-floor"), _token("--control-height-tiny")
    assert (floor, box) == ("2.75rem", "26px"), (
        f"his ruling is 18px, 44 less 26, and the floor is {floor} and the box {box} now")


def test_each_stack_reads_the_gap_in_a_top_level_coarse_block_at_every_width():
    """The touch sweeps read one width, 360px, and the stacks took each other's taps at other
    widths too: / at 800, 1024 and 1280px, the panel at 320, 420 and 500px, /exports and /sync
    at 480px. So each read sits directly in a top-level `(hover: none), (pointer: coarse)`
    block, with no other rule or at-rule around it. Scoped to a width, a stack keeps
    gap-x-2's 8px at every other width, and no sweep sees it. With a mouse a stack keeps its
    own gap. A read is held with every rule around it, so a width query inside the coarse
    block, or around it, fails as one in its place does."""
    reads = [((sheet.relative_to(ROOT).as_posix(), rules[-1], prop), rules[:-1], value)
             for sheet in authored()
             for rules, prop, value in _rules_around(sheet.read_text(encoding="utf-8"), r"[\w-]+")
             if "--touch-stack-gap" in value]
    found = sorted(where for where, _around, _value in reads)
    assert found == sorted(STACK_GAP), (
        f"reads of --touch-stack-gap and STACK_GAP disagree.\n"
        f"  read: {found}\n"
        f"  named: {sorted(STACK_GAP)}\n"
        f"Name a new stack with what it holds, or take out one that no longer reads it.")
    coarse = re.sub(r"\s", "", COARSE)
    misplaced = {where: around for where, around, _value in reads
                 if [re.sub(r"\s", "", rule) for rule in around] != [coarse]}
    assert not misplaced, (
        f"a stack reads --touch-stack-gap somewhere other than directly in a top-level "
        f"`{COARSE}` block, so at some width it keeps its own gap: {misplaced}")
    other = {where: value for where, _around, value in reads if value != "var(--touch-stack-gap)"}
    assert not other, f"a stack reads something other than the gap itself: {other}"
