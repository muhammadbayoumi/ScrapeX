"""Spec 23/24/25: job persistence, lifecycle, pause/resume/cancel, checkpoint recovery.

Every test drives the synchronous seam run_job_once — no threads — so the whole
lifecycle is deterministic. Capture is injected, so nothing touches the network.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from scrapex import db as dbmod
from scrapex.capture import CaptureResult
from scrapex.ingest import IngestResult
from scrapex.jobs import (
    JobRunner, append_log, create_job, get_job, job_logs, list_jobs, run_job_once, set_control,
)
from scrapex.vocab import JobControl, JobStatus, RunMode


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


class _FakeManifest:
    def __init__(self, keys, min_expected_rows=None, max_drop_pct=None):
        self._keys = list(keys)
        self._min, self._max_drop = min_expected_rows, max_drop_pct
    def get(self, key):
        if key not in self._keys:
            raise KeyError(f"unknown source_key {key!r}")
        return SimpleNamespace(source_key=key, min_expected_rows=self._min,
                               max_drop_pct=self._max_drop)


def _result(key, observations=3, products=2, requests=4, errors=(), rows=10) -> CaptureResult:
    ingest = IngestResult(source_key=key, run_id=1, observations=observations, products=products)
    ingest.errors = list(errors)
    return CaptureResult(ingest=ingest, requests_count=requests, tables=1, rows=rows)


def _capture_ok(calls: list):
    def capture(c, entry, job_id=None):
        calls.append(entry.source_key)
        return _result(entry.source_key)
    return capture


# ---- creation + persistence --------------------------------------------------

def test_create_job_is_queued_and_persisted(conn):
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    job = get_job(conn, ref)
    assert job["status"] == JobStatus.QUEUED.value and job["run_mode"] == "update"
    assert job["source_keys"] == ["A", "B"] and job["progress_total"] == 2
    assert job["progress_done"] == 0 and job["finished_at"] is None


def test_create_job_rejects_empty_source_list(conn):
    with pytest.raises(ValueError, match="at least one source_key"):
        create_job(conn, [])


def test_unknown_job_ref_raises(conn):
    with pytest.raises(KeyError):
        run_job_once(conn, "job_missing", _FakeManifest([]))


# ---- happy path --------------------------------------------------------------

def test_job_completes_and_aggregates_counters(conn):
    calls: list[str] = []
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    job = run_job_once(conn, ref, _FakeManifest(["A", "B"]), capture=_capture_ok(calls))
    assert calls == ["A", "B"]
    assert job["status"] == JobStatus.COMPLETED.value
    assert job["progress_done"] == 2 and job["finished_at"] is not None
    assert job["counters"]["observations"] == 6      # 3 per source, aggregated
    assert job["counters"]["requests"] == 8
    assert job["stage"] is None and job["current_source_key"] is None


# ---- per-source failure isolation (Q3) ---------------------------------------

def test_one_failing_source_downgrades_to_partially_completed(conn):
    calls: list[str] = []

    def capture(c, entry, job_id=None):
        calls.append(entry.source_key)
        if entry.source_key == "A":
            raise RuntimeError("site down")
        return _result(entry.source_key)

    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    job = run_job_once(conn, ref, _FakeManifest(["A", "B"]), capture=capture)
    assert calls == ["A", "B"]                        # B still ran
    assert job["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert "site down" in job["error_summary"]
    assert job["counters"]["observations"] == 3       # only B's


def test_all_sources_failing_is_failed(conn):
    def capture(c, entry, job_id=None):
        raise RuntimeError("boom")

    ref = create_job(conn, ["A"], RunMode.UPDATE)
    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture)
    assert job["status"] == JobStatus.FAILED.value and "boom" in job["error_summary"]


# ---- pause / resume / cancel at safe boundaries ------------------------------

def test_pause_stops_at_boundary_and_resume_skips_completed(conn):
    calls: list[str] = []
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)

    def capture(c, entry, job_id=None):
        calls.append(entry.source_key)
        if entry.source_key == "A":
            set_control(c, ref, JobControl.PAUSE)     # requested mid-run
        return _result(entry.source_key)

    job = run_job_once(conn, ref, _FakeManifest(["A", "B"]), capture=capture)
    assert job["status"] == JobStatus.PAUSED.value
    assert calls == ["A"]                              # B not started
    assert job["checkpoint"]["completed_source_keys"] == ["A"]

    assert set_control(conn, ref, JobControl.RESUME) is True
    assert get_job(conn, ref)["status"] == JobStatus.QUEUED.value
    resumed = run_job_once(conn, ref, _FakeManifest(["A", "B"]), capture=capture)
    assert resumed["status"] == JobStatus.COMPLETED.value
    assert calls == ["A", "B"]                         # A was NOT re-crawled
    assert resumed["counters"]["observations"] == 6    # counters carried across the pause


def test_cancelling_a_queued_job_settles_it_immediately(conn):
    """Regression (CRITICAL): a queued job parked in 'cancelling' was stranded
    forever — the worker only ever picks up 'queued', so nothing could settle it,
    and _source_is_busy then blocked that source's schedules for good."""
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    assert set_control(conn, ref, JobControl.CANCEL) is True

    job = get_job(conn, ref)
    assert job["status"] == JobStatus.CANCELLED.value      # terminal at once
    assert job["finished_at"] is not None
    # ...and it must NOT be selectable by the worker, nor look active any more.
    assert JobRunner._next_queued(conn) is None
    assert list_jobs(conn, active_only=True) == []


def test_pausing_a_queued_job_settles_it_immediately(conn):
    ref = create_job(conn, ["A"], RunMode.UPDATE)
    assert set_control(conn, ref, JobControl.PAUSE) is True
    assert get_job(conn, ref)["status"] == JobStatus.PAUSED.value
    assert JobRunner._next_queued(conn) is None      # paused waits on the owner


def test_cancel_through_the_real_dispatch_path_runs_nothing(conn):
    """Drives _next_queued -> run_job_once, the way the worker actually does."""
    calls: list[str] = []
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    set_control(conn, ref, JobControl.CANCEL)

    picked = JobRunner._next_queued(conn)
    if picked is not None:                      # must not be picked up at all
        run_job_once(conn, picked, _FakeManifest(["A", "B"]), capture=_capture_ok(calls))
    assert calls == []
    assert get_job(conn, ref)["status"] == JobStatus.CANCELLED.value


def test_cancel_mid_run_uses_the_transitional_status(conn):
    """A job the worker IS holding still settles at its next safe boundary."""
    calls: list[str] = []
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    seen: list[str] = []

    def capture(c, entry, job_id=None):
        calls.append(entry.source_key)
        if entry.source_key == "A":
            set_control(c, ref, JobControl.CANCEL)          # while RUNNING
            seen.append(get_job(c, ref)["status"])
        return _result(entry.source_key)

    job = run_job_once(conn, ref, _FakeManifest(["A", "B"]), capture=capture)
    assert seen == [JobStatus.CANCELLING.value]     # transitional while held
    assert calls == ["A"] and job["status"] == JobStatus.CANCELLED.value


def test_control_on_a_finished_job_is_refused(conn):
    ref = create_job(conn, ["A"], RunMode.UPDATE)
    run_job_once(conn, ref, _FakeManifest(["A"]), capture=_capture_ok([]))
    assert set_control(conn, ref, JobControl.CANCEL) is False   # already completed


def test_rerunning_a_terminal_job_is_a_no_op(conn):
    calls: list[str] = []
    ref = create_job(conn, ["A"], RunMode.UPDATE)
    run_job_once(conn, ref, _FakeManifest(["A"]), capture=_capture_ok(calls))
    run_job_once(conn, ref, _FakeManifest(["A"]), capture=_capture_ok(calls))
    assert calls == ["A"]


# ---- full_rebuild archives before crawling, never deletes (spec 13) ---------

def test_full_rebuild_backs_up_and_archives_before_crawling(conn):
    order: list[str] = []
    ref = create_job(conn, ["A"], RunMode.FULL_REBUILD)

    def capture(c, entry, job_id=None):
        order.append("crawl")
        return _result(entry.source_key)

    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture,
                       backup=lambda: (order.append("backup"), "/tmp/h.backup.db")[1])
    assert job["status"] == JobStatus.COMPLETED.value
    assert order == ["backup", "crawl"]          # backup happens FIRST
    assert any("backup created" in e["message"] for e in job_logs(conn, ref))
    assert any("archived" in e["message"] for e in job_logs(conn, ref))


def test_full_rebuild_without_a_backup_hook_still_archives(conn):
    ref = create_job(conn, ["A"], RunMode.FULL_REBUILD)
    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=_capture_ok([]))
    assert job["status"] == JobStatus.COMPLETED.value
    assert any("archived" in e["message"] for e in job_logs(conn, ref))


# ---- unknown source is isolated, not fatal ----------------------------------

def test_unknown_source_key_is_recorded_not_fatal(conn):
    calls: list[str] = []
    ref = create_job(conn, ["GHOST", "A"], RunMode.UPDATE)
    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=_capture_ok(calls))
    assert calls == ["A"]
    assert job["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert "GHOST" in job["error_summary"]


# ---- logs + listing ----------------------------------------------------------

def test_job_logs_tail_is_oldest_last_and_bounded(conn):
    ref = create_job(conn, ["A"], RunMode.UPDATE)
    job = get_job(conn, ref)
    for i in range(10):
        append_log(conn, job["job_id"], f"entry {i}")
    conn.commit()
    tail = job_logs(conn, ref, limit=3)
    assert [e["message"] for e in tail] == ["entry 7", "entry 8", "entry 9"]


def test_run_writes_aggregated_log_entries_not_one_per_record(conn):
    ref = create_job(conn, ["A"], RunMode.UPDATE)
    run_job_once(conn, ref, _FakeManifest(["A"]), capture=_capture_ok([]))
    messages = [e["message"] for e in job_logs(conn, ref)]
    assert any("job started" in m for m in messages)
    assert any("observations" in m for m in messages)
    assert len(messages) <= 5      # aggregated: a handful, never per-record


# ---- F6 volume canary (a rotted connector fails QUIETLY) --------------------

def test_zero_rows_is_a_canary_breach_not_a_success(conn):
    """The bug this locks in: a connector returning nothing used to complete clean."""
    ref = create_job(conn, ["A"], RunMode.UPDATE)

    def capture(c, entry, job_id=None):
        return _result(entry.source_key, observations=0, rows=0)

    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture)
    assert job["status"] == JobStatus.FAILED.value
    assert "zero rows" in job["error_summary"]


def test_rows_below_declared_minimum_breaches(conn):
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)
    manifest = _FakeManifest(["A", "B"], min_expected_rows=50)

    def capture(c, entry, job_id=None):
        return _result(entry.source_key, rows=5 if entry.source_key == "A" else 500)

    job = run_job_once(conn, ref, manifest, capture=capture)
    assert job["status"] == JobStatus.PARTIALLY_COMPLETED.value   # B was healthy
    assert "below the declared minimum" in job["error_summary"]


def test_healthy_volume_passes_the_canary(conn):
    ref = create_job(conn, ["A"], RunMode.UPDATE)
    manifest = _FakeManifest(["A"], min_expected_rows=50)
    job = run_job_once(conn, ref, manifest,
                       capture=lambda c, e, j=None: _result(e.source_key, rows=500))
    assert job["status"] == JobStatus.COMPLETED.value


# ---- the worker thread (spec 4: the runtime executes, not the panel) --------

def test_runner_thread_drains_the_queue(tmp_path):
    """The job outlives whoever queued it: nothing but the worker touches it."""
    import time

    db = tmp_path / "harvest.db"
    setup = dbmod.connect(db)
    dbmod.migrate(setup)
    ref = create_job(setup, ["A"], RunMode.UPDATE)
    setup.close()

    runner = JobRunner(str(db), lambda: _FakeManifest(["A"]), poll_interval_s=0.02,
                       capture=lambda c, e, j=None: _result(e.source_key))
    runner.start()
    try:
        deadline = time.monotonic() + 10
        status = None
        while time.monotonic() < deadline:
            check = dbmod.connect(db)
            try:
                status = get_job(check, ref)["status"]
            finally:
                check.close()
            if status == JobStatus.COMPLETED.value:
                break
            time.sleep(0.05)
    finally:
        runner.stop()
    assert status == JobStatus.COMPLETED.value


def test_list_jobs_active_only_excludes_finished(conn):
    done_ref = create_job(conn, ["A"], RunMode.UPDATE)
    run_job_once(conn, done_ref, _FakeManifest(["A"]), capture=_capture_ok([]))
    open_ref = create_job(conn, ["B"], RunMode.UPDATE)

    refs_all = {j["job_ref"] for j in list_jobs(conn)}
    refs_active = {j["job_ref"] for j in list_jobs(conn, active_only=True)}
    assert {done_ref, open_ref} <= refs_all
    assert refs_active == {open_ref}


def test_the_db_lock_wraps_only_the_ingest_not_the_network_fetch(tmp_path):
    """Regression: the lock used to span connector.fetch, so every unrelated UI
    write was refused for the whole (minutes-long) crawl. It must be held only
    while the ingest writes."""
    from scrapex import db as dbmod
    from scrapex.capture import capture_source
    from scrapex.config import ExtractSpec, SourceEntry
    from scrapex.connectors.base import ScrapedTable
    from scrapex.rowspec import PRODUCT_PRICES
    from scrapex.vocab import ExtractKind, ExtractScope

    db = tmp_path / "h.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    entry = SourceEntry.model_validate(dict(
        source_key="ELSEWEDYSHOP", source_name="Shop", base_url="https://x.co",
        family="shopify-json", currency="EGP", default_region="EG",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)]))

    held: list[bool] = []

    class _Connector:
        connector_id = "shopify-json"
        def fetch(self, source):
            # While fetching, the lock must be FREE — another writer can take it.
            try:
                with dbmod.write_lock(db, timeout_s=0.3):
                    held.append(False)          # free: acquired without contention
            except dbmod.DbLockedError:
                held.append(True)               # still held across the fetch (the bug)
            yield ScrapedTable("ELSEWEDYSHOP", PRODUCT_PRICES.kind, "u",
                               list(PRODUCT_PRICES.columns), [])

    class _Fetcher:
        requests_count = 0
        def close(self): pass

    import scrapex.capture as capmod
    original = capmod.build_connector
    # Two arguments now: the owner's crawl settings ride along with the entry.
    capmod.build_connector = lambda e, crawl=None: (_Connector(), _Fetcher())
    try:
        capture_source(conn, entry, lock=lambda: dbmod.write_lock(db))
    finally:
        capmod.build_connector = original
        conn.close()
    assert held == [False], "the DB lock was held across the network fetch"
