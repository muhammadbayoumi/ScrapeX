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
HELD names the reads that are a Supabase component but not at its default yet, each with the
issue that moves it. DEFAULT is what each component's default reads here: a READS row reads it,
and a HELD row does not, so a row cannot cite a component whose default it is not. Where a
row's selector matches extension/app.html, the element it matches is the element its component
is: a Button is a <button>, an Input an <input>, and one inside an InputGroup is the group's.

STEPS names the controls whose Supabase component defaults to a Tailwind h-N, a step of their
--spacing rather than a SIZE height, so they read the --sp-* token that step is and no
--control-height (#1430). KEPT also holds the literal heights #1430 found where no Supabase
component gives the element a control size.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from tools.value_literals import _px, _split, authored, declarations

# Reads extension/ stylesheets and the design/ sources copied into extension/;
# see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
PANEL = ROOT / "extension" / "app.html"

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
GROUP_BUTTON = ("input-group.tsx@86c813ec:122-137 InputGroupButton, a Button whose default size is "
                "tiny, h-6, 24px (:125, :130, :137)")

#: The element each component is drawn as, for the rows whose selector matches the panel's
#: markup. A Supabase InputGroup is a <div> (input-group.tsx@86c813ec:43).
ELEMENT = {BUTTON: {"button"}, INPUT: {"input", "select"}, GROUP: {"div"},
           GROUP_INSIDE: {"input"}, GROUP_BUTTON: {"button"}}

#: The value each component's default size reads here. GROUP_BUTTON has none: its default, h-6,
#: 24px, is no SIZE height but a step of their --spacing, so a row that cites it is in STEPS.
DEFAULT = {BUTTON: TINY, SPLIT: TINY, INPUT: SMALL, GROUP: SMALL, GROUP_INSIDE: SMALL_INSIDE}

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
    # A native <select> is laid out at `line-height: normal` whatever the sheet says, so it
    # takes the Select's h-[34px] as a height, not only a floor (#1430).
    (C, "select", "height"): (SMALL, INPUT),
    # So does a native date or time field, whose editor pads its own fields (#1430).
    (C, 'input[type="date"], input[type="time"]', "height"): (SMALL, INPUT),
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
    # The third column is the row's menu, an icon Button; the first is the face (KEPT).
    (APP, ".account-row", "grid-template-columns"): (f"var(--sp-7) minmax(0, 1fr) {TINY}", BUTTON),
    (APP, ".manage-account-heading", "grid-template-columns"): (f"{TINY} minmax(0, 1fr)", BUTTON),
    (APP, "button.manage-account-back", "width"): (TINY, BUTTON),
    (APP, "button.manage-account-back", "min-width"): (TINY, BUTTON),
    (APP, ".engine-detail-heading", "grid-template-columns"): (f"{TINY} minmax(0, 1fr)", BUTTON),
    (APP, "button.engine-detail-back", "width"): (TINY, BUTTON),
    (APP, "button.engine-detail-back", "min-width"): (TINY, BUTTON),
    # The third copy of the same ghost icon Button (extension/app.html `#source-edit-back`).
    (APP, ".source-edit-back", "width"): (TINY, BUTTON),
    (APP, ".source-edit-back", "min-width"): (TINY, BUTTON),
    (APP, ".finance-number-field input", "min-height"): (SMALL, INPUT),
    (APP, ".finance-converter-row", "height"): (SMALL, GROUP),
    (APP, ".finance-converter-row input", "line-height"): (SMALL_INSIDE, GROUP_INSIDE),
    ("extension/console.css", ".map-cells", "min-height"): (TINY, BUTTON),
    # #1430: the dataset picker's trigger (their combobox's Button) and the source list's
    # icon link (an icon-only Button, the panel's square).
    ("design/data-workspace.css", ".dataset-menu-trigger", "min-height"): (TINY, BUTTON),
    ("design/data-workspace.css", ".dataset-icon-button", "width"): (TINY, BUTTON),
    ("design/data-workspace.css", ".dataset-icon-button", "height"): (TINY, BUTTON),
}

#: The reads that are a Supabase component held off its default, each until the issue that
#: moves it: (authored sheet, selector, property) -> (the value it declares, the component, the
#: issue).
HELD: dict[tuple[str, str, str], tuple[str, str, str]] = {
    # Empty since #1430 brought the engine address Save, the one row here, to its
    # InputGroupButton default: it is in STEPS.
}

AVATAR = "avatar.tsx@86c813ec:14 h-10 w-10"
TOGGLE = "toggle.tsx@86c813ec:20 size default, h-10; ToggleGroup's default at toggle-group.tsx@86c813ec:11"

#: What each STEPS component's default reads here: Tailwind's h-N is N steps of their 0.25rem
#: --spacing, so h-6 is 1.5rem, --sp-5, and h-10 2.5rem, --sp-7.
STEP = {GROUP_BUTTON: "var(--sp-5)", AVATAR: "var(--sp-7)", TOGGLE: "var(--sp-7)"}

#: (authored sheet, selector, property) -> (the value it declares, the component that says so).
STEPS = {
    # `#save`, the <button> in the engine address group (extension/app.html), is Supabase's
    # InputGroupButton, h-6, 24px (input-group.tsx@86c813ec:125, :130). It was a 32px segment
    # of the group, InputGroupButton's `small` (:126), until #1430.
    (APP, ".engine-url-save", "min-height"): ("var(--sp-5)", GROUP_BUTTON),
    # The account row's face; the row's first column is the face (the test below).
    (APP, ".account-face", "width"): ("var(--sp-7)", AVATAR),
    (APP, ".account-face", "height"): ("var(--sp-7)", AVATAR),
    # Light, Dark and Device: one ToggleGroup. In the panel the touch target holds it (#1051).
    (C, ".appearance-scheme-picker button", "min-height"): ("var(--sp-7)", TOGGLE),
}

#: The reads that left the control scale, each at the size it rendered before #1050, and why.
KEPT = {
    (APP, ".engine-component", "min-height"): (
        "2rem", "a status tile (an <article>), not a control"),
    (APP, ".accounts-pill", "grid-template-columns"): (
        "minmax(0, 1fr) auto 2rem", "the column of the pill's chevron, a <span>"),
    (APP, ".accounts-pill-chevron", "width"): ("2rem", "a chevron in a <span>, not a control"),
    (APP, ".accounts-pill-chevron", "height"): ("2rem", "a chevron in a <span>, not a control"),
    ("scrapex/webui/static/pages/sync.css", ".sync-section-nav a", "min-height"): (
        "2rem", "an in-page section link, which Supabase gives no control size"),
    ("scrapex/webui/static/pages/overview.css", ".overview-source-more", "min-height"): (
        "2rem", "a text link, which Supabase gives no control size"),
    # The literal heights #1430 found and kept (#1040 rule 2).
    (APP, ".accounts-action", "min-height"): (
        "3.5rem", "a card's destination row (a <button>), which Supabase gives no control size"),
    ("design/data-workspace.css", ".data-source-overview-trigger", "min-height"): (
        "3.35rem", "a card's disclosure header (a <summary>); their AccordionTrigger declares "
                   "no height, only py-4 (accordion.tsx@86c813ec:32)"),
    ("scrapex/webui/static/webui.css", ".source-filter-trigger", "min-height"): (
        "3.4rem", "a source picker whose label is two lines, the name over its domain; their "
                  "trigger is a one-line Button, so taking its 26px drops a line: his call"),
    ("design/grid-theme.css", ".record-inspector-nav button", "width"): (
        "2.75rem", "the record inspector's icon rail; which Supabase component it is, a Button, "
                   "a Toggle or a sidebar item, is his call"),
    ("design/grid-theme.css", ".record-inspector-nav button", "min-height"): (
        "2.75rem", "the record inspector's icon rail; which Supabase component it is, a Button, "
                   "a Toggle or a sidebar item, is his call"),
}

#: Supabase's menu and select items declare no height, only padding and text
#: (dropdown-menu.tsx@86c813ec:104, select.tsx@86c813ec:159), so these two declare none either.
NO_HEIGHT = {(C, ".split-button-option"), (APP, ".finance-converter-option")}

#: A screen's rule for a Button or an Input that declares none of these, so the shared rule's
#: size is the control's (#1430): the enrichment page's fields were 40px on their own floor,
#: and the data model's zoom buttons a 40px square of their own.
SHARED_SIZE = {
    ("extension/enrichment.css", "input, select"): {
        "height", "min-height", "padding", "padding-block", "font", "font-size", "line-height"},
    ("scrapex/webui/static/pages/data-model.css", ".model-zoom .icon-button"): {
        "height", "min-height", "width", "min-width"},
}

TOKEN_READ = re.compile(r"--control-height")


def _reads_default(where: tuple[str, str, str], value: str, component: str) -> bool:
    """Whether `value` is `component`'s default here. A grid-template-columns value reads it
    when one of its tracks is it: the column a Button sits in."""
    tracks = ([track for _before, track in _split(value, " \t\n")]
              if where[2] == "grid-template-columns" else [value])
    return component in DEFAULT and DEFAULT[component] in tracks


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
    assert _reads_default(where, value, component), (
        f"{where[0]} `{where[1]}` {where[2]}: its row reads {value}, but it names {component}, "
        f"whose default reads {DEFAULT.get(component, 'no token')} here. Name the component it "
        f"is, or hold it in HELD with the issue that moves it.")
    found = _authored_declarations().get(where, [])
    assert found == [value], (
        f"{where[0]} `{where[1]}` declares {where[2]}: {found or 'nothing'}; it is {component}, "
        f"which is {value} here.")


def test_every_read_of_a_control_height_is_named_with_its_component():
    """The equality: every declaration that reads a --control-height-* token is in READS or
    HELD, and nothing in either has stopped reading one."""
    assert not set(READS) & set(HELD), sorted(set(READS) & set(HELD))
    named = set(READS) | set(HELD)
    reads = {where for where, values in _authored_declarations().items()
             if any(TOKEN_READ.search(value) for value in values)}
    assert reads == named, (
        f"reads of --control-height-* and READS | HELD disagree.\n"
        f"  read, not named: {sorted(reads - named)}\n"
        f"  named, not read: {sorted(named - reads)}\n"
        f"Name the control with the Supabase component it is, and read that component's "
        f"default size (#1050).")


@pytest.mark.parametrize("where", sorted(HELD), ids=lambda key: f"{key[0]} {key[1]} {key[2]}")
def test_a_control_held_off_its_default_names_the_issue_that_moves_it(where):
    value, component, issue = HELD[where]
    assert re.fullmatch(r"#\d+", issue), issue
    assert not _reads_default(where, value, component), (
        f"{where[0]} `{where[1]}` {where[2]}: its row reads {value}, which is {component}'s "
        f"default here, so it is not held: its row belongs in READS.")
    found = _authored_declarations().get(where, [])
    assert found == [value], (
        f"{where[0]} `{where[1]}` declares {where[2]}: {found or 'nothing'}; it is {component}, "
        f"held at {value} until {issue}. If {issue} moved it, its row belongs in READS.")


@pytest.mark.parametrize("where", sorted(STEPS), ids=lambda key: f"{key[0]} {key[1]} {key[2]}")
def test_a_control_whose_default_is_a_spacing_step_reads_that_step(where):
    """An InputGroupButton is h-6, an Avatar h-10 w-10 and a Toggle h-10: steps of Tailwind's
    --spacing, not SIZE heights, so each reads the --sp-* token its step is (#1430). A row
    cannot cite a component whose step it does not read, and none is a --control-height read,
    which READS or HELD would name."""
    value, component = STEPS[where]
    assert where not in READS and where not in HELD, where
    assert STEP.get(component) == value, (
        f"{where[0]} `{where[1]}` {where[2]}: its row reads {value}, but it names {component}, "
        f"whose default reads {STEP.get(component, 'no step')} here.")
    found = _authored_declarations().get(where, [])
    assert found == [value], (
        f"{where[0]} `{where[1]}` declares {where[2]}: {found or 'nothing'}; it is {component}, "
        f"which is {value} here.")


def test_the_account_rows_first_column_is_the_face():
    """The face and the column it sits in were two separate 2rem literals, so one could move
    without the other (#1437, finding 1). The column is the face's width."""
    columns = _authored_declarations()[(APP, ".account-row", "grid-template-columns")]
    face = _authored_declarations()[(APP, ".account-face", "width")]
    assert [_split(value, " \t\n")[0][1] for value in columns] == face, (columns, face)


def test_each_panel_read_names_the_element_its_selector_matches():
    """A row names the Supabase component its element is, so the element its selector matches
    in extension/app.html must be that component's: the engine address Save, a <button>, was
    cited as the group's Input until #1432's review. A selector that matches nothing there is
    drawn by app.js, and a grid column names the Button that sits in it, not the element the
    rule styles, so neither is read here.

    A Button and an InputGroupButton are both a <button>, so where the element sits tells them
    apart: an element inside a GROUP row's element is the group's Input or its InputGroupButton,
    and a GROUP_INSIDE or GROUP_BUTTON row's element sits inside one. The Save passed in HELD
    as a plain Button until #1432's second re-review."""
    markup = BeautifulSoup(PANEL.read_text(encoding="utf-8"), "html.parser")
    checked, grouped, wrong = set(), set(), []
    rows = {**{where: component for where, (_value, component) in READS.items()},
            **{where: component for where, (_value, component, _issue) in HELD.items()},
            **{where: component for where, (_value, component) in STEPS.items()}}
    # By identity: a bs4 Tag compares equal to any tag with the same name, attributes and
    # contents.
    groups = {id(element) for (sheet, selector, _prop), component in rows.items()
              if sheet == APP and component == GROUP for element in markup.select(selector)}
    for (sheet, selector, prop), component in sorted(rows.items()):
        if sheet != APP or prop == "grid-template-columns":
            continue
        elements = markup.select(selector)
        tags = {element.name for element in elements}
        if not tags:
            continue
        checked.add(selector)
        if not tags <= ELEMENT.get(component, set()):
            wrong.append(f"`{selector}` {prop} matches {sorted(tags)}, but its row names "
                         f"{component}, which is {sorted(ELEMENT.get(component, set()))}")
        inside = [any(id(parent) in groups for parent in element.parents) for element in elements]
        if any(inside):
            grouped.add(selector)
        if any(inside) and component not in {GROUP_INSIDE, GROUP_BUTTON}:
            wrong.append(f"`{selector}` {prop} sits inside an InputGroup but names {component}")
        if component in {GROUP_INSIDE, GROUP_BUTTON} and not all(inside):
            wrong.append(f"`{selector}` {prop} names {component}, but matches an element "
                         f"outside every GROUP row's element")
    assert not wrong, "\n  ".join(["a row names a component its element is not:", *wrong])
    # Eleven selectors match the panel's markup today; fewer means one or the parser moved.
    assert len(checked) >= 11 and ".engine-url-save" in checked, sorted(checked)
    # Three sit inside a group: the two groups' inputs and the Save. Fewer means a group's
    # selector stopped matching, and the check above stopped reading it.
    assert len(grouped) >= 3 and ".engine-url-save" in grouped, sorted(grouped)


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


@pytest.mark.parametrize("where", sorted(SHARED_SIZE), ids=lambda key: f"{key[0]} {key[1]}")
def test_a_screens_button_or_field_takes_the_shared_size(where):
    sheet, selector = where
    declared = {prop for (name, sel, prop) in _authored_declarations()
                if name == sheet and sel == selector}
    assert declared, f"{sheet} has no `{selector}` rule any more; update SHARED_SIZE"
    assert not declared & SHARED_SIZE[where], (
        f"{sheet} `{selector}` declares {sorted(declared & SHARED_SIZE[where])}; the shared "
        f"Button or Input rule in design/components.css sizes it (#1430).")


def test_the_parsers_see_the_three_surfaces():
    """A sheet that moved out of authored() would empty its rows from every test above."""
    sheets = {where[0] for where in [*READS, *HELD, *KEPT, *STEPS, *SHARED_SIZE]}
    found = {sheet.relative_to(ROOT).as_posix() for sheet in authored()}
    assert sheets <= found, sorted(sheets - found)
