"""The Console's inspect screen, RENDERED — the gap this repository named.

WHY IT IS WORTH THE MACHINERY. The Console is where all six sheets are read and
edited, and until now its only proof was static analysis plus one manual pass in
a browser (#186). `docs/HANDOFF-resume-the-migration.md` has carried "No DOM
test for the Console" as a named gap since it was written.

THE FAILURE THIS SHAPE OF SCREEN HAS. `showTable` appends its sections in order:

    Fields → Sources → Mappings → Export views → Ribbon

and they are appended by one function, in one pass. A throw anywhere in the
middle stops everything after it WITHOUT AN ERROR ON SCREEN — the owner opens a
table, sees Fields and Sources, and concludes the table has no export views and
no ribbon entry. Nothing static can see that; the page has to be built.

It is not idle worry. #197 replaced the Mappings block with 195 lines of new DOM
and merged with every guard green, having never once been drawn. The Data page
did exactly that two days earlier and was broken in production the whole time.

WHAT THESE TESTS ARE FOR, so the file does not sprawl. What only a rendered page
settles: that the screen is whole, that no row is dropped between the sheet and
the card, and that the layout claims made in CSS survive to computed style. The
sentence rules underneath are pure and are tested pure, without a browser, in
extension/tests/datamap-view.test.mjs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Guards the extension: this file reads extension/ sources, so a change there
# must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

pytest.importorskip("playwright", reason="needs the browser extra")
from playwright.sync_api import sync_playwright  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tabpage_harness as harness  # noqa: E402

#: One table fed by TWO profiles, because that is the shape #197 draws one card
#: per and the shape a single card would have to lie about. The blank
#: PROFILE_KEY on the first source is not decoration: a blank resolves to the
#: ENTITY, which is the rule `resolvedProfiles` keeps — and the reason the
#: mappings for that profile are keyed T_BITUMEN and not "".
WORKBOOK = {
    "1.TableDefinition": [
        {"ENTITY_KEY": "T_BITUMEN", "DISPLAY_NAME": "Bitumen",
         "ENTITY_TYPE": "COST", "STORAGE_STRATEGY": "MergeUpsert",
         "LICENSE_TIER": "Standard", "IS_ACTIVE": "TRUE"},
        {"ENTITY_KEY": "T_UNMAPPED", "DISPLAY_NAME": "Nothing maps here",
         "ENTITY_TYPE": "REF", "STORAGE_STRATEGY": "ReplaceAll",
         "LICENSE_TIER": "Free", "IS_ACTIVE": "TRUE"},
    ],
    "2.SchemaRule": [
        {"ENTITY_KEY": "T_BITUMEN", "ATTRIBUTE_KEY": "ITEM_CODE",
         "DATA_TYPE": "TEXT", "IS_PK": "TRUE", "ORDINAL_POS": "1"},
        {"ENTITY_KEY": "T_BITUMEN", "ATTRIBUTE_KEY": "PRICE",
         "DATA_TYPE": "DECIMAL", "SEMANTIC_ROLE": "PRICE", "ORDINAL_POS": "2"},
        {"ENTITY_KEY": "T_BITUMEN", "ATTRIBUTE_KEY": "CURRENCY",
         "DATA_TYPE": "TEXT", "ORDINAL_POS": "3"},
    ],
    "3.DataSource": [
        {"SOURCE_KEY": "S_BITUMEN", "TARGET_ENTITY_KEY": "T_BITUMEN",
         "PROFILE_KEY": "", "SOURCE_URI": "https://example.test/a.csv",
         "SOURCE_REGION": "MAIN", "IS_ACTIVE": "TRUE"},
        {"SOURCE_KEY": "S_BITUMEN_ALT", "TARGET_ENTITY_KEY": "T_BITUMEN",
         "PROFILE_KEY": "P_ALT", "SOURCE_URI": "https://example.test/b.csv",
         "SOURCE_REGION": "ALT", "IS_ACTIVE": "TRUE"},
    ],
    "4.DataMap": [
        {"PROFILE_KEY": "T_BITUMEN", "TARGET_ATTRIBUTE_KEY": "ITEM_CODE",
         "SOURCE_TYPE": "Header", "MATCH_MODE": "Exact",
         "SOURCE_EXPRESSION": "Item Code", "TRANSFORM_CHAIN": "TRIM|UPPER"},
        {"PROFILE_KEY": "T_BITUMEN", "TARGET_ATTRIBUTE_KEY": "PRICE",
         "SOURCE_TYPE": "Header", "MATCH_MODE": "StartsWith",
         "SOURCE_EXPRESSION": "Unit Price", "TRANSFORM_CHAIN": "TRIM|TO_DECIMAL"},
        {"PROFILE_KEY": "T_BITUMEN", "TARGET_ATTRIBUTE_KEY": "CURRENCY",
         "SOURCE_TYPE": "Constant", "MATCH_MODE": "",
         "SOURCE_EXPRESSION": "SAR", "TRANSFORM_CHAIN": ""},
        {"PROFILE_KEY": "P_ALT", "TARGET_ATTRIBUTE_KEY": "ITEM_CODE",
         "SOURCE_TYPE": "Index", "MATCH_MODE": "",
         "SOURCE_EXPRESSION": "0", "TRANSFORM_CHAIN": ""},
    ],
    "5.ExportViews": [
        {"VIEW_KEY": "V_BITUMEN", "ENTITY_KEY": "T_BITUMEN", "LABEL": "Bitumen",
         "COLUMNS": "ITEM_CODE,PRICE", "IS_ACTIVE": "TRUE"},
    ],
    "6.RibbonControls": [
        {"ITEM_KEY": "R_BITUMEN", "CONTROL_KEY": "mnuCost", "REGION": "MAIN",
         "ACTION_CLASS": "LoadTable", "ACTION_TAG": "T_BITUMEN",
         "LABEL": "Bitumen", "ORDER": "1", "IS_ACTIVE": "TRUE"},
    ],
}

#: Every section `showTable` appends, in the order it appends them. The point of
#: naming all five is the failure described at the top of this file: the screen
#: stops at the throw, so only the LAST one proves the ones before it ran.
#:
#: A SUBSEQUENCE, NOT THE WHOLE LIST, and both reasons are real behaviour rather
#: than slack. "Mappings" appears once PER PROFILE, so a two-profile table shows
#: it twice; and a table with findings against it gains "How this table is
#: written" at the end. Pinning the list exactly would make this test fail for a
#: second profile, which is the very shape #197 was built to draw.
SECTIONS = ["Fields", "Sources", "Mappings", "Export views", "Ribbon"]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture(scope="module")
def served():
    with harness.serve_extension() as base:
        yield base


@pytest.fixture()
def inspect(browser, served):
    """Open the Console, click a table, and return the page on its inspect screen.

    `table=None` stops at the workbook screen — which is where a REFUSED
    workbook stays, so waiting for a table list there would time out on the one
    path that is behaving correctly.
    """
    pages = []

    def opener(table="T_BITUMEN", *, rows=None, refused=False, **stub_kwargs):
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(
            harness.console_stub(WORKBOOK if rows is None else rows,
                                 **stub_kwargs))
        page.goto(f"{served}/console.html")
        pages.append(page)
        page.js_errors = errors

        # The workbook arrives over two awaited round trips before anything is
        # drawn. Wait for what proves both landed, rather than for a clock.
        if refused:
            page.wait_for_function(
                "document.getElementById('workbook-state').className"
                ".includes('err')", timeout=10_000)
            return page

        # ATTACHED, not visible: the Console opens on its overview and every
        # other view is hidden until its rail tab is pressed. Waiting for the
        # list to be VISIBLE waits for a click this fixture has not made yet.
        page.wait_for_selector("#tables-list button.pair-row",
                               state="attached", timeout=10_000)
        if table:
            page.click("#cv-tab-tables")
            page.locator("#tables-list button.pair-row",
                         has_text=table).first.click()
            # ATTACHED again, and this one matters. `showView("inspect")` is the
            # LAST line of `showTable`, so a throw anywhere above it leaves the
            # sections built but the screen never switched. Waiting for VISIBLE
            # would fail here as a timeout — and a guard whose failure message
            # is a stopwatch teaches nobody what broke. `assert_whole` says it.
            page.wait_for_selector("#inspect-body .card", state="attached",
                                   timeout=10_000)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def headings(page):
    return page.locator("#inspect-body h2").all_inner_texts()


def assert_whole(page):
    """Every section of `showTable` reached the screen, in order — and the
    screen is on screen.

    `showView("inspect")` is the last line of `showTable`. A throw above it
    builds the sections into a view that is never revealed, so the owner presses
    a table and NOTHING HAPPENS — no error, no half-drawn page, no clue.
    """
    assert page.locator("#inspect-body").is_visible(), (
        "the table was pressed and the inspect screen never appeared — "
        "showTable threw before its final showView(\"inspect\")")

    drawn = headings(page)
    remaining = list(SECTIONS)
    for heading in drawn:
        if remaining and heading == remaining[0]:
            remaining.pop(0)
    assert not remaining, (
        f"the inspect screen never reached {remaining[0]!r} — it drew {drawn}. "
        "A section missing from the TAIL means something above it threw and "
        "took the rest of the page with it, silently")


def card_for(page, profile):
    """The mappings card whose strip carries this profile key.

    BY KEY AND NOT BY POSITION. The cards are drawn in sorted order, so `P_ALT`
    comes first and a test reaching for "the card" by index quietly asserts
    against the wrong profile the day a key is renamed.
    """
    return page.locator("#inspect-body .map-card").filter(
        has=page.locator(".map-profile-key", has_text=profile))


def test_the_console_gets_as_far_as_a_list_of_tables(inspect):
    """The floor. Everything below assumes the page boots, reads a workbook over
    two round trips, and accepts it as the file the add-in reads — and if any of
    that is broken, every other failure in this file is a symptom of it."""
    page = inspect(table=None)

    assert page.locator("#tables-list button.pair-row").count() == 2
    assert page.locator("#workbook-identity").inner_text() == "mbiX Configuration"
    assert page.js_errors == [], f"the page threw: {page.js_errors}"


def test_the_inspect_screen_is_whole(inspect):
    """THE TEST THIS FILE EXISTS FOR.

    `showTable` appends five sections in one pass, so a throw in any of them
    truncates the screen in silence — no error, no empty state, just a page that
    ends early and reads as a table with nothing in it. Ribbon is last, which is
    why its absence is the sensitive end of this assertion."""
    page = inspect()

    assert_whole(page)
    assert page.js_errors == [], f"the page threw: {page.js_errors}"


def test_no_mapping_is_lost_between_the_sheet_and_the_card(inspect):
    """The card is drawn by looping over PROFILES and filtering the rows into
    them, not by looping over the rows. That is only complete while every row's
    profile is in the resolved set — so this counts what the sheet holds against
    what the screen shows, and would catch the day those two stop agreeing."""
    page = inspect()

    on_screen = page.locator("#inspect-body .map-row").count()
    in_sheet = len(WORKBOOK["4.DataMap"])
    assert on_screen == in_sheet, (
        f"{in_sheet} mappings in the sheet, {on_screen} rows drawn — a mapping "
        "whose profile is not in the resolved set is dropped without a word")


def test_each_profile_gets_its_own_card_carrying_its_own_key(inspect):
    """One strip per card, and the strip is a claim about every row beneath it.
    Two profiles on one table is a real shape, and one card would have to stand
    a single PROFILE_KEY over rows that do not all carry it."""
    page = inspect()

    assert page.locator("#inspect-body .map-card").count() == 2
    assert sorted(page.locator("#inspect-body .map-profile-key")
                  .all_inner_texts()) == ["P_ALT", "T_BITUMEN"]

    # Derived from the rows rendered, never a number typed beside them.
    assert card_for(page, "T_BITUMEN").locator(".map-count").inner_text() \
        == "3 rows"
    assert card_for(page, "P_ALT").locator(".map-count").inner_text() == "1 row"


def test_the_header_and_every_row_resolve_to_one_grid(inspect):
    """The template is declared once, in `--map-columns`, and read by two
    separate elements. Nothing but computed style can prove they still agree —
    and a header that has drifted from its rows is a table that mislabels every
    value under it."""
    page = inspect()

    templates = page.evaluate("""() => {
      const card = document.querySelector('.map-card');
      return [card.querySelector('.map-head'),
              ...card.querySelectorAll('.map-cells')]
        .map((node) => getComputedStyle(node).gridTemplateColumns);
    }""")

    assert len(set(templates)) == 1, (
        f"the header and its rows resolved to different grids: {templates}")


def test_a_row_says_in_words_what_its_five_cells_say_in_enums(inspect):
    page = inspect()
    row = card_for(page, "T_BITUMEN").locator(".map-row").nth(1)
    row.locator(".map-cells").click()

    said = row.locator(".map-said").inner_text().lower()
    for part in ("price", "comes from the column", "unit price", "matched",
                 "startswith", "then", "trim", "to_decimal"):
        assert part in said, f"{part!r} missing from {said!r}"


def test_a_constant_drops_the_clause_that_would_say_nothing(inspect):
    """`CURRENCY is always SAR` — no `matched`, because a constant has no name
    to look for and `matched —` is a sentence about nothing. The rule is pure
    and tested pure; this proves the DOM assembly honours it."""
    page = inspect()
    row = card_for(page, "T_BITUMEN").locator(".map-row").nth(2)
    row.locator(".map-cells").click()

    said = row.locator(".map-said").inner_text()
    assert "is always" in said and "SAR" in said, said
    assert "matched" not in said.lower(), f"a constant claimed a match: {said!r}"


def test_one_row_is_open_and_opening_another_closes_it(inspect):
    """A table where every row is shut looks inert, and a table where they all
    open at once stops being a table. Both are one function's job."""
    page = inspect()
    rows = card_for(page, "T_BITUMEN").locator(".map-cells")

    assert rows.nth(0).get_attribute("aria-expanded") == "true", (
        "no row was open — the sentence is the thing this card was redrawn for")

    rows.nth(1).click()
    assert [rows.nth(i).get_attribute("aria-expanded") for i in range(3)] \
        == ["false", "true", "false"]

    rows.nth(1).click()
    assert rows.nth(1).get_attribute("aria-expanded") == "false", (
        "pressing the open row did not close it")


def test_a_table_nothing_maps_to_still_says_so(inspect):
    """The empty state is the one path the new card does NOT draw, so it is the
    one most easily lost when a block becomes a card."""
    page = inspect("T_UNMAPPED")

    assert_whole(page)
    assert page.locator("#inspect-body .map-card").count() == 0
    assert "No mapping" in page.locator("#inspect-body").inner_text()


def test_a_workbook_that_is_not_the_add_ins_is_refused_by_tab_id(inspect):
    """The check that comes before every other check. A copy with all six tab
    NAMES looks perfect and is a file the add-in has never opened — and a
    Console that checked it would report that everything is fine about it."""
    page = inspect(table=None, refused=True,
                   tabs={"1.TableDefinition": "999999"})

    state = page.locator("#workbook-state").inner_text()
    assert "not the workbook the add-in reads" in state, state
    assert "1.TableDefinition is tab 999999 here" in state, state
    assert page.locator("#tables-list button.pair-row").count() == 0, (
        "the workbook was refused and its tables were listed anyway")
