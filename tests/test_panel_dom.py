"""The side panel, driven in a real browser and asserted on.

Fifteen panel capabilities were graded `partial` for one reason: no test of any
kind existed for any of them. Screenshots proved a layout, never a behaviour, and
they actively HID one blocker — every scenario clicked a nav button before
capturing, so the broken opening screen was never photographed.

These tests drive the panel's own HTML, CSS and JS through the same harness the
screenshots use, and assert what a person would see and do.

WHY MOST `.is_visible()` ASSERTIONS HERE CARRY NO WAIT, DELIBERATELY.

Nine of them read `.is_visible()` on the line after a click, a key press or a
fill. That is measured, not assumed — and the rule is narrower than it looks.

The load-bearing property is NOT "the handler did it". It is that the change
lands inside the action's own INPUT TASK, and the driver does not acknowledge the
action until that whole task is done. Three of the nine are applied by no
listener at all: both `<details>` sites and the Enter-on-an-option site flip in
the ACTIVATION BEHAVIOUR, which Blink runs after the event has finished
propagating. Measured — at the last window bubble listener the closing disclosure
still reads visible, and Enter changes nothing in any keydown listener; Blink
synthesises a click as the keydown's default action, and that second event's
listener is what closes the list. Both are still correct on the very next line,
because the action does not return until the task ends. Do not restate this as
"synchronous inside the handler": that is false for a third of the sites it
covers, and someone applying it to a new site would get the wrong answer.

The remaining six are CSS with nothing to defer: `.hidden {display: none
!important}` and `[data-save-state="saved"] {display: none}`, neither of them a
transitionable property.

A wait at any of the nine would wait for something already done, and the day the
panel stops showing or hiding the element it would convert a one-line assertion
failure into a timeout. Add one only where a state change is genuinely deferred,
and name the deferral when you do.

WHAT PROTECTS THE *SHOW* ASSERTIONS IS THINNER THAN IT LOOKS. Playwright's
predicate is `checkVisibility()` AND `visibility != hidden` AND a non-empty rect;
opacity is not in it. So `#view-appearance` is read while its entry animation is
still running and computes to `opacity: 0`, and passes anyway. The listboxes are
read at `select-menu-in` currentTime 0, where the box is non-empty only because
the 0% keyframe is `scale(.98)`: change it to an ordinary `scaleY(0)` and the
identical assertion reads not-visible on a 226x0 box — measured. If you touch
`@keyframes select-menu-in` (extension/app.css) or the keyframes in `showView`,
re-measure these. What protects them is the animated property, not the structure
of the code.

Measure before adding one, by performing the action inside the page and reading
the visibility in the same JavaScript task. Read it with `checkVisibility()`:
`getBoundingClientRect()` on a descendant of a CLOSED `<details>` still reports
the last laid-out size, because Chromium skips that subtree rather than resizing
it, so a rect-based check calls a shut disclosure visible and invents a race that
is not there.

Do NOT reach for a slow machine or CPU throttling to settle it. Throttling hides
a deferred change instead of exposing it: it stretches the round trip between the
action and the read far more than the work in between, so the deferred thing has
landed by the time you look. Measured — a build broken on purpose to defer one of
these failed 15/15 unthrottled and passed 15/15 at 20x. A green run under load is
not evidence of synchrony; the same-task read is.
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

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

SOURCE_TAB = 'nav.side-rail button[data-view="source"]'
RUN_TAB = 'nav.side-rail button[data-view="run"]'
DATA_TAB = 'nav.side-rail button[data-view="data"]'
SOURCES_TAB = 'nav.side-rail button[data-view="sources"]'
FINANCE_TAB = 'nav.side-rail button[data-view="finance"]'
SETTINGS_TAB = 'nav.side-rail button[data-view="settings"]'

# The engine's half of the handshake, read from the engine rather than typed.
from scrapex.native import PROTOCOL_VERSION as PROTOCOL  # noqa: E402


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

    def opener(*, view=None, **stub_kwargs):
        """`view` navigates after load. The panel opens on Welcome, and a test
        about Source has to get to Source the way an owner would — by pressing
        its rail button — rather than by asserting on a page it never entered."""
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"panel{len(pages)}.html")
        page = browser.new_page(viewport={"width": 360, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        if view is not None:
            page.click(f'nav.side-rail button[data-view="{view}"]')
            page.wait_for_timeout(400)
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

def test_source_reads_the_active_tab_the_moment_it_is_opened(open_panel):
    """The blocker screenshots could not see: a view entered without going
    through showView never ran its loader, so it sat at "Reading the active
    tab…" until you navigated away and back.

    The panel used to open on Source, which is why this was named for the
    opening screen. It now opens on Welcome — a page with nothing to load — so
    the regression can only be guarded where it can still happen, which is the
    first time Source is entered."""
    page = open_panel(view="source")
    assert page.is_visible("#view-source")
    assert text_of(page, "#cur-title") == harness.ACTIVE_TAB["title"]
    assert harness.ACTIVE_TAB["url"] in text_of(page, "#cur-url")
    assert not page.is_disabled("#cur-use")


def test_opening_the_panel_raises_no_script_errors(open_panel):
    page = open_panel()
    assert page.js_errors == [], f"the panel threw on load: {page.js_errors}"


def test_each_destination_owns_its_scroll_and_keeps_its_heading_fixed(open_panel):
    page = open_panel()
    assert page.locator("main").evaluate(
        "element => getComputedStyle(element).overflowY") == "hidden"

    destinations = (
        (SOURCE_TAB, "#view-source"),
        (RUN_TAB, "#view-run"),
        (DATA_TAB, "#view-data"),
        (SOURCES_TAB, "#view-sources"),
        (FINANCE_TAB, "#view-finance"),
        ("#tab-appearance", "#view-appearance"),
        (SETTINGS_TAB, "#view-settings"),
    )
    internally_scrolling = {
        "#view-run", "#view-data", "#view-sources", "#view-finance", "#view-settings"}
    for tab, view_selector in destinations:
        page.click(tab)
        view = page.locator(view_selector)
        heading = view.locator(":scope > .view-heading")
        assert heading.count() == 1
        assert heading.evaluate(
            "element => getComputedStyle(element).position") == "sticky"
        overflow = view.evaluate(
            "element => getComputedStyle(element).overflowY")
        assert overflow == ("hidden" if view_selector in internally_scrolling else "auto")
        if view_selector in {"#view-run", "#view-finance", "#view-settings"}:
            body = view.locator(":scope > .view-scroll")
            assert body.count() == 1
            assert body.evaluate(
                "element => getComputedStyle(element).overflowY") == "auto"
            heading_box = heading.bounding_box()
            body_box = body.bounding_box()
            assert heading_box and body_box
            assert body_box["y"] >= heading_box["y"] + heading_box["height"]

    page.click(SETTINGS_TAB)
    settings = page.locator("#view-settings > .view-scroll")
    heading = page.locator("#view-settings > .view-heading")
    page.wait_for_timeout(150)
    before = heading.bounding_box()
    page.evaluate("() => { document.querySelector('#view-settings > .view-scroll').scrollTop = 240; }")
    page.wait_for_timeout(100)
    after = heading.bounding_box()
    assert settings.evaluate("element => element.scrollTop") > 0
    assert before and after and after["y"] == pytest.approx(before["y"], abs=.1)


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

    # Rolled 7 -> 10 and 8 -> 11 on 2026-08-05, when the agreed shape gained
    # Profile, Engine and Console (docs/PLATFORM-PLAN.md). The RULE this
    # asserts is unchanged and is not the number: the rail holds the pages the
    # panel itself owns, and everything deeper stays behind one grouped menu.
    # The count is here so a page cannot be added to the rail without someone
    # deciding it belongs there.
    assert page.locator("nav.side-rail button[data-view]").count() == 10
    assert page.locator("nav.side-rail button.rail-item").count() == 11
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
    page = open_panel(view="source", tab={"url": "chrome://extensions", "title": "Extensions"})
    assert page.is_disabled("#cur-use"), "a chrome:// page cannot be crawled"
    assert "not a website" in text_of(page, "#cur-title")
    assert "Open a site in this tab" in text_of(page, "#cur-out")


def test_an_engine_failure_is_not_reported_as_a_browser_failure(open_panel):
    """Blaming the tab for an engine error sends the owner to the wrong place."""
    page = open_panel(view="source", fail_routes=["/api/resolve"])
    page.wait_for_timeout(400)
    assert text_of(page, "#cur-title") == harness.ACTIVE_TAB["title"], \
        "the tab WAS readable; only the engine failed"
    assert "engine" in text_of(page, "#cur-out").lower()


def test_an_already_registered_page_says_so_and_offers_no_duplicate_add(open_panel):
    page = open_panel(view="source", resolve={"matched": True, "source_name": "Example Store",
                               "source_key": "SHOP_EXAMPLE", "implemented": True})
    page.wait_for_timeout(300)
    assert "Already registered" in text_of(page, "#cur-out")
    assert "Add" not in page.text_content("#cur-use"), \
        "offering Add for a site that exists promises something that must fail"


# ---- Current Page, after the owner navigates --------------------------------

def test_current_page_re_reads_the_tab_rather_than_trusting_a_stale_read(open_panel):
    """The panel stays open while the owner browses. Acting on the address read
    minutes ago would register whichever site they have since left."""
    page = open_panel(view="source")
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
    page = open_panel(view="source")
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
    page = open_panel(view="source")
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://shop.example.com\nhttps://second.example.com")
    page.click("#urls-check")
    page.wait_for_selector("#urls-results [data-pick]")
    page.click("#urls-results [data-pick]")     # click the first one immediately
    page.wait_for_timeout(600)
    assert page.is_visible("#source-detail"), \
        "clicking Review did nothing — it was rendered before it was bound"


def test_an_unreachable_address_is_not_dressed_up_as_a_detected_platform(open_panel):
    page = open_panel(view="source", fail_routes=["/api/probe"])
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "https://nothing-here.example")
    page.click("#urls-check")
    page.wait_for_timeout(700)
    body = page.text_content("#urls-results")
    assert "shopify" not in body.lower(), "a failed probe must not report a family"
    assert "Pick one to review" not in text_of(page, "#urls-out"), \
        "there is nothing to pick when every address failed"


def test_a_malformed_address_is_refused_before_any_request(open_panel):
    page = open_panel(view="source")
    page.click('label[for="source-urls"]')
    page.fill("#urls-box", "not-a-url")
    page.click("#urls-check")
    page.wait_for_timeout(300)
    assert "Not a full address" in text_of(page, "#urls-out")
    calls = page.evaluate("() => window.__calls.filter(c => c.startsWith('/api/probe'))")
    assert calls == [], "a malformed address must not reach the network"


# ---- Add Site ----------------------------------------------------------------

def test_using_the_current_page_opens_the_add_site_choice_with_it_filled_in(open_panel):
    page = open_panel(view="source")
    page.click("#cur-use")
    page.wait_for_timeout(800)
    assert page.is_checked("#source-addsite"), \
        "the form lives in the Add Site panel, which must be the one that opens"
    assert harness.ACTIVE_TAB["url"] in page.input_value("#url")
    assert page.is_visible("#source-detail")


def test_a_probe_fills_the_form_from_what_was_detected(open_panel):
    page = open_panel(view="source")
    page.click("#cur-use")
    page.wait_for_timeout(900)
    assert page.input_value("#f-key") == "SHOP_EXAMPLE"
    assert page.input_value("#f-currency") == "SAR"
    assert "Shopify" in page.text_content("#probe-out") or \
        "shopify" in page.text_content("#probe-out")


def test_the_unbuilt_file_source_cannot_be_actioned(open_panel):
    page = open_panel(view="source")
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

def test_finance_tab_sits_immediately_above_workspace(open_panel):
    page = open_panel()
    assert page.locator("#tab-sources use").get_attribute("href") == "#add"
    data_y, finance_y, workspace_y, sources_y = page.evaluate("""() => [
        document.querySelector('[data-view="data"]').offsetTop,
        document.querySelector('[data-view="finance"]').offsetTop,
        document.querySelector('#workspace-toggle').offsetTop,
        document.querySelector('[data-view="sources"]').offsetTop,
    ]""")
    assert data_y < finance_y < workspace_y < sources_y
    # Finance used to be a group of its own, separated by a hairline, because
    # the only thing being said was "this is not one of the crawl pages". What
    # it IS was left unsaid: Google Finance is served by the engine exactly as
    # Source, Run and Data are, and is just as dead without one. It now closes
    # the engine's group instead of standing beside it, and it still sits
    # immediately above Workspace, which is what this test was protecting.
    assert page.evaluate("""() => {
        const engine = document.querySelector('#engine-tablist');
        return engine.lastElementChild.id === 'tab-finance' &&
          engine.nextElementSibling.id === 'workspace-toggle';
    }""")

    page.click(SOURCES_TAB)
    page.wait_for_timeout(300)
    assert page.is_visible("#view-sources")
    assert page.locator("#source-manager-list .source-manager-card").count() == 3
    assert "3 of 3" in text_of(page, "#source-manager-count")


def test_google_finance_is_a_standalone_responsive_page(open_panel):
    page = open_panel()
    assert page.locator('#view-settings [data-sect="s-finance"]').count() == 0

    page.click(FINANCE_TAB)
    page.wait_for_timeout(250)

    assert page.is_visible("#view-finance")
    assert not page.is_visible("#view-settings")
    assert page.get_attribute(FINANCE_TAB, "aria-current") == "page"
    assert page.locator("#view-finance .finance-summary").count() == 0
    finance_source_link = page.locator("#view-finance .finance-source-link")
    assert finance_source_link.count() == 1
    assert finance_source_link.get_attribute("href") == "https://www.google.com/finance/"
    assert finance_source_link.get_attribute("target") == "_blank"
    assert finance_source_link.locator("use").get_attribute("href") == \
        "#open-in-new"
    assert page.locator("#view-finance .finance-card").count() == 3
    assert page.locator("details.finance-preferences-card[open]").count() == 0
    assert page.locator("#view-finance .finance-card").evaluate_all("""elements =>
      elements.map(element => element.querySelector('h2')?.id)
    """) == [
        "finance-status-heading", "finance-refresh-heading", "finance-converter-heading"]
    page.click(".finance-preferences-card > summary")
    assert page.locator("details.finance-preferences-card[open]").count() == 1
    assert page.locator("#view-finance .finance-rate-fact").count() == 3
    card_elevation = page.locator("#view-finance .finance-card").evaluate_all("""elements =>
      elements.map(element => {
        const style = getComputedStyle(element);
        return [style.backgroundColor, style.borderTopWidth, style.borderRadius, style.boxShadow];
      })
    """)
    assert len({tuple(style) for style in card_elevation}) == 1
    assert card_elevation[0][3] == "none"
    assert page.locator(".finance-settings-surface > .finance-setting-row").count() == 2
    assert page.locator(".finance-settings-surface > .finance-setting-row").evaluate_all("""elements =>
      elements.map(element => getComputedStyle(element).borderTopWidth)
    """) == ["0px", "0px"]
    preferences_surface = page.locator(".finance-settings-surface").evaluate("""element => ({
      background: getComputedStyle(element).backgroundColor,
      sideBorder: getComputedStyle(element).borderLeftWidth,
      radius: getComputedStyle(element).borderRadius,
    })""")
    assert preferences_surface == {
        "background": "rgba(0, 0, 0, 0)", "sideBorder": "0px", "radius": "0px"}
    assert page.locator(".finance-settings-surface #google_finance_refresh_hours").count() == 1
    assert page.locator(".finance-preferences-card #finance-save").count() == 1
    assert page.locator(".finance-converter-card #finance-dataset").count() == 1
    assert page.locator(".finance-converter-card > .finance-section-heading #finance-dataset").count() == 1
    assert text_of(page, "#finance-save") == "Saved"
    assert page.is_disabled("#finance-save")
    assert not page.locator("#finance-save").is_visible()
    assert text_of(page, "#finance-saved-summary") == \
        "Rates refresh automatically every 6 hours."
    saved_summary_style = page.locator("#finance-saved-summary").evaluate("""element => {
      const style = getComputedStyle(element);
      return [style.fontFamily, style.fontSize, style.fontWeight, style.color];
    }""")
    currency_summary_style = page.locator("#finance-currency-details summary").evaluate(
        """element => {
          const style = getComputedStyle(element);
          return [style.fontFamily, style.fontSize, style.fontWeight, style.color];
        }""")
    assert saved_summary_style == currency_summary_style
    saved_text_styles = page.locator("#finance-saved-state > *").evaluate_all("""elements =>
      elements.map(element => {
        const style = getComputedStyle(element);
        return [style.fontFamily, style.fontSize, style.fontWeight, style.color, style.opacity];
      })
    """)
    assert len({tuple(style) for style in saved_text_styles}) == 1
    assert "Consolas" not in saved_text_styles[0][0]
    assert saved_text_styles[0][2] == "500"
    assert page.is_checked("#google_finance_auto_refresh")
    assert page.input_value("#google_finance_refresh_hours") == "6"
    switch = page.get_by_role("switch", name="Keep rates up to date")
    switch_box = switch.bounding_box()
    track_box = page.locator(".finance-m3-switch-track").bounding_box()
    assert switch_box and switch_box["width"] == pytest.approx(46, abs=.1)
    assert switch_box["height"] == pytest.approx(40, abs=.1)
    assert track_box and track_box["width"] == pytest.approx(46, abs=.1)
    assert track_box["height"] == pytest.approx(28, abs=.1)
    switch_styles = switch.evaluate("""element => ({
      opacity: getComputedStyle(element).opacity,
      borderWidth: getComputedStyle(element).borderTopWidth,
      background: getComputedStyle(element).backgroundColor,
    })""")
    assert switch_styles == {
        "opacity": "0", "borderWidth": "0px", "background": "rgba(0, 0, 0, 0)"}
    handle = page.locator(".finance-m3-switch-handle")
    handle_box = handle.bounding_box()
    assert handle_box and handle_box["width"] == pytest.approx(20, abs=.1)
    assert handle_box["height"] == pytest.approx(20, abs=.1)
    assert track_box["x"] + track_box["width"] - handle_box["x"] - handle_box["width"] \
        == pytest.approx(4, abs=.1)
    assert handle_box["y"] - track_box["y"] == pytest.approx(4, abs=.1)
    assert page.locator("#finance-saved-state").evaluate(
        "element => element.scrollHeight <= element.clientHeight")
    saved_layout = page.locator("#finance-saved-state").evaluate("""element => ({
      display: getComputedStyle(element).display,
      direction: getComputedStyle(element).flexDirection,
    })""")
    assert saved_layout == {"display": "flex", "direction": "row"}
    saved_background = page.locator("#finance-saved-state").evaluate(
        "element => getComputedStyle(element).backgroundColor")
    switch.click()
    page.wait_for_timeout(350)
    assert not switch.is_checked()
    track_box = page.locator(".finance-m3-switch-track").bounding_box()
    handle_box = handle.bounding_box()
    assert track_box
    assert handle_box and handle_box["width"] == pytest.approx(14, abs=.1)
    assert handle_box["height"] == pytest.approx(14, abs=.1)
    assert handle_box["x"] - track_box["x"] == pytest.approx(7, abs=.1)
    assert handle_box["y"] - track_box["y"] == pytest.approx(7, abs=.1)
    assert text_of(page, "#finance-save") == "Apply changes"
    assert page.locator("#finance-save .finance-save-icon-dirty").is_visible()
    assert not page.locator("#finance-save .finance-save-icon-saved").is_visible()
    assert page.locator("#finance-saved-state").evaluate(
        "element => getComputedStyle(element).backgroundColor") == saved_background
    switch.click()
    page.wait_for_timeout(350)
    assert switch.is_checked()
    track_box = page.locator(".finance-m3-switch-track").bounding_box()
    handle_box = handle.bounding_box()
    assert track_box and handle_box
    assert track_box["x"] + track_box["width"] - handle_box["x"] - handle_box["width"] \
        == pytest.approx(4, abs=.1)
    assert handle_box["y"] - track_box["y"] == pytest.approx(4, abs=.1)
    assert text_of(page, "#finance-save") == "Saved"
    assert not page.locator("#finance-save").is_visible()
    page.fill("#google_finance_refresh_hours", "12")
    assert text_of(page, "#finance-save") == "Apply changes"
    assert not page.is_disabled("#finance-save")
    assert page.locator("#finance-save").is_visible()
    dirty_save_box = page.locator("#finance-save").bounding_box()
    dirty_actions_box = page.locator("#finance-save").locator("..").bounding_box()
    dirty_saved_state_box = page.locator("#finance-saved-state").bounding_box()
    assert dirty_save_box and dirty_actions_box and dirty_saved_state_box
    action_padding = page.locator("#finance-save").locator("..").evaluate("""element => {
      const style = getComputedStyle(element);
      return parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    }""")
    assert dirty_save_box["width"] + action_padding == \
        pytest.approx(dirty_actions_box["width"], abs=.1)
    assert dirty_saved_state_box["y"] + dirty_saved_state_box["height"] <= dirty_save_box["y"]
    assert page.get_attribute("#finance-saved-state", "data-dirty") == "true"
    assert text_of(page, "#finance-saved-summary") == \
        "Rates refresh automatically every 6 hours."
    page.fill("#google_finance_refresh_hours", "6")
    assert text_of(page, "#finance-save") == "Saved"
    assert page.is_disabled("#finance-save")
    assert not page.locator("#finance-save").is_visible()
    assert text_of(page, "#finance-status-heading") == "Rate coverage"
    assert text_of(page, "#finance-rate-state-title") == "Rates are up to date"
    assert text_of(page, "#finance-currency-count") == "5 currencies"
    assert not page.locator("#finance-currencies").is_visible()
    page.click("#finance-currency-details summary")
    assert page.locator("#finance-currencies").is_visible()
    assert "SAR·AED·EUR" in text_of(page, "#finance-currencies").replace(" ", "")
    currency_list_style = page.locator("#finance-currencies").evaluate("""element => ({
      height: Math.round(element.getBoundingClientRect().height),
      overflow: getComputedStyle(element).overflowY,
      background: getComputedStyle(element).backgroundColor,
    })""")
    assert currency_list_style["height"] == 120
    assert currency_list_style["overflow"] == "auto"
    assert currency_list_style["background"] != "rgba(0, 0, 0, 0)"
    assert page.locator("#finance-converter-currency option").count() == 5
    page.select_option("#finance-converter-currency", "EUR")
    assert text_of(page, "#finance-converter-equation") == "1 Euro equals"
    assert text_of(page, "#finance-converter-usd") == \
        "1.087 United States Dollar"
    assert text_of(page, "#finance-converter-output") == "1.087"
    assert text_of(page, "#finance-converter-currency-trigger") == "Euro"
    page.click("#finance-converter-currency-trigger")
    assert page.locator("#finance-converter-currency-list").is_visible()
    assert page.locator("#finance-converter-currency-list .finance-converter-option").count() == 5
    source_trigger_box = page.locator("#finance-converter-currency-trigger").bounding_box()
    source_list_box = page.locator("#finance-converter-currency-list").bounding_box()
    assert source_trigger_box and source_list_box
    assert source_list_box["x"] == pytest.approx(source_trigger_box["x"], abs=.1)
    assert source_list_box["width"] == pytest.approx(source_trigger_box["width"], abs=.1)
    assert page.locator("#finance-converter-currency-trigger").evaluate(
        "element => getComputedStyle(element).textAlign") in {"end", "right"}
    source_trigger_label_style = page.locator(
        "#finance-converter-currency-trigger [data-finance-select-label]").evaluate(
        """element => {
          const label = element.getBoundingClientRect();
          const trigger = element.parentElement.getBoundingClientRect();
          return {
            centerDelta: Math.abs((label.top + label.height / 2) -
                                  (trigger.top + trigger.height / 2)),
            fontWeight: Number(getComputedStyle(element).fontWeight),
          };
        }""")
    assert source_trigger_label_style["centerDelta"] <= 1
    assert source_trigger_label_style["fontWeight"] <= 400
    selected_currency = page.locator(
        "#finance-converter-currency-list .finance-converter-option[aria-selected='true']")
    assert selected_currency.count() == 1
    assert selected_currency.evaluate(
        "element => getComputedStyle(element).textAlign") in {"start", "left"}
    selected_colors = selected_currency.evaluate("""element => {
      const probe = document.createElement('span');
      probe.style.background = 'var(--primary-container)';
      document.body.append(probe);
      const colors = [getComputedStyle(element).backgroundColor,
                      getComputedStyle(probe).backgroundColor];
      probe.remove();
      return colors;
    }""")
    assert selected_colors[0] == selected_colors[1]
    source_option_font = selected_currency.evaluate("""element => {
      const style = getComputedStyle(element);
      return [style.fontFamily, style.fontSize, style.fontWeight];
    }""")
    page.evaluate("""() => {
      const select = document.querySelector('#finance-converter-currency');
      select.add(new Option('Australian Dollar', 'AUD'));
      select.add(new Option('Argentine Peso', 'ARS'));
      select.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    page.click("#finance-converter-currency-trigger")
    page.click("#finance-converter-currency-trigger")
    page.wait_for_timeout(50)
    page.keyboard.press("a")
    first_a_currency = page.evaluate("() => document.activeElement.textContent.trim()")
    page.keyboard.press("a")
    second_a_currency = page.evaluate("() => document.activeElement.textContent.trim()")
    assert first_a_currency != second_a_currency
    assert first_a_currency.lower().startswith("a")
    assert second_a_currency.lower().startswith("a")
    page.wait_for_timeout(750)
    page.keyboard.press("j")
    assert "Japanese Yen" in page.evaluate("() => document.activeElement.textContent")
    page.keyboard.press("Enter")
    assert page.input_value("#finance-converter-currency") == "JPY"
    assert not page.locator("#finance-converter-currency-list").is_visible()
    page.select_option("#finance-converter-currency", "EUR")

    page.click("#finance-converter-target-trigger")
    assert page.locator("#finance-converter-target-list").is_visible()
    target_option = page.locator("#finance-converter-target-list .finance-converter-option")
    assert target_option.count() == 1
    target_option_font = target_option.evaluate("""element => {
      const style = getComputedStyle(element);
      return [style.fontFamily, style.fontSize, style.fontWeight];
    }""")
    assert target_option_font == source_option_font
    assert target_option.evaluate(
        "element => getComputedStyle(element).textAlign") in {"start", "left"}
    target_trigger_box = page.locator("#finance-converter-target-trigger").bounding_box()
    target_list_box = page.locator("#finance-converter-target-list").bounding_box()
    assert target_trigger_box and target_list_box
    assert target_list_box["x"] == pytest.approx(target_trigger_box["x"], abs=.1)
    assert target_list_box["width"] == pytest.approx(target_trigger_box["width"], abs=.1)
    assert page.locator("#finance-converter-target-trigger").evaluate(
        "element => getComputedStyle(element).textAlign") in {"end", "right"}
    target_trigger_label_style = page.locator(
        "#finance-converter-target-trigger [data-finance-select-label]").evaluate(
        """element => {
          const label = element.getBoundingClientRect();
          const trigger = element.parentElement.getBoundingClientRect();
          return {
            centerDelta: Math.abs((label.top + label.height / 2) -
                                  (trigger.top + trigger.height / 2)),
            fontWeight: Number(getComputedStyle(element).fontWeight),
          };
        }""")
    assert target_trigger_label_style["centerDelta"] <= 1
    assert target_trigger_label_style["fontWeight"] <= 400
    target_option.click()
    converter_rows = page.locator(".finance-converter-row").evaluate_all("""elements =>
      elements.map(element => ({
        height: Math.round(element.getBoundingClientRect().height),
        separatorHeight: getComputedStyle(element, '::after').height,
      }))
    """)
    assert converter_rows == [
        {"height": 40, "separatorHeight": "24px"},
        {"height": 40, "separatorHeight": "24px"},
    ]
    assert "Google Finance" in text_of(page, "#finance-converter-as-of")
    page.evaluate("() => window.ScrapeXTime.set('UTC')")
    utc_market_time = text_of(page, "#finance-latest-market")
    utc_rate_time = text_of(page, "#finance-converter-as-of")
    page.evaluate("() => window.ScrapeXTime.set('Asia/Riyadh')")
    assert text_of(page, "#finance-latest-market") != utc_market_time
    assert text_of(page, "#finance-converter-as-of") != utc_rate_time
    page.fill("#finance-converter-amount", "2")
    assert text_of(page, "#finance-converter-equation") == "2 Euro equals"
    assert text_of(page, "#finance-converter-output") == "2.174"
    assert "/api/rates/google-finance" in page.evaluate("() => window.__calls")
    assert page.locator("#finance-currencies .finance-currency-chip").count() == 0
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    interval_copy_box = page.locator(".finance-interval-row .finance-setting-copy").bounding_box()
    interval_field_box = page.locator(".finance-interval-row .finance-number-field").bounding_box()
    assert interval_copy_box and interval_field_box
    assert interval_field_box["y"] >= interval_copy_box["y"] + interval_copy_box["height"]

    page.set_viewport_size({"width": 560, "height": 800})
    page.wait_for_timeout(100)
    setting_copy_lefts = page.locator(".finance-settings-surface .finance-setting-copy").evaluate_all(
        "elements => elements.map(element => Math.round(element.getBoundingClientRect().left))")
    assert len(set(setting_copy_lefts)) == 1
    stat_tops = page.locator(".finance-rate-facts .finance-rate-fact").evaluate_all(
        "elements => elements.map(element => Math.round(element.getBoundingClientRect().top))")
    assert len(set(stat_tops)) == 1
    action_sizes = page.locator("#finance-refresh, #finance-dataset").evaluate_all("""elements =>
        elements.map(element => ({
          width: Math.round(element.getBoundingClientRect().width),
          height: Math.round(element.getBoundingClientRect().height),
        }))
    """)
    assert len({size["width"] for size in action_sizes}) == 1
    assert len({size["height"] for size in action_sizes}) == 1
    saved_state_box = page.evaluate("""() =>
      document.querySelector('#finance-saved-state').getBoundingClientRect().toJSON()
    """)
    assert saved_state_box["height"] > 0
    saved_state_style = page.locator("#finance-saved-state").evaluate("""element => ({
      border: getComputedStyle(element).borderTopWidth,
      background: getComputedStyle(element).backgroundColor,
    })""")
    assert saved_state_style == {"border": "0px", "background": "rgba(0, 0, 0, 0)"}

    page.click("#finance-refresh")
    page.wait_for_timeout(100)
    assert page.locator("#finance-refresh svg").count() == 1
    assert "Update now" in text_of(page, "#finance-refresh")
    assert any(write["path"] == "/api/rates/google-finance/refresh"
               for write in page.evaluate("() => window.__writes"))
    page.click(".finance-preferences-card > summary")
    assert page.locator("details.finance-preferences-card:not([open])").count() == 1
    assert not page.locator(".finance-settings-surface").is_visible()


def test_finance_cards_keep_their_content_when_the_panel_is_short(open_panel):
    page = open_panel()
    page.set_viewport_size({"width": 360, "height": 320})
    page.click(FINANCE_TAB)
    page.click(".finance-preferences-card > summary")

    layout = page.evaluate("""() => {
      const view = document.querySelector('#view-finance > .view-scroll');
      const card = document.querySelector('.finance-preferences-card');
      const saved = document.querySelector('#finance-saved-state');
      const cardRect = card.getBoundingClientRect();
      const savedRect = saved.getBoundingClientRect();
      return {
        viewScrolls: view.scrollHeight > view.clientHeight,
        cardIsClipped: card.scrollHeight > card.clientHeight,
        savedInsideCard: savedRect.bottom <= cardRect.bottom + 0.1,
      };
    }""")
    assert layout == {
        "viewScrolls": True,
        "cardIsClipped": False,
        "savedInsideCard": True,
    }
    assert page.locator("#finance-saved-summary").is_visible()


def test_rate_status_color_follows_automatic_refresh_policy(open_panel):
    base_status = {
        "refresh_hours": 6,
        "tracked_currencies": ["EUR"],
        "latest_rates": [{
            "currency": "EUR", "per_usd": .92,
            "as_of": "2026-08-02T10:29:00Z",
        }],
        "last_checked": "2026-08-02T01:00:00Z",
        "latest_market_at": "2026-08-02T10:29:00Z",
        "rows": 10,
        "warnings": [],
    }

    overdue = open_panel(rates_status={
        **base_status, "automatic": True, "due": True,
    })
    overdue.click(FINANCE_TAB)
    overdue.wait_for_timeout(100)
    assert overdue.get_attribute("#finance-rate-state", "data-tone") == "error"
    assert text_of(overdue, "#finance-rate-state-title") == "Rate update overdue"
    overdue_colors = overdue.locator("#finance-rate-state").evaluate("""element => {
      const probe = document.createElement('span');
      probe.style.background = 'var(--red-weak)';
      document.body.append(probe);
      const colors = [getComputedStyle(element).backgroundColor,
                      getComputedStyle(probe).backgroundColor];
      probe.remove();
      return colors;
    }""")
    assert overdue_colors[0] == overdue_colors[1]

    manual = open_panel(rates_status={
        **base_status, "automatic": False, "due": True,
    })
    manual.click(FINANCE_TAB)
    manual.wait_for_timeout(100)
    assert manual.get_attribute("#finance-rate-state", "data-tone") == "neutral"
    assert text_of(manual, "#finance-rate-state-title") == "Rates update manually"
    manual_colors = manual.locator("#finance-rate-state").evaluate("""element => {
      const probe = document.createElement('span');
      probe.style.background = 'var(--surface-subtle)';
      document.body.append(probe);
      const colors = [getComputedStyle(element).backgroundColor,
                      getComputedStyle(probe).backgroundColor];
      probe.remove();
      return colors;
    }""")
    assert manual_colors[0] == manual_colors[1]


def test_finance_converter_keeps_small_nonzero_values_visible(open_panel):
    page = open_panel(rates_status={
        "automatic": True,
        "refresh_hours": 6,
        "tracked_currencies": ["EGP", "MGA"],
        "latest_rates": [
            {"currency": "EGP", "per_usd": 50.99649,
             "as_of": "2026-08-02T10:29:00Z"},
            {"currency": "MGA", "per_usd": 3125,
             "as_of": "2026-08-02T10:29:00Z"},
        ],
        "last_checked": "2026-08-02T10:28:32Z",
        "latest_market_at": "2026-08-02T10:29:00Z",
        "rows": 2,
        "due": False,
        "warnings": [],
    })
    page.click(FINANCE_TAB)
    page.wait_for_timeout(100)

    page.select_option("#finance-converter-currency", "EGP")
    assert text_of(page, "#finance-converter-output") == "0.020"
    page.select_option("#finance-converter-currency", "MGA")
    assert text_of(page, "#finance-converter-output") == "0.00032"


def test_settings_cards_use_the_canonical_icon_sprite_instead_of_numbers(open_panel):
    page = open_panel()
    page.click(SETTINGS_TAB)

    icons = page.locator("#view-settings .settings-icon use")
    assert icons.count() == 7
    assert icons.evaluate_all("elements => elements.map(element => element.getAttribute('href'))") == [
        "#dns", "#storage", "#schedule", "#file-download",
        "#restart-alt", "#language", "#info",
    ]
    assert page.locator("#view-settings .settings-index").count() == 0


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
    page = open_panel(view="source", resolve={"matched": True, "source_name": "Example Store",
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
    page.click('nav.side-rail button[data-view="settings"]')
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
    page = open_panel(view="source")
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
    # WAITED FOR, not asserted on the next line.
    page.wait_for_selector("#run-mode-list", state="hidden")
    assert not page.locator("#run-mode-list").is_visible()


def test_escape_closes_the_list_while_focus_is_still_on_the_trigger(open_panel):
    """The defect the wait uncovered, and the reason it is a panel defect and
    not a test one.

    open() moves focus INTO the list inside a requestAnimationFrame, and the
    only Escape listener was on the list. Between the click that opens it and
    the frame that lands, focus is still on the trigger — and Escape reached
    nothing. The list stayed open with no keyboard way out of it, which is also
    true for anyone who shift-tabs back to the trigger afterwards.

    It showed up as an intermittently red CI job. I first recorded it as a race
    in the test and "not a defect in the panel"; that was wrong. Waiting
    properly did not make it pass — it made it fail for thirty seconds with the
    list resolved visible sixty-three times, which is what a real user gets.

    This test presses Escape with focus DELIBERATELY on the trigger, so it does
    not depend on losing a race to catch the bug."""
    page = open_panel()
    page.click(RUN_TAB)
    page.wait_for_timeout(200)

    page.click("#run-mode-trigger")
    page.wait_for_selector("#run-mode-list", state="visible")
    # Put focus back where a fast user's still is, and where a shift-tab leaves it.
    page.locator("#run-mode-trigger").focus()
    page.keyboard.press("Escape")

    # wait_for_selector IS the assertion — it raises if the list never hides,
    # which is exactly the 30-second failure CI produced. Nothing is asserted
    # about focus here: this test puts focus on the trigger itself, so finding
    # it there afterwards would be true whether or not close() restored it.
    # Proved by mutation — dropping restoreFocus left that assertion green, so
    # it was decoration and it is gone. The focus behaviour is the list
    # handler's, and belongs in a test that presses Escape from inside the list.
    page.wait_for_selector("#run-mode-list", state="hidden")


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
    # The zone is PINNED, so this asserts the product's format rather than the
    # zone of whichever machine runs it. It used to expect "2026-07-29 08:30" —
    # the hand-formatted UTC this line printed before spec 33 — which is the
    # very shape the owner reported as inconsistent with the rest of the
    # product (and which the Workspace showed differently again).
    page = open_panel(sources=sources,
                      timezone={"zone": "Asia/Riyadh", "updatedAt": 9_999_999_999_999})
    page.click(DATA_TAB)
    page.wait_for_timeout(300)
    card = page.text_content("#datasets")
    assert "Last crawled 29 July 2026, 11:30 AM — Asia/Riyadh" in card, (
        f"08:30Z is 11:30 in Riyadh and the zone is named beside it: {card!r}")
    assert "763 rows seen" in card
    assert "no recorded changes yet" not in card

    # And the stored instant is still reachable on the element itself (§6.12).
    stamp = page.locator("#datasets time[data-utc]").first
    assert stamp.get_attribute("data-utc") == "2026-07-29T08:30:00Z"
    assert stamp.get_attribute("title") == "Stored as 2026-07-29T08:30:00Z (UTC)"
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
    assert "Native helper unavailable — restarting through the engine." in panel
    assert "title: \"Local helper did not answer\"" in panel


def test_startup_blockers_have_a_visible_repair_path():
    """A failed restart must name the real blocker and leave its repair action
    reachable while the HTTP engine is down."""
    transport = (ROOT / "extension" / "transport.js").read_text(encoding="utf-8")
    panel = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")

    assert '"CHECK_STARTUP"' in transport
    assert '"UPGRADE_DATABASE"' in transport
    assert 'kind === "startup_blocked"' in panel
    assert "checkStartup()" in panel
    assert "upgradeDatabase()" in panel
    assert 'id="runtime-details"' in html
    assert 'class="engine-runtime-status"' in html
    assert 'id="runtime-note"' in html
    assert 'id="runtime-upgrade"' in html


def test_engine_actions_are_consistent_and_the_next_card_is_separate(open_panel):
    page = open_panel()
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-engine"]')

    engine_card = page.locator("#s-engine").locator("..")
    storage_card = page.locator("#s-storage").locator("..")
    engine_box = engine_card.bounding_box()
    storage_box = storage_card.bounding_box()
    assert engine_box and storage_box
    assert storage_box["y"] - (engine_box["y"] + engine_box["height"]) >= 8

    actions = page.locator("#s-engine .engine-maintenance-actions .engine-action")
    assert actions.count() == 2
    widths = [actions.nth(index).bounding_box()["width"] for index in range(2)]
    assert max(widths) - min(widths) <= 1
    assert page.locator("#s-engine .engine-action .sx-icon").count() == 2

    smart = page.locator("#runtime-check-action")
    assert smart.get_attribute("data-action") == "diagnostics"
    assert smart.text_content().strip() == "Run diagnostics"
    assert smart.locator("use").get_attribute("href").endswith("#tune")
    smart.click()
    assert "Engine reachable" in page.text_content("#diag-out")
    assert not page.evaluate(
        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth")


def test_the_engine_check_action_becomes_recheck_while_the_engine_is_down(open_panel):
    page = open_panel(engine_up=False)
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-engine"]')

    smart = page.locator("#runtime-check-action")
    assert smart.get_attribute("data-action") == "recheck"
    assert smart.text_content().strip() == "Recheck status"
    assert smart.locator("use").get_attribute("href").endswith("#sync")


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


# ---- versions: which one is running, and what it can do ----------------------
# The panel showed the ENGINE's version under the word "Engine" and its own
# nowhere at all. So a feature the installed extension could not reach looked
# exactly like a feature that had never been built — which is what happened,
# twice in two days, and is what issue 32 section 1 is about.

def _about_panel(page):
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-about"]')
    page.wait_for_timeout(200)


def test_about_names_the_side_every_version_belongs_to(open_panel):
    """A version shown without saying whose version it is, is the bug.

    THE NUMBERS COME FROM THE SOURCE, not from literals. Pinned as "0.2.0" this
    passed until the day 0.2.1 was cut, then failed for a reason that had
    nothing to do with what it tests — and a test that has to be edited on every
    bump is a test that will one day be edited without being read.
    """
    from scrapex.version import MINIMUM_EXTENSION_VERSION, VERSION

    page = open_panel(extension_version=VERSION, engine_version=VERSION)
    _about_panel(page)

    assert text_of(page, "#about-extension-version") == VERSION
    assert text_of(page, "#about-version") == VERSION
    assert text_of(page, "#about-latest-version") == VERSION
    assert text_of(page, "#about-minimum-version") == MINIMUM_EXTENSION_VERSION
    about = page.inner_text("#s-about")
    assert "This extension" in about and "Engine" in about
    # "Latest" must say where latest came from: there is no update server.
    assert "no remote update server" in text_of(page, "#about-latest-source")
    assert not page.js_errors


def test_about_lists_what_the_engine_deploys_and_the_version_it_arrived_in(open_panel):
    """INCIDENT ONE, answered in the panel: has this shipped, and since when?

    The crawl pace was built in c63ec21 and rendered only on the display-only
    web page; the owner asked for it as if it were new. There was nowhere to
    look it up. There is now, and it is on the surface he actually works from.
    """
    page = open_panel()
    _about_panel(page)

    ledger = page.inner_text("#about-capabilities")
    assert "crawl delay" in ledger, "the crawl pace is not in the panel's ledger"
    assert "several different sites at the same time" in ledger
    assert "c63ec21" in ledger, "the commit that built the crawl pace is not cited"
    assert "0.2.0" in ledger


def test_an_extension_older_than_its_engine_is_told_all_five_facts(open_panel):
    """INCIDENT TWO, caught before the question. The engine deploys crawling
    several sites at once; a 0.1.0 extension has no field for it, and the owner
    finds out by watching two jobs queue and asking why.

    Section 1.4 lists what the notification must carry, and every one of the
    five is asserted here — a notification missing the number, the requirement
    or the remedy sends its reader somewhere else to find the rest.
    """
    page = open_panel(view="source", extension_version="0.1.0", engine_version="0.2.0")

    notice = page.locator("#version-notice")
    assert notice.is_visible(), "a stale extension was told nothing"
    text = notice.inner_text()
    assert "0.1.0" in text, "1: the installed version is missing"
    assert "Latest available extension" in text and "0.2.0" in text, "2: latest is missing"
    assert "Minimum extension required" in text, "3: the requirement is missing"
    assert "several different sites at the same time" in text, (
        "4: what is actually missing is not named")
    assert "chrome://extensions" in text, "5: how to update is missing"
    # It must be readable without hunting: the engine's own status lives in a
    # collapsed settings panel, and this cannot.
    source_view_state = page.locator("#view-source").evaluate("""element => ({
      className: element.className,
      display: getComputedStyle(element).display,
      height: element.getBoundingClientRect().height,
      mainHeight: element.parentElement.getBoundingClientRect().height,
      noticeHeight: document.querySelector('#version-notice').getBoundingClientRect().height,
    })""")
    assert page.is_visible("#view-source"), source_view_state
    assert not page.js_errors


def test_an_extension_in_step_with_its_engine_is_not_nagged(open_panel):
    """A warning that fires when nothing is wrong is a warning people click
    past — the same reasoning that keeps engine-only changes out of the gate."""
    # In step means AT THE CURRENT VERSION, whatever it is. As a literal this
    # said "in step" until 0.2.1 was cut, after which it meant "one behind" —
    # and the notice it asserts is absent was correctly being shown.
    from scrapex.version import VERSION

    page = open_panel(extension_version=VERSION, engine_version=VERSION)
    assert not page.locator("#version-notice").is_visible()
    assert not page.js_errors


def test_an_engine_older_than_the_extension_says_so_in_different_words(open_panel):
    """The other direction, and it needs a different sentence: reloading the
    extension fixes nothing here. An engine from before version reporting
    answers /api/version with a 404, which must read as "old engine" and never
    as a broken feature."""
    page = open_panel(extension_version="0.2.0", engine_version="0.1.0",
                      version_reporting=False)

    text = page.locator("#version-notice").inner_text()
    assert "engine is older" in text.lower()
    assert "0.1.0" in text and "0.2.0" in text, "both versions must be named"
    # The engine is local and started from the same checkout, so it reports the
    # version of the code RUNNING, not the code on disk. After a pull those
    # differ until the process restarts, and that is the ordinary case — a
    # remedy that only says "update" sends the owner hunting for a download
    # they already have.
    assert "restart engine" in text.lower(), (
        "the usual fix for a locally-run engine is not mentioned")
    # A reader cannot see which version is on disk, so an instruction that
    # branches on it is not an instruction. Restart first — it is free and it
    # fixes the common case — and let the number afterwards decide the rest.
    assert text.lower().index("restart engine") < text.lower().index("updat"), (
        "it asks the reader to decide something they cannot see before acting")
    assert "chrome://extensions" not in text, (
        "it told the owner to reload the extension for a stale engine")
    assert not page.js_errors


def test_two_sides_at_the_same_version_are_not_told_one_is_older(open_panel):
    """The owner's screenshot. Installed extension 0.1.0, Engine 0.1.0, and a
    heading that said the engine was OLDER than the extension — contradicted by
    the two numbers printed directly beneath it — followed by "Update the engine
    to 0.1.0", which is the version already installed.

    The branch fired on the engine's silence and never compared the two numbers.
    Silence has three causes and they do not share a remedy: an engine really
    behind, both sides below the line where reporting began, or a process that
    did not restart when its files did."""
    page = open_panel(extension_version="0.1.0", engine_version="0.1.0",
                      version_reporting=False)

    text = page.locator("#version-notice").inner_text()
    assert "older than this extension" not in text.lower(), (
        "it called the engine older than an extension of the same version")
    assert "update the engine to 0.1.0" not in text.lower(), (
        "the remedy is the version already installed")
    assert "0.2.0" in text, "the sentence must name a version that would help"
    assert not page.js_errors


def test_an_engine_at_a_reporting_version_that_stays_silent_is_told_to_restart(open_panel):
    """The third cause, and the only one where downloading anything is wasted
    effort: the files on disk moved to a version that publishes a report, and
    the running process did not. Nothing to install — restart it."""
    page = open_panel(extension_version="0.2.0", engine_version="0.2.0",
                      version_reporting=False)

    text = page.locator("#version-notice").inner_text().lower()
    assert "restart" in text, "a stale process was sent to download something"
    # "older than its own files" is the true and useful sentence here. The claim
    # this guards against is the other one: older than the EXTENSION, which at
    # equal versions is false.
    assert "older than this extension" not in text
    assert not page.js_errors


def test_a_runtime_fault_is_shown_as_the_box_that_carries_its_repair(open_panel):
    """setRuntimeIssue has reached for #runtime-error and #engine-error since
    04687f3, and neither existed in the markup. The code is defensive — it
    falls back to writing plain text into #runtime-note — so nothing threw and
    nothing looked broken. What was lost is the half that matters: the fallback
    is a sentence, while the box carries a title, the sentence AND the button
    that ends the fault.

    So the panel could tell the owner his database was behind the code and
    have no way to offer him the Upgrade that fixes it — which is the whole
    reason the richer rendering was written."""
    page = open_panel()
    page.evaluate("window.__sx_test_issue = {kind: 'schema_lag'}")

    for identifier in ("#runtime-error", "#engine-error"):
        assert page.locator(identifier).count() == 1, (
            f"{identifier} is missing again, and setRuntimeIssue silently "
            "degrades to a plain line when it is")
    assert not page.js_errors


def test_an_unsupported_feature_fails_with_a_version_error_not_a_generic_one(open_panel):
    """Section 1.6. An engine that does not deploy `crawl_parallel_sources`
    answers the save with 400 "unknown setting 'crawl_parallel_sources'" — a
    sentence about a typo, for what is a version gap, and every other field in
    the same request would have saved. The version question is asked first."""
    page = open_panel(extension_version="0.2.0", engine_version="0.1.0",
                      version_reporting=False)
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(200)
    page.evaluate("() => { window.__writes.length = 0; }")

    page.click("#crawl-save")
    page.wait_for_timeout(300)

    message = page.inner_text("#crawl-msg")
    assert "0.1.0" in message and "0.2.0" in message, (
        "the refusal names neither version, which is the generic error again")
    assert "engine" in message.lower()
    assert "unknown setting" not in message
    writes = page.evaluate(
        "window.__writes.filter(w => w.path.startsWith('/api/settings'))")
    assert not writes, "it asked an engine that cannot do it, then reported the answer"
    assert not page.js_errors


def test_a_supported_feature_is_not_blocked_by_the_gate(open_panel):
    """The gate must refuse a version gap and nothing else. A gate that blocks
    a working feature is worse than the error it replaced."""
    page = open_panel(extension_version="0.2.0", engine_version="0.2.0")
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(200)

    page.click("#crawl-save")
    page.wait_for_timeout(300)

    assert "saved" in page.inner_text("#crawl-msg")
    assert page.evaluate(
        "window.__writes.filter(w => w.path.startsWith('/api/settings')).length") == 1


def test_an_engine_that_reports_and_lacks_the_feature_is_named_as_such(open_panel):
    """The third refusal, and the one the panel will actually meet next: an
    engine one release behind, which reports its capabilities and does not have
    this one. "Cannot say" and "does not have it" send the owner to the same
    place here, but not for the same reason, so they do not share a sentence."""
    page = open_panel(extension_version="0.2.0", engine_version="0.2.0",
                      omit_capabilities=("crawl_parallel_sources",))
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(200)
    page.evaluate("() => { window.__writes.length = 0; }")

    page.click("#crawl-save")
    page.wait_for_timeout(300)

    message = page.inner_text("#crawl-msg")
    assert "not deployed by this ScrapeX engine (0.2.0)" in message
    assert "this extension is 0.2.0" in message
    assert "too old to say" not in message
    assert not page.evaluate(
        "window.__writes.filter(w => w.path.startsWith('/api/settings')).length")
    assert not page.js_errors


def test_a_panel_that_cannot_read_its_own_version_says_so_and_loses_nothing(open_panel):
    """The gate's own failure mode, and it must not be silent (Q3).

    Handing an unreadable version to the comparison would throw inside the click
    handler: no message, no request, nothing saved and nothing said — which is
    worse than the generic error the gate replaced.
    """
    page = open_panel(extension_version="", engine_version="0.2.0")
    page.click(SETTINGS_TAB)
    page.click('[data-sect="s-crawl"]')
    page.wait_for_timeout(200)
    page.evaluate("() => { window.__writes.length = 0; }")

    page.click("#crawl-save")
    page.wait_for_timeout(300)

    assert "cannot read its own version" in page.inner_text("#crawl-msg")
    assert text_of(page, "#about-extension-version") == "unknown"
    assert not page.js_errors, f"the gate threw instead of speaking: {page.js_errors}"
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


def test_a_page_that_is_only_a_shape_says_so_on_itself(open_panel):
    """Profile, Engine and Console exist so their shape can be agreed before
    they are written. Every one of them is empty behind the glass.

    A page that looks finished and does nothing is worse than no page: the owner
    presses Install, nothing happens, and the product looks broken rather than
    unbuilt. So each carries a note naming the milestone it is waiting for, and
    every control on it is disabled.

    The project's own rule, from the brief: "Clearly identify mock and production
    integrations." This is the mechanical form of it."""
    page = open_panel()

    # PAGES LEAVE THIS LIST AS THEY ARE BUILT, and each has to be taken out by
    # hand. `engines` went when its rows became real (M1b); `profile` went when
    # its button started signing people in (M1c). Both would have passed here
    # afterwards — a note and a disabled control are easy to keep — which is
    # exactly why the removal is deliberate: a page reporting true facts under
    # "Not built yet" is lying in the safe direction, and the next reader
    # trusts neither line.
    shapes = (("console", "M7"),)
    assert shapes, (
        "every page is built, so this test now passes by checking nothing — "
        "delete it rather than leaving it green over an empty list")

    for view, milestone in shapes:
        page.click(f"#tab-{view}")
        panel = page.locator(f"#view-{view}")
        assert panel.is_visible(), f"the {view} page does not open"

        note = panel.locator(".planned-note")
        assert note.count() == 1, f"the {view} page does not say it is unbuilt"
        assert note.get_attribute("data-planned") == milestone, (
            f"the {view} page does not name the milestone it waits for")
        assert "Not built yet" in note.inner_text()

        buttons = panel.locator("button")
        for i in range(buttons.count()):
            assert buttons.nth(i).is_disabled(), (
                f"a control on the {view} page is pressable while the page does "
                "nothing — that reads as broken, not as unbuilt")


def test_the_shape_opens_on_who_you_are_and_what_is_installed(open_panel):
    """The agreed order, asserted because it is a decision and not an accident:
    Profile is page one and Engine page two, before anything can be run."""
    page = open_panel()
    views = page.eval_on_selector_all(
        "nav.side-rail button[data-view]", "els => els.map(e => e.dataset.view)")

    assert views[0] == "profile"
    assert views[1] == "engines"



def test_the_rail_groups_say_which_pages_need_an_engine(open_panel):
    """THE GROUPING CARRIES MEANING, so it is a guard and not a preference.

    Profile and Engine are answerable on a device with no engine on it at all
    — who am I, and what is installed. Every page in the second group is served
    by the engine and does nothing without one. A new install spends its whole
    first minute in exactly that state, so the boundary has to be visible
    before anything explains it.

    A page joining the wrong group is not a cosmetic mistake: it promises the
    owner something the panel cannot do yet.
    """
    page = open_panel()
    groups = page.eval_on_selector_all(
        "nav.side-rail .rail-tablist",
        """els => els.map(e => [...e.querySelectorAll('button[data-view]')]
                                 .map(b => b.dataset.view))""")

    assert groups[0] == ["profile", "engines"], "the extension's own pages"
    assert groups[1] == ["source", "run", "data", "finance"], "the engine's pages"
    assert groups[2] == ["appearance", "sources", "console", "settings"]

    # A group has to READ as one. The hairline it replaced said "something
    # changed here" without saying what, and one icon of four moving across it
    # would have looked like nothing at all.
    assert page.eval_on_selector_all(
        "nav.side-rail .rail-tablist",
        """els => els.every(e => {
            const s = getComputedStyle(e);
            return s.borderTopWidth !== '0px' && s.borderRadius !== '0px';
        })"""), "the groups are not drawn as containers"
    assert page.locator(".rail-divider").count() == 0


def test_the_panel_opens_on_one_question(open_panel):
    """The first screen a new install shows.

    Everything a profile page would normally print — the account, the last
    backup, which device holds the lease — is unknowable before sign-in, and a
    column of em dashes is not information. So the page asks the one question
    it can and shows nothing else, and it is what opens.
    """
    page = open_panel()
    panel = page.locator("#view-profile")

    assert panel.is_visible(), "the panel did not open on Welcome"
    assert page.get_attribute("#tab-profile", "aria-current") == "page"
    assert not page.is_visible("#view-source")

    # SCOPED TO THE SIGNED-OUT HALF. The page has two states since M1c, and the
    # signed-in one is in the markup with `hidden` on it — asserting across
    # both would count a heading and a button nobody can see.
    out = panel.locator("#welcome-signed-out")
    assert out.is_visible()
    assert not page.is_visible("#welcome-signed-in")
    assert out.locator("h1").inner_text() == "Welcome to ScrapeX"
    assert out.locator(".card").count() == 0, "the empty page grew cards again"
    assert out.locator(".kv").count() == 0, "it is printing values it cannot know"
    buttons = out.locator("button")
    assert buttons.count() == 1
    assert "Continue with Google" in buttons.first.inner_text()


def test_the_engine_is_named_and_offers_one_square_install(open_panel):
    """The engine is a product with a name — ScrapeX-Engine — not "the engine",
    because the page is a catalogue that will hold more than one of them."""
    page = open_panel()

    # The owner chose this glyph by name. It is the one icon in the rail that
    # comes from Material SYMBOLS rather than the classic filled set, because
    # the classic set has no folder-of-code at all — so a well-meaning tidy-up
    # towards "one icon set" would silently take it away.
    assert page.locator("#tab-engines use").get_attribute("href").endswith(
        "#folder-code")

    page.click("#tab-engines")
    card = page.locator("#view-engines .card").first

    assert (card.locator("h2").text_content() or "").strip() == "ScrapeX-Engine"
    # TWO buttons now: check-again and download, in that order. The count is
    # asserted rather than "at least one", because a third arriving unnoticed is
    # how a card becomes a toolbar.
    assert card.locator("button").count() == 2
    install = card.locator("#engine-download")
    # DOWNLOAD, not Install: Chrome does not let an extension write outside its
    # own storage or start a program, so the button hands over the file and the
    # owner decides. A label promising more than the button can do is the kind
    # of claim a store reviewer reads as a deceptive install.
    assert install.get_attribute("aria-label") == "Download ScrapeX-Engine"
    assert install.locator("use").get_attribute("href").endswith("#file-download")

    # A SMALL square, and both halves have to be asserted. `icon-button` alone
    # is already square at the full touch-target height, so a squareness check
    # on its own passes whether or not the control is compact and proves
    # nothing about the size that was asked for.
    box = install.bounding_box()
    # Measured rather than parsed, so the assertion holds whatever unit the
    # token is written in.
    small = page.evaluate("""() => {
        const probe = document.createElement('div');
        probe.style.cssText =
          'position:absolute;visibility:hidden;height:var(--control-height-sm)';
        document.body.appendChild(probe);
        const h = probe.getBoundingClientRect().height;
        probe.remove();
        return h;
    }""")
    assert box and abs(box["width"] - box["height"]) < 1.5, (
        f"the install control is {box['width']}x{box['height']}, not a square")
    assert abs(box["width"] - small) < 1.5, (
        f"the install square is {box['width']}px, not the compact {small}px")


def test_no_two_rail_buttons_wear_the_same_icon(open_panel):
    """Found by looking at a screenshot, which is the only thing that could
    have found it: Console shipped with `dashboard`, the icon the Workspace
    toggle four buttons above it already wore.

    The rail is icons only — every label is a tooltip or screen-reader text —
    so a repeated symbol is not a blemish, it is two destinations that cannot
    be told apart at the one moment the owner is choosing between them.
    """
    page = open_panel()
    icons = page.eval_on_selector_all(
        "nav.side-rail button",
        """els => els.map(e => [e.id, (e.querySelector('use')
             ?.getAttribute('href') || '').split('#').pop()])""")

    assert icons, "the rail has no buttons"
    seen: dict[str, str] = {}
    clashes = []
    for button, icon in icons:
        assert icon, f"{button} has no icon"
        if icon in seen:
            clashes.append(f"{seen[icon]} and {button} both use #{icon}")
        seen[icon] = button
    assert not clashes, "; ".join(clashes)


def test_the_profile_button_wears_the_account_and_not_a_shield(open_panel):
    """It carried `security` — a shield, which says "protection" and not "you".

    Before sign-in there is no photo to show, so the button falls back to the
    generic account mark. The photo slot is already in the markup beside it,
    hidden, so M1 swaps a class rather than rebuilding the button.
    """
    page = open_panel()

    assert page.locator("#tab-profile use").get_attribute("href").endswith(
        "#account-circle")
    assert page.is_visible("#profile-avatar-fallback")
    assert not page.is_visible("#profile-avatar"), (
        "an empty photo slot is drawn where the account mark should be")


def test_the_photo_replaces_the_mark_and_a_broken_one_gives_it_back(open_panel):
    """M1 will call setProfileAvatar with the account's `picture`. Everything
    it needs already works, which is why this is testable before sign-in exists.

    THE FALLBACK ON ERROR IS THE POINT. Google's avatar URLs expire and the
    panel is often opened offline; a photo that fails to load must not leave a
    blank hole where a rail button was. That is why the swap happens on `load`
    and is undone on `error`, rather than being set once and trusted.
    """
    page = open_panel()
    tiny_png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
                "FcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

    page.evaluate(f"() => setProfileAvatar({tiny_png!r})")
    page.wait_for_selector("#profile-avatar:visible")
    assert not page.is_visible("#profile-avatar-fallback"), (
        "the generic mark is still drawn on top of the account's own photo")

    # The URL expires, or the machine is offline. The button must not go blank.
    page.evaluate("() => setProfileAvatar('data:image/png;base64,not-an-image')")
    page.wait_for_selector("#profile-avatar-fallback:visible")
    assert not page.is_visible("#profile-avatar")

    # Signing out puts the mark back with no round trip at all.
    page.evaluate(f"() => setProfileAvatar({tiny_png!r})")
    page.wait_for_selector("#profile-avatar:visible")
    page.evaluate("() => setProfileAvatar(null)")
    assert page.is_visible("#profile-avatar-fallback")
    assert not page.is_visible("#profile-avatar")


def test_the_photo_is_drawn_at_the_size_of_the_mark_it_replaces(open_panel):
    """A photo one pixel larger than the icon would shift every button under it
    the moment someone signs in."""
    page = open_panel()
    icon = page.locator("#profile-avatar-fallback").bounding_box()

    page.evaluate("() => { const p = document.getElementById('profile-avatar');"
                  " p.classList.remove('hidden');"
                  " document.getElementById('profile-avatar-fallback')"
                  "   .classList.add('hidden'); }")
    photo = page.locator("#profile-avatar").bounding_box()

    assert icon and photo
    assert abs(photo["width"] - icon["width"]) < 0.5
    assert abs(photo["height"] - icon["height"]) < 0.5
    assert page.locator("#profile-avatar").evaluate(
        "el => getComputedStyle(el).borderRadius") == "50%", "a square face"


#: Page names are singular. `Settings` is the one declared exception and it
#: carries its reason, because an exception without one is how a rule becomes a
#: preference. Nothing else may be added here without the same.
PLURAL_PAGE_NAMES_ALLOWED = {
    "Settings": "the singular `Setting` means one setting, or a scene, and is "
                "broken English for a page that holds dozens; every product "
                "that has this page writes it plural",
}


def test_every_page_is_named_in_the_singular(open_panel):
    """The owner's rule: «اسماء الصفح دائما مفرد».

    A rail is read at a glance and the names sit under one another. One plural
    among singulars reads as a different KIND of destination — a list rather
    than a place — and the panel has both, so the difference has to mean
    something.

    Two names moved when this was written: `Engines` became `Engine`, and the
    source manager stopped being a sentence (`Add or edit sources`) and became
    `Library` — a name, singular, that does not collide with the `Source` page
    beside it, which does something else entirely.
    """
    page = open_panel()
    names = page.eval_on_selector_all(
        "nav.side-rail button[data-view]",
        "els => els.map(e => e.getAttribute('aria-label'))")

    assert names, "the rail has no destinations"
    plural = [n for n in names
              if n and n.endswith("s") and not n.endswith("ss")
              and n not in PLURAL_PAGE_NAMES_ALLOWED]
    assert not plural, f"page names in the plural: {plural}"

    # A name is a name, not a sentence. `Add or edit sources` was the one that
    # broke this and it is why the rule needed writing down.
    long_names = [n for n in names if n and len(n.split()) > 2]
    assert not long_names, f"these are sentences, not page names: {long_names}"


def test_the_rail_name_and_the_page_heading_are_the_same_word(open_panel):
    """A button labelled one thing opening a page headed another is a panel that
    cannot be talked about. `Add or edit sources` opened `Add or edit source`;
    now `Library` opens `Library`.

    THE RULE IS ABOUT TITLED PAGES, and one page is deliberately not one.
    Welcome carries no `.view-heading` at all — it is a line and a button, by
    the owner's instruction, and "Welcome to ScrapeX" is a greeting rather than
    a title. Keying the rule on the heading block instead of on a list of
    exceptions means a page that GAINS a title is checked from that moment,
    with nobody having to remember to take it off a list.
    """
    page = open_panel()
    checked = 0
    for view in ("profile", "engines", "sources", "console", "settings", "run"):
        name = page.locator(
            f'nav.side-rail button[data-view="{view}"]').get_attribute("aria-label")
        page.click(f'nav.side-rail button[data-view="{view}"]')
        heading = page.locator(f"#view-{view} > .view-heading h1").first
        if heading.count() == 0:
            continue
        checked += 1
        text = (heading.text_content() or "").strip()
        assert text == name or name in text, (
            f"the {view} button says {name!r} and its page is headed {text!r}")
    assert checked >= 4, (
        f"only {checked} titled pages were checked; the heading block moved and "
        "this now passes by finding nothing")


def test_an_exception_to_the_naming_rule_carries_its_reason():
    """An exception with a bare name is a place to put anything."""
    for name, reason in PLURAL_PAGE_NAMES_ALLOWED.items():
        assert len(reason.split()) >= 8, (
            f"{name!r} is allowed in the plural and the reason is {reason!r}")


def test_the_engine_page_reports_what_is_installed_and_what_is_available(open_panel):
    """M1b. The page stopped being a shape, and this is what it became.

    THE ONE PAGE THAT MUST WORK WITH NO ENGINE INSTALLED — that is its whole
    purpose, and it is the state every machine is in for its first minute. So
    the extension reads the release feed itself; an engine that fetched it could
    only answer once it was already there.
    """
    page = open_panel()
    page.click("#tab-engines")
    # Waited for, not slept through. The feed carries its own four-second
    # timeout, so a fixed pause here would either be a flake or be longer than
    # the check it is waiting on.
    page.wait_for_function(
        "() => document.getElementById('engine-latest-detail').textContent !== ''",
        timeout=10_000)

    assert text_of(page, "#engine-status") == "Running"
    assert text_of(page, "#engine-installed-version") not in ("", "—", "not installed")
    assert str(PROTOCOL) in text_of(page, "#engine-protocol-row")

    # THE DEFAULT IS TODAY'S TRUTH: no engine release has been cut, so the
    # version manifest is not on the delivery endpoint yet and the request 404s.
    #
    # THIS ASSERTION USED TO SAY "unknown" AND WAS PINNING A DEFECT. "unknown"
    # means we could not find out; here we asked, the endpoint answered, and the
    # answer was that nothing is released. The row therefore contradicted the
    # sentence directly beneath it, which said we had checked. Found by looking
    # at the panel — four guards covered the reader and none covered the row.
    assert text_of(page, "#engine-latest-version") == "none yet"
    assert "No engine has been released yet" in text_of(page, "#engine-latest-detail")


def test_the_latest_row_never_contradicts_the_sentence_under_it(open_panel):
    """THE GENERAL FORM OF THE DEFECT ABOVE, so it cannot come back in another
    state. The reader distinguishes four outcomes; the row is allowed to
    summarise them, but never to say the opposite of the line beneath it.

    "unknown" is a claim about OUR knowledge, and it may only appear when we
    genuinely could not find out.
    """
    page = open_panel()
    page.click("#tab-engines")
    page.wait_for_function(
        "() => document.getElementById('engine-latest-detail').textContent !== ''",
        timeout=10_000)

    value = text_of(page, "#engine-latest-version")
    detail = text_of(page, "#engine-latest-detail")

    if "has been released yet" in detail:
        assert value != "unknown", (
            f"the row says {value!r} — we could not find out — while the "
            f"sentence under it says we did: {detail!r}")


def test_a_published_engine_release_is_shown_by_its_version(open_panel):
    """The state this page exists for: something newer is available.

    The product name matters as much as the number. The delivery endpoint
    carries several products' manifests side by side, so one that does not say
    `scrapex-engine` says nothing about the engine — a case the pure reader
    covers, and this proves the page is wired to that reader."""
    page = open_panel(engine_manifest={
        "product": "scrapex-engine",
        "version": "0.9.0",
        "tag": "engine-v0.9.0",
        "published_at": "2026-08-06T09:00:00Z",
        "installer": {"name": "scrapex-engine.exe", "url": "https://x/e.exe",
                      "bytes": 24000000, "sha256": "a" * 64},
    })
    page.click("#tab-engines")
    page.wait_for_function(
        "() => document.getElementById('engine-latest-version').textContent !== '—'",
        timeout=10_000)

    assert text_of(page, "#engine-latest-version") == "0.9.0"
    assert text_of(page, "#engine-latest-detail") == "", (
        "a release with an installer needs no explanation under it")


def test_the_download_button_hands_over_the_file_and_the_steps(open_panel):
    """DOWNLOAD, NOT INSTALL, and the button now does the thing it shows.

    Chrome does not let an extension write outside its own storage or start a
    program — a browser security boundary, not a gap in this codebase. So the
    honest button hands the owner the file and says what to do with it, and the
    decision after that is theirs.

    It sat disabled under a note saying installing "is not built yet", which was
    true and useless: the row knew a release existed and the owner still had no
    way to get it.
    """
    page = open_panel(engine_manifest={
        "product": "scrapex-engine", "version": "0.9.0",
        "installer": {"name": "scrapex-engine.exe",
                      "url": "https://example.test/scrapex-engine.exe",
                      "bytes": 24000000, "sha256": "b" * 64},
    })
    page.click("#tab-engines")
    page.wait_for_function(
        "() => !document.getElementById('engine-download').disabled",
        timeout=10_000)

    assert not page.locator("#engine-download").is_disabled()
    assert page.locator("#engine-install-steps").is_visible()

    # The steps are folded shut by default; open them before reading the text.
    page.click("#engine-install-steps summary")
    steps = page.inner_text("#engine-install-steps")
    # The SmartScreen warning is named in the dialog's own words. A warning the
    # owner was told to expect is a detail; the same one unannounced is where
    # people stop installing.
    assert "More info" in steps and "Run anyway" in steps
    assert "no administrator rights" in steps
    # THE STEP MUST NAME THE CONTROL THE WAY THE CONTROL NAMES ITSELF, and this
    # assertion is read off the DOM rather than typed, so the two cannot drift.
    # It used to be `assert "refresh button" in steps` — which passed while the
    # step pointed at "the refresh button above" and the only button up there was
    # icon-only, named "Check ScrapeX-Engine again" by its `aria-label` and by
    # nothing else. Nothing on the card was called refresh. That is the same
    # shape as the two defects this suite has already been bitten by: a test
    # standing over wording the rest of the panel contradicts.
    recheck_name = page.get_attribute("#engine-recheck", "aria-label")
    assert recheck_name and recheck_name in steps, (
        f"the steps tell the owner to press something the card does not call "
        f"anything: the control's only name is {recheck_name!r}")
    assert "b" * 64 in text_of(page, "#engine-download-checksum"), (
        "the checksum is not shown, so a download cannot be proved whole")


def test_the_download_button_actually_hands_over_the_file(open_panel):
    """PRESS IT. Everything else about this button was asserted — that it is
    enabled, that the steps beside it are right, that the checksum is printed —
    and the one line that makes the feature exist was observed by nothing.

    The branch this landed on is called `the-download-button-downloads`, and a
    suite that never clicks the button cannot tell that name from a wish. Found
    by asking of each assertion what code change would break it, and finding that
    deleting the `onclick` broke none of them.
    """
    page = open_panel(engine_manifest={
        "product": "scrapex-engine", "version": "0.9.0",
        "installer": {"name": "scrapex-engine.exe",
                      "url": "https://example.test/scrapex-engine.exe",
                      "bytes": 24000000, "sha256": "b" * 64},
    })
    page.click("#tab-engines")
    page.wait_for_function(
        "() => !document.getElementById('engine-download').disabled",
        timeout=10_000)

    # Chrome's own download is a navigation the panel does not own, so what is
    # asserted is the handover itself: the url the panel was given, opened in a
    # new tab rather than replacing the panel.
    page.evaluate("""() => {
      window.__opened = [];
      window.open = (url, target) => { window.__opened.push([url, target]); return null; };
    }""")
    page.click("#engine-download")

    assert page.evaluate("window.__opened") == [
        ["https://example.test/scrapex-engine.exe", "_blank"]
    ], "the button did not hand over the url the manifest published"


def test_the_recheck_button_repaints_the_engine_card(open_panel):
    """The button exists so a release cut five minutes ago becomes visible
    without closing the panel. It called `render()`, which refreshes the panel's
    state and does not touch this card — `renderEngines` is reached from one
    other place, entering the view. So the cache was dropped, the feed was
    re-fetched, and every field went on showing the answer from when the page
    was opened: the button did nothing a person could see.

    Scribbling over the card first is what makes this bite. Without it the test
    passes against a button that does nothing, because the right answer is
    already on screen.
    """
    page = open_panel(engine_manifest={
        "product": "scrapex-engine", "version": "0.9.0",
        "installer": {"name": "scrapex-engine.exe",
                      "url": "https://example.test/scrapex-engine.exe",
                      "bytes": 24000000, "sha256": "b" * 64},
    })
    page.click("#tab-engines")
    page.wait_for_function(
        "() => document.getElementById('engine-latest-version').textContent === '0.9.0'",
        timeout=10_000)

    before = page.evaluate(
        "window.__calls.filter(c => String(c).includes('version.json')).length")
    page.evaluate(
        "document.getElementById('engine-latest-version').textContent = 'STALE'")

    page.click("#engine-recheck")

    page.wait_for_function(
        "() => document.getElementById('engine-latest-version').textContent === '0.9.0'",
        timeout=10_000)
    after = page.evaluate(
        "window.__calls.filter(c => String(c).includes('version.json')).length")
    assert after > before, (
        "the card was repainted from the cache — the button drops it precisely "
        "so the feed is asked again")


def test_the_download_button_stays_dead_when_there_is_nothing_to_download(open_panel):
    """The default state today: nothing released. A button that looks pressable
    and does nothing is worse than one that is plainly not ready."""
    page = open_panel()
    page.click("#tab-engines")
    page.wait_for_function(
        "() => document.getElementById('engine-latest-detail').textContent !== ''",
        timeout=10_000)

    assert page.locator("#engine-download").is_disabled()
    assert not page.locator("#engine-install-steps").is_visible()


def test_a_release_with_no_installer_says_so_before_the_press(open_panel):
    """Discovering it at the moment of pressing Install is the failure."""
    page = open_panel(engine_manifest={"product": "scrapex-engine",
                                       "version": "0.9.0", "installer": None})
    page.click("#tab-engines")
    page.wait_for_function(
        "() => document.getElementById('engine-latest-detail').textContent !== ''",
        timeout=10_000)

    assert text_of(page, "#engine-latest-version") == "0.9.0"
    assert "no installer attached" in text_of(page, "#engine-latest-detail")


def test_the_engine_page_says_not_installed_when_it_is_not(open_panel):
    """The first minute on a new machine, which is the state the page exists for."""
    page = open_panel(engine_up=False)
    page.click("#tab-engines")
    page.wait_for_function(
        "() => document.getElementById('engine-status').textContent !== 'Checking…'",
        timeout=10_000)

    assert "Not installed" in text_of(page, "#engine-status")
    assert text_of(page, "#engine-installed-version") == "not installed"
    assert "has not stated its own" in text_of(page, "#engine-protocol-row")
