"""The profile sweep is a job the panel can start, and its default is what is missing.

WHAT WAS ACTUALLY WRONG, MEASURED ON HIS WAREHOUSE 2026-09-06. `contractors.details` --
the step that fetches the profile page of every contractor a listing named -- was
reachable from `scrapex contractors --details` and from nowhere else: no route, no job
kind, no control. `R-81` says the panel is his only interface, so the profile half of
muqawil did not exist for the one person the tool is for.

    contractors sighted                      17,848
    profiles stored                          17,379
    sighted ids with NO profile                 469   <- the frontier this door builds
    the registered scope's whole frontier    ~35,700 pages, about 87 hours
    the missing set                              938 pages, about 2.4 hours

THE DEFAULT IS THE MISSING SET AND THAT IS HIS RULING. A control whose only question
takes 87 hours is one he cannot safely press.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import (  # noqa: E402
    contractors, datasetjob, directories, directoryjob, jobs, profilejob, sightings,
)
from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.vocab import JobControl, JobStatus  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = "muqawil_org"


def _register(conn: sqlite3.Connection) -> int:
    """The `source_site` row, because a sweep with no registered scope is refused.

    `snapshotcrawl.SiteNotRegistered` says why in terms: *"how deep its crawl may go has
    never been decided ... a crawl that picked the default would be answering for the
    owner."* The column defaults to `listing_only`, and that is deliberately left alone
    here -- NAMED IDS ARE NOT SUBJECT TO THE SCOPE (`contractors.details`), so a fixture
    that widened the scope would hide a regression in exactly that rule.
    """
    row = conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                       (SITE,)).fetchone()
    if row:
        return int(row[0])
    return int(conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, ?, ?, 'directory') RETURNING source_id",
        (SITE, "muqawil.org", "https://muqawil.org")).fetchone()[0])


@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    _register(conn)
    conn.commit()
    try:
        yield conn, path
    finally:
        conn.close()


def _sight(conn: sqlite3.Connection, dataset_key: str, ids) -> None:
    """Put contractor ids in the sighting ledger, which is where the frontier comes from."""
    for one in ids:
        conn.execute(
            "INSERT INTO dataset_sighting (dataset_key, external_id, seen_count) "
            "VALUES (?, ?, 1)", (dataset_key, str(one)))
    conn.commit()


def _dataset(conn: sqlite3.Connection, dataset_key: str, name: str) -> tuple[int, int]:
    """`(dataset_definition_id, schema_version_id)` for one dataset, created once.

    THE FULL FOREIGN-KEY CHAIN, and there is no shortcut: `generic_record` requires a
    `schema_version_id` and a `source_snapshot_id`, both NOT NULL into real tables, so a
    fixture that inserted a bare row would fail rather than lie -- which is the schema
    doing its job. `discovery_method` is NOT NULL with no default for the same reason.
    """
    source_id = _register(conn)
    row = conn.execute(
        "SELECT dataset_definition_id FROM dataset_definition WHERE dataset_key = ?",
        (dataset_key,)).fetchone()
    if row is None:
        row = conn.execute(
            "INSERT INTO dataset_definition "
            "  (source_id, dataset_key, original_name, dataset_kind, discovery_method) "
            "VALUES (?, ?, ?, 'table', 'repeating_dom') RETURNING dataset_definition_id",
            (source_id, dataset_key, name)).fetchone()
    definition = int(row[0])
    version = conn.execute(
        "SELECT schema_version_id FROM dataset_schema_version "
        " WHERE dataset_definition_id = ?", (definition,)).fetchone()
    if version is None:
        version = conn.execute(
            "INSERT INTO dataset_schema_version "
            "  (dataset_definition_id, version_number, schema_hash) "
            "VALUES (?, 1, ?) RETURNING schema_version_id",
            (definition, f"hash-{dataset_key}")).fetchone()
    conn.commit()
    return definition, int(version[0])


def _snapshot(conn: sqlite3.Connection, url: str) -> int:
    """One stored page, through the production writer.

    NOT RAW SQL, and the reason is recorded: seventeen tests in
    `test_two_warehouses_become_one.py` once passed both before and after a real defect
    because none of them stored a page the way the product does.
    """
    from scrapex.extract import service
    from scrapex.extract.models import SnapshotCreate
    stored = service.save_snapshot(conn, SnapshotCreate(
        source_url=url, html_content="<html><body>fixture</body></html>"))
    conn.commit()
    return int(stored["page_snapshot_id"])


def _profile_row(conn: sqlite3.Connection, contractor_id: str) -> None:
    """One stored profile, addressed the way the product addresses it.

    THROUGH `dataset_definition`, not by a literal id, because the whole point of the
    query under test is that it resolves the profile dataset BY KEY.
    """
    directory = directories.get(SITE)
    definition, version = _dataset(conn, directory.profiles.dataset_key,
                                   "Contractor profiles")
    snapshot = _snapshot(conn, f"https://muqawil.org/en/contractors/{contractor_id}")
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        "                            schema_version_id, data_json, source_snapshot_id, "
        "                            source_locator, content_hash, status) "
        "VALUES (?, ?, ?, ?, ?, 'div.info-box::row(1)', ?, 'active')",
        (definition, f"key-{contractor_id}", version,
         json.dumps({"contractor_id": contractor_id}), snapshot,
         f"hash-{contractor_id}"))
    conn.commit()


def test_the_frontier_is_what_has_no_profile(warehouse):
    """THE ONE NUMBER THE BUTTON ACTS ON."""
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["1001", "1002", "1003"])
    _profile_row(conn, "1002")

    missing = profilejob.missing_profile_ids(conn, directory)

    assert missing == ("1001", "1003"), missing


def test_it_joins_on_the_contractor_id_and_not_on_the_record_key(warehouse):
    """THE MISTAKE THIS GUARD EXISTS FOR, AND I MADE IT.

    My first count of the gap joined `generic_record.record_key` across the two datasets
    and reported 410. Those keys are digests of the PARSED ROW and the two datasets hash
    different things -- `source_locator` is `div.section-card::row(N)` for a listing card
    and `div.info-box::row(1)` for a profile -- so the join was meaningless and the
    number was a coincidence of the right order of magnitude. The real figure, on
    `contractor_id`, is 469.

    So this stores a profile whose `record_key` matches NOTHING and whose `contractor_id`
    matches a sighted contractor. A `record_key` join reports it missing; the right join
    does not.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["2001"])
    _profile_row(conn, "2001")
    stored = conn.execute(
        "SELECT record_key FROM generic_record WHERE data_json LIKE '%2001%'"
    ).fetchone()[0]
    assert stored == "key-2001" != "2001", (
        "the fixture's record_key happens to equal the contractor id, so this test "
        "cannot tell the two joins apart")

    assert profilejob.missing_profile_ids(conn, directory) == (), (
        "a stored profile was reported missing, which is what a record_key join does")


def test_a_warehouse_with_nothing_missing_refuses_rather_than_sweeping(warehouse):
    """AN EMPTY `ids` FALLS THROUGH TO THE SCOPE'S FRONTIER, which is the 87-hour
    question -- so "nothing missing" has to be a refusal and not an empty tuple passed
    on. `--ids` records four rounds of exactly this hole in `contractors.run`."""
    conn, path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["3001"])
    _profile_row(conn, "3001")
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()

    with pytest.raises(profilejob.NothingToFetch, match="nothing missing"):
        profilejob.run_profile_crawl_job_once(conn, job_ref)


def test_the_runner_refuses_a_job_of_another_kind(warehouse):
    conn, _path = warehouse
    job_ref = jobs.create_job(conn, [SITE], job_kind="directory_crawl")
    conn.commit()

    with pytest.raises(ValueError, match="not a 'profile_crawl'"):
        profilejob.run_profile_crawl_job_once(conn, job_ref)


def test_the_runner_refuses_a_key_that_is_no_directory(warehouse):
    conn, _path = warehouse
    job_ref = jobs.create_job(conn, ["ELSEWEDYSHOP"], job_kind=profilejob.JOB_KIND)
    conn.commit()

    with pytest.raises(profilejob.NotADirectory):
        profilejob.run_profile_crawl_job_once(conn, job_ref)


def test_the_kind_is_registered_and_the_schema_allows_it(warehouse):
    """A runner the dispatch cannot find is a job that queues and never starts, and a
    kind the CHECK refuses is a row that cannot be written at all. Both have been real:
    `0018` exists because the second happened."""
    conn, _path = warehouse

    assert jobs.runner_for(profilejob.JOB_KIND) is profilejob.run_profile_crawl_job_once
    assert profilejob.JOB_KIND in jobs.JOB_KINDS

    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()
    assert jobs.get_job(conn, job_ref)["job_kind"] == profilejob.JOB_KIND, (
        "the row was written with another kind, so the CHECK accepted it and the "
        "dispatch will run the wrong runner")


def test_the_sweep_can_be_stopped_between_pages(warehouse):
    """A PAGE IS THE BOUNDARY, and `details` had none: a 938-page sweep with no hook is
    two and a half hours the owner cannot interrupt."""
    conn, _path = warehouse
    directory = directories.get(SITE)
    asked: list[tuple[int, int]] = []

    def stop_at_two(index: int, total: int) -> bool:
        asked.append((index, total))
        return index >= 2

    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return "<html><body>nothing</body></html>"

    contractors.details(conn, directory, fetch, None, "run-stop",
                        ids=("4001", "4002", "4003"), between_pages=stop_at_two)

    assert len(fetched) == 2, (
        f"the sweep did not stop at the second page: {len(fetched)} fetched")
    assert asked[0] == (0, 6), (
        f"the first call must carry the total so the card can draw a bar: {asked[0]}")


def test_the_frontier_drops_an_id_the_site_will_not_serve(warehouse):
    """ISSUE 794. 37 of his 469 answered `/contractors/<id>/143` with the contractors
    listing at HTTP 200, so they can never become rows -- and the row gap stopped at 37
    with nothing able to move it. The card called them work waiting for ever, and the
    fetch control would have re-bought their 74 pages on every press.

    SUBTRACTED IN `missing_profile_ids` AND NOWHERE ELSE, because that is the DEFAULT
    frontier both `still_to_fetch` and the route start from -- one filter rather than
    three places to forget it.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["7001", "7002", "7003"])

    before = profilejob.missing_profile_ids(conn, directory)
    assert before == ("7001", "7002", "7003"), before

    marked = sightings.mark_profile_unresolved(
        conn, directory.dataset_key, external_ids=("7002",), run_ref="job-run")
    assert marked == ("7002",), marked

    after = profilejob.missing_profile_ids(conn, directory)
    assert after == ("7001", "7003"), (
        f"an id the site will not serve is still counted as a gap: {after}")


def test_a_named_id_still_reaches_a_marked_contractor(warehouse, monkeypatch):
    """OP-64 REMEDIATION IS RE-FETCHING EXACTLY THIS CONTRACTOR.

    A marked id is one whose stored pages are another contractor s document, so naming
    it explicitly must still fetch: the mark removes it from the DEFAULT frontier, which
    is the number on his card, and it is not a ban. Driven through the runner rather than
    asserted about the code, because the filter and the named path are two branches and
    only the runner chooses between them.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["7101"])
    sightings.mark_profile_unresolved(
        conn, directory.dataset_key, external_ids=("7101",), run_ref="job-earlier")
    assert profilejob.missing_profile_ids(conn, directory) == (), (
        "the fixture did not actually remove it from the default frontier")

    job_ref = jobs.create_job(conn, [SITE], checkpoint={"ids": ["7101"]},
                              job_kind=profilejob.JOB_KIND)
    conn.commit()
    fetched: list[str] = []
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, lambda url: fetched.append(url) or ""))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    assert fetched, (
        "naming a marked contractor fetched nothing, so the one remediation OP-64 "
        "defines is unreachable")
    assert all("7101" in url for url in fetched), fetched


def test_the_hook_is_refused_above_one_worker(warehouse):
    """ACCEPTING IT AND NOT HONOURING IT WOULD BE A PAUSE CONTROL THAT DOES NOTHING on
    the path he would press it on. The pool calls back from worker threads, where this
    connection cannot be used, and `ThreadPoolExecutor.__exit__` runs every queued task
    after a stop is decided."""
    conn, _path = warehouse
    directory = directories.get(SITE)

    with pytest.raises(ValueError, match="sequential hook"):
        contractors.details(conn, directory, lambda url: "", None, "run-pool",
                            ids=("5001",), workers=4, connect=lambda: conn,
                            between_pages=lambda index, total: False)


def test_a_stopped_sweep_closes_partial_and_not_success(warehouse):
    """A SWEEP THE OWNER PAUSED READ PART OF ITS FRONTIER, and a later reader taking
    that as "the site was fully read" is exactly what `RunStatus.PARTIAL` exists to
    prevent. The condition read only the ceiling before this."""
    conn, _path = warehouse
    directory = directories.get(SITE)

    contractors.details(conn, directory, lambda url: "<html></html>", None, "run-part",
                        ids=("6001", "6002", "6003"),
                        between_pages=lambda index, total: index >= 1)

    status = conn.execute(
        "SELECT status FROM crawl_run ORDER BY run_id DESC LIMIT 1").fetchone()[0]
    assert status == "partial", (
        f"a sweep stopped after one page closed as {status!r}")


# ---- the route the control presses ------------------------------------------


@pytest.fixture()
def served(tmp_path):
    """An engine holding ONE APPROVED-SHAPED DATASET, and two contractors sighted.

    A DATASET HAS TO EXIST FOR THIS TO TEST ANYTHING. `_registered_directories` lists a
    directory that has never been crawled, and such a card has nothing waiting by
    construction -- no crawl has finished, so nothing can be uninterpreted. The badge
    belongs to the DATASET row, so a warehouse with no dataset would let the guard for
    it pass against a row that never carries it.
    """
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    directory = directories.get(SITE)
    _dataset(conn, directory.dataset_key, "Contractors")
    _sight(conn, directory.dataset_key, ["9001", "9002"])
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(path, manifest_path=manifest)), path


def test_the_route_queues_a_profile_sweep_for_a_directory(served):
    client, path = served

    answer = client.post("/api/jobs", json={
        "source_keys": [SITE], "run_mode": "update", "job_kind": "profile_crawl"})

    assert answer.status_code == 200, answer.text
    conn = sqlite3.connect(str(path))
    try:
        kind = conn.execute(
            "SELECT job_kind FROM crawl_job WHERE job_ref = ?",
            (answer.json()["job_ref"],)).fetchone()[0]
    finally:
        conn.close()
    assert kind == "profile_crawl"


def test_the_fetch_gap_closes_when_the_pages_are_stored(warehouse):
    """THE DEFECT HIS SCREENSHOT SHOWED. Storing a profile page writes no row, so a
    frontier counting ROWS does not move when the sweep succeeds -- and the control
    re-derives the same contractors on every press. Measured on his engine: two sweeps
    fetched 938 pages EACH, 1,876 requests for what 938 would have bought.

    `still_to_fetch` IS THE SECOND QUESTION. `missing_profile_ids` stays the row gap,
    because that is the right frontier for interpreting and the honest coverage figure.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["7001", "7002"])
    rowless = profilejob.missing_profile_ids(conn, directory)
    assert set(rowless) == {"7001", "7002"}
    assert profilejob.still_to_fetch(conn, directory, rowless) == rowless, (
        "nothing is stored yet and the fetch gap is already empty")

    # Every locale of 7001's profile, stored the way the sweep stores them.
    from scrapex.sites.muqawil import MuqawilPageSource
    for url in MuqawilPageSource(last_page=1).profile_urls(directory.base_url, "7001"):
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
            "VALUES (?, 'text/html', X'00', ?, 'job-whatever-a1')",
            (url, f"hash-{url}"))
    conn.commit()

    assert profilejob.missing_profile_ids(conn, directory) == rowless, (
        "the ROW gap moved when a page was stored, which it must not: a stored page "
        "writes no row, and this number is the coverage figure")
    assert profilejob.still_to_fetch(conn, directory, rowless) == ("7002",), (
        "the FETCH gap still names a contractor whose pages are on disk, so the control "
        "would buy them again")


def test_one_locale_stored_is_not_fetched(warehouse):
    """ALL LOCALES OR NONE. `approve` pairs the halves and counts a lonely one as lonely,
    so a contractor with an English page and no Arabic one still needs a request --
    which is what a resume is for."""
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["8001"])
    from scrapex.sites.muqawil import MuqawilPageSource
    first = next(iter(MuqawilPageSource(last_page=1)
                      .profile_urls(directory.base_url, "8001")))
    conn.execute(
        "INSERT INTO generic_page_snapshot "
        "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
        "VALUES (?, 'text/html', X'00', 'h', 'job-half-a1')", (first,))
    conn.commit()

    assert profilejob.still_to_fetch(conn, directory, ("8001",)) == ("8001",), (
        "a contractor with one locale stored was treated as fetched, so the missing "
        "half is never asked for")


def test_the_runner_refuses_when_every_rowless_contractor_has_its_pages(warehouse):
    """AND IT SAYS WHICH REFUSAL IT IS. "Nothing to fetch" because nobody is missing and
    "nothing to fetch" because the pages are already here are different answers, and the
    second one means the next press is an interpretation. Saying only the first would
    send him looking for the wrong button -- which is exactly what the card did."""
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["9101"])
    from scrapex.sites.muqawil import MuqawilPageSource
    for url in MuqawilPageSource(last_page=1).profile_urls(directory.base_url, "9101"):
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
            "VALUES (?, 'text/html', X'00', ?, 'job-stored-a1')", (url, f"h-{url}"))
    conn.commit()
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()

    with pytest.raises(profilejob.NothingToFetch, match="nothing left to FETCH"):
        profilejob.run_profile_crawl_job_once(conn, job_ref)


def test_a_job_stopped_while_waiting_never_fetches(warehouse, monkeypatch):
    """THE WORST OF TODAY'S THREE, AND IT EXECUTED WORK HE HAD STOPPED.

    MEASURED 2026-09-07. Two sweeps were queued 18 seconds apart. The second entered its
    runner at 10:33:44, passed the terminal check, and BLOCKED on the per-host politeness
    lane for 33 minutes. He cancelled it at 11:02:54 -- thirty minutes after the only
    check that would have stopped it. At 11:06:23 the lane freed, it woke up, and it
    fetched 938 profile pages: 938 requests at muqawil.org and 38 minutes, for pages
    another job had already stored.

    `between_pages` COULD NOT SAVE IT. That hook reads `control`, and `_finish` clears
    `control` to `none` when it settles a job -- so by the time the sweep was running
    there was no pending instruction left to find, and its log never mentioned the cancel
    at all. **The hole is before the first page, not between pages.**

    THE LANE IS CANCELLED HERE BY CANCELLING THE JOB WHILE IT WAITS, which is what the
    admission object lets a test do: `lane` is entered, and the cancel lands inside it.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["9201"])
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()
    fetched: list[str] = []
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, lambda url: fetched.append(url) or ""))

    class CancelWhileWaiting:
        """An admission whose lane cancels the job before it lets go -- which is exactly
        what a 33-minute wait allows to happen."""

        def lane(self, host):
            from contextlib import contextmanager

            @contextmanager
            def held():
                jobs._finish(conn, jobs.get_job(conn, job_ref)["job_id"],
                             JobStatus.CANCELLED, None)
                conn.commit()
                yield
            return held()

    settled = profilejob.run_profile_crawl_job_once(
        conn, job_ref, admission=CancelWhileWaiting())

    assert fetched == [], (
        f"a cancelled job asked the site for {len(fetched)} page(s) -- it executed work "
        "that had been stopped")
    assert settled["status"] == JobStatus.CANCELLED.value, settled["status"]
    logged = " | ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "stopped while waiting" in logged, (
        f"it stopped in silence, so nobody can tell this from a job that never ran: "
        f"{logged!r}")


def test_a_settled_row_stops_a_running_sweep_even_with_no_control_left(warehouse,
                                                                       monkeypatch):
    """ISSUE 791, AND IT IS THE ONE THE MORNING'S FIX DOES NOT COVER.

    He pressed Cancel at 13:55:57 on a sweep that was AWAKE and fetching. It ran to
    `completed 938/938` at 14:23:50 and the word "cancel" appears nowhere in its log.
    At 13:58 the row read `finished_at = 13:55:57` AND `status = running` AND
    `control = none` -- finished and running at once, with no instruction left to find.

    TWO THINGS MADE THAT POSSIBLE. The beat wrote `status = running` FIRST and
    unconditionally, over the `cancelling` `set_control` parks there; and `_finish`
    clears `control`, so a stop already recorded leaves nothing for a guard that reads
    only `control`.

    SO THE ROW OUTRANKS THE INSTRUCTION. This settles the job from underneath, exactly as
    the live incident did, and leaves `control` clear -- the state in which the old guard
    saw nothing at all.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, [f"95{n:02d}" for n in range(8)])
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()
    fetched: list[str] = []
    monkeypatch.setattr(profilejob, "BEAT_EVERY_PAGES", 1)

    def settle_after_two(url):
        fetched.append(url)
        if len(fetched) == 2:
            # WHAT THE INCIDENT DID: the job is finished and its control cleared, while
            # the sweep goes on holding the thread.
            jobs._finish(conn, jobs.get_job(conn, job_ref)["job_id"],
                         JobStatus.CANCELLED, None)
            conn.commit()
        return "<html></html>"

    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, settle_after_two))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    assert len(fetched) <= 3, (
        f"the sweep asked for {len(fetched)} page(s) after its row was settled -- it "
        "fetched on past a stop, which is what cost 938 requests on 2026-09-07")
    logged = " | ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "already settled" in logged, (
        f"it stopped in silence, so this is indistinguishable from a sweep that simply "
        f"ended: {logged!r}")
    assert jobs.get_job(conn, job_ref)["status"] == JobStatus.CANCELLED.value


def test_the_beat_does_not_write_running_over_a_pending_stop(warehouse, monkeypatch):
    """`set_control` PARKS A WORKER-HELD JOB IN `cancelling` to mean "the worker will
    settle this at its next safe boundary", and its own docstring calls the
    compare-and-swap load-bearing so *"a job that reaches a terminal state concurrently
    can never be resurrected by a late control click"*. The beat resurrected it from the
    other side, by writing `running` before it read anything."""
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, [f"96{n:02d}" for n in range(6)])
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()
    monkeypatch.setattr(profilejob, "BEAT_EVERY_PAGES", 1)
    seen: list[str] = []

    def cancel_after_one(url):
        seen.append(url)
        if len(seen) == 1:
            jobs.set_control(conn, job_ref, JobControl.CANCEL)
            conn.commit()
        return "<html></html>"

    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, cancel_after_one))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    settled = jobs.get_job(conn, job_ref)
    assert settled["status"] == JobStatus.CANCELLED.value, (
        f"a pending cancel did not settle the job: {settled['status']}")
    logged = " | ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "cancelled between pages" in logged, (
        f"the cancel branch never fired, or never committed its line: {logged!r}")
    assert len(seen) <= 2, f"it fetched {len(seen)} page(s) past the cancel"


def test_a_paused_sweep_still_counts_the_pages_it_fetched(warehouse, monkeypatch):
    """A PAUSE THAT LOSES THE COUNT IS A PAUSE HE CANNOT READ, and this one was a
    REGRESSION OF THIS BRANCH rather than an old defect.

    Withholding `status = running` from a pending stop was right; withholding the whole
    write with it was not, because the page count travelled inside that call and the
    pause branch below does not write it. The listing crawl has the identical shape and
    its guard -- `test_a_pause_stops_at_a_cell_boundary_and_says_where` -- failed the
    moment the change landed. Nothing was watching the profile sweep, so this is that
    guard's twin.

    THE PAGE WAS FETCHED. That is a measurement, and a stop cannot make it untrue.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, [f"97{n:02d}" for n in range(6)])
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()
    monkeypatch.setattr(profilejob, "BEAT_EVERY_PAGES", 1)
    seen: list[str] = []

    def pause_after_one(url):
        seen.append(url)
        if len(seen) == 1:
            jobs.set_control(conn, job_ref, JobControl.PAUSE)
            conn.commit()
        return "<html></html>"

    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, pause_after_one))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    settled = jobs.get_job(conn, job_ref)
    assert settled["status"] == JobStatus.PAUSED.value, (
        f"a pending pause did not settle the job: {settled['status']}")
    assert seen, "nothing was fetched, so this proves nothing about the count"
    assert settled["progress_done"] == len(seen), (
        f"{len(seen)} page(s) were fetched and the row says "
        f"{settled['progress_done']} -- a resume cannot say what is left")


def test_a_pause_before_the_first_page_still_corrects_the_total(warehouse, monkeypatch):
    """`page_closed` PROMISES ITS FIRST CALL ALWAYS WRITES, so `progress_total` reaches
    the card before the work rather than after it -- the runner's entry can only write
    an ESTIMATE (`wanted * 2`), because the resume and the ceiling are applied inside
    `details`.

    A stop pending at that first call broke exactly that promise: the corrected total
    never landed and the card kept an estimate the run never had. Six sighted
    contractors are twelve pages by the estimate and three by the ceiling.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, [f"98{n:02d}" for n in range(6)])
    job_ref = jobs.create_job(conn, [SITE], checkpoint={"ceiling": 3},
                              job_kind=profilejob.JOB_KIND)
    # WORKER-HELD, WHICH IS WHAT MAKES THE PAUSE PENDING RATHER THAN DONE. `set_control`
    # settles a job the worker is not holding on the spot; it parks a held one in
    # `pausing` with `control = pause`, and the runner's own entry write leaves that
    # control alone. That is the live shape: he pressed Pause in the seconds between
    # dispatch and the first page.
    jobs._update(conn, jobs.get_job(conn, job_ref)["job_id"],
                 status=JobStatus.PREPARING.value)
    conn.commit()
    assert jobs.set_control(conn, job_ref, JobControl.PAUSE), "the pause was not parked"
    monkeypatch.setattr(profilejob, "BEAT_EVERY_PAGES", 1)
    seen: list[str] = []
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, lambda url: seen.append(url) or "<html/>"))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    settled = jobs.get_job(conn, job_ref)
    assert seen == [], f"it fetched {len(seen)} page(s) past a pause that was pending"
    assert settled["status"] == JobStatus.PAUSED.value, settled["status"]
    assert settled["progress_total"] == 3, (
        f"the total the run actually had is 3 and the row says "
        f"{settled['progress_total']} -- the card draws a bar against a frontier that "
        "never existed")


def test_the_route_still_refuses_a_kind_the_registry_owns(served):
    """The crawl kinds stay INFERRED. A caller free to name `directory_crawl` would be a
    second place deciding which collector runs, which is the drift the registry exists to
    remove -- and widening the nameable set for profiles must not widen it for those."""
    client, _path = served

    refused = client.post("/api/jobs", json={
        "source_keys": [SITE], "job_kind": "directory_crawl"})

    assert refused.status_code == 400, refused.text
    assert "source registry" in refused.json()["detail"]


def test_the_route_refuses_two_frontiers_at_once(served):
    """Named ids REPLACE the frontier rather than filtering it, so asking for both an id
    list and the whole frontier cannot mean anything. Refusing beats picking one."""
    client, _path = served

    refused = client.post("/api/jobs", json={
        "source_keys": [SITE], "job_kind": "profile_crawl",
        "ids": ["7001"], "whole_frontier": True})

    assert refused.status_code == 400, refused.text
    assert "different frontiers" in refused.json()["detail"]


def test_the_frontier_choice_reaches_the_job(served):
    """The runner reads these out of the checkpoint. A route that accepted them and
    dropped them would start the WRONG sweep -- the 87-hour one -- and say nothing."""
    client, path = served

    queued = client.post("/api/jobs", json={
        "source_keys": [SITE], "job_kind": "profile_crawl",
        "ids": ["8001", "8002"], "ceiling": 4})

    assert queued.status_code == 200, queued.text
    conn = sqlite3.connect(str(path))
    try:
        raw = conn.execute("SELECT checkpoint_json FROM crawl_job WHERE job_ref = ?",
                           (queued.json()["job_ref"],)).fetchone()[0]
    finally:
        conn.close()
    held = json.loads(raw)
    assert held["ids"] == ["8001", "8002"] and held["ceiling"] == 4, held


def test_the_default_asks_for_nothing_and_that_means_the_missing_set(served, tmp_path):
    """HIS RULING, ASSERTED: the panel sends no frontier, and the absence must mean the
    missing set rather than the whole one. A checkpoint that arrived carrying
    `whole_frontier` by default would be the 87-hour button."""
    client, path = served

    queued = client.post("/api/jobs", json={
        "source_keys": [SITE], "job_kind": "profile_crawl"})

    assert queued.status_code == 200, queued.text
    conn = sqlite3.connect(str(path))
    try:
        raw = conn.execute("SELECT checkpoint_json FROM crawl_job WHERE job_ref = ?",
                           (queued.json()["job_ref"],)).fetchone()[0]
    finally:
        conn.close()
    assert raw in (None, "", "null"), (
        f"the default carried a frontier choice: {raw!r}")


def test_the_route_sends_the_fetch_gap_and_not_the_row_gap_twice(served):
    """A MUTATION FOUND THIS GUARD MISSING. The DOM guard for the same defect drives a
    `sources=` stub, so replacing the route's `still_to_fetch` call with `len(rowless)`
    changed nothing any test could see -- the panel's half was proven and the engine's
    was not.

    HIS SCREENSHOT IS THE CASE. 469 rowless, 938 pages fetched, and the card went on
    offering a request that would buy them again -- because both numbers came from the
    row gap.
    """
    client, path = served
    directory = directories.get(SITE)
    conn = dbmod.connect(path)
    try:
        from scrapex.sites.muqawil import MuqawilPageSource
        for url in MuqawilPageSource(last_page=1).profile_urls(
                directory.base_url, "9001"):
            conn.execute(
                "INSERT INTO generic_page_snapshot "
                "  (source_url, content_type, html_content, content_hash, "
                "   crawl_run_ref) "
                "VALUES (?, 'text/html', X'00', ?, 'job-fetched-a1')",
                (url, f"h-{url}"))
        conn.commit()
    finally:
        conn.close()

    rows = client.get("/api/sources").json()["sources"]
    waiting = next(row["work_waiting"] for row in rows
                   if row.get("site_key") == SITE and row.get("work_waiting"))

    assert waiting["profiles"]["rowless"] == 2, (
        "the ROW gap moved because a page was stored, which it must not: that number is "
        f"the coverage figure: {waiting['profiles']}")
    assert waiting["profiles"]["fetch"] == 1, (
        "the FETCH gap still counts a contractor whose pages are on disk, so the card "
        f"offers a request that would buy them again: {waiting['profiles']}")


def test_a_finished_profile_sweep_sets_the_interpret_badge(served):
    """ISSUE 792, WHICH IS 782'S FILTER IN THE OTHER PLACE AND THE ONE I MISSED.

    The badge asked "has a LISTING crawl finished since the last interpretation?", so a
    profile sweep finishing with 938 uninterpreted pages set nothing. Measured on his
    warehouse: newest listing crawl 2026-09-06T05:01:44Z, newest interpretation
    2026-09-06T14:07:16Z, newest profile sweep 2026-09-07T14:23:50Z -- and the route
    answered `"interpret": null`.

    **The button worked and the card said nothing.** He pressed Interpret because I told
    him to in chat, not because the panel told him a press was owed -- and «حتى لا انتظر
    شى يحتاج اكشن منى» is the requirement that badge exists for.
    """
    client, path = served
    conn = dbmod.connect(path)
    try:
        # An interpretation that finished, and then a profile sweep AFTER it.
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status, "
            "                       finished_at) "
            "VALUES ('job_read','update',?,?,'completed','2026-09-06T14:07:16Z')",
            (f'["{SITE}"]', datasetjob.JOB_KIND))
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status, "
            "                       finished_at) "
            "VALUES ('job_sweep','update',?,?,'completed','2026-09-07T14:23:50Z')",
            (f'["{SITE}"]', profilejob.JOB_KIND))
        conn.commit()
    finally:
        conn.close()

    rows = client.get("/api/sources").json()["sources"]
    waiting = next(row["work_waiting"] for row in rows
                   if row.get("site_key") == SITE and row.get("work_waiting"))

    assert waiting["interpret"] is not None, (
        "a profile sweep finished after the last interpretation and the card says "
        "nothing is owed -- which is the whole point of that badge")
    assert waiting["interpret"]["crawl_finished_at"] == "2026-09-07T14:23:50Z", (
        f"the badge is dated from the wrong run: {waiting['interpret']}")
    assert waiting["interpret"]["interpreted_at"] == "2026-09-06T14:07:16Z"


def test_the_two_collecting_kinds_are_named_once(served):
    """TWO READERS, ONE FACT. The selection and the badge both need to know which kinds
    collect pages, and issue 792 happened because only the first was widened. A third
    reader would make it three, so the names live in `datasetjob.COLLECTING_KINDS` and
    this asserts nothing re-types them."""
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parent.parent
    app = (root / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")

    assert "COLLECTING_KINDS" in app, (
        "the route no longer reads the shared constant, so the two readers can drift "
        "again")
    assert '"profile_crawl"' not in app.replace(
        'profilejob.JOB_KIND', ''), (
        "the route re-types a collecting kind as a literal instead of reading the "
        "constant")
    assert set(datasetjob.COLLECTING_KINDS) == {directoryjob.JOB_KIND,
                                                profilejob.JOB_KIND}, (
        f"the constant and the modules disagree: {datasetjob.COLLECTING_KINDS}")


def test_the_sources_route_says_what_is_waiting(served):
    """HIS REQUIREMENT: *«اريد الظهور على الكارت انه يحتاج لعمل interpret store pages عند
    الحاجة»* -- so the card is not a place he waits for something that is waiting for
    him. The panel can only draw it if the route sends it."""
    client, _path = served

    rows = client.get("/api/sources").json()["sources"]
    cards = [row for row in rows
             if row.get("site_key") == SITE and row.get("kind") == "dataset"]

    assert cards, f"muqawil has no dataset card: {[r.get('kind') for r in rows]}"
    for row in cards:
        assert "work_waiting" in row, (
            "the route does not say what is waiting, so the card cannot")
        waiting = row["work_waiting"]
        assert set(waiting) >= {"interpret", "profiles"}, waiting
        # TWO NUMBERS, NOT ONE, AND HIS SCREENSHOT IS WHY. `rowless` is who has no
        # profile ROW -- the coverage figure -- and `fetch` is who still needs a REQUEST.
        # They were one number until 2026-09-07, when he fetched 938 pages, `rowless` did
        # not move (storing a page writes no row), and the card went on offering a button
        # that would buy the same pages again.
        #
        # EQUAL HERE, because nothing has been fetched in this warehouse: two sighted
        # contractors, no rows and no pages. The state where they DIVERGE is asserted in
        # `test_the_fetch_gap_closes_when_the_pages_are_stored` below.
        assert waiting["profiles"] == {"rowless": 2, "fetch": 2}, waiting
        assert waiting["interpret"] is None, (
            "no crawl has finished in this warehouse and the route says one has")


def test_a_re_entered_sweep_says_so_and_says_what_it_costs(warehouse, monkeypatch):
    """ISSUE 796 IN THIS RUNNER, AND THE CALL SITE IS THE SUBJECT. A mutation deleting
    the call from `run_profile_crawl_job_once` survived every guard that drove
    `jobs.note_a_re_entry` directly -- the vacuity shape of a test that reads a helper
    while the wiring goes unmeasured.

    The state is what `reclaim_orphaned_jobs` leaves behind when a restart requeues a
    running job: `started_at` set, `progress_done` at what the previous pass reached.
    Measured on his warehouse 2026-09-07, eight times across two jobs in half an hour
    while he was updating the engine -- and every runner writes `progress_done = 0` at
    entry, so his bar went back to zero with no line anywhere saying why.

    AND THE CONSEQUENCE IS THIS KIND'S OWN. A sweep skips what is already stored under
    its run ref; an interpretation asks the site for nothing at all. One sentence for
    both would be false for one of them.
    """
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["8201", "8202"])
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.execute(
        "UPDATE crawl_job SET started_at = ?, progress_done = ? WHERE job_ref = ?",
        ("2026-09-07T10:33:25Z", 620, job_ref))
    conn.commit()
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, lambda url: "<html></html>"))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    said = " | ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "not this job's first pass" in said, (
        f"the sweep reset his bar to zero and said nothing: {said}")
    assert "620 page(s)" in said, (
        f"the number he watched disappear is not in the line: {said}")
    assert "skipped rather than bought again" in said, (
        f"the line does not say what a re-entry costs for a SWEEP: {said}")


def test_a_first_sweep_says_nothing_about_a_restart(warehouse, monkeypatch):
    """A line on every start is noise, and noise on every start is how the line that
    matters stops being read."""
    conn, _path = warehouse
    directory = directories.get(SITE)
    _sight(conn, directory.dataset_key, ["8301"])
    job_ref = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
    conn.commit()
    monkeypatch.setattr(contractors, "make_fetch",
                        lambda pace: (None, lambda url: "<html></html>"))

    profilejob.run_profile_crawl_job_once(conn, job_ref)

    said = " | ".join(row["message"] for row in jobs.job_logs(conn, job_ref))
    assert "not this job's first pass" not in said, said


def test_the_route_says_what_each_kind_counted(served):
    """A NUMBER WITHOUT ITS UNIT IS A NUMBER THE PANEL HAS TO GUESS, and it guessed
    wrong: the Jobs page printed "469 of 469 source(s)" for 469 page pairs, against
    twelve registered sources.

    MEASURED ON HIS LIVE ENGINE, 2026-09-10: `GET /api/jobs` returns
    `fetch.requests = 0` and `fetch.expected = null` for every `profile_crawl` and
    `dataset_interpret` job -- neither runner is among `record_source_fetch`'s callers --
    so `progress` is the only pair a reader has, and it named nothing.

    THE RUNNER THAT WROTE THE NUMBER IS THE ONLY THING THAT KNOWS WHAT IT COUNTED, which
    is why the word is declared on the wire and not guessed in the panel.
    """
    client, path = served
    conn = dbmod.connect(path)
    try:
        sweep = jobs.create_job(conn, [SITE], job_kind=profilejob.JOB_KIND)
        interpret = jobs.create_job(conn, [SITE], job_kind=datasetjob.JOB_KIND)
        crawl = jobs.create_job(conn, [SITE])
        conn.commit()
    finally:
        conn.close()

    listed = {job["job_ref"]: job for job in client.get("/api/jobs").json()["jobs"]}

    assert listed[sweep]["progress"]["unit"] == "page(s)", (
        f"a profile sweep counts pages and says so: {listed[sweep]['progress']}")
    assert listed[interpret]["progress"]["unit"] == "page pair(s)", (
        f"an interpretation counts page PAIRS -- 469 pairs is 938 stored readings and "
        f"neither is the other: {listed[interpret]['progress']}")
    # AND A KIND THAT COUNTS SOURCES DECLARES NOTHING, which is what the pair meant
    # before any kind declared anything. Adding a word here would be a second guess.
    assert "unit" not in listed[crawl]["progress"], (
        f"a price crawl counts sources and was given a unit: {listed[crawl]['progress']}")

    # THE FETCH SIDE IS EMPTY FOR BOTH, which is the fact that makes the unit
    # load-bearing rather than decorative.
    for ref in (sweep, interpret):
        assert not listed[ref]["fetch"]["requests"], listed[ref]["fetch"]
        assert not listed[ref]["fetch"]["expected"], listed[ref]["fetch"]
