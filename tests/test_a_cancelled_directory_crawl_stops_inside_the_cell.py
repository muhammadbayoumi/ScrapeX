"""Cancel must stop a directory crawl INSIDE a cell, not at the end of it.

WHAT THIS COST, measured on `job_36bf9e2adc21` on 2026-09-22. He pressed Cancel at 12:41
and the pages kept landing at an unchanged twenty a minute:

    12:39  19      12:43  19
    12:40  20      12:44  22
    12:41  21   <- Cancel pressed here    12:45  22
    12:42  19      12:46  21
                   12:47  20
                   12:48   8   <- the engine was killed

152 further pages, and the rate never moved. The job log for those twenty-four hours is
five lines and the word "cancel" is in none of them until the orphan sweep settled it at
12:51:13, ten minutes after the process died. Issue 1028.

WHY: `run_directory_crawl_job_once` asked `still_wanted` in exactly two places -- once
before the crawl, after the politeness lane, and once in `cell_closed`, which
`contractors.crawl` calls BETWEEN cells. `OmanPartition.cells()` returns `(WHOLE,)`, so
the between-cells question is first asked when the crawl is already over. muqawil has 56
cells and hides this completely.

AND A SECOND READ IS NEEDED, WHICH IS THE SUBTLE HALF. `still_wanted` answers True for a
job in `cancelling` -- `cancelling` is not in `TERMINAL_JOB_STATUSES` (issue 1029) -- and
`cancelling` is exactly the status Cancel produces. A guard written on `still_wanted`
alone would have stopped nothing here, and
`test_the_cancel_is_seen_while_still_wanted_says_yes` is the test that holds that line.

THE BETWEEN-CELLS HALF IS ALREADY GUARDED, by
`test_a_settled_row_stops_the_listing_crawl_at_its_next_cell` in
`test_a_cancelled_crawls_pages_are_not_lost.py`. It passes, and it passed throughout the
run above: *at its next cell* is the whole of what it claims, and on a one-cell partition
there is no next cell. This file is the other half.

These tests drive `run_directory_crawl_job_once` and read what it wrote. The one
exception is the `PageWalker` pair at the foot, which exists because every layer between
the fetch callback and the job turns an `Exception` into a record rather than an end --
so the stop has to be the one thing they do not catch.
"""
from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("fastapi")

from scrapex import contractors, datasetjob, directoryjob, jobs  # noqa: E402
from scrapex import db as dbmod
from scrapex.crawlscope import CrawlScope  # noqa: E402
from scrapex.pagewalk import PageWalker  # noqa: E402
from scrapex.vocab import JobControl, JobStatus, LogLevel, RunMode  # noqa: E402
from scrapex.webui.app import _fetch_progress  # noqa: E402

# THIS FILE NAMES `extension/app.html` AND `extension/app.js`, in the guard that the
# copy must name a control the panel really draws and can reveal. The gate is
# one-directional -- reads-extension implies marked -- so carrying the mark costs
# nothing, and its absence would stop this file running on an extension-only change,
# which is exactly the change that would break what it guards.
pytestmark = pytest.mark.extension

SITE = "muqawil_org"


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "engine.db")
    dbmod.migrate(connection)
    connection.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, 'muqawil.org', 'https://muqawil.org', 'directory')", (SITE,))
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


class _Fetcher:
    """What `HttpFetcher` exposes to this path. `close()` is called in a `finally`."""

    def __init__(self) -> None:
        self.requests_count = 0
        self.expected_requests = None
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _drive(conn, monkeypatch, *, pages: int, at_page, press,
           beat_every_s: float = 0.0):
    """Run a crawl of `pages` pages, calling `press(own_conn, ref)` after page `at_page`.

    THE PRESS IS ON ITS OWN CONNECTION, because that is where it comes from in life: the
    panel writes the control through the web app while the job holds `conn`. Writing it
    on the job's connection would test a transaction that cannot happen.

    `at_page=None` presses before the first page, which is the ordering guard -- the
    check is in front of the request, so nothing may be spent.
    """
    fetcher = _Fetcher()
    fetched: list[str] = []
    db_path = str(conn.execute("PRAGMA database_list").fetchone()[2])

    def fetch(url: str) -> str:
        fetcher.requests_count += 1
        fetched.append(url)
        return "<html></html>"

    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, fetch))
    # Zero makes every page a checkpoint -- the same code path at a different cadence.
    # `test_the_shipped_interval_is_what_bounds_a_cancel` runs the same scenario at the
    # real 20s, because the checkpoint being free here is exactly what hides how coarse
    # it is in production.
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", beat_every_s)

    seen: dict = {}

    def press_now() -> None:
        # `dbmod.connect`, NOT A RAW ONE: `get_job` reads through `_as_job`, which needs
        # `row_factory = sqlite3.Row`. A raw connection reads the row back as a tuple.
        own = dbmod.connect(db_path)
        try:
            press(own, ref)
            own.commit()
            seen["still_wanted_at_the_press"] = jobs.still_wanted(own, ref)
            row = jobs.get_job(own, ref)
            seen["status_at_the_press"] = row["status"] if row else None
        finally:
            own.close()

    def crawl_some_pages(*args, **kwargs):
        # POSITIONAL: the runner calls
        # `contractors.crawl(conn, directory, beating, fetcher, run_ref, ...)`.
        beating = kwargs.get("beating") or args[2]
        if at_page is None:
            press_now()
        for page in range(pages):
            beating(f"https://muqawil.org/en/contractors?page={page}")
            if page == at_page:
                press_now()
        seen["ran_to_the_end"] = True

    monkeypatch.setattr(directoryjob.contractors, "crawl", crawl_some_pages)

    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)

    seen["fetched"] = fetched
    seen["requests"] = fetcher.requests_count
    seen["job"] = jobs.get_job(conn, ref)
    seen["log"] = [row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (seen["job"]["job_id"],))]
    return seen


def _cancel(own, ref):
    jobs.set_control(own, ref, JobControl.CANCEL)


def test_a_cancel_pressed_mid_cell_stops_before_the_next_request(conn, monkeypatch):
    """The finding itself: 152 pages were fetched after he pressed it."""
    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=_cancel)

    assert seen["requests"] == 3, (
        f"{seen['requests']} pages were fetched after Cancel was pressed at page 3 of "
        f"40. On his run that number was 152, at an unchanged twenty a minute, and the "
        f"crawl ended only because the engine was killed."
    )
    assert "ran_to_the_end" not in seen, (
        "the crawl ran every one of its forty pages, so nothing stopped it"
    )
    # WHICH pages, not only how many: the last one fetched is the page the cancel was
    # pressed after, so the stop landed in front of page 4 rather than behind it.
    assert seen["fetched"][-1].endswith("page=2"), (
        f"the last page fetched was {seen['fetched'][-1]!r}, not the one the cancel "
        f"followed"
    )


def test_the_cancel_is_seen_while_still_wanted_says_yes(conn, monkeypatch):
    """ISSUE 1029'S INTERLOCK, and the reason the guard reads `control` as well.

    `set_control` parks `cancelling` on a job a worker is holding, and `cancelling` is
    not in `TERMINAL_JOB_STATUSES` -- so `still_wanted` answers True for the one state
    Cancel produces. A guard written on `still_wanted` alone compiles, reads correctly,
    and stops nothing.
    """
    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=_cancel)

    assert seen["status_at_the_press"] == JobStatus.CANCELLING.value, (
        f"the press left the job at {seen['status_at_the_press']!r}; this test is "
        f"measuring a state that does not arise"
    )
    assert seen["still_wanted_at_the_press"] is True, (
        "`still_wanted` now answers False for a cancelling job, so issue 1029 is fixed "
        "and this test no longer proves the guard reads `control` -- rewrite it against "
        "whatever the new hole is, do not delete it"
    )
    assert seen["requests"] == 3, (
        "the crawl kept fetching, which is what a guard that trusts `still_wanted` "
        "alone does with a cancelling job"
    )


def test_the_check_is_in_front_of_the_request_not_behind_it(conn, monkeypatch):
    """A stop read after the fetch reports the page it has already paid for."""
    seen = _drive(conn, monkeypatch, pages=40, at_page=None, press=_cancel)

    assert seen["requests"] == 0, (
        f"{seen['requests']} request(s) were spent on a job that was cancelled before "
        f"the first one. The check has moved below the fetch."
    )


def test_the_cancelled_job_is_settled_here_and_not_by_the_sweep(conn, monkeypatch):
    """`cancelling` left behind is the state the orphan sweep cleans up ten minutes on.

    That is the line he actually got: *"orphan sweep: job_36bf9e2adc21 was cancelling
    with no runtime behind it, so it is now cancelled"* -- after a restart.
    """
    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=_cancel)

    assert seen["job"]["status"] == JobStatus.CANCELLED.value, (
        f"the job is {seen['job']['status']!r} after the crawl unwound. A transitional "
        f"status nothing settles waits for the orphan sweep."
    )
    assert seen["job"]["finished_at"], "a settled job with no finished_at"
    assert any("cancelled inside a cell" in line for line in seen["log"]), (
        f"the log says nothing about the cancel: {seen['log']!r}. His said nothing "
        f"either, for twenty-four hours."
    )


def test_a_job_something_else_already_settled_is_not_re_finished(conn, monkeypatch):
    """The orphan sweep, or a second session, got there first.

    `_finish` must not be written over it -- the same reading `cell_closed` takes of
    `still_wanted`: a job something else finished is not this run's to finish again.
    """
    def settle(own, ref):
        # BY `job_id`, NOT BY `job_ref` -- `_finish` takes the numeric id, and the ref
        # sails through the UPDATE matching nothing and then fails the log's foreign key.
        jobs._finish(own, jobs.get_job(own, ref)["job_id"], JobStatus.CANCELLED, None)

    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=settle)

    assert seen["still_wanted_at_the_press"] is False
    assert seen["requests"] == 3, (
        f"{seen['requests']} pages were fetched for a job that was already settled"
    )
    assert any("already settled" in line for line in seen["log"]), (
        f"the log does not say the job was already settled: {seen['log']!r}"
    )


def test_a_pause_is_still_left_to_the_cell_boundary(conn, monkeypatch):
    """A DECISION, NOT AN OMISSION, and this test is what keeps it one.

    A cell's completeness proof compares an id sequence against a witness read of page
    one, so a cell interrupted halfway has fetched pages and proved nothing.
    `cell_closed` pauses at a boundary precisely to keep that proof, and a pause exists
    to be resumed. Honouring a pause mid-cell would make the 56-cell crawl worse in
    order to improve the one-cell one.

    The cost is real and recorded in 1028: a pause on a one-cell partition still waits
    for the end of the crawl. Fixing that means keeping the proof, not stopping sooner.
    """
    def pause(own, ref):
        jobs.set_control(own, ref, JobControl.PAUSE)

    seen = _drive(conn, monkeypatch, pages=12, at_page=2, press=pause)

    assert seen["status_at_the_press"] == JobStatus.PAUSING.value
    assert seen["requests"] == 12, (
        f"the crawl stopped after {seen['requests']} of 12 pages on a PAUSE. A mid-cell "
        f"pause discards the cell's completeness proof, which is the one thing pausing "
        f"at a boundary exists to keep."
    )


def test_a_database_it_cannot_read_does_not_cancel_a_crawl_nobody_cancelled(
        conn, monkeypatch):
    """Lose the check, never the run -- the rule the heartbeat beside it already states.

    A five-second `busy_timeout` against another writer must not read as a stop.
    """
    refusals: list[int] = []
    real_connect = sqlite3.connect

    def refusing(*args, **kwargs):
        refusals.append(1)
        raise sqlite3.OperationalError("database is locked")

    fetcher = _Fetcher()

    def fetch(url: str) -> str:
        fetcher.requests_count += 1
        return "<html></html>"

    def crawl_some_pages(*args, **kwargs):
        beating = kwargs.get("beating") or args[2]
        monkeypatch.setattr(directoryjob.sqlite3, "connect", refusing)
        try:
            for page in range(9):
                beating(f"https://muqawil.org/en/contractors?page={page}")
        finally:
            monkeypatch.setattr(directoryjob.sqlite3, "connect", real_connect)

    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, fetch))
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)
    monkeypatch.setattr(directoryjob.contractors, "crawl", crawl_some_pages)

    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)

    assert refusals, "the guard never opened a connection, so nothing was refused"
    assert fetcher.requests_count == 9, (
        f"{fetcher.requests_count} of 9 pages were fetched. A locked database ended a "
        f"crawl the owner never stopped."
    )


# -- the layer that would have eaten it -------------------------------------------------

class _TenPages:
    """A `PageSource` of ten listing pages and nothing else."""

    site_key = SITE

    def listing_urls(self, base_url: str):
        return [f"{base_url}/en/contractors?page={n}" for n in range(1, 11)]

    def detail_urls(self, page):
        return []


def test_the_walker_records_an_ordinary_failure_and_keeps_going():
    """The behaviour that makes the stop hard, stated first so the pair reads.

    *"NOT RAISED. One dead page out of a hundred thousand must not discard the rest"* --
    `pagewalk._get`. This is right, and `snapshotcrawl.store`, `witness`, `size_cell` and
    the resize in `_crawl_one_cell` all repeat it.
    """
    def dead(url: str) -> str:
        raise RuntimeError("502 from the site")

    report = PageWalker(_TenPages(), dead, pace_s=0).walk(
        "https://muqawil.org", CrawlScope.LISTING_ONLY)

    assert len(report.failures) == 10, (
        f"{len(report.failures)} failures for ten dead pages; the walker stopped "
        f"instead of recording them"
    )


def test_a_cancel_is_the_one_thing_the_walker_does_not_turn_into_a_failed_page():
    """THE REASON `CrawlAbandoned` IS A `BaseException`.

    Raise a `CrawlStopped` -- or anything else deriving from `Exception` -- from the
    fetch callback and the walker above files it as one failed page, then asks for the
    next nine. A cancelled crawl would walk the whole cell turning every page into a
    failure, and the cell would then be retried for being incomplete.
    """
    asked: list[str] = []

    def cancelled(url: str) -> str:
        asked.append(url)
        raise contractors.CrawlAbandoned(JobControl.CANCEL.value)

    with pytest.raises(contractors.CrawlAbandoned):
        PageWalker(_TenPages(), cancelled, pace_s=0).walk(
            "https://muqawil.org", CrawlScope.LISTING_ONLY)

    assert len(asked) == 1, (
        f"the walker asked for {len(asked)} of ten pages after the crawl was cancelled. "
        f"`CrawlAbandoned` now derives from `Exception`, so every `except Exception` "
        f"between the fetch callback and the job swallows it."
    )


def test_the_shipped_interval_is_what_bounds_a_cancel(conn, monkeypatch):
    """THE COARSENESS THE OTHER TESTS PAY TO HIDE, stated here so it cannot grow.

    `_stop_if_dropped()` sits inside `if due:`, so `BEAT_EVERY_S` governs CANCEL LATENCY
    and not merely heartbeat cadence. Every test above patches it to 0.0, which makes
    every page a checkpoint and lets `requests == 3` read like a per-request guarantee.
    It is not one: the cancel is honoured at the next BEAT.

    THE CONSTANT ITSELF IS ALREADY PINNED, and this test does not do that --
    `test_the_shipped_heartbeat_interval_keeps_the_card_fresh`
    (`tests/test_the_button_drives_the_collector_the_source_needs.py`) has asserted
    `0 < BEAT_EVERY_S <= 60.0` since before this change. An earlier draft of this
    docstring claimed otherwise, on a mutation that survived THIS FILE and was killed by
    that one; the gate's second pass caught the claim.

    What this test adds is the COUPLING: that the cancel is bounded by that constant at
    all, which no other test states and which a reader of `requests == 3` above would
    never guess.

    In production the overshoot is one interval of FETCHING, not `pages`: at
    `DEFAULT_PACE_S = 1.0` that is up to about twenty requests on a one-cell source,
    against the 152 he measured. The improvement is real; the guarantee is per-beat, and
    a reader of the assertions above would otherwise conclude it is per-request.
    """
    assert directoryjob.BEAT_EVERY_S >= 1.0, (
        f"BEAT_EVERY_S is {directoryjob.BEAT_EVERY_S}, so this test is not measuring "
        f"the shipped cadence at all"
    )
    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=_cancel,
                  beat_every_s=directoryjob.BEAT_EVERY_S)

    # The FIRST call is always due -- `beat_at` starts at 0.0 and `time.monotonic()` is
    # seconds since boot -- so the guard does run before page 1, which is what
    # `test_the_check_is_in_front_of_the_request_not_behind_it` asserts. After that the
    # next check is one interval away, and this stub crawl outruns it.
    assert seen["requests"] == 40, (
        f"{seen['requests']} of 40 pages were fetched at the shipped "
        f"{directoryjob.BEAT_EVERY_S}s interval. If this now stops early the guard has "
        f"moved off the beat clock -- an improvement, but a behaviour change, and this "
        f"test is the record that it happened."
    )
    assert "ran_to_the_end" in seen, (
        "the crawl stopped at the shipped interval, so the cancel is no longer bounded "
        "by BEAT_EVERY_S and this file's docstrings are stale"
    )


def test_the_cancelled_card_says_what_the_crawl_spent_too(conn, monkeypatch):
    """THE MUST FIX'S OTHER HALF, and a surviving mutation is what named it.

    The gate's first pass found the FINISHED card reading `0 of 943 requests (0%)` with
    the job's own log saying 943 above it. The fix went into the runner's `finally`, so
    it covers every exit — but only the completed path was guarded, and a mutation making
    the merge conditional on `if not stopped:` survived the whole suite. Its paused card
    read `0 of 943 requests (0%)`: the identical defect, on the path this change is
    named after.

    `_fetch_progress` sums a slot into the numerator only while its `state` is
    `fetching`, and the `finally` writes `stopped` for a cancel and a pause alike. So
    the merged total is the ONLY thing standing between a cancelled crawl and a zero.
    """
    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=_cancel)
    job = jobs.get_job(conn, seen["job"]["job_ref"])
    progress = _fetch_progress(job)

    assert progress["requests"] == 3, (
        f"the cancelled card reads {progress['requests']} requests after 3 landed. The "
        f"log line beside it says 3, and two numbers on one card contradicting each "
        f"other is the shape this whole change exists to end."
    )
    assert any("after 3 request(s)" in line for line in seen["log"]), (
        f"the log does not carry the count the card is being checked against: "
        f"{seen['log']!r}"
    )
    # The denominator is not asserted here: this file's driver declares no frontier, so
    # `expected` is legitimately None. `test_the_declared_frontier_becomes_the_panels_
    # denominator` in the sibling file owns that half, and asserting it here would be a
    # test of this driver's setup rather than of the runner.


def test_a_resumed_crawl_adds_to_what_the_first_leg_spent(conn, monkeypatch):
    """IT ADDS, IT DOES NOT REPLACE -- measured by the gate's second pass.

    Every other writer of `counters["requests"]` accumulates: `jobs._merge_counters` is
    `counters.get("requests", 0) + result.requests_count`, and a resuming job rehydrates
    `counters` from the stored row. The first version of the merged write put `spent`
    there flat, so a crawl paused at a cell boundary and resumed reported only its
    SECOND leg -- 14 pages fetched, 5 on the finished card.
    """
    first = _drive(conn, monkeypatch, pages=9, at_page=None,
                   press=lambda own, ref: None)
    ref = first["job"]["job_ref"]
    after_one = _fetch_progress(jobs.get_job(conn, ref))["requests"]
    assert after_one == 9, f"the first leg reported {after_one} of 9"

    # The same job, run again -- which is what a resume is from this runner's side.
    jobs._update(conn, first["job"]["job_id"], status=JobStatus.QUEUED.value,
                 finished_at=None)
    conn.commit()
    fetcher = _Fetcher()
    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, _count_pages(fetcher)))

    def second_leg(*args, **kwargs):
        beating = kwargs.get("beating") or args[2]
        for page in range(5):
            beating(f"https://muqawil.org/en/contractors?page=9{page}")

    monkeypatch.setattr(directoryjob.contractors, "crawl", second_leg)
    directoryjob.run_directory_crawl_job_once(conn, ref)

    total = _fetch_progress(jobs.get_job(conn, ref))["requests"]
    assert total == 14, (
        f"the finished card reads {total} after two legs of 9 and 5. A flat write "
        f"reports {5} -- only the leg that happened to run last."
    )


def _count_pages(fetcher):
    def fetch(url: str) -> str:
        fetcher.requests_count += 1
        return "<html></html>"
    return fetch


# --- ES-1: the crawl queues its own interpretation -------------------------------------

def test_a_finished_crawl_queues_its_own_interpretation(conn, monkeypatch):
    """HIS WORDS, 2026-09-23: *«المفروض التفسير دا يشتغل تلقائى يعنى المستخدم العادى عمل
    crawl مش هيفهم يعنى اى تفسير اصلا ولية يطر يعمل خطوة زيادة»*.

    A price source is one pass — `capture.py` fetches and ingests straight into the
    warehouse. A directory source was two, with a button between them for a stage that is
    ours, not his. And the engine already knew the second was due: `_work_waiting`
    computes exactly that and drew a line on the card.

    ES-1 in `docs/ENGINEERING-SOURCES.md` is what this rests on.
    """
    fetcher = _Fetcher()

    def fetch(url: str) -> str:
        fetcher.requests_count += 1
        return "<html></html>"

    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, fetch))
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)

    def crawl_and_finish(*args, **kwargs):
        beating = kwargs.get("beating") or args[2]
        for page in range(3):
            beating(f"https://muqawil.org/en/contractors?page={page}")

    monkeypatch.setattr(directoryjob.contractors, "crawl", crawl_and_finish)
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)

    queued = [row for row in conn.execute(
        "SELECT job_ref, job_kind, status, source_keys FROM crawl_job "
        "ORDER BY job_id") if row["job_kind"] == datasetjob.JOB_KIND]

    assert len(queued) == 1, (
        f"the crawl finished and queued {len(queued)} interpretations. He should not "
        f"have to know the stage exists, and the engine already computed that it is due."
    )
    assert queued[0]["status"] == JobStatus.QUEUED.value, (
        f"the interpretation is {queued[0]['status']!r}. QUEUED, not run inline: two "
        f"jobs and two verdicts is what `datasetjob`'s own argument asks for, and it is "
        f"what gives the job a card he can stop it from."
    )
    assert SITE in queued[0]["source_keys"]
    # AND HE IS TOLD, because a second job appearing with no explanation is its own defect.
    log = [row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (jobs.get_job(conn, ref)["job_id"],))]
    assert any("queued the interpretation" in line for line in log), (
        f"nothing in the crawl's log says a second job was queued: {log!r}"
    )


def test_a_stopped_crawl_queues_nothing(conn, monkeypatch):
    """INTERPRETING A SWEEP HE STOPPED IS WORK HE DID NOT ASK FOR.

    The chain sits after the success path's own `return`, so every stop — cancel, pause,
    a job something else settled — reaches the end of the runner without it.

    AN EARLIER VERSION OF THIS DOCSTRING CLAIMED MORE THAN THE TEST HOLDS, and the gate
    measured it: moving the call above `if stopped:` passes every test here, because that
    line is only ever reached with `stopped` empty -- every `stopped.append` is followed
    by a return that leaves the `try`. So that mutation is equivalent, not a gap. What is
    NOT equivalent is moving it into the `except CrawlStopped` handler, which is the
    ordinary cancel-at-a-cell-boundary path, and the test at the foot of this file is
    what holds that.
    """
    seen = _drive(conn, monkeypatch, pages=40, at_page=2, press=_cancel)

    interprets = [row for row in conn.execute(
        "SELECT job_kind FROM crawl_job") if row["job_kind"] == datasetjob.JOB_KIND]
    assert not interprets, (
        f"a cancelled crawl queued {len(interprets)} interpretation(s). He pressed stop."
    )
    assert seen["job"]["status"] == JobStatus.CANCELLED.value


def test_a_crawl_that_cannot_queue_its_interpretation_still_finished(conn, monkeypatch):
    """LOSE THE CHAIN, NEVER THE CRAWL — the rule the heartbeat and the stop guard in this
    same runner both state. The crawl is the work; what follows it is not."""
    fetcher = _Fetcher()
    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, lambda url: "<html></html>"))
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)
    monkeypatch.setattr(directoryjob.contractors, "crawl", lambda *a, **k: None)

    def refuse(*args, **kwargs):
        raise RuntimeError("the queue is closed")

    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    monkeypatch.setattr(directoryjob.jobs if hasattr(directoryjob, "jobs") else jobs,
                        "create_job", refuse)
    directoryjob.run_directory_crawl_job_once(conn, ref)

    job = jobs.get_job(conn, ref)
    assert job["status"] == JobStatus.COMPLETED.value, (
        f"the crawl reads {job['status']!r} because the job AFTER it could not be queued"
    )
    log = [row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (job["job_id"],))]
    assert any("could not be queued" in line for line in log), (
        f"the failure was swallowed rather than recorded: {log!r}"
    )


def test_two_crawls_of_one_source_queue_one_interpretation(conn, monkeypatch):
    """ISSUE 779'S SHAPE, AND THIS CHANGE REPRODUCED IT BEFORE THE GUARD EXISTED.

    Measured on the branch: two finished crawls of one source left TWO `queued`
    interpretations. #779 records what that costs -- *"a worker slot out of
    `job_capacity` (3), held by a job doing nothing for 29 minutes"* and *"the Run
    screen, because the panel adopts the newest active job"*, which is how he came to
    report a working crawl as frozen at `0/938`.

    AND THIS PATH IS WORSE THAN THE BUTTONS THAT ISSUE IS ABOUT. Those needed him to
    press twice. This queues by itself, so a re-run, a schedule or a resume that
    completes stacks them with nobody pressing anything.
    """
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)
    refs = []
    for _ in range(2):
        fetcher = _Fetcher()
        monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                            lambda pace_s, f=fetcher: (f, lambda url: "<html></html>"))
        monkeypatch.setattr(directoryjob.contractors, "crawl", lambda *a, **k: None)
        ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
        conn.commit()
        directoryjob.run_directory_crawl_job_once(conn, ref)
        refs.append(ref)

    queued = [row for row in conn.execute(
        "SELECT job_ref, job_kind FROM crawl_job")
        if row["job_kind"] == datasetjob.JOB_KIND]
    assert len(queued) == 1, (
        f"two crawls of one source queued {len(queued)} interpretations. The second is "
        f"a worker slot doing nothing and, because the panel adopts the newest active "
        f"job, the screen he watches."
    )
    # AND THE SECOND CRAWL SAYS SO, because a step that silently did nothing is
    # indistinguishable from a step that was never reached.
    second = jobs.get_job(conn, refs[1])
    log = [row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (second["job_id"],))]
    assert any("already waiting" in line for line in log), (
        f"the second crawl queued nothing and never said why: {log!r}"
    )


def _finish_one_crawl(conn, monkeypatch, site=SITE):
    """Drive a directory crawl of `site` to completion. Returns its ref."""
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)
    fetcher = _Fetcher()
    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s, f=fetcher: (f, lambda url: "<html></html>"))
    monkeypatch.setattr(directoryjob.contractors, "crawl", lambda *a, **k: None)
    ref = jobs.create_job(conn, [site], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)
    return ref


def test_an_unrelated_active_job_does_not_block_the_interpretation(conn, monkeypatch):
    """THE GUARD IS ON THE KIND, and a mutation that dropped that check survived every
    test until this one: with no other job running, "any active job" and "an active
    interpretation" are the same set.

    They are not the same set in life. A profile crawl, an enrichment run or another
    source's listing crawl is active most of the time on his machine, and a guard that
    counted those would silently stop queueing anything at all — the worst shape a guard
    can take, because nothing would ever fail.
    """
    other = jobs.create_job(conn, [SITE], job_kind="profile_crawl")
    jobs._update(conn, jobs.get_job(conn, other)["job_id"],
                 status=JobStatus.RUNNING.value)
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    queued = [row for row in conn.execute("SELECT job_kind FROM crawl_job")
              if row["job_kind"] == datasetjob.JOB_KIND]
    assert len(queued) == 1, (
        f"{len(queued)} interpretations queued while an unrelated profile_crawl was "
        f"running. The guard is meant to refuse a SECOND INTERPRETATION OF THIS SOURCE, "
        f"not to stand down whenever the engine is busy."
    )


def test_another_sources_interpretation_does_not_block_this_one(conn, monkeypatch):
    """THE GUARD IS ON THE SOURCE, and the mutation that dropped that also survived.

    Two directories are the normal state — muqawil and the Oman register both exist — and
    an interpretation waiting for one must not swallow the other's. The cost would be
    invisible: the second source's rows simply never appear, with no failure anywhere.
    """
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES ('oman_tenderboard', 'Oman', 'https://etendering.tenderboard.gov.om/', "
        "'directory')")
    waiting = jobs.create_job(conn, ["oman_tenderboard"],
                              job_kind=datasetjob.JOB_KIND)
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    interprets = [dict(row) for row in conn.execute(
        "SELECT job_ref, source_keys FROM crawl_job WHERE job_kind = ?",
        (datasetjob.JOB_KIND,))]
    assert len(interprets) == 2, (
        f"{len(interprets)} interpretations exist. The one already waiting is for "
        f"oman_tenderboard ({waiting}); it cannot do muqawil's work, and a guard that "
        f"let it would lose a whole source in silence."
    )
    assert any(SITE in row["source_keys"] for row in interprets), (
        f"no interpretation was queued for {SITE}: {interprets!r}"
    )


# --- the gate's own findings, each pinned ----------------------------------------------

def test_a_completed_interpretation_does_not_block_the_next_crawl(conn, monkeypatch):
    """THE THIRD CONDITION, AND IT WAS THE UNGUARDED ONE.

    Kind and source each got a boundary test; `active_only` did not, and dropping it
    passed every test in this file. Its failure mode is the worst kind: once ONE
    interpretation has COMPLETED for a source, every later crawl of that source would
    find it "waiting" and queue nothing -- for ever, silently, with nothing failing
    anywhere and the rows simply never arriving.
    """
    done = jobs.create_job(conn, [SITE], job_kind=datasetjob.JOB_KIND)
    jobs._finish(conn, jobs.get_job(conn, done)["job_id"], JobStatus.COMPLETED, None)
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    queued = [row for row in conn.execute(
        "SELECT job_ref, status FROM crawl_job WHERE job_kind = ?",
        (datasetjob.JOB_KIND,)) if row["status"] == JobStatus.QUEUED.value]
    assert len(queued) == 1, (
        f"{len(queued)} interpretations queued after one had already COMPLETED. A "
        f"finished job is not a job on its way, and treating it as one stops this "
        f"source interpreting again permanently."
    )


def test_a_paused_interpretation_does_not_block_the_next_crawl(conn, monkeypatch):
    """`paused` WAITS ON HIM AND NEVER ADVANCES ON ITS OWN.

    `scheduler._source_is_busy` decided this for the schedule and wrote down why:
    *"counting them as busy would silently stop that source's schedule from ever firing
    again."* The first version of this guard used `active_only` alone, which includes
    `paused`, so a paused interpretation blocked every future crawl of that source --
    measured on the gate: three crawls, three `None`s.
    """
    stuck = jobs.create_job(conn, [SITE], job_kind=datasetjob.JOB_KIND)
    jobs._update(conn, jobs.get_job(conn, stuck)["job_id"],
                 status=JobStatus.PAUSED.value)
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    queued = [row for row in conn.execute(
        "SELECT job_ref, status FROM crawl_job WHERE job_kind = ?",
        (datasetjob.JOB_KIND,)) if row["status"] == JobStatus.QUEUED.value]
    assert len(queued) == 1, (
        "a PAUSED interpretation blocked the chain. Nothing restarts a paused job but "
        "him, so this source would never interpret again on its own."
    )


def test_any_other_kind_on_this_source_does_not_block_it(conn, monkeypatch):
    """THE BOUNDARY TEST PINNED THE MUTATION, NOT THE BEHAVIOUR, and the gate proved it:
    replacing the kind check with a blocklist naming `profile_crawl` -- the exact kind
    the other test uses -- passed everything. So this drives kinds that blocklist would
    have let through."""
    for kind in ("organization_enrichment", "crawl"):
        other = jobs.create_job(conn, [SITE], job_kind=kind)
        jobs._update(conn, jobs.get_job(conn, other)["job_id"],
                     status=JobStatus.RUNNING.value)
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    queued = [row for row in conn.execute(
        "SELECT job_ref FROM crawl_job WHERE job_kind = ?", (datasetjob.JOB_KIND,))]
    assert len(queued) == 1, (
        f"{len(queued)} interpretations queued while an enrichment and a price crawl "
        f"were running on this source. The guard refuses a second INTERPRETATION, not "
        f"work of any kind."
    )


def test_a_waiting_interpretation_is_found_behind_newer_jobs(conn, monkeypatch):
    """THE WINDOW IS PART OF THE GUARD. `list_jobs` is `ORDER BY job_id DESC LIMIT ?`,
    so an interpretation queued before other work falls out of a short window and the
    duplicate returns. `limit=1` passed every test until this one."""
    first = jobs.create_job(conn, [SITE], job_kind=datasetjob.JOB_KIND)
    for _ in range(4):
        noise = jobs.create_job(conn, [SITE], job_kind="profile_crawl")
        jobs._update(conn, jobs.get_job(conn, noise)["job_id"],
                     status=JobStatus.RUNNING.value)
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    queued = [row for row in conn.execute(
        "SELECT job_ref FROM crawl_job WHERE job_kind = ?", (datasetjob.JOB_KIND,))]
    assert len(queued) == 1 and queued[0]["job_ref"] == first, (
        f"the waiting interpretation {first} sat behind four newer jobs and the guard "
        f"missed it: {[dict(r) for r in queued]!r}"
    )


def test_a_stop_at_a_cell_boundary_queues_nothing(conn, monkeypatch):
    """THE OTHER STOP PATH, AND IT WAS UNCOVERED. Every other test here stops MID-CELL,
    which raises `CrawlAbandoned`. A cancel or pause honoured at a CELL BOUNDARY leaves
    through `except contractors.CrawlStopped` instead, and moving the chain into that
    handler survived the whole file."""
    def stop_at_the_boundary(*args, **kwargs):
        raise directoryjob.contractors.CrawlStopped

    fetcher = _Fetcher()
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)
    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, lambda url: "<html></html>"))
    monkeypatch.setattr(directoryjob.contractors, "crawl", stop_at_the_boundary)
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)

    queued = [row for row in conn.execute(
        "SELECT job_ref FROM crawl_job WHERE job_kind = ?", (datasetjob.JOB_KIND,))]
    assert not queued, (
        f"a crawl stopped at a cell boundary queued {len(queued)} interpretation(s). "
        f"He pressed stop; `CrawlStopped` is the path that carries it."
    )


def test_the_notification_names_the_job_it_queued(conn, monkeypatch):
    """A REF HE CANNOT FOLLOW IS WORSE THAN NO REF. Asserting only that the phrase
    appears let the crawl's OWN ref survive in its place -- he would open the job he was
    already looking at."""
    ref = _finish_one_crawl(conn, monkeypatch)
    queued = [row[0] for row in conn.execute(
        "SELECT job_ref FROM crawl_job WHERE job_kind = ?", (datasetjob.JOB_KIND,))]
    log = [row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (jobs.get_job(conn, ref)["job_id"],))]
    line = next(one for one in log if "queued the interpretation" in one)
    assert queued[0] in line, (
        f"the line reads {line!r}; the job it queued is {queued[0]}"
    )
    assert ref not in line, "it names the crawl's own ref, which he is already reading"


def test_the_lines_survive_the_connection(conn, monkeypatch):
    """`append_log` DOES NOT COMMIT, and the worker closes without one. Both new lines
    are written and committed by hand; removing either commit survived every assertion
    above, because they all read the same open connection that wrote them."""
    _finish_one_crawl(conn, monkeypatch)
    _finish_one_crawl(conn, monkeypatch)          # the second takes the skip branch

    db_path = str(conn.execute("PRAGMA database_list").fetchone()[2])
    own = dbmod.connect(db_path)
    try:
        seen = [row[0] for row in own.execute("SELECT message FROM job_log_entry")]
    finally:
        own.close()
    assert any("queued the interpretation" in one for one in seen), (
        "the line announcing the queued job never left the writing connection"
    )
    assert any("already waiting" in one for one in seen), (
        "the line explaining the skip never left the writing connection"
    )


def test_the_window_is_not_filled_by_finished_jobs(conn, monkeypatch):
    """`active_only=True` IS THE THIRD CONDITION AND IT IS ABOUT THE WINDOW.

    The status filter beside it already refuses a COMPLETED job, so dropping
    `active_only` changes no verdict on any job the guard actually sees -- which is why
    every test above survived the mutation. What it changes is WHICH JOBS IT SEES:
    `list_jobs` is `ORDER BY job_id DESC LIMIT 200`, and without the filter those 200
    slots are filled by history.

    HISTORY IS MOST OF A WAREHOUSE. Every crawl, sweep, enrichment and interpretation
    this source has ever run is terminal and sits above the one live job in that
    ordering. So the failure is not "sometimes": it arrives the day the job table passes
    200 rows and never leaves, and its shape is a duplicate interpretation queued on
    every crawl, for ever, with nothing failing.
    """
    first = jobs.create_job(conn, [SITE], job_kind=datasetjob.JOB_KIND)
    # 200 FINISHED JOBS, NEWER THAN IT -- exactly the window, so with `active_only`
    # dropped the waiting interpretation is the 201st row and invisible.
    conn.executemany(
        "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status, "
        "                       finished_at) "
        "VALUES (?,'update',?,?,'completed','2026-09-01T00:00:00Z')",
        [(f"job_old_{n}", f'["{SITE}"]', "profile_crawl") for n in range(200)])
    conn.commit()

    _finish_one_crawl(conn, monkeypatch)

    queued = [row["job_ref"] for row in conn.execute(
        "SELECT job_ref FROM crawl_job WHERE job_kind = ?", (datasetjob.JOB_KIND,))]
    assert queued == [first], (
        f"the waiting interpretation {first} sat behind 200 finished jobs and the guard "
        f"missed it, so it queued another: {queued!r}"
    )


def test_one_crawl_alone_commits_the_line_it_wrote(conn, monkeypatch):
    """ONE CRAWL, NOT TWO, AND THE DIFFERENCE IS THE WHOLE TEST.

    `test_the_lines_survive_the_connection` drives two, so the SKIP branch's commit
    lands the success branch's uncommitted line as well -- one connection, one
    transaction. Removing the success branch's own `conn.commit()` survived it, and
    survived every other test here too, because they all read the connection that wrote
    them.

    `create_job` COMMITS ITSELF, so the job appears either way. It is the SENTENCE that
    would be lost: the one line telling him a second job exists and naming its ref.
    """
    _finish_one_crawl(conn, monkeypatch)

    db_path = str(conn.execute("PRAGMA database_list").fetchone()[2])
    own = dbmod.connect(db_path)
    try:
        seen = [row[0] for row in own.execute("SELECT message FROM job_log_entry")]
    finally:
        own.close()
    assert any("queued the interpretation" in one for one in seen), (
        "the job was committed and the line announcing it was not. `append_log` does "
        "not commit and the worker closes without one, so he would find a job he never "
        "asked for and no record anywhere of what started it."
    )


def test_the_queued_interpretation_is_an_update_and_not_a_rebuild(conn, monkeypatch):
    """`full_rebuild` ARCHIVES THE DATASET FIRST, and no test pinned the mode.

    This is the one decision the chain makes on its own, so it may only make the
    conservative one. `update` adds what the new pages hold; `full_rebuild` replaces a
    dataset -- and the crawl that triggers this is an ordinary finished crawl, not an
    instruction to rebuild anything. It is also the label the panel draws on the card,
    so the wrong mode reads as his own choice.
    """
    _finish_one_crawl(conn, monkeypatch)

    queued = [(row["job_ref"], row["run_mode"]) for row in conn.execute(
        "SELECT job_ref, run_mode FROM crawl_job WHERE job_kind = ?",
        (datasetjob.JOB_KIND,))]
    assert [mode for _, mode in queued] == [RunMode.UPDATE.value], (
        f"the chain queued {queued!r}. Anything but `update` is a decision about his "
        f"dataset that he did not make."
    )


def test_the_failure_line_survives_the_connection(conn, monkeypatch):
    """THE THIRD EXIT, AND THE ONLY ONE WITHOUT THIS GUARD.

    All three exits of `_queue_the_interpretation` write a line `append_log` does not
    commit, and the worker closes without one. Two have a test that re-reads on a SECOND
    connection for exactly that reason. The failure branch had none:
    `test_a_crawl_that_cannot_queue_its_interpretation_still_finished` reads `conn` --
    the same open connection the runner wrote on -- so deleting that branch's
    `conn.commit()` passed everything.

    And it is the branch where losing the line costs most. The crawl finished, no
    interpretation exists, and the only record of why is this sentence. Without it he has
    stored pages, no rows, and nothing anywhere saying so.
    """
    fetcher = _Fetcher()
    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, lambda url: "<html></html>"))
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)
    monkeypatch.setattr(directoryjob.contractors, "crawl", lambda *a, **k: None)

    def refuse(*args, **kwargs):
        raise sqlite3.IntegrityError("no room at the inn")

    # The crawl's own job is made BEFORE the refusal is armed -- the chain's call is the
    # one being refused, not the runner's own.
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    monkeypatch.setattr(jobs, "create_job", refuse)
    directoryjob.run_directory_crawl_job_once(conn, ref)

    db_path = str(conn.execute("PRAGMA database_list").fetchone()[2])
    own = dbmod.connect(db_path)
    try:
        seen = [row[0] for row in own.execute("SELECT message FROM job_log_entry")]
        levels = [row[0] for row in own.execute(
            "SELECT level FROM job_log_entry WHERE message LIKE ?",
            ("%could not be queued%",))]
    finally:
        own.close()

    assert any("could not be queued" in one for one in seen), (
        f"the crawl {ref} could not queue its interpretation and the line saying so "
        f"never left the writing connection. He is left with pages, no rows and no "
        f"record of why. Committed lines: {seen!r}"
    )
    assert levels == [LogLevel.WARNING.value], (
        f"the line is recorded at {levels!r}. A crawl that could not queue its own "
        f"follow-up is a warning, not an ordinary note -- at INFO it reads as progress."
    )


def test_the_queued_interpretation_says_why_it_exists_in_its_OWN_log(conn, monkeypatch):
    """THE PANE THE PANEL OPENS IS THE NEW JOB'S, NOT THE CRAWL'S.

    `pollJobOnce` adopts the newest live job and draws ITS log, so the line written on the
    crawl -- "queued the interpretation of these pages as job_x" -- is off screen within
    about 1.5 s of being written. Measured on the gate: 2.51 ms between the crawl's
    COMPLETED commit and the interpretation's, against POLL_MS = 1500.

    So a job he did not start would open with an empty log. That is issue 778's shape:
    he reads the panel and cannot tell what is happening, or why.

    NOT A DUPLICATE OF THE LINE ON THE CRAWL. That one tells the crawl's reader what the
    crawl did last. This one tells the interpretation's reader why it exists, and it is
    the only one of the two he will be looking at.
    """
    crawl = _finish_one_crawl(conn, monkeypatch)

    queued = [row["job_ref"] for row in conn.execute(
        "SELECT job_ref FROM crawl_job WHERE job_kind = ?", (datasetjob.JOB_KIND,))]
    assert len(queued) == 1, queued
    own = [row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (jobs.get_job(conn, queued[0])["job_id"],))]

    assert own, (
        f"the interpretation {queued[0]} opens with an empty log, and it is the pane the "
        f"panel repoints to about 1.5 s after the crawl ends. He gets a job he did not "
        f"start and no sentence anywhere he is looking."
    )
    line = own[0]
    assert crawl in line, (
        f"it does not name the crawl that started it, so he cannot get back to what "
        f"bought these pages: {line!r}")
    assert "automatically" in line, (
        f"it does not say the ENGINE started it, so it reads as his own press: {line!r}")
    assert "makes no request" in line or "no request" in line, (
        f"it does not say the run costs no request, which is the whole reason it is safe "
        f"to leave running: {line!r}")


def test_neither_line_names_a_control_that_does_not_exist(conn, monkeypatch):
    """A SENTENCE THAT SENDS HIM SOMEWHERE THAT IS NOT THERE IS WORSE THAN NO SENTENCE.

    Both of these lines told him to stop the job from a place with no such control: one
    said "its own card" and one said "the jobs list". The source card's actions are
    update, table, enrich, changes, settings, pause, sheet, interpret, resume and
    profiles -- `pause` stops the SCHEDULE, not a running job -- and there is no jobs
    list with a Stop anywhere in the panel.

    The only control that ends a running job is the player's Cancel (`app.html`,
    `#mini-cancel`, confirmed by "Cancel this job? Work already saved is kept."), so that
    is the control both lines name, by its label.
    """
    _finish_one_crawl(conn, monkeypatch)
    said = [row[0] for row in conn.execute("SELECT message FROM job_log_entry")]
    about_stopping = [one for one in said if "want it" in one or "stop it" in one.lower()]
    assert about_stopping, f"neither line tells him how to stop it at all: {said!r}"

    for line in about_stopping:
        assert "Cancel" in line, (
            f"it names no control he can find: {line!r}. The player's Cancel is the only "
            f"thing that ends a running job.")
        assert "jobs list" not in line and "its own card" not in line, (
            f"it still sends him to a control that does not exist: {line!r}")
        # AND THE STEP THAT REVEALS IT, because the button is real and hidden.
        # `<details id="miniplayer">` in `extension/app.html` carries no `open`, Cancel
        # sits inside `<div class="mini-body">`, and nothing in `app.js` ever opens it --
        # `$("miniplayer")` has one use there and it only toggles `hidden`. So "press
        # Cancel in the player" named a button he cannot see, which is the same defect
        # as naming one that does not exist, one step in.
        assert "Open the player" in line, (
            f"it names Cancel without the step that shows it: {line!r}. If a reword ever "
            f"fails this line, the reword has to keep BOTH steps -- that is what this "
            f"assertion is for, not the exact words.")
