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

AN ICON-ONLY BUTTON IS 36x26, NOT A SQUARE (#1430; his ruling on #1457): its width is tiny's
padding around its 14px icon, so no --control-height sizes a width any more. ICON_RULES holds
the icon's size and ICON_ONLY_BOXES each such Button's own rule, which declares no width.
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
# "Test site" beside its field is a Button at size small, h-[34px], by his ruling on #1457.
BUTTON_SMALL = "Button size = 'small', constants.ts@86c813ec:62 h-[34px] (his ruling on #1457)"
INPUT = "input.tsx@86c813ec:31 size = 'small'; select.tsx@86c813ec:37-38 SIZE_VARIANTS_DEFAULT"
SPLIT = "button-split-dropdown.tsx@86c813ec:14-29: two Buttons at the Button's default size"
GROUP = "input-group.tsx@86c813ec:43-48 sets no height; its InputGroupInput is an Input (:164-170)"
GROUP_INSIDE = "input-group.tsx@86c813ec:170 -m-px: the Input fills the group inside its border"
GROUP_BUTTON = ("input-group.tsx@86c813ec:122-137 InputGroupButton, a Button whose default size is "
                "tiny, h-6, 24px (:125, :130, :137)")

#: The element each component is drawn as, for the rows whose selector matches the panel's
#: markup. A Supabase InputGroup is a <div> (input-group.tsx@86c813ec:43).
ELEMENT = {BUTTON: {"button"}, BUTTON_SMALL: {"button"}, INPUT: {"input", "select"}, GROUP: {"div"},
           GROUP_INSIDE: {"input"}, GROUP_BUTTON: {"button"}}

#: The value each component's default size reads here. GROUP_BUTTON has none: its default, h-6,
#: 24px, is no SIZE height but a step of their --spacing, so a row that cites it is in STEPS.
DEFAULT = {BUTTON: TINY, BUTTON_SMALL: SMALL, SPLIT: TINY, INPUT: SMALL, GROUP: SMALL,
           GROUP_INSIDE: SMALL_INSIDE}

C = "design/components.css"
APP = "extension/app.css"

#: (authored sheet, selector, property) -> (the value it declares, the component that says so).
READS = {
    (C, "button, .button", "min-height"): (TINY, BUTTON),
    # Supabase's Button has no size below tiny, so `xs` is tiny too. An icon-only Button's
    # width is its padding's, no --control-height (ICON_ONLY below).
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
    (APP, ".dataset-card .split-button-trigger", "min-height"): (TINY, SPLIT),
    (APP, ".engine-smart-action", "height"): (TINY, BUTTON),
    (APP, ".engine-maintenance-actions .engine-action", "min-height"): (TINY, BUTTON),
    # Test site, beside the Site URL field (extension/app.html `#check`): its own size, not its
    # row's stretch.
    (APP, "#check", "min-height"): (SMALL, BUTTON_SMALL),
    (APP, ".engine-url-field", "min-height"): (SMALL, GROUP),
    (APP, ".engine-url-field input", "min-height"): (SMALL_INSIDE, GROUP_INSIDE),
    (APP, ".finance-number-field input", "min-height"): (SMALL, INPUT),
    (APP, ".finance-converter-row", "height"): (SMALL, GROUP),
    (APP, ".finance-converter-row input", "line-height"): (SMALL_INSIDE, GROUP_INSIDE),
    ("extension/console.css", ".map-cells", "min-height"): (TINY, BUTTON),
    # #1430: the dataset picker's trigger (their combobox's Button) and the source list's
    # icon link (an icon-only Button, 36x26: its width is its padding's).
    ("design/data-workspace.css", ".dataset-menu-trigger", "min-height"): (TINY, BUTTON),
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

#: The record inspector's rail, kept by his ruling on #1457 (#1040 rule 2).
INSPECTOR = ("the record inspector's icon rail, kept until the grid rebuild (#1367) rewrites it, "
             "so it is not decided twice: #1040 rule 2, his ruling on #1457")

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
        "3.4rem", "a source picker whose label is two lines, the name over its domain: no "
                  "Supabase trigger shows two, and dropping the domain would lose what tells "
                  "similar sources apart, so it keeps both: #1040 rule 2, his ruling on #1457"),
    ("design/grid-theme.css", ".record-inspector-nav button", "width"): ("2.75rem", INSPECTOR),
    ("design/grid-theme.css", ".record-inspector-nav button", "min-height"): ("2.75rem", INSPECTOR),
}

#: Supabase's menu and select items declare no height, only padding and text
#: (dropdown-menu.tsx@86c813ec:104, select.tsx@86c813ec:159), so these two declare none either.
NO_HEIGHT = {(C, ".split-button-option"), (APP, ".finance-converter-option")}

#: A screen's rule for a Button or an Input that declares none of these, so the shared rule's
#: size is the control's (#1430): the enrichment page's fields were 40px on their own floor,
#: and the data model's zoom buttons a 40px square of their own, then a 26px one with no
#: padding. They take tiny's padding around their glyph now, as an icon-only Button does.
SHARED_SIZE = {
    ("extension/enrichment.css", "input, select"): {
        "height", "min-height", "padding", "padding-block", "font", "font-size", "line-height"},
    ("scrapex/webui/static/pages/data-model.css", ".model-zoom .icon-button"): {
        "height", "min-height", "width", "min-width", "padding", "padding-inline"},
}

#: AN ICON-ONLY BUTTON IS SUPABASE'S, 36x26 (#1430; his ruling on #1457): their "Only an icon"
#: Button (button-icon.tsx@86c813ec:5) at its tiny default, tiny's px-2.5 py-1
#: (constants.ts@86c813ec:54) around its 14px icon (Button.tsx@86c813ec:127) in the Button's
#: 1px border (:25). Its width is that padding's, so its rule declares no width but `auto`
#: and no padding of 0, which together drew the 26px square; its icon reads tiny's 14px,
#: 3.5 steps of their --spacing. The split chevron beside a primary half is #1059's.
ICON_ONLY = "Button.tsx@86c813ec:127 tiny: [&_svg]:h-[14px] [&_svg]:w-[14px]"
TINY_ICON = "calc(var(--sp-1) * 3.5)"
ICON_RULES = {
    (C, "button.icon-button .sx-icon, .button.icon-button .sx-icon"),
    (APP, ".dataset-card .split-button-trigger .sx-icon"),
    ("design/data-workspace.css", ".dataset-icon-button svg"),
}
#: The icon-only Buttons' own rules: the shared `xs` notch, the three back buttons (their
#: icon is `icon-button`'s, extension/app.html), the Data card's menu trigger and the source
#: list's icon link.
ICON_ONLY_BOXES = {
    (C, "button.icon-button.xs, .button.icon-button.xs"),
    (APP, "button.manage-account-back"),
    (APP, "button.engine-detail-back"),
    (APP, ".source-edit-back"),
    (APP, ".dataset-card .split-button-trigger"),
    ("design/data-workspace.css", ".dataset-icon-button"),
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
    # Nine selectors match the panel's markup today; fewer means one or the parser moved. The
    # three back buttons' width rows left when their width became their padding's, and Test
    # site's row arrived as a Button at size small (#1430).
    assert len(checked) >= 9 and {".engine-url-save", "#check"} <= checked, sorted(checked)
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


@pytest.mark.parametrize("where", sorted(ICON_RULES), ids=lambda key: f"{key[0]} {key[1]}")
def test_an_icon_only_buttons_icon_is_tinys_14px(where):
    found = _authored_declarations()
    sizes = {prop: found.get((*where, prop), []) for prop in ("width", "height")}
    assert sizes == {"width": [TINY_ICON], "height": [TINY_ICON]}, (
        f"{where[0]} `{where[1]}` declares {sizes}; an icon-only Button's icon is "
        f"{ICON_ONLY}, which is {TINY_ICON} here (his ruling on #1457).")


@pytest.mark.parametrize("where", sorted(ICON_ONLY_BOXES), ids=lambda key: f"{key[0]} {key[1]}")
def test_an_icon_only_buttons_width_is_its_padding(where):
    found = _authored_declarations()
    declared = {prop: found[(*where, prop)] for prop in
                ("width", "min-width", "padding", "padding-inline", "padding-inline-start",
                 "padding-inline-end", "padding-left", "padding-right") if (*where, prop) in found}
    assert any(sheet == where[0] and selector == where[1] for sheet, selector, _ in found), (
        f"{where[0]} has no `{where[1]}` rule any more; update ICON_ONLY_BOXES")
    square = {prop: values for prop, values in declared.items()
              if (prop in {"width", "min-width"} and values != ["auto"])
              or (prop.startswith("padding") and any(re.fullmatch(r"0(px)?( 0(px)?)*", value)
                                                      or value.startswith("0 ") for value in values))}
    assert not square, (
        f"{where[0]} `{where[1]}` declares {square}: an icon-only Button takes its 36px width "
        f"from tiny's px-2.5 around its 14px icon ({ICON_ONLY}), not from a width of its own.")


def test_the_parsers_see_the_three_surfaces():
    """A sheet that moved out of authored() would empty its rows from every test above."""
    sheets = {where[0] for where in [*READS, *HELD, *KEPT, *STEPS, *SHARED_SIZE, *ICON_RULES,
                                     *ICON_ONLY_BOXES]}
    found = {sheet.relative_to(ROOT).as_posix() for sheet in authored()}
    assert sheets <= found, sorted(sheets - found)
