"""The side panel, driven in a real browser and asserted on.

Fifteen panel capabilities were graded `partial` for one reason: no test of any
kind existed for any of them. Screenshots proved a layout, never a behaviour, and
they actively HID one blocker — every scenario clicked a nav button before
capturing, so the broken opening screen was never photographed.

These tests drive the panel's own HTML, CSS and JS through the same harness the
screenshots use, and assert what a person would see and do.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")
from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402

SOURCE_TAB = 'nav.tabs button[data-view="source"]'
RUN_TAB = 'nav.tabs button[data-view="run"]'
DATA_TAB = 'nav.tabs button[data-view="data"]'
SOURCES_TAB = 'nav.tabs button[data-view="sources"]'
SETTINGS_TAB = 'nav.tabs button[data-view="settings"]'


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_panel(browser, tmp_path):
    """Open the panel with a given stub and return the live page."""
    pages = []

    def opener(**stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"panel{len(pages)}.html")
        page = browser.new_page(viewport={"width": 360, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def text_of(page, selector: str) -> str:
    return (page.text_content(selector) or "").strip()


# ---- the opening screen ------------------------------------------------------

def test_the_panel_opens_on_source_with_the_active_tab_already_read(open_panel):
    """The blocker screenshots could not see: the opening view never ran its
    loader, so it sat at "Reading the active tab…" until you navigated away."""
    page = open_panel()
    assert page.is_visible("#view-source")
    assert text_of(page, "#cur-title") == harness.ACTIVE_TAB["title"]
    assert harness.ACTIVE_TAB["url"] in text_of(page, "#cur-url")
    assert not page.is_disabled("#cur-use")


def test_opening_the_panel_raises_no_script_errors(open_panel):
    page = open_panel()
    assert page.js_errors == [], f"the panel threw on load: {page.js_errors}"


def test_the_icon_rail_keeps_deep_workspace_pages_in_one_grouped_menu(open_panel):
    page = open_panel()
    page.evaluate("""() => {
        window.__opened = [];
        window.chrome.tabs.create = (o) => window.__opened.push(o.url);
    }""")
    rail = page.locator("nav.side-rail")
    bounds = rail.bounding_box()
    assert bounds and bounds["x"] + bounds["width"] == pytest.approx(360, abs=1)
    assert bounds["y"] == pytest.approx(0, abs=1)
    assert bounds["height"] == pytest.approx(800, abs=1)

    assert page.locator("nav.side-rail button[data-view]").count() == 6
    assert page.locator("nav.side-rail button.rail-item").count() == 7
    workspace = page.locator("#workspace-links [data-workspace-path]")
    # One per workspace destination the rail does not own as its own view.
    # Rolled 10 -> 11 when Data Model joined System: the panel mirrors the
    # destination contract, so a page added on one surface and not the other is
    # exactly what this count exists to catch.
    assert workspace.count() == 11
    assert page.locator("#workspace-links .workspace-menu-group").count() == 4
    assert not page.locator("#workspace-menu").get_attribute("class").endswith("is-open")

    page.click("#workspace-toggle")
    assert page.get_attribute("#workspace-toggle", "aria-expanded") == "true"
    assert page.get_attribute("#workspace-menu", "aria-hidden") == "false"
    page.click('[data-workspace-key="changes"]')
    page.wait_for_timeout(100)
    opened = page.evaluate("() => window.__opened")
    assert len(opened) == 1 and opened[0].endswith("/changes")


def test_appearance_is_a_complete_android_style_destination(open_panel):
    page = open_panel()
    tab = page.locator("#tab-appearance")
    view = page.locator("#view-appearance")
    device_colours = view.locator("[data-appearance-device-colors]")

    page.evaluate("() => window.ScrapeXAppearance.set({mode: 'device', deviceColors: true})")
    assert page.locator("html").get_attribute("data-appearance") == "device"
    assert not view.is_visible()

    tab.click()
    assert view.is_visible()
    assert tab.get_attribute("aria-selected") == "true"
    assert tab.get_attribute("aria-current") == "page"
    assert view.locator(".appearance-live-preview").is_visible()
    assert view.locator('[data-appearance-scheme-mode="device"]').get_attribute(
        "aria-pressed") == "true"
    assert device_colours.is_checked()
    assert view.locator("[data-appearance-group]").count() == 0
    assert view.locator("[data-appearance-palette]").count() == 2
    scheme_icons = view.locator(".appearance-scheme-picker svg use")
    assert scheme_icons.count() == 2
    assert scheme_icons.nth(0).get_attribute("href").endswith("#light-mode")
    assert scheme_icons.nth(1).get_attribute("href").endswith("#dark-mode")
    assert view.locator(
        '[data-appearance-scheme-mode="device"] svg'
    ).count() == 0
    assert page.locator("#appearance-popover").count() == 0
    assert page.locator("#appearance-backdrop").count() == 0
    assert page.locator("#s-appearance").count() == 0

    view_bounds = view.bounding_box()
    main_bounds = page.locator("main").bounding_box()
    assert view_bounds and main_bounds
    assert view_bounds["x"] >= main_bounds["x"]
    assert view_bounds["x"] + view_bounds["width"] <= (
        main_bounds["x"] + main_bounds["width"] + 1)
    for selector in (
        '[data-appearance-scheme-mode="light"]',
        ".appearance-palette-tile",
        ".appearance-switch",
    ):
        bounds = view.locator(selector).first.bounding_box()
        assert bounds and bounds["height"] >= 48

    view.locator('[data-appearance-scheme-mode="light"]').click()
    assert page.locator("html").get_attribute("data-theme") == "light"
    device_colours.uncheck(force=True)
    view.locator('[data-appearance-palette="whatsapp"]').click()
    assert page.locator("html").get_attribute("data-palette") == "whatsapp"
    assert page.locator("html").get_attribute("data-color-mode") == "manual"
    whatsapp_light = page.evaluate("() => getComputedStyle(document.body).backgroundColor")

    view.locator('[data-appearance-palette="github"]').click()
    github_light = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    assert github_light != whatsapp_light

    view.locator('[data-appearance-scheme-mode="dark"]').click()
    github_dark = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    assert github_dark != github_light

    view.locator('[data-appearance-scheme-mode="device"]').click()
    assert page.locator("html").get_attribute("data-appearance") == "device"
    assert page.locator("html").get_attribute("data-theme") is None
    device_colours.check(force=True)
    assert page.locator("html").get_attribute("data-color-mode") == "device"
    assert page.locator("html").get_attribute("data-palette") is None


def _contrast(first: str, second: str) -> float:
    def luminance(colour: str) -> float:
        channels = [int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("palette", ["whatsapp", "github"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_manual_theme_keeps_text_controls_and_focus_legible(
        open_panel, palette, scheme):
    page = open_panel()
    values = page.evaluate("""([palette, scheme]) => {
        window.ScrapeXAppearance.set({
          mode: "manual", scheme, palette, deviceColors: false,
        });
        const style = getComputedStyle(document.documentElement);
        const read = (name) => style.getPropertyValue(name).trim().toUpperCase();
        return {
          text: read("--text"), muted: read("--muted"),
          subtle: read("--text-subtle"), surface: read("--surface"),
          bg: read("--bg"), accent: read("--accent"),
          accentHover: read("--accent-hover"),
          accentInk: read("--accent-ink"),
          accentContrast: read("--accent-contrast"),
          buttonBg: read("--button-bg"),
          buttonHover: read("--button-hover"),
          buttonText: read("--button-text"),
          buttonHoverText: read("--button-hover-text"),
          lineStrong: read("--line-strong"), focus: read("--focus"),
          amber: read("--amber"), amberWeak: read("--amber-weak"),
          red: read("--red"), redHover: read("--red-hover"),
          redWeak: read("--red-weak"),
          dangerContrast: read("--danger-contrast"),
          switchTrack: read("--switch-track"),
          switchTrackHover: read("--switch-track-hover"),
          switchTrackOff: read("--switch-track-off"),
          switchThumb: read("--switch-thumb"),
          switchThumbOff: read("--switch-thumb-off"),
        };
    }""", [palette, scheme])

    text_pairs = (
        ("text", "bg"),
        ("text", "surface"),
        ("muted", "surface"),
        ("subtle", "surface"),
        ("accentInk", "surface"),
        ("accentContrast", "accent"),
        ("accentContrast", "accentHover"),
        ("buttonText", "buttonBg"),
        ("buttonHoverText", "buttonHover"),
        ("amber", "amberWeak"),
        ("red", "redWeak"),
        ("dangerContrast", "red"),
    )
    for foreground, background in text_pairs:
        assert _contrast(values[foreground], values[background]) >= 4.5, (
            f"{palette} {scheme}: {foreground} on {background} is not WCAG AA")
    assert _contrast(values["lineStrong"], values["surface"]) >= 3
    assert _contrast(values["focus"], values["bg"]) >= 3
    assert _contrast(values["switchThumb"], values["switchTrack"]) >= 2.9
    assert _contrast(values["switchThumb"], values["switchTrackHover"]) >= 3
    assert _contrast(values["switchThumbOff"], values["switchTrackOff"]) >= 2.9


def test_whatsapp_theme_matches_the_current_application_palette(open_panel):
    page = open_panel()

    for scheme, expected in (
        ("light", {
            "--bg": "#F7F5F3", "--surface": "#FFFFFF",
            "--text": "#0A0A0A", "--accent": "#35AA65",
            "--accent-weak": "#DBFDD5", "--red": "#B3002F",
            "--red-weak": "#FCE5EA", "--switch-track": "#35AA65",
            "--switch-track-off": "#FFFFFF",
            "--switch-thumb-off": "#959393",
            "--button-bg": "#43D36D", "--button-hover": "#1C1E21",
            "--button-text": "#0A0A0A", "--button-hover-text": "#FFFFFF",
        }),
        ("dark", {
            "--bg": "#121B21", "--surface": "#182229",
            "--text": "#FFFFFF", "--accent": "#43D36D",
            "--red": "#FF7892", "--red-weak": "#3A1722",
            "--switch-track": "#35AA65", "--switch-track-off": "#182229",
            "--switch-thumb-off": "#959393",
            "--button-bg": "#43D36D", "--button-hover": "#FFFFFF",
            "--button-text": "#0A0A0A", "--button-hover-text": "#0A0A0A",
        }),
    ):
        values = page.evaluate("""([scheme, properties]) => {
            window.ScrapeXAppearance.set({
              mode: "manual", scheme, palette: "whatsapp", deviceColors: false,
            });
            const style = getComputedStyle(document.documentElement);
            return Object.fromEntries(properties.map((property) => [
              property, style.getPropertyValue(property).trim().toUpperCase(),
            ]));
        }""", [scheme, list(expected)])
        assert values == expected


def test_whatsapp_extension_layers_navigation_and_primary_hover(open_panel):
    page = open_panel()
    page.evaluate("""() => window.ScrapeXAppearance.set({
      mode: "manual", scheme: "light", palette: "whatsapp", deviceColors: false,
    })""")
    page.click("#tab-data")
    page.wait_for_timeout(220)

    initial = page.evaluate("""() => {
      const colour = (selector, property) =>
        getComputedStyle(document.querySelector(selector))[property];
      return {
        main: colour("main", "backgroundColor"),
        rail: colour("nav.side-rail", "backgroundColor"),
        indicator: colour("#rail-indicator", "backgroundColor"),
        active: colour("#tab-data", "color"),
        button: colour("#open-workbook", "backgroundColor"),
        buttonText: colour("#open-workbook", "color"),
      };
    }""")
    assert initial == {
        "main": "rgb(255, 255, 255)",
        "rail": "rgb(247, 245, 243)",
        "indicator": "rgb(53, 170, 101)",
        "active": "rgb(24, 134, 75)",
        "button": "rgb(67, 211, 109)",
        "buttonText": "rgb(10, 10, 10)",
    }

    page.hover("#open-workbook")
    page.wait_for_timeout(180)
    hovered = page.evaluate("""() => {
      const style = getComputedStyle(document.querySelector("#open-workbook"));
      return [style.backgroundColor, style.color];
    }""")
    assert hovered == ["rgb(28, 30, 33)", "rgb(255, 255, 255)"]


def test_vertical_tab_navigation_moves_the_indicator_and_the_content(open_panel):
    page = open_panel()
    page.focus(SOURCE_TAB)
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(220)

    assert page.is_visible("#view-run")
    assert page.get_attribute(RUN_TAB, "aria-current") == "page"
    indicator_y, run_y = page.evaluate("""() => [
        getComputedStyle(document.querySelector("nav.side-rail"))
          .getPropertyValue("--rail-indicator-y").trim(),
        document.querySelector('[data-view="run"]').offsetTop + "px",
    ]""")
    assert indicator_y == run_y

    page.click("#workspace-toggle")
    assert page.get_attribute("#workspace-menu", "aria-hidden") == "false"
    workspace_y = page.evaluate(
        "() => document.querySelector('#workspace-toggle').offsetTop + 'px'")
    assert page.evaluate("""() =>
        getComputedStyle(document.querySelector("nav.side-rail"))
          .getPropertyValue("--rail-indicator-y").trim()
    """) == workspace_y
    assert page.locator("nav.side-rail .rail-item.is-rail-active").count() == 1
    assert page.locator("#workspace-toggle").evaluate(
        "(button) => button.classList.contains('is-rail-active')")
    assert not page.locator(RUN_TAB).evaluate(
        "(button) => button.classList.contains('is-rail-active')")

    page.keyboard.press("Escape")
    assert page.get_attribute("#workspace-menu", "aria-hidden") == "true"
    assert page.evaluate("() => document.activeElement.id") == "workspace-toggle"
    assert page.evaluate("""() =>
        getComputedStyle(document.querySelector("nav.side-rail"))
          .getPropertyValue("--rail-indicator-y").trim()
    """) == run_y
    assert page.locator("nav.side-rail .rail-item.is-rail-active").count() == 1
    assert page.locator(RUN_TAB).evaluate(
        "(button) => button.classList.contains('is-rail-active')")


def test_a_tab_that_is_not_a_website_is_refused_with_a_reason(open_panel):
    page = open_panel(tab={"url": "chrome://extensions", "title": "Extensions"})
    assert page.is_disabled("#cur-use"), "a chrome:// page cannot be crawled"
    assert "not a website" in text_of(page, "#cur-title")
    assert "Open a site in this tab" in text_of(page, "#cur-out")


def test_an_engine_failure_is_not_reported_as_a_browser_failure(open_panel):
    """Blaming the tab for an engine error sends the owner to the wrong place."""
    page = open_panel(fail_routes=["/api/resolve"])
    page.wait_for_timeout(400)
    assert text_of(page, "#cur-title") == harness.ACTIVE_TAB["title"], \
        "the tab WAS readable; only the engine failed"
    assert "engine" in text_of(page, "#cur-out").lower()


def test_an_already_registered_page_says_so_and_offers_no_duplicate_add(open_panel):
    page = open_panel(resolve={"matched": True, "source_name": "Example Store",
                               "source_key": "SHOP_EXAMPLE", "implemented": True})
    page.wait_for_timeout(300)
    assert "Already registered" in text_of(page, "#cur-out")
    assert "Add" not in page.text_content("#cur-use"), \
        "offering Add for a site that exists promises something that must fail"


# ---- Current Page, after the owner navigates --------------------------------

def test_current_page_re_reads_the_tab_rather_than_trusting_a_stale_read(open_panel):
    """The panel stays open while the owner browses. Acting on the address read
    minutes ago would register whichever site they have since left."""
    page = open_panel()
    page.evaluate("""() => {
        window.chrome.tabs.query = async () => [
            {url: "https://a-different-store.example/x", title: "A Different Store"}];
    }""")
    page.click('label[for="source-current"]')
    page.wait_for_timeout(300)
    assert "a-different-store.example" in text_of(page, "#cur-url"), \
        "Use this page would have registered the site the owner already left"


# ---- the URL batch -----------------------------------------------------------

def test_pasted_addresses_are_each_reported_with_what_was_detected(open_panel):
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://second.example.com")
    page.click("#urls-check")
    page.wait_for_timeout(900)
    rows = page.locator("#urls-results .srow")
    assert rows.count() == 2
    assert "shopify-json" in page.text_content("#urls-results")


def test_every_review_button_works_the_moment_it_is_visible(open_panel):
    """A row rendered clickable but bound only after the LAST address finished
    means an early click silently does nothing."""
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://second.example.com")
    page.click("#urls-check")
    page.wait_for_selector("#urls-results [data-pick]")
    page.click("#urls-results [data-pick]")     # click the first one immediately
    page.wait_for_timeout(600)
    assert page.is_visible("#source-detail"), \
        "clicking Review did nothing — it was rendered before it was bound"


def test_an_unreachable_address_is_not_dressed_up_as_a_detected_platform(open_panel):
    page = open_panel(fail_routes=["/api/probe"])
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://nothing-here.example")
    page.click("#urls-check")
    page.wait_for_timeout(700)
    body = page.text_content("#urls-results")
    assert "shopify" not in body.lower(), "a failed probe must not report a family"
    assert "Pick one to review" not in text_of(page, "#urls-out"), \
        "there is nothing to pick when every address failed"


def test_a_malformed_address_is_refused_before_any_request(open_panel):
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "not-a-url")
    page.click("#urls-check")
    page.wait_for_timeout(300)
    assert "Not a full address" in text_of(page, "#urls-out")
    calls = page.evaluate("() => window.__calls.filter(c => c.startsWith('/api/probe'))")
    assert calls == [], "a malformed address must not reach the network"


# ---- Add Site ----------------------------------------------------------------

def test_using_the_current_page_opens_the_add_site_choice_with_it_filled_in(open_panel):
    page = open_panel()
    page.click("#cur-use")
    page.wait_for_timeout(800)
    assert page.is_checked("#source-addsite"), \
        "the form lives in the Add Site panel, which must be the one that opens"
    assert harness.ACTIVE_TAB["url"] in page.input_value("#url")
    assert page.is_visible("#source-detail")


def test_a_probe_fills_the_form_from_what_was_detected(open_panel):
    page = open_panel()
    page.click("#cur-use")
    page.wait_for_timeout(900)
    assert page.input_value("#f-key") == "SHOP_EXAMPLE"
    assert page.input_value("#f-currency") == "SAR"
    assert "Shopify" in page.text_content("#probe-out") or \
        "shopify" in page.text_content("#probe-out")


def test_the_unbuilt_file_source_cannot_be_actioned(open_panel):
    page = open_panel()
    page.click('label[for="source-file"]')
    page.wait_for_timeout(300)
    assert page.is_disabled('[data-integration="file-upload"]')
    assert page.is_disabled('[data-integration="screenshot-capture"]')


# ---- the sites list (spec 10) ------------------------------------------------

def test_select_all_selects_only_what_the_search_is_showing(open_panel):
    """Select All ignored the active filter and took the whole catalogue, while
    the count then contradicted the visible list."""
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(400)
    page.fill("#site-search", "a.co")
    page.wait_for_timeout(300)
    page.click("#select-all")
    page.wait_for_timeout(300)
    assert text_of(page, "#sel-count") == "1 selected", \
        "Select all took sites the owner could not see"


def test_an_unsupported_site_cannot_be_selected(open_panel):
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(400)
    assert page.is_disabled('input[data-key="NOT_READY"]')
    assert "Not supported yet" in page.text_content("#sites")


def test_the_engine_being_down_is_stated_not_left_blank(open_panel):
    page = open_panel(engine_up=False)
    page.click(RUN_TAB)
    page.wait_for_timeout(500)
    assert "Start the engine" in page.text_content("#sites") or \
        "Couldn't reach" in page.text_content("#sites")


# ---- data browsing and output configuration have separate homes --------------

def test_data_output_is_grouped_under_settings_not_run_or_data(open_panel):
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(300)
    assert "Data output settings" not in page.text_content("#view-run")

    page.click(DATA_TAB)
    page.wait_for_timeout(300)
    assert text_of(page, DATA_TAB) == "Data"
    assert "Browse Data" in page.text_content("#view-data")
    assert "Data output settings" not in page.text_content("#view-data")

    page.click(SETTINGS_TAB)
    page.click('button.sect[data-sect="s-output"]')
    page.wait_for_timeout(300)
    assert page.is_visible("#s-output")
    assert "Local storage" in page.text_content("#outputs")
    assert "Synchronization services" in page.text_content("#outputs")


def test_dataset_action_opens_the_workspace_directly(open_panel):
    page = open_panel()
    page.evaluate("""() => {
        window.__opened = [];
        window.chrome.tabs.create = (o) => window.__opened.push(o.url);
    }""")
    page.click(DATA_TAB)
    page.wait_for_timeout(300)
    assert page.locator("header.sx-header").count() == 0
    assert page.locator("#open-workbook").count() == 1
    assert page.locator("#datasets button").count() == 0
    assert "Open in Workspace" not in page.text_content("#view-data")

    page.click("#open-workbook")
    page.wait_for_timeout(200)
    opened = page.evaluate("() => window.__opened")
    assert len(opened) == 1
    assert opened[0].endswith("/data")

    page.evaluate("() => { window.__opened = []; }")
    page.click('[data-open="LONG_AR"]')
    page.wait_for_timeout(200)

    opened = page.evaluate("() => window.__opened")
    assert len(opened) == 1
    assert opened[0].endswith("/source/LONG_AR")


def test_data_rows_scroll_inside_the_browse_card_not_the_page(open_panel):
    page = open_panel()
    page.click(DATA_TAB)
    page.wait_for_timeout(200)

    page_overflow, list_overflow = page.evaluate("""() => [
        getComputedStyle(document.querySelector("main")).overflowY,
        getComputedStyle(document.querySelector("#datasets")).overflowY,
    ]""")
    assert page_overflow == "hidden"
    assert list_overflow == "auto"


def test_dataset_hover_does_not_move_the_card_out_of_its_scrollport(open_panel):
    page = open_panel()
    page.click(DATA_TAB)
    page.wait_for_timeout(200)

    card = page.locator("#datasets .dataset-card").first
    before = card.bounding_box()
    card.hover()
    page.wait_for_timeout(180)
    after = card.bounding_box()
    assert before and after and after["y"] == pytest.approx(before["y"], abs=.1)
    assert card.evaluate("(element) => getComputedStyle(element).transform") == "none"


# ---- source management ------------------------------------------------------

def test_sources_has_its_own_page_immediately_above_settings(open_panel):
    page = open_panel()
    sources_y, settings_y = page.evaluate("""() => [
        document.querySelector('[data-view="sources"]').offsetTop,
        document.querySelector('[data-view="settings"]').offsetTop,
    ]""")
    assert sources_y < settings_y

    page.click(SOURCES_TAB)
    page.wait_for_timeout(300)
    assert page.is_visible("#view-sources")
    assert page.locator("#source-manager-list .source-manager-card").count() == 3
    assert "3 of 3" in text_of(page, "#source-manager-count")


def test_add_source_opens_the_existing_working_form(open_panel):
    page = open_panel()
    page.click(SOURCES_TAB)
    page.click("#source-manager-add")
    page.wait_for_timeout(220)

    assert page.is_visible("#view-source")
    assert page.is_checked("#source-addsite")
    assert page.is_visible("#source-detail")
    assert page.evaluate("() => document.activeElement?.id") == "url"


def test_edit_source_stays_inside_the_extension(open_panel):
    page = open_panel()
    page.evaluate("""() => {
        window.__opened = [];
        window.chrome.tabs.create = (o) => window.__opened.push(o.url);
    }""")
    page.click(SOURCES_TAB)
    page.wait_for_timeout(300)
    page.click('[data-edit-source="SHORT"]')
    page.wait_for_timeout(220)

    assert page.is_visible("#view-source-edit")
    assert text_of(page, "#source-edit-domain") == "a.co"
    # The facts became editable fields when the owner asked to change a source
    # from the panel, so they carry a value rather than text now.
    assert page.input_value("#source-edit-name") == "A"
    assert page.input_value("#source-edit-key") == "SHORT"
    assert page.is_checked("#source-edit-active")
    assert page.get_attribute(SOURCES_TAB, "aria-current") == "page"
    assert page.evaluate("() => window.__opened") == []

    page.click("#source-edit-back")
    page.wait_for_timeout(220)
    assert page.is_visible("#view-sources")
    assert page.evaluate(
        "() => document.activeElement?.dataset.editSource") == "SHORT"


def test_edit_source_saves_automation_without_leaving_the_extension(open_panel):
    page = open_panel()
    page.click(SOURCES_TAB)
    page.wait_for_timeout(250)
    page.click('[data-edit-source="SHORT"]')
    page.uncheck("#source-edit-active")
    page.click("#source-edit-save")
    page.wait_for_timeout(250)

    calls = page.evaluate("() => window.__calls")
    assert any(call.startswith("/api/sources/SHORT/active") for call in calls)
    assert page.is_visible("#view-source-edit")
    assert "Changes saved" in text_of(page, "#source-edit-result")


def test_sources_scroll_inside_the_library_card_not_the_page(open_panel):
    page = open_panel()
    page.click(SOURCES_TAB)
    page.wait_for_timeout(200)

    page_overflow, list_overflow = page.evaluate("""() => [
        getComputedStyle(document.querySelector("main")).overflowY,
        getComputedStyle(document.querySelector("#source-manager-list")).overflowY,
    ]""")
    assert page_overflow == "hidden"
    assert list_overflow == "auto"


# ---- untrusted content (spec 34) --------------------------------------------

def test_a_scraped_name_containing_markup_cannot_inject_into_the_panel(open_panel):
    """Scraped values are untrusted. A site name is attacker-controlled text."""
    page = open_panel(sources=[{
        "source_key": "XSS", "base_url": "https://evil.example",
        "source_name": "<img src=x onerror=\"window.__owned=1\">",
        "family": "shopify-json", "active": True, "implemented": True,
        "observations": 1, "products": 1}])
    page.click(RUN_TAB)
    page.wait_for_timeout(500)
    assert page.evaluate("() => window.__owned") is None, "scraped markup executed"
    assert "<img" in page.text_content("#sites"), "it must render as visible text"


# ---- the last review minors --------------------------------------------------

def test_the_action_label_does_not_survive_onto_a_tab_it_cannot_apply_to(open_panel):
    """A stale "Open its dataset" on a chrome:// page promises something that
    page cannot do, even with the button disabled."""
    page = open_panel(resolve={"matched": True, "source_name": "Example Store",
                               "source_key": "SHOP_EXAMPLE", "implemented": True})
    page.wait_for_timeout(300)
    assert "Open its dataset" in page.text_content("#cur-use")

    page.evaluate("""() => {
        window.chrome.tabs.query = async () => [
            {url: "chrome://settings", title: "Settings"}];
    }""")
    page.click('label[for="source-current"]')
    page.wait_for_timeout(300)
    assert page.is_disabled("#cur-use")
    assert "Open its dataset" not in page.text_content("#cur-use")


# ---- keyboard access (spec 28) ----------------------------------------------

def test_the_workspace_links_can_be_reached_and_fired_from_the_keyboard(open_panel):
    """These three were click-only <span>s, and they are the ONLY routes from the
    panel into the workspace — so the Settings tab dead-ended completely for
    anyone not using a mouse. A span takes no focus and fires on no key."""
    page = open_panel()
    page.evaluate("""() => {
        window.__opened = [];
        window.chrome.tabs.create = (o) => window.__opened.push(o.url);
    }""")
    page.click('nav.tabs button[data-view="settings"]')
    page.wait_for_timeout(300)
    # The links live behind progressive disclosure, so reaching them by keyboard
    # means the section toggle has to be operable that way too.
    page.focus('button.sect[data-sect="s-storage"]')
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert page.is_visible("#open-storage"), "the section did not open from the keyboard"

    for control in ("#open-storage", "#open-browse"):
        page.focus(control)
        assert page.evaluate(
            "(sel) => document.activeElement === document.querySelector(sel)", control
        ), f"{control} cannot take keyboard focus"
        page.keyboard.press("Enter")

    page.wait_for_timeout(300)
    opened = page.evaluate("() => window.__opened")
    assert len(opened) == 2, f"a keyboard press opened nothing: {opened}"


def test_nothing_that_looks_like_a_link_is_an_unfocusable_span(open_panel):
    """A guard, not a spot check: the styling makes these read as links, so the
    next one added as a <span> would look correct and be unusable."""
    page = open_panel()
    offenders = page.evaluate("""() => Array.from(
        document.querySelectorAll('.link'))
        .filter(el => !['BUTTON', 'A', 'INPUT'].includes(el.tagName))
        .map(el => el.tagName + '#' + (el.id || '?') + ' — ' + el.textContent.trim())""")
    assert offenders == [], f"click-only controls, unreachable by keyboard: {offenders}"


def test_duplicate_pasted_addresses_do_not_stall_the_counter(open_panel):
    page = open_panel()
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://shop.example.com")
    page.click("#urls-check")
    page.wait_for_timeout(900)
    assert page.locator("#urls-results .srow").count() == 2, \
        "both pasted lines must be reported, even when identical"


# ---- run modes follow the data (owner rule) ----------------------------------
#
# "Update existing data" over a site with no data is not an update of anything,
# and a rebuild has nothing to archive; "Initial crawl" over sites that all
# have data already happened. The select must say so, not let a meaningless
# choice run and be quietly reinterpreted.

EMPTY_SITE = {"source_key": "FRESH", "base_url": "https://fresh.example.com",
              "source_name": "Fresh Site", "family": "shopify-json",
              "active": True, "implemented": True, "observations": 0, "products": 0}
FULL_SITE = {"source_key": "STOCKED", "base_url": "https://stocked.example.com",
             "source_name": "Stocked Site", "family": "salla-html",
             "active": True, "implemented": True, "observations": 42, "products": 7}


def _pick(page, key):
    page.click(RUN_TAB)
    page.wait_for_timeout(400)
    page.check(f'input[data-key="{key}"]')
    page.wait_for_timeout(200)


def test_run_mode_uses_the_themed_listbox_instead_of_the_native_blue_popup(open_panel):
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(200)

    native_proxy = page.locator("#run-mode").evaluate("""element => {
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return {
        pointerEvents: style.pointerEvents,
        clipped: style.clipPath !== "none",
        width: box.width,
        height: box.height,
      };
    }""")
    assert native_proxy["pointerEvents"] == "none"
    assert native_proxy["clipped"]
    assert native_proxy["width"] <= 1 and native_proxy["height"] <= 1
    page.click("#run-mode-trigger")
    assert page.locator("#run-mode-list").is_visible()
    assert page.locator("#run-mode-list [role=option]").count() == 4
    selected = page.locator('#run-mode-list [aria-selected="true"]')
    assert selected.count() == 1
    assert selected.text_content().strip() == "Update existing data"
    themed = selected.evaluate("""element => {
      const probe = document.createElement("i");
      probe.style.background = "var(--primary-container)";
      document.body.append(probe);
      const expected = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return getComputedStyle(element).backgroundColor === expected;
    }""")
    assert themed, "the selected row escaped the active theme"

    page.keyboard.press("Escape")
    assert not page.locator("#run-mode-list").is_visible()


def test_update_is_not_on_offer_for_a_site_with_no_data(open_panel):
    page = open_panel(sources=[EMPTY_SITE, FULL_SITE])
    _pick(page, "FRESH")

    assert page.is_disabled('#run-mode option[value="update"]')
    assert page.is_disabled('#run-mode option[value="full_rebuild"]')
    assert page.input_value("#run-mode") == "initial_crawl"
    assert "first crawl" in page.text_content("#mode-help")


def test_a_first_crawl_is_not_on_offer_where_it_already_happened(open_panel):
    page = open_panel(sources=[EMPTY_SITE, FULL_SITE])
    _pick(page, "STOCKED")

    assert page.is_disabled('#run-mode option[value="initial_crawl"]')
    assert not page.is_disabled('#run-mode option[value="update"]')
    assert not page.is_disabled('#run-mode option[value="full_rebuild"]')


def test_a_mixed_selection_offers_every_mode(open_panel):
    page = open_panel(sources=[EMPTY_SITE, FULL_SITE])
    _pick(page, "FRESH")
    page.check('input[data-key="STOCKED"]')
    page.wait_for_timeout(200)

    for value in ("update", "initial_crawl", "full_rebuild"):
        assert not page.is_disabled(f'#run-mode option[value="{value}"]'), value


def test_a_chosen_mode_that_stops_meaning_anything_is_moved_visibly(open_panel):
    """Select a stocked site, choose Update, then swap the selection to an
    empty site: running "update" now would update nothing. The select must
    move to the only honest mode and the help line must say why."""
    page = open_panel(sources=[EMPTY_SITE, FULL_SITE])
    _pick(page, "STOCKED")
    page.select_option("#run-mode", "update")
    page.wait_for_timeout(150)

    page.uncheck('input[data-key="STOCKED"]')
    page.check('input[data-key="FRESH"]')
    page.wait_for_timeout(200)

    assert page.input_value("#run-mode") == "initial_crawl"
    assert "no data yet" in page.text_content("#mode-help")
    assert "Start initial crawl" in page.text_content("#run")


# ---- history backfill is offered per CAPABILITY, not per data ----------------

HISTORY_SITE = {"source_key": "GPP_LIKE", "base_url": "https://prices.example.com",
                "source_name": "Energy Prices", "family": "static-html-table",
                "active": True, "implemented": True, "observations": 700,
                "products": 5, "supports_history": True}


def test_history_backfill_is_offered_only_where_the_source_publishes_history(open_panel):
    page = open_panel(sources=[HISTORY_SITE, FULL_SITE])
    _pick(page, "GPP_LIKE")

    assert not page.is_disabled('#run-mode option[value="history_backfill"]')

    page.check('input[data-key="STOCKED"]')     # a shop joins the selection
    page.wait_for_timeout(200)
    assert page.is_disabled('#run-mode option[value="history_backfill"]'), \
        "a shop with no history capability left the mode on offer"
    assert "History backfill is available only for" in page.text_content("#mode-help")
    assert "Energy Prices" in page.text_content("#mode-help")


# ---- the rebuilt Activity panel: progress that states its denominator --------

def _running_job(**over):
    job = {
        "job_ref": "job_live", "source_keys": ["SALLA_SHOP"],
        "status": "running", "stage": "fetching",
        "started_at": "2026-07-30T10:00:00Z", "current_source_key": "SALLA_SHOP",
        "progress": {"done": 0, "total": 1},
        "fetch": {"requests": 0, "expected": None, "basis": None, "as_of": None,
                  "unknown_sources": [], "sources": {}},
        "counters": {"observations": 0, "duplicates": 0, "products": 0,
                     "requests": 0, "errors": 0},
        "queued_behind": None,
    }
    job.update(over)
    return job


def _bar_width_pct(page):
    return page.evaluate("""() => {
        const bar = document.getElementById("act-bar");
        const fill = bar.getBoundingClientRect().width;
        const track = bar.parentElement.getBoundingClientRect().width;
        return track ? Math.round(fill / track * 100) : 0;
    }""")


def _open_on_run(open_panel, **kw):
    """Open the panel and reveal the Run view, where the Activity card lives."""
    page = open_panel(**kw)
    page.click(RUN_TAB)
    page.wait_for_timeout(400)
    return page


def test_the_bar_is_a_fraction_of_requests_against_a_stated_denominator(open_panel):
    """The whole complaint: 0% for 18 minutes because the bar measured SOURCES.
    Now it measures requests against a real total, and the sentence beneath it
    says what that total is and — for an estimate — its date."""
    job = _running_job(
        current_source_key="SALLA_SHOP",
        fetch={"requests": 1030, "expected": 2461, "basis": "estimate",
               "as_of": "2026-07-29", "unknown_sources": [],
               "sources": {"SALLA_SHOP": {"state": "fetching", "requests": 1030,
                                          "expected": 2461, "basis": "estimate",
                                          "as_of": "2026-07-29", "not_modified": 40,
                                          "retries": 2, "pace_s": 1.0,
                                          "honouring_delay": True}}})
    page = _open_on_run(open_panel, jobs=[job])

    label = text_of(page, "#act-progress-label")
    assert "1,030" in label and "2,461" in label, label
    assert "42%" in label, label                 # 1030/2461
    assert "estimate" in label and "29 Jul" in label, label
    width = _bar_width_pct(page)
    assert 38 <= width <= 46, f"the bar did not reflect the fraction: {width}%"
    # The politeness read-out the owner asked for: 304s against the total.
    assert "304" in text_of(page, "#act-counters")
    assert not page.js_errors


def test_a_declared_total_reads_as_a_count_not_an_estimate(open_panel):
    """A sitemap connector KNOWS its frontier — that is a count, so no "~" and no
    date, and the bar is a true fraction from the first pages."""
    job = _running_job(
        fetch={"requests": 50, "expected": 400, "basis": "declared", "as_of": None,
               "unknown_sources": [],
               "sources": {"SALLA_SHOP": {"state": "fetching", "requests": 50,
                                          "expected": 400, "basis": "declared"}}})
    page = _open_on_run(open_panel, jobs=[job])
    label = text_of(page, "#act-progress-label")
    assert "50" in label and "400" in label
    assert "estimate" not in label
    assert "page count" in label            # "the site's own page count"
    assert not page.js_errors


def test_an_unknown_denominator_reads_as_unknown_not_zero_percent(open_panel):
    """A first-ever crawl of a site with no sitemap genuinely cannot know its
    total. The bar is indeterminate and SAYS the total is not known — the one
    thing it must never do is sit at 0% of a number nobody has."""
    job = _running_job(
        fetch={"requests": 340, "expected": None, "basis": None, "as_of": None,
               "unknown_sources": ["SALLA_SHOP"],
               "sources": {"SALLA_SHOP": {"state": "fetching", "requests": 340}}})
    page = _open_on_run(open_panel, jobs=[job])

    label = text_of(page, "#act-progress-label")
    assert "340" in label
    assert "not known yet" in label, label
    assert "0%" not in label
    assert page.locator("#act-bar").evaluate("el => el.classList.contains('indeterminate')")
    assert not page.js_errors


def test_a_queued_second_job_says_why_it_waits(open_panel):
    """"queued" with no reason read as the parallel feature failing. Now it names
    what holds the worker and this job's place in line."""
    job = _running_job(
        status="queued", stage=None, current_source_key=None, started_at=None,
        fetch={"requests": 0, "expected": None, "basis": None, "as_of": None,
               "unknown_sources": [], "sources": {}},
        queued_behind={"position": 1, "capacity": 1, "running_count": 1,
                       "starting_now": False,
                       "running": [{"job_ref": "job_first",
                                    "source_keys": ["ELBUROJ"]}]})
    page = _open_on_run(open_panel, jobs=[job])
    queue = text_of(page, "#act-queue")
    assert "Queued" in queue
    assert "ELBUROJ" in queue
    assert "slot frees" in queue
    assert "Sites crawled at the same time" in queue   # points to the fix
    assert not page.js_errors


# ---- the log: no cap, one split button, no auto-scroll button ----------------

def _log_entries(n):
    return [{"logged_at": f"2026-07-30T10:{i // 60:02d}:{i % 60:02d}Z",
             "level": "info", "message": f"fetching — {i} requests so far"}
            for i in range(n)]


def test_no_log_entry_is_dropped_and_the_cap_is_gone(open_panel):
    """The 200 cap was the client's, and it dropped exactly the line that
    explained a long run's failure. Every entry is shown, and the request no
    longer asks for a limited slice."""
    entries = _log_entries(250)
    page = _open_on_run(open_panel, jobs=[_running_job()], logs=entries)

    assert page.locator("#logbox .logline").count() == 250, "the log was truncated"
    assert "250" in text_of(page, "#log-caption") and "all shown" in text_of(page, "#log-caption")
    # No caller asked for ?limit=200 (or any limit) on the log endpoint.
    limited = page.evaluate(
        "() => window.__calls.filter(p => /\\/logs/.test(p) && /limit=/.test(p))")
    assert limited == [], f"a log fetch still capped itself: {limited}"


def test_the_pause_auto_scroll_button_is_gone(open_panel):
    """He asked for it removed."""
    page = _open_on_run(open_panel, jobs=[_running_job()], logs=_log_entries(5))
    assert page.locator("#autoscroll").count() == 0
    body = page.text_content("#activity")
    assert "auto-scroll" not in body.lower()


def test_the_log_controls_are_one_shared_split_button(open_panel):
    """Copy and Download become ONE split button — the SAME component the dataset
    Export uses, not a second implementation."""
    page = _open_on_run(open_panel, jobs=[_running_job()], logs=_log_entries(5))

    split = page.locator("#activity .split-button")
    assert split.count() == 1
    # The primary copies; the menu holds copy + download. Wired by the shared
    # ScrapeXSplitButton, so the menu opens and closes like the Export one.
    assert page.locator('#activity .split-button-primary[data-split-action="copy"]').count() == 1
    assert page.locator('#activity [data-split-action="download"]').count() == 1
    assert "Every line now on screen" not in split.text_content()
    assert "engine's complete record" not in split.text_content()

    menu = page.locator("#activity .split-button-menu")
    assert not menu.evaluate("el => el.open")
    page.click("#activity .split-button-trigger")
    assert menu.evaluate("el => el.open"), "the shared split-button behaviour did not open the menu"
    assert not page.js_errors


def test_the_split_button_copies_the_visible_log_and_downloads_the_full_one(open_panel):
    """Both actions do what they say: copy writes the on-screen lines to the
    clipboard; download opens the FULL log endpoint, uncapped."""
    page = _open_on_run(open_panel, jobs=[_running_job()], logs=_log_entries(3))
    page.evaluate("""() => {
        window.__copied = [];
        navigator.clipboard.writeText = (t) => { window.__copied.push(t); return Promise.resolve(); };
        window.__opened = [];
        window.chrome.tabs.create = (o) => window.__opened.push(o.url);
    }""")

    page.click('#activity .split-button-primary[data-split-action="copy"]')
    page.wait_for_timeout(100)
    copied = page.evaluate("() => window.__copied")
    assert copied and "fetching — 0 requests so far" in copied[0]
    assert copied[0].count("\n") == 2, "copy did not carry every visible line"

    page.click("#activity .split-button-trigger")
    page.click('#activity [data-split-action="download"]')
    page.wait_for_timeout(100)
    opened = page.evaluate("() => window.__opened")
    assert len(opened) == 1 and opened[0].endswith("/api/jobs/job_live/logs"), opened
    assert "limit=" not in opened[0], "the full-log download capped itself"
    assert not page.js_errors


def test_the_data_tab_states_when_each_source_was_last_crawled(open_panel):
    """The card read "no recorded changes yet"; the freshness of the data is the
    fact the owner actually asked for."""
    sources = [
        {"source_key": "SALLA_SHOP", "base_url": "https://shop.example.com",
         "source_name": "Example Shop", "family": "salla-html", "active": True,
         "implemented": True, "observations": 763, "products": 763,
         "last_success": {"started_at": "2026-07-29T08:30:00Z", "finished_at": "",
                          "rows_seen": 763, "requests_count": 812,
                          "products_discovered": 763, "errors_count": 0}},
    ]
    page = open_panel(sources=sources)
    page.click(DATA_TAB)
    page.wait_for_timeout(300)
    card = page.text_content("#datasets")
    assert "Last crawled 2026-07-29 08:30" in card
    assert "763 rows seen" in card
    assert "no recorded changes yet" not in card
    assert not page.js_errors


def test_a_source_that_never_succeeded_says_so_on_the_data_tab(open_panel):
    """"never" is a real answer the card must state, not paper over with a zero."""
    sources = [
        {"source_key": "NEWSHOP", "base_url": "https://new.example.com",
         "source_name": "New Shop", "family": "salla-html", "active": True,
         "implemented": True, "observations": 5, "products": 5, "last_success": None},
    ]
    page = open_panel(sources=sources)
    page.click(DATA_TAB)
    page.wait_for_timeout(300)
    assert "no successful crawl yet" in page.text_content("#datasets")
    assert not page.js_errors


# ---- active crawl status bar -------------------------------------------------

def test_the_active_crawl_minimizes_to_a_statusbar_and_opens_again(open_panel):
    job = {
        "job_ref": "job_live", "source_keys": ["GPP_ENERGY"],
        "status": "running", "stage": "crawl", "started_at": "2026-07-22T10:00:00Z",
        "current_source_key": "GPP_ENERGY",
        "progress": {"done": 0, "total": 1, "percent": 0},
        "counters": {"observations": 0, "duplicates": 0, "products": 0,
                     "requests": 1, "errors": 0},
    }
    page = open_panel(jobs=[job])
    bar = page.locator("#miniplayer")

    assert bar.is_visible()
    assert bar.evaluate("el => el.tagName") == "DETAILS"
    assert not bar.evaluate("el => el.open"), "a running crawl should rest minimized"
    assert page.is_visible("#mini-title") and page.is_visible("#mini-pct")
    assert not page.is_visible("#mini-sub")
    assert not page.is_visible("#mini-pause")

    page.click("#miniplayer > summary")
    assert bar.evaluate("el => el.open")
    for control in ("#mini-view", "#mini-pause", "#mini-cancel"):
        assert page.is_visible(control), f"{control} did not open with the status bar"
    assert not page.evaluate(
        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth")

    page.focus("#miniplayer > summary")
    page.keyboard.press("Enter")
    assert not bar.evaluate("el => el.open")
    assert page.is_visible("#mini-title"), "minimizing hid the crawl status itself"
    assert not page.js_errors


def test_no_surface_tells_the_owner_to_open_a_terminal():
    """The owner's standing rule: anything that needs a terminal is a missing
    button. The panel told him to run `scrapex ui` in one - on a machine where
    the launcher WAS installed and the helper answered - because a cold start
    took longer than the five-second budget and every failure printed the same
    sentence."""
    panel = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    settings = (ROOT / "scrapex" / "webui" / "templates" / "settings.html").read_text(encoding="utf-8")

    for surface, name in ((panel, "the panel"), (settings, "Settings")):
        assert "scrapex ui" not in surface, f"{name} still names a terminal command"
        assert "in a terminal" not in surface, f"{name} still sends the owner to a terminal"


def test_each_native_failure_is_named_rather_than_blamed_on_the_install():
    """One anonymous Error for four different failures is how "the launcher is
    not installed" got printed on a working install."""
    transport = (ROOT / "extension" / "transport.js").read_text(encoding="utf-8")
    panel = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")

    for kind in ("absent", "forbidden", "crashed", "timeout"):
        assert f'"{kind}"' in transport, f"transport cannot report {kind}"
        assert f'"{kind}"' in panel, f"the panel has no message for {kind}"
    # Starting an engine is not a ping and may not be judged by a ping's budget.
    assert "START_TIMEOUT_MS = 60000" in transport
    assert "sendNative({ command: \"START_ENGINE\" }, START_TIMEOUT_MS)" in transport


# ---- adding a site: which SYSTEM it goes to ----------------------------------
# MarketLens and General are two systems with two databases. The panel asks
# before the form is filled, because nothing converts one into the other
# afterwards, and the two do not even spell a key the same way.

def _open_add_form(page):
    """Reach the filled-in Add Site form the way a person does: pick Add Site,
    type a URL, test it. The form is revealed only by a successful probe."""
    page.click(SOURCE_TAB)
    page.click('label[for="source-addsite"]')
    page.fill("#url", "https://shop.example.com")
    # Fired through getElementById rather than clicked. The harness inlines the
    # icon sprite ahead of the body, so `document.getElementById("check")`
    # returns the sprite's <symbol id="check"> - and the panel binds its Test
    # site handler to exactly that element. A real click on the button would
    # therefore reach no listener at all. This is an artifact of the harness,
    # not of the panel: in the extension the sprite is an external file.
    page.evaluate("""() => document.getElementById("check")
        .dispatchEvent(new MouseEvent("click", {bubbles: true}))""")
    page.wait_for_selector("#add-form:not(.hidden)")


def test_store_is_the_default_and_the_price_settings_are_shown(open_panel):
    page = open_panel()
    _open_add_form(page)
    assert page.is_checked("input[name='add-system'][value='store']")
    assert page.is_visible("#add-price-only"), "the price settings must be visible for a shop"
    assert page.is_visible("#add-name-ar-row")
    assert page.text_content("#add-btn").strip() == "Add site"


def test_choosing_general_hides_every_price_setting_rather_than_ignoring_it(open_panel):
    """General does not read prices. Leaving VAT, currency and identity rules on
    screen would invite the owner to fill in fields that go nowhere."""
    page = open_panel()
    _open_add_form(page)
    page.click("label:has(input[name='add-system'][value='general'])")
    assert not page.is_visible("#add-price-only")
    assert not page.is_visible("#add-name-ar-row"),         "the General catalogue stores one display name, so an Arabic one would be dropped"
    assert page.is_visible("#f-key") and page.is_visible("#f-name")
    assert "General" in page.text_content("#add-btn")
    assert "General" in page.text_content("#add-system-note")


def test_the_key_is_respelled_for_the_system_it_is_going_to(open_panel):
    """MarketLens keys are UPPER_SNAKE, General keys are lower_snake. The probe
    suggests the MarketLens spelling, so a General registration would be handed
    a key its own validator rejects — after the form looked correctly filled."""
    page = open_panel()
    _open_add_form(page)
    assert page.input_value("#f-key") == "SHOP_EXAMPLE"
    page.click("label:has(input[name='add-system'][value='general'])")
    assert page.input_value("#f-key") == "shop_example"
    page.click("label:has(input[name='add-system'][value='store'])")
    assert page.input_value("#f-key") == "SHOP_EXAMPLE"


def test_each_system_registers_against_its_own_endpoint(open_panel):
    """The two systems have two databases; posting a General site to
    /api/sources would file it in the price warehouse."""
    page = open_panel()
    _open_add_form(page)
    page.evaluate("() => { window.__calls.length = 0; }")
    page.click("#add-btn")
    page.wait_for_timeout(200)
    store_calls = page.evaluate("() => window.__calls.slice()")
    assert any(c.startswith("/api/sources") for c in store_calls), store_calls

    # A finished add closes the form and moves to Run, so the General half
    # starts from a freshly opened form rather than a screen that is gone.
    _open_add_form(page)
    page.click("label:has(input[name='add-system'][value='general'])")
    page.evaluate("() => { window.__calls.length = 0; }")
    page.click("#add-btn")
    page.wait_for_timeout(200)
    general_calls = page.evaluate("() => window.__calls.slice()")
    assert any(c.startswith("/api/general/catalog/sites") for c in general_calls), general_calls
    assert not any(c.startswith("/api/sources") for c in general_calls),         "a General site must not be filed in the price warehouse"


def test_a_key_in_the_wrong_spelling_is_refused_with_that_system_s_rule(open_panel):
    page = open_panel()
    _open_add_form(page)
    page.click("label:has(input[name='add-system'][value='general'])")
    page.fill("#f-key", "SHOP EXAMPLE!")
    page.click("#add-btn")
    page.wait_for_timeout(100)
    assert "lower_snake_case" in page.text_content("#err-key")


# ---- the crawl pace is reachable from the panel, 2026-07-29 ---------------

def test_the_crawl_pace_can_be_read_and_changed_from_the_panel(open_panel):
    """It had been built, plumbed to the fetcher, and rendered ONLY on the
    engine's own web page — so from here, where the work happens, it did not
    exist and the owner asked for a feature that had already shipped."""
    page = open_panel()
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(300)

    assert page.is_visible("#s-crawl")
    assert page.is_checked("#crawl_honour_delay")
    assert page.input_value("#crawl_min_interval_s") == "1.0"
    # The consequence is spelled out, not left as a bare checkbox: this one
    # decides whether elburoj takes one hour or eleven.
    assert "wins" in page.inner_text("#crawl-pace-effect")

    page.uncheck("#crawl_honour_delay")
    page.wait_for_timeout(100)
    assert "Our pace only" in page.inner_text("#crawl-pace-effect")
    assert not page.js_errors


def test_a_pace_of_zero_is_refused_before_it_reaches_the_engine(open_panel):
    """Zero seconds between requests is not a pace, it is a flood."""
    page = open_panel()
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(300)
    page.fill("#crawl_min_interval_s", "0")
    page.click("#crawl-save")
    page.wait_for_timeout(200)

    assert "greater than zero" in page.inner_text("#crawl-msg")
    posted = page.evaluate("window.__calls.filter(c => c.includes('/api/settings'))")
    assert not [c for c in posted if "POST" in c], "the flood reached the engine"


# ---- kept pages: a partly crawled site can be continued, 2026-07-29 ---------
#
# «ازرار الخاصة بـresume للمواقع التى تم زحف جزء منها غير موجودة» — the engine
# had journaled 871 elburoj pages and could resume from them, but the panel
# never said they existed and offered no way to continue. The only button on
# the row was the one that throws them away.

KEPT_SITE = {"source_key": "ELBUROJ", "base_url": "https://elburoj.com",
             "source_name": "Elburoj", "source_name_ar": "البروج",
             "family": "salla-html", "active": False, "implemented": True,
             "observations": 0, "products": 0,
             "kept_pages": 871, "kept_at": "2026-07-29T09:14:30Z"}
CLEAN_SITE = {"source_key": "MADAR", "base_url": "https://madar.example.com",
              "source_name": "Madar", "family": "salla-html",
              "active": True, "implemented": True,
              "observations": 120, "products": 40,
              "kept_pages": 0, "kept_at": None}


def _run_tab(page):
    page.click(RUN_TAB)
    page.wait_for_timeout(400)


def _writes(page, path="/api/jobs"):
    return [w for w in page.evaluate("() => window.__writes.slice()")
            if w["path"].startswith(path)]


def test_a_partly_crawled_site_says_how_much_it_kept_and_offers_to_continue(open_panel):
    """The count is the whole point: "partly crawled" with no number is not
    something the owner can decide anything from."""
    page = open_panel(sources=[KEPT_SITE, CLEAN_SITE])
    _run_tab(page)

    resume = page.locator('button[data-resume="ELBUROJ"]')
    assert resume.is_visible()
    assert "871" in resume.inner_text()

    note = page.inner_text("#sites")
    assert "871 pages kept" in note
    assert "stopped" in note and "Jul" in note and "Invalid" not in note
    # The difference between the two buttons is stated, not left to be guessed.
    assert "re-fetches none of them" in note and "discards them" in note


def test_a_site_with_nothing_kept_is_offered_no_resume(open_panel):
    """A Resume that starts from the top would be a lie, and the row would carry
    a control that does nothing it says."""
    page = open_panel(sources=[KEPT_SITE, CLEAN_SITE])
    _run_tab(page)

    assert page.locator('button[data-resume="MADAR"]').count() == 0
    assert "kept" not in text_of(page, '.srow:has(input[data-key="MADAR"])')


def test_resume_queues_a_run_that_continues_instead_of_starting_over(open_panel):
    page = open_panel(sources=[KEPT_SITE, CLEAN_SITE])
    _run_tab(page)
    page.evaluate("() => { window.__writes.length = 0; }")

    page.click('button[data-resume="ELBUROJ"]')
    page.wait_for_timeout(300)

    queued = _writes(page)
    assert queued, page.evaluate("() => window.__writes.slice()")
    assert queued[0]["body"] == {
        "source_keys": ["ELBUROJ"], "resume": True, "run_mode": "initial_crawl"}
    assert not page.js_errors


def test_a_fresh_run_warns_before_it_throws_the_kept_pages_away(open_panel):
    """Losing 871 pages and most of a day to a mis-click is exactly the failure
    this feature exists to prevent."""
    page = open_panel(sources=[KEPT_SITE, CLEAN_SITE])
    _run_tab(page)
    page.check('input[data-key="ELBUROJ"]')
    asked: list[str] = []
    page.on("dialog", lambda d: (asked.append(d.message), d.dismiss()))
    page.evaluate("() => { window.__writes.length = 0; }")

    page.click("#run")
    page.wait_for_timeout(300)

    assert asked, "the run started with no warning at all"
    assert "871 pages" in asked[0] and "ELBUROJ" in asked[0]
    assert not _writes(page), "the kept pages were discarded without a word"


def test_the_warned_run_still_runs_when_the_owner_says_yes(open_panel):
    """The warning is a warning, not a block — and what it starts is a plain
    run, never a resume wearing the wrong name."""
    page = open_panel(sources=[KEPT_SITE, CLEAN_SITE])
    _run_tab(page)
    page.check('input[data-key="ELBUROJ"]')
    page.on("dialog", lambda d: d.accept())
    page.evaluate("() => { window.__writes.length = 0; }")

    page.click("#run")
    page.wait_for_timeout(300)

    queued = _writes(page)
    assert queued and queued[0]["body"] == {
        "source_keys": ["ELBUROJ"], "run_mode": "initial_crawl"}


def test_a_selection_that_keeps_nothing_is_not_nagged(open_panel):
    """The warning must fire on the fact, not on every run."""
    page = open_panel(sources=[KEPT_SITE, CLEAN_SITE])
    _run_tab(page)
    page.check('input[data-key="MADAR"]')
    asked: list[str] = []
    page.on("dialog", lambda d: (asked.append(d.message), d.accept()))

    page.click("#run")
    page.wait_for_timeout(300)

    assert asked == []
    assert _writes(page), "the run did not start"


def test_the_number_of_sites_crawled_at_once_is_reachable(open_panel):
    """The engine gained per-host concurrency and the panel had no field for it,
    so the feature shipped switched off with no way to switch it on — the same
    shape of miss as the crawl pace itself."""
    page = open_panel()
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(300)

    assert page.input_value("#crawl_parallel_sources") == "1"
    # One at a time is the default, and the panel says what that COSTS.
    assert "holds up every source" in page.inner_text("#crawl-parallel-effect")

    page.fill("#crawl_parallel_sources", "4")
    page.wait_for_timeout(100)
    effect = page.inner_text("#crawl-parallel-effect")
    assert "4 different sites" in effect
    # The part people get wrong, said out loud: no site is asked for more.
    assert "SAME site" in effect
    assert not page.js_errors


def test_a_width_above_the_engines_ceiling_is_clamped_not_ignored(open_panel):
    """The engine clamps to MAX_PARALLEL_SOURCES anyway. Accepting 40 and
    silently running 8 would teach the owner a number that is not true."""
    page = open_panel()
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(300)
    page.fill("#crawl_parallel_sources", "40")
    page.click("#crawl-save")
    page.wait_for_timeout(300)

    writes = page.evaluate(
        "window.__writes.filter(w => w.path.startsWith('/api/settings'))")
    assert writes, "nothing was sent to the engine"
    assert writes[-1]["body"]["crawl_parallel_sources"] == "8", (
        "40 reached the engine, which clamps to 8 — so the panel taught a "
        "number that is not what runs")
    assert "saved" in page.inner_text("#crawl-msg")


# ---- the display time zone (spec 33 / issue #33), 2026-07-30 ----------------
#
# The owner ruled on 2026-07-30 that the SELECTOR lives here and nowhere else:
# the web page displays the active zone and never offers to change it (issue #32
# §2.3). So the panel is the only surface where "can he choose a zone" can be
# asked at all, and these are the tests that ask it.

# 22:30 UTC is deliberate. In Asia/Riyadh (+03, no DST) it is 01:30 the NEXT
# DAY, so every assertion below distinguishes a real conversion from a string
# that merely got reformatted — the day has to move too.
KEPT_LATE = {**KEPT_SITE, "kept_at": "2026-07-30T22:30:00Z"}

SCHEDULE_SOON = {
    "schedules": [{"source_key": "MADAR", "schedule_id": 1, "enabled": True,
                   "frequency": "daily", "run_at": "09:00", "weekday": None,
                   "timezone": "Asia/Riyadh", "run_mode": "update",
                   "missed_run_policy": "run_when_available",
                   "overlap_policy": "queue",
                   "next_run_at": "2026-07-30T22:30:00Z"}],
    "note": "Schedules run only while the ScrapeX engine is running.",
}


def _open_time_zone(page):
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-timezone"]')
    page.wait_for_timeout(300)


def _choose_zone(page, zone: str):
    page.select_option("#ui_time_zone", zone)
    page.wait_for_timeout(350)


def test_the_time_zone_can_be_chosen_from_the_panels_settings_tab(open_panel):
    """Spec 33 6.1 and 6.4: a real selector, filled from the browser's own list.

    The count matters. A hand-written list is the thing 6.4 rules out, because
    it starts rotting the day a country moves its clocks — so the assertion is
    that the list is far longer than anyone would type, and that the issue's own
    four examples are all in it.
    """
    page = open_panel()
    _open_time_zone(page)

    assert page.is_visible("#ui_time_zone")
    options = page.eval_on_selector(
        "#ui_time_zone", "s => [...s.options].map(o => o.value)")
    assert len(options) > 100, (
        f"only {len(options)} zones offered — that is a hand-written list, and "
        "6.4 asks for the IANA set the browser itself publishes")
    for example in ["Asia/Riyadh", "Europe/London", "America/New_York", "Asia/Dubai"]:
        assert example in options, f"{example} (named in 6.4) is not offered"

    # "" is first and means Detected: 6.5's default is an option he can come
    # back to, not a zone silently written in his name.
    assert options[0] == ""
    assert "Detected" in page.eval_on_selector("#ui_time_zone", "s => s.options[0].text")

    _choose_zone(page, "Asia/Riyadh")
    assert page.evaluate("() => window.ScrapeXTime.get().zone") == "Asia/Riyadh"
    assert page.evaluate("() => window.ScrapeXTime.resolution().step") == "selected"
    assert not page.js_errors


def test_choosing_a_zone_shares_it_with_the_engine_for_the_web_page(open_panel):
    """Spec 33 6.9, the half that can be tested here: the choice is PUSHED to
    the one shared preference, which is what the web page reads. One preference,
    so the two surfaces cannot be showing different times."""
    page = open_panel()
    _open_time_zone(page)
    page.evaluate("() => { window.__writes.length = 0; }")
    _choose_zone(page, "Asia/Riyadh")

    writes = [w for w in page.evaluate("() => window.__writes.slice()")
              if w["path"].startswith("/api/timezone")]
    assert writes, "the chosen zone never reached the engine"
    assert writes[-1]["method"] == "POST"
    assert writes[-1]["body"]["zone"] == "Asia/Riyadh"
    assert writes[-1]["body"]["updatedAt"] > 0, (
        "without a timestamp the two surfaces cannot tell which choice is newer")
    assert not page.js_errors


def test_a_zone_saved_on_the_other_surface_arrives_here(open_panel):
    """The other direction of 6.9: the engine already holds a zone, so the
    panel adopts it on connect rather than starting from its own detection."""
    page = open_panel(sources=[KEPT_LATE, CLEAN_SITE],
                      timezone={"zone": "Asia/Riyadh", "updatedAt": 9_999_999_999_999})
    assert page.evaluate("() => window.ScrapeXTime.get().zone") == "Asia/Riyadh"
    _run_tab(page)
    assert "31 Jul" in page.inner_text(".source-row-kept"), (
        "the panel rendered a time without the zone the engine already held")
    assert not page.js_errors


def test_changing_the_zone_re_renders_visible_times_without_refetching(open_panel):
    """Spec 33 6.10, and the assertion that gives it teeth: NOTHING is refetched.

    Re-rendering by reloading the data would satisfy the sentence and miss the
    point — a zone change is a presentation change, and on a panel polling a
    live crawl it must not cost a single request for data.
    """
    page = open_panel(sources=[KEPT_LATE, CLEAN_SITE])
    # A known starting zone, because "detected" is whatever machine runs this.
    # UTC also makes the before/after the clearest possible evidence: 22:30 on
    # the 30th becomes 01:30 on the 31st.
    page.evaluate("() => window.ScrapeXTime.set('UTC')")
    page.wait_for_timeout(150)
    _run_tab(page)

    kept = page.locator(".source-row-kept time[data-utc]")
    assert kept.count() == 1, page.inner_text(".source-row-kept")
    before = kept.inner_text()
    assert "30 Jul" in before and "10:30 PM" in before, (
        f"expected the stored 22:30Z to read as itself in UTC, got {before!r}")

    _open_time_zone(page)
    page.evaluate("() => { window.__calls.length = 0; }")
    _choose_zone(page, "Asia/Riyadh")

    _run_tab(page)
    after = page.locator(".source-row-kept time[data-utc]").inner_text()
    assert after != before, "the visible time did not follow the new zone"
    assert "31 Jul" in after, (
        f"22:30 UTC is 01:30 the next day in Riyadh, so the DAY must move: {after!r}")

    # No DATA route may be touched. The two preference-sync endpoints are
    # excluded because neither carries data: /api/timezone is the change itself,
    # and /api/appearance is the colour module's own poll, which runs on its own
    # clock whether or not anyone touches the zone.
    calls = page.evaluate("() => window.__calls.slice()")
    preferences = ("/api/timezone", "/api/appearance")
    refetched = [c for c in calls if not c.startswith(preferences)]
    assert not refetched, (
        f"changing the zone refetched data: {refetched}. 6.10 asks for a "
        "re-render from what is already in hand.")
    assert not page.js_errors


def test_the_raw_utc_stays_reachable_on_every_converted_time(open_panel):
    """Spec 33 6.12: the interface may convert, but the stored value must remain
    available for diagnosis. The truncated category does this with `title`
    already (grid.js), so a converted time does it the same way."""
    page = open_panel(sources=[KEPT_LATE, CLEAN_SITE],
                      timezone={"zone": "Asia/Riyadh", "updatedAt": 9_999_999_999_999})
    _run_tab(page)
    stamp = page.locator(".source-row-kept time[data-utc]")

    assert stamp.get_attribute("data-utc") == "2026-07-30T22:30:00Z", (
        "the raw instant left the element, so the conversion is no longer "
        "reversible or checkable")
    assert stamp.get_attribute("title") == "Stored as 2026-07-30T22:30:00Z (UTC)"
    # <time datetime> stays machine-readable UTC, never the converted text.
    assert stamp.get_attribute("datetime") == "2026-07-30T22:30:00Z"
    assert not page.js_errors


def test_the_zone_is_named_beside_a_time_whose_reading_depends_on_it(open_panel):
    """Spec 33 6.8, in the issue's own shape: "30 July 2026, 11:05 AM — Zone".

    A schedule's next fire is the case that earned it: the row used to say
    "UTC" in fixed text, so a 09:00 daily run read as 09:00 and fired at noon.
    """
    page = open_panel(sources=[CLEAN_SITE], schedules=SCHEDULE_SOON,
                      timezone={"zone": "Asia/Riyadh", "updatedAt": 9_999_999_999_999})
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-sched"]')
    page.wait_for_timeout(500)
    next_run = page.locator('.sched-row [data-role="next"]')
    assert next_run.count() >= 1, page.inner_text("#schedules")
    shown = next_run.first.inner_text()

    assert "— Asia/Riyadh" in shown, (
        f"the zone is not named beside the time: {shown!r}")
    assert "31 July 2026" in shown and "1:30 AM" in shown, (
        f"expected the issue's shape for 22:30Z in Riyadh, got {shown!r}")
    assert "UTC" not in shown, (
        "the row still claims UTC while showing a converted time — the exact "
        "misreading 6.8 exists to prevent")
    assert not page.js_errors


def test_an_invalid_zone_falls_back_down_the_chain_and_says_which_step(open_panel):
    """Spec 33 6.11, all three of its promises at once.

    A zone the browser cannot resolve — a typo, or one this tz database dropped
    — must fall back in order, must NOT rewrite the stored preference, and must
    say where it landed instead of failing silently.
    """
    page = open_panel(sources=[KEPT_LATE, CLEAN_SITE],
                      timezone={"zone": "Mars/Phobos", "updatedAt": 9_999_999_999_999})

    state = page.evaluate("() => window.ScrapeXTime.resolution()")
    assert state["step"] == "detected", (
        f"an unresolvable zone did not fall through to the detected one: {state}")
    assert state["zone"] == page.evaluate("() => window.ScrapeXTime.detected()")

    # It must not have quietly corrected the preference. Fixing the tz data has
    # to restore his choice, not find it overwritten.
    assert page.evaluate("() => window.ScrapeXTime.get().zone") == "Mars/Phobos", (
        "the fallback rewrote the stored preference, which 6.11 forbids")

    # And it says so, naming both the rejected zone and where it landed.
    _open_time_zone(page)
    note = page.inner_text("[data-time-zone-note]")
    assert "Mars/Phobos" in note and state["zone"] in note, (
        f"the fallback did not say which step it landed on: {note!r}")

    # Times still render, in the fallback zone, with the stored value intact.
    _run_tab(page)
    stamp = page.locator(".source-row-kept time[data-utc]")
    assert stamp.count() == 1, "an invalid zone stopped a time from rendering"
    assert stamp.get_attribute("data-utc") == "2026-07-30T22:30:00Z"
    assert stamp.inner_text().strip(), "the time rendered empty"
    assert not page.js_errors


def test_a_business_date_is_never_shifted_by_the_display_zone(open_panel):
    """The line this feature must not cross.

    A calendar date — a price_observation.business_date — is not a moment in
    time. Pushing it through a zone would either do nothing or move it a day,
    and a price filed under the wrong day is a false fact about the market. The
    formatter refuses anything that is not an instant, and returns it verbatim.
    """
    page = open_panel(timezone={"zone": "Pacific/Kiritimati",
                                "updatedAt": 9_999_999_999_999})
    verdicts = page.evaluate("""() => ({
        date_only: window.ScrapeXTime.format("2026-07-30"),
        is_instant: window.ScrapeXTime.isInstant("2026-07-30"),
        empty: window.ScrapeXTime.format(""),
        instant: window.ScrapeXTime.isInstant("2026-07-30T22:30:00Z"),
    })""")
    assert verdicts["date_only"] == "2026-07-30", (
        f"a calendar date was converted: {verdicts['date_only']!r}")
    assert verdicts["is_instant"] is False
    assert verdicts["empty"] == ""
    assert verdicts["instant"] is True
    assert not page.js_errors
