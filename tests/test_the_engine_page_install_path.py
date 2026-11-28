"""The Engine page's install path and the DB Browser card, as he approved them (#1556).

Designed through `design-the-experience` and approved on 2026-11-26 («أوافق على
الاثنين»): the record, the reference sheet and the 40 drawn states are on #1556.
These tests drive the shipped panel through `tools/panel_harness.py`, the page the
drawings were made from, and hold each approved state:

- A, no engine answered and no helper: "Not detected", one sentence with the
  action, one note in place of the version rows, Download engine the one primary.
- B, an engine there but not answering: no Download; a stopped engine (the helper
  answers PING) reads "Stopped" and names Run's Start; a silent helper says so.
- C, an engine running: "Version", "Installed build" / "Project files", no
  Download unless a newer release can be installed, "Unreleased" on project files
  newer than the release, "Too old" on a Python below the pin, no control.
- the DB Browser for SQLite card on the Database page: the read-only warning, Copy
  database path, the download page, and what it says when it cannot copy.
"""
from __future__ import annotations

import re

import pytest

from tests.test_panel_dom import (  # noqa: F401  (fixtures are used by name)
    browser,
    harness,
    open_engine,
    open_panel,
    text_of,
)

pytestmark = pytest.mark.extension

#: The manifest the hub serves, in the shape `ScrapeX/json/version.json` has.
RELEASE = {
    "product": "scrapex-engine",
    "version": "0.4.67",
    "tag": "engine-v0.4.67",
    "published_at": "2026-10-24T13:00:16Z",
    "release_url": "https://github.com/muhammadbayoumi/mbiX-hub/releases/tag/engine-v0.4.67",
    "minimum_extension_version": "0.3.9",
    "protocol_version": 1,
    "installer": {
        "name": "scrapex-engine.exe",
        "url": "https://github.com/muhammadbayoumi/mbiX-hub/releases/download/"
               "engine-v0.4.67/scrapex-engine.exe",
        "bytes": 39477574,
        "sha256": "a50b07f539ed2111d0480a4564eebce237b7c86e91d63a9352adc3ac1d49afca",
    },
}

#: An installed build, as `scrapex/provenance.py` reports one.
FROZEN = {"mode": "frozen", "sealed_at": "2026-11-25T10:00:00+00:00",
          "commit": "e99ca9ba" + "0" * 32, "commit_now": None, "moved": None,
          "stale": None,
          "detail": ("this is an installed build; it carries no source tree to compare "
                     "against, so whether newer code exists on disk cannot be answered "
                     "from inside it.")}
#: Project files, level with the disk.
SOURCE = {"mode": "source", "sealed_at": "2026-11-25T10:00:00+00:00",
          "commit": "6cb6291c" + "0" * 32, "commit_now": "6cb6291c" + "0" * 32,
          "moved": False, "stale": False,
          "detail": "running from source, and level with the code on disk."}

A_SENTENCE = ("No engine answered on this computer. Download engine to install it, or "
              "run scrapex-engine.exe if it is already installed.")
VERSIONS_LATER = "Versions show here once the engine answers."
LATEST_IN_A = ("37.6 MB installer, published 24 October 2026. Version 0.4.67 cannot "
               "open a database that a newer version has upgraded.")
THE_HIDDEN_ROWS = ("#engine-spec-installed", "#engine-spec-build", "#engine-spec-python",
                   "#engine-spec-sqlite", "#engine-spec-protocol")


def visible(page, selector: str) -> bool:
    return page.locator(selector).first.is_visible()


def wait_for_state(page, text: str, timeout: int = 12_000) -> None:
    page.wait_for_function(
        "(want) => (document.getElementById('engine-state-text').textContent || '')"
        ".trim() === want", arg=text, timeout=timeout)


def detail_page(open_panel, width: int = 400, **stub):
    page = open_panel(view="engines", **stub)
    page.set_viewport_size({"width": width, "height": 900})
    open_engine(page)
    return page


# ---- A: no engine answered, no helper ---------------------------------------

@pytest.mark.parametrize("width", [320, 400, 480])
def test_with_no_engine_and_no_helper_download_is_the_one_action(open_panel, width):
    page = detail_page(open_panel, width, engine_up=False, engine_manifest=RELEASE,
                       native_mode="absent")
    wait_for_state(page, "Not detected")
    page.wait_for_function(
        "(want) => document.getElementById('engine-state-detail').textContent === want",
        arg=A_SENTENCE)
    # ONE NOTE WHERE THE VERSION ROWS WERE: nothing can report them, and Python and
    # SQLite are not things he installs (packaging/engine_entry.py:179-180).
    assert visible(page, "#engine-spec-versions-note")
    assert text_of(page, "#engine-versions-note-title") == \
        "Python and SQLite come with the engine"
    assert text_of(page, "#engine-versions-note-text") == \
        "Nothing else has to be installed. " + VERSIONS_LATER
    for row in THE_HIDDEN_ROWS:
        assert not visible(page, row), f"{row} is drawn with no engine to report it"
    # THE LATEST ROW SAYS WHAT DOWNLOAD BRINGS, and wears no badge: the button says it.
    assert text_of(page, "#engine-latest-version") == "0.4.67"
    assert text_of(page, "#engine-latest-detail") == LATEST_IN_A
    assert not visible(page, "#engine-release-verdict")
    assert not visible(page, "#engine-row-verdict")
    # DOWNLOAD ENGINE, THE PAGE'S ONE PRIMARY.
    assert visible(page, "#engine-download")
    assert page.locator("#engine-download").is_enabled()
    assert text_of(page, "#engine-download-label") == "Download engine"
    primaries = page.locator("#view-engine-detail .engine-action-primary:visible")
    assert primaries.count() == 1
    # Nothing to restart.
    assert not visible(page, "#runtime-restart")
    # "Not installed" is the one answer the startup trace leaves out (`askTheHelper`).
    assert page.evaluate(
        "() => performance.getEntriesByName('scrapex:helper-unanswered').length") == 0


def test_an_unreachable_release_page_is_said_and_download_is_held(open_panel):
    page = detail_page(open_panel, engine_up=False, engine_manifest="offline",
                       native_mode="absent")
    wait_for_state(page, "Not detected")
    page.wait_for_function(
        "(want) => document.getElementById('engine-state-detail').textContent === want",
        arg=("No engine answered on this computer, and the release page could not be "
             "reached. Press Check again to retry."))
    assert text_of(page, "#engine-latest-version") == "Unavailable"
    # NOT "The engine you have keeps working.": there is none.
    assert text_of(page, "#engine-latest-detail") == "Could not reach the release page."
    assert visible(page, "#engine-download")
    assert not page.locator("#engine-download").is_enabled()


def test_a_release_feed_that_answers_404_draws_no_download(open_panel):
    page = detail_page(open_panel, engine_up=False, engine_manifest=None,
                       native_mode="absent")
    wait_for_state(page, "Not detected")
    page.wait_for_function(
        "() => document.getElementById('engine-state-detail').textContent"
        " === 'No engine answered on this computer.'")
    assert text_of(page, "#engine-latest-version") == "No release yet"
    assert text_of(page, "#engine-latest-detail") == ""
    # CLAUDE.md: if the route 404s, do not draw the control.
    assert not visible(page, "#engine-download")
    assert not visible(page, "#engine-install-steps")


# ---- B: an engine is there but does not answer ----------------------------------

def test_a_stopped_engine_reads_stopped_and_names_runs_start(open_panel):
    page = detail_page(open_panel, engine_up=False, engine_manifest=RELEASE,
                       native_mode="ok", engine_version="0.4.89")
    wait_for_state(page, "Stopped")
    assert text_of(page, "#engine-state-detail") == (
        "ScrapeX Engine 0.4.89 is on this computer and not running. "
        "Start engine is on the Run page.")
    assert visible(page, "#engine-spec-versions-note")
    assert text_of(page, "#engine-versions-note-title") == ""
    assert text_of(page, "#engine-versions-note-text") == VERSIONS_LATER
    # AN ENGINE IS INSTALLED, so nothing offers to download one.
    assert not visible(page, "#engine-download")
    assert not visible(page, "#engine-install-steps")
    assert not visible(page, "#runtime-restart")
    # One summary writes the row too.
    assert text_of(page, "#engine-status") == "Stopped"


def test_a_silent_helper_is_said_and_the_row_keeps_two_words(open_panel):
    page = detail_page(open_panel, engine_up=False, engine_manifest=RELEASE,
                       native_mode="nonresponsive")
    wait_for_state(page, "Local helper did not answer", timeout=15_000)
    assert text_of(page, "#engine-state-detail") == "Press Check again."
    assert not visible(page, "#engine-download")
    assert not visible(page, "#runtime-restart")
    # THE LIST ROW: one or two words in the badge (badge.mdx@86c813ec:23), and the
    # sentence names the page that holds Check again.
    assert text_of(page, "#engine-status") == "No answer"
    assert text_of(page, "#engine-status-detail") == (
        "The local helper did not answer. Press Check again on the ScrapeX Engine page.")
    # NOT SWALLOWED: a helper that does not answer is in the startup trace.
    page.wait_for_function(TRACED, arg="helper-unanswered")


@pytest.mark.parametrize("mode, title, detail, row, row_detail", [
    ("forbidden", "Local helper not linked",
     "It does not recognise this extension, so Chrome cannot start the engine from "
     "here. Start it by running scrapex-engine.exe.", "Not linked",
     "The local helper does not recognise this extension. Open ScrapeX Engine for what "
     "to do."),
    ("crashed", "Local helper stopped",
     "It closed before it answered. Nothing is lost, and the engine can still be "
     "started from Windows.", "Helper stopped",
     "The local helper closed before it answered. Open ScrapeX Engine for what to do."),
])
def test_a_helper_that_refuses_or_dies_keeps_its_approved_words(open_panel, mode, title,
                                                                 detail, row, row_detail):
    page = detail_page(open_panel, engine_up=False, engine_manifest=RELEASE,
                       native_mode=mode)
    wait_for_state(page, title)
    assert text_of(page, "#engine-state-detail") == detail
    # THE LIST ROW: two words in the badge, and a sentence naming the page to open.
    assert text_of(page, "#engine-status") == row
    assert text_of(page, "#engine-status-detail") == row_detail
    assert not visible(page, "#engine-download")
    # NOT SWALLOWED: a helper that refuses or dies is in the startup trace.
    page.wait_for_function(TRACED, arg="helper-unanswered")


def test_a_check_that_timed_out_offers_no_download(open_panel):
    page = detail_page(open_panel, engine_up=True, engine_manifest=RELEASE,
                       native_mode="ok", blackhole_routes=("/api/health",))
    wait_for_state(page, "Check timed out", timeout=15_000)
    assert visible(page, "#engine-spec-versions-note")
    assert not visible(page, "#engine-download")
    assert not visible(page, "#engine-release-verdict")
    # THE TONE IS ON THE ICON ONLY (#1556's N6): the words stay the foreground colour.
    colours = page.evaluate("""() => {
      const banner = document.getElementById('engine-state-banner');
      const words = getComputedStyle(document.getElementById('engine-state-text')).color;
      const text = getComputedStyle(document.body).color;
      return {words, bannerBg: getComputedStyle(banner).backgroundColor,
              surface: getComputedStyle(document.querySelector('.engine-spec-list')).backgroundColor,
              text};
    }""")
    assert colours["bannerBg"] == colours["surface"], colours
    assert colours["words"] == colours["text"], colours
    # THE TONE IS THE ICON TILE'S: --warning-600 in light, as the busy tile wears it.
    tile = page.evaluate("""() => {
      const style = getComputedStyle(document.querySelector('#engine-state-banner > .icon-tile'));
      return [style.color, style.borderTopColor];
    }""")
    assert tile == ["rgb(220, 123, 24)", "rgb(220, 123, 24)"], tile
    # AN ENGINE MAY STILL BE THERE, so Restart stays: it goes only when nothing answered.
    assert visible(page, "#runtime-restart")


def test_a_worker_that_stopped_reads_not_running_for_either_build(open_panel):
    for build in (FROZEN, SOURCE):
        page = detail_page(open_panel, engine_up=True, engine_manifest=RELEASE,
                           native_mode="ok", worker_alive=False, engine_build=build)
        wait_for_state(page, "Not running")
        assert not visible(page, "#engine-download")


# ---- C: an engine running -----------------------------------------------------

def test_an_installed_build_at_the_release_is_up_to_date_and_offers_nothing(open_panel):
    page = detail_page(open_panel, engine_up=True, engine_manifest=RELEASE,
                       native_mode="ok", engine_version="0.4.67", engine_build=FROZEN)
    wait_for_state(page, "Running")
    page.wait_for_function(
        "() => document.getElementById('engine-release-verdict').textContent === 'Up to date'")
    assert text_of(page, "#engine-spec-installed .engine-spec-label") == "Version"
    assert text_of(page, "#engine-build-value") == "Installed build · e99ca9b"
    # NO DETAIL UNDER AN INSTALLED BUILD: the engine's sentence was six lines of jargon.
    assert text_of(page, "#engine-build-detail") == ""
    assert not visible(page, "#engine-download")
    assert not visible(page, "#engine-install-steps")


def test_project_files_newer_than_the_release_are_unreleased_and_get_no_download(
        open_panel):
    page = detail_page(
        open_panel, engine_up=True, engine_manifest=RELEASE, native_mode="ok",
        engine_version="0.4.89", engine_build=SOURCE,
        update_report={"installed": "0.4.89", "latest": dict(
            state="ok", detail="", version="0.4.67", tag="engine-v0.4.67",
            published_at="2026-10-24T13:00:16Z", url="", minimum_extension="0.3.9",
            protocol=1, installer=dict(RELEASE["installer"], verifiable=True)),
            "update_available": False, "can_self_update": False,
            "self_update_blocked_because": "", "progress_state": {"phase": "idle"}})
    wait_for_state(page, "Running")
    page.wait_for_function(
        "() => document.getElementById('engine-version-verdict').textContent === 'Unreleased'")
    badge = page.locator("#engine-version-verdict")
    # NEUTRAL: the amber badge is 2.68:1 in light (#1934); the word carries the state.
    assert badge.get_attribute("class") == "badge"
    assert text_of(page, "#engine-build-value") == "Project files · 6cb6291"
    assert not visible(page, "#engine-release-verdict")
    # NOT "0.4.89 is the published version." -- 0.4.67 is.
    assert "is the published version" not in text_of(page, "#engine-update-state")
    assert not visible(page, "#engine-download")


def test_project_files_behind_the_release_are_told_where_they_update(open_panel):
    page = detail_page(
        open_panel, engine_up=True, engine_manifest=RELEASE, native_mode="ok",
        engine_version="0.4.60", engine_build=SOURCE,
        update_report={"installed": "0.4.60", "latest": dict(
            state="ok", detail="", version="0.4.67", tag="engine-v0.4.67",
            published_at="2026-10-24T13:00:16Z", url="", minimum_extension="0.3.9",
            protocol=1, installer=dict(RELEASE["installer"], verifiable=True)),
            "update_available": True, "can_self_update": False,
            "self_update_blocked_because": ("This is a source checkout, not an installed "
                                            "engine. Update it with git rather than "
                                            "from here."),
            "progress_state": {"phase": "idle"}})
    wait_for_state(page, "Running")
    page.wait_for_function(
        "() => document.getElementById('engine-release-verdict').textContent"
        " === 'Update available'")
    page.wait_for_function(
        "() => document.getElementById('engine-update-state').textContent.length > 0")
    assert text_of(page, "#engine-update-state") == (
        "0.4.67 is published. These project files are 0.4.60; they are updated with "
        "the code, not downloaded here.")
    # NO SWITCH TO THE INSTALLED BUILD FROM HERE (his decision, 2026-11-26).
    assert not visible(page, "#engine-download")


def test_an_installed_build_behind_the_release_keeps_the_shipped_update(open_panel):
    page = detail_page(
        open_panel, engine_up=True, engine_manifest=RELEASE, native_mode="ok",
        engine_version="0.4.60", engine_build=FROZEN,
        update_report={"installed": "0.4.60", "latest": dict(
            state="ok", detail="", version="0.4.67", tag="engine-v0.4.67",
            published_at="2026-10-24T13:00:16Z", url="", minimum_extension="0.3.9",
            protocol=1, installer=dict(RELEASE["installer"], verifiable=True)),
            "update_available": True, "can_self_update": True,
            "self_update_blocked_because": "", "progress_state": {"phase": "idle"}})
    wait_for_state(page, "Running")
    page.wait_for_function(
        "() => document.getElementById('engine-download-label').textContent"
        " === 'Download and check 0.4.67'")
    assert visible(page, "#engine-download")


def test_python_below_the_pin_is_too_old_names_the_project_files_and_has_no_control(
        open_panel):
    page = detail_page(open_panel, engine_up=True, engine_manifest=RELEASE,
                       native_mode="ok", engine_build=SOURCE,
                       engine_python={"version": "3.14.10", "floor": "3.15",
                                      "verdict": "below"})
    wait_for_state(page, "Running")
    badge = page.locator("#engine-python-verdict")
    assert text_of(page, "#engine-python-verdict") == "Too old"
    assert badge.get_attribute("class") == "badge"
    assert text_of(page, "#engine-python-detail") == (
        "This engine runs Python 3.14.10 from the project files; ScrapeX needs 3.15 or "
        "newer. Parts of the engine can fail until the project files run on 3.15.")
    assert page.locator("#engine-spec-python button, #engine-spec-python a").count() == 0


def test_an_engine_without_the_keys_says_who_did_not_report(open_panel):
    page = detail_page(open_panel, engine_up=True, engine_manifest=RELEASE,
                       native_mode="ok", engine_version="0.4.20", engine_build=False,
                       engine_python=False, engine_sqlite=False)
    wait_for_state(page, "Running")
    for value in ("#engine-build-value", "#engine-python-value", "#engine-sqlite-value"):
        assert text_of(page, value) == "Not reported by this engine", value


@pytest.mark.parametrize("width", [320, 360])
def test_a_badge_never_breaks_a_version(open_panel, width):
    """#1527: a row's badge wraps under its label before a number breaks."""
    page = detail_page(open_panel, width, engine_up=True, engine_manifest=RELEASE,
                       native_mode="ok", engine_version="0.4.60", engine_build=FROZEN,
                       engine_python={"version": "3.14.10", "floor": "3.15",
                                      "verdict": "below"})
    wait_for_state(page, "Running")
    page.wait_for_function(
        "() => document.getElementById('engine-release-verdict').textContent.length > 0")
    lines = page.evaluate("""() => ['engine-latest-version', 'engine-python-value',
                                    'engine-installed-version'].map(id => {
      const v = document.getElementById(id);
      const lh = parseFloat(getComputedStyle(v).lineHeight);
      return [id, v.textContent, Math.round(v.getBoundingClientRect().height / lh)];
    })""")
    for row_id, value, count in lines:
        assert count == 1, f"{row_id} '{value}' lays out on {count} lines at {width}px"


# ---- the check, and the page left open across a change --------------------------

def test_the_helper_is_asked_once_per_check_and_never_while_the_engine_answers(
        open_panel):
    """Once per draw of the Engine screens -- the list, then the engine's own page --
    and once per Check again. Never polled, and never while the engine answers, on a
    draw or on Check again."""
    page = open_panel(engine_up=False, engine_manifest=RELEASE, native_mode="ok")
    page.click('nav.side-rail button[data-view="engines"]')
    open_engine(page)
    wait_for_state(page, "Stopped")
    assert pings(page) == 2, "one ask per draw: the list, then the engine's own page"
    page.wait_for_timeout(3_000)
    assert pings(page) == 2, "the helper is being polled"
    page.click("#engine-recheck")
    page.wait_for_function("() => !document.getElementById('engine-recheck').disabled")
    wait_for_state(page, "Stopped")
    assert pings(page) == 3

    up = open_panel(engine_up=True, engine_manifest=RELEASE, native_mode="ok")
    up.click('nav.side-rail button[data-view="engines"]')
    open_engine(up)
    wait_for_state(up, "Running")
    up.click("#engine-recheck")
    up.wait_for_function("() => !document.getElementById('engine-recheck').disabled")
    wait_for_state(up, "Running")
    assert pings(up) == 0, "the helper was asked about an engine that answers"


FLIP = """
(() => { let inner;
  Object.defineProperty(window, 'fetch', { configurable: true,
    get() { const captured = inner;
      return (u, o) => (window.__engineDown && /127\\.0\\.0\\.1|localhost/.test(String(u)))
        ? Promise.reject(new TypeError('Failed to fetch')) : captured(u, o); },
    set(v) { inner = v; } }); })();
"""


def flipping_page(open_panel, browser, tmp_path, down_at_start: bool):
    """A panel whose engine can go down or come up while it stays open."""
    page_file = harness.build_page(
        tmp_path, harness.stub(engine_up=True, engine_manifest=RELEASE, native_mode="ok",
                               storage=None),
        name="flip.html")
    page = browser.new_page(viewport={"width": 400, "height": 900})
    page.add_init_script(f"window.__engineDown = {str(down_at_start).lower()};" + FLIP)
    page.goto(page_file.as_uri())
    harness.wait_until_settled(page)
    return page


def test_check_again_names_the_database_once_an_engine_comes_up(open_panel, browser,
                                                                tmp_path):
    page = flipping_page(open_panel, browser, tmp_path, down_at_start=True)
    try:
        page.click('nav.side-rail button[data-view="engines"]')
        open_engine(page)
        page.wait_for_function(
            "() => document.getElementById('engine-state-text').textContent !== 'Running'")
        page.evaluate("() => window.__engineDown = false")
        page.click("#engine-recheck")
        wait_for_state(page, "Running")
        page.wait_for_function(
            "() => document.getElementById('engine-state-detail').textContent"
            ".startsWith('Database: ')")
    finally:
        page.close()


@pytest.mark.parametrize("down_at_start", [False, True])
def test_runs_start_card_follows_the_engine_pages_check(open_panel, browser, tmp_path,
                                                        down_at_start):
    """#1974's first half: B0 says Start engine is on the Run page, so it must be."""
    page = flipping_page(open_panel, browser, tmp_path, down_at_start=down_at_start)
    try:
        page.click('nav.side-rail button[data-view="engines"]')
        open_engine(page)
        page.evaluate(f"() => window.__engineDown = {str(not down_at_start).lower()}")
        page.click("#engine-recheck")
        page.wait_for_function("() => !document.getElementById('engine-recheck').disabled")
        page.click('nav.side-rail button[data-view="run"]')
        page.wait_for_selector("#view-run", state="visible")
        engine_now_down = not down_at_start
        assert visible(page, "#setup") == engine_now_down
    finally:
        page.close()


# ---- no verdict before the helper answers (#2014's merge gate, reviewer B) -----------

#: Holds every fetch whose URL matches the pattern for `delay_ms` before the stub answers.
SLOW = """
(() => { let inner;
  Object.defineProperty(window, 'fetch', { configurable: true,
    get() { const captured = inner;
      return (u, o) => new RegExp(%s).test(String(u))
        ? new Promise((r) => setTimeout(r, %d)).then(() => captured(u, o))
        : captured(u, o); },
    set(v) { inner = v; } }); })();
"""


def slow_page(browser, tmp_path, pattern: str, delay_ms: int, ready: str, **stub):
    """A panel opened with every fetch matching `pattern` held for `delay_ms`."""
    page_file = harness.build_page(tmp_path, harness.stub(**stub), name="slow.html")
    page = browser.new_page(viewport={"width": 400, "height": 900})
    page.add_init_script(SLOW % (repr(pattern), delay_ms))
    page.goto(page_file.as_uri())
    {"settled": harness.wait_until_settled,
     "interactive": harness.wait_until_interactive}[ready](page)
    return page


def pings(page) -> int:
    return page.evaluate("() => window.__nativeCalls.filter((c) => c === 'PING').length")


def test_the_first_check_concludes_and_offers_nothing_before_the_helper_answers(
        browser, tmp_path):
    """A9: nothing is offered and no verdict is drawn until the first check answers. With
    the release feed taking 3 s, the banner said Not detected over an installed engine,
    Download drawn, before the helper was asked."""
    page = slow_page(browser, tmp_path, r"raw\.githubusercontent\.com", 3000, "settled",
                     engine_up=False, engine_manifest=RELEASE, native_mode="ok")
    try:
        page.click('nav.side-rail button[data-view="engines"]')
        open_engine(page)
        page.wait_for_timeout(1000)
        assert text_of(page, "#engine-state-text") == "Checking engine…"
        assert not visible(page, "#engine-download"), "Download offered before any answer"
        wait_for_state(page, "Stopped")
        assert not visible(page, "#engine-download")
    finally:
        page.close()


@pytest.mark.parametrize("native_mode, state", [("ok", "Stopped"), ("absent", "Not detected")])
def test_a_check_that_settles_with_the_engine_page_open_asks_the_helper(
        browser, tmp_path, native_mode, state):
    """He opened the Engine page while the panel's first health check was still out. It
    settled there with no one asking the helper: an installed engine read Not detected
    until Check again, and with no engine the sentence named a Download not drawn."""
    page = slow_page(browser, tmp_path, r"127\.0\.0\.1.*/api/health", 1500, "interactive",
                     engine_up=False, engine_manifest=RELEASE, native_mode=native_mode)
    try:
        page.click('nav.side-rail button[data-view="engines"]')
        open_engine(page)
        wait_for_state(page, state)
        assert pings(page) >= 1, "the helper was never asked"
        if state == "Stopped":
            assert not visible(page, "#engine-download")
        else:
            assert text_of(page, "#engine-state-detail") == A_SENTENCE
            page.wait_for_function(
                "() => !document.getElementById('engine-download').classList.contains('hidden')")
    finally:
        page.close()


def test_run_diagnostics_that_finds_the_engine_gone_asks_the_helper(open_panel, browser,
                                                                    tmp_path):
    """Run diagnostics on the Engine page found the engine gone and drew Not detected, the
    no-engine sentence and note, without asking the helper that says it is installed."""
    page = flipping_page(open_panel, browser, tmp_path, down_at_start=False)
    try:
        page.click('nav.side-rail button[data-view="engines"]')
        open_engine(page)
        wait_for_state(page, "Running")
        assert pings(page) == 0
        page.evaluate("() => window.__engineDown = true")
        page.click("#engine-diagnostics")
        wait_for_state(page, "Stopped")
        assert pings(page) == 1
        assert not visible(page, "#engine-download")
    finally:
        page.close()


#: A startup trace mark the panel wrote (`markStartup`), by name.
TRACED = "(name) => performance.getEntriesByName('scrapex:' + name).length >= 1"

#: The first PING is held and never answered (the transport times it out at 5 s); every
#: later PING is answered at once, as `scrapex/native.py` answers it.
HOLD_THE_FIRST_PING = """() => {
  const real = chrome.runtime.sendNativeMessage;
  let asked = 0;
  chrome.runtime.sendNativeMessage = (host, message, callback) => {
    if (message.command !== 'PING') return real(host, message, callback);
    asked += 1;
    window.__pings = asked;
    if (asked === 1) return;
    setTimeout(() => callback({ok: true, app: 'scrapex', app_version: '0.4.89',
                               protocol_version: message.protocol_version}), 0);
  };
}"""


def test_the_newest_ask_owns_the_answer(open_panel):
    """The list's ask is still out when the engine's own page asks again and hears that an
    engine is here. The list's ask then times out, and its late answer must not overwrite
    the newer one (`helperGeneration`)."""
    page = open_panel(engine_up=False, engine_manifest=RELEASE, native_mode="ok")
    page.evaluate(HOLD_THE_FIRST_PING)
    page.click('nav.side-rail button[data-view="engines"]')
    page.wait_for_function("() => window.__pings === 1")
    open_engine(page)
    page.wait_for_function("() => window.__pings === 2")
    wait_for_state(page, "Stopped")
    page.wait_for_timeout(6_500)          # past the first ask's own 5 s deadline
    assert text_of(page, "#engine-state-text") == "Stopped", (
        "an older ask's late answer overwrote the newer one")


def test_a_check_holds_download_and_a_press_in_it_starts_nothing(browser, tmp_path):
    """A check keeps the last answer and holds Download (`refreshEngineBusy`). A press
    in the meantime is dropped (`startInstallerDownload`), and the hold ends with the
    check."""
    page = slow_page(browser, tmp_path, r"127\.0\.0\.1.*/api/health", 2500, "interactive",
                     engine_up=False, engine_manifest=RELEASE, native_mode="absent")
    try:
        page.click('nav.side-rail button[data-view="engines"]')
        open_engine(page)
        wait_for_state(page, "Not detected")
        page.wait_for_function(
            "() => !document.getElementById('engine-download').classList.contains('hidden')")
        page.evaluate("""() => { window.__opened = [];
          window.open = (url) => { window.__opened.push(url); return null; }; }""")
        page.click("#engine-recheck")
        page.wait_for_function(
            "() => document.getElementById('engine-download').getAttribute('aria-disabled') === 'true'")
        page.evaluate("() => document.getElementById('engine-download').click()")
        assert page.evaluate("() => window.__opened") == [], (
            "a press during a check handed over the installer")
        page.wait_for_function("() => !document.getElementById('engine-recheck').disabled",
                               timeout=15_000)
        assert page.get_attribute("#engine-download", "aria-disabled") != "true"
        page.evaluate("() => document.getElementById('engine-download').click()")
        assert page.evaluate("() => window.__opened") == [RELEASE["installer"]["url"]]
    finally:
        page.close()


def test_a_helper_that_refuses_ping_is_still_a_helper(open_panel):
    """An older host answers PING "unknown command". It answered, so it is there and an
    engine is installed: read as absent, Download engine would be offered over it."""
    page = detail_page(open_panel, engine_up=False, engine_manifest=RELEASE,
                       native_mode="refuses")
    wait_for_state(page, "Stopped")
    assert text_of(page, "#engine-state-detail") == (
        "ScrapeX Engine is on this computer and not running. Start engine is on the Run page.")
    assert not visible(page, "#engine-download")
    page.wait_for_function(TRACED, arg="helper-unanswered")


def test_an_unreadable_release_manifest_is_said_and_download_is_held(open_panel):
    """A feed that answered with a manifest the panel cannot use: as with one that cannot
    be reached, the sentence says to retry and Download stays drawn, held."""
    page = detail_page(open_panel, engine_up=False, native_mode="absent",
                       engine_manifest={"product": "xaddin", "version": "1.0.0"})
    wait_for_state(page, "Not detected")
    page.wait_for_function(
        "(want) => document.getElementById('engine-state-detail').textContent === want",
        arg=("No engine answered on this computer, and the release page could not be "
             "reached. Press Check again to retry."))
    assert visible(page, "#engine-download")
    assert not page.locator("#engine-download").is_enabled()


def test_with_an_engine_running_an_offline_feed_keeps_its_own_words(open_panel):
    """"Could not reach the release page." is the no-engine sentence. With an engine
    running, the Latest row keeps the feed's own words, which say that engine keeps
    working."""
    page = detail_page(open_panel, engine_up=True, engine_manifest="offline",
                       native_mode="ok", engine_build=FROZEN)
    wait_for_state(page, "Running")
    page.wait_for_function(
        "() => document.getElementById('engine-latest-detail').textContent !== ''")
    assert text_of(page, "#engine-latest-detail") == (
        "Could not reach the release endpoint. The engine you have keeps working.")


# ---- the page drawn whole from each answer (#2014's merge gate, reviewer A) ------------

#: PINGs are held until the test releases them, in the order it chooses; every other
#: command goes to the stub's host. Unhandled rejections are recorded, because
#: `renderEngines` is not awaited where the engine's page is opened.
HOLD_PINGS = """() => {
  window.__held = [];
  window.__rejections = [];
  window.addEventListener('unhandledrejection', (e) => {
    window.__rejections.push(String((e.reason && e.reason.message) || e.reason));
  });
  const original = chrome.runtime.sendNativeMessage;
  chrome.runtime.sendNativeMessage = (host, message, callback) => {
    if (message.command !== 'PING') return original(host, message, callback);
    window.__nativeCalls.push('PING');
    window.__held.push(() => callback({ok: true, app: 'scrapex', app_version: '0.4.89',
                                       protocol_version: 1}));
  };
}"""

#: /api/health hangs while `window.__healthHangs` is true, honouring the abort signal, so
#: the panel's own deadline fires: a check that times out, on demand.
HEALTH_HANGS = """
(() => { let inner;
  Object.defineProperty(window, 'fetch', { configurable: true,
    get() { const captured = inner;
      return (u, o) => {
        if (window.__healthHangs && /\\/api\\/health/.test(String(u))) {
          return new Promise((_, reject) => {
            const s = o && o.signal;
            if (s) s.addEventListener('abort', () => reject(
              s.reason || Object.assign(new Error('aborted'), {name: 'AbortError'})),
              {once: true});
          });
        }
        return captured(u, o);
      }; },
    set(v) { inner = v; } }); })();
"""


def scripted_page(browser, tmp_path, init: str, name: str, **stub):
    """A panel with `init` run before its own scripts, settled, its page errors kept."""
    page_file = harness.build_page(tmp_path, harness.stub(**stub), name=name)
    page = browser.new_page(viewport={"width": 400, "height": 900})
    page.js_errors = []
    page.on("pageerror", lambda e: page.js_errors.append(str(e)))
    page.add_init_script(init)
    page.goto(page_file.as_uri())
    harness.wait_until_settled(page)
    return page


def to_the_engine_page(page) -> None:
    page.click('nav.side-rail button[data-view="engines"]')
    page.wait_for_selector("#view-engines", state="visible")
    open_engine(page)


def diagnose(page) -> None:
    page.click("#engine-diagnostics")
    page.wait_for_function(
        "() => !document.getElementById('engine-diagnostics-output').textContent"
        ".startsWith('Running diagnostics')")


def runs_start_card_is_drawn(page) -> bool:
    page.click('nav.side-rail button[data-view="run"]')
    page.wait_for_selector("#view-run", state="visible")
    return visible(page, "#setup")


def test_check_again_racing_a_draw_paints_the_release_it_read(open_panel):
    """A draw holds its release across the helper's ask, while Check again empties the
    cache: the draw went on to paint `null` and threw, unseen behind Check again's own
    paint."""
    page = open_panel(view="engines", engine_up=False, engine_manifest=RELEASE,
                      native_mode="ok")
    page.wait_for_function(
        "() => document.getElementById('engine-status').textContent.trim() === 'Stopped'")
    page.evaluate(HOLD_PINGS)
    open_engine(page)                       # a draw: the release in hand, PING 1 out
    page.wait_for_function("() => window.__held.length === 1")
    page.click("#engine-recheck")           # Check again: the cache emptied, PING 2 out
    page.wait_for_function("() => window.__held.length === 2", timeout=4_000)
    page.evaluate("() => window.__held[0]()")   # the draw's PING answers first
    page.wait_for_timeout(300)
    page.evaluate("() => window.__held[1]()")
    page.wait_for_function("() => !document.getElementById('engine-recheck').disabled")
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__rejections") == []
    assert not page.js_errors, page.js_errors


def test_run_diagnostics_draws_the_release_row_and_download_from_its_answer(browser,
                                                                            tmp_path):
    """No engine, then project files at 0.4.89 come up and he presses Run diagnostics:
    the banner said Running beside Download engine and the 0.4.67 installer's line, the
    downgrade this page never offers."""
    page = scripted_page(browser, tmp_path, "window.__engineDown = true;" + FLIP,
                         "diagnose-up.html", engine_up=True, engine_manifest=RELEASE,
                         native_mode="absent", engine_version="0.4.89", engine_build=SOURCE,
                         storage=None)
    try:
        to_the_engine_page(page)
        wait_for_state(page, "Not detected")
        page.wait_for_function(
            "() => !document.getElementById('engine-download').classList.contains('hidden')")
        page.evaluate("() => window.__engineDown = false")
        diagnose(page)
        wait_for_state(page, "Running")
        page.wait_for_function(
            "() => document.getElementById('engine-download').classList.contains('hidden')")
        assert text_of(page, "#engine-latest-detail") != LATEST_IN_A
        assert not visible(page, "#engine-install-steps")
        page.wait_for_function(
            "() => document.getElementById('engine-version-verdict').textContent === 'Unreleased'")
    finally:
        page.close()


@pytest.mark.parametrize("down_at_start", [True, False], ids=["comes-up", "goes-away"])
def test_run_diagnostics_draws_runs_start_card_from_its_answer(browser, tmp_path,
                                                                 down_at_start):
    """After Run diagnostics, Run's Start card stayed as the last check drew it: beside an
    engine now running, or missing for one now gone."""
    page = scripted_page(browser, tmp_path,
                         f"window.__engineDown = {str(down_at_start).lower()};" + FLIP,
                         f"diagnose-card-{down_at_start}.html", engine_up=True,
                         engine_manifest=RELEASE, native_mode="ok", storage=None)
    try:
        to_the_engine_page(page)
        page.evaluate(f"() => window.__engineDown = {str(not down_at_start).lower()}")
        diagnose(page)
        assert runs_start_card_is_drawn(page) == (not down_at_start)
    finally:
        page.close()


def test_the_stopped_sentence_finds_its_start_on_run(browser, tmp_path):
    """The engine stops; Run diagnostics; the Engine page reopened says "Start engine is
    on the Run page." Run had no Start card to show for it."""
    page = scripted_page(browser, tmp_path, "window.__engineDown = false;" + FLIP,
                         "stopped-sentence.html", engine_up=True, engine_manifest=RELEASE,
                         native_mode="ok", engine_version="0.4.89", storage=None)
    try:
        to_the_engine_page(page)
        wait_for_state(page, "Running")
        page.evaluate("() => window.__engineDown = true")
        diagnose(page)
        page.click("#engine-detail-back")
        page.wait_for_selector("#view-engines", state="visible")
        open_engine(page)
        wait_for_state(page, "Stopped")
        assert "Start engine is on the Run page." in text_of(page, "#engine-state-detail")
        assert runs_start_card_is_drawn(page), "the sentence points at a Start that is not there"
    finally:
        page.close()


def test_a_check_again_that_times_out_offers_no_start_beside_a_slow_engine(browser,
                                                                          tmp_path):
    """A DEADLINE IS NOT THE DARK: a check that ran out of time says nothing about
    whether the engine is gone. Check again drew Run's "Engine not running" and Start
    beside one still serving, which the restart's preflight already refuses to do."""
    page = scripted_page(browser, tmp_path, "window.__healthHangs = false;" + HEALTH_HANGS,
                         "slow-check.html", engine_up=True, engine_manifest=RELEASE,
                         native_mode="ok", engine_version="0.4.67", engine_build=FROZEN)
    try:
        assert not visible(page, "#setup")
        to_the_engine_page(page)
        wait_for_state(page, "Running")
        page.evaluate("() => window.__healthHangs = true")
        page.click("#engine-recheck")
        wait_for_state(page, "Check timed out", timeout=15_000)
        page.wait_for_function("() => !document.getElementById('engine-recheck').disabled",
                               timeout=15_000)
        assert not runs_start_card_is_drawn(page), "Start offered beside a slow engine"
    finally:
        page.close()


# ---- the DB Browser for SQLite card, on the Database page -----------------------

HIS_PATH = "C:\\Users\\Muham\\.scrapex\\engine\\scrapex-engine.db"
WARNING = ("Open it read-only. In DB Browser, choose File › Open Database Read Only… "
           "(Ctrl+Shift+O). If you open it any other way, one edit there stops the "
           "engine from saving until you choose Revert Changes.")


def database_page(open_panel, **stub):
    storage = stub.pop("storage", None)
    page = open_panel(view="database", storage=storage, **stub)
    page.wait_for_function(
        "() => (document.getElementById('db-health-status').textContent || '').trim() !== '—'")
    return page


def his_storage():
    return {"path": HIS_PATH, "folder": "C:\\Users\\Muham\\.scrapex\\engine",
            "backup_folder": "C:\\Users\\Muham\\.scrapex",
            "sizes": {"db_bytes": 4194304, "wal_bytes": 8192, "shm_bytes": 32768,
                      "free_bytes": 51539607552, "backup_bytes": 0, "backup_count": 0},
            "health": {"status": "healthy", "ok": True, "integrity_checked": False,
                       "detail": "Readable."},
            "schema": {"version": 27, "expected": 27, "pending": []},
            "last": None, "integrity": None, "backups": []}


@pytest.mark.parametrize("width", [320, 400, 480])
def test_the_db_browser_card_sits_after_health_and_says_how_to_open_it(open_panel, width):
    page = database_page(open_panel, engine_up=True, storage=his_storage())
    page.set_viewport_size({"width": width, "height": 900})
    card = page.locator("#db-browser")
    assert card.is_visible()
    # AFTER HEALTH, and the second card of the page.
    order = page.evaluate(
        "() => [...document.querySelectorAll('#view-database > .card')].map(c => c.id)")
    assert order.index("db-browser") == 2, order
    assert text_of(page, "#db-browser-title") == "DB Browser for SQLite"
    assert text_of(page, "#db-browser-line") == \
        "A free desktop app for looking through this database's tables."
    assert re.sub(r"\s+", " ", text_of(page, "#db-browser-warning")) == WARNING
    link = page.locator("#db-browser-download")
    assert link.get_attribute("href") == "https://sqlitebrowser.org/dl/"
    assert link.get_attribute("target") == "_blank"
    assert "noreferrer" in (link.get_attribute("rel") or "")
    assert text_of(page, "#db-browser-download") == "Open download page"
    assert visible(page, "#db-browser-copy")
    assert page.locator("#db-browser-result").get_attribute("role") == "status"
    # NOTHING SCROLLS SIDEWAYS.
    assert page.evaluate("() => document.documentElement.scrollWidth") == width
    # THE WARNING'S GLYPH CARRIES THE TONE; ITS WORDS ARE THE FOREGROUND (mandate,
    # docs/DESIGN-SYSTEM-SOURCES.md, "Warning words readable at 12 px").
    colours = page.evaluate("""() => {
      const probe = document.createElement('span');
      probe.style.color = 'var(--warning-600)'; document.body.append(probe);
      const warning600 = getComputedStyle(probe).color; probe.remove();
      const text = document.createElement('span');
      text.style.color = 'var(--text)'; document.body.append(text);
      const fg = getComputedStyle(text).color; text.remove();
      const glyph = getComputedStyle(document.querySelector('#db-browser-warning .sx-icon')).color;
      const words = getComputedStyle(document.getElementById('db-browser-warning')).color;
      return {warning600, fg, glyph, words};
    }""")
    assert colours["glyph"] == colours["warning600"], colours
    assert colours["words"] == colours["fg"], colours


def test_the_card_is_on_the_database_page_and_not_on_the_engine_page(open_panel):
    page = detail_page(open_panel, engine_up=True, engine_manifest=RELEASE, native_mode="ok")
    wait_for_state(page, "Running")
    assert page.locator("#view-engine-detail #db-browser").count() == 0


def test_copy_database_path_copies_the_path_and_says_so(open_panel):
    page = database_page(open_panel, engine_up=True, storage=his_storage())
    page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
      configurable: true, value: {writeText: async (t) => { window.__copied = t; }}})""")
    # MEASURED ONCE THE CARD IS SETTLED: Copy is drawn only when the path arrives, and
    # the line under it is written by the same read, so a measure taken as the page
    # opens can be of a card still taking shape.
    page.wait_for_selector("#db-browser-copy", state="visible")
    page.wait_for_function(
        "() => document.getElementById('db-browser-result').textContent === '\\u00a0'")
    width_before = page.locator("#db-browser-copy").bounding_box()["width"]
    below = ("() => document.querySelector('#db-browser + .card').getBoundingClientRect().top"
             " - document.getElementById('db-browser').getBoundingClientRect().top")
    below_before = page.evaluate(below)
    page.click("#db-browser-copy")
    page.wait_for_function(
        "() => document.getElementById('db-browser-result').textContent === 'Database path copied.'")
    assert page.evaluate("() => window.__copied") == HIS_PATH
    # THE BUTTON KEEPS ITS LABEL AND ITS WIDTH, and the result line is reserved
    # (&nbsp;), so the card below does not move. Waited for with a bound, not read once.
    assert text_of(page, "#db-browser-copy") == "Copy database path"
    assert page.locator("#db-browser-copy").bounding_box()["width"] == width_before
    try:
        page.wait_for_function(f"(want) => ({below})() === want", arg=below_before,
                               timeout=2_000)
    except Exception:
        raise AssertionError(f"the result moved the card below it: {below_before} px "
                             f"before, {page.evaluate(below)} px after") from None


def test_a_refused_copy_is_said(open_panel):
    page = database_page(open_panel, engine_up=True, storage=his_storage())
    page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {writeText: async () => { throw new DOMException('denied', 'NotAllowedError'); }}})""")
    page.click("#db-browser-copy")
    page.wait_for_function(
        "() => document.getElementById('db-browser-result').textContent.startsWith('Could not copy')")
    assert text_of(page, "#db-browser-result") == \
        "Could not copy. Select the path at the top of this page and copy it."
    page.wait_for_function(TRACED, arg="db-browser-copy-refused")


def test_the_card_waits_for_the_path_and_says_a_failed_ask(open_panel):
    page = open_panel(view="database", engine_up=True, fail_routes=("/api/storage",))
    page.wait_for_function(
        "() => document.getElementById('db-browser-result').textContent.trim().length > 0")
    assert visible(page, "#db-browser")
    assert not visible(page, "#db-browser-copy"), "Copy offered with no path to copy"
    assert visible(page, "#db-browser-download")
    assert text_of(page, "#db-browser-result") == \
        "Could not ask the engine which database is open. Open this page again to retry."


def test_the_card_is_not_drawn_without_an_engine(open_panel):
    page = open_panel(view="database", engine_up=False)
    page.wait_for_timeout(500)
    assert not visible(page, "#db-browser")


#: Every `/api/storage` read fails while `window.__fail` is true.
STORAGE_FAILS = """() => { window.__fail = true; const inner = window.fetch;
  window.fetch = async (url, options = {}) => (window.__fail && String(url).includes('/api/storage'))
    ? Promise.reject(new TypeError('Failed to fetch')) : inner(url, options); }"""


def reopen_database(page) -> None:
    page.click('nav.side-rail button[data-view="run"]')
    page.click('nav.side-rail button[data-view="database"]')


def test_a_failed_read_withdraws_a_path_an_earlier_read_left(open_panel):
    """A good read, then a failed one: Copy goes with the failure, though `state` still
    holds the path the first read left."""
    page = database_page(open_panel, engine_up=True, storage=his_storage())
    assert visible(page, "#db-browser-copy")
    page.evaluate(STORAGE_FAILS)
    reopen_database(page)
    page.wait_for_function(
        "() => document.getElementById('db-browser-result').textContent.startsWith('Could not ask')",
        timeout=10_000)
    assert not visible(page, "#db-browser-copy"), "Copy offered beside the failure"


def test_a_read_that_works_clears_the_failure_an_earlier_one_said(open_panel):
    """A failed read, then a good one: the failure sentence goes, and Copy comes back."""
    page = open_panel(view="database", engine_up=True, storage=his_storage())
    page.evaluate(STORAGE_FAILS)
    reopen_database(page)
    page.wait_for_function(
        "() => document.getElementById('db-browser-result').textContent.startsWith('Could not ask')",
        timeout=10_000)
    page.evaluate("() => { window.__fail = false; }")
    reopen_database(page)
    page.wait_for_function(
        "() => !document.getElementById('db-browser-copy').classList.contains('hidden')",
        timeout=10_000)
    assert text_of(page, "#db-browser-result").strip() == "", (
        "the failure outlived a read that worked")
