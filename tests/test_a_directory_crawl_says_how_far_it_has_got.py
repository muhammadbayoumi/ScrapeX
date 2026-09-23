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
from scrapex.connectors import base as connectors_base  # noqa: E402
from scrapex.vocab import JobStage, JobStatus  # noqa: E402
from scrapex.webui.app import _fetch_progress  # noqa: E402

# THIS FILE NAMES `extension/` -- `test_the_card_carries_the_politeness_rows_the_panel_draws`
# asserts the slot carries the four fields `extension/app.js::activityCounters`
# renders, so an extension-only change must still run it. The gate that caught the
# omission is deliberately broad: a false positive costs one marker, a false
# negative costs a guard nobody notices is gone.
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

    def expect_requests(self, pages: int) -> None:
        """`HttpFetcher.expect_requests`'s arithmetic, not a convenient shortcut.

        COUNTED FROM THE REQUESTS ALREADY MADE, which is the whole point and the thing
        the first version of these tests assumed away by setting `expected_requests`
        directly. Sizing spends two requests per cell -- page 1 and page L -- before the
        frontier is known, so the denominator the panel reads is always ABOVE the
        connector's declaration. A stub that ignored that let a docstring claim the Oman
        register's denominator was 943 when the panel shows about 947.
        """
        self.expected_requests = max(int(self.expected_requests or 0),
                                     self.requests_count + int(pages))

    def close(self) -> None:
        self.closed = True


def _counting(fetcher):
    """A fetch that only counts. Shared so a test spelling its own does not drift."""
    def fetch(url: str) -> str:
        fetcher.requests_count += 1
        return "<html></html>"
    return fetch


def _job_now(conn: sqlite3.Connection, ref: str) -> dict:
    """The job row as the API would read it, from a SECOND connection.

    The beats were written on their own connection and this one has to see them
    committed -- the same reason the beat opens its own.
    """
    import json as _json
    own = sqlite3.connect(str(conn.execute("PRAGMA database_list").fetchone()[2]))
    own.row_factory = sqlite3.Row
    try:
        job = dict(own.execute(
            "SELECT * FROM crawl_job WHERE job_ref = ?", (ref,)).fetchone())
    finally:
        own.close()
    job["counters"] = _json.loads(job.get("counters_json") or "{}")
    return job


def _drive(conn: sqlite3.Connection, monkeypatch, *, pages: int,
           frontier: int | None, beat_every_s: float = 0.0,
           sizing_requests: int = 4):
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
            # THROUGH THE REAL GUARD, so the sizing offset is real too: this is the line
            # `crawl_partition` runs after it has sized every cell, and `declare_frontier`
            # is what a connector is allowed to call.
            for spent in range(sizing_requests):
                fetcher.requests_count += 1
            connectors_base.declare_frontier(fetcher, frontier)
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

    # 947, NOT 943, AND THE FOUR ARE THE POINT. `expect_requests` counts from the
    # requests ALREADY MADE (`connectors/base.py:500`) -- sizing spends page 1 and page L
    # per cell before the frontier is known, and those are real requests through this
    # same fetcher. A denominator that ignored them would be short by exactly those pages
    # and the bar would arrive at 100% early. The first version of this test wrote
    # `expected_requests` directly and so could never have seen the difference.
    assert progress["expected"] == 943 + 4, (
        f"expected reads {progress['expected']!r}; the frontier the crawl declared after "
        f"sizing never reached the job, or the sizing requests it counts from were lost"
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
    # 7 pages plus the 4 requests sizing spent before the frontier was declared --
    # both went through this fetcher, so both are in the count the panel reads.
    assert seen["progress"]["requests"] == 7 + 4


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


def test_the_finished_card_still_says_what_the_crawl_spent(conn, monkeypatch):
    """THE ONE THIS FILE COULD NOT SEE, and its own `_drive` says why.

    `_drive` snapshots `_fetch_progress` from INSIDE the crawl, because
    `_fetch_progress` sums a slot into the numerator only while its `state` is
    `fetching`. That was the right fix for reading a live crawl and it made the finished
    card unobservable: every assertion above is taken before the `finally` runs.

    So this drives the runner TO COMPLETION and reads the card afterwards, which is what
    he does -- he comes back to a four-hour crawl and looks at it. Before the merged
    total was written, the card read `0 of 943 requests (0%)` with the job's own log line
    saying 943 directly above it. Worse than saying nothing: without `expected` the panel
    drew `starting...` and claimed no precision at all.
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
        fetcher.expected_requests = 943
        for page in range(9):
            beating(f"https://muqawil.org/en/contractors?page={page}")
        # RETURNS, so the runner writes its `finally` and settles the job -- the whole
        # difference from `_drive`, which raises to freeze the mid-crawl state.

    monkeypatch.setattr(directoryjob.contractors, "crawl", crawl_and_finish)

    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)

    job = jobs.get_job(conn, ref)
    progress = _fetch_progress(job)
    assert progress["requests"] == 9, (
        f"the finished card reads {progress['requests']} requests after 9 landed. "
        f"`_fetch_progress` counts a slot only while it is `fetching` and falls back to "
        f"the merged `counters['requests']`, which this path has to write."
    )
    assert progress["expected"] == 943, (
        "the denominator vanished when the merged total was written -- `json_patch` "
        "keeps `sources`, a plain column write does not"
    )
    # And the number he sees must not contradict the line the job logged beside it.
    spent = [line for line in (row[0] for row in conn.execute(
        "SELECT message FROM job_log_entry WHERE job_id = ? ORDER BY job_log_id",
        (job["job_id"],))) if "request(s)" in line]
    assert spent and "9 request(s)" in spent[-1], (
        f"the log says {spent[-1]!r} while the card says {progress['requests']} -- two "
        f"numbers on one card contradicting each other is the OP-130 shape"
    )


def test_the_card_carries_the_politeness_rows_the_panel_draws(conn, monkeypatch):
    """`activityCounters` renders four more fields, and the directory crawl had none.

    `extension/app.js` draws `Unchanged pages (304)`, `Retries`, `Pace` and whether the
    site's requested delay is being honoured, per source, from this same slot. The first
    version of `_measured` wrote five of the nine fields `capture.py` writes, so the one
    collector that runs for twenty-four hours showed none of the politeness evidence --
    on a fetcher that carries all four. One builder now, in `connectors/base.py`.

    THE VALUES, NOT THE KEYS. An earlier version of this test asserted `field in slot`,
    and a mutation hard-coding `pace_s = 0.0` survived it -- along with 370 other tests.
    That mutation is not cosmetic: `extension/app.js` draws the Pace row only when
    `source.pace_s != null && source.pace_s > 0`, so a falsy value suppresses exactly
    the row this test is named after, which is the defect and not a near miss.
    """
    fetcher = _Fetcher()
    fetcher.not_modified_count = 37
    fetcher.retry_count = 4
    fetcher._min_interval_s = 1.0
    fetcher._honour_crawl_delay = False        # he overrode a delay: it must SHOW

    monkeypatch.setattr(directoryjob.contractors, "make_fetch",
                        lambda pace_s: (fetcher, _counting(fetcher)))
    monkeypatch.setattr(directoryjob, "BEAT_EVERY_S", 0.0)

    def crawl_some_pages(*args, **kwargs):
        beating = kwargs.get("beating") or args[2]
        connectors_base.declare_frontier(fetcher, 943)
        for page in range(4):
            beating(f"https://muqawil.org/en/contractors?page={page}")
        seen["progress"] = _fetch_progress(_job_now(conn, ref))
        raise RuntimeError("stopped on purpose, after the beats were written")

    seen: dict = {}
    monkeypatch.setattr(directoryjob.contractors, "crawl", crawl_some_pages)
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    with pytest.raises(RuntimeError, match="on purpose"):
        directoryjob.run_directory_crawl_job_once(conn, ref)

    slot = seen["progress"]["sources"][SITE]
    assert slot["not_modified"] == 37, (
        f"not_modified reads {slot.get('not_modified')!r}; the 304 count is the single "
        f"best sign a recurring crawl is being cheap and polite"
    )
    assert slot["retries"] == 4, (
        f"retries reads {slot.get('retries')!r}; retries are the earliest sign a site "
        f"is pushing back"
    )
    # `> 0`, because that is the condition `extension/app.js` draws the row on.
    assert slot["pace_s"] == 1.0 and slot["pace_s"] > 0, (
        f"pace_s reads {slot.get('pace_s')!r}. The panel draws the Pace and Rate rows "
        f"only when it is truthy, so a falsy value hides them exactly as a missing key "
        f"would"
    )
    assert slot["honouring_delay"] is False, (
        "honouring_delay reads True on a run that overrode the site's requested delay. "
        "A run that was fast because the site asked for nothing and one that was fast "
        "because we overrode a 10s delay must not look identical while it happens."
    )
