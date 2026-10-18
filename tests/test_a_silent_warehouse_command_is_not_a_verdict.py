"""A command that reads the whole warehouse and has not answered yet has not FAILED.

#1706, measured on his 2.2 GB warehouse on 2026-10-17: he pressed Upgrade database,
the panel gave the native host five seconds, and said *"The database was not changed.
The reason is shown above."* The host had backed the file up and applied three
migrations, and no reason was shown anywhere. #1094 is the same five seconds in front
of Restart, plus a refused connection read as a restart in progress.

THE DURATIONS HERE ARE HIS. Measured 2026-10-17 through the host, launched as Chrome
launches it, on copies of his 2,232,049,664-byte warehouse: UPGRADE_DATABASE up to
146.0 s, CHECK_STARTUP up to 66.8 s cold, and START_ENGINE is that scan plus up to
3.5 s. The budgets themselves are derived at `warehouseCopy` and `integrityScan`
in `extension/startup.js`; these tests hold the host for as long as his file took,
or for ever, on Playwright's clock rather than the wall's.

EVERY SENTENCE IS KEPT, NOT ONLY THE LAST. A note that said "not changed" for one
tick and was then overwritten is the defect, so a recorder logs each text the note
ever held and the assertions read that history.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")
from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402

SLOWEST_UPGRADE_MS = 146_000
SLOWEST_CHECK_MS = 66_800
SLOWEST_START_MS = SLOWEST_CHECK_MS + 3_500
#: Erase data for AHRAMBC, `storage.wipe_source` itself, on the same copy: 6.05 and
#: 6.15 s, of which the copy before the delete was 5.8 -- past the 5 s it had.
SLOWEST_ERASE_MS = 6_150
#: Past any budget the panel has, so "never answers" is never.
FOREVER_MS = 20 * 60_000

V24 = {"engine": {"kind": "engine", "path": "C:/x/scrapex-engine.db", "ok": True,
                  "status": "Healthy", "action": "No action is required.",
                  "schema_version": 24, "application_id": 1, "integrity_checked": True}}
BEHIND_ACTION = ("This database is at schema v21 and this build expects v24. Use the "
                 "Upgrade database button on the Database screen, then retry.")
V21 = {"engine": {**V24["engine"], "ok": False, "status": "Needs upgrade",
                  "action": BEHIND_ACTION, "schema_version": 21}}
DAMAGED = {"engine": {**V24["engine"], "ok": False, "status": "Failed",
                      "action": "Restore this database from a verified backup, then retry."}}

FOUND_CURRENT = {"ok": True, "databases": V24}
# `ok` ON THE ANSWER IS "NOTHING BLOCKS A START", and `startup_check` does not count a
# Missing database as blocking -- so this answer is ok about a file that is not there.
FOUND_MISSING = {"ok": True, "databases": {"engine": {
    **V24["engine"], "ok": False, "status": "Missing", "schema_version": None,
    "action": "Reconnect the storage containing this database, then retry."}}}
FOUND_BEHIND = {"ok": False, "error": "startup_blocked", "action": "upgrade_database",
                "detail": f"engine: Needs upgrade. {BEHIND_ACTION}", "databases": V21}
FOUND_DAMAGED = {"ok": False, "error": "startup_blocked", "action": "check_storage",
                 "detail": "engine: Failed. Restore this database from a verified "
                           "backup, then retry.", "databases": DAMAGED}

# A HOST THAT ANSWERS ON THE PAGE'S OWN CLOCK. `after: null` never answers; a
# command with no rule answers at once, as the harness's own host does, so the
# panel's other native questions do not wait on this test.
WAIT = "The upgrade may still be running: wait a few minutes before pressing Upgrade database again."

SCRIPTED_HOST = """(script) => {
  window.__nativeCalls = [];
  window.chrome.runtime.sendNativeMessage = (_host, message, callback) => {
    window.__nativeCalls.push(message.command);
    const rule = script[message.command] || {after: 0, reply: {ok: true, installed: false}};
    if (rule.after === null) return;
    // What Chrome does when the host ends before it replies, or is not there.
    if (rule.chromeError) {
      setTimeout(() => {
        window.chrome.runtime.lastError = {message: rule.chromeError};
        callback(undefined);
        window.chrome.runtime.lastError = null;
      }, rule.after);
      return;
    }
    setTimeout(() => callback(rule.reply), rule.after);
  };
}"""

RECORD = """(ids) => {
  window.__said = {};
  for (const id of ids) {
    const el = document.getElementById(id);
    window.__said[id] = [el.textContent];
    new MutationObserver(() => window.__said[id].push(el.textContent))
      .observe(el, {childList: true, characterData: true, subtree: true});
  }
}"""


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
    pages = []

    def opener(*, host: dict, record: tuple[str, ...], **stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"silent{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        harness.wait_until_settled(page)
        page.evaluate(SCRIPTED_HOST, host)
        page.evaluate(RECORD, list(record))
        # AFTER BOOT, as the Jobs probe test does: boot waits on timers of its own.
        page.clock.install()
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def said(page, element_id: str) -> list[str]:
    return page.evaluate("(id) => window.__said[id]", element_id)


def wait_for_text(page, element_id: str, fragment: str) -> None:
    page.wait_for_function(
        "([id, part]) => document.getElementById(id).textContent.includes(part)",
        arg=[element_id, fragment], timeout=5000)


# THE ENGINE'S DOOR, ANSWERING AS SLOWLY AS HIS UPGRADE DID. The stub has no route for
# it, so this one is installed by hand: held on the page's clock, and given up the
# moment the panel's own deadline aborts it, as a real request is.
SLOW_ENGINE_UPGRADE = """(after) => {
  const real = window.fetch;
  window.fetch = (url, options = {}) => {
    if (!String(url).includes("/api/databases/upgrade")) return real(url, options);
    window.__writes.push({path: "/api/databases/upgrade", method: "POST", body: null});
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(new Response(
        JSON.stringify({ok: true, message: "Applied 3 migrations to engine."}),
        {status: 200, headers: {"Content-Type": "application/json"}})), after);
      if (options.signal) options.signal.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(options.signal.reason);
      }, {once: true});
    });
  };
}"""


def press_upgrade(open_panel, host: dict, prepare=None, **stub_kwargs):
    page = open_panel(host=host, record=("runtime-note", "engine-note"), **stub_kwargs)
    if prepare:
        prepare(page)
    page.click('nav.side-rail button[data-view="database"]')
    page.wait_for_selector("#view-database", state="visible")
    page.wait_for_function(
        "() => !document.getElementById('runtime-upgrade').disabled", timeout=5000)
    page.click("#runtime-upgrade")
    return page


def never_said_unchanged(page) -> None:
    for element_id in ("runtime-note", "engine-note"):
        history = said(page, element_id)
        assert not [text for text in history if "not changed" in text], (
            f"#{element_id} reported the database unchanged while the upgrade had "
            f"not answered -- #1706's sentence about a migrated warehouse: {history}")


# ---- Upgrade database ---------------------------------------------------------

def test_an_upgrade_as_slow_as_his_is_reported_as_its_answer(open_panel):
    """The 146 s his warehouse took is waited for, and its answer is what he reads."""
    message = ("Applied 3 migrations to engine. engine backed up to "
               "C:\\x\\scrapex-engine.pre-upgrade-20261017T055227Z.backup.db.")
    page = press_upgrade(open_panel, engine_up=False, host={
        "UPGRADE_DATABASE": {"after": SLOWEST_UPGRADE_MS, "reply": {"ok": True,
                                                                    "message": message}}})

    page.clock.run_for(SLOWEST_UPGRADE_MS - 1000)
    assert page.text_content("#runtime-note") == "Upgrading the database…", (
        "the panel stopped waiting before the time his own upgrade took")
    page.clock.run_for(2000)
    wait_for_text(page, "runtime-note", "Applied 3 migrations")

    never_said_unchanged(page)
    assert "CHECK_STARTUP" not in page.evaluate("window.__nativeCalls"), (
        "an upgrade that answered was re-checked as though it had not")
    assert page.js_errors == []


@pytest.mark.parametrize("found, expected", [
    pytest.param(FOUND_CURRENT, "the database is now at v24 and healthy", id="upgraded"),
    # NOT the engine's "use the Upgrade database button": a host that timed out has not
    # exited, and a read beside it sees the file as it was.
    pytest.param(FOUND_BEHIND, "still at v21. " + WAIT, id="still-behind"),
    pytest.param(FOUND_DAMAGED, "found a problem", id="something-else-wrong"),
    pytest.param(FOUND_MISSING, "reports: Missing. Reconnect the storage", id="file-missing"),
])
def test_an_upgrade_with_no_answer_reads_the_database_and_says_what_it_found(
        open_panel, found, expected):
    """No answer is said as no answer, and then the state is ASKED, not assumed."""
    page = press_upgrade(open_panel, engine_up=False, host={
        "UPGRADE_DATABASE": {"after": None},
        "CHECK_STARTUP": {"after": 0, "reply": found}})

    page.clock.run_for(FOREVER_MS)
    never_said_unchanged(page)
    wait_for_text(page, "runtime-note", expected)

    note = page.text_content("#runtime-note")
    assert note.startswith("No answer from the upgrade after "), (
        f"the sentence does not say the upgrade went unanswered, or for how long: {note!r}")
    assert page.evaluate("window.__nativeCalls.filter(c => c !== 'AUTOSTART_STATUS')") \
        [:2] == ["UPGRADE_DATABASE", "CHECK_STARTUP"], (
        "the database was not re-read after the upgrade went silent")
    history = said(page, "runtime-note")
    assert any(text.endswith("Checking the database…") for text in history), (
        f"nothing said the panel was checking while it checked: {history}")
    assert not page.locator("#runtime-upgrade").is_disabled(), (
        "the control stayed dead after the panel stopped waiting")


def test_a_silent_upgrade_and_a_silent_check_say_nothing_is_known(open_panel):
    page = press_upgrade(open_panel, engine_up=False, host={
        "UPGRADE_DATABASE": {"after": None}, "CHECK_STARTUP": {"after": None}})

    page.clock.run_for(FOREVER_MS)
    page.clock.run_for(FOREVER_MS)
    never_said_unchanged(page)
    wait_for_text(page, "runtime-note", "did not answer either. " + WAIT)


@pytest.mark.parametrize("found, expected", [
    pytest.param(FOUND_CURRENT, "v24 and healthy", id="upgraded"),
    # A host that STOPPED is done, so here the engine's own next step stands.
    pytest.param(FOUND_BEHIND, "still behind. " + BEHIND_ACTION, id="still-behind"),
])
def test_a_host_that_exits_mid_upgrade_is_not_a_verdict_either(open_panel, found, expected):
    """`crashed` is a host that stopped before it replied -- which can be halfway
    through a copy or a migration. Nothing it did is known, so it is read, not said."""
    page = press_upgrade(open_panel, engine_up=False, host={
        "UPGRADE_DATABASE": {"after": 40_000, "chromeError": "Native host has exited."},
        "CHECK_STARTUP": {"after": 0, "reply": found}})

    page.clock.run_for(41_000)
    never_said_unchanged(page)
    wait_for_text(page, "runtime-note", expected)
    assert "CHECK_STARTUP" in page.evaluate("window.__nativeCalls")


def test_an_engine_that_took_the_upgrade_is_not_sent_a_second_one(open_panel):
    """THE OTHER DOOR. The engine's route runs the same guarded upgrade, and it used to
    fall back to the native host whenever it did not answer -- so an engine still
    copying the warehouse would have been joined by a second upgrade of the same file.
    Its silence is read like the host's: re-read, never re-run."""
    page = press_upgrade(
        open_panel, route_delays={"/api/databases/upgrade": 10 ** 9},
        host={"UPGRADE_DATABASE": {"after": 0, "reply": {"ok": True, "message": "again"}},
              "CHECK_STARTUP": {"after": 0, "reply": FOUND_CURRENT}})

    page.clock.run_for(FOREVER_MS)
    calls = page.evaluate("window.__nativeCalls")
    assert "UPGRADE_DATABASE" not in calls, (
        f"the engine had the upgrade and the native host was sent another: {calls}")
    never_said_unchanged(page)
    wait_for_text(page, "runtime-note", "v24 and healthy")


def test_the_engines_door_waits_as_long_as_his_upgrade_took(open_panel):
    """ONE NUMBER FOR BOTH DOORS. `POST /api/databases/upgrade` runs the same guarded
    upgrade as the host, and it had 15 s -- `engineRepair`, a restart's bound -- for
    work measured at up to 146."""
    page = press_upgrade(
        open_panel, prepare=lambda p: p.evaluate(SLOW_ENGINE_UPGRADE, SLOWEST_UPGRADE_MS),
        host={"UPGRADE_DATABASE": {"after": 0, "reply": {"ok": True, "message": "again"}}})

    page.clock.run_for(SLOWEST_UPGRADE_MS - 1000)
    assert page.text_content("#runtime-note") == "Upgrading the database…", (
        "the panel gave up on the engine's upgrade before the time his own took")
    page.clock.run_for(2000)
    wait_for_text(page, "runtime-note", "Applied 3 migrations to engine.")

    calls = page.evaluate("window.__nativeCalls")
    assert "UPGRADE_DATABASE" not in calls and "CHECK_STARTUP" not in calls, calls
    never_said_unchanged(page)


def test_a_refusal_carries_its_reason_on_the_page_that_shows_it(open_panel):
    """"THE REASON IS SHOWN ABOVE" WAS SHOWN NOWHERE. The Database page has no issue
    card, and Run's sits below its note, so the reason goes in the sentence."""
    detail = ("the database was not upgraded because its fault is not a pending "
              "migration: engine: Failed. Restore this database from a verified "
              "backup, then retry.")
    page = press_upgrade(open_panel, engine_up=False, host={
        "UPGRADE_DATABASE": {"after": 0, "reply": {
            "ok": False, "error": "database_upgrade_failed", "detail": detail,
            "action": "check_storage"}}})

    page.clock.run_for(1000)
    wait_for_text(page, "runtime-note", detail[1:])

    # IN THE HOST'S OWN WORDS, and not under "The database was not changed": an
    # answered failure can come after the migration (`native.upgrade_database`).
    note = page.text_content("#runtime-note")
    assert note == detail[0].upper() + detail[1:], note
    assert "shown above" not in page.text_content("#engine-note")
    assert "CHECK_STARTUP" not in page.evaluate("window.__nativeCalls"), (
        "a host that ANSWERED no was re-checked as though it had been silent")


def test_a_host_that_never_ran_is_the_one_case_that_says_not_changed(open_panel):
    page = press_upgrade(open_panel, engine_up=False, host={
        "UPGRADE_DATABASE": {"after": 0, "chromeError":
                             "Specified native messaging host not found."}})

    page.clock.run_for(1000)
    wait_for_text(page, "runtime-note", "The database was not changed: Chrome cannot "
                                        "find the ScrapeX helper on this machine.")


def test_the_issue_cards_button_cannot_start_a_second_upgrade(open_panel):
    """THE CARD DRAWS ITS OWN UPGRADE BUTTON, on Run and in Settings, and it stayed
    live while the first upgrade waited -- five seconds once, five minutes now, and each
    press copies the whole warehouse before it waits for the write lock."""
    page = open_panel(engine_up=False, record=("engine-note", "runtime-note"), host={
        "START_ENGINE": {"after": 0, "reply": FOUND_BEHIND},
        "UPGRADE_DATABASE": {"after": None}})
    page.click('nav.side-rail button[data-view="run"]')
    page.click("#engine-start")
    page.clock.run_for(1000)
    card = page.locator("#engine-error [data-runtime-upgrade]")
    card.wait_for(state="visible", timeout=5000)
    card.click()
    page.clock.run_for(10_000)

    assert card.is_disabled(), "the card's Upgrade stayed live while one was running"
    assert page.text_content("#engine-note") == "Upgrading the database…", (
        "Run, where the press was made, does not say an upgrade is running")
    # START AND BOTH CHECK AGAINS rewrite this note or redraw the card mid-wait.
    for control in ("#engine-start", "#setup-recheck", "#engine-recheck"):
        assert page.locator(control).is_disabled(), f"{control} stayed live mid-upgrade"
    # A card drawn again mid-wait is drawn with its button down, not as a press the
    # guard would swallow without a word.
    page.evaluate("""() => setRuntimeIssue(Object.assign(new Error("behind"),
        {kind: "startup_blocked", action: "upgrade_database"}))""")
    assert page.locator("#engine-error [data-runtime-upgrade]").is_disabled(), (
        "a card redrawn mid-wait offers an Upgrade press that does nothing")
    page.evaluate("() => upgradeDatabaseFromPanel()")
    calls = [c for c in page.evaluate("window.__nativeCalls") if c == "UPGRADE_DATABASE"]
    assert calls == ["UPGRADE_DATABASE"], f"a second upgrade was started: {calls}"


def test_an_upgrade_gives_back_only_the_controls_it_took(open_panel):
    """A Start that is still scanning holds its own button. An upgrade pressed beside
    it, and refused at once, used to hand that button back -- and a second press sent a
    second START_ENGINE, a second scan of the whole file beside the first."""
    page = open_panel(engine_up=False, record=("engine-note",), host={
        "START_ENGINE": {"after": None},
        "UPGRADE_DATABASE": {"after": 0, "reply": {
            "ok": False, "error": "database_upgrade_failed", "action": "check_storage",
            "detail": "the database was not upgraded because it is not behind"}}})
    page.click('nav.side-rail button[data-view="run"]')
    page.click("#engine-start")
    page.clock.run_for(1000)
    assert page.locator("#engine-start").is_disabled()
    page.click('nav.side-rail button[data-view="database"]')
    page.click("#runtime-upgrade")
    page.clock.run_for(1000)
    wait_for_text(page, "runtime-note", "The database was not upgraded")

    assert page.locator("#engine-start").is_disabled(), (
        "the upgrade released a Start it never took, while that Start still runs")


def test_a_card_drawn_mid_wait_is_live_again_when_the_wait_ends(open_panel):
    """Jobs and Schedules each draw a Start of their own; pressed mid-wait, a Start
    redraws the issue card, and the card's Upgrade is drawn down while one runs. It
    stayed down after, under a sentence telling him to press it."""
    page = open_panel(engine_up=False, record=("runtime-note",), host={
        "UPGRADE_DATABASE": {"after": 40_000, "chromeError": "Native host has exited."},
        "CHECK_STARTUP": {"after": 0, "reply": FOUND_BEHIND}})
    page.click('nav.side-rail button[data-view="database"]')
    page.click("#runtime-upgrade")
    page.clock.run_for(1000)
    page.evaluate("""() => setRuntimeIssue(Object.assign(new Error("behind"),
        {kind: "startup_blocked", action: "upgrade_database"}))""")
    card = page.locator("#engine-error [data-runtime-upgrade]")
    assert card.is_disabled()

    page.clock.run_for(41_000)
    wait_for_text(page, "runtime-note", "Use the Upgrade database button")
    assert not card.is_disabled(), (
        "the card says to press Upgrade database and its button is still down")


def test_no_start_runs_beside_an_upgrade(open_panel):
    """The Jobs and Schedules banners draw a Start of their own, and each press during
    the wait was another whole-file scan beside the upgrade's, ending in a Run line that
    said "try again" while the upgrade still ran."""
    page = open_panel(engine_up=False, record=("engine-note",), host={
        "UPGRADE_DATABASE": {"after": None}, "START_ENGINE": {"after": 0,
                                                             "reply": FOUND_BEHIND}})
    page.click('nav.side-rail button[data-view="database"]')
    page.click("#runtime-upgrade")
    page.clock.run_for(1000)

    page.evaluate("() => startEngineFromPanel()")  # what each banner's Start calls
    page.clock.run_for(1000)
    assert "START_ENGINE" not in page.evaluate("window.__nativeCalls"), (
        "a Start ran beside the upgrade")
    assert page.text_content("#engine-note") == "Upgrading the database…"


def test_the_card_under_a_wait_does_not_say_press_again(open_panel):
    """Run is the main road here: Start, blocked, the card's Upgrade. When the upgrade
    times out and the file still reads behind, the note says to wait -- and the card
    under it said "use the Upgrade database button", with the button live."""
    page = open_panel(engine_up=False, record=("engine-note",), host={
        "START_ENGINE": {"after": 0, "reply": FOUND_BEHIND},
        "UPGRADE_DATABASE": {"after": None},
        "CHECK_STARTUP": {"after": 0, "reply": FOUND_BEHIND}})
    page.click('nav.side-rail button[data-view="run"]')
    page.click("#engine-start")
    page.clock.run_for(1000)
    page.locator("#engine-error [data-runtime-upgrade]").click()

    page.clock.run_for(FOREVER_MS)
    wait_for_text(page, "engine-note", WAIT)
    assert not page.locator("#engine-error").is_visible(), (
        "the card still tells him to press Upgrade under a note that says to wait: "
        + page.text_content("#engine-error"))


# ---- Restart engine -----------------------------------------------------------

def press_restart(open_panel, host: dict, **stub_kwargs):
    page = open_panel(host=host, record=("engine-restart-note", "runtime-note"),
                      **stub_kwargs)
    page.click('nav.side-rail button[data-view="engines"]')
    page.click('#view-engines .engine-row[data-engine-id="scrapex-engine"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)", timeout=10_000)
    page.evaluate("() => { window.__writes.length = 0; }")
    page.click("#runtime-restart")
    return page


def restart_posts(page) -> list:
    return [w for w in page.evaluate("window.__writes")
            if w["path"] == "/api/engine/restart"]


def test_restart_with_no_engine_running_says_so_and_waits_for_nothing(open_panel):
    """#1094's second fault: the refused POST was read as the engine leaving, and
    the panel then waited two minutes for an engine nobody was starting."""
    page = press_restart(open_panel, engine_up=False,
                         host={"CHECK_STARTUP": {"after": 0, "reply": FOUND_CURRENT}})

    page.clock.run_for(3 * 60_000)
    assert restart_posts(page) == [], "a restart was sent to an engine that is not there"
    wait_for_text(page, "engine-restart-note", "No engine is running")
    history = said(page, "engine-restart-note")
    assert history[-1] == ("No engine is running, so there is nothing to restart. "
                           "Start it on the Run page."), history
    assert not [t for t in history if "Restarting" in t or "two minutes" in t], (
        f"the panel announced or waited for a restart that was never sent: {history}")
    assert not page.locator("#runtime-restart").is_disabled()


# THE ENGINE TAKES THE RESTART AND DOES NOT COME BACK: the POST is answered, and every
# health probe after it is refused.
NEVER_BACK = """() => {
  const real = window.fetch;
  let restarted = false;
  window.fetch = (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/api/engine/restart")) {
      restarted = true;
      window.__writes.push({path: "/api/engine/restart", method: "POST", body: null});
      return Promise.resolve(new Response("{}", {status: 200,
        headers: {"Content-Type": "application/json"}}));
    }
    if (restarted && path.includes("/api/health")) {
      return Promise.reject(new TypeError("Failed to fetch"));
    }
    return real(url, options);
  };
}"""


def test_after_two_quiet_minutes_the_check_is_said_and_not_called_unavailable(open_panel):
    """The check at the END of the restart poll has the scan's two minutes now, not
    five seconds -- so it is said while it runs, the buttons stay down, and running
    out is not "the local helper is unavailable"."""
    page = open_panel(host={"CHECK_STARTUP": {"after": 0, "reply": FOUND_CURRENT}},
                      record=("engine-restart-note",))
    page.evaluate(NEVER_BACK)
    page.click('nav.side-rail button[data-view="engines"]')
    page.click('#view-engines .engine-row[data-engine-id="scrapex-engine"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)", timeout=10_000)
    page.click("#runtime-restart")
    page.clock.run_for(1000)
    # From here the host goes silent: the check at the end of the poll never answers.
    page.evaluate("""() => { window.chrome.runtime.sendNativeMessage =
        (_h, message) => { window.__nativeCalls.push(message.command); }; }""")

    page.clock.run_for(130_000)
    wait_for_text(page, "engine-restart-note", "Checking the database…")
    assert page.locator("#runtime-restart").is_disabled(), (
        "Restart came back while the check it is waiting on was still running")
    page.clock.run_for(FOREVER_MS)
    wait_for_text(page, "engine-restart-note", "the database check did not answer either")

    history = said(page, "engine-restart-note")
    assert not [t for t in history if "unavailable" in t], history
    assert not page.locator("#runtime-restart").is_disabled()


def test_overlapping_ticks_end_the_restart_once(open_panel):
    """A refused connection to 127.0.0.1 measured up to 2 s here, against the poll's
    1 s interval, so ticks overlap -- and every one still in flight at the end ran
    the whole ending, each with a two-minute scan of the warehouse."""
    page = open_panel(host={"CHECK_STARTUP": {"after": 0, "reply": FOUND_CURRENT}},
                      record=("engine-restart-note",))
    page.evaluate(NEVER_BACK.replace(
        'return Promise.reject(new TypeError("Failed to fetch"));',
        'return new Promise((_ok, no) => setTimeout(() => no(new TypeError("refused")), 2000));'))
    page.click('nav.side-rail button[data-view="engines"]')
    page.click('#view-engines .engine-row[data-engine-id="scrapex-engine"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)", timeout=10_000)
    page.click("#runtime-restart")
    page.clock.run_for(1000)
    page.evaluate("() => { window.__nativeCalls.length = 0; }")

    page.clock.run_for(135_000)
    page.clock.run_for(5_000)
    checks = [c for c in page.evaluate("window.__nativeCalls") if c == "CHECK_STARTUP"]
    assert checks == ["CHECK_STARTUP"], (
        f"the restart's ending ran {len(checks)} times, each a full scan: {checks}")


def test_a_slow_answer_from_the_engine_that_came_back_is_taken_once(open_panel):
    """The other half of the same overlap: when the successor answers, every tick
    still in flight sees it answer, and each said "The engine is back." and redrew
    the panel."""
    page = open_panel(host={"CHECK_STARTUP": {"after": 0, "reply": FOUND_CURRENT}},
                      record=("engine-restart-note",))
    page.evaluate(NEVER_BACK.replace(
        'return Promise.reject(new TypeError("Failed to fetch"));',
        'return new Promise((ok) => setTimeout(ok, 2000)).then(() => real(url, options));'))
    page.click('nav.side-rail button[data-view="engines"]')
    page.click('#view-engines .engine-row[data-engine-id="scrapex-engine"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)", timeout=10_000)
    page.click("#runtime-restart")

    page.clock.run_for(10_000)
    wait_for_text(page, "engine-restart-note", "The engine is back.")
    page.clock.run_for(5_000)
    back = [t for t in said(page, "engine-restart-note") if t == "The engine is back."]
    assert len(back) == 1, f"the restart was ended {len(back)} times"


def test_a_preflight_as_slow_as_his_is_waited_for(open_panel):
    """66.8 s cold, and the five seconds it had sent Restart round the check."""
    page = press_restart(open_panel, host={
        "CHECK_STARTUP": {"after": SLOWEST_CHECK_MS, "reply": FOUND_CURRENT}})

    page.clock.run_for(SLOWEST_CHECK_MS - 1000)
    assert restart_posts(page) == [], (
        "Restart went round the database check before the time his check took")
    assert page.text_content("#engine-restart-note") == (
        "Checking the database before restarting…")
    page.clock.run_for(2000)
    page.wait_for_function(
        "() => window.__writes.some(w => w.path === '/api/engine/restart')", timeout=5000)

    history = said(page, "engine-restart-note")
    assert not [t for t in history if "unavailable" in t or "did not answer" in t], (
        f"a check that answered was reported as missing: {history}")


def test_a_preflight_that_never_answers_is_called_slow_not_unavailable(open_panel):
    page = press_restart(open_panel, host={"CHECK_STARTUP": {"after": None}})

    page.clock.run_for(FOREVER_MS)
    page.wait_for_function(
        "() => window.__writes.some(w => w.path === '/api/engine/restart')", timeout=5000)

    history = said(page, "engine-restart-note")
    assert [t for t in history if t.startswith("The database check did not answer after ")
            and t.endswith("— restarting through the engine.")], history
    assert not [t for t in history if "unavailable" in t], (
        f"a helper that was still scanning was called unavailable: {history}")


# ---- Start engine -------------------------------------------------------------

def press_start(open_panel, host: dict):
    page = open_panel(host=host, record=("engine-note",), engine_up=False)
    page.click('nav.side-rail button[data-view="run"]')
    page.wait_for_selector("#engine-start", state="visible")
    page.click("#engine-start")
    return page


def test_a_start_as_slow_as_his_is_not_sent_to_setup(open_panel):
    """START_ENGINE runs the same scan first, so 66.8 s plus its 3.5 s confirm was
    already past the 60 s it had -- and running out said "Check Setup below"."""
    page = press_start(open_panel, host={
        "START_ENGINE": {"after": SLOWEST_START_MS, "reply": {"ok": True,
                                                              "confirmed": False}}})

    page.clock.run_for(SLOWEST_START_MS + 1000)
    page.clock.run_for(90_000)

    history = said(page, "engine-note")
    assert not [t for t in history if "Setup" in t], (
        f"a start that was answered was blamed on the installation: {history}")


def test_a_start_that_never_answers_says_it_may_still_be_starting(open_panel):
    page = press_start(open_panel, host={"START_ENGINE": {"after": None}})

    page.clock.run_for(FOREVER_MS)
    wait_for_text(page, "engine-note", "No answer from the helper after ")

    note = page.text_content("#engine-note")
    assert note.endswith("The engine may still be starting — press Check again in a "
                         "few seconds."), note
    assert "Setup" not in note
    # Eight sentences of this change land here; a screen reader hears them only if
    # the node is a live region, as `#engine-error` under it already is.
    assert page.get_attribute("#engine-note", "role") == "status"


# ---- Erase data -----------------------------------------------------------------

# THE ENGINE'S ERASE, ANSWERING AS SLOWLY AS HIS DID, held on the page's clock and given
# up when the panel's deadline aborts it -- as the upgrade door's double above is.
SLOW_ERASE = """(after) => {
  const real = window.fetch;
  window.fetch = (url, options = {}) => {
    if (!String(url).endsWith("/wipe")) return real(url, options);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(new Response(JSON.stringify({ok: true,
        detail: "Erased 1,046 rows. Backed up first."}),
        {status: 200, headers: {"Content-Type": "application/json"}})), after);
      if (options.signal) options.signal.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(options.signal.reason);
      }, {once: true});
    });
  };
  window.prompt = () => "ERASE";
}"""


def test_an_erase_as_slow_as_his_is_shown_its_answer(open_panel):
    """THE THIRD SURFACE OF #1706. Erase data copies the warehouse before it deletes,
    and inherited a page of rows' 5,000 ms: he read "The request exceeded its 5000 ms
    deadline." three times, pressed three times, and three 2.2 GB copies were made."""
    page = open_panel(host={}, record=("source-edit-danger-result",))
    page.evaluate(SLOW_ERASE, SLOWEST_ERASE_MS)
    page.click('nav.side-rail button[data-view="sources"]')
    page.click('[data-edit-source="SHORT"]')
    page.wait_for_selector("#view-source-edit", state="visible")
    page.click("#source-edit-wipe")

    page.clock.run_for(SLOWEST_ERASE_MS + 1000)
    history = said(page, "source-edit-danger-result")
    assert not [t for t in history if "deadline" in t], (
        f"Erase data gave up before the time his own erase took: {history}")
    wait_for_text(page, "source-edit-danger-result", "Erased 1,046 rows.")
