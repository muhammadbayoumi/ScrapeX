"""The orphan sweep may not requeue a job this runtime is still running.

MEASURED ON HIS WAREHOUSE, 2026-09-06. One `dataset_interpret` job wrote its entry
preamble THREE times, read from `job_log_entry` in id order:

    9972  14:01:15  interpreting the stored pages of job-job_6eb28381bf56 ...
    9973  14:01:21  approve job-job_6eb28381bf56: 909 page pair(s) ...
    9974  14:06:51  interpreting the stored pages of ...          <- again
    9975  14:07:05  interpreting the stored pages of ...          <- again
    9976  14:07:16  approved 908 page(s): ...
    9980  14:07:16  interpretation finished in 6.0 min ...

That line is written once per entry to `run_dataset_interpret_job_once`, immediately
after it sets the job `preparing` with `progress_done=0`. So two extra entries landed
five and six minutes into a pass that had announced itself at 14:01:21 and did not report
until 14:07:16 -- and his progress bar went back to zero twice mid-run. Nothing was
corrupted that time because neither extra entry got past the preamble; a longer sweep
would have started a second concurrent pass over the same rows.

`reclaim_orphaned_jobs` IS THE ONLY MECHANISM THAT REQUEUES, and it moved every
`preparing`/`running`/`resuming` row to `queued` unconditionally -- no ownership test, no
age test. Its own docstring justified that with a startup premise: *"at startup any
in-flight job is ours and nobody else's -- nothing can be legitimately running."* True at
startup. `_loop` also calls it MID-LIFE, on the path that reopens a dropped connection.

AND THE CAUSE WAS NOT RECOVERABLE AFTER THE FACT. `clear_worker_failure` runs on every
healthy pass, so a loop that died and restarted leaves no trace by the next poll -- and
this warehouse holds no `runtime_worker_error` at all. Which of the two mechanisms fired
is therefore unproven, and the fix does not depend on knowing: `keep` closes the one this
runtime can see, and the sweep now NAMES every job it moves so the next occurrence is a
fact rather than a deduction.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod, jobs
from scrapex.vocab import JobControl, JobStatus

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(connection)
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _job(connection: sqlite3.Connection, status: JobStatus,
         source: str = "ELSEWEDYSHOP") -> str:
    ref = jobs.create_job(connection, [source])
    connection.execute("UPDATE crawl_job SET status = ? WHERE job_ref = ?",
                       (status.value, ref))
    connection.commit()
    return ref


def _status(connection: sqlite3.Connection, ref: str) -> str:
    return connection.execute(
        "SELECT status FROM crawl_job WHERE job_ref = ?", (ref,)).fetchone()[0]


def _log(connection: sqlite3.Connection, ref: str) -> str:
    return " | ".join(row["message"] for row in jobs.job_logs(connection, ref))


def test_a_job_this_runtime_is_running_is_left_alone(conn):
    """THE DEFECT, DIRECTLY. Requeueing it is what let `_dispatch` enter the runner a
    second time, and the runner's first act resets `progress_done` to zero."""
    mine = _job(conn, JobStatus.RUNNING)

    moved = jobs.reclaim_orphaned_jobs(conn, keep={mine})

    assert _status(conn, mine) == JobStatus.RUNNING.value, (
        "the sweep requeued a job this runtime is running, so the dispatch can start it "
        "again on a second thread over the same rows")
    assert moved == 0, moved


def test_it_says_it_left_it_and_why(conn):
    """A DECISION NOBODY CAN READ IS A DECISION THAT COSTS AN AFTERNOON NEXT TIME. The
    only evidence of the real incident was a preamble printed three times."""
    mine = _job(conn, JobStatus.RUNNING)

    jobs.reclaim_orphaned_jobs(conn, keep={mine})

    said = _log(conn, mine)
    assert "not an orphan" in said, (
        f"the sweep spared it in silence: {said!r}")
    assert mine in said, "the line does not name the job it decided about"


def test_a_job_no_runtime_is_behind_is_still_reclaimed(conn):
    """THE OTHER HALF, AND THE REASON THE SWEEP EXISTS. Without it a crash mid-crawl left
    a job `running` for ever and `_source_is_busy` blocked that source's schedules
    permanently with no error anywhere. A guard that spared everything would be worse
    than the defect it fixes."""
    orphan = _job(conn, JobStatus.RUNNING)

    moved = jobs.reclaim_orphaned_jobs(conn, keep=set())

    assert _status(conn, orphan) == JobStatus.QUEUED.value
    assert moved == 1, moved
    said = _log(conn, orphan)
    assert "no runtime behind it" in said, f"it moved the job in silence: {said!r}"
    assert "queued" in said


def test_startup_passes_nothing_and_therefore_reclaims_everything(conn):
    """`keep` DEFAULTS TO EMPTY, so the startup call is unchanged by construction rather
    than by argument. A default that spared anything would strand the exact jobs this
    function was written for."""
    left = {
        JobStatus.PREPARING: _job(conn, JobStatus.PREPARING, "ELSEWEDYSHOP"),
        JobStatus.RUNNING: _job(conn, JobStatus.RUNNING, "ELSEWEDYSHOP"),
        JobStatus.RESUMING: _job(conn, JobStatus.RESUMING, "ELSEWEDYSHOP"),
    }

    moved = jobs.reclaim_orphaned_jobs(conn)

    assert moved == 3, moved
    for ref in left.values():
        assert _status(conn, ref) == JobStatus.QUEUED.value


def test_the_two_stop_states_keep_their_own_targets(conn):
    """`pausing -> paused` and `cancelling -> cancelled` are the OWNER's decisions, not
    orphan recovery, and they must not be swept into `queued` by a rewrite of this
    function. A cancelled job that came back as queued would run work he stopped."""
    pausing = _job(conn, JobStatus.PAUSING)
    cancelling = _job(conn, JobStatus.CANCELLING)

    jobs.reclaim_orphaned_jobs(conn)

    assert _status(conn, pausing) == JobStatus.PAUSED.value
    assert _status(conn, cancelling) == JobStatus.CANCELLED.value
    finished = conn.execute(
        "SELECT finished_at FROM crawl_job WHERE job_ref = ?", (cancelling,)).fetchone()[0]
    assert finished, "a cancelled job was left with no finish time"


def test_a_kept_job_keeps_its_control_word_too(conn):
    """The sweep clears `control` on everything it moves. A job it LEAVES must keep the
    pause or cancel the owner asked for -- clearing that would swallow a stop he pressed
    while the sweep happened to run."""
    mine = _job(conn, JobStatus.RUNNING)
    conn.execute("UPDATE crawl_job SET control = ? WHERE job_ref = ?",
                 (JobControl.CANCEL.value, mine))
    conn.commit()

    jobs.reclaim_orphaned_jobs(conn, keep={mine})

    held = conn.execute("SELECT control FROM crawl_job WHERE job_ref = ?",
                        (mine,)).fetchone()[0]
    assert held == JobControl.CANCEL.value, (
        "the sweep cleared a cancel the owner pressed, on a job it did not even move")


def test_the_reopen_path_passes_what_it_is_running(conn):
    """READ OFF THE SOURCE, and the alternative is worse: reaching that branch needs a
    connection that fails to reopen and then succeeds, mid-poll, with a job thread alive.
    A test that staged all of it would fail for a dozen reasons unrelated to the one line
    that matters. What matters is that the mid-life call names the running set and the
    startup call does not."""
    source = (ROOT / "scrapex" / "jobs.py").read_text(encoding="utf-8")

    assert "reclaim_orphaned_jobs(conn, keep=set(self._running))" in source, (
        "the reopen path still sweeps without saying what it is running, which is the "
        "call that can requeue a live job")
    assert "reclaim_orphaned_jobs(conn)     # a previous runtime may have died" in source, (
        "the startup call no longer reclaims everything, which is what it is for")
    assert source.count("reclaim_orphaned_jobs(") == 4, (
        "a call site was added or removed and this guard was not told: every one of them "
        "has to have decided about `keep`")
