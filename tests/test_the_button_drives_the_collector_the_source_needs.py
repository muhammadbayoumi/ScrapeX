"""The panel's crawl button reached the price collector for a contractor directory.

WHAT WAS ACTUALLY WRONG. `REQ-45` taught `POST /api/jobs` to accept `muqawil_org` -- it
had been answering 404, which is why every muqawil crawl to date ran from a terminal. But
the worker then handed every queued source to `capture_source`, and `capture_source`
returns a `CaptureResult` whose counters are `observations`, `duplicates`, `products`,
`variants` and `attributes`. A contractor LISTING crawl produces none of those: it
produces stored pages, a per-cell completeness proof, arrivals and departures. So the key
was accepted at the door and the wrong collector ran behind it -- and `R-81` says a
command-line answer is not an answer, so "it works from the terminal" was not one.

THE SHAPE OF THE FIX IS NOT NEW, WHICH IS THE POINT. `organization_enrichment` already
established that a job kind gets its own runner reached from the job loop, sharing the job
row, the log, the progress fields and the pause/cancel controls and nothing else. This
follows it exactly, and the two-branch `if` in `_start_job` becomes a table -- «خلى الشغل
dry» -- with `JOB_KINDS` derived from that table rather than listed a thousand lines away
from it.

WHAT THESE TESTS DO NOT DO. Not one of them opens a socket. The crawl itself is
`contractors.crawl`, which has its own suite; what is under test here is the three things
a JOB adds to it -- the log gets the crawl's own lines, progress is counted in cells, and
a pause or cancel is applied at a cell boundary -- plus the two seams that make a mistake
impossible to hide: a kind the database refuses, and a kind no runner claims.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import time

import pytest

from scrapex import contractors, directories, directoryjob, jobs
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.vocab import JobControl, JobStatus, RunMode


@pytest.fixture(autouse=True)
def _log_goes_nowhere_real(tmp_path, monkeypatch):
    """`say` writes into `~/.scrapex/trial/`, and a suite that writes to a real home
    is a suite that cannot be trusted twice."""
    monkeypatch.setattr(contractors, "LOG", tmp_path / "trial" / "listing.log")


@pytest.fixture()
def conn(tmp_path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


# ---- the two registries may not drift ---------------------------------------

def test_every_kind_a_job_may_have_is_a_kind_a_worker_can_run():
    """THE DRIFT THIS REPLACES WAS TWO FACTS A THOUSAND LINES APART.

    `JOB_KINDS` was a literal set near the top of `jobs.py`; the branch that chose a
    runner was near the bottom. A kind added to one and forgotten in the other is either
    refused at the door for no reason a reader can see, or accepted and handed to the
    price collector in silence -- which is the defect this whole change is about, one
    level up.

    `JOB_KINDS` is derived from `SPECIALISED_RUNNERS` now, so this asserts the property
    that derivation buys rather than re-deriving it: every kind resolves to something
    callable, except the price crawl, whose runner is deliberately absent because it
    needs five arguments this table has nowhere to put.
    """
    assert "crawl" in jobs.JOB_KINDS
    assert jobs.runner_for("crawl") is None, (
        "the price crawl gained a table entry, but `run_job_once` takes a manifest, a "
        "capture, a backup, a connect factory and an admission -- see the comment on "
        "SPECIALISED_RUNNERS")
    for kind in sorted(jobs.JOB_KINDS - {"crawl"}):
        runner = jobs.runner_for(kind)
        assert callable(runner), f"{kind!r} is an accepted kind with no runner"
    assert jobs.runner_for("directory_crawl").__name__ == \
        "run_directory_crawl_job_once"


def test_the_database_accepts_exactly_the_kinds_the_code_does(conn):
    """A CHECK CONSTRAINT AND A PYTHON SET, WITH NOTHING COMPARING THEM.

    `job_kind` arrived in `0011` with `CHECK (job_kind IN ('crawl',
    'organization_enrichment'))`, and SQLite offers no way to alter a CHECK -- it needs a
    table rebuild, which is what `0017` does. So the moment the route learned to name a
    third kind, `create_job` failed with `CHECK constraint failed` and the job was never
    written. Measured: that is exactly how this was found.

    Asserted in both directions, because one direction is the cheap half. A kind Python
    allows and the database refuses is a job that cannot be queued; a kind the database
    allows and Python does not is a row no worker will ever pick up.
    """
    accepted = set()
    for kind in sorted(jobs.JOB_KINDS):
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, status, source_keys, job_kind) "
            "VALUES (?, 'update', 'queued', '[]', ?)", (f"probe-{kind}", kind))
        accepted.add(kind)
    conn.commit()
    assert accepted == set(jobs.JOB_KINDS)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, status, source_keys, job_kind) "
            "VALUES ('probe-nonsense', 'update', 'queued', '[]', 'nonsense')")
    conn.rollback()


def test_the_kind_string_is_written_once(conn):
    """`directoryjob.JOB_KIND` is the name, and `jobs.SPECIALISED_RUNNERS` reads it
    rather than spelling it again. A second spelling is a kind the route queues and no
    runner claims -- which the database would accept, because the CHECK holds the
    string, not the mapping."""
    assert directoryjob.JOB_KIND in jobs.SPECIALISED_RUNNERS
    assert jobs.SPECIALISED_RUNNERS[directoryjob.JOB_KIND][1] == \
        "run_directory_crawl_job_once"


# ---- the runner refuses what it cannot honour --------------------------------

def test_a_job_of_another_kind_is_refused_rather_than_run(conn):
    """The runner is reached by a table now, and a table can be wrong. A directory
    runner handed an enrichment job would crawl a site nobody asked about."""
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind="organization_enrichment")

    with pytest.raises(ValueError, match="organization_enrichment"):
        directoryjob.run_directory_crawl_job_once(conn, job_ref)


def test_a_job_naming_a_source_that_is_not_a_directory_is_refused(conn):
    """REFUSED, NOT FALLEN BACK TO THE PRICE PATH. A `directory_crawl` whose key
    `BUILDERS` does not know is a mistake above this module, and running the price
    collector over it would report a success about a source nobody crawled."""
    job_ref = jobs.create_job(conn, ["MADAR"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)

    with pytest.raises(directoryjob.NotADirectory, match="MADAR"):
        directoryjob.run_directory_crawl_job_once(conn, job_ref)


def test_two_directories_in_one_job_are_refused_by_the_runner(conn):
    """ONE DENOMINATOR PER JOB, and the reason is the progress figure rather than
    tidiness: cells are the denominator, two directories have different cell counts,
    and a bar mixing them cannot say what is left of either. The route refuses this
    too; the runner refuses it again because the route is not its only caller."""
    job_ref = jobs.create_job(conn, ["muqawil_org", "muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)

    with pytest.raises(ValueError, match="exactly one directory"):
        directoryjob.run_directory_crawl_job_once(conn, job_ref)


def test_a_finished_job_is_not_crawled_again(conn, monkeypatch):
    """A cancelled job that ran again would crawl a site the owner has already
    stopped, which is the one thing a re-pick must never do."""
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET status = ? WHERE job_ref = ?",
                 (JobStatus.CANCELLED.value, job_ref))
    conn.commit()

    def _never(*a, **k):
        raise AssertionError("a cancelled job reached the crawl")

    monkeypatch.setattr(contractors, "crawl", _never)
    found = directoryjob.run_directory_crawl_job_once(conn, job_ref)

    assert found["status"] == JobStatus.CANCELLED.value


# ---- the crawl's own report reaches the job log -------------------------------

def test_the_crawls_own_lines_reach_the_job_log(conn, monkeypatch):
    """THE PANEL SHOWS THE CRAWL'S WORDS, NOT A SUMMARY WRITTEN BESIDE THEM.

    `say`'s docstring has always claimed "one line to the console AND to the log" while
    only printing and appending to a file. A job that wrote its own summary instead
    would be a second account of the same run, free to disagree with the console's --
    and the crawl already says the things worth reading: the registered scope, the
    validators it replayed, each cell's outcome.
    """
    said: list[str] = []
    with contractors.lines_go_to(said.append):
        contractors.say("registered scope: full_then_listing")
        contractors.say("  [1/56] region_id_1")

    assert said == ["registered scope: full_then_listing", "  [1/56] region_id_1"]

    # AND THE SINK DOES NOT OUTLIVE ITS BLOCK. One that did would append a later
    # command's output to a finished job's log, and the panel would show a job that
    # kept talking after it ended.
    contractors.say("after the block")
    assert said == ["registered scope: full_then_listing", "  [1/56] region_id_1"]


def test_the_file_log_is_written_whether_a_sink_is_installed_or_not():
    """THE REGRESSION THE SINK NEARLY SHIPPED, and it is here because it was real.

    The first draft put `if sink is None: return` in FRONT of `say`'s file write, so
    every command-line run -- every run with no sink, which is all of them until a job
    starts one -- would silently have stopped writing `LOG`. That file is what the
    owner's own crawl of 2026-08-23 was read back from.
    """
    contractors.say("with no sink at all")
    assert "with no sink at all" in contractors.LOG.read_text(encoding="utf-8")

    with contractors.lines_go_to(lambda line: None):
        contractors.say("and with one")
    assert "and with one" in contractors.LOG.read_text(encoding="utf-8")


def test_a_sink_that_raises_loses_the_log_and_not_the_crawl():
    """`say` MAY NOT RAISE -- the rule that already cost this track hours, one layer
    out. The sink writes to SQLite, which can be locked, and a locked log must never end
    a crawl. Dropped rather than retried: a retry loop here would hold hours of fetching
    on the one thing that is only a record of it."""
    def explode(line: str) -> None:
        raise sqlite3.OperationalError("database is locked")

    with contractors.lines_go_to(explode):
        contractors.say("this must not raise")
        contractors.say("and neither must this")

    assert "this must not raise" in contractors.LOG.read_text(encoding="utf-8")


# ---- stopping between cells ---------------------------------------------------

class _CellByCell:
    """Stands in for `crawl_partition` and calls its `on_cell` hook once per cell.

    NOT A NETWORK, AND NOT A CRAWL EITHER. What is under test is the boundary: `crawl`
    calls `report` after each cell closes, and `on_cell` is asked there. This provides
    the boundary and counts how many were reached, which is the only number the stop
    behaviour can be judged on.
    """

    def __init__(self, cells: int = 4) -> None:
        self.cells = cells
        self.reported = 0

    def __call__(self, *args, **kwargs):
        from scrapex.partitioncrawl import (
            WHOLE,
            Attempt,
            CellOutcome,
            CellSize,
            PartitionOutcome,
        )

        # `on_cell` IS `crawl_partition`'S OWN NAME for the report hook, which is
        # exactly why `contractors.crawl`'s stop question is called
        # `between_cells`: this fake found the collision.
        report = kwargs["on_cell"]
        size = CellSize(cell=WHOLE, last_page=1, cards_per_page=1, tail_cards=1,
                        requests=1)
        for _ in range(self.cells):
            self.reported += 1
            report(CellOutcome(size=size, attempts=(
                Attempt(ids=(), pages_read=1, witnessed=True, note="fake",
                        run_ref="fake-a1"),)))
        return PartitionOutcome(whole=size, cells=(), whole_at_end=None, parent=WHOLE)


def test_a_stop_asked_for_at_a_cell_boundary_ends_the_crawl_there(conn, monkeypatch):
    """BETWEEN CELLS IS THE ONLY SAFE PLACE, and the reason is the proof.

    A cell's completeness claim compares an id sequence against a witness read of page
    one, so a cell interrupted halfway has fetched pages and proved nothing. Stopping
    between cells keeps every closed cell's proof and loses only the pages of the one in
    flight -- and those are on disk, so a resume under the same run ref skips them.
    """
    partition = _CellByCell(cells=4)
    monkeypatch.setattr(contractors, "crawl_partition", partition)
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")
    seen: list[int] = []

    def stop_after_two() -> bool:
        seen.append(len(seen) + 1)
        return len(seen) >= 2

    with pytest.raises(contractors.CrawlStopped):
        contractors.crawl(conn, directories.get(), None, None, "run-1",
                          contractors.DEFAULT_MAX_ATTEMPTS, between_cells=stop_after_two)

    assert seen == [1, 2], "the crawl kept going after it was told to stop"
    assert partition.reported == 2


def test_the_cells_outcome_is_said_before_the_stop_is_asked_for(conn, monkeypatch):
    """Asking first would end the run one line short of the report for the cell that
    had already finished paying for itself."""
    monkeypatch.setattr(contractors, "crawl_partition", _CellByCell(cells=3))
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")
    said: list[str] = []

    with contractors.lines_go_to(said.append), pytest.raises(contractors.CrawlStopped):
        contractors.crawl(conn, directories.get(), None, None, "run-1",
                          contractors.DEFAULT_MAX_ATTEMPTS, between_cells=lambda: True)

    assert any("[1/" in line for line in said), (
        "the cell that closed was not reported before the stop: " + str(said))


def test_no_between_cells_means_the_crawl_is_not_interruptible(
        conn, monkeypatch):
    """The command line passes no `between_cells`, and a default that stopped anything would
    change what `scrapex contractors --crawl` does."""
    partition = _CellByCell(cells=3)
    monkeypatch.setattr(contractors, "crawl_partition", partition)
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")

    contractors.crawl(conn, directories.get(), None, None, "run-1",
                      contractors.DEFAULT_MAX_ATTEMPTS)

    assert partition.reported == 3


# ---- the job runner, driven end to end over the fake partition ----------------

def _run_the_job(conn, monkeypatch, *, cells: int = 3, control: str | None = None):
    """Queue a directory crawl and run it, with the partition faked and no network."""
    partition = _CellByCell(cells=cells)
    monkeypatch.setattr(contractors, "crawl_partition", partition)
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (_QuietFetcher(), lambda url: ""))
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)
    if control is not None:
        conn.execute("UPDATE crawl_job SET control = ? WHERE job_ref = ?",
                     (control, job_ref))
        conn.commit()
    found = directoryjob.run_directory_crawl_job_once(conn, job_ref)
    return job_ref, found, partition


class _QuietFetcher:
    requests_count = 7

    def close(self) -> None:
        return None

    def validators(self) -> dict:
        return {}

    def remember_validators(self, kept) -> None:
        return None


def test_a_directory_job_runs_the_listing_crawl_and_succeeds(conn, monkeypatch):
    """The whole point: a job the panel could queue, executed by the collector the
    source actually needs."""
    job_ref, found, partition = _run_the_job(conn, monkeypatch, cells=3)

    assert found["status"] == JobStatus.COMPLETED.value
    assert partition.reported == 3
    assert found["progress_total"] == len(
        directories.get().partition().cells()), (
        "progress is counted in cells, and the denominator must be the partition's")
    logged = " ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "listing crawl" in logged
    assert "LISTING phase" in logged, (
        "the job did not say the profile pages are a separate collector, so a finished "
        "listing crawl reads as everything the site publishes")


def test_the_run_ref_is_the_jobs_own_so_a_resume_skips_its_pages(conn, monkeypatch):
    """`already_stored` is scoped to the run ref, and the job ref is the only label
    that survives a pause and a re-pick."""
    monkeypatch.setattr(contractors, "crawl_partition", _CellByCell(cells=1))
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (_QuietFetcher(), lambda url: ""))
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)

    # ASSERTED THROUGH THE JOB LOG, NOT AN OUTER SINK. The runner installs its own sink
    # for the duration, and the sink is ONE global on purpose -- two readers of `say`
    # would be two accounts of one run -- so a capture wrapped around the runner sees
    # nothing. The log is also where the line has to be for the panel to show it, which
    # makes it the right subject anyway.
    directoryjob.run_directory_crawl_job_once(conn, job_ref)

    logged = " ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert f"job-{job_ref}" in logged, (
        "the crawl did not run under the job's own ref: " + logged)


def test_a_pause_stops_at_a_cell_boundary_and_says_where(conn, monkeypatch):
    """A PAUSE THAT SAYS NOTHING IS INDISTINGUISHABLE FROM A CRAWL THAT STOPPED, and
    the difference is whether resuming is worth anything. The line names how many cells
    closed and which ref to resume under."""
    job_ref, found, partition = _run_the_job(
        conn, monkeypatch, cells=4, control=JobControl.PAUSE.value)

    assert found["status"] == JobStatus.PAUSED.value
    assert partition.reported == 1, "it paused after the first cell, not later"
    logged = " ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "paused at a cell boundary" in logged
    assert f"job-{job_ref}" in logged, "the pause did not name the ref to resume under"
    assert found["progress_done"] == 1, (
        "the closed cell was not counted, so a resume cannot say what is left")


def test_a_cancel_stops_at_a_cell_boundary(conn, monkeypatch):
    _job_ref, found, partition = _run_the_job(
        conn, monkeypatch, cells=4, control=JobControl.CANCEL.value)

    assert found["status"] == JobStatus.CANCELLED.value
    assert partition.reported == 1


def test_a_failure_is_recorded_and_re_raised(conn, monkeypatch):
    """The worker's own handler parks the job, and it cannot do that for a runner that
    swallowed the exception. Recorded here AND re-raised, in that order."""
    def explode(*a, **k):
        raise RuntimeError("the site answered 503 sixty times")

    monkeypatch.setattr(contractors, "crawl", explode)
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (_QuietFetcher(), lambda url: ""))
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)

    with pytest.raises(RuntimeError, match="503"):
        directoryjob.run_directory_crawl_job_once(conn, job_ref)

    found = jobs.get_job(conn, job_ref)
    assert found["status"] == JobStatus.FAILED.value
    assert "503" in (found["error_summary"] or "")


def test_the_requests_it_spent_are_recorded_against_the_source(conn, monkeypatch):
    """A politeness figure nobody records is one nobody can audit -- `R-21` and `SR-8`
    are about the RATE, and the count is how a rate is checked afterwards.

    READ THE WAY `record_source_fetch` WRITES IT: a json_set into `$.sources.<key>` of
    the counters column, so two lanes updating different sources cannot clobber each
    other. `get_job` does not surface it as a field, so this reads the column it lands in
    rather than inventing one.
    """
    job_ref, _found, _ = _run_the_job(conn, monkeypatch, cells=2)

    counters = jobs.get_job(conn, job_ref)["counters"]
    slot = (counters.get("sources") or {}).get("muqawil_org") or {}
    assert slot.get("requests") == _QuietFetcher.requests_count, (
        "the request count never reached the job's per-source slot: "
        + json.dumps(counters))


# ---- the route, which is the button ------------------------------------------

def _panel(tmp_path):
    """The engine as the panel reaches it, with muqawil registered."""
    import shutil

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.catalog import register_site
    from scrapex.catalog_models import SiteCreate
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    register_site(conn, SiteCreate(site_key="muqawil_org",
                                   display_name="Saudi Contractors Authority",
                                   base_url="https://muqawil.org"))
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest)), db_path


def _kind_of(db_path, job_ref: str) -> str:
    from scrapex import db as dbmod

    conn = dbmod.connect(db_path)
    try:
        return conn.execute("SELECT job_kind FROM crawl_job WHERE job_ref = ?",
                            (job_ref,)).fetchone()[0]
    finally:
        conn.close()


def test_pressing_the_button_on_a_directory_queues_a_directory_crawl(tmp_path):
    """THE WHOLE DEFECT, END TO END, AND THE ONE ASSERTION THAT WOULD HAVE CAUGHT IT.

    `REQ-45` made this route answer 200 instead of 404 for `muqawil_org`, and every test
    written for it asserted `status == "queued"`. It was queued. It was queued as a
    `crawl`, so the worker handed a contractor directory to `capture_source` -- and no
    assertion anywhere looked at the KIND, which is the only field that says which
    collector will run.
    """
    client, db_path = _panel(tmp_path)

    posted = client.post("/api/jobs",
                         json={"source_keys": ["muqawil_org"], "run_mode": "update"})

    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "queued"
    assert _kind_of(db_path, posted.json()["job_ref"]) == directoryjob.JOB_KIND, (
        "the button queued a directory as a price crawl, which is the defect this "
        "change exists for")


def test_pressing_it_on_a_price_source_is_still_a_price_crawl(tmp_path):
    """THE HALF THAT MUST NOT MOVE. Twelve registered shops reach the same route, and a
    change that made every job a directory crawl would break all of them while making
    this file's other tests pass."""
    client, db_path = _panel(tmp_path)

    posted = client.post("/api/jobs",
                         json={"source_keys": ["MADAR"], "run_mode": "update"})

    assert posted.status_code == 200, posted.text
    assert _kind_of(db_path, posted.json()["job_ref"]) == "crawl"


def test_a_directory_and_a_price_source_in_one_request_are_refused(tmp_path):
    """ONE DENOMINATOR PER JOB, refused at the door rather than inside the run.

    `R-71` and `OP-92`: a request accepted here and refused by the worker is a job the
    owner watches start and die. The message names which keys are which, because
    "invalid request" is not something a person can act on.
    """
    client, _ = _panel(tmp_path)

    refused = client.post("/api/jobs",
                          json={"source_keys": ["muqawil_org", "MADAR"],
                                "run_mode": "update"})

    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert "muqawil_org" in detail and "MADAR" in detail, (
        "the refusal did not say which key was which, so nobody can act on it: "
        + detail)


def test_two_directories_in_one_request_are_refused_at_the_door(tmp_path):
    """The runner refuses this too, and that is deliberate rather than redundant: the
    message a person reads should come from the door they knocked on, not from a job
    that started and stopped."""
    client, _ = _panel(tmp_path)

    refused = client.post("/api/jobs",
                          json={"source_keys": ["muqawil_org", "muqawil_org"],
                                "run_mode": "update"})

    assert refused.status_code == 400, refused.text
    assert "one directory at a time" in refused.json()["detail"]


# ---- OP-128: the cross-job politeness gate reaches this kind too -------------

def test_every_specialised_runner_accepts_the_admission():
    """THE CHEAPEST OF THE FOUR, AND THE ONE A NEW KIND CANNOT FORGET.

    The contract was `(conn, job_ref)`, so `_start_job` handed the cross-job admission to
    `run_job_once` and to nothing else -- and a runner that could not ACCEPT the gate made
    the omission invisible: the dispatch had nowhere to put it, so there was nothing to
    notice. A signature check is what stops the third kind repeating it.

    What a runner DOES with the gate is its own question -- `run_enrichment_job_once`
    accepts and does not use it, and says why. Accepting is the contract.
    """
    import inspect

    for kind in sorted(jobs.SPECIALISED_RUNNERS):
        runner = jobs.runner_for(kind)
        parameters = inspect.signature(runner).parameters
        assert "admission" in parameters, (
            f"{kind!r}'s runner cannot accept the cross-job admission, so the dispatch "
            f"has nowhere to hand it and the omission is invisible: {list(parameters)}")


def test_the_dispatch_hands_the_admission_to_a_specialised_runner(conn, tmp_path,
                                                                 monkeypatch):
    """THE OMISSION ITSELF, asserted where it lived.

    `_start_job` chose a runner and called `runner(conn, job_ref)`. Everything about the
    admission was correct on either side of that line -- the worker built it, the price
    path used it -- and the line itself dropped it. Nothing looked at this call.
    """
    seen: dict = {}

    def spy(connection, job_ref, admission=None):
        seen["job_ref"] = job_ref
        seen["admission"] = admission
        return jobs.get_job(connection, job_ref)

    # THE REAL KIND, WITH THE RUNNER REPLACED. An invented `job_kind` is refused by the
    # CHECK `0017` widened -- which is that constraint working, and the reason this test
    # goes through `directory_crawl` instead of a fictional row.
    monkeypatch.setattr(jobs, "runner_for",
                        lambda kind: spy if kind == directoryjob.JOB_KIND else None)

    worker = jobs.JobRunner(str(tmp_path / "scrapex-engine.db"), lambda: None)
    admission = jobs._CrawlAdmission(2)
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)
    conn.commit()

    worker._db_path = tmp_path / "scrapex-engine.db"
    worker._start_job(job_ref, admission)
    for _ in range(200):
        if "admission" in seen:
            break
        time.sleep(0.02)

    assert seen.get("job_ref") == job_ref, (
        "the dispatch never reached the runner at all: " + str(seen))
    assert seen["admission"] is admission, (
        "the dispatch chose the runner and dropped the cross-job admission, so this kind "
        f"crawls outside the per-host reservation: {seen['admission']!r}")


def test_two_directory_crawls_on_one_host_do_not_run_together(tmp_path, monkeypatch):
    """THE PROPERTY, TIMED, and it is the one his warehouse could actually hit.

    `job_capacity` on his warehouse is **3**, not the shipped 1, so two `muqawil_org`
    jobs -- a scheduled one and a hand-started one, or two presses of the panel's button
    -- would have run concurrently with their own `HttpFetcher` at `DEFAULT_PACE_S` each
    and doubled the request rate on that site. `R-21`, `SR-8`.

    ASSERTED AS NON-OVERLAP RATHER THAN AS AN ORDER, because which of the two goes first
    is not a property: only that the second does not start before the first has finished.
    """
    import threading

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (_QuietFetcher(), lambda url: ""))

    spans: list[tuple[str, float]] = []
    lock = threading.Lock()

    class _Slow:
        """One cell, held long enough that an overlap could not be a timing artefact."""

        def __call__(self, *args, **kwargs):
            from scrapex.partitioncrawl import (
                WHOLE,
                Attempt,
                CellOutcome,
                CellSize,
                PartitionOutcome,
            )
            with lock:
                spans.append(("in", time.monotonic()))
            time.sleep(0.35)
            with lock:
                spans.append(("out", time.monotonic()))
            size = CellSize(cell=WHOLE, last_page=1, cards_per_page=1, tail_cards=1,
                            requests=1)
            kwargs["on_cell"](CellOutcome(size=size, attempts=(
                Attempt(ids=(), pages_read=1, witnessed=True, note="fake",
                        run_ref="fake-a1"),)))
            return PartitionOutcome(whole=size, cells=(), whole_at_end=None, parent=WHOLE)

    monkeypatch.setattr(contractors, "crawl_partition", _Slow())
    admission = jobs._CrawlAdmission(2)          # budget of two, ONE host

    refs = []
    for _ in range(2):
        one = registry.engine.connect()
        try:
            refs.append(jobs.create_job(one, ["muqawil_org"], RunMode.UPDATE,
                                        job_kind=directoryjob.JOB_KIND))
            one.commit()
        finally:
            one.close()

    def run(job_ref: str) -> None:
        own = registry.engine.connect()
        try:
            directoryjob.run_directory_crawl_job_once(own, job_ref, admission=admission)
        finally:
            own.close()

    threads = [threading.Thread(target=run, args=(ref,)) for ref in refs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(spans) == 4, f"both crawls did not run: {spans}"
    # in, out, in, out -- never in, in, out, out
    assert [kind for kind, _ in spans] == ["in", "out", "in", "out"], (
        "two directory crawls of ONE host overlapped, so the request rate on that site "
        f"doubled: {spans}")


def test_the_host_rule_has_one_definition():
    """THE CRACK `_host_of`'S OWN DOCSTRING NAMES, guarded.

    *"ONE definition, used to bucket lanes AND to reserve a host across jobs -- so a
    source cannot be filed under one host name for grouping and a different one for
    reservation, which is the crack two jobs would slip through to crawl a site
    together."*

    The registry source the directory runner reserves is one the MANIFEST cannot resolve,
    so it needs the rule without the lookup. `host_of_url` is that rule and `_host_of`
    delegates to it; a second `urlsplit(...).netloc.lower()` in the runner would have been
    the copy. This asserts they agree, including on the fallback.
    """
    assert jobs.host_of_url("https://www.Muqawil.org/", "fallback") == "muqawil.org"
    assert jobs.host_of_url("https://muqawil.org", "fallback") == "muqawil.org"
    assert jobs.host_of_url("", "fallback") == "fallback", (
        "an unresolvable base_url must fall back to something unique to the source, or "
        "two unknowns share a reservation")

    class _One:
        base_url = "https://WWW.Muqawil.org/en"

    class _Manifest:
        def get(self, key):
            return _One()

    assert (jobs._host_of(_Manifest(), "muqawil_org", "fallback")
            == jobs.host_of_url(_One.base_url, "fallback")), (
        "the manifest path and the url path disagree about a host, which is exactly the "
        "crack the docstring names")

    # AND THE RUNNER MUST NOT HAVE ITS OWN COPY. Read as source, because a second
    # derivation that happened to agree today would pass every assertion above.
    runner_source = pathlib.Path(directoryjob.__file__).read_text(encoding="utf-8")
    assert "netloc" not in runner_source, (
        "scrapex/directoryjob.py derives a host itself instead of calling "
        "`jobs.host_of_url`, which is the second definition `_host_of` warns about")


def test_the_request_count_is_visible_before_the_job_ends(conn, monkeypatch):
    """`OP-130`: TWO NUMBERS ON ONE CARD THAT CONTRADICTED EACH OTHER.

    `record_source_fetch` was called once, in `finally`, so the panel showed
    `requests: 0` beside `cells 2/56` for as long as the crawl ran -- and the crawl he
    started ran for hours. A progress figure that says nothing while work happens is the
    same defect as a silent resume, one card over.

    ASSERTED AT A CELL BOUNDARY, not at the end, because at the end the old code was
    already right. The count is read from inside `between_cells`, which is the only point
    where every figure on that card agrees with the others.
    """
    seen: list[int | None] = []
    partition = _CellByCell(cells=3)

    def watch() -> bool:
        counters = jobs.get_job(conn, job_ref)["counters"]
        slot = (counters.get("sources") or {}).get("muqawil_org") or {}
        seen.append(slot.get("requests"))
        return False

    monkeypatch.setattr(contractors, "crawl_partition", partition)
    monkeypatch.setattr(contractors, "coverage", lambda *a, **k: "coverage")
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (_QuietFetcher(), lambda url: ""))
    job_ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=directoryjob.JOB_KIND)

    real = contractors.crawl

    def crawl_and_watch(*args, **kwargs):
        # THE RUNNER'S OWN `between_cells` RUNS FIRST, then this reads what it wrote --
        # so the assertion is about what a poll from the panel would have seen mid-run.
        inner = kwargs.pop("between_cells", None)

        def both() -> bool:
            stop = bool(inner()) if inner is not None else False
            watch()
            return stop

        return real(*args, between_cells=both, **kwargs)

    monkeypatch.setattr(contractors, "crawl", crawl_and_watch)
    directoryjob.run_directory_crawl_job_once(conn, job_ref)

    assert seen, "no cell boundary was reached, so this proves nothing"
    assert seen[0] == _QuietFetcher.requests_count, (
        "the panel would have shown `requests: 0` while cells were closing -- two figures "
        f"on one card contradicting each other: {seen}")

    counters = jobs.get_job(conn, job_ref)["counters"]
    slot = (counters.get("sources") or {}).get("muqawil_org") or {}
    assert slot.get("state") == "done", (
        f"the final state is not `done`, so the card never settles: {slot}")


def test_the_fetcher_exists_before_the_closure_that_reads_it():
    """STRUCTURAL, NOT INCIDENTAL. `cell_closed` reports the fetcher's request count, and
    a closure resolves its names at CALL time -- so building the fetcher below the closure
    worked, and worked by ordering. Moving `make_fetch` under the crawl call would then be
    a `NameError` on the FIRST CELL, hours into a run that had already fetched real pages.

    Read as source, because the ordering is the property and no behaviour distinguishes it
    until the day someone reorders the function."""
    import pathlib as _pathlib

    lines = _pathlib.Path(directoryjob.__file__).read_text(encoding="utf-8").split(chr(10))
    built = next(n for n, line in enumerate(lines, 1) if "make_fetch(" in line)
    closure = next(n for n, line in enumerate(lines, 1) if "def cell_closed(" in line)

    assert built < closure, (
        f"`make_fetch` is at line {built} and `cell_closed` at {closure}: the closure "
        "reads a name assigned after it, which holds only until someone moves either one")
