"""The tender control, drawn in the real panel (milestone 51, part 3b-2b; #1701, confirmed 2026-10-19).

Every state here is one the confirmed design draws, through `tools/panel_harness.py`, at the three
widths his panel is studied at (320, 400 and 480 px). The engine's side is the engine's own code
wherever it can be: the source row's sentences and the cost question come from `tenders` and
`tenderjob`, so this stub cannot drift from what the route answers
(`tests/test_the_tender_control_reaches_the_engine.py` holds the route to the same functions).

POST /api/jobs is answered by a script laid over the harness's fetch, in the route's order: a mix,
a crawl not settled, then the cost question, which queues nothing until its figure is accepted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
pytest.importorskip("playwright", reason="needs the browser extra")
import panel_harness as harness  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from scrapex import tenderjob, tenders  # noqa: E402
from scrapex.vocab import RunMode  # noqa: E402

WIDTHS = (320, 400, 480)
WB_SOURCE = tenders.get("worldbank_org")
HOST = WB_SOURCE.host
NOTHING_HELD = tenderjob.SourceState(count=None, areas_read=frozenset(), first_counted_at=None,
                                     held_whole_at=None)
#: The question an initial crawl of a source holding nothing asks, in the engine's own words.
COST_FIRST = tenderjob.cost(NOTHING_HELD, WB_SOURCE, RunMode.INITIAL_CRAWL.value,
                            WB_SOURCE.crawl_pace_s)
WB = {"kind": "tender", "site_key": "worldbank_org", "source_key": "worldbank_org",
      "source_name": WB_SOURCE.display_name, "source_name_ar": "",
      "base_url": WB_SOURCE.base_url, "family": "generic", "implemented": True,
      "supports_history": False, "runs_blocked": WB_SOURCE.runs_blocked,
      "observations": 0, "products": 0, "last_success": None, "kept_pages": 0, "kept_at": None}
#: Egypt's measured store (#1658): 944 tenders.
WB_DATA = dict(WB, observations=944, products=944)
WB_PARTIAL = dict(WB_DATA, first_crawl={"read": 41, "of": 184, "unit": "areas",
                                        "stopped_at": "2026-10-13T16:30:00Z"})
SOURCES = harness.STRESS_SOURCES + [WB]
MIXED = f"{HOST} collects tenders and runs on its own. Start a.co separately."
DUPLICATE = f"{HOST} already has a crawl that has not finished. Follow or cancel it on Jobs."


def tender_job(status, *, ref="job_7c1e2a90b4d1", done=0, total=0, unit="areas", requests=0,
               expected=None, notices=0, new=None, unchanged=0, errors=0):
    """One `tender_crawl` job as `_job_view` reports it. Every notice is new unless `new` says
    otherwise."""
    return {"job_ref": ref, "job_kind": tenderjob.JOB_KIND, "status": status,
            "source_keys": ["worldbank_org"], "current_source_key": "worldbank_org",
            "stage": "reading Kenya" if status == "running" else None,
            "created_at": "2026-10-14T12:00:00Z", "started_at": "2026-10-14T12:00:00Z",
            "finished_at": None, "updated_at": "2026-10-14T12:20:00Z",
            "progress": {"done": done, "total": total, "unit": unit},
            "fetch": {"requests": requests, "expected": expected,
                      "basis": "declared" if expected else None,
                      **({"counted_from": tenderjob.COUNTED_FROM} if expected else {}),
                      "sources": {"worldbank_org": {"state": "fetching", "requests": requests,
                                                    "pace_s": 2.5, "retries": 0}}},
            "counters": {"notices": notices, "releases_new": notices if new is None else new,
                         "releases_unchanged": unchanged, "errors": errors},
            "error_summary": None, "queued_behind": None}


PRICE_RUNNING = {"job_ref": "job_6be2c94a07f1", "job_kind": "crawl", "status": "running",
                 "source_keys": ["LONG_AR"], "current_source_key": "LONG_AR", "stage": None,
                 "created_at": "2026-10-14T12:00:00Z", "started_at": "2026-10-14T12:00:00Z",
                 "finished_at": None, "updated_at": "2026-10-14T12:20:00Z",
                 "progress": {"done": 0, "total": 1}, "fetch": {"requests": 3},
                 "counters": {}, "error_summary": None, "queued_behind": None}


def engine(*, cost=None, mixed=False, duplicate=False, moves=0, hold=False, writes=None,
           fail=False):
    """POST /api/jobs as the route answers it, laid over the harness's fetch. `window.__posts`
    holds every body sent. `moves` is how far the figure moves at the first acceptance, as a
    count taken again would; `fail` drops the connection the way Chrome does, a TypeError.

    `hold` keeps every answer until the test sets `window.__release`, so a test waits for what
    it needs rather than for a clock; and, as fetch does, the request rejects when the panel's
    own deadline aborts it first. `writes` is a job the engine writes before it answers, into
    the harness's job list. `window.__polls` counts the panel's polls of that list, and
    `window.__pollsAtPost` holds the count when the last press arrived."""
    return """(() => { window.__posts = []; window.__polls = 0; const real = window.fetch;
      window.fetch = async (u, o = {}) => {
        const answer = (status, payload) => ({ok: status < 300, status,
          statusText: String(status), json: async () => payload});
        const method = o.method || 'GET';
        const path = String(u).replace(/^https?:\\/\\/[^/]+/, '');
        if (method === 'GET' && path.startsWith('/api/jobs?')) window.__polls += 1;
        if (!(path.startsWith('/api/jobs') && method === 'POST' && !path.includes('/control')))
          return real(u, o);
        const body = JSON.parse(o.body || '{}'); window.__posts.push(body);
        window.__pollsAtPost = window.__polls;
        const written = %(writes)s;
        if (written) ROUTES['/api/jobs'].jobs.push(written);
        if (%(hold)s) await new Promise((resolve, reject) => {
          const held = setInterval(() => {
            if (window.__release) { clearInterval(held); resolve(); } }, 20);
          if (o.signal) o.signal.addEventListener('abort', () => {
            clearInterval(held); reject(o.signal.reason); }, {once: true});
        });
        if (%(fail)s) throw new TypeError('Failed to fetch');
        if (%(mixed)s && body.source_keys.length > 1) return answer(400, {detail: %(mixed_detail)s});
        if (%(duplicate)s) return answer(409, {detail: %(duplicate_detail)s});
        if (window.__cost === undefined) window.__cost = %(cost)s;
        const cost = window.__cost;
        if (cost && body.accept_cost && !window.__moved && %(moves)d) {
          window.__moved = true; cost.requests += %(moves)d; cost.counted_at = '2026-10-14'; }
        if (cost && !(body.accept_cost && body.accept_cost.requests === cost.requests))
          return answer(409, {question: 'cost', detail: 'confirm the cost to start', cost});
        return answer(200, {job_ref: 'job_7c1e2a90b4d1', status: 'queued'});
      }; })()""" % {"hold": json.dumps(hold), "writes": json.dumps(writes),
                    "fail": json.dumps(fail), "mixed": json.dumps(mixed),
                    "mixed_detail": json.dumps(MIXED), "duplicate": json.dumps(duplicate),
                    "duplicate_detail": json.dumps(DUPLICATE), "cost": json.dumps(cost),
                    "moves": moves}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def panel(browser, tmp_path):
    pages = []

    def opener(*, width=400, height=800, view="run", script=None, **stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"panel{len(pages)}.html")
        page = browser.new_page(viewport={"width": width, "height": height})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(page_file.as_uri())
        harness.wait_until_settled(page)
        if script:
            page.evaluate(script)
        page.click(f'nav.side-rail button[data-view="{view}"]')
        page.wait_for_selector(f"#view-{view}", state="visible")
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def text(page, selector):
    return (page.text_content(selector) or "").strip()


def tick(page, key):
    page.click(f'#sites input[data-key="{key}"]')


def choose_mode(page, mode):
    page.evaluate("(mode) => { const s = document.getElementById('run-mode'); s.value = mode;"
                  " s.dispatchEvent(new Event('change')); }", mode)


def press_start(page):
    """From the keyboard, as the study drew the question, so its focus is real."""
    page.focus("#run")
    page.keyboard.press("Enter")


def asking(page):
    return page.evaluate("() => !document.getElementById('confirm-veil').classList.contains('hidden')")


def wait_asking(page):
    page.wait_for_function("() => !document.getElementById('confirm-veil').classList.contains('hidden')")


def posts(page):
    return page.evaluate("window.__posts")


def facts(page):
    return page.evaluate("""() => [...document.querySelectorAll('#confirm-facts .kv')].map(
        (row) => [row.querySelector('dt').textContent, row.querySelector('dd').textContent])""")


def no_horizontal_overflow(page):
    return page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def counters(page):
    """Activity's figures as label and value pairs, as `.kv` rows draw them."""
    page.wait_for_function("() => document.querySelectorAll('#act-counters .kv').length")
    return dict(page.evaluate("""() => [...document.querySelectorAll('#act-counters .kv')].map(
        (row) => [...row.children].slice(0, 2).map((cell) => cell.textContent.trim()))"""))


def focused(page):
    return page.evaluate("() => document.activeElement && document.activeElement.id")


def focus_in_view(page):
    """Whether what holds focus lies inside what the question's card shows."""
    return page.evaluate("""() => { const a = document.activeElement.getBoundingClientRect();
        const box = document.getElementById('confirm-dialog').getBoundingClientRect();
        return a.top >= Math.max(0, box.top) && a.bottom <= Math.min(innerHeight, box.bottom); }""")


def ask(page):
    """Tick the World Bank, choose an initial crawl, and press Start from the keyboard."""
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)


REFUSED = "() => document.getElementById('run-refused').textContent !== ''"
#: The display zone pinned, so a stored time reads the same on every machine (UTC+3).
RIYADH = {"zone": "Asia/Riyadh", "updatedAt": 9_999_999_999_999}


# ---- Run: the row, the modes and the note (rows 1-6, 11-13) ------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_the_world_bank_is_on_run_with_its_tenders_and_no_auto_switch(panel, width):
    page = panel(width=width, sources=harness.STRESS_SOURCES + [WB_DATA])
    row = page.locator('#sites .srow:has(input[data-key="worldbank_org"])')
    assert HOST in row.inner_text() and "944" in row.inner_text()
    # NOTHING UNATTENDED MEETS THE COST QUESTION: no Auto switch on a tender row.
    assert row.locator(".chip, [role='switch']").count() == 0
    tick(page, "worldbank_org")
    assert "Tenders" in text(page, "#selected") and "Dataset" not in text(page, "#selected")
    # ROW 6: "Tenders 944", the label and the source's own count beside it.
    assert page.evaluate("""() => [...document.querySelectorAll('#selected .kv')]
        .filter((row) => row.children[0].textContent === 'Tenders')
        .map((row) => row.children[1].textContent)""") == ["944"]
    assert no_horizontal_overflow(page) and not page.js_errors


@pytest.mark.parametrize("width", WIDTHS)
def test_a_first_crawl_that_stopped_partway_is_said_on_its_row_and_under_the_modes(panel, width):
    page = panel(width=width, sources=harness.STRESS_SOURCES + [WB_PARTIAL], timezone=RIYADH)
    row = text(page, '#sites .srow:has(input[data-key="worldbank_org"])')
    # ROW 13, WITH WHEN IT STOPPED: 16:30 UTC is 7:30 PM in the zone pinned above.
    assert ("41 of 184 areas read when the last crawl stopped 13 Oct, 7:30 PM."
            in " ".join(row.split()))
    assert "An update reads the other 143 first." in " ".join(row.split())
    tick(page, "worldbank_org")
    help_text = text(page, "#mode-help")
    assert (f"Update finishes the initial crawl of {HOST} first: 143 areas are not read yet."
            in help_text)
    # ROW 12: the note is INSTEAD of the one about data already held, which would read as if
    # nothing were left of the first crawl.
    assert "a first crawl is not on offer" not in help_text
    assert no_horizontal_overflow(page) and not page.js_errors


def test_a_row_says_nothing_of_a_first_crawl_the_engine_did_not_send(panel):
    page = panel(sources=harness.STRESS_SOURCES + [WB_DATA])
    assert "areas read" not in text(page, '#sites .srow:has(input[data-key="worldbank_org"])')


def test_full_rebuild_is_off_with_the_engines_sentence_where_it_would_be_offered(panel):
    page = panel(sources=harness.STRESS_SOURCES + [WB_DATA])
    tick(page, "worldbank_org")
    assert page.evaluate("() => document.querySelector('#run-mode option[value=\"full_rebuild\"]')"
                         ".disabled")
    assert WB_SOURCE.runs_blocked["full_rebuild"] in text(page, "#mode-help")


def test_a_source_holding_nothing_says_nothing_of_a_rebuild_it_could_not_have(panel):
    """Said only where it changes what is offered: a source with no data has no rebuild on offer
    anyway, and the sentence is noise at 320 px."""
    page = panel(sources=SOURCES)
    tick(page, "worldbank_org")
    assert WB_SOURCE.runs_blocked["full_rebuild"] not in text(page, "#mode-help")


# ---- Start: the cost question (rows 7-10) -------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_start_asks_the_engines_cost_question_and_confirming_sends_its_figure(panel, width):
    page = panel(width=width, sources=SOURCES, script=engine(cost=COST_FIRST))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)
    assert text(page, "#confirm-title") == f"Initial crawl · {HOST}"
    assert text(page, "#confirm-copy") == f"{COST_FIRST['reads']} {COST_FIRST['basis']}"
    assert facts(page) == [["Requests", "about 537"], ["Time", "at least 22 minutes"],
                           ["Pace", "2.5s between requests"], ["Counted on", "10 Oct 2026"]]
    assert text(page, "#confirm-go") == "Start initial crawl"
    # ROW 10: in the primary tone, the empty variant; `danger` is for what cannot be undone.
    assert page.get_attribute("#confirm-go", "class") == ""
    assert no_horizontal_overflow(page)
    page.click("#confirm-go")
    page.wait_for_function("() => window.__posts.length === 2")
    assert posts(page)[1]["accept_cost"] == {"requests": 537}
    assert posts(page)[1]["source_keys"] == ["worldbank_org"]
    page.wait_for_function("() => document.activeElement === document.getElementById('run')")
    assert not asking(page) and not text(page, "#run-refused") and not page.js_errors


def test_the_figures_are_pairs_outside_the_description(panel):
    """A screen reader reads a description as one string: the figures are a <dl> of their own."""
    page = panel(sources=SOURCES, script=engine(cost=COST_FIRST))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)
    assert page.get_attribute("#confirm-dialog", "aria-describedby") == "confirm-copy"
    assert "537" not in text(page, "#confirm-copy")
    assert page.evaluate("() => document.getElementById('confirm-facts').tagName") == "DL"


@pytest.mark.parametrize("answer", ["cancel", "escape"])
def test_cancelling_the_question_sends_nothing_more(panel, answer):
    page = panel(sources=SOURCES, script=engine(cost=COST_FIRST))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)
    if answer == "cancel":
        page.click("#confirm-keep")
    else:
        page.keyboard.press("Escape")
    page.wait_for_function("() => document.activeElement === document.getElementById('run')")
    page.wait_for_timeout(300)
    assert len(posts(page)) == 1 and not asking(page)


def test_a_moved_figure_is_asked_again_naming_both(panel):
    page = panel(sources=SOURCES, script=engine(cost=COST_FIRST, moves=3))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)
    page.click("#confirm-go")
    page.wait_for_function("() => window.__posts.length === 2")
    wait_asking(page)
    assert text(page, "#confirm-copy").startswith(
        "The figure changed from about 537 to about 540 requests. ")
    assert ["Counted on", "14 Oct 2026"] in facts(page)
    page.click("#confirm-go")
    page.wait_for_function("() => window.__posts.length === 3")
    assert posts(page)[2]["accept_cost"] == {"requests": 540}


@pytest.mark.parametrize("requests, time", [(2, "at least 2 seconds"), (1, None)])
def test_time_is_the_wait_between_the_requests_and_is_left_out_under_a_second(panel, requests,
                                                                               time):
    """Row 8: Time is the panel's arithmetic, (requests - 1) x pace, a floor, and is left out
    under a second. At 537 requests the -1 cannot show: 536 and 537 paces of 2.5 s both floor
    to 22 minutes."""
    page = panel(sources=SOURCES, script=engine(cost=dict(COST_FIRST, requests=requests)))
    ask(page)
    assert dict(facts(page)).get("Time") == time


def test_the_same_figure_asked_again_is_a_refusal_not_a_trap(panel):
    """An engine that asks again about the figure he accepted would return whatever he answers."""
    cost = dict(COST_FIRST)
    page = panel(sources=SOURCES, script=engine(cost=cost) + "; window.__keepAsking = true")
    page.evaluate("""() => { const prior = window.fetch; window.fetch = async (u, o = {}) => {
        const r = await prior(u, o);
        if ((o.method || 'GET') === 'POST' && String(u).includes('/api/jobs') && r.ok)
          return {ok: false, status: 409, statusText: '409', json: async () => (
            {question: 'cost', detail: 'confirm the cost to start', cost: window.__cost})};
        return r; }; }""")
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)
    page.click("#confirm-go")
    page.wait_for_function("() => document.getElementById('run-refused').textContent !== ''")
    assert text(page, "#run-refused") == (
        "Couldn't start: the engine asked again about the 537 requests already accepted.")
    assert len(posts(page)) == 2 and not asking(page)


def test_a_question_missing_a_figure_is_refused_with_what_it_lacks(panel):
    page = panel(sources=SOURCES, script=engine(cost={k: v for k, v in COST_FIRST.items()
                                                       if k != "pace_s"}))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    page.wait_for_function("() => document.getElementById('run-refused').textContent !== ''")
    assert text(page, "#run-refused") == ("Couldn't start: the engine's cost question has no "
                                          "usable pace_s.")
    assert not asking(page)


@pytest.mark.parametrize("width, height, first", [
    (320, 320, "confirm-title"), (400, 320, "confirm-keep"), (480, 320, "confirm-keep"),
    (320, 800, "confirm-keep")])
def test_the_question_focuses_its_title_only_where_cancel_would_scroll_it_away(
        panel, width, height, first):
    """Row 7: the APG Dialog (Modal) pattern's note on initial focus, where Supabase's atom leaves
    focus on a Cancel out of view."""
    page = panel(width=width, height=height, sources=SOURCES, script=engine(cost=COST_FIRST))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    press_start(page)
    wait_asking(page)
    assert focused(page) == first
    if first == "confirm-title":
        # FOCUS ON THE TITLE IS FOCUS AT THE TOP: nothing was scrolled to reach it.
        assert page.evaluate("() => document.getElementById('confirm-dialog').scrollTop") == 0
    assert focus_in_view(page)


def test_a_question_asked_again_opens_at_its_top(panel):
    """Row 7: every question opens scrolled to its top. The card stays in the page between
    questions, and kept the scroll the last one was left at, its title out of view."""
    page = panel(width=320, height=320, sources=SOURCES, script=engine(cost=COST_FIRST))
    ask(page)
    page.evaluate("() => { document.getElementById('confirm-dialog').scrollTop = 10000; }")
    assert page.evaluate("() => document.getElementById('confirm-dialog').scrollTop") > 0
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.activeElement === document.getElementById('run')")
    press_start(page)
    wait_asking(page)
    assert page.evaluate("() => document.getElementById('confirm-dialog').scrollTop") == 0
    assert focused(page) == "confirm-title"


def test_tab_brings_the_next_choice_into_view(panel):
    """Row 7: Tab scrolls the next button into view. At 320 x 320 the question opens on its
    title, with Cancel below what the card shows: focus there is focus he cannot see."""
    page = panel(width=320, height=320, sources=SOURCES, script=engine(cost=COST_FIRST))
    ask(page)
    assert focused(page) == "confirm-title"
    page.keyboard.press("Tab")
    assert focused(page) == "confirm-keep" and focus_in_view(page)


def test_start_stays_disabled_while_the_engine_answers(panel):
    """The study's probe: a price crawl running, so the 1.5 s tick redraws Start, and the engine
    answering late. The tick re-enabled Start, a second press posted a second job, and one
    behind an open question took its focus. The engine holds its answer until a tick has
    redrawn Start, so no clock decides whether the guard was tested."""
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING], script=engine(cost=COST_FIRST, hold=True))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    page.click("#run")
    # A TICK HAS REDRAWN START SINCE THE PRESS: `pollJobOnce` draws, then schedules the next
    # poll, so the second poll after the press starts only once the first has drawn.
    page.wait_for_function("() => window.__posts.length === 1"
                           " && window.__polls >= window.__pollsAtPost + 2")
    assert page.is_disabled("#run"), "a tick re-enabled Start while the engine answered"
    page.click("#run", force=True)
    page.evaluate("() => { window.__release = true; }")
    wait_asking(page)
    assert len(posts(page)) == 1


def test_focus_he_moves_while_the_engine_answers_stays_where_he_put_it(panel):
    """The sheet's measured press (round 11): focus he moves away from Start while the engine
    answers is not pulled back to it, so a Space after the answer presses nothing."""
    page = panel(sources=SOURCES, script=engine(mixed=True, hold=True))
    tick(page, "worldbank_org")
    tick(page, "SHORT")
    press_start(page)
    page.wait_for_function("() => window.__posts.length === 1")
    page.focus("#site-search")
    page.evaluate("() => { window.__release = true; }")
    page.wait_for_function(REFUSED)
    assert focused(page) == "site-search"


# ---- refusals and the hint (rows 14-15) --------------------------------------------------------

def test_a_refusal_stands_through_the_polls_and_clears_when_the_selection_changes(panel):
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING], script=engine(mixed=True))
    tick(page, "worldbank_org")
    tick(page, "SHORT")
    page.click("#run")
    page.wait_for_function("() => document.getElementById('run-refused').textContent !== ''")
    assert text(page, "#run-refused") == f"Couldn't start: {MIXED}"
    page.wait_for_timeout(3_600)
    assert text(page, "#run-refused") == f"Couldn't start: {MIXED}"
    # NO HINT BESIDE IT: it would promise the queue the engine has just refused.
    assert text(page, "#run-blocked") == ""
    assert page.get_attribute("#run-refused", "role") == "status"
    tick(page, "SHORT")
    page.wait_for_function("() => document.getElementById('run-refused').textContent === ''")


def test_a_refusal_clears_when_the_mode_changes(panel):
    """Row 14: a refusal stays until the selection OR THE MODE changes after it arrives."""
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING], script=engine(mixed=True))
    tick(page, "worldbank_org")
    tick(page, "SHORT")
    page.click("#run")
    page.wait_for_function(REFUSED)
    other = page.evaluate("""() => { const select = document.getElementById('run-mode');
        const option = [...select.options].find((o) => !o.disabled && o.value !== select.value);
        return option ? option.value : null; }""")
    assert other, "no other mode is on offer for this selection"
    choose_mode(page, other)
    page.wait_for_function("() => document.getElementById('run-refused').textContent === ''")


@pytest.mark.parametrize("status", ["running", "paused", "queued"])
def test_the_hint_names_a_tender_crawl_not_settled_at_any_status(panel, status):
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING, tender_job(status)])
    tick(page, "worldbank_org")
    page.wait_for_function("() => document.getElementById('run-blocked').textContent !== ''")
    assert text(page, "#run-blocked") == f"{HOST} already has a crawl that has not finished."


@pytest.mark.parametrize("key", ["SHORT", "LONG_AR"])
def test_every_other_source_keeps_the_queue_sentence(panel, key):
    """Row 15: every source but a tender source keeps the queue sentence, which the engine
    honours for it. LONG_AR is the source of the price crawl running here: a second price
    crawl of it queues, so it is the source a rule for every busy source would get wrong."""
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING, tender_job("paused")])
    tick(page, key)
    page.wait_for_function("() => document.getElementById('run-blocked').textContent !== ''")
    assert text(page, "#run-blocked") == "A job is already running. It will queue behind it."


def test_a_press_whose_connection_fails_is_no_answer_not_a_refusal(panel):
    page = panel(sources=SOURCES, script=engine(fail=True))
    tick(page, "worldbank_org")
    page.click("#run")
    page.wait_for_function("() => document.getElementById('run-refused').textContent !== ''")
    assert text(page, "#run-refused") == ("No answer to Start: the connection to the engine "
                                          "failed. If the engine started the run, Activity "
                                          "shows it.")


def test_a_press_past_its_deadline_is_no_answer_polls_once_and_keeps_the_hint(panel):
    """Rows 14 and 15, state 09f: a press the engine did not answer within its deadline is not
    a refusal. The engine writes the job before it answers, so the panel says it had no answer,
    asks once whether a job appeared, and draws the hint that job calls for. No job ran before
    the press, so no tick would have found it."""
    page = panel(sources=SOURCES, script=engine(
        hold=True, writes=tender_job("running", done=1, total=184)))
    tick(page, "worldbank_org")
    page.click("#run")
    page.wait_for_function(REFUSED, timeout=15_000)
    assert text(page, "#run-refused") == (
        "No answer to Start: the request exceeded its 5000 ms deadline. If the engine started "
        "the run, Activity shows it.")
    page.wait_for_selector("#activity:not(.hidden)", timeout=5_000)
    page.wait_for_function("() => document.getElementById('run-blocked').textContent !== ''",
                           timeout=5_000)
    assert text(page, "#run-blocked") == f"{HOST} already has a crawl that has not finished."


def test_the_engines_duplicate_refusal_is_said_in_its_words(panel):
    page = panel(sources=SOURCES, script=engine(duplicate=True))
    tick(page, "worldbank_org")
    page.click("#run")
    page.wait_for_function("() => document.getElementById('run-refused').textContent !== ''")
    assert text(page, "#run-refused") == f"Couldn't start: {DUPLICATE}"


# ---- following the crawl (rows 17-25) -----------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_activity_counts_a_tender_crawl_in_its_own_unit(panel, width):
    # ROWS 19-20, FOUR FIGURES THAT DIFFER, so none can stand in for another.
    job = tender_job("running", done=41, total=184, requests=318, expected=537, notices=95_120,
                     new=1_204, unchanged=93_900, errors=16)
    page = panel(width=width, sources=SOURCES, jobs=[job])
    page.wait_for_selector("#activity:not(.hidden)")
    figures = counters(page)
    # NO-BREAK SPACES keep the fraction whole where `.kv` lets a value shrink below a word.
    assert figures["Areas read"] == "41 / 184"
    assert figures["Notices read"] == "95,120" and figures["New or changed"] == "1,204"
    assert figures["Unchanged"] == "93,900" and figures["Errors"] == "16"
    assert "Sites done" not in figures
    assert "counted from the Bank's notice totals" in text(page, "#act-progress-label")
    assert no_horizontal_overflow(page) and not page.js_errors


def test_the_pass_over_changes_counts_pages_with_no_total(panel):
    job = tender_job("running", done=3, total=0, unit="pages", requests=40)
    page = panel(sources=SOURCES, jobs=[job])
    assert counters(page)["Pages read"] == "3"
    assert "counted from" not in text(page, "#act-progress-label")


def test_jobs_labels_a_tender_crawl(panel):
    page = panel(view="jobs", sources=SOURCES, jobs=[tender_job("running", done=1, total=184)])
    page.wait_for_function("() => document.getElementById('view-jobs').textContent"
                           ".includes('Tender crawl')")


# ---- Data and Schedules (rows 26, and round six's h) -------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_data_draws_the_tender_source_with_no_link_and_no_menu(panel, width):
    """A link would open a page that cannot show tenders (`CLAUDE.md`: if the route 404s, do not
    draw the control), and every item of the card's menu acts on a dataset or a price source."""
    page = panel(width=width, view="data", sources=harness.STRESS_SOURCES + [WB_DATA])
    page.wait_for_function("() => document.getElementById('datasets').textContent"
                           ".includes('No page shows tenders yet.')")
    card = page.locator("#datasets .dataset-card", has_text="No page shows tenders yet.")
    assert "944" in card.inner_text() and "Tenders" in card.inner_text()
    assert card.locator(".split-button, [role='link']").count() == 0
    assert card.get_attribute("data-open") is None
    assert page.locator('[data-open="worldbank_org"]').count() == 0
    assert no_horizontal_overflow(page) and not page.js_errors


def test_data_holding_only_tenders_draws_their_card_and_not_no_data(panel):
    page = panel(view="data", sources=[WB_DATA])
    page.wait_for_function("() => document.getElementById('datasets').textContent"
                           ".includes('No page shows tenders yet.')")
    assert "No data yet" not in text(page, "#datasets")


def test_data_draws_no_tender_card_before_a_tender_is_held(panel):
    page = panel(view="data", sources=harness.STRESS_SOURCES + [WB])
    # THE LIST IS DRAWN FIRST: every card comes in the one write, so once the others are there
    # an absent tender card is absent, not late.
    page.wait_for_function("() => document.querySelectorAll('#datasets .dataset-card').length")
    assert "No page shows tenders yet." not in text(page, "#datasets")


def test_schedules_names_the_tender_source_it_leaves_out(panel):
    page = panel(view="schedules", sources=harness.STRESS_SOURCES + [WB])
    page.wait_for_function("() => document.getElementById('sched-dir-note').textContent !== ''")
    assert text(page, "#sched-dir-note") == (
        f"Tender sources ({HOST}) can't be scheduled yet. Run them from the Run page.")


def test_schedules_names_directories_and_tender_sources_together(panel):
    directory = {"kind": "directory", "source_key": "muqawil_org", "site_key": "muqawil_org",
                 "source_name": "Muqawil", "base_url": "https://muqawil.org", "family": "generic",
                 "implemented": True, "observations": 0, "products": 0}
    page = panel(view="schedules", sources=harness.STRESS_SOURCES + [directory, WB])
    page.wait_for_function("() => document.getElementById('sched-dir-note').textContent !== ''")
    assert text(page, "#sched-dir-note") == (
        f"Directory sources (muqawil.org) and tender sources ({HOST}) can't be scheduled yet. "
        "Run them from the Run page.")
