"""A directory crawl must report its request count while it works.

WHAT THIS COST, measured on his own machine on 2026-09-21. He started the Oman vendor
register's first crawl and watched this, for four hours:

    ACTIVITY                                    elapsed 4h 1m
    preparing · preparing                       oman_tenderboard
    starting...
    Sites done                                          0 / 1
    Requests                                                0
    New data rows                                           0

Behind it, 401 pages had been fetched and stored with zero errors. His first question was
whether the crawl had failed.

THE PANEL WAS NOT WRONG, IT WAS BLIND. `webui/app.py::_fetch_progress` builds the
numerator from `counters`, never from `progress_done`, and its own docstring says why:
*"a one-source job is 0/1 for its whole duration, which is the 0% the owner watched for 18
minutes while 1,030 requests succeeded behind it."* The design was already right. The
directory path simply never wrote that counter -- `grep -c 'counters["requests"]'
scrapex/directoryjob.py` returned **0**.

WHY `cell_closed` COULD NOT DO IT. It runs BETWEEN cells, and the Oman register's whole
partition is one cell (`OmanPartition.cells()` returns `(WHOLE,)`, because its paging is
not stable enough to slice). So the only per-cell writer never ran until the sweep ended.
`muqawil_org` has 56 cells and hides this completely, which is why it went unseen.

THE DENOMINATOR WAS ALREADY THERE TOO. `crawl_partition` calls `declare_frontier(fetcher,
sum(last_page * locales + 1))` once after sizing -- 471 x 2 + 1 = 943 for this register --
and nothing carried it onto the job either.

These tests drive `run_directory_crawl_job_once` and read what it wrote, rather than
testing the helper: a guard on the helper alone is the vacuity that
`test_the_runner_really_crawls_under_the_inherited_ref` in the sibling file was written to
close.
"""
from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("fastapi")

from scrapex import db as dbmod, directoryjob, jobs  # noqa: E402
from scrapex.vocab import JobStage, JobStatus  # noqa: E402
from scrapex.webui.app import _fetch_progress  # noqa: E402

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
    """What `HttpFetcher` exposes to this code path, and nothing else.

    `requests_count` and `expected_requests` are the two attributes read. A real
    `HttpFetcher` would open sockets; `declare_frontier` is the guarded setter the crawl
    uses for the second, and it tolerates a fetcher that has neither, which is why this
    minimal stand-in is faithful rather than convenient.

    `close()` IS HERE BECAUSE THE RUNNER CALLS IT, in a `finally` that runs on the way out
    of every crawl. The first version of this stub omitted it and all five tests failed
    with `AttributeError` -- a stub that cannot be closed is not the object the code has.
    """

    def __init__(self) -> None:
        self.requests_count = 0
        self.expected_requests = None
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _drive(conn: sqlite3.Connection, monkeypatch, *, pages: int,
           frontier: int | None, beat_every_s: float = 0.0):
    """Run one directory job through `beating` exactly `pages` times.

    NOTHING REACHES THE NETWORK. `make_fetch` is the seam the runner builds its fetcher
    from, so replacing it replaces both the counter and the transport at once.

    READ WHILE IT RUNS, WHICH IS WHEN THE PANEL READS IT. The snapshot is taken inside the
    crawl, after the last beat and before the stub raises. Reading afterwards measures
    something else: `_fetch_progress` sums a slot into the numerator only while its
    `state` is `fetching`, so a finished or failed job reports the merged total instead --
    and the first version of these tests read four zeroes for exactly that reason, on a
    change that was working.

    `expected` has no such filter, which is why the denominator survived the same mistake
    and the numerator did not. That asymmetry is in `_fetch_progress`, not here.
    """
    seen: dict = {}
    fetcher = _Fetcher()

    def fetch(url: str) -> str:
        fetcher.requests_count += 1
        return "<html></html>"

    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, fetch))
    # The real interval is 20s, so a short test would write one beat or none. Zero makes
    # every page a beat, which is the same code path at a different cadence.
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", beat_every_s)

    def crawl_some_pages(*args, **kwargs):
        # POSITIONAL, for the sibling file's stated reason: the runner calls
        # `contractors.crawl(conn, directory, beating, fetcher, run_ref, ...)`.
        beating = kwargs.get("beating") or args[2]
        if frontier is not None:
            # What `crawl_partition` does after sizing, without the sizing requests.
            fetcher.expected_requests = frontier
        for page in range(pages):
            beating(f"https://muqawil.org/en/contractors?page={page}")
        # ON ITS OWN CONNECTION, because the beats were written on theirs and this one
        # has to see them committed -- the same reason the beat opens its own.
        own = sqlite3.connect(str(conn.execute("PRAGMA database_list").fetchone()[2]))
        own.row_factory = sqlite3.Row
        try:
            seen["job"] = dict(own.execute(
                "SELECT * FROM crawl_job WHERE job_ref = ?", (ref,)).fetchone())
        finally:
            own.close()
        import json as _json
        seen["job"]["counters"] = _json.loads(seen["job"].get("counters_json") or "{}")
        seen["progress"] = _fetch_progress(seen["job"])
        raise RuntimeError("stopped on purpose, after the beats were written")

    monkeypatch.setattr(directoryjob.contractors, "crawl", crawl_some_pages)

    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    with pytest.raises(RuntimeError, match="on purpose"):
        directoryjob.run_directory_crawl_job_once(conn, ref)
    assert seen, "the crawl stub never ran, so nothing below measures anything"
    return seen


def test_the_request_count_reaches_the_panel_while_the_crawl_works(conn, monkeypatch):
    """The whole finding: 401 requests, and the panel read 0."""
    progress = _drive(conn, monkeypatch, pages=7, frontier=None)["progress"]

    assert progress["requests"] == 7, (
        f"the panel would read {progress['requests']} requests after seven pages were "
        f"fetched. That is the 0 he watched for four hours while 401 landed."
    )


def test_the_declared_frontier_becomes_the_panels_denominator(conn, monkeypatch):
    """943 is arithmetic, not a guess, so the bar may be drawn against it."""
    progress = _drive(conn, monkeypatch, pages=7, frontier=943)["progress"]

    assert progress["expected"] == 943, (
        f"expected reads {progress['expected']!r}; the frontier the crawl declared after "
        f"sizing never reached the job, so the bar has no denominator"
    )
    assert progress["basis"] == "declared", (
        f"basis reads {progress['basis']!r}. `declared` is the claim that this is a "
        f"count: every cell published its own page count before it was summed."
    )
    assert progress["unknown_sources"] == [], (
        "the source is still listed as one the panel cannot predict"
    )


def test_a_crawl_that_has_not_sized_yet_reports_a_count_and_no_total(conn, monkeypatch):
    """The honest intermediate state, and it must not be mistaken for a total of zero.

    `_fetch_progress` requires `expected` to be None when nothing knows the total, and
    says a bar drawn at 0% against it is the original defect. So a beat written before
    sizing finishes carries the numerator alone.
    """
    progress = _drive(conn, monkeypatch, pages=3, frontier=None)["progress"]

    assert progress["requests"] == 3
    assert progress["expected"] is None, (
        f"expected reads {progress['expected']!r} before any frontier was declared -- a "
        f"denominator invented here would be a bar drawn against nothing"
    )
    assert progress["unknown_sources"] == [SITE], (
        "the panel cannot say which source it is unable to predict"
    )


def test_the_beat_states_the_count_without_claiming_the_job_is_running(conn, monkeypatch):
    """ISSUE 791'S SHAPE, AND THE REASON THIS WRITES AN OBSERVATION ONLY.

    He pressed Cancel on a running sweep and it fetched all 938 pages anyway: a beat wrote
    `status = running` over the `cancelling` that `set_control` had just parked there.
    `cell_closed` carries the guard for that and withholds the claim while a stop is
    pending -- so a beat that re-asserted the status would reintroduce the defect at a
    cadence of every twenty seconds instead of every cell.

    Driven, not argued: the job is left `queued` here, and seven beats must not move it.
    """
    seen = _drive(conn, monkeypatch, pages=7, frontier=943)
    job = seen["job"]
    # `run_directory_crawl_job_once` sets `preparing` before it crawls, which is its
    # claim to make. What the beat may not do is ADVANCE it -- `running` is written by
    # `cell_closed`, after the guard that withholds it while a stop is pending.
    assert job["status"] == JobStage.PREPARING.value, (
        f"the job reads {job['status']!r} after seven beats. The beat is a record OF the "
        f"work, not a claim about it, and `cell_closed` owns every status transition."
    )
    assert job["status"] != JobStatus.RUNNING.value
    # And the observation still landed, which is the half that must survive.
    assert seen["progress"]["requests"] == 7


def test_the_count_survives_the_real_beat_interval(conn, monkeypatch):
    """Not a test of the cadence -- a test that the cadence cannot swallow the count.

    With the shipped 20-second interval a short crawl writes ONE beat, the first. If the
    count were only ever written on a later beat, every crawl shorter than the interval
    would report zero -- and the first page is exactly when he looks.
    """
    progress = _drive(conn, monkeypatch, pages=5, frontier=943,
                      beat_every_s=directoryjob.BEAT_EVERY_S)["progress"]
    assert progress["requests"] >= 1, (
        "no beat was written inside the real interval, so a crawl shorter than 20 seconds "
        "reports nothing at all"
    )
