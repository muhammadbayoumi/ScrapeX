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

# ---- issue 796: and the pass that follows a requeue says it is not the first ----

def _entered(connection: sqlite3.Connection, ref: str, *, reached: int) -> None:
    """A job that has already run once and been requeued, which is the live shape.

    `started_at` SET AND `status` BACK TO `queued` is exactly what
    `reclaim_orphaned_jobs` leaves behind, and it is the state all three runners read
    and discard.
    """
    connection.execute(
        "UPDATE crawl_job SET started_at = ?, progress_done = ?, status = 'queued' "
        " WHERE job_ref = ?", ("2026-09-07T14:31:42Z", reached, ref))
    connection.commit()


def test_a_first_entry_says_nothing_and_reports_nothing(conn):
    """MOST ENTRIES ARE FIRST ONES. A line on every start would be noise, and noise on
    every start is how the line that matters stops being read."""
    ref = _job(conn, JobStatus.QUEUED)
    job = jobs.get_job(conn, ref)

    reached = jobs.note_a_re_entry(conn, job, unit="page pair(s)",
                                  consequence="nothing is fetched")

    assert reached == 0
    assert "not this job's first pass" not in _log(conn, ref), _log(conn, ref)


def test_a_re_entry_says_so_and_names_what_the_last_pass_reached(conn):
    """ISSUE 796. Two interpret jobs logged their opening preamble five times each on
    2026-09-07 while he was updating the engine, and every runner writes
    `progress_done = 0` at entry -- so his bar went back to zero eight times with no
    line anywhere explaining it. The panel is his only surface."""
    ref = _job(conn, JobStatus.QUEUED)
    _entered(conn, ref, reached=300)
    job = jobs.get_job(conn, ref)

    reached = jobs.note_a_re_entry(
        conn, job, unit="page pair(s)",
        consequence="Every pair is read from disk again")

    assert reached == 300
    said = _log(conn, ref)
    assert "not this job's first pass" in said, said
    assert "300 page pair(s)" in said, (
        f"the number he watched disappear is not in the line: {said}")
    # AND IT BLAMES NOTHING. `started_at` cannot tell a restart from a resume, and this
    # PR makes the resume the common path: a Resume button on every paused row.
    assert "restart" not in said, (
        f"the line names a cause `started_at` cannot know: {said}")
    assert "read from disk again" in said, (
        f"the caller's own consequence was dropped: {said}")


def test_the_count_survives_the_callers_reset(conn):
    """THE SNAPSHOT IS THE CONTRACT, NOT THE ORDER. `note_a_re_entry` reads the `job`
    dict it was handed; `_update` writes the row and cannot reach that dict. So the
    number stands whichever side of the caller's `progress_done = 0` the call sits on --
    and this drives the reset FIRST to prove it. What this refuses is a future version
    that re-reads the row, which would report every re-entry as having reached nothing:
    the same silence issue 796 is about, with an extra line."""
    ref = _job(conn, JobStatus.QUEUED)
    _entered(conn, ref, reached=620)
    job = jobs.get_job(conn, ref)
    # What the runners do immediately after the call under test.
    jobs._update(conn, job["job_id"], progress_done=0)
    conn.commit()

    reached = jobs.note_a_re_entry(conn, job, unit="page(s)",
                                   consequence="skipped rather than bought again")

    assert reached == 620, (
        "the number came from a re-read row rather than from the job handed in, so "
        "the caller's order stopped mattering and the line reports zero for ever")


def test_the_consequence_belongs_to_the_caller(conn):
    """AN INTERPRETATION ASKS THE SITE FOR NOTHING AND A SWEEP DOES NOT, so one sentence
    for both would be false for one of them. What is shared is that a re-entry must be
    said at all, and with the number."""
    interpret = _job(conn, JobStatus.QUEUED, source="muqawil_org")
    _entered(conn, interpret, reached=300)
    sweep = _job(conn, JobStatus.QUEUED, source="muqawil_org")
    _entered(conn, sweep, reached=620)

    jobs.note_a_re_entry(
        conn, jobs.get_job(conn, interpret), unit="page pair(s)",
        consequence="Every pair is read from disk again and the site is asked for "
                    "nothing")
    jobs.note_a_re_entry(
        conn, jobs.get_job(conn, sweep), unit="page(s)",
        consequence="The pages already stored under job-x are skipped rather than "
                    "bought again")

    assert "asked for nothing" in _log(conn, interpret)
    assert "skipped rather than bought again" in _log(conn, sweep)
    assert "asked for nothing" not in _log(conn, sweep), (
        "one kind's consequence reached the other kind's log")


def test_the_line_is_a_warning_like_the_sweep_line_above_it(conn):
    """It sits one line below `orphan sweep: ... is now queued` in his log, and a plain
    `info` under a warning reads as a different event rather than its consequence."""
    ref = _job(conn, JobStatus.QUEUED)
    _entered(conn, ref, reached=12)

    jobs.note_a_re_entry(conn, jobs.get_job(conn, ref), unit="cell(s)",
                         consequence="re-proved from disk")

    levels = [row["level"] for row in jobs.job_logs(conn, ref)
              if "not this job's first pass" in row["message"]]
    assert levels == ["warning"], levels

