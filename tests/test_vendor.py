"""Vendored third-party assets are present, whole, and licensed.

ScrapeX is local-first: it must work on a machine with no internet. A page that
fetched a library from a CDN would fail exactly when the owner is offline — the
one condition the product promises to survive — and would let a third party
change what runs on their machine without a commit. So the bytes are in the
repository, and these tests are what stop them from silently going missing,
being truncated by a bad checkout, or losing their licence text.
"""
from __future__ import annotations

from pathlib import Path

import pytest

VENDOR = Path(__file__).resolve().parent.parent / "scrapex" / "webui" / "static" / "vendor"
TEMPLATES = Path(__file__).resolve().parent.parent / "scrapex" / "webui" / "templates"

# name -> (minimum plausible size, a string that must appear in it)
EXPECTED = {
    "tabulator.min.js": (300_000, "Tabulator"),
    "tabulator.min.css": (15_000, "tabulator"),
    "tabulator.LICENSE.txt": (500, "MIT"),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_vendored_file_is_present_and_whole(name):
    """A truncated file is worse than a missing one: the page loads, the grid
    silently does not, and nothing says why."""
    path = VENDOR / name
    assert path.is_file(), f"{name} is not vendored — the Datasets grid cannot load offline"
    minimum, marker = EXPECTED[name]
    data = path.read_bytes()
    assert len(data) >= minimum, f"{name} is {len(data)} bytes — truncated?"
    assert marker.encode() in data or marker.lower().encode() in data.lower()


def test_the_licence_travels_with_the_code():
    """MIT requires the notice to be distributed with the software. Shipping the
    minified file and dropping its licence is a licence violation, not an
    oversight."""
    licence = (VENDOR / "tabulator.LICENSE.txt").read_text(encoding="utf-8")
    assert "MIT" in licence
    assert "Copyright" in licence


def test_nothing_in_the_ui_loads_code_from_the_internet():
    """The whole reason the bytes are vendored. A CDN reference anywhere here
    would break the offline promise and hand a third party the ability to change
    what runs on the owner's machine."""
    offenders = []
    for template in TEMPLATES.glob("*.html"):
        text = template.read_text(encoding="utf-8")
        for host in ("cdn.", "unpkg.com", "jsdelivr", "cdnjs", "googleapis.com/ajax"):
            if host in text:
                offenders.append(f"{template.name}: {host}")
    assert offenders == [], f"remote code referenced: {offenders}"


def test_the_datasets_page_loads_the_grid_from_our_own_origin():
    page = (TEMPLATES / "datasets.html").read_text(encoding="utf-8")
    assert '/static/vendor/tabulator.min.js' in page
    assert '/static/vendor/tabulator.min.css' in page


def test_the_data_page_uses_the_grid_from_our_own_origin():
    """The owner overruled the earlier "no grid on the Data page" rule after
    seeing what a header menu, drag-resize and drag-reorder actually buy. What
    does NOT change is where the bytes come from: our origin, never a CDN.

    The URL-as-question property that argued against a grid is kept where it
    still pays — the watch tiles, saved views and the offer history are all
    still plain links — while the table itself is now a grid.
    """
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    assert "/static/vendor/tabulator.min.js" in page
    assert "/static/grid.js" in page


def test_the_grid_script_is_served_from_our_origin_too():
    script = (VENDOR.parent / "grid.js")
    assert script.is_file(), "the Data page loads /static/grid.js"
    body = script.read_text(encoding="utf-8")
    assert "http://" not in body and "https://" not in body, (
        "the grid must not reach the internet at runtime")


def test_the_grid_features_panel_is_keyboard_operable_by_construction():
    """A real <details> with real checkboxes, not a custom popup: it opens and
    closes with the keyboard for free, and every toggle is a control that tabs.
    Building that from divs is where keyboard support usually gets lost."""
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert "<details id=\"grid-features\"" in page
    assert page.count('type="checkbox" data-feature=') >= 6


def test_feature_choices_are_per_source_not_global():
    """A commodity table and a shop table do not want the same shape, so one
    global preference would be wrong for one of them."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "scrapex-features" in script and "mount.dataset.source" in script


def test_a_total_is_only_offered_where_a_total_means_something():
    """Summing prices across different currencies and units would be a number
    with no referent. The count is what is shown for anything not plainly
    additive."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert 'topCalc = "avg"' in script and 'topCalc = "count"' in script


# ---- the grid must not change how the table LOOKS ---------------------------
#
# Tabulator ships a light theme with every colour hardcoded — #fff rows, #efefef
# stripes, #bbb hover — and exposes no CSS variables to redirect. Inside a dark
# page that rendered as light-grey rows on a dark surface: the table's colours
# changed because its renderer changed, which is not a thing a renderer may do.

THEME = VENDOR.parent / "grid-theme.css"


def test_the_grid_theme_is_loaded_after_the_library():
    """Order is the whole mechanism. Loaded first, every rule loses."""
    for page in ("source.html", "datasets.html"):
        markup = (TEMPLATES / page).read_text(encoding="utf-8")
        assert markup.index("grid-theme.css") > markup.index("tabulator.min.css"), (
            f"{page} loads the theme before the library it overrides")


def test_the_grid_binds_to_the_projects_variables_not_its_own_colours():
    """Every colour comes from the same variables the project's own table rules
    use, so a grid table and a plain table cannot drift apart."""
    css = THEME.read_text(encoding="utf-8")

    for token in ("var(--surface)", "var(--text)", "var(--line)", "var(--muted)"):
        assert token in css
    # No literal colour may be introduced here.
    import re
    literals = re.findall(r":\s*(#[0-9a-fA-F]{3,8})\b", css)
    assert literals == [], f"hardcoded colours in the grid theme: {literals}"


def test_every_hardcoded_row_colour_the_library_sets_is_overridden():
    """Named explicitly, because a library update that adds one more will show
    through, and the failure is silent — it just looks wrong."""
    css = THEME.read_text(encoding="utf-8")

    assert ".tabulator-row.tabulator-row-even" in css, "the library's zebra"
    assert "tabulator-selectable:hover" in css, "the library's #bbb hover"
    assert "tabulator-calcs" in css, "the library's totals row"
    assert "tabulator-placeholder" in css


def test_striping_is_off_unless_the_owner_asks_for_it():
    """The project's tables have no zebra. Turning it on by default was mine,
    not the owner's."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "stripe: false}" in script.replace(" ", "").replace("\n", " ") or \
           "stripe: false" in script


def test_a_preference_saved_under_the_old_defaults_cannot_resurrect_them():
    """The storage key is versioned. Otherwise a browser that saved
    stripe:true keeps showing stripes, and "clear your storage" is not an
    answer to "why did the table change"."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "scrapex-features-v2-" in script


# ---- the five defects the owner reported on the live grid -------------------

def test_a_capability_switch_does_not_also_choose_the_column():
    """Turning grouping ON used to group the table immediately, by a column the
    server guessed. That made one control do two things: allow grouping, AND
    decide what by. The switch allows; the column chooses."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "payload.tree && payload.tree.by" not in script, (
        "the server's guess is back — switching the feature on will silently group")
    assert "if (features.tree && groupedBy)" in script


def test_grouping_and_nesting_are_separate_capabilities():
    """The owner drew the distinction: a GROUP is a synthetic band above rows
    carrying a count; a TREE nests real rows inside one column. Different
    questions, so different controls — both per column."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert 'data-feature="rows"' in page, "no switch for nested rows"
    assert "dataTree" in script and "dataTreeChildField" in script
    assert "Nest rows by this column" in script and "Group by this column" in script


def test_the_two_hierarchies_cannot_be_on_at_once():
    """Bands above rows that are themselves nested is two hierarchies stacked;
    neither reads. Choosing one clears the other rather than rendering both."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert 'if (groupedBy) { treeBy = ""' in script
    assert 'if (treeBy) { groupedBy = ""' in script


def test_no_colour_the_library_chose_survives_into_the_table():
    """The library paints its group counts red and its scrollbars light. Red
    means failure in this project, and the scrollbars were the one part of the
    dark table still drawn in light mode."""
    css = THEME.read_text(encoding="utf-8")
    assert ".tabulator-row.tabulator-group span" in css, "the library's red count"
    assert "scrollbar-color" in css and "::-webkit-scrollbar-thumb" in css
    import re
    literals = re.findall(r":\s*(#[0-9a-fA-F]{3,8})", css)
    assert literals == [], f"hardcoded colours in the grid theme: {literals}"


def test_a_table_too_wide_for_its_column_can_still_be_scrolled_to():
    """overflow-x was hidden to kill a 15px phantom scrollbar. That also removed
    the real one, so columns past the edge became unreachable. The phantom is
    handled by reserving the gutter; the real overflow gets its scrollbar."""
    css = THEME.read_text(encoding="utf-8")
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "overflow-x: hidden" not in css, "columns past the edge are unreachable again"
    assert "overflow-x: auto" in css
    assert "scrollbar-gutter: stable" in css, "without this the phantom bar returns"
    # fitColumns shrinks without limit unless the columns have a floor, and then
    # nothing ever overflows — the scrollbar above would be dead code.
    assert "columnDefaults" in script and "minWidth" in script


def test_a_tree_heading_never_speaks_for_its_children():
    """The first build promoted the set's FIRST row to be the branch, which made
    Andorra the face of all 169 diesel rows — one arbitrary country's price
    presented as the heading for every country, and Andorra itself then missing
    from the children. A heading carries the shared value and a count; every
    other cell is empty, because no single value stands for the set."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "_children: set}" in script.replace(", ", "").replace("_branch: set.length", "") or \
           "_children: set," in script, "the whole set must become the children"
    assert "Object.assign({}, set[0], {_children" not in script, (
        "a real row is being promoted to a heading again")
    assert "_branch" in script and "branchCount" in script


def test_a_heading_row_offers_no_link_to_a_record_it_does_not_have():
    """A heading has no offer_id, so a History link on it pointed at
    /offer/undefined — a control that looks live and leads nowhere."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "if (!cell.getValue()) return \"\";" in script
