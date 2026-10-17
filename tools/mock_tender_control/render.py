"""DRAFT TOOL, NOT FOR MERGE: the tender control's mock-up (milestone 51, part 2), seventh draft.

It renders the panel through tools/panel_harness.py with the part 3b engine stubbed as the
study's contract describes it. The study, its reference sheet and the review rounds are on
the STUDY issue; this file only regenerates the images it shows.

Usage, from the repository root:
    python tools/mock_tender_control/render.py . tools/mock_tender_control/world_facets.json <outdir> [state ...]
world_facets.json is #1647's request 12, saved as the Bank answered it.
Every state at 320, 400 and 480 px, light and dark, three widths per image, with
numbered markers on the elements the reference sheet names. The clock is fixed, so a
live job's elapsed time is the same at every width.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WT = Path(sys.argv[1]).resolve()
FACETS = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(WT / "tools"))
sys.path.insert(0, str(WT))
import panel_harness as H  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

assert "tender_crawl" in (WT / "extension" / "jobsview.js").read_text(encoding="utf-8")
assert "asked again about the" in (WT / "extension" / "app.js").read_text(encoding="utf-8")

WIDTHS = (320, 400, 480)
HEIGHT = 800
NOW = datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc)


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- real numbers, from the study's saved world facet (#1647 request 12) ----------------
facet = json.loads(FACETS.read_text(encoding="utf-8"))["facets"]["project_ctry_name_exact"]
areas = sorted(facet.values(), key=lambda v: -v["count"])
pages = [math.ceil(v["count"] / 1000) for v in areas]
AREAS, TOTAL = len(areas), sum(v["count"] for v in areas)
EXPECTED = sum(pages) + 1                          # 536 notice pages + the count request
DONE = 41
DONE_REQUESTS = 1 + sum(pages[:DONE])
DONE_NOTICES = sum(v["count"] for v in areas[:DONE])
LEFT_REQUESTS = 1 + sum(pages[DONE:])
CURRENT = areas[DONE]["name"]
# Egypt is the one store measured end to end (#1658): 944 tenders from 1,448 notices.
EGYPT_TENDERS = 944
PARTIAL_TENDERS = round(DONE_NOTICES * 944 / 1448)  # Egypt's ratio, said so in the sheet

BLOCKED = {"full_rebuild": "Full rebuild is not offered for search.worldbank.org: it keeps "
                           "every notice as it was read, so there is nothing to archive."}
WB = {"kind": "tender", "site_key": "worldbank_org", "source_key": "worldbank_org",
      "source_name": "World Bank procurement notices", "source_name_ar": "",
      "base_url": "https://search.worldbank.org", "family": "generic",
      "implemented": True, "supports_history": False, "runs_blocked": BLOCKED,
      "observations": 0, "products": 0, "last_success": None, "kept_pages": 0,
      "kept_at": None}
WB_DATA = dict(WB, observations=EGYPT_TENDERS, products=EGYPT_TENDERS)
WB_PARTIAL = dict(WB, observations=PARTIAL_TENDERS, products=PARTIAL_TENDERS,
                  first_crawl={"read": DONE, "of": AREAS, "unit": "areas",
                               "stopped_at": "2026-10-13T16:30:00Z"})
# WHILE THE FIRST CRAWL RUNS: tenders already held, and no `first_crawl` (it has not ended).
WB_CRAWLING = dict(WB, observations=PARTIAL_TENDERS, products=PARTIAL_TENDERS)
SOURCES = H.STRESS_SOURCES + [WB]
SOURCES_DATA = H.STRESS_SOURCES + [WB_DATA]
SOURCES_PARTIAL = H.STRESS_SOURCES + [WB_PARTIAL]
SOURCES_CRAWLING = H.STRESS_SOURCES + [WB_CRAWLING]

COST_FIRST = {"source": "search.worldbank.org", "requests": EXPECTED, "pace_s": 2.5,
              "counted_at": "2026-10-10",
              "reads": f"Reads every notice the Bank lists, {TOTAL:,} of them, one area "
                       f"at a time. An area is one of the Bank's {AREAS} countries and "
                       "regions.",
              "basis": "Counted from the Bank's own notice totals."}
COST_LEFT = dict(COST_FIRST, requests=LEFT_REQUESTS, counted_at="2026-10-13",
                 reads=f"Reads the {AREAS - DONE} areas the initial crawl did not reach, "
                       "then the notices changed since.",
                 basis="Counted from the Bank's own notice totals when the initial crawl "
                       "started. The notices changed since are not in these figures.")
MIXED = "search.worldbank.org collects tenders and runs on its own. Start a.co separately."
# WORDED TO HOLD AT EVERY STATUS NOT SETTLED: running, paused, or queued behind another job.
DUPLICATE = ("search.worldbank.org already has a crawl that has not finished. Follow or "
             "cancel it on Jobs.")


def job(status, *, ref="job_7c1e2a90b4d1", stage=None, requests=0, expected=None,
        done=0, total=None, unit="areas", notices=0, new=None,
        unchanged=0, errors=0, summary=None, started=None, finished=None):
    """One `tender_crawl` job as part 3b reports it."""
    started = started or iso(NOW - timedelta(seconds=requests * 2.5 + 20))
    return {"job_ref": ref, "job_kind": "tender_crawl", "status": status,
            "source_keys": ["worldbank_org"],
            "current_source_key": None if finished else "worldbank_org",
            "stage": stage, "created_at": started, "started_at": started,
            "finished_at": finished, "updated_at": finished or iso(NOW),
            "progress": {"done": done, "total": total or 0, "unit": unit},
            "fetch": {"requests": requests, "expected": expected,
                      "basis": "declared" if expected else None,
                      "counted_from": "the Bank's notice totals" if expected else None,
                      "sources": {"worldbank_org": {
                          "state": "fetching", "requests": requests, "pace_s": 2.5,
                          "honouring_delay": True, "retries": 0}}},
            "counters": {"notices": notices,
                         "releases_new": notices if new is None else new,
                         "releases_unchanged": unchanged, "errors": errors},
            "error_summary": summary, "queued_behind": None}


def requests_word(n):
    return f"{n:,} request{'' if n == 1 else 's'}"


def area_line(v):
    """The contract's one log line per area read: "<area>: <n> notices in <m> requests"."""
    return {"level": "info", "message": f"{v['name']}: {v['count']:,} notices in "
                                        f"{requests_word(math.ceil(v['count'] / 1000))}"}


# THE ORDER THE MOCK READS AREAS IN is the facet's, largest first: the first crawl read
# areas[:DONE] and stopped before areas[DONE]; every later state continues from there.
RUNNING = job("running", stage=f"reading {CURRENT}", requests=DONE_REQUESTS,
              expected=EXPECTED, done=DONE, total=AREAS, notices=DONE_NOTICES)
# THE LONGEST NAME THE BANK PUBLISHES, from the facet, not a long name chosen by hand.
LONGEST_NAME = max((v["name"] for v in areas), key=len)
LONGEST_AT = next(i for i, v in enumerate(areas) if v["name"] == LONGEST_NAME)
LONGEST = job("running", stage=f"reading {LONGEST_NAME}",
              requests=1 + sum(pages[:LONGEST_AT]), expected=EXPECTED, done=LONGEST_AT,
              total=AREAS, notices=sum(v["count"] for v in areas[:LONGEST_AT]))
STARTING = job("running", stage="counting notices")
PAUSED = job("paused", stage=f"reading {CURRENT}", requests=DONE_REQUESTS,
             expected=EXPECTED, done=DONE, total=AREAS, notices=DONE_NOTICES)
# A TENDER CRAWL QUEUED BEHIND A PRICE CRAWL: the adopted job is the price crawl, which
# holds the worker, and the tender crawl is only in the list. Newest first, as the engine
# lists them.
QUEUED = job("queued", ref="job_d3a8f05c61b2", started=iso(NOW - timedelta(minutes=2)))
QUEUED["current_source_key"] = None
QUEUED["started_at"] = None
PRICE_RUNNING = {"job_ref": "job_6be2c94a07f1", "job_kind": "crawl", "status": "running",
                 "run_mode": "update", "source_keys": ["LONG_AR"],
                 "current_source_key": "LONG_AR", "stage": "fetching",
                 "progress": {"done": 0, "total": 1},
                 "created_at": iso(NOW - timedelta(minutes=9)),
                 "started_at": iso(NOW - timedelta(minutes=9)), "finished_at": None,
                 "updated_at": iso(NOW),
                 "fetch": {"requests": 212, "expected": None, "basis": None,
                           "sources": {"LONG_AR": {"state": "fetching", "requests": 212,
                                                   "pace_s": 2.5, "honouring_delay": False,
                                                   "retries": 0}}},
                 "counters": {"observations": 1_830}, "error_summary": None,
                 "queued_behind": None}
# AN UPDATE OF THE STOPPED FIRST CRAWL, 12 areas into the 143 it did not read.
UPDATE_READ = 12
UPDATE_AREAS = job("running", stage=f"reading {areas[DONE + UPDATE_READ]['name']}",
                   requests=1 + sum(pages[DONE:DONE + UPDATE_READ]),
                   expected=LEFT_REQUESTS, done=UPDATE_READ, total=AREAS - DONE,
                   notices=sum(v["count"] for v in areas[DONE:DONE + UPDATE_READ]))
# THE SAME UPDATE AFTER EVERY AREA, 3 pages into the notices changed since.
CHANGES = (1_000, 1_000, 412)
LEFT_NOTICES = TOTAL - DONE_NOTICES
UPDATE_CHANGES = job("running", stage="reading changes",
                     requests=LEFT_REQUESTS + len(CHANGES), unit="pages", done=len(CHANGES),
                     notices=LEFT_NOTICES + sum(CHANGES), new=LEFT_NOTICES + 58,
                     unchanged=sum(CHANGES) - 58)
# THE HISTORY ON JOBS, oldest last: the first crawl failed at areas[DONE]; an update read
# the rest but two areas; the next update read those two, then the changes.
MISSED = (areas[DONE + 1], areas[DONE + 17])
MISSED_PAGES = sum(math.ceil(v["count"] / 1000) for v in MISSED)
MISSED_NOTICES = sum(v["count"] for v in MISSED)
FIRST_FAIL_PAGE = 1
HISTORY_DONE = 1 + MISSED_PAGES + 3
HISTORY = [
    job("running", ref="job_a91c03d2e7f4", stage="reading changes", requests=2, unit="pages",
        done=2, notices=1_611, new=37, unchanged=1_574),
    job("completed", ref="job_0b9f61c2d8e7", requests=HISTORY_DONE, unit="pages", done=3,
        notices=MISSED_NOTICES + sum(CHANGES), new=MISSED_NOTICES + 58,
        unchanged=sum(CHANGES) - 58,
        # AT 2.5 S APART, N REQUESTS TAKE AT LEAST 2.5 * (N - 1) S; this one takes 3 s more.
        started="2026-10-13T08:00:01Z",
        finished=iso(datetime(2026, 10, 13, 8, 0, 1, tzinfo=timezone.utc)
                     + timedelta(seconds=math.ceil(2.5 * (HISTORY_DONE - 1)) + 3))),
    job("completed_with_errors", ref="job_51d0aa7e3c22",
        requests=LEFT_REQUESTS - MISSED_PAGES, expected=LEFT_REQUESTS,
        done=AREAS - DONE - 2, total=AREAS - DONE, notices=LEFT_NOTICES - MISSED_NOTICES,
        errors=2,
        summary=f"2 areas not read; an update reads them first. {MISSED[0]['name']}: HTTP 503 "
                f"after 3 tries. {MISSED[1]['name']}: response cut off at 1,204,111 bytes.",
        started="2026-10-12T08:00:02Z", finished="2026-10-12T08:17:40Z"),
    # THE CONSEQUENCE LEADS, so the two-line clamp on Jobs keeps it (row 24).
    job("failed", ref="job_e4472b1f9a03",
        requests=DONE_REQUESTS + FIRST_FAIL_PAGE, expected=EXPECTED,
        done=DONE, total=AREAS, notices=DONE_NOTICES + 1_000, errors=1_000,
        summary=f"{DONE} of {AREAS} areas read; an update reads the rest. Stopped because "
                f"the Bank's notices changed shape at {CURRENT}, page {FIRST_FAIL_PAGE}: none "
                "of 1,000 notices could be read ('Prequalification Notice' is not a known "
                "notice type).",
        started="2026-10-11T08:00:01Z", finished="2026-10-11T08:14:03Z"),
]
# ONE LINE PER AREA READ, as the contract says, after the line that plans the phase.
LOGS = [
    {"level": "info", "message": f"counted {TOTAL:,} notices in {AREAS} areas: "
                                 f"{EXPECTED:,} requests"},
    *(area_line(v) for v in areas[:DONE]),
]
LOGS_LONGEST = LOGS[:1] + [area_line(v) for v in areas[:LONGEST_AT]]
LOGS_UPDATE_AREAS = [
    {"level": "info", "message": f"{AREAS - DONE} areas not read yet: "
                                 f"{LEFT_REQUESTS:,} requests"},
    *(area_line(v) for v in areas[DONE:DONE + UPDATE_READ]),
]
LOGS_UPDATE_CHANGES = [
    LOGS_UPDATE_AREAS[0],
    *(area_line(v) for v in areas[DONE:]),
    {"level": "info", "message": "every area read; reading the notices changed since "
                                 "13 Oct 2026, 8:00 AM"},
    *({"level": "info", "message": f"changes: {n:,} notices in 1 request"} for n in CHANGES),
]


def engine_jobs(cost=None, mixed=False, duplicate=False, started=None, moves=0):
    """POST /api/jobs as part 3b answers it, in its order: a mix, a duplicate, then the
    cost question. An accepted run then appears in the job list, as a queued job does."""
    return ("js", """window.__posts = []; const real = window.fetch;
      const STARTED = %s;
      window.fetch = async (u, o = {}) => {
        const answer = (status, payload) => ({ok: status < 300, status,
          statusText: String(status), json: async () => payload});
        const method = o.method || 'GET';
        const path = String(u).replace(/^https?:\\/\\/[^/]+/, '');
        if (STARTED && window.__started && method === 'GET' && /^\\/api\\/jobs(\\?|$)/.test(path))
          return answer(200, {jobs: [STARTED]});
        if (!(path.startsWith('/api/jobs') && method === 'POST' && !path.includes('/control')))
          return real(u, o);
        const body = JSON.parse(o.body || '{}'); window.__posts.push(body);
        if (%s && body.source_keys.length > 1) return answer(400, {detail: %s});
        if (%s) return answer(409, {detail: %s});
        // ONE FIGURE FOR THE PAGE'S LIFE, as the engine's count is: once it moves it stays.
        if (window.__cost === undefined) window.__cost = %s;
        const cost = window.__cost;
        if (cost && body.accept_cost && !window.__moved && %d) {
          // A MOVED FIGURE WAS COUNTED AGAIN, so it carries the day of that count.
          window.__moved = true; cost.requests += %d; cost.counted_at = %s; }
        if (cost && !(body.accept_cost && body.accept_cost.requests === cost.requests))
          return answer(409, {question: 'cost', detail: 'confirm the cost to start', cost});
        window.__started = true;
        return answer(200, {job_ref: 'job_7c1e2a90b4d1', status: 'queued'});
      };""" % (json.dumps(started), "true" if mixed else "false", json.dumps(MIXED),
               "true" if duplicate else "false", json.dumps(DUPLICATE), json.dumps(cost),
               moves, moves, json.dumps(NOW.strftime("%Y-%m-%d"))))


def click(sel):
    return ("click", sel)


def fill(sel, text):
    return ("fill", sel, text)


def scroll(sel, block="start"):
    return ("scroll", sel, block)


def wait(ms):
    return ("wait", ms)


TICK_WB = click('input[data-key="worldbank_org"]')
# START FROM THE KEYBOARD, so the focus the question opens with is drawn.
PRESS_RUN = ("press", "#run", "Enter")
# THE RULES ANSWER PART 3B SENDS FOR THE SOURCE: robots.txt obeyed (his ruling on Q2) and
# 2.5 s between requests (the pace #1647's Q2 put to him), both from the source.
SHIPS_OBEY = ("js", """window.__rules = {worldbank_org: {
  active: {value: false, shipped: false, origin: "source"},
  robots: {value: "obey", custom: null, shipped: "obey", shipped_custom: null,
           origin: "source"},
  user_agent: {value: null, shipped: null, origin: "general"},
  crawl_pace_s: {value: 2.5, shipped: 2.5, origin: "source"}}};""")
TICK_SHORT = click('input[data-key="SHORT"]')
ROW_WB = '#sites input[data-key="worldbank_org"] ~ .source-identity'
WB_ROW = '#sites .srow:has(input[data-key="worldbank_org"])'
STATES = {
    "01-run-list": (dict(sources=SOURCES), [click("#tab-run"), scroll(WB_ROW, "center")],
                    [(1, ROW_WB + " .source-identity-domain"),
                     (2, ROW_WB + " .source-identity-meta")]),
    "02-run-first-crawl": (dict(sources=SOURCES),
                           [click("#tab-run"), TICK_WB, scroll("#run-options-heading")],
                           [(3, "#run-mode-trigger"), (4, "#mode-help"), (5, "#run"),
                            (6, "#selected .card .kv:nth-of-type(3)")]),
    "03-confirm-first-crawl": (dict(sources=SOURCES),
                               [click("#tab-run"), TICK_WB, engine_jobs(cost=COST_FIRST),
                                PRESS_RUN, wait(250)],
                               [(7, "#confirm-title"), (8, "#confirm-copy"),
                                (8, "#confirm-facts"), (9, "#confirm-keep"),
                                (10, "#confirm-go")]),
    "03b-after-confirming": (dict(sources=SOURCES),
                             [click("#tab-run"), TICK_WB,
                              engine_jobs(cost=COST_FIRST, started=STARTING),
                              click("#run"), wait(250), click("#confirm-go"), wait(900),
                              scroll("#activity")],
                             [(17, "#act-state"), (18, "#act-progress-label")]),
    "03c-asked-again": (dict(sources=SOURCES),
                        [click("#tab-run"), TICK_WB, engine_jobs(cost=COST_FIRST, moves=3),
                         click("#run"), wait(250), click("#confirm-go"), wait(400)],
                        [(8, "#confirm-copy"), (10, "#confirm-go")]),
    "04-run-with-data-mode-menu": (dict(sources=SOURCES_DATA),
                                   [click("#tab-run"), TICK_WB, scroll("#run-options-heading"),
                                    click("#run-mode-trigger")],
                                   [(11, '#run-mode-list [data-select-value="full_rebuild"]')]),
    "05-run-with-data-note": (dict(sources=SOURCES_DATA),
                              [click("#tab-run"), TICK_WB, scroll("#run-options-heading")],
                              [(12, "#mode-help"), (5, "#run")]),
    "06-run-partial-first-crawl": (dict(sources=SOURCES_PARTIAL),
                                   [click("#tab-run"), TICK_WB, scroll(WB_ROW, "start")],
                                   [(13, WB_ROW + " .source-row-kept"), (12, "#mode-help")]),
    "07-confirm-the-rest": (dict(sources=SOURCES_PARTIAL),
                            [click("#tab-run"), TICK_WB, engine_jobs(cost=COST_LEFT),
                             PRESS_RUN, wait(250)],
                            [(7, "#confirm-title"), (8, "#confirm-copy"),
                             (8, "#confirm-facts")]),
    "08-run-mixed-refused": (dict(sources=SOURCES),
                             [click("#tab-run"), TICK_WB, TICK_SHORT,
                              engine_jobs(cost=COST_FIRST, mixed=True), click("#run"),
                              wait(300), scroll("#run", "center")],
                             [(14, "#run-refused")]),
    "09-refused-while-a-job-runs": (dict(sources=SOURCES, jobs=[PRICE_RUNNING], logs=[]),
                                    [click("#tab-run"), TICK_WB, TICK_SHORT,
                                     engine_jobs(cost=COST_FIRST, mixed=True), click("#run"),
                                     wait(3600), scroll("#run", "center")],
                                    [(15, "#run-blocked"), (14, "#run-refused")]),
    "09b-start-while-it-crawls": (dict(sources=SOURCES_CRAWLING, jobs=[RUNNING], logs=LOGS),
                                  [click("#tab-run"), TICK_WB,
                                   engine_jobs(cost=COST_FIRST, duplicate=True),
                                   click("#run"), wait(600), scroll("#run", "center")],
                                  [(12, "#mode-help"), (14, "#run-refused")]),
    "09c-its-own-crawl-runs": (dict(sources=SOURCES_CRAWLING, jobs=[RUNNING], logs=LOGS),
                               [click("#tab-run"), TICK_WB, wait(400),
                                scroll("#run", "center")],
                               [(15, "#run-blocked")]),
    "09d-its-own-crawl-paused": (dict(sources=SOURCES_CRAWLING, jobs=[PAUSED], logs=LOGS),
                                 [click("#tab-run"), TICK_WB, wait(400),
                                  scroll("#run", "center")],
                                 [(15, "#run-blocked")]),
    "09e-queued-behind-a-price-crawl": (dict(sources=SOURCES_CRAWLING,
                                             jobs=[QUEUED, PRICE_RUNNING], logs=LOGS),
                                        [click("#tab-run"), TICK_WB, wait(400),
                                         scroll("#run", "center")],
                                        [(15, "#run-blocked")]),
    "10-run-filtered-to-nothing": (dict(sources=SOURCES),
                                   [click("#tab-run"), fill("#site-search", "tenders")],
                                   [(16, "#sites .srow")]),
    "11-activity-counting": (dict(sources=SOURCES, jobs=[STARTING]),
                             [click("#tab-run"), wait(400), scroll("#activity")],
                             [(17, "#act-state"), (18, "#act-progress-label"),
                              (19, "#act-counters .kv:nth-child(1)")]),
    "12-activity-running": (dict(sources=SOURCES_CRAWLING, jobs=[RUNNING], logs=LOGS),
                            [click("#tab-run"), wait(400), scroll("#activity")],
                            [(17, "#act-state"), (18, "#act-progress-label"),
                             (19, "#act-counters .kv:nth-child(1)"),
                             (20, "#act-counters .kv:nth-child(4)"), (21, "#logbox")]),
    "13a-update-reads-the-rest": (dict(sources=SOURCES_CRAWLING, jobs=[UPDATE_AREAS],
                                       logs=LOGS_UPDATE_AREAS),
                                  [click("#tab-run"), wait(400), scroll("#activity")],
                                  [(17, "#act-state"), (18, "#act-progress-label"),
                                   (19, "#act-counters .kv:nth-child(1)")]),
    "13b-update-reads-changes": (dict(sources=SOURCES_DATA, jobs=[UPDATE_CHANGES],
                                      logs=LOGS_UPDATE_CHANGES),
                                 [click("#tab-run"), wait(400), scroll("#activity")],
                                 [(17, "#act-state"), (18, "#act-progress-label"),
                                  (19, "#act-counters .kv:nth-child(1)")]),
    "14-activity-longest-name": (dict(sources=SOURCES_CRAWLING, jobs=[LONGEST],
                                      logs=LOGS_LONGEST),
                                 [click("#tab-run"), wait(400), scroll("#activity")],
                                 [(17, "#act-state")]),
    "15-activity-paused": (dict(sources=SOURCES_CRAWLING, jobs=[PAUSED], logs=LOGS),
                           [click("#tab-run"), wait(400), scroll("#activity")],
                           [(17, "#act-state")]),
    "16-jobs-page": (dict(sources=SOURCES, jobs=HISTORY, logs=LOGS),
                     [click("#tab-jobs"), wait(500)],
                     [(22, "#jobs-list > :nth-child(1)"), (23, "#jobs-list > :nth-child(3)")]),
    "17-jobs-page-failed": (dict(sources=SOURCES, jobs=HISTORY, logs=LOGS),
                            [click("#tab-jobs"), wait(500),
                             scroll("#jobs-list > :nth-child(4)", "end")],
                            [(24, "#jobs-list > :nth-child(4)")]),
    "18-player-and-data-page": (dict(sources=SOURCES_CRAWLING, jobs=[RUNNING], logs=LOGS),
                                [click("#tab-data"), wait(500),
                                 scroll("#datasets > :last-child", "end")],
                                [(25, "#miniplayer"), (26, "#datasets > :last-child")]),
    "19-data-page-only-tenders": (dict(sources=[WB_DATA]), [click("#tab-data"), wait(500)],
                                  [(26, "#datasets > :last-child")]),
    "20-library": (dict(sources=SOURCES_DATA),
                   [click("#tab-sources"), wait(300),
                    scroll('[data-edit-source="worldbank_org"]', "center")],
                   [(27, '[data-edit-source="worldbank_org"]')]),
    "20b-library-editor": (dict(sources=SOURCES_DATA),
                           [click("#tab-sources"), wait(300), SHIPS_OBEY,
                            click('[data-edit-source="worldbank_org"]'), wait(600),
                            scroll("#source-edit-robots-card", "start")],
                           [(29, "#source-edit-robots"), (29, "#source-edit-robots-origin")]),
    "20c-library-editor-his-choice": (dict(sources=SOURCES_DATA),
                                      [click("#tab-sources"), wait(300), SHIPS_OBEY,
                                       click('[data-edit-source="worldbank_org"]'), wait(600),
                                       ("js", "const s = document.getElementById("
                                              "'source-edit-robots'); s.value = 'default'; "
                                              "s.dispatchEvent(new Event('change', "
                                              "{bubbles: true}))"),
                                       click("#source-edit-save"), wait(600),
                                       scroll("#source-edit-robots-card", "start")],
                                      [(29, "#source-edit-robots"),
                                       (29, "#source-edit-robots-origin")]),
    "21-engine-down": (dict(sources=SOURCES, engine_up=False), [click("#tab-run")],
                       [(28, "#setup")]),
}
SHORT = {
    "23r-asked-again-320-high": (dict(sources=SOURCES),
                                 [click("#tab-run"), TICK_WB,
                                  engine_jobs(cost=COST_FIRST, moves=3), PRESS_RUN, wait(250),
                                  # ONE SHIFT+TAB reaches the confirm button from the title
                                  # (320 px) and from Cancel (400, 480 px) alike.
                                  ("key", "Shift+Tab"), ("key", "Enter"), wait(400)],
                                 [(8, "#confirm-copy")]),
    "22-short-panel-320-high": (dict(sources=SOURCES),
                                [click("#tab-run"), TICK_WB, scroll("#run", "end")],
                                [(5, "#run")]),
    "23-confirm-320-high": (dict(sources=SOURCES),
                            [click("#tab-run"), TICK_WB, engine_jobs(cost=COST_FIRST),
                             PRESS_RUN, wait(250)],
                            # NO MARKER ON THE TITLE: its box would cover the focus ring
                            # this state and 23s compare. Row 7 is marked in 03.
                            [(9, "#confirm-keep")]),
    # THE COMPARISON, SUPABASE'S SIDE: ConfirmationModal sets no initial focus, so Radix focuses the
    # first tabbable element, Cancel, with `preventScroll: true`
    # (@radix-ui/react-focus-scope@1.1.7, `focus()`). Drawn by doing exactly that.
    "23s-confirm-320-high-supabase": (dict(sources=SOURCES),
                                      [click("#tab-run"), TICK_WB,
                                       engine_jobs(cost=COST_FIRST), PRESS_RUN, wait(250),
                                       # AT ITS TOP FIRST: Radix mounts a fresh dialog,
                                       # where the draft has scrolled Cancel into view.
                                       ("js", "document.getElementById('confirm-dialog')"
                                              ".scrollTop = 0; document.getElementById("
                                              "'confirm-keep').focus({preventScroll: true})")],
                                      [(9, "#confirm-keep")]),
}

MARK = (214, 40, 160)


def drive(page, steps):
    for step in steps:
        kind = step[0]
        if kind == "click":
            page.click(step[1])
        elif kind == "fill":
            page.fill(step[1], step[2])
        elif kind == "scroll":
            page.eval_on_selector(step[1], "(e, b) => e.scrollIntoView({block: b})", step[2])
        elif kind == "js":
            page.evaluate(step[1])
        elif kind == "press":
            page.focus(step[1])
            page.keyboard.press(step[2])
        elif kind == "key":
            page.keyboard.press(step[1])
        elif kind == "wait":
            page.wait_for_timeout(step[1])
        page.wait_for_timeout(120)


def marks(page, markers):
    found = []
    for number, selector in markers:
        rect = page.evaluate("""(sel) => { const e = document.querySelector(sel);
            if (!e) return null; const r = e.getBoundingClientRect();
            return r.width || r.height ? [r.left, r.top, r.right, r.bottom] : null; }""",
                             selector)
        found.append((number, selector, rect))
    return found


def shoot(browser, stub_kwargs, steps, markers, width, height, scheme, tmp):
    page_file = H.build_page(tmp, H.stub(**stub_kwargs), name=f"p{width}{scheme}.html")
    page = browser.new_page(viewport={"width": width, "height": height},
                            color_scheme=scheme)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(page_file.as_uri())
    H.wait_until_settled(page)
    # AFTER THE PANEL SETTLES: a clock fixed before it stops the startup marks firing.
    page.clock.set_fixed_time(NOW)
    drive(page, steps)
    page.wait_for_timeout(250)
    found = marks(page, markers)
    facts = page.evaluate("""() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        refused: (document.getElementById('run-refused') || {}).textContent || '',
        blocked: (document.getElementById('run-blocked') || {}).textContent || '',
        posts: window.__posts || null,
        tenderCard: !!document.querySelector('[data-open="worldbank_org"]'),
        // WHETHER HE CAN SEE WHAT HAS FOCUS: inside the open card's visible box, or the
        // viewport when no question is open.
        focusInView: (() => { const a = document.activeElement;
          if (!a || a === document.body) return null;
          const r = a.getBoundingClientRect();
          const open = !document.getElementById('confirm-veil').classList.contains('hidden');
          const box = open ? document.getElementById('confirm-dialog').getBoundingClientRect()
                           : {top: 0, bottom: innerHeight};
          return r.top >= Math.max(0, box.top) && r.bottom <= Math.min(innerHeight, box.bottom);
        })(),
        focus: document.activeElement && (document.activeElement.id
               || document.activeElement.tagName)})""")
    shot = tmp / f"s{width}{scheme}.png"
    page.screenshot(path=str(shot))
    page.close()
    return Image.open(shot).convert("RGB"), found, errors, facts


def draw_marks(img, found):
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("arialbd.ttf", 13)
    for number, _sel, rect in found:
        if not rect:
            continue
        left, top, right, bottom = rect
        if bottom < 0 or top > img.height:
            continue
        # 7 PX OUT, clear of the focus ring, which reaches 4 px out (`--focus-ring-offset`
        # and `--focus-ring-width`, tokens.css:439-440): a marker must not hide the focus
        # a state shows.
        left, top, right, bottom = left - 7, top - 7, right + 7, bottom + 7
        d.rectangle([left, top, right, bottom], outline=MARK, width=2)
        cx, cy = max(10, min(img.width - 10, right + 2)), max(10, min(img.height - 10, top - 2))
        d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=MARK)
        text = str(number)
        w = d.textlength(text, font=font)
        d.text((cx - w / 2, cy - 8), text, fill=(255, 255, 255), font=font)


def compose(name, scheme, shots, height):
    gap, head = 24, 34
    width = sum(s[0].width for s in shots) + gap * (len(shots) + 1)
    sheet = Image.new("RGB", (width, height + head + gap),
                      (250, 250, 250) if scheme == "light" else (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 15)
    ink = (30, 30, 30) if scheme == "light" else (230, 230, 230)
    x = gap
    for shot, w in zip(shots, WIDTHS):
        d.text((x, 10), f"{name} · {scheme} · {w} px", fill=ink, font=font)
        sheet.paste(shot[0], (x, head))
        x += shot[0].width + gap
    sheet.save(OUT / f"{name}-{scheme}.png")


def main():
    from playwright.sync_api import sync_playwright
    tmp = OUT / "_tmp"
    tmp.mkdir(exist_ok=True)
    report = {}
    only = set(sys.argv[4:])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for group, height in ((STATES, HEIGHT), (SHORT, 320)):
            for name, (kwargs, steps, markers) in group.items():
                if only and name not in only:
                    continue
                for scheme in ("light", "dark"):
                    shots = []
                    for width in WIDTHS:
                        img, found, errors, facts = shoot(browser, kwargs, steps, markers,
                                                          width, height, scheme, tmp)
                        draw_marks(img, found)
                        shots.append((img, found, errors, facts))
                    compose(name, scheme, shots, height)
                    report[f"{name}-{scheme}"] = {
                        str(w): {"missing": [n for n, _s, r in s[1] if not r],
                                 "errors": s[2], **s[3]} for w, s in zip(WIDTHS, shots)}
        browser.close()
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({"areas": AREAS, "total": TOTAL, "expected": EXPECTED,
                      "done_requests": DONE_REQUESTS, "done_notices": DONE_NOTICES,
                      "left_requests": LEFT_REQUESTS, "partial_tenders": PARTIAL_TENDERS,
                      "current": CURRENT}))
    for key, widths in report.items():
        for w, r in widths.items():
            if r["missing"] or r["errors"] or r["overflow"]:
                print(key, w, {k: r[k] for k in ("missing", "errors", "overflow")})


main()
