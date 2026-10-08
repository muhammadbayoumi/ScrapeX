"""A robots.txt the site cannot serve pauses that site's run, on every collector.

THE OWNER'S RULING ON #1585, replacing #1413's for these cases: RFC 9309 §2.3.1.4 --
"If the robots.txt is unreachable due to server or network errors, this means the
robots.txt is undefined and the crawler MUST assume complete disallow". So a 5xx, or a
read that got no answer at all, PAUSES the site's run with its reason in the log, and
no page of that host is fetched (ES-2). A 4xx is untouched: §2.3.1.3 lets it mean "no
file", and tests/test_what_robots_reports_is_what_the_crawl_does.py holds that half.

MEASURED BEFORE THE CHANGE, on the real runners over a cut wire:

  * the listing crawl: a 503 on robots.txt wrote the "could not be read" WARNING and
    asked for the first page anyway; a `CrawlBlocked` reaching the runner settled the
    job FAILED, not paused -- #1448's ruling had reached the price path only;
  * the profile sweep: `contractors.details` filed every exception from a fetch as one
    dead page, `CrawlBlocked` included, so the request breaker tripped on page five
    and the sweep went on asking for every page after it, then reported `completed`.

THE REAL COLLECTORS, NOT STAND-INS. `contractors.crawl` and `contractors.details` run
as shipped, and the fetcher is the one the runner builds from the saved settings with
only its transport swapped -- the pattern
tests/test_a_directory_crawl_takes_the_owners_crawl_settings.py uses.
"""
from __future__ import annotations

import sqlite3

import httpx
import pytest

from scrapex import contractors, directoryjob, jobs, localinbox, profilejob
from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors import base as connectors_base
from scrapex.connectors.base import CrawlBlocked, RobotsUnreachable, ScrapedTable
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope, JobControl

SITE = "muqawil_org"
HOST = "muqawil.org"
ROBOTS = f"https://{HOST}/robots.txt"
#: Far from zero for the reason tests/test_http_fetcher.py gives at FROZEN_CLOCK.
FROZEN_CLOCK = 1_000.0

UNREACHABLE = [
    pytest.param(httpx.Response(503), "HTTP 503", id="503"),
    pytest.param(httpx.ConnectError("connection refused"), "ConnectError", id="exception"),
]


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


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """The pace and the breaker's backoff are measured, never waited out."""
    now = [FROZEN_CLOCK]

    def sleep(seconds):
        now[0] += seconds
    monkeypatch.setattr("scrapex.connectors.base.time.monotonic", lambda: now[0])
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", sleep)


class _Site:
    """The far end of the wire: what robots.txt answers, what a page answers, and
    every request that reached it, in order.

    `robots` is a response, an exception the read raises, or a function of the
    request -- for a site whose answer depends on the host, or on the moment."""

    def __init__(self, robots, page=None) -> None:
        self.robots = robots
        self.page = page or (lambda request: httpx.Response(200, text="<html></html>"))
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(str(request.url))
        if request.url.path == "/robots.txt":
            if isinstance(self.robots, Exception):
                raise self.robots
            if callable(self.robots):
                return self.robots(request)
            return self.robots
        return self.page(request)

    @property
    def pages(self) -> list[str]:
        return [url for url in self.asked if not url.endswith("/robots.txt")]


def _wire(monkeypatch, site: _Site, *, max_attempts: int | None = None) -> dict:
    """Let the runner build its fetcher for real, then cut only the wire."""
    built: dict = {}
    real = contractors.make_fetch

    def cut(crawl_settings):
        fetcher, fetch = real(crawl_settings)
        fetcher._client.close()
        fetcher._client = httpx.Client(transport=httpx.MockTransport(site))
        if max_attempts is not None:
            fetcher._max_attempts = max_attempts
        built["fetcher"] = fetcher
        return fetcher, fetch

    monkeypatch.setattr(contractors, "make_fetch", cut)
    return built


def _messages(conn, ref: str) -> list[str]:
    return [line["message"] for line in jobs.job_logs(conn, ref)]


def _runs(conn) -> list[str]:
    return [row[0] for row in conn.execute("SELECT status FROM crawl_run")]


def _listing(conn) -> str:
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)
    return ref


def _profiles(conn, ids=("7101",)) -> str:
    # NAMED IDS need no sighting ledger and are not subject to the scope, so the REAL
    # `details` reaches its fetch with nothing else set up.
    ref = jobs.create_job(conn, [SITE], checkpoint={"ids": list(ids)},
                          job_kind=profilejob.JOB_KIND)
    conn.commit()
    profilejob.run_profile_crawl_job_once(conn, ref)
    return ref


# ---- the listing crawl ------------------------------------------------------------

@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_the_listing_crawl_pauses_and_asks_for_no_page(conn, monkeypatch, robots,
                                                       named):
    site = _Site(robots)
    built = _wire(monkeypatch, site)

    ref = _listing(conn)

    assert jobs.get_job(conn, ref)["status"] == "paused"
    assert site.asked == [ROBOTS] * built["fetcher"]._max_attempts, site.asked
    assert built["fetcher"].requests_count == 0
    lines = jobs.job_logs(conn, ref)
    paused = [line for line in lines if line["message"].startswith("paused: ")]
    assert len(paused) == 1, _messages(conn, ref)
    assert paused[0]["level"] == "warning"
    said = paused[0]["message"]
    assert HOST in said and named in said and "RFC 9309 §2.3.1.4" in said, said
    assert "Resuming under" in said, "the line does not say what Resume does"
    assert not any(m.startswith("failed:") for m in _messages(conn, ref))
    assert "running" not in _runs(conn), "the crawl's run row was left open"
    job = jobs.get_job(conn, ref)
    # The card's slot says the fetch STOPPED, not that it finished.
    assert job["counters"]["sources"][SITE]["state"] == "stopped", job["counters"]
    # A pause as the owner's writes it: no instruction left behind, no stage.
    assert job["control"] == "none" and job["stage"] is None, job


def test_the_listing_breaker_pauses_too_when_it_trips_on_the_first_request(
        conn, monkeypatch):
    """#1448's ruling reaches the listing: the breaker is a `CrawlBlocked`, and it
    settled the job FAILED here. It trips on the sizing request, which nothing guards."""
    site = _Site(httpx.Response(404), page=lambda request: httpx.Response(429))
    _wire(monkeypatch, site, max_attempts=10)

    ref = _listing(conn)

    assert jobs.get_job(conn, ref)["status"] == "paused"
    assert len(site.pages) == connectors_base.HttpFetcher.BLOCK_LIMIT, site.pages
    assert any(m.startswith("paused: blocked by the site (5 refusals in a row")
               for m in _messages(conn, ref)), _messages(conn, ref)


def test_a_paused_listing_resumes_and_finishes_once_robots_txt_reads(conn,
                                                                     monkeypatch):
    """THE RESUME WORKS AS AN OWNER'S PAUSE DOES: Resume queues it, and the next run
    -- robots.txt readable now -- crawls and completes under the same run ref."""
    site = _Site(httpx.Response(503))
    _wire(monkeypatch, site)
    ref = _listing(conn)
    assert jobs.get_job(conn, ref)["status"] == "paused"

    assert jobs.set_control(conn, ref, JobControl.RESUME) is True
    conn.commit()
    assert jobs.get_job(conn, ref)["status"] == "queued"

    site.robots = httpx.Response(404)
    asked: list[str] = []

    def crawl(*args, **kwargs):
        # The rest of the partition is not this test's question: one page, through
        # the runner's own fetch wrapper, is enough to show the site is crawled again.
        args[2](f"https://{HOST}/en/contractors?page=1")
        asked.append(args[4])

    monkeypatch.setattr(contractors, "crawl", crawl)
    directoryjob.run_directory_crawl_job_once(conn, ref)

    assert jobs.get_job(conn, ref)["status"] == "completed"
    assert site.pages == [f"https://{HOST}/en/contractors?page=1"]
    assert asked == [f"job-{ref}"], "the resume crawled under a different run ref"


def test_a_cancel_pending_when_the_site_stops_the_run_is_honoured(conn, monkeypatch):
    """THE ROW OUTRANKS THE EXCEPTION. He pressed Cancel while robots.txt was being
    read; pausing would leave him a job to cancel a second time."""
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    refs: list[str] = []

    pressed: list[bool] = []

    def robots_after_a_cancel(request: httpx.Request) -> httpx.Response:
        # ONCE: the read is retried, and a second press on a job already
        # `cancelling` is a different question from the one asked here.
        if not pressed:
            own = dbmod.connect(db_file)
            try:
                pressed.append(jobs.set_control(own, refs[0], JobControl.CANCEL))
                own.commit()
            finally:
                own.close()
        return httpx.Response(503)

    _wire(monkeypatch, _Site(robots_after_a_cancel))
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    refs.append(ref)
    conn.commit()

    directoryjob.run_directory_crawl_job_once(conn, ref)

    assert jobs.get_job(conn, ref)["status"] == "cancelled"
    assert any("a cancel was already pending" in m for m in _messages(conn, ref))


def test_a_job_already_settled_is_not_resurrected_by_the_pause(conn):
    """`pause_for_the_site` on a job something else finished leaves it as it is."""
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    job = jobs.get_job(conn, ref)
    jobs._finish(conn, job["job_id"], jobs.JobStatus.CANCELLED, None)
    conn.commit()

    directoryjob.pause_for_the_site(
        conn, job, ref, SITE, RobotsUnreachable("x: robots.txt could not be reached"),
        "Resuming does nothing")

    assert jobs.get_job(conn, ref)["status"] == "cancelled"
    assert any("already settled" in m for m in _messages(conn, ref))


# ---- the profile sweep -------------------------------------------------------------

@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_the_profile_sweep_pauses_and_asks_for_no_page(conn, monkeypatch, robots,
                                                       named):
    """The REAL `details`: its per-page guard filed this as one dead page, then the
    next, and the sweep `completed` having stored nothing."""
    site = _Site(robots)
    built = _wire(monkeypatch, site)

    ref = _profiles(conn, ids=("7101", "7102"))

    assert jobs.get_job(conn, ref)["status"] == "paused"
    assert site.asked == [ROBOTS] * built["fetcher"]._max_attempts, site.asked
    assert built["fetcher"].requests_count == 0
    lines = jobs.job_logs(conn, ref)
    paused = [line for line in lines if line["message"].startswith("paused: ")]
    assert len(paused) == 1, _messages(conn, ref)
    assert paused[0]["level"] == "warning"
    said = paused[0]["message"]
    assert HOST in said and named in said and "RFC 9309 §2.3.1.4" in said, said
    assert "Resuming re-reads" in said, said
    assert not any(m.startswith("failed:") for m in _messages(conn, ref))
    assert not any(named in m and m.startswith("  [") for m in _messages(conn, ref)), (
        "a page was filed as a failed page before the pause")
    assert _runs(conn) == ["partial"], "the sweep's run row was not closed as partial"


def test_the_breaker_stops_the_profile_sweep_instead_of_being_swallowed(conn,
                                                                        monkeypatch):
    """#1448 on the profile sweep: four contractors are eight pages, the site refuses
    every one, and the breaker trips on the fifth. Before, pages six to eight were
    asked for anyway and the sweep read `completed`."""
    site = _Site(httpx.Response(404), page=lambda request: httpx.Response(403))
    _wire(monkeypatch, site, max_attempts=1)

    ref = _profiles(conn, ids=("7101", "7102", "7103", "7104"))

    assert len(site.pages) == connectors_base.HttpFetcher.BLOCK_LIMIT, site.pages
    assert jobs.get_job(conn, ref)["status"] == "paused"
    assert any(m.startswith("paused: blocked by the site (5 refusals in a row")
               for m in _messages(conn, ref)), _messages(conn, ref)
    # The four refusals before the trip are still ordinary failed pages, said.
    assert sum(m.startswith("  [") and "HTTPStatusError" in m
               for m in _messages(conn, ref)) == 4, _messages(conn, ref)
    assert _runs(conn) == ["partial"]
    # THE RUN ROW'S ACCOUNT: nothing stored, the four refused pages, five requests.
    assert tuple(conn.execute("SELECT rows_seen, errors_count, requests_count "
                              "FROM crawl_run").fetchone()) == (0, 4, 5)


def test_a_run_row_that_cannot_be_closed_does_not_swallow_the_stop(conn, monkeypatch):
    """THE RECORD MAY NOT DESTROY THE OUTCOME. A locked warehouse at `close_run` must
    not turn the site's stop into an OperationalError the job settles as FAILED --
    and the row it could not close is said, not skipped in silence."""
    import sqlite3

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    site = _Site(httpx.Response(503))
    fetcher, fetch = contractors.make_fetch({"min_interval_s": 0.0})
    fetcher._client = httpx.Client(transport=httpx.MockTransport(site))
    said: list[str] = []
    monkeypatch.setattr(contractors.runs, "close_run", locked)

    with contractors.lines_go_to(said.append), pytest.raises(RobotsUnreachable):
        contractors.details(conn, directoryjob.directories.get(SITE), fetch, fetcher,
                            "locked-run", ids=("7101",))
    fetcher.close()

    assert any(line.startswith("could not close this run's row: OperationalError: "
                               "database is locked") for line in said), said


def test_a_pause_pending_when_the_site_stops_the_run_settles_as_one_pause(
        conn, monkeypatch):
    """He pressed Pause while robots.txt was being read: one pause, and the pending
    instruction is cleared rather than left to fire on the resumed run."""
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    refs: list[str] = []
    pressed: list[bool] = []

    def robots_after_a_pause(request: httpx.Request) -> httpx.Response:
        if not pressed:
            own = dbmod.connect(db_file)
            try:
                pressed.append(jobs.set_control(own, refs[0], JobControl.PAUSE))
                own.commit()
            finally:
                own.close()
        return httpx.Response(503)

    _wire(monkeypatch, _Site(robots_after_a_pause))
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    refs.append(ref)
    conn.commit()

    directoryjob.run_directory_crawl_job_once(conn, ref)

    assert pressed == [True]
    job = jobs.get_job(conn, ref)
    assert job["status"] == "paused" and job["control"] == "none", job
    assert sum(m.startswith("paused: ") for m in _messages(conn, ref)) == 1


def test_a_paused_sweep_resumes_once_robots_txt_reads(conn, monkeypatch):
    site = _Site(httpx.Response(503))
    _wire(monkeypatch, site)
    ref = _profiles(conn)
    assert jobs.get_job(conn, ref)["status"] == "paused"

    assert jobs.set_control(conn, ref, JobControl.RESUME) is True
    conn.commit()
    site.robots = httpx.Response(404)
    profilejob.run_profile_crawl_job_once(conn, ref)

    assert jobs.get_job(conn, ref)["status"] == "completed"
    assert len(site.pages) == 2, site.pages        # one contractor, two locales


@pytest.mark.parametrize("robots,page", [
    pytest.param(httpx.Response(503), None, id="unreachable"),
    pytest.param(httpx.Response(404), lambda request: httpx.Response(403), id="breaker"),
])
def test_the_pooled_sweep_stops_every_worker(conn, monkeypatch, robots, page):
    """THE COMMAND LINE'S POOL. `ThreadPoolExecutor.__exit__` runs every queued task
    after one raises, so without the halt each queued page would still be asked for --
    one request each against a site whose breaker had tripped."""
    site = _Site(robots, page=page)
    fetcher, fetch = contractors.make_fetch({"min_interval_s": 0.0})
    fetcher._client = httpx.Client(transport=httpx.MockTransport(site))
    fetcher._max_attempts = 1
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    ids = tuple(str(7100 + n) for n in range(10))           # twenty pages
    directory = directoryjob.directories.get(SITE)
    workers = 3

    with pytest.raises(CrawlBlocked):
        contractors.details(conn, directory, fetch, fetcher, "pool-run", ids=ids,
                            workers=workers, connect=lambda: dbmod.connect(db_file))
    fetcher.close()

    if page is None:
        assert site.asked == [ROBOTS], site.asked  # max_attempts is 1 here
    else:
        # The trip, plus at most what the other workers already had in flight.
        limit = connectors_base.HttpFetcher.BLOCK_LIMIT
        assert limit <= len(site.pages) <= limit + workers - 1, site.pages
    assert _runs(conn) == ["partial"]


def test_the_pooled_sweep_counts_every_page_its_workers_stored(conn, monkeypatch):
    """THE RUN ROW IS AN ACCOUNT, AND IT SAID NOTHING WAS STORED. Raising at the first
    blocked future dropped every later future's result, so pages other workers had
    stored -- on disk, under the run -- closed as `rows_seen=0`, and their notes went
    unsaid. Six pages answer, then the site refuses until the breaker trips."""
    served: list[str] = []
    guard = __import__("threading").Lock()

    def six_then_refuse(request: httpx.Request) -> httpx.Response:
        with guard:
            served.append(str(request.url))
            n = len(served)
        if n <= 6:
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(403)

    site = _Site(httpx.Response(404), page=six_then_refuse)
    fetcher, fetch = contractors.make_fetch({"min_interval_s": 0.0})
    fetcher._client = httpx.Client(transport=httpx.MockTransport(site))
    fetcher._max_attempts = 1
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    ids = tuple(str(7100 + n) for n in range(10))           # twenty pages
    said: list[str] = []

    with contractors.lines_go_to(said.append), pytest.raises(CrawlBlocked):
        contractors.details(conn, directoryjob.directories.get(SITE), fetch, fetcher,
                            "pool-run", ids=ids, workers=3,
                            connect=lambda: dbmod.connect(db_file))
    fetcher.close()

    on_disk = conn.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot WHERE crawl_run_ref = 'pool-run'"
    ).fetchone()[0]
    rows_seen, errors = conn.execute(
        "SELECT rows_seen, errors_count FROM crawl_run").fetchone()
    assert on_disk == 6, on_disk
    assert rows_seen == on_disk, f"the run row says {rows_seen}, the disk holds {on_disk}"
    refused = [line for line in said if "HTTPStatusError" in line]
    assert errors == len(refused), (errors, said)
    assert len(refused) >= 4, "the refusals before the trip were not said"


def test_one_dead_profile_is_still_one_failed_page(conn, monkeypatch):
    """THE ISOLATION THAT STAYS. A 404 is not the site's stop: filed, said, and the
    sweep carries on to `completed`."""
    site = _Site(httpx.Response(404), page=lambda request: (
        httpx.Response(404) if "7101" in str(request.url) else
        httpx.Response(200, text="<html></html>")))
    _wire(monkeypatch, site, max_attempts=1)

    ref = _profiles(conn, ids=("7101", "7102"))

    assert jobs.get_job(conn, ref)["status"] == "completed"
    assert len(site.pages) == 4, site.pages
    assert sum(m.startswith("  [") and "HTTPStatusError" in m
               for m in _messages(conn, ref)) == 2, _messages(conn, ref)


# ---- the price path ----------------------------------------------------------------

_BUILDER = RowBuilder(COMMODITY_PRICE)


def _price_entry() -> SourceEntry:
    return SourceEntry.model_validate({
        "source_key": "GPP_ENERGY", "source_name": "أسعار الطاقة العالمية",
        "base_url": "https://www.globalpetrolprices.com",
        "family": "static-html-table", "cadence": "weekly", "authority": "aggregator",
        "currency": "USD",
        "extract": [ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                                scope=ExtractScope.LATEST_ONLY,
                                materials=["DIESEL"], regions=["*"])],
    })


class _TwoHostConnector:
    """One page from a host whose robots.txt reads, then one from a host whose does
    not: the only way a robots pause can land AFTER a page was kept, since a fetcher
    reads each host's file before that host's first page."""

    connector_id = "two-hosts"

    def __init__(self, fetcher) -> None:
        self.fetcher = fetcher
        self.skip_tokens: set[str] = set()

    def fetch(self, entry):
        for token, url in (("DIESEL--EG", "https://good.test/eg"),
                           ("DIESEL--SA", "https://down.test/sa")):
            if token in self.skip_tokens:
                continue
            self.fetcher.get(url)
            row = _BUILDER.row(material_key="DIESEL", country_code_alpha2=token[-2:],
                               currency="EGP", unit="liter", tax_included="1",
                               price="1.00", provenance="observed",
                               price_basis="original")
            yield ScrapedTable("GPP_ENERGY", ExtractKind.COMMODITY_PRICE, url,
                               _BUILDER.header, [row], page_token=token)


@pytest.fixture()
def journal(tmp_path, monkeypatch):
    jdir = tmp_path / "job-journal"
    monkeypatch.setattr(localinbox, "JOURNAL_DIR", jdir)
    return jdir


@pytest.fixture()
def memory() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def _price_wire(monkeypatch, site, connector_for=None) -> dict:
    """The real connector and fetcher `capture` builds, with only the wire cut."""
    import scrapex.capture as capmod

    built: dict = {}
    real = capmod.build_connector

    def cut(entry, crawl_settings=None):
        connector, fetcher = real(entry, crawl_settings)
        fetcher._client.close()
        fetcher._client = httpx.Client(transport=httpx.MockTransport(site))
        built["fetcher"] = fetcher
        return (connector_for(fetcher) if connector_for else connector), fetcher

    monkeypatch.setattr(capmod, "build_connector", cut)
    return built


@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_a_price_source_pauses_and_says_why_not_that_it_was_blocked(
        memory, journal, monkeypatch, robots, named):
    """The REAL connector of a price source. The price path already paused on any
    `CrawlBlocked` (#1448); what this guards is that no page goes out and that the
    line names robots.txt -- "blocked by the site" over a refused connection would
    send him looking for a ban that does not exist."""
    site = _Site(robots)
    built = _price_wire(monkeypatch, site)
    ref = jobs.create_job(memory, ["GPP_ENERGY"])

    jobs.run_job_once(memory, ref, {"GPP_ENERGY": _price_entry()})

    assert site.pages == [], site.pages
    assert built["fetcher"].requests_count == 0
    lines = [line for line in jobs.job_logs(memory, ref)
             if line["source_key"] == "GPP_ENERGY"]
    said = [line for line in lines if "could not be reached" in line["message"]]
    assert len(said) == 1, [line["message"] for line in lines]
    assert said[0]["level"] == "warning"
    assert named in said[0]["message"] and "RFC 9309" in said[0]["message"]
    assert "blocked by the site" not in said[0]["message"], said[0]["message"]
    assert "no page was kept" in said[0]["message"], said[0]["message"]
    assert not any(line["message"].startswith("failed:") for line in lines)
    # And the job's own error text, the one the finished card shows, says the same.
    error = jobs.get_job(memory, ref)["error_summary"]
    assert "could not be reached" in error and "blocked by the site" not in error, error


def test_a_price_source_paused_after_a_page_keeps_it_for_resume(memory, journal,
                                                                 monkeypatch):
    """The journal is untouched by the new cause: the page fetched before the pause
    stays, and the line says Resume continues from it."""
    site = _Site(lambda request: httpx.Response(
        503 if request.url.host == "down.test" else 404))
    _price_wire(monkeypatch, site, connector_for=_TwoHostConnector)
    ref = jobs.create_job(memory, ["GPP_ENERGY"])

    jobs.run_job_once(memory, ref, {"GPP_ENERGY": _price_entry()})

    assert site.pages == ["https://good.test/eg"], site.pages
    assert localinbox.list_tokens(journal, "GPP_ENERGY") == {"DIESEL--EG"}
    said = [m for m in _messages(memory, ref) if "could not be reached" in m]
    assert len(said) == 1 and "1 fetched page(s) kept" in said[0], said
    assert "down.test" in said[0], said
