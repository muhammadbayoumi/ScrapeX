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
               expected=None, notices=0):
    """One `tender_crawl` job as `_job_view` reports it."""
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
            "counters": {"notices": notices, "releases_new": notices, "releases_unchanged": 0,
                         "errors": 0},
            "error_summary": None, "queued_behind": None}


PRICE_RUNNING = {"job_ref": "job_6be2c94a07f1", "job_kind": "crawl", "status": "running",
                 "source_keys": ["LONG_AR"], "current_source_key": "LONG_AR", "stage": None,
                 "created_at": "2026-10-14T12:00:00Z", "started_at": "2026-10-14T12:00:00Z",
                 "finished_at": None, "updated_at": "2026-10-14T12:20:00Z",
                 "progress": {"done": 0, "total": 1}, "fetch": {"requests": 3},
                 "counters": {}, "error_summary": None, "queued_behind": None}


def engine(*, cost=None, mixed=False, duplicate=False, moves=0, delay_ms=0, fail=False):
    """POST /api/jobs as the route answers it, laid over the harness's fetch. `window.__posts`
    holds every body sent. `moves` is how far the figure moves at the first acceptance, as a
    count taken again would; `fail` drops the connection the way Chrome does, a TypeError."""
    return """(() => { window.__posts = []; const real = window.fetch;
      window.fetch = async (u, o = {}) => {
        const answer = (status, payload) => ({ok: status < 300, status,
          statusText: String(status), json: async () => payload});
        const method = o.method || 'GET';
        const path = String(u).replace(/^https?:\\/\\/[^/]+/, '');
        if (!(path.startsWith('/api/jobs') && method === 'POST' && !path.includes('/control')))
          return real(u, o);
        const body = JSON.parse(o.body || '{}'); window.__posts.push(body);
        if (%(delay)d) await new Promise((resolve) => setTimeout(resolve, %(delay)d));
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
      }; })()""" % {"delay": delay_ms, "fail": json.dumps(fail), "mixed": json.dumps(mixed),
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
    assert no_horizontal_overflow(page) and not page.js_errors


@pytest.mark.parametrize("width", WIDTHS)
def test_a_first_crawl_that_stopped_partway_is_said_on_its_row_and_under_the_modes(panel, width):
    page = panel(width=width, sources=harness.STRESS_SOURCES + [WB_PARTIAL])
    row = text(page, '#sites .srow:has(input[data-key="worldbank_org"])')
    assert "41 of 184 areas read when the last crawl stopped" in " ".join(row.split())
    assert "An update reads the other 143 first." in " ".join(row.split())
    tick(page, "worldbank_org")
    assert (f"Update finishes the initial crawl of {HOST} first: 143 areas are not read yet."
            in text(page, "#mode-help"))
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
    assert page.evaluate("() => document.getElementById('confirm-dialog').scrollTop") >= 0
    in_view = page.evaluate("""() => { const a = document.activeElement.getBoundingClientRect();
        const box = document.getElementById('confirm-dialog').getBoundingClientRect();
        return a.top >= Math.max(0, box.top) && a.bottom <= Math.min(innerHeight, box.bottom); }""")
    assert in_view


def test_start_stays_disabled_while_the_engine_answers(panel):
    """A second press posted a second job, and one behind an open question took its focus."""
    page = panel(sources=SOURCES, script=engine(cost=COST_FIRST, delay_ms=1_500))
    tick(page, "worldbank_org")
    choose_mode(page, "initial_crawl")
    page.click("#run")
    page.wait_for_timeout(300)
    assert page.is_disabled("#run")
    page.click("#run", force=True)
    wait_asking(page)
    assert len(posts(page)) == 1


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


@pytest.mark.parametrize("status", ["running", "paused", "queued"])
def test_the_hint_names_a_tender_crawl_not_settled_at_any_status(panel, status):
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING, tender_job(status)])
    tick(page, "worldbank_org")
    page.wait_for_function("() => document.getElementById('run-blocked').textContent !== ''")
    assert text(page, "#run-blocked") == f"{HOST} already has a crawl that has not finished."


def test_every_other_source_keeps_the_queue_sentence(panel):
    page = panel(sources=SOURCES, jobs=[PRICE_RUNNING, tender_job("paused")])
    tick(page, "SHORT")
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


def test_the_engines_duplicate_refusal_is_said_in_its_words(panel):
    page = panel(sources=SOURCES, script=engine(duplicate=True))
    tick(page, "worldbank_org")
    page.click("#run")
    page.wait_for_function("() => document.getElementById('run-refused').textContent !== ''")
    assert text(page, "#run-refused") == f"Couldn't start: {DUPLICATE}"


# ---- following the crawl (rows 17-25) -----------------------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_activity_counts_a_tender_crawl_in_its_own_unit(panel, width):
    job = tender_job("running", done=41, total=184, requests=318, expected=537, notices=95_120)
    page = panel(width=width, sources=SOURCES, jobs=[job])
    page.wait_for_selector("#activity:not(.hidden)")
    figures = counters(page)
    # NO-BREAK SPACES keep the fraction whole where `.kv` lets a value shrink below a word.
    assert figures["Areas read"] == "41 / 184"
    assert figures["Notices read"] == "95,120" and figures["New or changed"] == "95,120"
    assert figures["Unchanged"] == "0" and figures["Errors"] == "0"
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
    page.wait_for_timeout(300)
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
