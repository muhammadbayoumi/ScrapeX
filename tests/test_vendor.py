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

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "scrapex" / "webui" / "static" / "vendor"
TEMPLATES = ROOT / "scrapex" / "webui" / "templates"
MATERIAL_ICONS = VENDOR.parent / "material-icons"

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


def test_grid_behaviour_changes_bust_the_browser_cache():
    """Starlette supplies ETag and Last-Modified but no explicit cache policy.
    A new grid behaviour therefore needs a new URL or an open browser can keep
    running the previous script after the application has been updated."""
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    # design-system-3: menuLabel learned that "" means no icon — the strict
    # validator threw on pinMenu's blank states and killed the whole
    # three-dot menu (owner-reported live).
    assert '/static/grid.js?v=design-system-4' in page
    assert '/static/grid-theme.css?v=design-system-2' in page


def test_material_header_icons_are_local_and_dry():
    """The three shapes come from Google's Material Icons, but one local SVG
    sprite is enough; separate copies add files without adding behaviour."""
    sprite = (MATERIAL_ICONS / "material-icons.svg").read_text(encoding="utf-8")
    licence = (MATERIAL_ICONS / "material-icons.LICENSE.txt").read_text(encoding="utf-8")
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    ui = (VENDOR.parent / "ui.js").read_text(encoding="utf-8")
    expected_symbols = {
        'id="filter-list"', 'id="more-vert"', 'id="arrow-upward"',
        'id="arrow-downward"', 'id="check"', 'id="push-pin"',
        'id="fit-screen"', 'id="unfold-more"', 'id="view-stream"',
        'id="account-tree"', 'id="view-column"', 'id="restart-alt"',
        'id="unfold-less"', 'id="close"', 'id="search"',
        'id="drag-indicator"', 'id="settings"',
    }

    assert all(token in sprite for token in expected_symbols)
    assert "Apache License" in licence and "Version 2.0" in licence
    assert "window.ScrapeXUI.icon" in script
    assert "material-icons.svg" in ui
    assert not list(MATERIAL_ICONS.glob("*_*.svg")), "use the single SVG sprite"


def test_the_grid_features_panel_is_keyboard_operable_by_construction():
    """A real <details> with real checkboxes, not a custom popup: it opens and
    closes with the keyboard for free, and every toggle is a control that tabs.
    Building that from divs is where keyboard support usually gets lost."""
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert "<details id=\"grid-features\"" in page
    assert page.count('type="checkbox" data-feature=') >= 6


def test_status_bar_is_a_real_feature_and_owns_the_row_total():
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")

    assert 'data-feature="statusbar"' in page
    assert "statusbar: true" in script
    assert "footerElement: features.statusbar ? footer : undefined" in script
    assert 'class="data-grid-count"' not in page


def test_export_actions_follow_the_grid_instead_of_sitting_above_it():
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert 'class="data-grid-exportbar"' in page
    assert page.index('class="data-grid-viewport"') < page.index('class="data-grid-exportbar"')


def test_unimplemented_grid_features_are_visible_but_disabled():
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    for label in ("Advanced Filter", "Column Groups", "Pagination", "Row Drag",
                  "Row Pinning", "Show Integrated Chart Popup"):
        assert f'"{label}"' in page
    assert 'class="is-planned"' in page
    assert '<input type="checkbox" disabled> {{ feature }}' in page


def test_grid_has_a_stable_reserved_viewport():
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")

    assert 'class="data-grid-frame"' in page
    assert 'class="data-grid-viewport" data-grid-viewport' in page
    assert ".data-grid-viewport" in css
    assert "--data-grid-height: clamp(36rem, 72vh, 42rem)" in css
    assert 'height: "100%"' in (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert "contain: inline-size" in css


def test_row_selection_is_an_explicit_feature_and_zero_is_not_noise():
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")

    assert 'data-feature="select"' in page
    assert "select: true" in script
    assert "selectableRows: !!features.select" in script
    assert "footerSelected.stat.hidden = selected === 0" in script
    assert ".grid-footer-stat[hidden]" in css
    assert "note.hidden = details.length === 0" in script


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
TABLE_THEME = VENDOR.parent / "table-theme.css"
BASE = TEMPLATES / "base.html"


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


def test_grid_styling_is_fully_separated_from_the_base_template():
    """The application shell must not know Tabulator's selectors or the names
    of controls created by grid.js. Otherwise changing the grid requires edits
    in two stylesheets and the two copies can silently drift apart."""
    base = BASE.read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")

    grid_only = (".tabulator", ".setfilter", ".featuregrid", ".material-icon",
                 "#grid-features")
    assert all(selector not in base for selector in grid_only)
    assert all(selector in css for selector in grid_only)


def test_native_table_styling_is_fully_separated_from_the_base_template():
    """The shell loads the native table renderer but contains none of its
    rules. Table presentation therefore has one file and one owner."""
    import re

    base = BASE.read_text(encoding="utf-8")
    native = TABLE_THEME.read_text(encoding="utf-8")

    assert '/static/table-theme.css' in base
    assert re.search(r"(?m)^\s*(?:table|th,\s*td|\.tablewrap)\s*\{", base) is None
    assert "--table-" not in base
    assert "table {" in native and ".tablewrap {" in native


def test_native_and_grid_tables_consume_one_set_of_shape_tokens():
    """Shared appearance is named once; each renderer only maps its selectors
    onto that vocabulary."""
    native = TABLE_THEME.read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")

    tokens = ("--table-surface", "--table-text", "--table-rule", "--table-radius",
              "--table-cell-padding", "--table-font-size",
              "--table-header-font-size", "--table-hover-bg")
    for token in tokens:
        assert f"{token}:" in native, f"{token} has no single definition"
        assert f"var({token})" in native, f"native tables do not consume {token}"
        assert f"var({token})" in css, f"the grid does not consume {token}"


def test_header_is_one_and_a_quarter_normal_rows_with_bold_white_text():
    """The requested ratio is between the header and an ordinary unwrapped,
    non-compact data row; wrapping must still be allowed to grow."""
    import re

    css = THEME.read_text(encoding="utf-8")

    row = float(re.search(r"--grid-row-height:\s*([\d.]+)rem", css).group(1))
    header = float(re.search(r"--grid-header-height:\s*([\d.]+)rem", css).group(1))
    assert header == pytest.approx(row * 1.25)
    tokens = (ROOT / "design" / "tokens.css").read_text(encoding="utf-8")
    assert "--grid-header-weight: var(--fw-heavy)" in css
    assert "--fw-heavy: 700" in tokens
    assert "--grid-header-text: var(--surface)" in css
    assert "--grid-header-text: var(--text)" in css
    assert ".tabulator:not(.compact):not(.wrap)" in css
    assert "min-height: var(--grid-header-height)" in css


def test_header_sort_cycles_back_to_the_original_row_order():
    """One column click means ascending, two descending, three no sorter. The
    no-sort state is Tabulator's original input order, not a third invented
    ordering."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    vendor = (VENDOR / "tabulator.min.js").read_text(encoding="utf-8")

    assert "headerSortTristate: true" in script
    assert "headerSortTristate" in vendor, "the pinned Tabulator lacks tri-state sorting"
    assert "columnHeaderSortMulti: false" in script
    assert 'persistence: pinned.size ? false : {columns: ["width"]}' in script, (
        "a saved sorter can make the next click cycle start in an old state")
    assert 'PERSISTENCE_ID = "scrapex-grid-v2-"' in script


def test_no_sort_state_does_not_preview_an_arrow_on_hover():
    """After the third click the pointer is necessarily still over the header.
    A hover-only arrow made the cleared state look as though it had not cleared."""
    css = THEME.read_text(encoding="utf-8")

    assert ".tabulator .tabulator-col .material-sort-icon" in css
    assert ".tabulator .tabulator-col:hover .material-sort-icon" not in css


def test_header_parts_follow_label_sort_filter_menu_order():
    """The sorter belongs to the label; filter and menu form the far-edge
    control cluster shown in the reference image."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")

    assert 'className = "grid-header-label"' in script
    assert ".grid-header-label" in css and "order: 0" in css
    assert ".tabulator-col-sorter" in css and "order: 1" in css
    assert ".tabulator-header-popup-button" in css and "order: 2" in css
    assert "margin-inline-start: auto" in css
    assert "material-filter-icon" in css and "material-menu-icon" in css
    assert "material-sort-icon" in css


def test_minimum_column_width_always_keeps_filter_and_menu_visible():
    import re

    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")
    minimum = int(re.search(r"GRID_MIN_COLUMN_WIDTH\s*=\s*(\d+)", script).group(1))

    assert minimum >= 128
    assert "minWidth: GRID_MIN_COLUMN_WIDTH" in script
    assert "minWidth: 80" not in script, "a per-column override defeats the shared floor"
    assert css.count("min-width: 1.5rem") >= 1


def test_data_grid_edges_are_rounded_without_changing_other_tables():
    css = THEME.read_text(encoding="utf-8")

    assert "#grid.tablewrap" in css and "#grid.tabulator" in css
    assert "border-radius: var(--table-radius)" in css
    assert "overflow: hidden" in css


def test_column_resize_boundary_is_visible_and_highlights_while_dragging():
    css = THEME.read_text(encoding="utf-8")

    header_handle = ".tabulator .tabulator-header .tabulator-col-resize-handle"
    assert f"{header_handle}::after" in css
    assert "\n.tabulator-col-resize-handle::after" not in css
    assert "background: var(--muted)" in css
    assert f"{header_handle}:hover::after" in css
    assert f"{header_handle}:active::after" in css
    assert "background: var(--accent)" in css
    assert "cursor: col-resize" in css


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
    assert "if (features.tree && groupedBy.length)" in script


def test_grouping_and_nesting_are_separate_capabilities():
    """The owner drew the distinction: a GROUP is a synthetic band above rows
    carrying a count; a TREE nests real rows inside one column. Different
    questions, so different controls — both per column."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert 'data-feature="rows"' in page, "no switch for nested rows"
    assert "dataTree" in script and "dataTreeChildField" in script
    assert "Nest rows by this column" in script and '"Group by " + title' in script


def test_row_grouping_supports_ordered_multiple_levels_and_group_controls():
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")

    assert "groupedBy = groupedBy.concat(field)" in script
    assert "options.groupBy = groupedBy.slice()" in script
    assert "options.groupHeader = groupedBy.map" in script
    assert "as Group Level " in script
    for label in ("Remove ", "Un-Group All", "Expand All Row Groups",
                  "Collapse All Row Groups"):
        assert label in script
    assert "getSubGroups" in script and "table.getGroups().forEach(visit)" in script


def test_choose_columns_is_an_inline_searchable_reorderable_tool_panel():
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    css = THEME.read_text(encoding="utf-8")

    assert "function openColumnChooser()" in script
    assert 'fetch("/api/fields/"' in script
    assert 'search.type = "search"' in script
    assert "row.draggable = true" in script
    assert 'event.key !== "ArrowUp"' in script
    assert "hidden: field.is_hidden" in script
    assert "order: fields.map" in script
    assert "location.assign(url)" not in script
    assert ".column-chooser" in css and ".column-chooser-row" in css


def test_column_menu_matches_the_grid_workflow_and_autosize_measures_content():
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")

    for label in ("Sort Ascending", "Sort Descending", "Pin Column", "No Pin",
                  "Pin Left", "Pin Right", "Autosize This Column",
                  "Autosize All Columns", "Choose Columns", "Reset Columns"):
        assert label in script
    assert "menu: pinMenu(field)" in script
    assert 'menuLabel("push-pin", "Pin Column")' in script
    assert 'menuLabel("fit-screen", "Autosize This Column")' in script
    assert 'menuLabel("view-column", "Choose Columns")' in script
    assert 'menuLabel("restart-alt", "Reset Columns")' in script
    assert "column.setWidth(true)" in script
    assert "requestAnimationFrame(() => requestAnimationFrame(() =>" in script
    assert "column.setWidth(measured)" in script
    assert "function measureHeaderWidth(column)" in script
    assert "label.scrollWidth" in script
    assert 'titleHolder.querySelectorAll(' in script
    assert "measureHeaderWidth(column)" in script
    assert 'layout: "fitColumns"' in script
    assert "persistence: pinned.size ? false" in script


def test_the_two_hierarchies_cannot_be_on_at_once():
    """Bands above rows that are themselves nested is two hierarchies stacked;
    neither reads. Choosing one clears the other rather than rendering both."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert 'if (groupedBy.length) { treeBy = ""' in script
    assert 'if (treeBy) { groupedBy = []' in script


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


def test_history_opens_inline_and_the_full_page_link_survives():
    """The owner's ask: History must open UNDER the table, not navigate away —
    and the real href must stay, so middle-click and scripting-off still reach
    the full page. The interception is only ever a plain left-click."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert 'id="offer-panel"' in page
    assert "openOfferPanel" in script and "/api/offer/" in script
    assert "event.preventDefault()" in script
    assert "event.ctrlKey || event.metaKey" in script, \
        "modified clicks must keep opening the full page"


def test_the_panel_never_renders_scraped_values_as_html():
    """Everything in the panel goes through textContent/createElement. One
    innerHTML over API data and a scraped product name becomes live markup."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    panel = script.split("the History panel")[1].split("---- export")[0]
    assert "innerHTML" not in panel, "the panel builds HTML from strings"
