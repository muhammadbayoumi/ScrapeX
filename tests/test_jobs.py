"""Spec 23/24/25: job persistence, lifecycle, pause/resume/cancel, checkpoint recovery.

Every test drives the synchronous seam run_job_once — no threads — so the whole
lifecycle is deterministic. Capture is injected, so nothing touches the network.
"""
from __future__ import annotations

import json
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


# ---- ingest errors surface at job level (the stranded-run incident) ----------

def test_ingest_errors_finish_the_job_completed_with_errors(conn):
    """Regression: the worker folded result.ingest.errors into a bare integer,
    so a job whose only run degraded to PARTIAL finished 'completed' with
    error_summary NULL and checkpoint errors [] — the message that explained a
    live data loss was unrecoverable from anywhere."""
    ref = create_job(conn, ["A"], RunMode.UPDATE)

    def capture(c, entry, job_id=None):
        return _result(entry.source_key, errors=("row 3: price is empty",))

    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture)
    assert job["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
    assert "A: row 3: price is empty" in job["error_summary"]
    assert job["checkpoint"]["errors"] == ["A: row 3: price is empty"]
    warned = [e for e in job_logs(conn, ref) if e["level"] == "warning"]
    assert any("row 3" in e["message"] and e["source_key"] == "A" for e in warned)


def test_a_dead_source_still_outranks_completed_with_errors(conn):
    """One source dies, the other merely degrades: the job is partially
    completed — a whole source missing is the stronger statement."""
    ref = create_job(conn, ["A", "B"], RunMode.UPDATE)

    def capture(c, entry, job_id=None):
        if entry.source_key == "A":
            raise RuntimeError("site down")
        return _result(entry.source_key, errors=("row 1: bad money",))

    job = run_job_once(conn, ref, _FakeManifest(["A", "B"]), capture=capture)
    assert job["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert "A: site down" in job["error_summary"]
    assert "B: row 1: bad money" in job["error_summary"]


def test_contained_notes_warn_but_do_not_degrade_the_job(conn):
    """A contained side-effect failure (tax evidence) is logged for the owner
    and counted, but the run succeeded — so the job stays 'completed'."""
    ref = create_job(conn, ["A"], RunMode.UPDATE)

    def capture(c, entry, job_id=None):
        result = _result(entry.source_key)
        result.ingest.contained = ["tax evidence not recorded: disk I/O error"]
        return result

    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture)
    assert job["status"] == JobStatus.COMPLETED.value
    assert job["error_summary"] is None
    assert job["counters"]["errors"] == 1             # visible, not fatal
    warned = [e for e in job_logs(conn, ref) if e["level"] == "warning"]
    assert any("tax evidence" in e["message"] for e in warned)


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
    asked: list[bool] = []
    ref = create_job(conn, ["A"], RunMode.FULL_REBUILD)

    def capture(c, entry, job_id=None, **kw):
        order.append("crawl")
        asked.append(kw.get("archive_first", False))
        return _result(entry.source_key)

    job = run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture,
                       backup=lambda: (order.append("backup"), "/tmp/h.backup.db")[1])
    assert job["status"] == JobStatus.COMPLETED.value
    assert order == ["backup", "crawl"]          # backup happens FIRST
    assert any("backup created" in e["message"] for e in job_logs(conn, ref))
    # The archive itself travels INTO the capture, to run inside the same
    # write lock as the ingest: doing it here left the catalogue archived and
    # nothing re-crawled when the lock was held (the owner's sika run).
    assert asked == [True]


def test_only_a_rebuild_asks_capture_to_archive(conn):
    asked: list[dict] = []
    ref = create_job(conn, ["A"], RunMode.UPDATE)

    def capture(c, entry, job_id=None, **kw):
        asked.append(kw)
        return _result(entry.source_key)

    run_job_once(conn, ref, _FakeManifest(["A"]), capture=capture)
    assert asked == [{}], "an ordinary update must never archive"


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


def test_locked_capture_forwards_every_capture_keyword(tmp_path):
    """Regression (owner-reported: every full_rebuild failed on an unexpected
    'archive_first'). run_job_once passes history/resume/archive_first through
    **extras; the _locked_capture seam only ADDS the write lock, so it must
    forward whatever it is handed instead of enumerating a keyword set that
    goes stale the moment capture_source grows one."""
    import inspect

    from scrapex.jobs import JobRunner

    seen: dict = {}

    def fake_capture(conn, entry, job_id=None, *, lock=None, **kw):
        seen.update(kw)
        return _result(entry.source_key)

    runner = JobRunner(str(tmp_path / "h.db"), lambda: _FakeManifest(["A"]))
    # Patch the module capture_source the seam calls, then drive the seam the
    # way run_job_once does — with the rebuild keyword.
    import scrapex.jobs as jobs_mod
    original = jobs_mod.capture_source
    jobs_mod.capture_source = fake_capture
    try:
        runner._locked_capture(None, SimpleNamespace(source_key="A"), 1,
                               history=True, resume=True, archive_first=True)
    finally:
        jobs_mod.capture_source = original

    assert seen == {"history": True, "resume": True, "archive_first": True}
    # And the seam must not hardcode a keyword list that can drift.
    params = inspect.signature(JobRunner._locked_capture).parameters
    assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()), \
        "the capture seam must forward **extras, not a fixed keyword set"


# ---- a fault that hides itself costs more than the fault ----------------------

def test_a_worker_failure_is_recorded_where_a_person_can_find_it(conn):
    """The owner watched pages answer on the port while no crawl could start,
    and waited. The worker HAD failed and HAD said so — to stderr, from a
    process launched with pythonw, which has no console and no redirect. The
    diagnosis was produced and discarded in the same breath.

    So a failure now lands in the warehouse, which is the one place both the
    engine and the interface can already reach.
    """
    from scrapex.jobs import WORKER_ERROR_KEY, record_worker_failure, worker_health

    record_worker_failure(conn, RuntimeError("the connector exploded"), fatal=False)

    stored = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                          (WORKER_ERROR_KEY,)).fetchone()
    assert stored, "the failure was not written anywhere a person can look"
    failure = json.loads(stored[0])
    assert failure["error"] == "RuntimeError: the connector exploded"
    assert "the connector exploded" in failure["traceback"]
    assert failure["fatal"] is False

    # And the health answer CARRIES the reason, instead of a bare "not running"
    # that leaves the owner to guess.
    health = worker_health(conn)
    assert health["alive"] is False
    assert "the connector exploded" in health["detail"]


def test_a_recovered_worker_stops_showing_the_fault_it_survived(conn):
    from scrapex.jobs import (WORKER_ERROR_KEY, clear_worker_failure,
                              record_worker_failure)

    record_worker_failure(conn, RuntimeError("transient"), fatal=False)
    clear_worker_failure(conn)
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM scrapex_meta WHERE key = ?",
                        (WORKER_ERROR_KEY,)).fetchone()[0] == 0


def test_a_live_port_is_never_taken_as_proof_the_worker_runs(conn):
    """The distinction that cost an afternoon. The heartbeat is written by the
    LOOP, so it is the only signal that can prove a crawl could start — the port
    answering proves the web server and nothing else.
    """
    from scrapex.jobs import HEARTBEAT_MAX_AGE_S, touch_runtime_heartbeat, worker_health

    assert worker_health(conn)["alive"] is False, "never beaten = not running"
    assert "never reported" in worker_health(conn)["detail"]

    touch_runtime_heartbeat(conn)
    conn.commit()
    fresh = worker_health(conn)
    assert fresh["alive"] is True and fresh["age_s"] <= HEARTBEAT_MAX_AGE_S

    # A stale beat is NOT alive, and says so in the owner's terms.
    conn.execute("UPDATE scrapex_meta SET value = '2020-01-01T00:00:00Z' "
                 "WHERE key = 'runtime_heartbeat'")
    conn.commit()
    stale = worker_health(conn)
    assert stale["alive"] is False
    assert "Pages may still open" in stale["detail"]


def test_the_worker_can_still_report_when_stderr_is_gone(tmp_path, monkeypatch):
    """The root cause, pinned. Under pythonw sys.stderr IS None, and the worker
    reports with traceback.print_exc(file=sys.stderr) — writing to None raises
    inside the handler, so the act of reporting a fault killed the thread that
    hit it. The engine then served pages while nothing could crawl, and said
    nothing anywhere.

    Two things now stand between that and the owner: the engine binds its
    streams to ~/.scrapex/engine.log before it starts, and the failure is
    written to the warehouse regardless of whether any stream exists.
    """
    import sys as _sys

    from scrapex import cli
    from scrapex.cli import _bind_log_streams

    # Its own log file. Pointed at the real one, this test opened the
    # engine's live handle and failed whenever ScrapeX was RUNNING —
    # exactly the machine-state dependence that made the extension test
    # pass only where the app was not installed.
    monkeypatch.setattr(cli, "RUN_DUE_LOG", tmp_path / "engine.log")

    out, err = _sys.stdout, _sys.stderr
    try:
        _sys.stdout = None      # exactly what pythonw hands a process
        _sys.stderr = None
        _bind_log_streams()
        assert _sys.stdout is not None and _sys.stderr is not None, \
            "the engine would have no way to say anything at all"
        _sys.stderr.write("")   # must not raise
    finally:
        _sys.stdout, _sys.stderr = out, err


# ---- a reopen that fails must stay recoverable --------------------------------
# The worker released its only connection, could not get a new one, and kept the
# CLOSED object: every later pass took the same dead handle (the reopen guard
# matched again because the path had already been committed), the failure
# recorder's own rollback raised on it, and the loop spun at poll speed with no
# crawls, no scheduler, no heartbeat and nothing written anywhere. A transient
# fault — the instant during a restore's os.replace when the file is absent —
# became permanent until the engine was restarted, and /api/health went on
# saying the worker was fine.

@pytest.fixture()
def warehouse(tmp_path):
    """A real file — the reopen path renames and reopens one, which :memory: cannot."""
    path = tmp_path / "harvest.db"
    c = dbmod.connect(path)
    dbmod.migrate(c)
    c.commit()
    c.close()
    return path


def _runner(path) -> JobRunner:
    return JobRunner(str(path), lambda: {}, path_provider=lambda: str(path))


def test_a_failed_reopen_does_not_commit_the_new_path_or_clear_the_request(warehouse, monkeypatch):
    runner = _runner(warehouse)
    runner._db_path = str(warehouse.parent / "old.db")   # a move is in progress
    runner.release_database()
    conn = dbmod.connect(warehouse)

    monkeypatch.setattr(dbmod, "connect", _refuse)
    with pytest.raises(sqlite3.OperationalError):
        runner._follow_the_warehouse(conn)

    assert runner._reopen.is_set(), \
        "the reopen request was consumed by an attempt that failed — nothing will retry"
    assert str(runner._db_path) != str(warehouse), \
        "the worker committed to a database it never managed to open, so the guard " \
        "will short-circuit every later pass and hand back the closed handle"


def _refuse(_path):
    raise sqlite3.OperationalError("unable to open database file")


def test_a_reopen_that_succeeds_after_a_failure_recovers_fully(warehouse, monkeypatch):
    runner = _runner(warehouse)
    runner._db_path = str(warehouse.parent / "old.db")
    runner.release_database()

    real = dbmod.connect
    monkeypatch.setattr(dbmod, "connect", _refuse)
    with pytest.raises(sqlite3.OperationalError):
        runner._follow_the_warehouse(real(warehouse))

    # The fault has passed (the restore finished). The next pass must go through.
    monkeypatch.setattr(dbmod, "connect", real)
    fresh = runner._follow_the_warehouse(real(warehouse))
    try:
        assert fresh.execute("SELECT 1").fetchone()[0] == 1
        assert not runner._reopen.is_set(), "a successful reopen must clear the request"
        assert str(runner._db_path) == str(warehouse)
    finally:
        fresh.close()


def test_the_failure_is_recorded_even_with_no_connection_left(warehouse):
    """The pass with no handle is the one whose reason the owner most needs, and
    it was the only pass that recorded nothing."""
    from scrapex.jobs import WORKER_ERROR_KEY

    _runner(warehouse)._record_failure(
        None, sqlite3.OperationalError("unable to open database file"))

    conn = dbmod.connect(warehouse)
    try:
        row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                           (WORKER_ERROR_KEY,)).fetchone()
    finally:
        conn.close()
    assert row is not None, "a worker that lost its database left no trace of why"
    assert "unable to open database file" in json.loads(row[0])["error"]
