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

from scrapex import contractors, db as dbmod, directoryjob, jobs  # noqa: E402
from scrapex.crawlscope import CrawlScope  # noqa: E402
from scrapex.pagewalk import PageWalker  # noqa: E402
from scrapex.vocab import JobControl, JobStatus  # noqa: E402

SITE = "muqawil_org"


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "harvest.db")
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


def _drive(conn, monkeypatch, *, pages: int, at_page, press):
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
    # The shipped interval is 20s, so a short test would check once or never. Zero makes
    # every page a checkpoint -- the same code path at a different cadence.
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)

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
