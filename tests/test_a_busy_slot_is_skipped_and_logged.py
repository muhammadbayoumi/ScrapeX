"""A scheduled firing that finds its source busy is skipped, and says so (#1596, step A).

His rulings on #1596: a run that comes due while the same source is already running, or
while another app holds the warehouse's write lock, is skipped. A finished `skipped` job
records why, naming the run that blocked it, and the schedule fires again at its next
slot. It never waits in a queue, whatever the stored `overlap_policy` says (D2), and a
PAUSED directory run counts as busy while a paused price run does not (D3). A skip
decided while another app holds the lock is written once the lock is free (D5).

Every row is written into the real schema (`dbmod.migrate`).
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scrapex import cli, jobs, native, scheduler
from scrapex import db as dbmod
from scrapex.config import SourceEntry
from scrapex.jobs import JobRunner, create_job, list_jobs
from scrapex.scheduler import (
    HELD_LOCK,
    HELD_WAIT,
    LOCK_HELD_REASON,
    HeldOutUnreadable,
    fire_due,
    fire_due_under_lock,
    get_schedule,
    held_out_path,
    read_held_out,
    upsert_schedule,
    utcnow,
)
from scrapex.vocab import JobStatus, MissedRunPolicy, OverlapPolicy

SHOP = "SHOP"
ISO = "%Y-%m-%dT%H:%M:%SZ"


def utc(y, m, d, hh=0, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


class _Manifest:
    """Every source active unless told otherwise."""

    def __init__(self, active: bool = True) -> None:
        self.active = active

    def get(self, key):
        return SourceEntry.model_validate({
            "source_key": key, "source_name": key, "base_url": "https://source.test",
            "family": "custom-json-api", "active": self.active,
            "extract": [{"kind": "product_prices"}]})


class _NoSuchSource:
    """A resolver that knows no source, as `SourceResolver` answers one (#1609)."""

    def get(self, key):
        raise LookupError(key)


@pytest.fixture()
def conn():
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def _skips(conn) -> list[dict]:
    return [job for job in list_jobs(conn, limit=100)
            if job["status"] == JobStatus.SKIPPED.value]


def _queued(conn) -> list[dict]:
    return [job for job in list_jobs(conn, limit=100)
            if job["status"] == JobStatus.QUEUED.value]


def _daily(conn, policy: str = OverlapPolicy.QUEUE.value) -> None:
    upsert_schedule(conn, SHOP, frequency="daily", run_at="09:00",
                    overlap_policy=policy, now=utc(2026, 7, 20, 8, 0))


# ---- a busy source -----------------------------------------------------------

@pytest.mark.parametrize("policy", [OverlapPolicy.QUEUE.value, OverlapPolicy.SKIP.value])
@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSING])
def test_a_busy_source_is_skipped_once_names_its_blocker_and_rearms(conn, policy, status):
    """D2: `queue` -- the default every schedule he saved without touching it carries --
    skips now too. Exactly one finished row, its reason naming the job in the way, the
    slot re-armed to tomorrow, and nothing queued behind the running job."""
    blocker = create_job(conn, [SHOP])
    conn.execute("UPDATE crawl_job SET status = ? WHERE job_ref = ?", (status.value, blocker))
    conn.commit()
    _daily(conn, policy)

    assert fire_due(conn, utc(2026, 7, 20, 9, 0)) == [], "a skip is not a queued job"

    skips = _skips(conn)
    assert len(skips) == 1, skips
    skip = skips[0]
    assert skip["error_summary"] == f"This site's previous run was still going ({blocker})"
    assert skip["finished_at"], "a skip is written finished"
    assert skip["source_keys"] == [SHOP]
    assert skip["job_kind"] == "crawl" and skip["run_mode"] == "update", (
        "the skip must carry the kind and mode the firing would have had")
    assert [j["job_ref"] for j in _queued(conn)] == (
        [blocker] if status == JobStatus.QUEUED else []), "a second run was queued"
    assert len(list_jobs(conn, active_only=True)) == 1, "a second run was lined up"
    assert get_schedule(conn, SHOP)["next_run_at"] == "2026-07-21T09:00:00Z"
    assert get_schedule(conn, SHOP)["last_run_at"] is None, "it did not run"
    log = jobs.job_logs(conn, skip["job_ref"])
    assert any(row["message"] == skip["error_summary"] for row in log), (
        "the reason is not in the job's log, where the Logs page reads it")


def test_two_ticks_on_a_busy_source_leave_one_row(conn):
    """The worker asks twice a second. Only the tick that met the slot writes a row."""
    create_job(conn, [SHOP])
    _daily(conn)

    fire_due(conn, utc(2026, 7, 20, 9, 0))
    fire_due(conn, utc(2026, 7, 20, 9, 0) + timedelta(seconds=1))

    assert len(_skips(conn)) == 1


def test_a_skip_does_not_block_the_next_slot(conn):
    """`skipped` is not in `BLOCKING_JOB_STATUSES`: once the run in the way is over, the
    next slot fires, and the skip row before it stands in nobody's way."""
    blocker = create_job(conn, [SHOP])
    _daily(conn)
    fire_due(conn, utc(2026, 7, 20, 9, 0))
    jobs._finish(conn, jobs.get_job(conn, blocker)["job_id"], JobStatus.COMPLETED, None)

    assert len(fire_due(conn, utc(2026, 7, 21, 9, 0))) == 1


@pytest.mark.parametrize("kind", ["directory_crawl", "profile_crawl"])
def test_a_paused_directory_run_blocks_and_says_it_waits_for_him(conn, kind):
    """D3: a paused directory run is a run waiting for him."""
    paused = create_job(conn, [SHOP], job_kind=kind, status=JobStatus.PAUSED)
    _daily(conn)

    assert fire_due(conn, utc(2026, 7, 20, 9, 0)) == []

    skips = _skips(conn)
    assert [s["error_summary"] for s in skips] == [
        f"A paused run of this site was waiting for you ({paused})"]


@pytest.mark.parametrize("status", [JobStatus.PAUSED, JobStatus.REQUIRES_REVIEW])
def test_a_paused_price_run_does_not_block(conn, status):
    """A paused PRICE run waits on him and never advances alone; counting it would stop
    the schedule for good. D3 widened the busy set for directories only."""
    create_job(conn, [SHOP], status=status)
    _daily(conn)

    assert len(fire_due(conn, utc(2026, 7, 20, 9, 0))) == 1
    assert _skips(conn) == []


def test_another_sources_run_does_not_block(conn):
    create_job(conn, ["OTHER"])
    _daily(conn)

    assert len(fire_due(conn, utc(2026, 7, 20, 9, 0))) == 1
    assert _skips(conn) == []


def test_a_schedule_no_registry_knows_is_still_spent_without_a_row(conn):
    """#1609 holds: a source no registry knows is spent, busy or not, and no skip row is
    written for a source that was never going to run."""
    create_job(conn, [SHOP])
    _daily(conn)

    assert fire_due(conn, utc(2026, 7, 20, 9, 0), manifest=_NoSuchSource()) == []

    assert get_schedule(conn, SHOP)["next_run_at"] == "2026-07-21T09:00:00Z"
    assert _skips(conn) == []


def test_a_skip_carries_the_schedules_own_run_mode(conn):
    """The row is the firing that did not happen, so it says what that firing was."""
    create_job(conn, [SHOP])
    upsert_schedule(conn, SHOP, frequency="daily", run_at="09:00",
                    run_mode="full_rebuild", now=utc(2026, 7, 20, 8, 0))

    fire_due(conn, utc(2026, 7, 20, 9, 0))

    assert [s["run_mode"] for s in _skips(conn)] == ["full_rebuild"]


def test_a_busy_job_behind_two_hundred_newer_ones_still_blocks(conn):
    """Every candidate, not the newest 200: a running job of this source behind 210
    newer paused price jobs of the same source -- which do not block -- is still the
    run in the way."""
    running = create_job(conn, [SHOP], status=JobStatus.RUNNING)
    for _ in range(210):
        create_job(conn, [SHOP], status=JobStatus.PAUSED, commit=False)
    conn.commit()
    _daily(conn)

    assert fire_due(conn, utc(2026, 7, 20, 9, 0)) == []
    assert [s["error_summary"] for s in _skips(conn)] == [
        f"This site's previous run was still going ({running})"]


def test_another_key_the_pattern_matches_is_not_busy_with_it(conn):
    """The LIKE only narrows; the exact match is Python's. SQLite's LIKE ignores ASCII
    case, so `shop`'s run matches the pattern and is still not SHOP's."""
    create_job(conn, ["shop"])
    create_job(conn, ["SHOP2"])
    _daily(conn)

    assert len(fire_due(conn, utc(2026, 7, 20, 9, 0))) == 1


# ---- a slot held back from the warehouse -------------------------------------

def _held(conn, why: str) -> dict:
    slot = get_schedule(conn, SHOP)
    return {slot["schedule_id"]: {"slot": slot["next_run_at"], "why": why}}


@pytest.mark.parametrize("missed", [MissedRunPolicy.RUN_WHEN_AVAILABLE.value,
                                    MissedRunPolicy.SKIP.value])
def test_a_held_out_slot_is_written_as_a_skip_and_the_next_slot_fires(conn, missed):
    """D5: decided at the slot, written when the lock frees. A long hold is still a
    skip, not a missed slot: the row is written whatever `missed_run_policy` says."""
    upsert_schedule(conn, SHOP, frequency="daily", run_at="09:00",
                    missed_run_policy=missed, now=utc(2026, 7, 20, 8, 0))
    held_out = _held(conn, HELD_LOCK)

    assert fire_due(conn, utc(2026, 7, 20, 9, 30), held_out=held_out) == []

    assert [s["error_summary"] for s in _skips(conn)] == [LOCK_HELD_REASON]
    assert get_schedule(conn, SHOP)["next_run_at"] == "2026-07-21T09:00:00Z"
    assert get_schedule(conn, SHOP)["last_run_at"] is None, "a slot that never ran"
    assert len(fire_due(conn, utc(2026, 7, 21, 9, 0), held_out=held_out)) == 1, (
        "the next slot did not fire: a remembered hold outlived the slot it was for")
    assert len(_skips(conn)) == 1


def test_a_held_out_slot_he_has_since_moved_is_not_skipped(conn):
    """Matched on the slot, not the schedule: one he re-saved meanwhile is a new slot."""
    _daily(conn)
    held_out = {get_schedule(conn, SHOP)["schedule_id"]:
                {"slot": "2026-07-19T09:00:00Z", "why": HELD_LOCK}}

    assert len(fire_due(conn, utc(2026, 7, 20, 9, 0), held_out=held_out)) == 1
    assert _skips(conn) == []


@pytest.mark.parametrize("manifest", ["unknown", "inactive"])
def test_a_held_out_slot_of_a_source_that_would_not_run_writes_no_row(conn, manifest):
    """The registry and `active` gates come first (#1609, #1584): a source that was never
    going to run was not skipped, so no row says it was."""
    _daily(conn)
    held_out = _held(conn, HELD_LOCK)
    given = _NoSuchSource() if manifest == "unknown" else _Manifest(active=False)

    assert fire_due(conn, utc(2026, 7, 20, 9, 0), manifest=given, held_out=held_out) == []

    assert _skips(conn) == []
    assert get_schedule(conn, SHOP)["next_run_at"] == "2026-07-21T09:00:00Z"


def test_a_slot_our_own_writer_held_back_is_not_missed(conn):
    """S1: a slot first seen while our own ingest held the gate fires when the gate frees,
    however late, even under `missed_run_policy=skip` -- the machine was not off."""
    upsert_schedule(conn, SHOP, frequency="daily", run_at="09:00",
                    missed_run_policy=MissedRunPolicy.SKIP.value,
                    now=utc(2026, 7, 20, 8, 0))
    held_out = _held(conn, HELD_WAIT)

    assert len(fire_due(conn, utc(2026, 7, 20, 9, 10), held_out=held_out)) == 1
    assert _skips(conn) == []


def test_a_slot_our_own_writer_held_back_is_still_skipped_when_busy(conn):
    create_job(conn, [SHOP])
    _daily(conn)

    assert fire_due(conn, utc(2026, 7, 20, 9, 10), held_out=_held(conn, HELD_WAIT)) == []
    assert len(_skips(conn)) == 1


# ---- the lock helper ---------------------------------------------------------

@pytest.fixture()
def other_process():
    """A live process that is not us, so a lock file can name a real foreign holder."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait()


def _hold_as(db_path: Path, pid: int) -> Path:
    lock = Path(str(db_path) + ".lock")
    lock.write_text(f"{pid}:{dbmod._process_started_at(pid)}", encoding="ascii")
    return lock


def test_the_holder_is_another_live_process_or_nobody(tmp_path, other_process):
    db_path = tmp_path / "w.db"
    assert dbmod.write_lock_holder(db_path) is None, "no lock file, nobody holds it"

    lock = _hold_as(db_path, other_process)
    assert dbmod.write_lock_holder(db_path) == other_process

    _hold_as(db_path, dbmod.os.getpid())
    assert dbmod.write_lock_holder(db_path) is None, "our own pid is not another app"
    lock.unlink()

    with dbmod.write_lock(db_path):
        assert dbmod.write_lock_holder(db_path) is None, (
            "a thread of this runtime holding the lock was taken for another app")


def test_a_dead_holders_lock_is_reclaimed_not_reported(tmp_path):
    db_path = tmp_path / "w.db"
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    lock = Path(str(db_path) + ".lock")
    lock.write_text(f"{proc.pid}:stale", encoding="ascii")

    assert dbmod.write_lock_holder(db_path) is None
    assert not lock.exists(), "a dead holder's lock was left to block the next writer"


# ---- the engine's loop -------------------------------------------------------

@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "w.db"
    c = dbmod.connect(path)
    dbmod.migrate(c)
    upsert_schedule(c, SHOP, frequency="daily", run_at="00:00")
    c.execute("UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
              ((utcnow() - timedelta(seconds=30)).strftime(ISO), SHOP))
    c.commit()
    yield path, c
    c.close()


def _runner(path) -> JobRunner:
    return JobRunner(path, manifest_provider=lambda: _Manifest())


def test_the_loop_skips_a_slot_another_app_held_and_writes_it_once_free(
        warehouse, other_process):
    path, conn = warehouse
    runner = _runner(path)
    slot = get_schedule(conn, SHOP)["next_run_at"]
    lock = _hold_as(path, other_process)

    runner._fire_schedules(conn)
    runner._fire_schedules(conn)

    assert list_jobs(conn) == [], "a row was written while another app held the lock"
    assert get_schedule(conn, SHOP)["next_run_at"] == slot, (
        "the schedule was re-armed while another app held the lock")
    assert list(read_held_out(path).values()) == [{"slot": slot, "why": HELD_LOCK}]

    lock.unlink()
    runner._fire_schedules(conn)

    assert [j["error_summary"] for j in list_jobs(conn)] == [LOCK_HELD_REASON]
    assert _queued(conn) == [], "the held-out slot ran late instead of being skipped"
    assert get_schedule(conn, SHOP)["next_run_at"] > slot
    assert not held_out_path(path).exists(), "the record outlived the row it was for"

    conn.execute("UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
                 ((utcnow() - timedelta(seconds=1)).strftime(ISO), SHOP))
    conn.commit()
    runner._fire_schedules(conn)
    assert len(_queued(conn)) == 1, "the next slot did not fire"
    assert len(_skips(conn)) == 1


def test_a_restarted_engine_writes_the_skip_the_last_one_decided(warehouse, other_process):
    """M1: the decision outlives the process that made it."""
    path, conn = warehouse
    lock = _hold_as(path, other_process)
    _runner(path)._fire_schedules(conn)
    lock.unlink()

    _runner(path)._fire_schedules(conn)          # a new JobRunner, as after a restart

    assert [j["error_summary"] for j in list_jobs(conn)] == [LOCK_HELD_REASON]
    assert _queued(conn) == []


def test_a_gate_held_past_the_wait_keeps_the_slot_and_fires_it_on_time(
        warehouse, monkeypatch):
    """S1: our own ingest holding the gate past the wait records the slot HELD_WAIT and
    clears nothing; when the gate frees -- however much later -- the slot fires and is
    not classed as missed, even under `missed_run_policy=skip`."""
    path, conn = warehouse
    conn.execute("UPDATE schedule SET missed_run_policy = 'skip'")
    conn.commit()
    sid = get_schedule(conn, SHOP)["schedule_id"]
    earlier = {"slot": "2020-01-01T00:00:00Z", "why": HELD_LOCK}
    scheduler._write_held_out(path, {sid + 1: earlier})     # another schedule's entry
    release, holding = threading.Event(), threading.Event()

    def ingest():
        with dbmod.write_lock(path):
            holding.set()
            release.wait(10)

    thread = threading.Thread(target=ingest)
    thread.start()
    holding.wait(5)
    try:
        with pytest.raises(dbmod.DbLockedError):
            fire_due_under_lock(conn, path, _Manifest(), 0.2)
    finally:
        release.set()
        thread.join()

    held = read_held_out(path)
    assert held[sid]["why"] == HELD_WAIT
    assert held[sid + 1] == earlier, "a timed-out wait dropped what was already held"
    later = utcnow() + timedelta(minutes=10)
    monkeypatch.setattr(scheduler, "utcnow", lambda: later)

    assert len(fire_due_under_lock(conn, path, _Manifest(), 2.0)) == 1, (
        "a slot our own writer held back was treated as missed")
    assert _skips(conn) == []


def test_our_own_ingest_holding_the_gate_is_waited_for_not_skipped(warehouse):
    """A job thread of this runtime ingesting under `write_lock` is not another app. The
    loop waits on the in-process gate and then fires the slot."""
    path, conn = warehouse
    runner = _runner(path)
    holding = threading.Event()

    def ingest():
        with dbmod.write_lock(path):
            holding.set()
            time.sleep(0.5)

    thread = threading.Thread(target=ingest)
    thread.start()
    holding.wait(5)
    runner._fire_schedules(conn)
    thread.join()

    assert _skips(conn) == [], "our own ingest was taken for another app"
    assert len(_queued(conn)) == 1


def test_the_loop_fires_under_the_write_lock(warehouse, monkeypatch):
    """The scheduler no longer writes without the lock."""
    path, conn = warehouse
    seen: list[bool] = []
    from scrapex import scheduler

    def spy(c, **kwargs):
        lock = Path(str(path) + ".lock")
        seen.append(lock.exists() and int(lock.read_text().split(":")[0]) == dbmod.os.getpid())
        return []

    monkeypatch.setattr(scheduler, "fire_due", spy)
    _runner(path)._fire_schedules(conn)

    assert seen == [True]


def test_an_idle_loop_does_not_take_the_lock(tmp_path, monkeypatch):
    """Nothing due, no lock: an engine asking twice a second must not contend with
    every other writer for nothing."""
    path = tmp_path / "w.db"
    c = dbmod.connect(path)
    dbmod.migrate(c)
    monkeypatch.setattr(dbmod, "write_lock",
                        lambda *a, **k: pytest.fail("took the lock with nothing due"))
    try:
        _runner(path)._fire_schedules(c)
    finally:
        c.close()


# ---- run-due -----------------------------------------------------------------

def _run_due_stubs(monkeypatch):
    monkeypatch.setattr(native, "_engine_listening", lambda port: False)
    monkeypatch.setattr(native, "_spawn_engine",
                        lambda port: pytest.fail("a skip queues nothing to run"))
    monkeypatch.setattr(cli, "load_manifest", lambda *a, **k: _Manifest())
    monkeypatch.setattr(cli, "RUN_DUE_LOCK_TIMEOUT_S", 0.3)


@pytest.mark.parametrize("missed", [MissedRunPolicy.RUN_WHEN_AVAILABLE.value,
                                    MissedRunPolicy.SKIP.value])
def test_run_due_skips_a_slot_another_app_held_on_its_next_tick(
        warehouse, other_process, monkeypatch, capsys, missed):
    """M1: the lock outlasts this tick's wait; the next tick, fifteen minutes on, finds it
    free and writes the skip -- never a late run, and never a silent re-arm."""
    path, conn = warehouse
    conn.execute("UPDATE schedule SET missed_run_policy = ?", (missed,))
    conn.commit()
    _run_due_stubs(monkeypatch)
    lock = _hold_as(path, other_process)

    assert cli.main(["run-due", "--db", str(path)]) == 0
    assert list_jobs(conn) == []
    assert "skipped this tick" in capsys.readouterr().out

    lock.unlink()
    later = utcnow() + timedelta(minutes=15)
    monkeypatch.setattr(scheduler, "utcnow", lambda: later)
    assert cli.main(["run-due", "--db", str(path)]) == 0

    assert [j["error_summary"] for j in list_jobs(conn)] == [LOCK_HELD_REASON]
    assert "no schedules were due" in capsys.readouterr().out
    assert not held_out_path(path).exists()


def test_run_due_and_the_loop_share_one_record(warehouse, other_process, monkeypatch):
    """What `run-due` held back, the engine's loop skips -- one rule, not two."""
    path, conn = warehouse
    _run_due_stubs(monkeypatch)
    lock = _hold_as(path, other_process)
    assert cli.main(["run-due", "--db", str(path)]) == 0
    lock.unlink()

    _runner(path)._fire_schedules(conn)

    assert [j["error_summary"] for j in list_jobs(conn)] == [LOCK_HELD_REASON]


@pytest.mark.parametrize("text", ["{not json", "[1, 2]",
                                  '{"1": {"slot": "yesterday", "why": "lock"}}',
                                  '{"1": {"slot": "2026-07-20T09:00:00Z", "why": "?"}}'])
def test_a_corrupt_record_is_refused_loudly_and_moved_aside(
        warehouse, monkeypatch, capsys, text):
    path, conn = warehouse
    _run_due_stubs(monkeypatch)
    monkeypatch.setattr(native, "_spawn_engine", lambda port: None)
    held_out_path(path).write_text(text, encoding="utf-8")

    with pytest.raises(HeldOutUnreadable):
        _runner(path)._fire_schedules(conn)
    assert Path(str(held_out_path(path)) + ".corrupt").read_text(encoding="utf-8") == text

    held_out_path(path).write_text(text, encoding="utf-8")
    assert cli.main(["run-due", "--db", str(path)]) == 1
    assert "could not be read" in capsys.readouterr().err
    assert list_jobs(conn) == [], "a refused record still let the tick write"

    assert cli.main(["run-due", "--db", str(path)]) == 0, "the next tick starts clean"
    assert len(_queued(conn)) == 1
