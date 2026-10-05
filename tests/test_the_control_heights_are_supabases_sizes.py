"""Each control height is one of Supabase's SIZE heights, named for it, and each control reads
the one its Supabase component defaults to (#1050).

WHERE THE VALUES COME FROM. packages/ui/src/lib/constants.ts@86c813ec:61-65 declares SIZE.height:
tiny h-[26px], small h-[34px], medium h-[38px], large h-[42px], xlarge h-[50px]. Their Button
defaults to tiny (Button.tsx@86c813ec:192); their Input to small (input.tsx@86c813ec:31), and
their SelectTrigger to SIZE_VARIANTS_DEFAULT (select.tsx@86c813ec:37-38), which is small
(constants.ts@86c813ec:111). A larger size applies only where a Supabase pattern names one, and
no control here maps to such a pattern today.

WHAT WAS TRUE BEFORE. --control-height was 2.5rem (40px), and --control-height-sm and
--control-height-xs were both 2rem (32px): none of the three on the scale, and two of them the
same value under two names.

THE READS TABLE IS AN EQUALITY, not a list of cases. A new read of a --control-height-* token
fails until it is named here with the Supabase component it is, so a control cannot arrive at
a size because the nearest example had it. KEPT names the reads that left the scale instead:
elements Supabase gives no control height, kept at the size they rendered (#1040 rule 2).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from tools.value_literals import authored, declarations

# Reads extension/ stylesheets and the design/ sources copied into extension/;
# see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"

#: packages/ui/src/lib/constants.ts@86c813ec:61-65, SIZE.height, in px.
SIZES = {"tiny": 26, "small": 34, "medium": 38, "large": 42, "xlarge": 50}

TINY = "var(--control-height-tiny)"
SMALL = "var(--control-height-small)"
# The Input inside an InputGroup sits within the group's 1px border: `-m-px`.
SMALL_INSIDE = "calc(var(--control-height-small) - 2px)"

# The Supabase component each read is, at the pin.
BUTTON = "Button.tsx@86c813ec:192 size = 'tiny'"
INPUT = "input.tsx@86c813ec:31 size = 'small'; select.tsx@86c813ec:37-38 SIZE_VARIANTS_DEFAULT"
SPLIT = "button-split-dropdown.tsx@86c813ec:14-29: two Buttons at the Button's default size"
GROUP = "input-group.tsx@86c813ec:43-48 sets no height; its InputGroupInput is an Input (:164-170)"
GROUP_INSIDE = "input-group.tsx@86c813ec:170 -m-px: the Input fills the group inside its border"

C = "design/components.css"
APP = "extension/app.css"

#: (authored sheet, selector, property) -> (the value it declares, the component that says so).
READS = {
    (C, "button, .button", "min-height"): (TINY, BUTTON),
    (C, "button.icon-button, .button.icon-button", "width"): (TINY, BUTTON),
    (C, "button.icon-button, .button.icon-button", "min-width"): (TINY, BUTTON),
    # Supabase's Button has no size below tiny, so the two smaller notches are tiny too.
    (C, "button.icon-button.compact, .button.icon-button.compact", "width"): (TINY, BUTTON),
    (C, "button.icon-button.compact, .button.icon-button.compact", "min-width"): (TINY, BUTTON),
    (C, "button.icon-button.xs, .button.icon-button.xs", "width"): (TINY, BUTTON),
    (C, "button.icon-button.xs, .button.icon-button.xs", "min-width"): (TINY, BUTTON),
    (C, "button.icon-button.xs, .button.icon-button.xs", "min-height"): (TINY, BUTTON),
    (C, "button.compact, .button.compact", "min-height"): (TINY, BUTTON),
    (C, "input, select, textarea", "min-height"): (SMALL, INPUT),
    (C, "button.chip", "min-height"): (TINY, BUTTON),
    (C, ".split-button-primary, .split-button-trigger", "min-height"): (TINY, SPLIT),
    (C, ".split-button-trigger", "width"): (TINY, SPLIT),
    (C, ".split-button-trigger", "min-width"): (TINY, SPLIT),
    ("design/grid-theme.css", "#offer-panel .record-action", "min-height"): (TINY, BUTTON),
    (APP, ".dataset-card .split-button-trigger", "width"): (TINY, SPLIT),
    (APP, ".dataset-card .split-button-trigger", "min-width"): (TINY, SPLIT),
    (APP, ".dataset-card .split-button-trigger", "min-height"): (TINY, SPLIT),
    (APP, ".engine-smart-action", "height"): (TINY, BUTTON),
    (APP, ".engine-maintenance-actions .engine-action", "min-height"): (TINY, BUTTON),
    (APP, ".engine-url-field", "min-height"): (SMALL, GROUP),
    (APP, ".engine-url-field input", "min-height"): (SMALL_INSIDE, GROUP_INSIDE),
    (APP, ".engine-url-save", "min-height"): (SMALL_INSIDE, GROUP_INSIDE),
    # The third column is the row's menu, an icon Button; the first is the face (KEPT).
    (APP, ".account-row", "grid-template-columns"): (f"2rem minmax(0, 1fr) {TINY}", BUTTON),
    (APP, ".manage-account-heading", "grid-template-columns"): (f"{TINY} minmax(0, 1fr)", BUTTON),
    (APP, "button.manage-account-back", "width"): (TINY, BUTTON),
    (APP, "button.manage-account-back", "min-width"): (TINY, BUTTON),
    (APP, ".engine-detail-heading", "grid-template-columns"): (f"{TINY} minmax(0, 1fr)", BUTTON),
    (APP, "button.engine-detail-back", "width"): (TINY, BUTTON),
    (APP, "button.engine-detail-back", "min-width"): (TINY, BUTTON),
    (APP, ".finance-number-field input", "min-height"): (SMALL, INPUT),
    (APP, ".finance-converter-row", "height"): (SMALL, GROUP),
    (APP, ".finance-converter-row input", "line-height"): (SMALL_INSIDE, GROUP_INSIDE),
    ("extension/console.css", ".map-cells", "min-height"): (TINY, BUTTON),
}

#: The reads that left the control scale, each at the size it rendered before #1050, and why.
KEPT = {
    (APP, ".engine-component", "min-height"): (
        "2rem", "a status tile (an <article>), not a control"),
    (APP, ".accounts-pill", "grid-template-columns"): (
        "minmax(0, 1fr) auto 2rem", "the column of the pill's chevron, a <span>"),
    (APP, ".accounts-pill-chevron", "width"): ("2rem", "a chevron in a <span>, not a control"),
    (APP, ".accounts-pill-chevron", "height"): ("2rem", "a chevron in a <span>, not a control"),
    (APP, ".account-face", "width"): (
        "2rem", "an Avatar, which is h-10 w-10 at avatar.tsx@86c813ec:14, not a control"),
    (APP, ".account-face", "height"): (
        "2rem", "an Avatar, which is h-10 w-10 at avatar.tsx@86c813ec:14, not a control"),
    ("scrapex/webui/static/pages/sync.css", ".sync-section-nav a", "min-height"): (
        "2rem", "an in-page section link, which Supabase gives no control size"),
    ("scrapex/webui/static/pages/overview.css", ".overview-source-more", "min-height"): (
        "2rem", "a text link, which Supabase gives no control size"),
}

#: Supabase's menu and select items declare no height, only padding and text
#: (dropdown-menu.tsx@86c813ec:104, select.tsx@86c813ec:159), so these two declare none either.
NO_HEIGHT = {(C, ".split-button-option"), (APP, ".finance-converter-option")}

TOKEN_READ = re.compile(r"--control-height")


def _px(value: str) -> float | None:
    found = re.fullmatch(r"(\d*\.?\d+)(px|rem)", value.strip())
    if not found:
        return None
    return float(found.group(1)) * (16 if found.group(2) == "rem" else 1)


def _declared_heights() -> list[tuple[str, str, str]]:
    """(file, token, value) for every --control-height* declaration, in tokens.css and in
    every sheet this repository authors, duplicates included."""
    return [(sheet.relative_to(ROOT).as_posix(), prop, value)
            for sheet in [TOKENS, *authored()]
            for _selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8"))
            if prop.startswith("--control-height")]


def _authored_declarations() -> dict[tuple[str, str, str], list[str]]:
    found: dict[tuple[str, str, str], list[str]] = {}
    for sheet in authored():
        name = sheet.relative_to(ROOT).as_posix()
        for selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8")):
            found.setdefault((name, selector, prop), []).append(value)
    return found


def test_every_control_height_is_a_supabase_size():
    """The issue's own test: the set of --control-height* values is a subset of
    {26, 34, 38, 42, 50}px. It failed on 40 and 32."""
    declared = _declared_heights()
    assert declared, "found no --control-height* declaration: the parser or tokens.css moved"
    off = [f"{name}: {token}: {value}" for name, token, value in declared
           if _px(value) not in SIZES.values()]
    assert not off, (
        "control heights that are not one of Supabase's SIZE heights "
        f"{sorted(SIZES.values())}px (constants.ts@86c813ec:61-65):\n  " + "\n  ".join(off))


def test_each_control_height_is_named_for_the_supabase_size_it_is():
    """--control-height-tiny is 26px and nothing else; a token named -sm or -xs said nothing
    about which Supabase size it was, and two of them were the same 32px."""
    declared = _declared_heights()
    wrong = [f"{name}: {token}: {value}" for name, token, value in declared
             if _px(value) != SIZES.get(token.removeprefix("--control-height-"))]
    assert not wrong, (
        "each --control-height-<size> must be Supabase's SIZE.height.<size> "
        f"{SIZES}:\n  " + "\n  ".join(wrong))


def test_each_size_is_declared_once_in_tokens_css():
    """One declaration per size, in tokens.css and nowhere else. A second, in a dark block or in
    a surface's own sheet, is what the extension's 48px override was."""
    declared = Counter((name, token) for name, token, _value in _declared_heights())
    assert declared == Counter({("design/tokens.css", "--control-height-tiny"): 1,
                                ("design/tokens.css", "--control-height-small"): 1}), declared


@pytest.mark.parametrize("where", sorted(READS), ids=lambda key: f"{key[0]} {key[1]} {key[2]}")
def test_each_control_reads_the_size_its_supabase_component_defaults_to(where):
    value, component = READS[where]
    found = _authored_declarations().get(where, [])
    assert found == [value], (
        f"{where[0]} `{where[1]}` declares {where[2]}: {found or 'nothing'}; it is {component}, "
        f"which is {value} here.")


def test_every_read_of_a_control_height_is_named_with_its_component():
    """The equality: every declaration that reads a --control-height-* token is in READS, and
    nothing in READS has stopped reading one."""
    reads = {where for where, values in _authored_declarations().items()
             if any(TOKEN_READ.search(value) for value in values)}
    assert reads == set(READS), (
        f"reads of --control-height-* and READS disagree.\n"
        f"  read, not named: {sorted(reads - set(READS))}\n"
        f"  named, not read: {sorted(set(READS) - reads)}\n"
        f"Name the control with the Supabase component it is, and read that component's "
        f"default size (#1050).")


@pytest.mark.parametrize("where", sorted(KEPT), ids=lambda key: f"{key[0]} {key[1]} {key[2]}")
def test_an_element_supabase_gives_no_control_height_keeps_its_size(where):
    value, why = KEPT[where]
    found = _authored_declarations().get(where, [])
    assert found == [value], (
        f"{where[0]} `{where[1]}` declares {where[2]}: {found or 'nothing'}; it is {why}, so "
        f"#1040 rule 2 keeps the {value} it rendered at before #1050.")


@pytest.mark.parametrize("where", sorted(NO_HEIGHT), ids=lambda key: f"{key[0]} {key[1]}")
def test_a_menu_or_select_item_declares_no_height(where):
    sheet, selector = where
    declared = {prop for (name, sel, prop) in _authored_declarations()
                if name == sheet and sel == selector}
    assert declared, f"{sheet} has no `{selector}` rule any more; update NO_HEIGHT"
    assert not declared & {"height", "min-height"}, (
        f"{sheet} `{selector}` declares a height; Supabase's item takes its height from its "
        f"padding and text (dropdown-menu.tsx@86c813ec:104, select.tsx@86c813ec:159).")


def test_the_parsers_see_the_three_surfaces():
    """A sheet that moved out of authored() would empty its rows from every test above."""
    sheets = {where[0] for where in [*READS, *KEPT]}
    found = {sheet.relative_to(ROOT).as_posix() for sheet in authored()}
    assert sheets <= found, sorted(sheets - found)
