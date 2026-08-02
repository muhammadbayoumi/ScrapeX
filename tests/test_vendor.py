"""Vendored third-party assets are present, whole, and licensed.

ScrapeX is local-first: it must work on a machine with no internet. A page that
fetched a library from a CDN would fail exactly when the owner is offline — the
one condition the product promises to survive — and would let a third party
change what runs on their machine without a commit. So the bytes are in the
repository, and these tests are what stop them from silently going missing,
being truncated by a bad checkout, or losing their licence text.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct

import pytest

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "scrapex" / "webui" / "static" / "vendor"
TEMPLATES = ROOT / "scrapex" / "webui" / "templates"
MATERIAL_ICONS = VENDOR.parent / "material-icons"
CANONICAL_ICON_SPRITE = ROOT / "design" / "material-icons.svg"

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


def test_appearance_manager_is_shared_and_runs_before_the_design_tokens():
    canonical = (ROOT / "design" / "appearance.js").read_bytes()
    panel = (ROOT / "extension" / "appearance.js").read_bytes()
    workspace = (ROOT / "scrapex" / "webui" / "static" / "appearance.js").read_bytes()
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    extension = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")

    assert panel == canonical == workspace
    assert base.index("appearance.js") < base.index("tokens.css")
    assert extension.index("appearance.js") < extension.index("tokens.css")
    script = canonical.decode("utf-8")
    assert 'mode: "device"' in script
    assert "deviceColors: true" in script
    assert "data-appearance-scheme-mode" in script
    assert "data-appearance-palettes" in script


def test_appearance_colour_rebuilds_the_whole_tonal_surface_family():
    tokens = (ROOT / "design" / "tokens.css").read_text(encoding="utf-8")
    appearance = (ROOT / "design" / "appearance.js").read_text(encoding="utf-8")
    tonal = tokens.split("/* Device-derived tonal surfaces", 1)[1].split(
        "@media (prefers-contrast: more)", 1)[0]

    assert ':root[data-color-mode="device"]' in tonal
    for token in (
        "--bg",
        "--surface",
        "--surface-subtle",
        "--surface-raised",
        "--line",
        "--line-strong",
        "--chip",
        "--control-bg",
        "--control-hover",
    ):
        assert f"{token}:" in tonal
    assert "light-dark(" in tonal
    assert "color-mix(in srgb, var(--accent)" in tonal
    assert "const THEME_PROPERTIES" in appearance
    assert 'bg: "#F7F5F3"' in appearance  # WhatsApp light
    assert 'bg: "#121B21"' in appearance  # WhatsApp dark
    assert 'bg: "#FFFFFF"' in appearance  # GitHub light
    assert 'bg: "#0D1117"' in appearance  # GitHub dark


def test_only_the_two_reviewed_application_palettes_are_available():
    appearance = (ROOT / "design" / "appearance.js").read_text(encoding="utf-8")

    assert appearance.count('description: "') == 2
    assert '["whatsapp", {' in appearance
    assert '["github", {' in appearance
    assert 'accent: "#35AA65"' in appearance
    assert 'red: "#B3002F"' in appearance
    assert 'switchTrack: "#35AA65"' in appearance
    assert 'buttonBg: "#43D36D"' in appearance
    assert 'buttonHover: "#1C1E21"' in appearance
    for removed in (
        "popular-blush", "light-rose", "dark-harbour", "warm-coral",
        "earth-clay", "cold-ocean", "coolors-sunset", 'id: "custom"',
    ):
        assert removed not in appearance
    assert 'data-accent="' not in (
        ROOT / "design" / "tokens.css"
    ).read_text(encoding="utf-8")


def test_appearance_has_one_cross_surface_sync_contract():
    appearance = (ROOT / "design" / "appearance.js").read_text(encoding="utf-8")
    panel = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")

    assert 'const SYNC_PATH = "/api/appearance"' in appearance
    assert "window.ScrapeXAppearance?.connect(backend)" in panel
    assert '@app.get("/api/appearance")' in server
    assert '@app.post("/api/appearance")' in server


def test_ui_colour_literals_live_only_in_the_canonical_colour_system():
    allowed = {
        ROOT / "design" / "tokens.css",
        ROOT / "design" / "appearance.js",
        ROOT / "extension" / "tokens.css",
        ROOT / "extension" / "appearance.js",
        ROOT / "scrapex" / "webui" / "static" / "tokens.css",
        ROOT / "scrapex" / "webui" / "static" / "appearance.js",
    }
    colour = re.compile(
        r"(?<![&A-Za-z0-9_-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|"
        r"[0-9a-fA-F]{3})(?![A-Za-z0-9_-])|rgba?\(",
    )
    offenders = []
    for folder in (ROOT / "design", ROOT / "extension", ROOT / "scrapex" / "webui"):
        for path in folder.rglob("*"):
            if path.suffix not in {".css", ".js", ".html"} or path in allowed:
                continue
            if "vendor" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if colour.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == [], f"colour literals outside the shared system: {offenders}"


def test_every_material_icon_reference_exists_in_the_one_shared_sprite():
    """An icon is a component, not decoration: missing IDs leave an invisible
    control while the button remains clickable. Keep the two distributed
    copies byte-for-byte equal to the reviewed canonical sprite, then verify
    every static reference against its symbol IDs."""
    canonical = CANONICAL_ICON_SPRITE.read_bytes()
    assert (ROOT / "extension" / "icons" / "material-icons.svg").read_bytes() == canonical
    assert (
        ROOT / "scrapex" / "webui" / "static" / "material-icons" / "material-icons.svg"
    ).read_bytes() == canonical

    symbols = set(re.findall(
        r'<symbol\b[^>]*\bid="([A-Za-z0-9_-]+)"',
        canonical.decode("utf-8"),
    ))
    referenced: set[str] = set()
    for folder in (ROOT / "extension", ROOT / "scrapex" / "webui"):
        for path in folder.rglob("*"):
            if path.suffix not in {".html", ".js"}:
                continue
            referenced.update(re.findall(
                r"material-icons\.svg#([A-Za-z0-9_-]+)",
                path.read_text(encoding="utf-8"),
            ))
    assert referenced
    assert referenced <= symbols, f"missing material icon symbols: {sorted(referenced - symbols)}"


def test_original_logo_is_shared_and_chrome_has_every_required_raster_size():
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    canonical = (ROOT / "design" / "x-mark.svg").read_bytes()

    assert canonical == (ROOT / "extension" / "icons" / "x-mark.svg").read_bytes()
    assert canonical == (ROOT / "scrapex" / "webui" / "static" / "x-mark.svg").read_bytes()

    for size, relative in manifest["icons"].items():
        data = (ROOT / "extension" / relative).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (int(size), int(size))
        assert "original" in relative


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
    # design-system-12/11: the record panel became a container of cards and the
    # selection column appeared. A cached script here would keep drawing the
    # old bare tables and would not know the new class names the CSS styles.
    # design-system-13/12: the AR|EN switch now governs the panel too, and
    # English is the default. A cached script would keep printing both
    # languages in the cards under the table.
    # design-system-14: the Excel button asks the SERVER for the whole workbook.
    # A cached script would keep calling Tabulator's xlsx writer, which needs a
    # library this project does not vendor, and keep producing nothing.
    # design-system-15/13: the History column is gone, an empty column title no
    # longer prints "&nbsp;", and the arrow wears the theme's accent instead of
    # the amber reserved for text links.
    # design-system-15/13: row checkboxes now accumulate selection, the header
    # checkbox reports partial/all state, and the frozen selection divider is
    # removed from the shared table frame.
    # design-system-16/14: selected rows now become product summary cards and
    # the full descriptions/history open in one wide details surface.
    # design-system-17/15: the product gallery gained previous/next controls,
    # while details and history now share a wide side inspector.
    # design-system-18/16: the cards left the outer container, comparison was
    # removed, and the details navigation became an icon rail.
    # design-system-18/17: the media gallery returned to the theme's original
    # surface colours without changing its larger layout.
    # design-system-18/18: multiple product cards stretch evenly to the table's
    # full width, so their outer edges share the same alignment.
    # design-system-19/19: Details and History now toggle one attached,
    # animated inspector with the redundant media section removed.
    # design-system-20/20: the product and inspector became one visual shell,
    # description hierarchy was flattened, and numeric display was unified.
    # design-system-21/21: detail tabs no longer impose a generic heading;
    # each section displays the title stored with its source data instead.
    # design-system-23/23: the established detail-card headings remain in
    # place, with Keywords added only inside the Description card.
    # design-system-24/24: the language picker is a compact segmented control
    # and the saved-views content opens as a real anchored panel.
    # design-system-26: an owner's width (autosize or drag) is widthGrow 0,
    # so fitColumns can never quietly re-stretch it — the intermittent
    # Autosize the owner reported was the cache AND the layout both.
    # design-system-27 (CSS): the light header uses a distinct semantic
    # container band instead of disappearing into the white data rows.
    # design-system-28: the seven detail groups reached the panel. Keywords
    # kept their chip rendering when 0046 refiled them out of Description, and
    # the inspector rail gained a button per group — Store and Site metadata
    # had none, so both were being stacked under Specifications.
    # design-system-35: the image gallery is one inset box and disappears when
    # empty; the lower rail group follows the same populated-only rule.
    # design-system-36: the non-language vocabulary sweep (0051) reached the
    # grid — every price and tax key moved, and the record arrow became
    # `product_link`, the same key the export already used.
    # design-system-37: contain both inspector button groups, inset the gallery
    # scrollbar, and bridge the live server's legacy effective_price field.
    # design-system-38: centre the divider between the boxed inspector groups
    # and lock image-navigation controls against the global pressed transform.
    # design-system-39: the three export actions now live in one accessible,
    # dismissible format menu without changing any export behaviour.
    # design-system-40: the ALL|ONE control above the table, which folds a
    # product's same-priced variations into one row. Without the bump the
    # owner's browser keeps a cached grid that has no such control.
    # design-system-41: Excel is the direct split-button action; CSV and JSON
    # stay together in its compact, accessible format menu.
    # design-system-42: header filter/menu controls gained keyboard semantics
    # and a visible token-based focus state.
    # design-system-44: the export split control gained a quieter hierarchy
    # and a structured, descriptive menu without changing export behaviour.
    assert '/static/grid.js?v=design-system-45' in page
    assert '/static/grid-theme.css?v=design-system-45' in page
    assert '/static/grid-theme.css?v=design-system-45' in (
        TEMPLATES / "datasets.html").read_text(encoding="utf-8")
    # design-system-45: opening a card no longer rearranges the others — the
    # column count is unchanged on focus and nothing is pinned to a row.
    # design-system-44: two selected cards keep the established card width and
    # aligned slots; the focused card KEEPS ITS PLACE with the inspector beside
    # it, and the other selected cards move below without clearing the table
    # selection.


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
        'id="palette"', 'id="light-mode"', 'id="dark-mode"',
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
    assert "footerElement: (features.statusbar || features.select) ? footer : undefined" in script
    assert 'class="data-grid-count"' not in page


def test_export_actions_follow_the_grid_instead_of_sitting_above_it():
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    # The split-button SHELL is now the shared component (components.css); the
    # grid-theme keeps only where the exportbar sits and how it stacks.
    theme_css = THEME.read_text(encoding="utf-8")
    shared_css = (VENDOR.parent / "components.css").read_text(encoding="utf-8")

    assert 'class="data-grid-exportbar"' in page
    assert page.index('class="data-grid-viewport"') < page.index('class="data-grid-exportbar"')
    # The Export control IS the shared split button — the same classes the panel
    # log control uses. That reuse is the DRY the owner asked for by name.
    assert 'class="split-button"' in page
    assert 'class="split-button-primary" data-split-action="xlsx"' in page
    assert 'class="split-button-menu"' in page
    assert 'class="split-button-trigger"' in page
    assert '<span>Excel workbook</span>' in page
    assert 'class="split-button-options-head"' not in page
    assert page.count('class="split-button-option"') == 2
    assert page.count('class="split-button-option-tag"') == 2
    assert "Filtered rows in a spreadsheet-friendly file." not in page
    assert "Structured data from the current table view." not in page
    assert page.count("data-split-action=") == 3
    assert 'class="chip" data-split-action=' not in page
    assert 'role="menu" aria-label="Export format"' in page
    # The behaviour lives ONCE, in split-button.js, and grid.js calls it rather
    # than re-implementing the open/close/escape/outside-click dance.
    assert "ScrapeXSplitButton.wire(" in script
    assert 'if (event.key !== "Escape" || !menu.open) return;' not in script, \
        "grid.js must not carry a second copy of the split-button behaviour"
    # The shell styles live in the SHARED component, not re-declared per grid.
    assert ".grid-export-split" not in theme_css and ".grid-export-menu" not in theme_css
    assert ".split-button {" in shared_css
    split_rule = shared_css.split(".split-button {", 1)[1].split("}", 1)[0]
    assert "overflow: hidden" not in split_rule, "the split must not clip its menu"
    assert ".split-button-menu[open] .split-button-trigger" in shared_css
    assert ".split-button-primary:active:not(:disabled)" in shared_css
    assert ".split-button-options" in shared_css
    options_rule = shared_css.split(".split-button-options {", 1)[1].split("}", 1)[0]
    assert "inset-inline: 0" in options_rule
    assert "top: calc(100% + var(--sp-1))" in options_rule
    assert "width: 100%" in options_rule
    assert "bottom:" not in options_rule
    assert ".split-button-trigger:focus-visible" in shared_css
    focus_rule = shared_css.split(".split-button-trigger:focus-visible {", 1)[1].split("}", 1)[0]
    assert "outline-offset: -2px" in focus_rule
    assert ".split-button-option:active:not(:disabled)" in shared_css


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
    assert 'selectableRowsRangeMode: "click"' not in script
    assert "cell.getRow().toggleSelect()" not in script
    assert 'cssClass: "grid-select-column"' in script
    assert "(features.statusbar || features.select) ? footer : undefined" in script
    assert "footerSelected.stat.hidden = selected === 0" in script
    assert ".grid-select-column.tabulator-frozen.tabulator-frozen-left" in css
    assert '.grid-select-column input[type="checkbox"]' in css
    assert "font-family: var(--font)" in css
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


def test_header_is_one_and_a_quarter_normal_rows_and_follows_the_theme():
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
    assert "--grid-header-surface: color-mix(" in css
    assert "var(--surface-container-low) 76%" in css
    assert "var(--outline-variant)" in css
    assert "--grid-header-hover: color-mix(" in css
    assert "var(--grid-header-surface) 90%" in css
    assert "var(--primary)" in css
    assert "--grid-header-text: var(--on-surface)" in css
    assert "@media (prefers-color-scheme: dark)" not in css
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
    # v3: the vocabulary sweep renamed the columns whose widths this key
    # remembers, so the stored layout is about columns that no longer exist.
    assert 'PERSISTENCE_ID = "scrapex-grid-v3-"' in script


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
    # The ordered list of levels is what drives the grouping. This used to pin
    # the exact expression, `groupedBy.slice()`, and broke the moment a column
    # that renders from somewhere other than its own field needed a reader
    # function rather than a bare field name. What it actually GROUPS BY is
    # asserted by driving the real table in tests/test_grid_dom.py, where a
    # wrong answer is visible instead of merely differently spelled.
    assert "options.groupBy = groupedBy" in script
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
    # The hide write moved into moveToZone: one function now serves the
    # checkbox, the drag between zones and the keyboard, so the endpoint is
    # called from ONE place instead of three (the mechanism the owner's
    # "move a field to the details" ask is built on).
    assert "moveToZone" in script and "updateFields({field_key: key, hidden})" in script
    assert "order: fields.map" in script
    assert "location.assign(url)" not in script
    assert ".column-chooser" in css and ".column-chooser-row" in css


def test_column_menu_matches_the_grid_workflow_and_autosize_measures_content():
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")

    for label in ("Sort Ascending", "Sort Descending", "Pin Column", "No Pin",
                  "Pin Left", "Pin Right", "Auto-fit column width",
                  "Auto-fit all column widths", "Choose Columns", "Reset Columns"):
        assert label in script
    assert "menu: pinMenu(field)" in script
    assert 'menuLabel("push-pin", "Pin Column")' in script
    assert 'menuLabel("fit-screen", "Auto-fit column width")' in script
    assert 'menuLabel("view-column", "Choose Columns")' in script
    assert 'menuLabel("restart-alt", "Reset Columns")' in script
    assert "column.setWidth(true)" in script
    # A TIMER, not rAF: requestAnimationFrame never fires while the tab is
    # hidden or the window is throttled, so the measurement was parked
    # indefinitely and Autosize did nothing at all — one of the owner's
    # three "sometimes it does not work" causes. And the deferred pass now
    # ends in build(), because only a width in the column DEFINITIONS
    # (width + widthGrow 0) survives every later fitColumns pass.
    autosize_body = script.split("function autosizeColumns")[1].split("function autosize(")[0]
    assert "requestAnimationFrame(" not in autosize_body, \
        "the deferred measure went back to a frame that hidden tabs never paint"
    assert "setTimeout(() => {" in script
    assert "widths.has(col.key) ? 0" in script
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
    """A grouping heading is not an offer, so nothing may open a record for it.

    This used to pin the History column's own guard ("if (!cell.getValue())"),
    and that column is gone: selecting a row opens the record underneath, so a
    column whose only job was to open the same container was a second door into
    a room the row already opens. The concern outlived the column - the guard
    that matters now is the selection filter, because a heading row IS
    selectable and has no offer_id."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert 'title: "History"' not in script, "the History column is back"
    assert ".filter((row) => row.offer_id)" in script,         "a heading row would open /api/offer/undefined"


def test_history_opens_inline_and_the_full_page_link_survives():
    """The owner's ask: the record opens UNDER the table, never by navigating
    away — and the full page must stay reachable, for bookmarking.

    The modified-click passthrough this used to assert belonged to the History
    LINK, and that link is gone with its column: selecting a row opens the same
    container, so a column whose only job was to open it was a second door into
    a room the row already opens. The full page did not go with it — the
    record's own header carries a real href to it."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert 'id="offer-panel"' in page
    assert "openOfferPanel" in script and "/api/offer/" in script
    assert 'el("a", "record-action record-action-subtle", "Full record")' in script
    assert 'full.href = "/source/" + encodeURIComponent(SOURCE) + "/offer/"' in script


def test_selected_rows_render_as_product_cards_with_a_responsive_inspector():
    """A selected product keeps the attached side inspector; with several
    selected products, the other cards move below without being deselected."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    css = (VENDOR.parent / "grid-theme.css").read_text(encoding="utf-8")

    assert 'el("article", "selected-product-card")' in script
    assert 'el("section", "record-inspector")' in script
    assert '"Details"' in script and '"History"' in script
    assert '"View details"' not in script
    assert '"Description"' in script and '"Specifications"' in script
    assert '"Attachments"' in script
    assert "Previous product image" in script and "Next product image" in script
    assert "if (images.length) box.appendChild(media)" in script
    assert "row.price !== undefined" in script
    assert ": row.effective_price" in script
    assert '"Compare selected"' not in script and '"Side by side"' not in script
    assert 'materialIconElement(item.icon, "record-inspector-nav-icon")' in script
    assert 'materialIconElement("open-in-new", "selected-product-site-icon")' in script
    assert "shortDescription" in script and "deepestCategoryLevel" in script
    assert "displayProductName" in script
    assert "toggleInspector" in script and "openInspector" not in script
    assert '{key: "media", label: "Media"' not in script
    assert '"record-inspector-tab"' not in script
    assert '"record-inspector-head"' not in script
    assert '"record-card-wide record-card-prose"' in script
    assert "const databaseTitle" in script
    assert "Collected from the source" not in script
    assert '"record-inspector-content-head"' not in script
    assert "const INSPECTOR_VIEWS" in script
    assert '"record-inspector-nav-mode"' in script
    assert '"record-inspector-nav-divider"' in script
    assert '"record-inspector-nav-section"' in script
    assert "populated.forEach((item)" in script
    assert "if (populated.length)" in script
    assert "button.disabled = disabled" not in script
    assert "detailSectionTitles" not in script
    assert "keywordSection" in script and '"record-keywords"' in script
    assert "code.startsWith(\"keywords\")" in script
    assert '"selected-product-category"' in script
    assert '"selected-product-category-label", "Category"' in script
    assert 'materialIconElement("account-tree"' not in script
    assert ".selected-product-card" in css
    assert "#offer-panel button.selected-product-image-nav:active:not(:disabled)" in css
    assert "#offer-panel button.selected-product-image-nav:focus-visible" in css
    assert "outline-offset: -3px" in css
    assert "transform: translateY(-50%)" in css
    assert ".selected-product-thumbs::-webkit-scrollbar-track" in css
    assert ".selected-product-thumbs::-webkit-scrollbar-button" in css
    assert "height: 5.25rem" in css
    assert 'const thumbs = el("div", "selected-product-thumbs")' in script
    assert "images.forEach((image, index)" in script
    assert ".record-product-workspace.has-inspector" in css
    assert ".record-inspector-nav" in css
    assert ".record-inspector-nav-primary" in css
    assert ".record-inspector-nav-sections" in css
    assert ".record-inspector-nav-primary,\n.record-inspector-nav-sections" in css
    assert ".record-inspector-nav-divider" in css
    assert "margin-block: var(--sp-1)" in css
    assert "grid-template-columns: minmax(0, 24rem) minmax(0, 0fr)" in css
    assert "transform: translateX(-.75rem)" in css
    assert "width: min(24rem, 100%)" in css
    assert ".record-prose-list" in css
    assert ".record-detail-subsection" in css and ".record-keyword" in css
    assert ".record-product-workspace .selected-product-card" in css
    assert ".selected-product-description::-webkit-scrollbar" in css
    assert 'box.appendChild(el("div", "record-card-body"))' in script
    assert "function cardBody(box)" in script
    assert ".record-inspector-content .record-card-body" in css
    assert ".record-inspector-content .record-card-prose" not in css
    assert ".record-inspector-content .record-prose," in css
    assert "max-width: none" in css
    assert ".record-card-body::-webkit-scrollbar" in css
    assert ":has(.spec-list)" not in css
    assert "repeat(auto-fit, minmax(min(20rem, 100%), 1fr))" in css
    assert '"selected-product-grid is-pair"' in script
    assert ".selected-product-grid.is-pair" in css
    assert "repeat(2, minmax(0, 24rem))" in css
    multi = script.split("function renderSelectedCardsPanel", 1)[1].split(
        "// ---- export", 1)[0]
    assert '"selected-product-detail-host"' in multi
    assert "renderOfferPanel(detailPanel, data, row.offer_id, view," in multi
    assert "table.deselectRow()" not in multi
    # THE INSPECTOR SITS BESIDE ITS CARD, and the card stays. The first version
    # hid the focused card and put a full-width panel above the grid, so the
    # record you clicked vanished at the moment you asked to look at it.
    assert "panel.append(productGrid)" in multi
    assert 'button.closest(".selected-product-card")' in multi
    assert "focusedCard.hidden = true" not in multi, "the focused card is hidden again"
    assert "focusedCard.after(detailHost)" in multi, "the inspector must follow ITS card"
    assert 'focusedCard.classList.add("is-focused")' in multi
    assert 'productGrid.classList.add("has-focused-record")' in multi
    assert ".selected-product-grid.has-focused-record" in css
    # OPENING A CARD MUST NOT REARRANGE THE OTHERS. The first attempt cut the
    # grid to two tracks and pinned every card to column 1, so the opened card
    # rose to the top and the rest fell into a single stack. The column count
    # must not change on focus, and nothing may be pinned to a row or a column.
    assert "grid-template-columns: minmax(0, 24rem) minmax(0, 1fr);" not in css
    focused = css.split(".selected-product-card.is-focused {", 1)[1].split("}", 1)[0]
    assert "grid-row" not in focused and "grid-column" not in focused, (
        "the focused card is pinned again, so it jumps out of its place")
    host = css.split(".selected-product-detail-host {", 1)[1].split("}", 1)[0]
    assert "grid-column: span 2;" in host, "the inspector must span, not be pinned"
    assert "grid-row" not in host
    assert ".selected-product-card.is-focused" in css
    # A truncated value must stay readable somewhere, or the card decides what
    # a fact SAYS rather than where it is shown.
    assert "value.title = categoryLevel;" in script
    assert ".selected-product-detail-host .selected-product-grid { display: none; }" not in css
    assert "grid-template-rows:" in css
    assert "height: 3.25rem" in css
    assert ".record-card-wide { grid-column: 1 / -1; }" in css


def test_record_inspector_follows_the_central_detail_group_order():
    from scrapex.vocab import DETAIL_GROUP_ORDER

    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    definitions = script.split("const DETAIL_SECTIONS = [", 1)[1].split(
        "];", 1)[0]
    visible = [group for group in DETAIL_GROUP_ORDER if group != "Media"]
    positions = [definitions.index(f'label: "{group}"') for group in visible]
    assert positions == sorted(positions)


# The one file that builds markup from strings rather than from createElement,
# and is allowed to: /data-model draws a diagram whose shape is easier to state
# as HTML than to assemble node by node. It carries its own esc() and the guard
# below holds it to using it. Anything ADDED to this set is a decision, not an
# oversight.
_HTML_BUILDING_UI_SCRIPTS = {"pages/data-model.js"}

# Property names that hold words from the warehouse and therefore need escaping
# before interpolation into markup. Counts, scales and coordinates are absent:
# a number cannot open a tag.
_TEXT_BEARING_FIELDS = frozenset({
    "name", "title", "purpose", "group", "key", "type", "label",
    "text", "description", "summary", "value", "unit", "note",
})


def _ui_scripts() -> list:
    """Every web UI script we own (vendored libraries are outside this rule)."""
    root = VENDOR.parent
    return sorted(p for p in root.rglob("*.js") if "vendor" not in p.parts)


def test_the_web_ui_never_renders_scraped_values_as_html():
    """Any new innerHTML use must be explicit and guarded, across every script."""
    import re

    offenders = {}
    for script in _ui_scripts():
        relative = script.relative_to(VENDOR.parent).as_posix()
        if relative in _HTML_BUILDING_UI_SCRIPTS:
            continue
        source = script.read_text(encoding="utf-8")
        assignments = re.findall(r"\.innerHTML\s*=", source)
        if assignments:
            offenders[relative] = len(assignments)
    assert not offenders, (
        "these scripts build HTML from strings, so a scraped value can become "
        f"live markup: {offenders}. Use textContent/createElement, or add the "
        "file to _HTML_BUILDING_UI_SCRIPTS and prove it escapes its text")


def test_the_one_html_building_script_escapes_every_text_value_it_interpolates():
    """The diagram exception remains safe only while its text holes use esc()."""
    import re

    for relative in sorted(_HTML_BUILDING_UI_SCRIPTS):
        source = (VENDOR.parent / relative).read_text(encoding="utf-8")
        assert re.search(r"const esc = ", source), f"{relative} lost its esc()"

        unescaped, inside = [], False
        for number, line in enumerate(source.splitlines(), 1):
            if ".innerHTML" in line:
                inside = True
            if inside:
                for hole in re.findall(r"\$\{(?!esc\()([^}]+)\}", line):
                    leaf = hole.strip().rsplit(".", 1)[-1]
                    if leaf in _TEXT_BEARING_FIELDS:
                        unescaped.append(
                            f"{relative}:{number} ${{{hole.strip()}}}")
                if line.rstrip().endswith(("`;", '`.join("")',
                                           "].join(\"\")")):
                    inside = False
        assert not unescaped, (
            "these values reach innerHTML without esc(), so markup would be "
            f"rendered as markup: {unescaped}")


def test_the_dataset_freshness_line_does_not_crush_the_name():
    """The owner's screenshot: madar, masdar, samehgabriel and sika all rendered
    as four characters and an ellipsis, with the [Row N] badge sitting on top of
    the words it collided with.

    The freshness line was placed in grid-column 2 — the narrow auto-width
    column the badge lives in — so "Last crawled 2026-07-30 10:15 UTC · 19,548
    rows seen" widened that column until the name had nothing left. It is a
    caption on the card, not a figure beside the badge."""
    css = (VENDOR.parent / "pages" / "data-workspace.css").read_text(encoding="utf-8")

    detail = css.split(".dataset-choice-detail{", 1)[1].split("}", 1)[0]
    assert "grid-column:1/-1" in detail, (
        "the freshness caption is back in the narrow column beside the badge")
    assert "grid-column:2" not in detail
    # The identity must own row 1, or the caption can be auto-placed back beside
    # it. Only .source-identity and .dataset-choice-detail are grid items here:
    # .dataset-choice>.source-identity-meta matches nothing, because the badge is
    # nested inside .source-identity-footer. Asserting a rule that styles no
    # element is how a guard comes to protect nothing.
    assert "grid-row:1" in css.split(".dataset-choice>.source-identity{", 1)[1].split("}", 1)[0]


def test_the_dataset_freshness_line_stays_readable_when_truncated():
    """It is ellipsised to one line, so the whole value must be reachable — the
    card decides where a fact is shown, never what it says."""
    html = (TEMPLATES / "_source_list.html").read_text(encoding="utf-8")
    css = (VENDOR.parent / "pages" / "data-workspace.css").read_text(encoding="utf-8")

    line = css.split(".dataset-choice-detail>.dataset-choice-state{", 1)[1].split("}", 1)[0]
    assert "text-overflow:ellipsis" in line and "min-width:0" in line, (
        "without min-width:0 a grid item refuses to shrink below its content, "
        "so the caption widens the card instead of ellipsising")
    # The title must be the WHOLE line, not its opening. A title that stopped at
    # "UTC" would hide exactly the "· 19,548 rows seen" tail the ellipsis cuts —
    # a recovery mechanism that recovers the part you could already read.
    # Two ways to satisfy one rule, and both are exact. A caption the server can
    # write in full carries the string twice by construction; a caption whose
    # time only timezone.js can convert is marked data-clamped-title and the
    # formatter fills it from the rendered text. What is forbidden is a title
    # that is a PREFIX of what it recovers.
    assert html.count("data-clamped-title") == 2, (
        "both time-bearing captions must ask the formatter to title them")
    assert 'title="Ready - refresh' in html, (
        "a caption with no time in it the server can title itself")
    assert html.count("Last crawled") == 1, (
        "the line is built twice, so the two copies can drift apart")


def test_every_dataset_freshness_state_can_be_read_in_full(tmp_path):
    """Not only the happy one. The clamp applies to whichever caption renders,
    so a source that has data but has never finished a crawl gets a 39-character
    sentence on one line with nothing to recover it — unless it is titled too."""
    from fastapi.testclient import TestClient
    from scrapex.webui.app import create_app
    from scrapex import db as dbmod

    p = tmp_path / "w.db"
    conn = dbmod.connect(p)
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar,"
                 " source_name, base_url, platform, currency, timezone, authority,"
                 " active) VALUES (1,'MADAR','مدار','Madar',"
                 "'https://madar.test','custom_json','SAR','UTC','shop',1)")
    conn.commit()

    page = TestClient(create_app(p)).get("/data").text
    for state in page.split('class="dataset-choice-state"')[1:]:
        head = state.split(">", 1)[0]
        assert "title=" in head or "data-clamped-title" in head, (
            f"a freshness caption ships unreadable: {head[:80]}")
