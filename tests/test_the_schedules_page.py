"""The panel's Schedules page (#1631, option C, parts 1 and 2), driven in a real browser.

His ruling on #1631: option C as drawn, price sources only, no engine change. Part 1 is
the page itself: the rail button below Jobs, the one read, the banners, the rows (and the
orphan row), the Active switch with its two-read timeout, the ⋮ menu (Edit schedule, View
skipped runs, Remove schedule…), focus after a row leaves, and every "open its schedule"
link landing here. Part 2 is the sheet that creates and edits a schedule, where Settings'
editor was, and Add source's link here in place of its "Schedule" select (his option (c)).
Search, Status and "· N off" are part 3.

The key states are drawn at the panel's three widths, 320, 400 and 480 px. The engine is
`tools/panel_harness.py`'s stub, so a state a live engine cannot produce on demand -- a
write that never answers, a job end whose schedules read fails -- is staged by changing
what the stub answers while the page is open (`ROUTES`, `FAIL`, `BLACKHOLE_ROUTES` are
the stub's own globals).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")
import panel_harness as harness  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.extension

WIDTHS = (320, 400, 480)
TALL = 900
VIEW = "#view-schedules"

# His sources, shaped as `/api/sources` lists them (the real dump behind the mock-up,
# `last_success` in the engine's own shape, app.py `_source_rows`).
def _source(key, url, name, ar, *, active=True, implemented=True, kind=None, last=None):
    return {"source_key": key, "base_url": url, "source_name": name, "source_name_ar": ar,
            "kind": kind, "active": active, "implemented": implemented,
            "family": "salla-html", "observations": 1200 if implemented and not kind else 0,
            "products": 40, "kept_pages": 0, "kept_at": None, "supports_history": False,
            "last_success": None if last is None else {
                "started_at": last, "finished_at": last, "rows_seen": 412,
                "requests_count": 37}}


SOURCES = [
    _source("MADAR", "https://www.madar.com", "Madar", "المدار",
            last="2026-10-09T06:12:40Z"),
    _source("ALSWEED", "https://alsweed.sa", "Alsweed", "السويد", active=False,
            last="2026-10-05T03:52:31Z"),
    _source("ELBUROJ", "https://elburoj.com", "Elburoj", "البروج"),
    _source("ADVANCEDCASTLE", "https://advancedcastle.com", "Advanced Castle",
            "القلعة المتقدمة"),
    _source("AHMEDELSALLAB", "https://www.ahmedelsallab.com", "Ahmed El Sallab",
            "أحمد السلاب", active=False, implemented=False),
    _source("muqawil_org", "https://muqawil.org", "Saudi Contractors Authority", "",
            active=None, kind="directory"),
    _source("oman_tenderboard", "https://etendering.tenderboard.gov.om",
            "Oman Tender Board", "", active=None, kind="directory"),
]
NOTE = ("Schedules run only while the ScrapeX engine is running. Nothing can wake a "
        "sleeping or powered-off machine; a slot missed while it was off follows the "
        "missed-run policy.")
ROW = {"run_mode": "update", "missed_run_policy": "run_when_available",
       "overlap_policy": "skip", "enabled": 1, "last_run_at": None}
PRICE = [
    {**ROW, "schedule_id": 1, "source_key": "MADAR", "frequency": "daily", "run_at": "09:00",
     "timezone": "Asia/Riyadh", "weekday": None, "next_run_at": "2026-10-11T06:00:00Z"},
    {**ROW, "schedule_id": 2, "source_key": "ALSWEED", "frequency": "weekly",
     "run_at": "06:30", "timezone": "Asia/Riyadh", "weekday": 0,
     "next_run_at": "2026-10-12T03:30:00Z"},
    {**ROW, "schedule_id": 3, "source_key": "ELBUROJ", "frequency": "daily", "run_at": "08:30",
     "timezone": "Africa/Cairo", "weekday": None, "next_run_at": "2026-10-11T05:30:00Z",
     "run_mode": "full_rebuild", "missed_run_policy": "skip"},
    # Removed earlier: kept as `manual`, so it has no row.
    {**ROW, "schedule_id": 4, "source_key": "ADVANCEDCASTLE", "frequency": "manual",
     "run_at": "07:45", "timezone": "Asia/Riyadh", "weekday": 3, "next_run_at": None},
]
# A stored schedule whose source left the manifest (#1645 removes AHRAMBC; #1650).
ORPHAN = [{**ROW, "schedule_id": 9, "source_key": "AHRAMBC", "frequency": "daily",
           "run_at": "10:00", "timezone": "Africa/Cairo", "weekday": None,
           "next_run_at": "2026-10-11T07:00:00Z"}]


def sched(rows):
    return {"schedules": copy.deepcopy(rows), "note": NOTE}


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
    """Open the panel at a width and scheme, with his sources and schedules by default."""
    pages = []

    def opener(*, width=400, scheme="light", **stub):
        stub.setdefault("sources", copy.deepcopy(SOURCES))
        stub.setdefault("schedules", sched(PRICE + ORPHAN))
        page_file = harness.build_page(tmp_path, harness.stub(**stub),
                                       name=f"schedules{len(pages)}.html")
        # His display zone is the browser's, so it is pinned: CI runs in UTC and his
        # machine does not, and a Next run asserted in "his zone" must mean one zone.
        page = browser.new_page(viewport={"width": width, "height": TALL},
                                color_scheme=scheme, timezone_id="UTC")
        # A missing control fails in seconds, by name, not after Playwright's 30 s.
        page.set_default_timeout(5_000)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        harness.wait_until_settled(page)
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def show_schedules(page):
    """Press the rail button, and wait for the page's first read to be drawn."""
    page.click("#tab-schedules")
    page.wait_for_selector(VIEW, state="visible")
    drawn(page)


def drawn(page):
    page.wait_for_function("""() => {
        const list = document.getElementById('sched-list');
        if (!list || list.hasAttribute('aria-busy')) return false;
        return /Read at/.test(document.getElementById('sched-count').textContent)
            || document.querySelector('#sched-state > :not([data-role="old"])') !== null;
    }""")


def row(page, key):
    return page.locator(f'{VIEW} .schedule-row[data-sched="{key}"]')


def text(page, selector):
    return (page.text_content(selector) or "").strip()


def writes(page):
    return [w for w in page.evaluate("window.__writes")
            if w["path"].startswith("/api/schedules/")]


def calls(page, path):
    return [c for c in page.evaluate("window.__calls") if c.split("?")[0] == path]


def wait_toast(page, words, timeout=5_000):
    page.wait_for_function("(w) => document.getElementById('toast').textContent === w",
                           arg=words, timeout=timeout)


def answer(page, path, change):
    """Make the stub answer `path` with a changed copy of what it answered before. A
    copy, because the stub hands the page the very objects it holds."""
    page.evaluate("""([path, change]) => {
        const next = JSON.parse(JSON.stringify(ROUTES[path]));
        new Function('body', change)(next);
        ROUTES[path] = next;
    }""", [path, change])


def no_horizontal_scroll(page):
    return page.evaluate("""() => {
        const scroll = document.querySelector('#view-schedules .view-scroll');
        return document.documentElement.scrollWidth <= innerWidth
            && scroll.scrollWidth <= scroll.clientWidth;
    }""")


def load_run_first(page):
    """Run is shown and loaded before the Schedules page is opened: Run does not re-read
    on a later show (`loadRunDestination`), so only a redraw by this page can change
    its chips."""
    page.click('nav.side-rail button[data-view="run"]')
    page.wait_for_function("() => runDestinationLoadedFor === backendGeneration()"
                           " && document.querySelector('#sites [data-sched-link=\"MADAR\"]')")


def chip(page, key):
    return text(page, f'#sites [data-sched-link="{key}"]')


def flip(page, key):
    row(page, key).locator('[data-role="sched-active"]').click()
    page.wait_for_selector("#confirm-veil:not(.hidden)")


def open_menu(page, key):
    row(page, key).locator('[data-role="kebab"]').click()
    page.wait_for_selector(f'{VIEW} .schedule-row[data-sched="{key}"] [role="menu"]:not(.hidden)')


def press_item(page, key, words):
    open_menu(page, key)
    row(page, key).locator('[role="menuitem"]', has_text=words).click()


# ---- the rail ---------------------------------------------------------------------

def test_the_rail_carries_schedules_directly_below_jobs(open_panel):
    page = open_panel()
    tab = page.locator("#tab-schedules")
    assert tab.get_attribute("aria-controls") == "view-schedules"
    assert tab.get_attribute("aria-label") == "Schedules"
    assert tab.locator("use").get_attribute("href") == "#material-schedule"
    order = page.evaluate("""() => [...document.querySelectorAll(
        'nav.side-rail button[data-view]')].map((b) => b.dataset.view)""")
    assert order[order.index("jobs") + 1] == "schedules", order

    show_schedules(page)
    assert tab.get_attribute("aria-current") == "page"
    assert text(page, f"{VIEW} h1") == "Schedules"
    assert text(page, f"{VIEW} .view-heading p") == "When each source runs automatically"
    assert not page.js_errors


# ---- the list ---------------------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_the_list_draws_each_scheduled_price_source_with_its_facts(open_panel, width):
    page = open_panel(width=width)
    show_schedules(page)

    keys = page.evaluate("""() => [...document.querySelectorAll(
        '#view-schedules .schedule-row')].map((r) => r.dataset.sched)""")
    # A removed (manual) schedule, an unbuilt source and a directory have no row; the
    # orphan has its own, last.
    assert keys == ["MADAR", "ALSWEED", "ELBUROJ", "AHRAMBC"], keys
    count = text(page, "#sched-count")
    assert count.startswith("4 schedules · 1 without a source · Read at "), count

    madar = row(page, "MADAR")
    facts = madar.locator(".schedule-facts").inner_text()
    assert "Daily 09:00 · Asia/Riyadh" in facts, facts
    # Next run in the schedule's own zone and clock, then the instant in his zone.
    nxt = madar.locator('[data-fact="next"]').inner_text()
    assert "11 Oct" in nxt and "09:00" in nxt and "UTC" in nxt, nxt
    assert "9 October 2026" in madar.locator('[data-fact="last"]').inner_text()
    switch = madar.locator('[data-role="sched-active"]')
    assert switch.get_attribute("role") == "switch"
    assert switch.get_attribute("aria-checked") == "true"
    assert switch.get_attribute("aria-label") == "Scheduled runs for madar.com"
    assert madar.locator('[data-role="runs"]').get_attribute("aria-label") \
        == "Runs of madar.com on Jobs"
    assert madar.locator('[data-role="kebab"]').get_attribute("aria-label") \
        == "Actions for madar.com"

    alsweed = row(page, "ALSWEED")
    assert alsweed.locator('[data-fact="next"]').inner_text() == "Off"
    assert alsweed.locator('[data-role="sched-active"]').get_attribute("aria-checked") \
        == "false"
    assert "Weekly Monday 06:30 · Asia/Riyadh" in alsweed.inner_text()
    assert row(page, "ELBUROJ").locator('[data-fact="last"]').inner_text() == "None yet"

    orphan = row(page, "AHRAMBC")
    assert orphan.locator('[data-role="sched-active"]').count() == 0
    assert orphan.locator('[data-role="kebab"]').count() == 0
    assert orphan.locator('[data-fact="next"]').inner_text() == "Never"
    assert ("This source is no longer in your sources, so its schedule never runs. "
            "It can't be changed or removed yet.") in orphan.inner_text()

    assert text(page, "#sched-dir-note") == (
        "Directory sources (muqawil.org, etendering.tenderboard.gov.om) can't be "
        "scheduled yet. Run them from the Run page.")
    assert text(page, "#sched-engine-note") == NOTE
    assert page.locator("#sched-create").is_visible()
    assert no_horizontal_scroll(page)
    assert not page.js_errors


def test_next_run_is_read_on_the_schedules_own_clock(open_panel):
    """A schedule's next slot in ITS zone and 24-hour clock (ECMA-402 `timeZone`), from
    the one formatter, so "Daily 09:00 · Asia/Riyadh" reads 09:00 whatever his zone is."""
    page = open_panel()
    wall = "(a) => ScrapeXTime.wallClock(a[0], a[1])"
    assert page.evaluate(wall, ["2026-10-11T06:00:00Z", "Asia/Riyadh"]) == "Sun 11 Oct, 09:00"
    assert page.evaluate(wall, ["2026-10-11T05:30:00Z", "Africa/Cairo"]) == "Sun 11 Oct, 08:30"
    assert page.evaluate(wall, ["2026-10-11T23:30:00Z", "Asia/Riyadh"]) == "Mon 12 Oct, 02:30"
    # A zone the browser does not know draws nothing rather than a wrong clock.
    assert page.evaluate(wall, ["2026-10-11T06:00:00Z", "Mars/Olympus"]) == ""
    assert page.evaluate(wall, ["not an instant", "Asia/Riyadh"]) == ""
    show_schedules(page)
    assert row(page, "MADAR").locator('[data-fact="next"]').inner_text() \
        .startswith("Sun 11 Oct, 09:00")


@pytest.mark.parametrize("width", WIDTHS)
def test_with_no_schedules_the_page_says_so_and_offers_create(open_panel, width):
    page = open_panel(width=width, schedules=sched([PRICE[3]]))
    show_schedules(page)

    card = page.locator('#sched-state [data-role="empty"]')
    assert card.locator("p").all_inner_texts() == [
        "No schedules yet", "Create one to run a source automatically."]
    assert card.locator("button").inner_text() == "Create schedule"
    # The empty card carries Create, and no count stands over nothing.
    assert page.locator("#sched-create").is_hidden()
    assert text(page, "#sched-count") == ""
    assert page.locator("#sched-list").is_hidden()
    assert no_horizontal_scroll(page)
    assert not page.js_errors


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("failing,title", [("/api/schedules", "Unable to read schedules"),
                                           ("/api/sources", "Unable to read sources")])
def test_a_failed_first_read_names_what_failed_and_draws_no_controls(open_panel, width,
                                                                      failing, title):
    page = open_panel(width=width, fail_routes=(failing,))
    show_schedules(page)

    banner = page.locator('#sched-state [data-role="banner"]')
    assert banner.get_attribute("role") == "alert"
    assert "danger" in banner.get_attribute("class")
    assert banner.locator("strong").inner_text() == title
    assert banner.locator("p").inner_text() == "the engine could not do that"
    assert banner.locator("button").inner_text() == "Try again"
    # No read, no controls: nothing to act on.
    assert page.locator("#sched-tools").is_hidden()
    assert page.locator("#sched-list").is_hidden()
    assert page.locator(f"{VIEW} .schedule-row").count() == 0

    # Try again reads again; once the engine answers, the list is drawn.
    before = len(calls(page, "/api/schedules"))
    page.evaluate("FAIL.length = 0")
    banner.locator("button").click()
    page.wait_for_selector(f'{VIEW} .schedule-row[data-sched="MADAR"]')
    assert len(calls(page, "/api/schedules")) == before + 1
    assert page.locator('#sched-state [data-role="banner"]').count() == 0
    assert no_horizontal_scroll(page)
    assert not page.js_errors


@pytest.mark.parametrize("width", WIDTHS)
def test_with_the_engine_down_the_page_offers_to_start_it(open_panel, width):
    page = open_panel(width=width, engine_up=False)
    show_schedules(page)

    banner = page.locator('#sched-state [data-role="banner"]')
    assert banner.locator("strong").inner_text() == "Engine not running"
    assert banner.locator("p").inner_text() == "Start the engine to read schedules."
    assert banner.locator("button").inner_text() == "Start engine"
    assert page.locator("#sched-tools").is_hidden()
    assert no_horizontal_scroll(page)
    assert not page.js_errors


def test_an_engine_without_the_switch_says_so_and_draws_none(open_panel):
    page = open_panel(engine_version="0.4.57",
                      omit_capabilities=("schedule_active_switch", "scheduled_skips"))
    show_schedules(page)

    note = page.locator('#sched-state [data-role="old"]')
    assert note.locator("strong").inner_text() \
        == "No on/off switch on the rows with this engine"
    assert note.locator("p").inner_text() == (
        "This engine is 0.4.57. Turning a schedule on or off from its row needs engine "
        "0.4.60 or newer. Until then, use Enabled in Edit schedule, and Auto on the Run "
        "page.")
    assert page.locator(f'{VIEW} [data-role="sched-active"]').count() == 0
    assert not page.js_errors


def switches(page):
    return page.locator(f'{VIEW} [data-role="sched-active"]')


def old_note(page):
    return page.locator('#sched-state [data-role="old"]')


def engine_lacks_the_switch(page, version):
    """The engine the panel meets after a downgrade: it reports, at `version`, without
    `schedule_active_switch`. Then the panel checks it again, as Check again does."""
    answer(page, "/api/health", f"body.version = {version!r};")
    answer(page, "/api/version", "body.capabilities = body.capabilities.filter("
                                 "(c) => c.key !== 'schedule_active_switch');")
    page.evaluate("updateEngineState()")


def test_an_engine_whose_version_is_unknown_is_not_called_old(open_panel):
    """A version report that times out (its deadline is 2.5 s, the page's reads 5 s)
    proves nothing about the engine: no "needs engine 0.4.60" note, and no switch the
    panel cannot confirm. When a check answers, the rows gain their switches in place."""
    page = open_panel(blackhole_routes=("/api/version",))
    show_schedules(page)
    assert page.evaluate("state.versionStatus") == "timeout"
    assert row(page, "MADAR").count() == 1
    assert old_note(page).count() == 0
    assert switches(page).count() == 0

    page.evaluate("BLACKHOLE_ROUTES.length = 0")
    before = len(calls(page, "/api/schedules"))
    page.evaluate("updateEngineState()")
    page.wait_for_function(f"""() => document.querySelectorAll(
        '{VIEW} [data-role="sched-active"]').length === 3""")
    assert old_note(page).count() == 0
    # Drawn from what the page already held: the engine's answer costs no read.
    assert len(calls(page, "/api/schedules")) == before
    flip(page, "MADAR")
    page.click("#confirm-go")
    wait_toast(page, "Disabled scheduled runs for madar.com")
    assert writes(page)[-1]["body"]["active"] is False
    assert not page.js_errors


def test_an_engine_too_old_to_report_is_known_to_have_no_switch(open_panel):
    """A 404 on /api/version is an engine from before version reporting: that is known,
    so the note is drawn, in the version its health check gave."""
    page = open_panel(engine_version="0.1.9", version_reporting=False)
    show_schedules(page)
    assert page.evaluate("state.versionStatus") == "unsupported"
    assert "This engine is 0.1.9." in old_note(page).inner_text()
    assert switches(page).count() == 0
    assert not page.js_errors


def test_the_switches_and_the_note_follow_the_engine_after_the_page_is_drawn(open_panel):
    """A downgrade takes the switches away and draws the note in this engine's version;
    the next engine's version rewrites it; an upgrade takes it away and brings the
    switches back. Focus on a switch that leaves stays in its row."""
    page = open_panel()
    show_schedules(page)
    full = page.evaluate("JSON.parse(JSON.stringify(ROUTES['/api/version']))")
    assert switches(page).count() == 3
    row(page, "MADAR").locator('[data-role="sched-active"]').focus()

    engine_lacks_the_switch(page, "0.4.58")
    old_note(page).wait_for()
    assert switches(page).count() == 0
    assert "This engine is 0.4.58." in old_note(page).inner_text()
    assert page.evaluate("document.activeElement.dataset.role") == "runs"
    assert page.evaluate("document.activeElement.closest('.schedule-row').dataset.sched") \
        == "MADAR"
    # Paused needs an engine without the switch; an Off source still reads Off.
    assert row(page, "ALSWEED").locator('[data-fact="next"]').inner_text() == "Off"

    engine_lacks_the_switch(page, "0.4.59")
    page.wait_for_function("""() => document.querySelector('#sched-state [data-role="old"]')
        .textContent.includes('This engine is 0.4.59.')""")
    assert old_note(page).count() == 1

    page.evaluate("(report) => { ROUTES['/api/version'] = report; }", full)
    page.evaluate("updateEngineState()")
    old_note(page).wait_for(state="detached")
    assert switches(page).count() == 3
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-checked") == "true"
    assert writes(page) == []
    assert not page.js_errors


def test_a_switch_confirmed_after_the_engine_lost_it_sends_nothing(open_panel):
    """The question was asked while the engine had the switch, and answered after a
    check found it gone: that engine would save the schedule, ignore `active` and answer
    200, so a press would toast a change that never happened."""
    page = open_panel()
    show_schedules(page)
    flip(page, "MADAR")
    engine_lacks_the_switch(page, "0.4.58")
    old_note(page).wait_for()
    page.click("#confirm-go")
    page.wait_for_selector("#confirm-veil.hidden", state="attached")
    page.wait_for_timeout(300)
    assert writes(page) == []
    assert "scheduled runs" not in text(page, "#toast")
    assert not page.js_errors


# ---- the menu -----------------------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_the_menu_holds_edit_skipped_runs_and_remove(open_panel, width):
    page = open_panel(width=width)
    show_schedules(page)
    kebab = row(page, "MADAR").locator('[data-role="kebab"]')
    kebab.focus()
    page.keyboard.press("ArrowDown")

    menu = row(page, "MADAR").locator('[role="menu"]')
    assert menu.is_visible()
    assert kebab.get_attribute("aria-expanded") == "true"
    items = menu.locator('[role="menuitem"]')
    assert items.all_inner_texts() == ["Edit schedule", "View skipped runs",
                                       "Remove schedule…"]
    assert menu.locator('[role="separator"]').count() == 1
    assert "is-destructive" in items.nth(2).get_attribute("class")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Edit schedule"
    page.keyboard.press("End")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Remove schedule…"
    page.keyboard.press("Escape")
    assert menu.is_hidden()
    assert page.evaluate("document.activeElement.dataset.role") == "kebab"
    # ArrowUp opens it on its last item.
    page.keyboard.press("ArrowUp")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Remove schedule…"
    # A press outside closes it, applying nothing.
    page.mouse.click(5, 5)
    assert menu.is_hidden()
    assert no_horizontal_scroll(page)
    assert writes(page) == []
    assert not page.js_errors


def test_view_skipped_runs_is_offered_only_by_an_engine_that_records_skips(open_panel):
    page = open_panel(omit_capabilities=("scheduled_skips",))
    show_schedules(page)
    open_menu(page, "MADAR")
    assert row(page, "MADAR").locator('[role="menuitem"]').all_inner_texts() == [
        "Edit schedule", "Remove schedule…"]


# ---- each control's route -----------------------------------------------------------

def test_the_rows_identity_opens_jobs_narrowed_to_the_source(open_panel):
    page = open_panel()
    show_schedules(page)
    row(page, "MADAR").locator('[data-role="runs"]').click()
    page.wait_for_selector("#view-jobs", state="visible")
    assert page.input_value("#jobs-search") == "MADAR"
    assert text(page, "#jobs-status-label") == "Status"
    assert not page.js_errors


def test_view_skipped_runs_opens_jobs_narrowed_to_its_skips(open_panel):
    page = open_panel()
    show_schedules(page)
    press_item(page, "MADAR", "View skipped runs")
    page.wait_for_selector("#view-jobs", state="visible")
    assert page.input_value("#jobs-search") == "MADAR"
    assert text(page, "#jobs-status-label") == "Status: 1"
    assert page.evaluate("[...jobsPage.statuses]") == ["skipped"]


# ---- the sheet: Create and Edit (#1631 part 2) --------------------------------------
# Supabase's Sheet laid out as Studio's CreateCronJobSheet, where Settings' editor was.

SIKA = _source("SIKAEGSHOP", "https://sikaegshop.com", "Sika Egypt", "سيكا مصر",
               active=False)
SHEET = "#sched-sheet"
SHEET_VEIL = "#sched-sheet-veil"


def with_sika():
    return [*copy.deepcopy(SOURCES), copy.deepcopy(SIKA)]


def sheet_settled(page):
    """Open, and done sliding in: a box read, or a press aimed at the veil, during the
    slide reads the sheet on its way."""
    page.locator(SHEET).wait_for()
    page.wait_for_function("""() => document.getElementById('sched-sheet').getAnimations()
        .every((a) => a.playState !== 'running')""")


def open_create(page, via="#sched-create"):
    page.click(via)
    sheet_settled(page)


def open_edit(page, key):
    press_item(page, key, "Edit schedule")
    sheet_settled(page)


def domain_of(page, identity):
    """The domain an identity names, read whole (it breaks only after its dots)."""
    return "".join(page.locator(f"{identity} .source-identity-domain").inner_text().split())


def sheet_value(page, name):
    return page.input_value(f"#sched-sheet-{name}")


def sheet_closed(page):
    page.locator(SHEET_VEIL).wait_for(state="hidden")


def focus_is(page):
    return page.evaluate("""() => { const a = document.activeElement;
        return a.id || a.dataset.role || a.tagName; }""")


def holds_engine(page, key, change):
    """The engine holds what the save sent: the next read of /api/schedules says so."""
    answer(page, "/api/schedules", f"Object.assign(body.schedules.find((s) => s.source_key "
                                   f"=== '{key}'), {change});")


@pytest.mark.parametrize("width", WIDTHS)
def test_create_opens_a_sheet_beside_the_rail_with_the_panel_behind_it_inert(open_panel,
                                                                            width):
    page = open_panel(width=width, sources=with_sika())
    show_schedules(page)
    open_create(page)
    sheet = page.locator(SHEET)
    assert (sheet.get_attribute("role"), sheet.get_attribute("aria-modal")) == ("dialog", "true")
    assert text(page, "#sched-sheet-title") == "Create a schedule"
    assert sheet.get_attribute("aria-labelledby") == "sched-sheet-title"
    # Modal: what is behind it cannot be reached, and focus starts on its first field.
    assert page.evaluate("[document.querySelector('main').inert,"
                         " document.querySelector('nav.side-rail').inert]") == [True, True]
    assert focus_is(page) == "sched-sheet-source"
    # Beside the rail, never over it; the veil covers the rail.
    sheet_box, rail, veil = (page.locator(s).bounding_box()
                             for s in (SHEET, "nav.side-rail", SHEET_VEIL))
    assert sheet_box["x"] == 0 and abs(sheet_box["x"] + sheet_box["width"] - rail["x"]) < 1
    assert veil["x"] + veil["width"] == width
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # At panel widths the primary sits above Cancel (sheet.tsx@86c813ec:214).
    save, cancel = (page.locator(s).bounding_box()
                    for s in ("#sched-sheet-save", "#sched-sheet-cancel"))
    assert save["y"] < cancel["y"]
    assert text(page, "#sched-sheet-save") == "Create schedule"
    assert not page.js_errors


def test_create_offers_only_the_sources_without_a_schedule(open_panel):
    page = open_panel(sources=with_sika())
    show_schedules(page)
    open_create(page)
    options = page.eval_on_selector_all(
        "#sched-sheet-source option", "os => os.map((o) => [o.value, o.textContent])")
    # A scheduled, an unbuilt and a directory source are not offered; a removed one is.
    assert options == [["ADVANCEDCASTLE", "advancedcastle.com"],
                       ["SIKAEGSHOP", "sikaegshop.com"]]
    assert text(page, "#sched-sheet-source-hint") == "Sources that have no schedule yet."
    assert domain_of(page, "#sched-sheet-source-identity") == "advancedcastle.com"
    assert text(page, "#sched-sheet-source-identity .source-identity-name") == "القلعة المتقدمة"
    assert not page.js_errors


def test_create_fills_a_removed_schedule_back_in_and_starts_a_new_one_daily(open_panel):
    page = open_panel(sources=with_sika())
    show_schedules(page)
    open_create(page)
    # Removed earlier as `manual`, its day kept: it reopens as Weekly Thursday.
    page.select_option("#sched-sheet-source", "ADVANCEDCASTLE")
    assert [sheet_value(page, n) for n in ("frequency", "weekday", "time", "zone")] == [
        "weekly", "3", "07:45", "Asia/Riyadh"]
    assert page.locator("#sched-sheet-weekday").is_visible()
    assert text(page, "#sched-sheet-filled") == "Filled in from its removed schedule."
    assert page.locator("#sched-sheet-filled").is_visible()
    # Never scheduled: Daily at 09:00 in his browser's zone.
    page.select_option("#sched-sheet-source", "SIKAEGSHOP")
    assert [sheet_value(page, n) for n in ("frequency", "time", "zone", "mode", "missed")] \
        == ["daily", "09:00", "UTC", "update", "run_when_available"]
    assert page.locator("#sched-sheet-weekday").is_hidden()
    assert page.locator("#sched-sheet-filled").is_hidden()
    assert domain_of(page, "#sched-sheet-source-identity") == "sikaegshop.com"
    # No overlap choice: a busy slot is skipped and listed, and the sheet says so (#1596).
    assert page.locator(f"{SHEET} select").count() == 5
    assert text(page, "#sched-sheet-skip-note") == (
        "If this site's previous run is still going, ScrapeX skips the slot and lists it on "
        "the Jobs page.")
    # Without the switch only: on this engine `active` is the switch's, never a box here.
    assert page.locator("#sched-sheet-enabled").is_hidden()
    assert not page.js_errors


def test_create_says_it_turns_runs_on_and_saves_the_schedule_with_active(open_panel):
    page = open_panel(sources=with_sika())
    show_schedules(page)
    open_create(page)
    page.select_option("#sched-sheet-source", "SIKAEGSHOP")
    assert text(page, "#sched-sheet-runs-note") == (
        "Auto is off for sikaegshop.com. Creating this schedule turns it on, and runs start "
        "from the next slot.")
    page.select_option("#sched-sheet-source", "ADVANCEDCASTLE")
    assert text(page, "#sched-sheet-runs-note") == "Scheduled runs start from the next slot."
    holds_engine(page, "ADVANCEDCASTLE", "{frequency: 'weekly'}")
    sources = len(calls(page, "/api/sources"))
    page.click("#sched-sheet-save")
    wait_toast(page, "Created the schedule for advancedcastle.com")
    assert writes(page) == [{"path": "/api/schedules/ADVANCEDCASTLE", "method": "POST",
                             "body": {"frequency": "weekly", "run_at": "07:45",
                                      "timezone": "Asia/Riyadh", "weekday": 3,
                                      "run_mode": "update",
                                      "missed_run_policy": "run_when_available",
                                      "overlap_policy": "skip", "enabled": True,
                                      "active": True}}]
    sheet_closed(page)
    row(page, "ADVANCEDCASTLE").wait_for()
    # It changed the source's `active` too, which /api/sources holds: read again.
    page.wait_for_function("(n) => window.__calls.filter((c) => c === '/api/sources')"
                           ".length > n", arg=sources)
    assert focus_is(page) == "sched-create"
    assert page.evaluate("document.querySelector('main').inert") is False
    assert not page.js_errors


def test_edit_opens_with_the_stored_schedule_and_saves_it_without_the_switch(open_panel):
    page = open_panel()
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    assert text(page, "#sched-sheet-title") == "Edit schedule"
    assert domain_of(page, "#sched-sheet-identity") == "elburoj.com"
    assert page.locator("#sched-sheet-source").is_hidden()
    assert [sheet_value(page, n) for n in ("frequency", "time", "zone", "mode", "missed")] \
        == ["daily", "08:30", "Africa/Cairo", "full_rebuild", "skip"]
    assert focus_is(page) == "sched-sheet-frequency"
    assert text(page, "#sched-sheet-save") == "Save schedule"
    assert text(page, "#sched-sheet-runs-note") == ""
    page.fill("#sched-sheet-time", "10:00")
    reads = len(page.evaluate("window.__calls"))
    page.click("#sched-sheet-save")
    wait_toast(page, "Saved the schedule for elburoj.com")
    # The schedule as edited, its stored `enabled`, and no `active`: the switch alone
    # decides that (#1630 review E1).
    assert writes(page)[-1]["body"] == {
        "frequency": "daily", "run_at": "10:00", "timezone": "Africa/Cairo",
        "run_mode": "full_rebuild", "missed_run_policy": "skip", "overlap_policy": "skip",
        "enabled": True}
    sheet_closed(page)
    assert "Daily 10:00" in row(page, "ELBUROJ").locator(".schedule-facts").inner_text()
    # Edit reads nothing more: the row and Run's cards take the Map just written.
    assert [c for c in page.evaluate("window.__calls")[reads:]
            if c.split("?")[0] in ("/api/schedules", "/api/sources")] == []
    assert focus_is(page) == "kebab"
    assert page.evaluate("document.activeElement.closest('.schedule-row').dataset.sched") \
        == "ELBUROJ"
    assert not page.js_errors


def test_the_sheet_asks_before_it_drops_what_he_entered(open_panel):
    page = open_panel()
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    # Nothing entered: Escape closes it at once, and focus goes back to ⋮.
    page.keyboard.press("Escape")
    sheet_closed(page)
    assert focus_is(page) == "kebab"
    for close in ("Escape", "veil", "#sched-sheet-close", "#sched-sheet-cancel"):
        open_edit(page, "ELBUROJ")
        page.fill("#sched-sheet-time", "10:00")
        if close == "Escape":
            page.keyboard.press("Escape")
        elif close == "veil":
            rail = page.locator("nav.side-rail").bounding_box()
            page.mouse.click(rail["x"] + rail["width"] / 2, 200)
        else:
            page.click(close)
        page.wait_for_selector("#confirm-veil:not(.hidden)")
        assert (text(page, "#confirm-title"), text(page, "#confirm-copy")) == (
            "Discard changes?", "Discarding loses what you entered in this sheet."), close
        assert (text(page, "#confirm-keep"), text(page, "#confirm-go")) == (
            "Keep editing", "Discard changes")
        assert page.get_attribute("#confirm-go", "class") == "danger"
        page.click("#confirm-keep")
        assert page.locator(SHEET).is_visible() and sheet_value(page, "time") == "10:00"
        assert page.evaluate("document.getElementById('sched-sheet')"
                             ".contains(document.activeElement)")
        page.keyboard.press("Escape")
        page.wait_for_selector("#confirm-veil:not(.hidden)")
        page.click("#confirm-go")
        sheet_closed(page)
        assert focus_is(page) == "kebab", close
    # A press on its own labels never closes it.
    open_edit(page, "ELBUROJ")
    page.click('label[for="sched-sheet-time"]')
    page.click("#sched-sheet-title")
    assert page.locator(SHEET).is_visible()
    assert writes(page) == []
    assert not page.js_errors


def test_tab_stays_inside_the_sheet(open_panel):
    page = open_panel(sources=with_sika())
    show_schedules(page)
    open_create(page)
    inside = "document.getElementById('sched-sheet').contains(document.activeElement)"
    for key in ["Tab"] * 14 + ["Shift+Tab"] * 14:
        page.keyboard.press(key)
        assert page.evaluate(inside), key
    assert not page.js_errors


def test_a_refused_save_says_why_above_the_buttons_and_keeps_the_sheet(open_panel):
    page = open_panel(sources=with_sika(), fail_routes=("/api/schedules/ADVANCEDCASTLE",))
    show_schedules(page)
    open_create(page)
    page.click("#sched-sheet-save")
    reason = page.locator("#sched-sheet-reason")
    reason.wait_for()
    assert reason.inner_text() == "Unable to save: the engine could not do that"
    # In the footer, above the buttons, so a short panel shows it (round-2 N-S8).
    assert page.evaluate("document.getElementById('sched-sheet-reason')"
                         ".closest('.sheet-footer') !== null")
    assert reason.bounding_box()["y"] < page.locator("#sched-sheet-save").bounding_box()["y"]
    assert page.locator(SHEET).is_visible()
    assert text(page, "#sched-sheet-save") == "Create schedule"
    assert page.get_attribute("#sched-sheet-cancel", "aria-disabled") is None
    # A reason is about the source it was said for (round-3 O4).
    page.select_option("#sched-sheet-source", "SIKAEGSHOP")
    assert reason.is_hidden()
    assert not page.js_errors


def test_a_read_that_left_before_an_edit_does_not_undo_it(open_panel):
    """A tick's read, held by a slow engine, left before the Edit was answered and lands
    after it: the edit stands, as a Remove does."""
    page = open_panel()
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    page.fill("#sched-sheet-time", "10:00")
    hold_next_read(page, "/api/schedules", 1_000)
    page.evaluate("() => { window.__tick = loadSchedulesPage({ quiet: true }); }")
    page.click("#sched-sheet-save")
    wait_toast(page, "Saved the schedule for elburoj.com")
    page.evaluate("window.__tick")
    assert "Daily 10:00" in row(page, "ELBUROJ").locator(".schedule-facts").inner_text()
    assert not page.js_errors


def test_the_sheet_names_a_long_site_in_full_at_320(open_panel):
    """A row's names ellipsize, as Jobs' do; the sheet that edits one shows every word."""
    long_names = _source("LONG_AR", "https://very-long-subdomain.example-store-name.com.sa",
                         "A Very Long English Store Name For Building Materials",
                         "متجر طويل جدا لمواد البناء والتشطيبات والأدوات")
    long_row = {**ROW, "schedule_id": 5, "source_key": "LONG_AR", "frequency": "daily",
                "run_at": "09:00", "timezone": "Asia/Riyadh", "weekday": None,
                "next_run_at": "2026-10-11T06:00:00Z"}
    page = open_panel(width=320, sources=[*copy.deepcopy(SOURCES), long_names],
                      schedules=sched([*PRICE, long_row]))
    show_schedules(page)
    open_edit(page, "LONG_AR")
    cut = page.evaluate("""() => [...document.querySelectorAll('#sched-sheet-identity *')]
        .filter((el) => el.children.length === 0 && el.textContent.trim()
                && el.scrollWidth > el.clientWidth + 1)
        .map((el) => el.textContent.trim())""")
    assert cut == [], cut
    shown = page.locator("#sched-sheet-identity").inner_text()
    assert "Building Materials" in shown and "والأدوات" in shown, shown
    # Each name on lines of its own, never two narrow columns side by side.
    english, arabic = (page.locator(f"#sched-sheet-identity {s}").bounding_box()
                       for s in (".source-identity-name-en", ".source-identity-name"))
    assert arabic["y"] >= english["y"] + english["height"] - 1, (english, arabic)
    assert page.locator("#sched-sheet-identity .source-identity-separator").is_hidden()
    assert not page.js_errors


def test_a_save_in_flight_holds_the_sheet_and_one_read_finds_it_saved(open_panel):
    page = open_panel(sources=with_sika(), blackhole_routes=("/api/schedules/ADVANCEDCASTLE",))
    show_schedules(page)
    open_create(page)
    page.click("#sched-sheet-save")
    assert text(page, "#sched-sheet-save") == "Creating schedule…"
    for held in ("#sched-sheet-save", "#sched-sheet-cancel", "#sched-sheet-close"):
        assert page.get_attribute(held, "aria-disabled") == "true", held
    page.keyboard.press("Escape")
    page.click("#sched-sheet-cancel", force=True)
    assert page.locator("#confirm-veil").is_hidden() and page.locator(SHEET).is_visible()
    # The engine commits while the panel waits; the one read after the timeout finds it.
    holds_engine(page, "ADVANCEDCASTLE", "{frequency: 'weekly'}")
    wait_toast(page, "Created the schedule for advancedcastle.com", timeout=9_000)
    sheet_closed(page)
    row(page, "ADVANCEDCASTLE").wait_for()
    assert len(writes(page)) == 1
    assert not page.js_errors


def test_a_save_never_answered_says_it_is_not_saved_yet(open_panel):
    page = open_panel(blackhole_routes=("/api/schedules/ELBUROJ",))
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    page.fill("#sched-sheet-time", "10:00")
    page.click("#sched-sheet-save")
    assert text(page, "#sched-sheet-save") == "Saving schedule…"
    page.wait_for_function("""() => document.getElementById('sched-sheet-reason')
        .textContent.startsWith('No answer from the engine')""", timeout=9_000)
    words = text(page, "#sched-sheet-reason")
    assert words.startswith("No answer from the engine, and the schedule is not saved yet "
                            "(checked at "), words
    assert words.endswith("). Press Save schedule to try again."), words
    assert text(page, "#sched-sheet-save") == "Save schedule"
    assert page.get_attribute("#sched-sheet-cancel", "aria-disabled") is None
    assert page.locator(SHEET).is_visible()
    assert not page.js_errors


def test_a_save_whose_read_fails_after_a_timeout_says_so(open_panel):
    page = open_panel(blackhole_routes=("/api/schedules/ELBUROJ",))
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    page.click("#sched-sheet-save")
    page.evaluate("FAIL.push('/api/schedules')")   # the read after the timeout fails
    page.wait_for_function("""() => document.getElementById('sched-sheet-reason')
        .textContent.startsWith('No answer from the engine')""", timeout=9_000)
    assert text(page, "#sched-sheet-reason") == (
        "No answer from the engine in 5 s, and it could not be read again. Press Save "
        "schedule to try again.")
    assert not page.js_errors


def test_at_the_limit_create_waits_and_says_why(open_panel):
    every = [dict(s, frequency="daily") if s["source_key"] == "ADVANCEDCASTLE" else s
             for s in PRICE]
    page = open_panel(schedules=sched(every + ORPHAN))
    show_schedules(page)
    create = page.locator("#sched-create")
    assert create.get_attribute("aria-disabled") == "true"
    assert " ".join(text(page, "#sched-limit").split()) == (
        "Every price source that can run has a schedule. Add a source in Library to "
        "schedule another.")
    create.click(force=True)
    assert page.locator(SHEET_VEIL).is_hidden()
    assert not page.js_errors


@pytest.mark.parametrize("where", ["header", "empty"])
def test_create_is_pressed_from_the_header_or_the_empty_card(open_panel, where):
    page = open_panel(sources=with_sika(),
                      schedules=sched(PRICE) if where == "header" else sched([]))
    show_schedules(page)
    via = "#sched-create" if where == "header" else '#sched-state [data-role="empty"] button'
    open_create(page, via)
    assert text(page, "#sched-sheet-title") == "Create a schedule"
    page.keyboard.press("Escape")
    sheet_closed(page)
    assert page.locator(via).evaluate("(el) => el === document.activeElement")
    assert not page.js_errors


def test_a_link_to_an_unscheduled_source_opens_create_with_it_picked(open_panel):
    page = open_panel(sources=with_sika())
    page.evaluate("openScheduleRow('SIKAEGSHOP')")
    sheet_settled(page)
    assert text(page, "#sched-sheet-title") == "Create a schedule"
    assert sheet_value(page, "source") == "SIKAEGSHOP"
    assert not page.js_errors


def test_a_link_answered_after_he_moved_on_opens_nothing_there(open_panel):
    """The page's read was out when he pressed Run's chip for an unscheduled source, and he
    moved to Data before it landed: the sheet opens on the Schedules page only, never over
    the page he went to (#1746 review A1)."""
    page = open_panel(sources=with_sika())
    load_run_first(page)
    hold_next_read(page, "/api/schedules", 1_500)
    page.click('#sites [data-sched-link="SIKAEGSHOP"]')
    page.click('nav.side-rail button[data-view="data"]')
    page.evaluate("schedulesPage.loading")
    page.evaluate("new Promise((resolve) => setTimeout(resolve, 0))")
    assert page.evaluate("currentViewName()") == "data"
    assert page.locator(SHEET_VEIL).is_hidden()
    assert page.evaluate("document.querySelector('main').inert") is False
    assert not page.js_errors


def test_an_engine_without_the_switch_edits_enabled_and_hears_what_a_slot_does(open_panel):
    queued = [dict(s, overlap_policy="queue") if s["source_key"] == "ELBUROJ" else s
              for s in PRICE]
    page = open_panel(sources=with_sika(), schedules=sched(queued + ORPHAN), **OLD_ENGINE)
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    enabled = page.locator("#sched-sheet-enabled")
    assert enabled.is_visible() and enabled.is_checked()
    assert text(page, "#sched-sheet-skip-note") == (
        "This engine still starts a second run if this site's previous run is still going. "
        "Save this schedule to skip the slot instead, and update the engine to see skipped "
        "slots on the Jobs page.")
    enabled.uncheck()
    page.click("#sched-sheet-save")
    wait_toast(page, "Saved the schedule for elburoj.com")
    body = writes(page)[-1]["body"]
    assert body["enabled"] is False and "active" not in body, body
    # Create there sends no `active`, which that engine ignores, and says so.
    open_create(page)
    page.select_option("#sched-sheet-source", "SIKAEGSHOP")
    assert text(page, "#sched-sheet-runs-note") == (
        "Auto is off for this site, so this will not fire.")
    page.click("#sched-sheet-save")
    wait_toast(page, "Created the schedule for sikaegshop.com")
    assert "active" not in writes(page)[-1]["body"]
    assert not page.js_errors


@pytest.mark.parametrize("policy", ["queue", "skip"])
def test_an_engine_known_without_skips_reads_the_stored_policy(open_panel, policy):
    """#1620 review S9: an engine that writes no skip row is not promised the Jobs page,
    and still reads the stored policy; `queue` starts a second run there."""
    rows = [dict(s, overlap_policy=policy) if s["source_key"] == "ELBUROJ" else s
            for s in PRICE]
    page = open_panel(schedules=sched(rows), engine_version="0.4.57",
                      omit_capabilities=("scheduled_skips",))
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    note = text(page, "#sched-sheet-skip-note")
    assert "lists it on the Jobs page" not in note and "update the engine" in note.lower()
    assert ("still starts a second run" in note) == (policy == "queue"), note


def test_a_failed_version_report_is_promised_nothing_about_a_busy_slot(open_panel):
    page = open_panel(fail_routes=("/api/version",))
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    assert page.locator("#sched-sheet-skip-note").is_hidden()
    assert text(page, "#sched-sheet-skip-note") == ""


def test_a_panel_that_cannot_read_its_own_version_is_not_told_to_update_the_engine(
        open_panel):
    """The line asks the ENGINE's report, not `capabilityRefusal`, which also refuses when
    Chrome did not say this extension's version -- a fault no engine update fixes."""
    page = open_panel(extension_version="")
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    note = text(page, "#sched-sheet-skip-note")
    assert "lists it on the Jobs page" in note and "update the engine" not in note.lower()


def test_settings_holds_no_schedules_editor_any_more(open_panel):
    """One feature in one place (#1631): Settings' editor is gone, and Settings reads no
    schedules."""
    page = open_panel()
    before = len(calls(page, "/api/schedules"))
    page.click('nav.side-rail button[data-view="settings"]')
    page.wait_for_selector("#view-settings", state="visible")
    assert page.locator('[data-sect="s-sched"], #schedules, #sched-note').count() == 0
    assert page.evaluate("[typeof openScheduleEditor, typeof loadSchedules]") == [
        "undefined", "undefined"]
    assert len(calls(page, "/api/schedules")) == before
    assert not page.js_errors


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("state", ["create", "edit", "refused", "old-engine"])
def test_every_word_in_the_sheet_reads_at_4_5_to_1(open_panel, state, scheme):
    """WCAG 2.2 SC 1.4.3 in the sheet, in both themes: it types no colour."""
    stub = {"refused": {"fail_routes": ("/api/schedules/ADVANCEDCASTLE",)},
            "old-engine": OLD_ENGINE}.get(state, {})
    page = open_panel(scheme=scheme, sources=with_sika(), **stub)
    show_schedules(page)
    if state == "edit":
        open_edit(page, "ELBUROJ")
    else:
        open_create(page)
    if state == "refused":
        page.click("#sched-sheet-save")
        page.locator("#sched-sheet-reason").wait_for()
    found = page.evaluate(CONTRAST_JS.replace("getElementById('view-schedules')",
                                              "getElementById('sched-sheet')"))
    assert found, "no text was measured"
    low = [(f["text"], round(f["ratio"], 2)) for f in found if f["ratio"] < 4.5]
    assert low == [], low


# ---- the switch ---------------------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_the_switch_asks_then_saves_active_with_the_stored_schedule(open_panel, width):
    page = open_panel(width=width)
    show_schedules(page)
    flip(page, "MADAR")
    assert text(page, "#confirm-title") == "Disable scheduled runs"
    assert text(page, "#confirm-copy") == (
        "Disable scheduled runs for madar.com? Its schedule is kept and stops firing "
        "until you enable it. Manual runs still work.")
    assert (text(page, "#confirm-keep"), text(page, "#confirm-go")) == ("Cancel", "Disable")
    reads = len(calls(page, "/api/sources"))
    page.click("#confirm-go")
    wait_toast(page, "Disabled scheduled runs for madar.com")

    sent = writes(page)
    assert [w["path"] for w in sent] == ["/api/schedules/MADAR"], sent
    assert sent[0]["body"] == {
        "frequency": "daily", "run_at": "09:00", "timezone": "Asia/Riyadh",
        "weekday": None, "run_mode": "update", "missed_run_policy": "run_when_available",
        "overlap_policy": "skip", "active": False}
    madar = row(page, "MADAR")
    assert madar.locator('[data-role="sched-active"]').get_attribute("aria-checked") \
        == "false"
    assert madar.locator('[data-fact="next"]').inner_text() == "Off"
    # The source's `active` is what the engine now holds: read again, with sources.
    page.wait_for_function("(n) => window.__calls.filter((c) => c === '/api/sources')"
                           ".length > n", arg=reads)
    assert no_horizontal_scroll(page)
    assert not page.js_errors


def test_enabling_says_when_it_runs_and_cancel_changes_nothing(open_panel):
    page = open_panel()
    show_schedules(page)
    flip(page, "ALSWEED")
    assert text(page, "#confirm-title") == "Enable scheduled runs"
    assert text(page, "#confirm-copy") == (
        "Enable scheduled runs for alsweed.sa? It runs weekly Monday 06:30 from the "
        "next slot.")
    page.click("#confirm-keep")
    assert writes(page) == []
    assert row(page, "ALSWEED").locator('[data-role="sched-active"]') \
        .get_attribute("aria-checked") == "false"
    assert page.evaluate("document.activeElement.dataset.role") == "sched-active"


def test_a_refused_switch_says_why_on_its_row(open_panel):
    page = open_panel(fail_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    flip(page, "MADAR")
    page.click("#confirm-go")
    wait_toast(page, "Unable to change scheduled runs for madar.com: "
                     "the engine could not do that")
    status = row(page, "MADAR").locator('[data-role="status"]')
    assert status.inner_text() == "Unable to save: the engine could not do that"
    assert "err" in status.get_attribute("class")
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-checked") == "true"
    # The next good read clears it.
    page.evaluate("FAIL.length = 0")
    page.evaluate("loadSchedulesPage({quiet: true})")
    page.wait_for_function("""() => document.querySelector(
        '#view-schedules .schedule-row[data-sched="MADAR"] [data-role="status"]')
        .textContent === ''""")


def test_a_switch_with_no_answer_reads_again_and_finds_it_saved(open_panel):
    """The panel stops waiting at 5 s; the engine may still commit. A timeout is not a
    refusal: the row reads again and says what the engine holds."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    flip(page, "MADAR")
    page.click("#confirm-go")
    madar = row(page, "MADAR")
    switch = madar.locator('[data-role="sched-active"]')
    page.wait_for_function("""() => document.querySelector(
        '#view-schedules .schedule-row[data-sched="MADAR"] [data-role="status"]')
        .textContent === 'Saving…'""")
    assert switch.get_attribute("aria-busy") == "true"
    assert switch.get_attribute("aria-disabled") == "true"
    assert madar.locator('[data-role="kebab"]').get_attribute("aria-disabled") == "true"
    # The engine commits while the panel waits.
    answer(page, "/api/sources",
           "body.sources.find((s) => s.source_key === 'MADAR').active = false;")
    wait_toast(page, "Disabled scheduled runs for madar.com", timeout=9_000)
    assert madar.locator('[data-role="status"]').inner_text() \
        == "Scheduled runs are off for madar.com."
    assert switch.get_attribute("aria-checked") == "false"
    assert switch.get_attribute("aria-busy") is None
    assert switch.get_attribute("aria-disabled") is None
    assert not page.js_errors


def test_a_switch_never_saved_says_so_after_the_engines_own_wait(open_panel):
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    flip(page, "MADAR")
    page.click("#confirm-go")
    status = row(page, "MADAR").locator('[data-role="status"]')
    page.wait_for_function("""() => document.querySelector(
        '#view-schedules .schedule-row[data-sched="MADAR"] [data-role="status"]')
        .textContent.startsWith('No answer from the engine in 5 s')""", timeout=9_000)
    assert status.inner_text() == (
        "No answer from the engine in 5 s, and scheduled runs are not off yet. The engine "
        "can still save it for a few seconds; this row checks again then.")
    # Writes stay held while the engine may still commit.
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-disabled") == "true"
    page.wait_for_function("""() => document.querySelector(
        '#view-schedules .schedule-row[data-sched="MADAR"] [data-role="status"]')
        .textContent.startsWith('No answer from the engine, and')""", timeout=12_000)
    words = status.inner_text()
    assert words.startswith("No answer from the engine, and the change is not saved yet "
                            "(checked at "), words
    assert words.endswith("). Press the switch to try again."), words
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-disabled") is None
    assert not page.js_errors


# ---- Remove -------------------------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_remove_asks_once_then_saves_manual_and_the_row_leaves(open_panel, width):
    page = open_panel(width=width)
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.wait_for_selector("#confirm-veil:not(.hidden)")
    assert text(page, "#confirm-title") == "Remove schedule"
    assert text(page, "#confirm-copy") == (
        "Remove the schedule for madar.com? It stops running automatically. Its past "
        "runs stay on the Jobs page, and manual runs still work.")
    assert (text(page, "#confirm-keep"), text(page, "#confirm-go")) == (
        "Cancel", "Remove schedule")
    assert page.get_attribute("#confirm-go", "class") == "danger"
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")

    sent = writes(page)
    assert [w["path"] for w in sent] == ["/api/schedules/MADAR"]
    # The route has no delete: a removed schedule is `manual`, its time and zone kept.
    assert sent[0]["body"] == {
        "frequency": "manual", "run_at": "09:00", "timezone": "Asia/Riyadh",
        "weekday": None, "run_mode": "update", "missed_run_policy": "run_when_available",
        "overlap_policy": "skip", "enabled": True}
    page.wait_for_selector(f'{VIEW} .schedule-row[data-sched="MADAR"]', state="detached")
    assert text(page, "#sched-count").startswith("3 schedules · 1 without a source")
    assert no_horizontal_scroll(page)
    assert not page.js_errors


def test_a_refused_remove_keeps_the_row_and_says_why(open_panel):
    page = open_panel(fail_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.click("#confirm-go")
    wait_toast(page, "Unable to remove the schedule for madar.com: "
                     "the engine could not do that")
    assert row(page, "MADAR").locator('[data-role="status"]').inner_text() \
        == "Unable to remove the schedule: the engine could not do that"


@pytest.mark.parametrize("width", WIDTHS)
def test_focus_goes_to_the_row_that_takes_the_removed_rows_place(open_panel, width):
    """C56: from the keyboard, focus in a row that leaves goes to the row that takes its
    place, else the one before, else the empty card's Create -- never to <body>."""
    page = open_panel(width=width, schedules=sched(PRICE))

    def remove_from_keyboard(key):
        row(page, key).locator('[data-role="kebab"]').focus()
        page.keyboard.press("ArrowUp")              # opens on its last item, Remove
        page.keyboard.press("Enter")
        page.wait_for_selector("#confirm-veil:not(.hidden)")
        page.keyboard.press("Tab")                  # Cancel -> Remove schedule
        page.keyboard.press("Enter")
        page.wait_for_selector(f'{VIEW} .schedule-row[data-sched="{key}"]',
                               state="detached")

    show_schedules(page)
    remove_from_keyboard("MADAR")
    assert page.evaluate("""() => [document.activeElement.dataset.role,
        document.activeElement.closest('.schedule-row')?.dataset.sched]""") == [
        "sched-active", "ALSWEED"]
    remove_from_keyboard("ELBUROJ")                 # the last row: the one before it
    assert page.evaluate("""() => document.activeElement.closest('.schedule-row')
        ?.dataset.sched""") == "ALSWEED"
    remove_from_keyboard("ALSWEED")                 # none left: the empty card's Create
    assert page.evaluate("""() => [document.activeElement.textContent.trim(),
        document.activeElement.closest('[data-role="empty"]') !== null]""") == [
        "Create schedule", True]
    assert not page.js_errors


# ---- a write in flight, a read that fails, an engine that is gone ---------------------
# Each of these was a mutation that survived the whole file at #1704's gate (R1-R15).

STATUS = f'{VIEW} .schedule-row[data-sched="MADAR"] [data-role="status"]'
MADAR_OFF = "body.sources.find((s) => s.source_key === 'MADAR').active = false;"
OLD_ENGINE = {"engine_version": "0.4.57",
              "omit_capabilities": ("schedule_active_switch", "scheduled_skips")}


def status_starts(page, words, timeout=5_000):
    page.wait_for_function("([sel, w]) => document.querySelector(sel).textContent.startsWith(w)",
                           arg=[STATUS, words], timeout=timeout)


def banner(page):
    return page.locator('#sched-state [data-role="banner"]')


def press_and_hold(page):
    """MADAR's switch, pressed against an engine that never answers the write."""
    flip(page, "MADAR")
    page.evaluate("window.__pressed = Date.now()")
    page.click("#confirm-go")
    status_starts(page, "Saving…")


def unread_words(page):
    at = page.evaluate("ScrapeXTime.format(schedulesPage.readAt, 'time')")
    return ("No answer from the engine in 5 s, and it could not be read again. "
            f"The row shows what was read at {at}.")


def test_a_commit_inside_the_engines_lock_wait_is_still_found(open_panel):
    """R1. The engine waits up to 10 s for the write lock (`db.py`, `write_lock`), so a
    commit 7.5 s after the press is found by the second read, at 11 s, and said."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    press_and_hold(page)
    status_starts(page, "No answer from the engine in 5 s", timeout=9_000)
    page.wait_for_timeout(2_500)
    answer(page, "/api/sources", MADAR_OFF)
    wait_toast(page, "Disabled scheduled runs for madar.com", timeout=8_000)
    assert page.evaluate("Date.now() - window.__pressed") >= 10_900
    assert not page.js_errors


def test_a_press_on_a_switch_in_flight_does_nothing(open_panel):
    """R3. The switch is aria-disabled while its write is out, never `disabled` (#1542),
    so Space still reaches it: it asks nothing and sends nothing."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    press_and_hold(page)
    row(page, "MADAR").locator('[data-role="sched-active"]').focus()
    page.keyboard.press("Space")
    page.wait_for_timeout(300)
    assert page.locator("#confirm-veil").is_hidden()
    assert len(writes(page)) == 1
    assert not page.js_errors


def test_the_menu_of_a_row_in_flight_does_not_open(open_panel):
    """R14. ⋮ is aria-disabled while the row's write is out, and a press opens nothing."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    press_and_hold(page)
    kebab = row(page, "MADAR").locator('[data-role="kebab"]')
    kebab.click(force=True)
    page.wait_for_timeout(300)
    assert row(page, "MADAR").locator('[role="menu"]').is_hidden()
    assert kebab.get_attribute("aria-expanded") == "false"
    assert not page.js_errors


def test_a_failed_first_reread_after_a_timeout_says_so_and_frees_the_row(open_panel):
    """R4. The read at once after a timeout fails: the row says it could not be read
    again, and when it was last read, and its switch is live and unchanged."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    press_and_hold(page)
    page.evaluate("FAIL.push('/api/sources')")
    status_starts(page, "No answer from the engine in 5 s, and it could not", timeout=9_000)
    assert text(page, STATUS) == unread_words(page)
    switch = row(page, "MADAR").locator('[data-role="sched-active"]')
    assert switch.get_attribute("aria-disabled") is None
    assert switch.get_attribute("aria-checked") == "true"
    assert banner(page).locator("strong").inner_text() == "Unable to refresh data"
    assert not page.js_errors


def test_a_failed_second_reread_after_a_timeout_says_so(open_panel):
    """R4. The first read found the change not there yet; the one at 11 s fails."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    show_schedules(page)
    press_and_hold(page)
    status_starts(page, "No answer from the engine in 5 s, and scheduled", timeout=9_000)
    page.evaluate("FAIL.push('/api/sources')")
    status_starts(page, "No answer from the engine in 5 s, and it could not", timeout=9_000)
    assert text(page, STATUS) == unread_words(page)
    assert not page.js_errors


def test_an_http_failure_over_a_shown_list_keeps_the_list_and_its_controls(open_panel):
    """R8. A tick the engine refuses, over a list already shown: "Unable to refresh
    data", the time the list was read, the engine's words, no action, and the rows
    stay live -- the engine is answering."""
    page = open_panel()
    show_schedules(page)
    at = page.evaluate("ScrapeXTime.format(schedulesPage.readAt, 'time')")
    page.evaluate("FAIL.push('/api/schedules')")
    page.evaluate("loadSchedulesPage({ quiet: true })")
    assert banner(page).locator("strong").inner_text() == "Unable to refresh data"
    assert banner(page).locator("p").inner_text() == (
        f"Showing the schedules as read at {at}. The engine answered: "
        "the engine could not do that")
    assert "danger" not in banner(page).get_attribute("class")
    assert banner(page).locator("button").count() == 0
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-disabled") is None
    assert not page.js_errors


def test_a_job_end_whose_sources_read_fails_says_so_and_try_again_reads_them(open_panel):
    """R7 and R15. A job end's reload of sources fails: the list stays, and the banner
    says so (never a stale list in silence). Try again reads sources as well as
    schedules, because the last read that wanted them failed."""
    page = open_panel()
    show_schedules(page)
    page.evaluate("FAIL.push('/api/sources')")
    page.evaluate("redrawWhatTheJobChanged()")   # what the tick calls at a job end
    banner(page).wait_for()
    assert banner(page).locator("strong").inner_text() == "The engine did not answer"
    assert banner(page).locator("p").inner_text().startswith("Showing the schedules as read at ")
    assert row(page, "MADAR").count() == 1
    answer(page, "/api/sources", MADAR_OFF)
    page.evaluate("FAIL.length = 0")
    sources = len(calls(page, "/api/sources"))
    banner(page).locator("button").click()
    banner(page).wait_for(state="detached")
    assert len(calls(page, "/api/sources")) == sources + 1
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-checked") == "false"
    assert not page.js_errors


def test_a_tick_after_a_failed_sources_read_reads_them_again(open_panel):
    """R15. A tick reads schedules alone -- unless the last read that wanted sources
    failed, and then it reads them too."""
    page = open_panel()
    show_schedules(page)
    page.evaluate("FAIL.push('/api/sources')")
    page.evaluate("loadSchedulesPage({ quiet: true, sourcesToo: true })")
    banner(page).wait_for()
    answer(page, "/api/sources", MADAR_OFF)
    page.evaluate("FAIL.length = 0")
    sources = len(calls(page, "/api/sources"))
    page.evaluate("loadSchedulesPage({ quiet: true })")
    assert len(calls(page, "/api/sources")) == sources + 1
    assert row(page, "MADAR").locator('[data-role="sched-active"]') \
        .get_attribute("aria-checked") == "false"
    assert not page.js_errors


def test_a_start_that_fails_sends_him_to_run(open_panel):
    """R11. Start engine on the banner, and the engine does not start: the reason is drawn
    where the engine is started from, so the banner sends him there."""
    page = open_panel(engine_up=False)
    show_schedules(page)
    banner(page).locator("button").click()
    page.wait_for_function("""() => document.querySelector(
        '#sched-state [data-role="banner"] p')?.textContent
        === 'The engine did not start. Open Run to see why.'""")
    assert banner(page).locator("strong").inner_text() == "Engine not running"
    assert banner(page).locator("button").inner_text() == "Open Run"
    banner(page).locator("button").click()
    page.wait_for_selector("#view-run", state="visible")
    assert not page.js_errors


def assert_writes_wait(page, *, switch):
    """⋮ and Create schedule are aria-disabled, and so is the switch where there is one;
    pressed, none of them asks, opens or sends anything."""
    madar = row(page, "MADAR")
    kebab = madar.locator('[data-role="kebab"]')
    assert kebab.get_attribute("aria-disabled") == "true"
    assert page.get_attribute("#sched-create", "aria-disabled") == "true"
    toggle = madar.locator('[data-role="sched-active"]')
    assert toggle.count() == (1 if switch else 0)
    if switch:
        assert toggle.get_attribute("aria-disabled") == "true"
        toggle.focus()
        page.keyboard.press("Space")
    kebab.click(force=True)
    page.click("#sched-create", force=True)
    page.wait_for_timeout(300)
    assert page.locator("#confirm-veil").is_hidden()
    assert madar.locator('[role="menu"]').is_hidden()
    assert page.locator(VIEW).is_visible()
    assert writes(page) == []


def test_a_stopped_engine_holds_every_write_over_a_shown_list(open_panel):
    """R12. The engine answers but is not running (its worker is gone), and a read fails:
    the list stays, and every write waits. Its version report is still known, so the
    switches stay, held."""
    page = open_panel()
    show_schedules(page)
    answer(page, "/api/health", "body.worker_alive = false;")
    page.evaluate("updateEngineState()")
    page.evaluate("FAIL.push('/api/schedules')")
    page.evaluate("loadSchedulesPage({ quiet: true })")
    banner(page).wait_for()
    assert page.evaluate("state.engineUp") is False
    assert_writes_wait(page, switch=True)
    assert not page.js_errors


def test_an_engine_that_is_gone_holds_every_write_over_a_shown_list(open_panel):
    """R12. The engine stopped answering altogether: "Engine stopped answering" over the
    list, the writes wait, and the switches leave with the version report that said the
    engine had them -- "their controls return when the engine answers"."""
    page = open_panel()
    show_schedules(page)
    page.evaluate("""() => { const real = window.fetch;
        window.fetch = (url, options) => /\\/api\\//.test(String(url))
          ? Promise.reject(new TypeError("Failed to fetch")) : real(url, options); }""")
    page.evaluate("updateEngineState()")
    page.evaluate("loadSchedulesPage({ quiet: true })")
    assert banner(page).locator("strong").inner_text() == "Engine stopped answering"
    assert old_note(page).count() == 0
    assert_writes_wait(page, switch=False)
    assert not page.js_errors


def test_the_idle_probe_reads_the_list_while_it_is_shown(open_panel):
    """R5. With no job running the page's list is read on the panel's idle probe, every
    30 s, while the page is shown."""
    page = open_panel()
    show_schedules(page)
    page.clock.install()
    page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(500)
    answer(page, "/api/schedules",
           "body.schedules = body.schedules.filter((s) => s.source_key !== 'ELBUROJ');")
    page.clock.run_for(31_000)
    page.wait_for_selector(f'{VIEW} .schedule-row[data-sched="ELBUROJ"]', state="detached",
                           timeout=3_000)
    assert not page.js_errors


def test_a_paused_schedule_on_an_old_engine_reads_paused_and_remove_keeps_it(open_panel):
    """R2 and R9. On an engine without the switch, `enabled = 0` is a pause: the row
    reads "Paused", and Remove keeps `enabled` as stored, so nothing is lost."""
    paused = [dict(PRICE[0], enabled=0, next_run_at=None), *PRICE[1:]]
    page = open_panel(schedules=sched(paused), **OLD_ENGINE)
    show_schedules(page)
    assert row(page, "MADAR").locator('[data-fact="next"]').inner_text() == "Paused"
    press_item(page, "MADAR", "Remove schedule…")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    assert writes(page)[0]["body"]["enabled"] is False
    assert not page.js_errors


# ---- Run follows what this page writes (C53, C53b) ---------------------------------

def test_runs_chip_follows_the_switch(open_panel):
    page = open_panel()
    load_run_first(page)
    assert chip(page, "MADAR") == "Daily 09:00"
    show_schedules(page)
    flip(page, "MADAR")
    page.click("#confirm-go")
    wait_toast(page, "Disabled scheduled runs for madar.com")
    page.wait_for_function("""() => document.querySelector(
        '#sites [data-sched-link="MADAR"]').textContent.trim() === 'Daily 09:00 · Off'""")


def test_runs_chip_follows_remove(open_panel):
    page = open_panel()
    load_run_first(page)
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    assert chip(page, "MADAR") == "Not scheduled"


def test_runs_chip_follows_an_edit_and_a_create(open_panel):
    """Run does not re-read on a later show, so a sheet's save redraws its cards from the Map
    just written (C53)."""
    page = open_panel(sources=with_sika())
    load_run_first(page)
    show_schedules(page)
    open_edit(page, "ELBUROJ")
    page.fill("#sched-sheet-time", "10:00")
    page.click("#sched-sheet-save")
    wait_toast(page, "Saved the schedule for elburoj.com")
    assert chip(page, "ELBUROJ") == "Daily 10:00"
    holds_engine(page, "ADVANCEDCASTLE", "{frequency: 'weekly'}")
    open_create(page)
    page.click("#sched-sheet-save")
    wait_toast(page, "Created the schedule for advancedcastle.com")
    page.wait_for_function("""() => document.querySelector(
        '#sites [data-sched-link="ADVANCEDCASTLE"]').textContent === 'Weekly Thursday 07:45'""")


def test_a_remove_found_late_still_redraws_runs_chip(open_panel):
    """Remove's late-found path: no answer, the first read still holds the schedule,
    the engine commits, and the read after the engine's own wait finds it removed."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    load_run_first(page)
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.click("#confirm-go")
    assert text(page, f'{VIEW} .schedule-row[data-sched="MADAR"] [data-role="status"]') \
        == "Removing schedule…"
    page.wait_for_function("""() => document.querySelector(
        '#view-schedules .schedule-row[data-sched="MADAR"] [data-role="status"]')
        .textContent.startsWith('No answer from the engine in 5 s, and the schedule is')""",
        timeout=9_000)
    answer(page, "/api/schedules",
           "body.schedules.find((s) => s.source_key === 'MADAR').frequency = 'manual';")
    wait_toast(page, "Removed the schedule for madar.com", timeout=12_000)
    assert row(page, "MADAR").count() == 0
    assert chip(page, "MADAR") == "Not scheduled"
    assert not page.js_errors


def test_a_late_read_leaves_run_alone_while_he_is_on_it(open_panel):
    """A re-read that lands after he moved to Run does not rebuild Run's cards under
    him: the checkbox he is on keeps its focus."""
    page = open_panel(blackhole_routes=("/api/schedules/MADAR",))
    load_run_first(page)
    show_schedules(page)
    flip(page, "MADAR")
    page.click("#confirm-go")
    page.click('nav.side-rail button[data-view="run"]')
    page.focus('#sites input[data-key="MADAR"]')
    page.evaluate("window.__held = document.activeElement")
    answer(page, "/api/sources",
           "body.sources.find((s) => s.source_key === 'MADAR').active = false;")
    wait_toast(page, "Disabled scheduled runs for madar.com", timeout=9_000)
    assert page.evaluate("window.__held.isConnected"
                         " && document.activeElement === window.__held")


def test_a_good_read_after_a_failed_job_end_read_brings_runs_chips_back(open_panel):
    """A job end whose schedules read fails leaves Run with no chips (loadSources reads
    them with `.catch(() => null)`); the page's next good read draws them again."""
    page = open_panel()
    load_run_first(page)
    show_schedules(page)
    page.evaluate("FAIL.push('/api/schedules')")
    page.evaluate("redrawWhatTheJobChanged()")
    page.wait_for_function(
        "() => !document.querySelector('#sites [data-sched-link=\"MADAR\"]')")
    banner = page.locator('#sched-state [data-role="banner"]')
    banner.wait_for()
    assert banner.locator("strong").inner_text() == "The engine did not answer"
    page.evaluate("FAIL.length = 0")
    banner.locator("button").click()
    page.wait_for_selector('#sites [data-sched-link="MADAR"]', state="attached")
    assert chip(page, "MADAR") == "Daily 09:00"


RUNNING = {
    "job_ref": "job_madar0001", "job_kind": "crawl", "status": "running",
    "run_mode": "update", "source_keys": ["MADAR"], "current_source_key": "MADAR",
    "stage": None, "progress": {"done": 0, "total": 1},
    "fetch": {"requests": 0, "expected": None, "basis": None, "as_of": None,
              "unknown_sources": [], "sources": {}},
    "queued_behind": None, "counters": {}, "created_at": "2026-10-11T06:00:00Z",
    "started_at": "2026-10-11T06:00:00Z", "finished_at": None,
    "last_heartbeat_at": None, "error_summary": None}


def adopted(page, ref):
    page.wait_for_function("(ref) => state.jobRef === ref", arg=ref)


def test_a_job_end_through_the_tick_redraws_the_page_from_the_panels_own_read(open_panel):
    """A job end costs the page no read of its own: the panel's reload reads sources and
    schedules once (`redrawWhatTheJobChanged`), and the page draws from it. Driven
    through the real tick (`pollJobOnce`), where `noticeActiveSet` also sees the job go."""
    page = open_panel(jobs=[RUNNING])
    adopted(page, RUNNING["job_ref"])
    show_schedules(page)
    answer(page, "/api/sources", "body.sources.find((s) => s.source_key === 'MADAR')"
                                 ".last_success = {started_at: '2026-10-11T06:00:00Z',"
                                 " finished_at: '2026-10-11T06:20:00Z'};")
    schedules, sources = len(calls(page, "/api/schedules")), len(calls(page, "/api/sources"))
    page.evaluate("ROUTES['/api/jobs'] = {jobs: []}")
    page.wait_for_function(f"""() => document.querySelector(
        '{VIEW} .schedule-row[data-sched="MADAR"] [data-fact="last"]')
        .textContent.includes('11 October 2026')""", timeout=6_000)
    # Every read of this job end left before /api/sources did (noticeActiveSet's at once,
    # loadSources' beside it), so the count is final here.
    assert len(calls(page, "/api/sources")) == sources + 1
    assert len(calls(page, "/api/schedules")) == schedules + 1
    assert not page.js_errors


def test_a_job_that_appears_has_the_page_read_its_schedules(open_panel):
    """A firing makes a job and re-arms its slot: the job that appears in the tick has the
    page read schedules once, and no sources -- the job has changed none yet."""
    page = open_panel(jobs=[RUNNING])
    adopted(page, RUNNING["job_ref"])
    show_schedules(page)
    answer(page, "/api/schedules", "body.schedules.find((s) => s.source_key === 'ELBUROJ')"
                                   ".next_run_at = '2026-10-12T05:30:00Z';")
    schedules, sources = len(calls(page, "/api/schedules")), len(calls(page, "/api/sources"))
    fired = {**RUNNING, "job_ref": "job_elburoj001", "status": "queued",
             "source_keys": ["ELBUROJ"], "current_source_key": None, "started_at": None}
    page.evaluate("(job) => { ROUTES['/api/jobs'] = {jobs: [ROUTES['/api/jobs'].jobs[0], job]}; }",
                  fired)
    page.wait_for_function(f"""() => document.querySelector(
        '{VIEW} .schedule-row[data-sched="ELBUROJ"] [data-fact="next"]')
        .textContent.includes('Mon 12 Oct')""", timeout=6_000)
    page.wait_for_timeout(1_600)   # one more tick, with the same jobs: nothing more is read
    assert len(calls(page, "/api/schedules")) == schedules + 1
    assert len(calls(page, "/api/sources")) == sources
    assert not page.js_errors


def test_a_job_end_on_an_engine_without_the_switch_claims_no_schedules_read(open_panel):
    """loadSources reads no schedules on an engine without the switch, so a job end there
    is no fresh read: a failed one stays said, and "Read at" stays where it was."""
    page = open_panel(engine_version="0.4.57",
                      omit_capabilities=("schedule_active_switch", "scheduled_skips"))
    show_schedules(page)
    page.evaluate("FAIL.push('/api/schedules')")
    page.evaluate("loadSchedulesPage({ quiet: true })")   # the tick's read, as it fails
    banner = page.locator('#sched-state [data-role="banner"]')
    banner.wait_for()
    read_at = page.evaluate("schedulesPage.readAt")
    page.evaluate("redrawWhatTheJobChanged()")
    assert banner.locator("strong").inner_text() == "Unable to refresh data"
    assert page.evaluate("schedulesPage.readAt") == read_at
    assert not page.js_errors


def test_a_job_end_that_reads_sources_again_clears_their_failure(open_panel):
    """A job end whose sources read failed is said; the next job end reads them, and the
    banner goes. On an engine without the switch, where loadSources reads no schedules,
    so only the sources read can clear it."""
    page = open_panel(**OLD_ENGINE)
    show_schedules(page)
    page.evaluate("FAIL.push('/api/sources')")
    page.evaluate("redrawWhatTheJobChanged()")
    banner(page).wait_for()
    assert banner(page).locator("strong").inner_text() == "The engine did not answer"
    page.evaluate("FAIL.length = 0")
    page.evaluate("redrawWhatTheJobChanged()")
    banner(page).wait_for(state="detached")
    assert not page.js_errors


def test_a_read_that_left_before_a_remove_does_not_bring_the_row_back(open_panel):
    """A job end's reload left while the Remove question was open, and lands after the
    Remove was answered: its schedules are older than the Remove, so the row stays gone
    and nothing about it is live. (`redrawWhatTheJobChanged` is what the tick calls at a
    job end; called here so its read can be held across the press.)"""
    page = open_panel(route_delays={"/api/sources": 1_500})
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.wait_for_selector("#confirm-veil:not(.hidden)")
    page.evaluate("() => { window.__end = redrawWhatTheJobChanged(); }")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    assert row(page, "MADAR").count() == 0
    page.evaluate("window.__end")   # the held reload, landed and drawn
    assert row(page, "MADAR").count() == 0
    assert page.evaluate("state.schedules.get('MADAR').frequency") == "manual"
    assert not page.js_errors


def hold_next_read(page, path, ms):
    """Hold the answer to the next GET of exactly `path` for `ms`, after the stub has
    answered it: route timing only, for one read, so the reads around it are untouched."""
    page.evaluate("""([path, ms]) => {
        const real = window.fetch;
        let held = ms;
        window.fetch = async (url, options = {}) => {
            const bare = String(url).replace(/^https?:\\/\\/[^/]+/, '').split('?')[0];
            const get = !options.method || options.method === 'GET';
            if (!(held && get && bare === path)) return real(url, options);
            const wait = held;
            held = 0;
            const answered = await real(url, options);
            const body = JSON.parse(JSON.stringify(await answered.json()));
            await new Promise((resolve) => setTimeout(resolve, wait));
            return { ok: answered.ok, status: answered.status, json: async () => body };
        };
    }""", [path, ms])


def test_a_page_read_that_left_before_a_remove_does_not_bring_the_row_back(open_panel):
    """The page's own read -- a tick's, held by a slow engine -- left before the Remove
    was answered and lands after it: the Remove stands."""
    page = open_panel()
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.wait_for_selector("#confirm-veil:not(.hidden)")
    hold_next_read(page, "/api/schedules", 1_000)
    read_at = page.evaluate("schedulesPage.readAt")
    page.evaluate("() => { window.__tick = loadSchedulesPage({ quiet: true }); }")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    page.evaluate("window.__tick")
    assert row(page, "MADAR").count() == 0
    assert text(page, "#sched-count").startswith("3 schedules · 1 without a source")
    # What it shows was not read by that read, so "Read at" does not say it was.
    assert page.evaluate("schedulesPage.readAt") == read_at
    assert not page.js_errors


def test_the_switch_sends_the_schedule_a_read_brought_in_while_he_answered(open_panel):
    """The engine's own page saved MADAR as Weekly Wednesday 07:15 Africa/Cairo while the
    question was open, and a tick brought it in. The route stores every field it is sent,
    so the POST carries that schedule, not the one he pressed on."""
    page = open_panel()
    show_schedules(page)
    flip(page, "MADAR")
    answer(page, "/api/schedules", "Object.assign(body.schedules.find((s) => s.source_key "
                                   "=== 'MADAR'), {frequency: 'weekly', weekday: 2, "
                                   "run_at: '07:15', timezone: 'Africa/Cairo'});")
    page.evaluate("loadSchedulesPage({ quiet: true })")   # the tick's read
    page.wait_for_function(f"""() => document.querySelector(
        '{VIEW} .schedule-row[data-sched="MADAR"] .schedule-facts')
        .textContent.includes('Weekly Wednesday 07:15')""")
    page.click("#confirm-go")
    wait_toast(page, "Disabled scheduled runs for madar.com")
    body = writes(page)[-1]["body"]
    assert (body["frequency"], body["weekday"], body["run_at"], body["timezone"],
            body["active"]) == ("weekly", 2, "07:15", "Africa/Cairo", False), body
    assert not page.js_errors


def test_a_switch_on_a_schedule_removed_while_he_answered_sends_nothing(open_panel):
    """Removed elsewhere while the question was open: its row left with the tick, and a
    POST would save it back as a schedule and turn the source off."""
    page = open_panel()
    show_schedules(page)
    flip(page, "MADAR")
    answer(page, "/api/schedules",
           "body.schedules.find((s) => s.source_key === 'MADAR').frequency = 'manual';")
    page.evaluate("loadSchedulesPage({ quiet: true })")
    row(page, "MADAR").wait_for(state="detached")
    page.click("#confirm-go")
    page.wait_for_selector("#confirm-veil.hidden", state="attached")
    page.wait_for_timeout(300)
    assert writes(page) == []
    assert not page.js_errors


def test_remove_keeps_the_time_and_zone_stored_when_it_is_answered(open_panel):
    """Remove keeps the time and zone: the ones stored when he answers, not when he
    opened the question."""
    page = open_panel()
    show_schedules(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.wait_for_selector("#confirm-veil:not(.hidden)")
    answer(page, "/api/schedules", "Object.assign(body.schedules.find((s) => s.source_key "
                                   "=== 'MADAR'), {run_at: '07:15', timezone: 'Africa/Cairo'});")
    page.evaluate("loadSchedulesPage({ quiet: true })")
    page.wait_for_function(f"""() => document.querySelector(
        '{VIEW} .schedule-row[data-sched="MADAR"] .schedule-facts')
        .textContent.includes('07:15 · Africa/Cairo')""")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    body = writes(page)[-1]["body"]
    assert (body["frequency"], body["run_at"], body["timezone"]) \
        == ("manual", "07:15", "Africa/Cairo"), body
    assert not page.js_errors


# Another reader's Map in state.schedules: the panel's own loadSources, landing after the
# page's read (the re-review's A1 and A2).
MADAR_MANUAL = "body.schedules.find((s) => s.source_key === 'MADAR').frequency = 'manual';"


def another_readers_map(page):
    page.wait_for_function("() => state.schedules instanceof Map"
                           " && state.schedules !== schedulesPage.saved")


def test_a_remove_reaches_runs_chip_over_a_map_another_read_left(open_panel):
    """Sources' loadSources, its schedules read slow, lands after the page's read, so Run
    draws from a Map the page does not hold. A Remove still reaches Run's chip."""
    page = open_panel()
    load_run_first(page)
    hold_next_read(page, "/api/schedules", 1_500)
    page.click("#tab-sources")
    show_schedules(page)
    another_readers_map(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    assert chip(page, "MADAR") == "Not scheduled"
    assert not page.js_errors


def test_a_job_end_across_a_remove_takes_no_older_map(open_panel):
    """Another reader's Map sits in state.schedules, and a job end's reload is in flight
    across a Remove: the reload drops its own read, and takes no other Map for it, so
    the removed row stays gone."""
    page = open_panel()
    hold_next_read(page, "/api/schedules", 1_500)
    page.click("#tab-sources")
    show_schedules(page)
    another_readers_map(page)
    press_item(page, "MADAR", "Remove schedule…")
    page.wait_for_selector("#confirm-veil:not(.hidden)")
    hold_next_read(page, "/api/sources", 1_500)
    read_at = page.evaluate("schedulesPage.readAt")
    page.evaluate("() => { window.__end = redrawWhatTheJobChanged(); }")
    page.click("#confirm-go")
    wait_toast(page, "Removed the schedule for madar.com")
    answer(page, "/api/schedules", MADAR_MANUAL)
    page.evaluate("window.__end")
    assert row(page, "MADAR").count() == 0
    assert page.evaluate("schedulesPage.saved.get('MADAR').frequency") == "manual"
    # The page's own Map, which the Remove put in state.schedules, is no read either.
    assert page.evaluate("schedulesPage.readAt") == read_at
    assert not page.js_errors


def test_an_engine_check_during_the_first_read_keeps_it_loading(open_panel):
    """No list read yet: an engine check draws nothing over "Loading schedules…"."""
    page = open_panel(route_delays={"/api/schedules": 1_500})
    page.click("#tab-schedules")
    page.wait_for_function("() => document.getElementById('sched-count').textContent"
                           " === 'Loading schedules…'")
    page.evaluate("updateEngineState()")
    assert text(page, "#sched-count") == "Loading schedules…"
    assert page.locator("#sched-list").is_visible()
    assert not page.js_errors


def test_the_old_engine_note_is_not_rewritten_by_a_tick_or_a_check(open_panel):
    """A role="status" node rewritten on every draw is announced on every tick: the
    same words keep the same node."""
    page = open_panel(**OLD_ENGINE)
    show_schedules(page)
    page.evaluate("window.__note = document.querySelector('#sched-state [data-role=\"old\"]')")
    page.evaluate("loadSchedulesPage({ quiet: true })")
    page.evaluate("updateEngineState()")
    assert page.evaluate("window.__note.isConnected")
    assert not page.js_errors


def test_a_switch_that_returns_sits_before_the_menu(open_panel):
    """The switch a late report adds is where a built row has it, before ⋮, so Tab
    reaches it in the order it is drawn."""
    page = open_panel(blackhole_routes=("/api/version",))
    show_schedules(page)
    page.evaluate("BLACKHOLE_ROUTES.length = 0")
    page.evaluate("updateEngineState()")
    order = page.evaluate(f"""() => [...document.querySelector(
        '{VIEW} .schedule-row[data-sched="MADAR"]').children]
        .map((el) => el.dataset.role || el.className.split(' ')[0])""")
    assert order.index("sched-active") < order.index("job-kebab"), order
    assert not page.js_errors


def test_a_tick_where_one_job_ends_and_one_starts_reads_the_schedules(open_panel):
    """The active set keeps its size, one job out and one in -- the crawl's handoff to its
    interpretation. On an engine without the switch the job end's reload reads no
    schedules, so only noticeActiveSet's read brings in the slot the firing re-armed."""
    page = open_panel(jobs=[RUNNING], **OLD_ENGINE)
    adopted(page, RUNNING["job_ref"])
    show_schedules(page)
    answer(page, "/api/schedules", "body.schedules.find((s) => s.source_key === 'ELBUROJ')"
                                   ".next_run_at = '2026-10-12T05:30:00Z';")
    fired = {**RUNNING, "job_ref": "job_elburoj001", "status": "queued",
             "source_keys": ["ELBUROJ"], "current_source_key": None, "started_at": None}
    page.evaluate("(job) => { ROUTES['/api/jobs'] = {jobs: [job]}; }", fired)
    page.wait_for_function(f"""() => document.querySelector(
        '{VIEW} .schedule-row[data-sched="ELBUROJ"] [data-fact="next"]')
        .textContent.includes('Mon 12 Oct')""", timeout=6_000)
    assert not page.js_errors


# ---- the shared list, state.sources ---------------------------------------------------

def test_load_sources_says_whether_it_read_them(open_panel):
    page = open_panel()
    assert page.evaluate("loadSources()") is True
    page.evaluate("FAIL.push('/api/sources')")
    assert page.evaluate("loadSources()") is False


def test_the_pages_read_of_sources_prunes_the_run_selection_and_redraws_the_manager(
        open_panel):
    page = open_panel()
    load_run_first(page)
    page.check('#sites input[data-key="ELBUROJ"]')
    assert page.evaluate("state.selected.has('ELBUROJ')")
    answer(page, "/api/sources",
           "body.sources = body.sources.filter((s) => s.source_key !== 'ELBUROJ');")
    show_schedules(page)
    page.wait_for_function("() => !state.selected.has('ELBUROJ')")
    manager = page.text_content("#source-manager-list")
    assert "MADAR" in manager and "ELBUROJ" not in manager
    assert page.locator('#sites input[data-key="ELBUROJ"]').count() == 0


# ---- every "open its schedule" link lands here ----------------------------------------

def _lands_on_the_row(page, key):
    page.wait_for_selector(VIEW, state="visible")
    page.wait_for_function("""(key) => {
        const r = document.querySelector(`#view-schedules .schedule-row[data-sched="${key}"]`);
        return r && document.activeElement === r.querySelector('[data-role="runs"]');
    }""", arg=key)


def test_runs_chip_opens_its_row_on_this_page(open_panel):
    page = open_panel()
    load_run_first(page)
    page.click('#sites [data-sched-link="ELBUROJ"]')
    _lands_on_the_row(page, "ELBUROJ")
    assert not page.js_errors


def test_the_source_managers_edit_schedule_opens_its_row_on_this_page(open_panel):
    page = open_panel()
    page.evaluate("openScheduleRow('ALSWEED')")
    _lands_on_the_row(page, "ALSWEED")


def test_edit_sources_schedule_link_opens_its_row_on_this_page(open_panel):
    page = open_panel()
    page.evaluate("state.editingSourceKey = 'MADAR'")
    page.evaluate("document.getElementById('source-edit-schedule-link').click()")
    _lands_on_the_row(page, "MADAR")


def test_a_link_to_a_source_that_cannot_be_scheduled_says_so(open_panel):
    page = open_panel()
    page.evaluate("openScheduleRow('muqawil_org')")
    wait_toast(page, "This source can't be scheduled here.")
    assert page.locator(VIEW).is_visible()


# ---- moved from Settings' editor, onto the page's own rows (#1631 part 2) -------------

LONG_HOST = _source("LONG_AR", "https://very-long-subdomain.example-store-name.com.sa",
                    "Long Host Store", "متجر طويل الاسم")
LONG_ROW = {**ROW, "schedule_id": 5, "source_key": "LONG_AR", "frequency": "weekly",
            "run_at": "09:00", "timezone": "Asia/Riyadh", "weekday": 2,
            "next_run_at": "2026-10-14T06:00:00Z"}


@pytest.mark.parametrize("width", WIDTHS)
def test_a_rows_name_and_switch_share_its_first_line(open_panel, width):
    """Nothing that identifies a row is cut at narrow widths: the name and the switch
    share the first line, and the facts go under them (#1596)."""
    page = open_panel(width=width, sources=[*copy.deepcopy(SOURCES), LONG_HOST],
                      schedules=sched([*PRICE, LONG_ROW]))
    show_schedules(page)
    for key in ("MADAR", "LONG_AR"):
        name = row(page, key).locator(".source-identity-domain").bounding_box()
        switch = row(page, key).locator('[data-role="sched-active"]').bounding_box()
        assert name and name["width"] > 40, (width, key, name)
        assert switch["y"] < name["y"] + name["height"], (width, key, name, switch)
        assert switch["x"] > name["x"] + name["width"] - 1, (width, key, name, switch)
    assert not page.js_errors


@pytest.mark.parametrize("width", WIDTHS)
def test_the_toast_never_covers_the_rail_or_its_row(open_panel, width):
    page = open_panel(width=width)
    page.set_viewport_size({"width": width, "height": 460})
    show_schedules(page)
    switch = row(page, "ELBUROJ").locator('[data-role="sched-active"]')
    # The switch starts out exactly where the toast will appear.
    page.evaluate("""(el) => {
        const box = el.getBoundingClientRect();
        el.closest('.view-scroll').scrollBy(0, box.top - (innerHeight - 55));
    }""", switch.element_handle())
    assert switch.bounding_box()["y"] > 460 - 90, "the switch is not where the toast appears"
    flip(page, "ELBUROJ")
    page.click("#confirm-go")
    wait_toast(page, "Disabled scheduled runs for elburoj.com")
    covered = page.evaluate("""() => [...document.querySelectorAll('nav.side-rail button')]
        .filter((b) => b.offsetParent && b.getBoundingClientRect().top >= 0
                && b.getBoundingClientRect().bottom <= window.innerHeight)
        .map((b) => { const r = b.getBoundingClientRect();
                      const hit = document.elementFromPoint(r.x + r.width / 2,
                                                            r.y + r.height / 2);
                      return hit && hit.closest('nav.side-rail') ? null : b.dataset.view; })
        .filter(Boolean)""")
    assert covered == [], covered
    toast = page.locator("#toast").bounding_box()
    rail = page.locator("nav.side-rail").bounding_box()
    assert toast["x"] + toast["width"] <= rail["x"], (toast, rail)
    moved = switch.bounding_box()
    assert not (moved["y"] + moved["height"] > toast["y"]
                and moved["y"] < toast["y"] + toast["height"]), (moved, toast)
    assert page.evaluate("getComputedStyle(document.getElementById('toast')).pointerEvents") \
        == "none"


def test_a_switch_that_is_on_shows_its_edge_at_three_to_one(open_panel):
    """WCAG 2.2 SC 1.4.11: brand on white is 1.96:1, so the edge carries the state in
    Supabase's darker brand step, --accent-ink (brand-600)."""
    page = open_panel()
    show_schedules(page)
    switch = row(page, "MADAR").locator('[data-role="sched-active"]')
    assert switch.get_attribute("aria-checked") == "true"
    edge, ink, surface = page.evaluate("""(el) => {
        const probe = document.createElement('i');
        probe.style.color = 'var(--accent-ink)';
        document.body.append(probe);
        const ink = getComputedStyle(probe).color;
        probe.remove();
        return [getComputedStyle(el).borderTopColor, ink,
                getComputedStyle(el.closest('.card')).backgroundColor];
    }""", switch.element_handle())
    assert edge == ink, (edge, ink)

    def lum(rgb):
        parts = [int(v) / 255 for v in rgb[rgb.index("(") + 1:-1].split(",")[:3]]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    high, low = sorted((lum(edge), lum(surface)), reverse=True)
    assert (high + 0.05) / (low + 0.05) >= 3, (edge, surface)


def test_next_runs_instant_names_his_display_zone(open_panel):
    """Spec 33 6.8: a converted time names its zone. MADAR's next slot is 06:00 UTC: 09:00
    on its own Riyadh clock, and 3:00 PM in a display zone of Tokyo, which is named."""
    page = open_panel(timezone={"zone": "Asia/Tokyo", "updatedAt": 9_999_999_999_999})
    show_schedules(page)
    shown = row(page, "MADAR").locator('[data-fact="next"]').inner_text()
    assert "09:00" in shown and "3:00 PM" in shown and "Asia/Tokyo" in shown, shown
    assert "UTC" not in shown, shown
    assert not page.js_errors


# ---- the contrast of every state colour ----------------------------------------------

# Every text node on the page, against the background it is drawn on (alpha composited
# up the tree), through a canvas so any colour syntax the tokens use is read the same.
CONTRAST_JS = """() => {
  const ctx = document.createElement('canvas').getContext('2d', {willReadFrequently: true});
  const rgba = (c) => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c;
    ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255]; };
  const over = (top, under) => top.slice(0, 3).map((v, i) => v * top[3] + under[i] * (1 - top[3]));
  const lum = (c) => { const [r, g, b] = c.map((v) => { v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ground = (el) => { const layers = [];
    for (let n = el; n; n = n.parentElement) layers.push(rgba(getComputedStyle(n).backgroundColor));
    let under = rgba(getComputedStyle(document.body).backgroundColor);
    if (under[3] < 1) under = over(under, [255, 255, 255]);
    for (const layer of layers.reverse()) under = over(layer, under);
    return under; };
  const out = [];
  const walk = document.createTreeWalker(document.getElementById('view-schedules'),
    NodeFilter.SHOW_TEXT);
  for (let t = walk.nextNode(); t; t = walk.nextNode()) {
    const el = t.parentElement;
    if (!t.textContent.trim() || !el.checkVisibility() || el.closest('.visually-hidden')) continue;
    const fg = over(rgba(getComputedStyle(el).color), ground(el));
    const [a, b] = [lum(fg), lum(ground(el))];
    out.push({text: t.textContent.trim().slice(0, 50),
              ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)});
  }
  return out;
}"""


def _stage(page, state):
    if state == "menu":
        open_menu(page, "MADAR")
    elif state == "refused":
        flip(page, "MADAR")
        page.click("#confirm-go")
        wait_toast(page, "Unable to change scheduled runs for madar.com: "
                         "the engine could not do that")
    elif state == "saving":
        flip(page, "MADAR")
        page.click("#confirm-go")
        page.wait_for_function("""() => document.querySelector(
            '#view-schedules .schedule-row[data-sched="MADAR"] [data-role="status"]')
            .textContent === 'Saving…'""")


STATES = {
    "list": {},
    "menu": {},
    "refused": {"fail_routes": ("/api/schedules/MADAR",)},
    "saving": {"blackhole_routes": ("/api/schedules/MADAR",)},
    "empty": {"schedules": sched([])},
    "failed-read": {"fail_routes": ("/api/schedules",)},
    "engine-down": {"engine_up": False},
    "old-engine": {"engine_version": "0.4.57",
                   "omit_capabilities": ("schedule_active_switch", "scheduled_skips")},
}


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("state", STATES)
def test_every_word_on_the_page_reads_at_4_5_to_1(open_panel, state, scheme):
    """WCAG 2.2 SC 1.4.3, in every state, in both themes: the page types no colour, so
    this proves the shared tokens it composes hold where it puts them."""
    page = open_panel(scheme=scheme, **STATES[state])
    show_schedules(page)
    _stage(page, state)
    found = page.evaluate(CONTRAST_JS)
    assert found, "no text was measured"
    low = [(f["text"], round(f["ratio"], 2)) for f in found if f["ratio"] < 4.5]
    assert low == [], low


def test_the_harness_stub_globals_this_file_drives_exist(open_panel):
    """The staging above changes what the stub answers through its own globals; if they
    were renamed, every late-commit test would stage nothing and still time out."""
    page = open_panel()
    assert page.evaluate("[typeof ROUTES, Array.isArray(FAIL),"
                         " Array.isArray(BLACKHOLE_ROUTES)]") == ["object", True, True]
    assert page.evaluate("ROUTES['/api/schedules'].note") == NOTE
