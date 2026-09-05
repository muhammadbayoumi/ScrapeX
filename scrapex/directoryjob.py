"""One directory listing crawl, driven as a job so the panel can start it.

WHY THIS IS A JOB KIND AND NOT A WIDER `capture_source`. `REQ-45` made `POST /api/jobs`
queue `muqawil_org`, and the worker then handed it to `capture_source` -- the price path,
whose `CaptureResult` carries `observations`, `duplicates`, `products`, `variants` and
`attributes`. A contractor listing crawl produces none of those. It produces stored pages,
a per-cell completeness proof, arrivals and departures. Forcing it through that result
would mean either five zeroes reported as a success or five fields renamed to mean
something else on one source, and `docs/BACKLOG.md` has a name for the second.

`organization_enrichment` already established the alternative and it is the one followed
here: a job KIND with its own runner, reached from `jobs.runner_for`, sharing the job
table, the log, the progress fields and the pause/cancel controls and nothing else.

WHAT IT DOES NOT DUPLICATE. Not one line of crawling lives here. `contractors.crawl` is
the same function `scrapex contractors --crawl` calls -- «خلى الشغل dry» -- and this module
is the three things a job needs that a command line does not: the log gets the lines
instead of a console, progress is counted in cells, and the owner's pause or cancel is
applied at a cell boundary.

A CELL BOUNDARY IS THE ONLY SAFE PLACE, for the reason `jobs.py` states about sources:
a cell's completeness proof compares an id sequence against a witness read of page one, so
a cell interrupted halfway has fetched pages and proved nothing. Stopping between cells
keeps every closed cell's proof and loses only the pages of the one in flight -- and those
are already on disk, so a resume under the same `--run-ref` skips them.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing, nullcontext

from . import contractors, directories
from . import db as dbmod
from .payload import utc_now_iso
from .vocab import JobControl, JobStage, JobStatus, LogLevel

#: The kind this module runs. Named once; `jobs.SPECIALISED_RUNNERS` reads it so the
#: string cannot be spelled two ways in two files.
JOB_KIND = "directory_crawl"

#: Seconds between requests. The panel offers no pace control, so this is the pace a
#: crawl he starts from the extension runs at, and it is the CLI's own default rather
#: than a number chosen here -- `R-21` and `SR-8` are about the rate, and a second
#: opinion about it living in a second file is how two front doors start being polite
#: to different degrees.
DEFAULT_PACE_S = contractors.DEFAULT_PACE_S

#: Seconds between heartbeats while a cell is being fetched. A request takes about a
#: second at `DEFAULT_PACE_S`, so this is roughly one small write every twenty pages --
#: often enough that the job card is never more than twenty seconds behind, rare enough
#: that it is not a write per request.
#:
#: AT MODULE SCOPE BECAUSE IT WAS A LOCAL AND THAT HID IT. A tuning number inside the
#: function cannot be varied by a test or seen by anyone reading the module, and the guard
#: for the beat found exactly that: it set the interval to zero, nothing changed, and five
#: of six fetches were silently throttled.
BEAT_EVERY_S = 20.0

#: The setting that says how many cells one directory crawl reads at once.
#:
#: THE KEY IS NAMED HERE AND THE NUMBER IS NOT. `settings.SETTINGS` carries the shipped
#: number and the reason for it, so changing the default is one edit in one file; a
#: constant here beside a duplicate of itself in the catalogue is two places for one
#: fact, and the panel field would have been a third.
WORKERS_SETTING = "directory_crawl_workers"

#: Refused above this however the setting is written. A pool wider than the partition is
#: threads queued on a pace lock, and a mistyped 600 should not open 600 connections to a
#: 2 GB warehouse. The panel input carries the same ceiling; this is the one that binds.
MAX_WORKERS = 8


def workers_for(conn: sqlite3.Connection) -> int:
    """How many cells this crawl reads at once, from the setting, clamped.

    READ FROM THE SETTINGS TABLE AND CLAMPED HERE, for the reason `jobs.job_capacity`
    gives about `crawl_parallel_sources`: one definition, read by the thing that
    enforces it, so nothing can promise a concurrency the crawl will not deliver.

    A BAD VALUE IS THE SHIPPED DEFAULT, NOT A FAILURE. A crawl that refused to start
    because the setting held the word "six" would be a mistyped number taking the
    collection offline, and the number is typed into a panel field that will happily
    submit an empty string.
    """
    from . import settings

    spec = settings.SETTINGS.get(WORKERS_SETTING)
    # ONE IF THE KEY IS GONE, which is a build that deleted the setting rather than a
    # database that never had it -- so the safe reading is the old behaviour, not a
    # concurrency nothing declared.
    shipped = int(spec.default) if spec is not None else 1
    try:
        asked = settings.get(conn, WORKERS_SETTING)
    except (sqlite3.DatabaseError, settings.UnknownSettingError):
        return shipped
    try:
        return max(1, min(int(asked), MAX_WORKERS))
    except (TypeError, ValueError):
        return shipped


class NotADirectory(LookupError):
    """This job names a source that is not a directory this build can crawl.

    REFUSED RATHER THAN FALLEN BACK TO THE PRICE PATH. A job queued as a directory
    crawl whose key `directories.BUILDERS` does not know is a mistake somewhere above
    this module, and running the wrong collector over it would report a success about
    a source nobody crawled.
    """


def run_directory_crawl_job_once(conn: sqlite3.Connection, job_ref: str,
                                 admission=None) -> dict:
    """Execute one directory listing crawl to completion, or to a control boundary.

    Synchronous and connection-injected, exactly like `jobs.run_job_once`, so the
    thread loop in `JobRunner` is the only thing that needs a thread.

    `admission` IS THE CROSS-JOB POLITENESS GATE AND IT IS HELD AROUND THE CRAWL. Without
    it this runner crawled outside the per-host reservation, so two jobs for one directory
    -- a scheduled one and a hand-started one, or two presses of the panel's button -- ran
    concurrently with their own fetcher at `DEFAULT_PACE_S` each and doubled the request
    rate on that site. His `job_capacity` is 3, so it was live rather than theoretical.
    `OP-128`, and `_CrawlAdmission`'s own docstring calls this "the safety property the
    task calls the whole risk".

    HELD HERE RATHER THAN AT THE DISPATCH, deliberately: only this function knows when the
    first request goes out and when the last one returns, and a reservation taken around
    the whole job would hold a site against other jobs through the sizing, the validator
    replay and the coverage report -- none of which asks the site for anything.

    `None` ADMITS ITSELF, which is the same default `run_job_once` has: the CLI, every
    test and the sequential path are unchanged.
    """
    from . import jobs

    job = jobs.get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind") != JOB_KIND:
        raise ValueError(
            f"job {job_ref!r} is a {job.get('job_kind')!r}, not a {JOB_KIND!r}")
    if job["status"] in {status.value for status in jobs.TERMINAL_JOB_STATUSES}:
        # ALREADY DECIDED. A cancelled or finished job that ran again would crawl a
        # site the owner has already stopped, which is the one thing a re-pick must
        # never do.
        return job

    keys = list(job["source_keys"])
    if len(keys) != 1:
        # ONE DIRECTORY PER JOB, AND THE REASON IS THE PROGRESS FIGURE. Cells are the
        # denominator, two directories have different cell counts, and a bar that
        # mixes them cannot say what is left of either. The route refuses a mixed
        # queue; this refuses it again, because the route is not the only caller.
        raise ValueError(
            f"a {JOB_KIND!r} job crawls exactly one directory and {job_ref!r} names "
            f"{len(keys)}: {keys}")
    source_key = keys[0]
    if source_key not in directories.BUILDERS:
        raise NotADirectory(
            f"{source_key!r} is not a directory this build can crawl. Known: "
            f"{sorted(directories.BUILDERS)}")

    directory = directories.get(source_key)
    # THE REF IS THE JOB'S, so a resume under the same job skips the pages it already
    # stored -- `already_stored` is scoped to the ref, and the job ref is the only
    # label that is stable across a pause and a re-pick.
    run_ref = f"job-{job_ref}"
    cells = len(directory.partition().cells())
    #: The warehouse this job connection is open on, asked of the connection itself
    #: rather than threaded in as a parameter -- the runner contract is
    #: `(conn, job_ref, admission)` and a fourth argument for a path the connection
    #: already knows would be a second place for it to be wrong.
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    # A POOL NEEDS A FILE ON DISK. `PRAGMA database_list` reports an empty name for an
    # in-memory database, and `dbmod.connect(":memory:")` called from a worker would be
    # a DIFFERENT, empty database -- so the crawl would store its pages where nothing
    # can read them and report a success over it. An in-memory run therefore stays
    # sequential, which is also what every existing test of this runner gets.
    workers = workers_for(conn) if db_file else 1

    jobs._update(conn, job["job_id"], status=JobStatus.PREPARING.value,
                 stage=JobStage.PREPARING.value, progress_total=cells,
                 progress_done=0, current_source_key=source_key,
                 last_heartbeat_at=utc_now_iso(),
                 **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    jobs.append_log(conn, job["job_id"],
                    f"{directory.display_name}: listing crawl of {cells:,} cell(s) "
                    f"as {run_ref}", source_key=source_key)
    if workers > 1:
        # SAID, BECAUSE HE CANNOT SEE IT ANY OTHER WAY. A pool is invisible from the job
        # card -- the cells still close one at a time -- and a crawl that suddenly runs
        # six times faster with nothing saying why is a crawl he cannot audit. The
        # sentence names the RATE as well as the width, because the rate is the part
        # `R-21` is about and the part that has not changed.
        jobs.append_log(
            conn, job["job_id"],
            f"  {workers} cell(s) at once. The request RATE is unchanged at one per "
            f"{DEFAULT_PACE_S:g}s -- what overlaps is the waiting, not the asking",
            source_key=source_key)
    conn.commit()

    done = {"cells": 0}
    stopped: list[str] = []
    # BUILT BEFORE THE CLOSURES THAT READ IT. `cell_closed` reports this fetcher's request
    # count, and a closure resolves its names at CALL time -- so building the fetcher
    # further down worked, and worked BY ORDERING. Moving `make_fetch` below the crawl
    # would then be a `NameError` on the first cell, hours into a run that had already
    # fetched real pages. Structural beats incidental.
    fetcher, fetch = contractors.make_fetch(DEFAULT_PACE_S)

    def beating(url: str) -> str:
        """One page, and a heartbeat if one is due.

        THE JOB'S HEARTBEAT WAS WRITTEN AT CELL BOUNDARIES ONLY, and a cell can be long:
        the fourth cell of his 2026-09-03 run fetched for over forty minutes, so the job
        card read "reported 40 min ago" while it was storing hundreds of pages.
        `jobs.py`'s own comment above `JOB_HEARTBEAT_MAX_AGE_S` names this defect at a
        narrower window -- *"judging a job by the loop's 30s window is what made a working
        crawl look dead"* -- and a boundary-only beat reintroduced it at fifteen minutes.
        `OP-130`.

        AFTER THE FETCH, NOT BEFORE, because the claim is that a request COMPLETED. A beat
        written before would keep a hung request looking healthy, which is the one state
        worth seeing.

        ON ITS OWN CONNECTION, for `record_worker_failure`'s stated reason one file over:
        a heartbeat written inside the crawl's transaction is a heartbeat that can be
        rolled away with whatever the crawl was doing -- and it would commit the crawl's
        pending work on a schedule the crawl did not choose.
        """
        text = fetch(url)
        now = time.monotonic()
        if now - beat_at[0] < globals()["BEAT_EVERY_S"]:
            return text
        beat_at[0] = now
        try:
            own = sqlite3.connect(db_file, timeout=5.0)
            try:
                own.execute("PRAGMA busy_timeout = 5000")
                own.execute(
                    "UPDATE crawl_job SET last_heartbeat_at = ? WHERE job_id = ?",
                    (utc_now_iso(), job["job_id"]))
                own.commit()
            finally:
                own.close()
        except sqlite3.Error:
            # A HEARTBEAT MAY NOT END A CRAWL. It is a record OF the work, not the work,
            # and the same rule `contractors.say` states about a log line: lose the beat,
            # never the run.
            pass
        return text

    beat_at = [0.0]

    #: The thread the job was handed to. `for_writing` compares against it, so the
    #: comparison is with THIS run rather than with whatever the main thread happens to
    #: be -- the job loop runs every job in a thread of its own.
    job_thread = threading.get_ident()

    def for_writing():
        """The connection this callback writes on: the job connection, or a fresh one.

        THE ONE CHANGE THAT MADE A POOL POSSIBLE HERE. `crawl_partition` calls `on_cell`
        -- and so `contractors.say`s sink and `between_cells` -- in the thread that
        closed the cell, and `sqlite3` refuses a connection from a thread it was not
        created on. Every write below went through the job connection, so the first cell
        to close inside a worker would have raised `ProgrammingError` from inside the job
        log writer, hours into a real crawl.

        BY THREAD, AND NOT BY `workers > 1`, WHICH IS WHAT MEASUREMENT CHANGED. The
        first version took a fresh connection whenever the pool was wide, and two
        directory jobs then spent 11.75 s doing 0.7 s of work. A thread dump two seconds
        in showed the crawl blocked inside its own `jobs.append_log`: `contractors.crawl`
        writes `validator_store.save(conn, ...)` on the job connection and commits only
        after its closing report, so a log line written on a SECOND connection to the
        same file waited out the whole `busy_timeout` against an uncommitted write of its
        own making. A connection deadlocked against its sibling, and the only symptom is
        a five-second stall and then `database is locked`.

        SO THE JOB THREAD KEEPS THE JOB CONNECTION -- sharing that transaction rather
        than fighting it -- and only a worker takes its own. That also makes the
        sequential path identical by construction rather than by argument: with one
        worker nothing runs off this thread, so every write goes exactly where it went
        before.
        """
        if threading.get_ident() == job_thread:
            return nullcontext(conn)
        return closing(dbmod.connect(db_file))

    def note(line: str) -> None:
        """One line of the crawl's own report, into the job log.

        WRITTEN THROUGH `contractors.say`'S SINK rather than by re-implementing its
        report. The crawl already says what it saw -- the registered scope, the
        validators it replayed, each cell's outcome, arrivals and departures -- and a
        job that logged its own summary instead would be a second account of the same
        run, free to disagree with the console's.
        """
        with for_writing() as own:
            jobs.append_log(own, job["job_id"], line, source_key=source_key)
            # COMMITTED HERE, WHERE IT USED TO RIDE ON THE NEXT `cell_closed`. A line
            # written on a connection that is then closed is a line that was rolled
            # back, and the report the crawl writes IS the job log.
            own.commit()

    def cell_closed() -> bool:
        """Called between cells. `True` asks the crawl to stop here.

        `between_cells`, NOT `on_cell`: `crawl_partition` already has an `on_cell`, and
        it is the per-cell report hook rather than a stop question.

        The heartbeat and the progress write happen here too, because between cells is
        also the only moment at which `progress_done` is a fact rather than a guess.
        """
        if stopped:
            # ALREADY STOPPED BY AN EARLIER CELL, AND THIS IS A POOL DEFECT WITH A
            # SEQUENTIAL PATH THAT NEVER HAD IT. When a pause is honoured, the cells that
            # were already in flight still close -- `stopping` in `crawl_partition` keeps
            # the UNSTARTED ones from running, and nothing can un-start the others -- so
            # their progress write would put `running` back over `paused`. A job that says
            # it is running with nothing running is exactly the state
            # `test_a_killed_engine_does_not_leave_a_job_claiming_to_run` exists for, and
            # from the panel it is a crawl he cannot resume because it never stopped.
            #
            # `True` RATHER THAN `False`: the answer to "may this run continue?" is still
            # no, so the cell that asked raises too and its worker stops as well.
            return True
        done["cells"] += 1
        # NOT LOCKED, AND IT DOES NOT NEED TO BE. `crawl_partition` calls `on_cell`
        # inside one lock, and `contractors.crawl` asks `between_cells` from inside
        # `on_cell` -- so however wide the pool, exactly one thread is in this function
        # at a time. That is also what makes `done["cells"]` a count rather than a race.
        with for_writing() as own:
            jobs._update(own, job["job_id"], status=JobStatus.RUNNING.value,
                         stage=JobStage.FETCHING.value, progress_done=done["cells"],
                         last_heartbeat_at=utc_now_iso())
            # AND THE REQUEST COUNT, HERE RATHER THAN ONLY AT THE END. It was written
            # once in `finally`, so the panel showed `requests: 0` beside `cells 2/56`
            # for hours -- two numbers on one card contradicting each other, on the
            # surface he watches. `OP-130`. The price path updates as it goes and its
            # vocabulary is already `waiting` / `fetching` / `done`.
            #
            # AT THE BOUNDARY, because mid-cell `requests_count` is a number in motion
            # and this is the one point where every figure on that card agrees with the
            # others. With a pool it is also the only point at which it is READ from one
            # thread rather than incremented by several, which is why it is taken here
            # and not inside the fetch.
            jobs.record_source_fetch(
                own, job["job_id"], source_key,
                requests=int(getattr(fetcher, "requests_count", 0) or 0),
                state="fetching")
            own.commit()
            current = jobs.get_job(own, job_ref)
            control = jobs._control_of(own, job["job_id"])
            if control == JobControl.PAUSE.value:
                jobs._update(own, job["job_id"], status=JobStatus.PAUSED.value,
                             control=JobControl.NONE.value, stage=None,
                             last_heartbeat_at=utc_now_iso())
                jobs.append_log(
                    own, job["job_id"],
                    f"paused at a cell boundary, {done['cells']:,} of {cells:,} closed. "
                    f"Resuming under {run_ref} skips the pages already stored",
                    source_key=source_key)
                own.commit()
                stopped.append(JobStatus.PAUSED.value)
                return True
            if control == JobControl.CANCEL.value:
                jobs._finish(own, job["job_id"], JobStatus.CANCELLED, None)
                stopped.append(JobStatus.CANCELLED.value)
                return True
            # `current` IS READ AND USED, not read and discarded: a job the worker has
            # been told to drop its database for is a job whose next cell must not open.
            return bool(current is None)

    started = time.monotonic()
    # ONE DEFINITION OF A HOST, taken from `jobs` rather than written again here.
    # `_host_of`'s docstring names the crack a second derivation would open: a source
    # filed under one host name for grouping and another for reservation is two jobs
    # crawling a site together. The fallback is the source key, which is unique to this
    # source, so two unresolvable sources can never share a reservation.
    host = jobs.host_of_url(directory.base_url, source_key)
    admit = admission.lane(host) if admission is not None else nullcontext()

    def a_connection() -> sqlite3.Connection:
        """One connection for one worker, opened IN that worker.

        THE FACTORY IS PASSED, NOT A CONNECTION, for the reason
        `partitioncrawl._run_and_close` states in terms: calling it on the submitting
        thread and handing the result over raises on the `close()`, after the cell has
        already been crawled.

        THE JOB DATABASE, NOT THE DEFAULT ONE. `contractors.py` builds its factory from
        `DatabaseRegistry.defaults()`, which is right for a command line and wrong here
        -- a job running against a test or a second warehouse would have its cells
        crawled into the default one. This asks the job connection where it is.
        """
        return dbmod.connect(db_file)

    try:
        with admit, contractors.lines_go_to(note):
            contractors.crawl(conn, directory, beating, fetcher, run_ref,
                              contractors.DEFAULT_MAX_ATTEMPTS,
                              between_cells=cell_closed, workers=workers,
                              connect=a_connection if workers > 1 else None)
    except contractors.CrawlStopped:
        # NOT AN ERROR, AND NOT SILENT EITHER. The crawl was asked to stop by
        # `cell_closed`, which has already written the status and said why.
        return jobs.get_job(conn, job_ref)
    except Exception as exc:
        jobs.append_log(conn, job["job_id"], f"failed: {exc}",
                        level=LogLevel.ERROR, source_key=source_key)
        jobs._finish(conn, job["job_id"], JobStatus.FAILED, str(exc))
        raise
    finally:
        fetcher.close()
        jobs.record_source_fetch(
            conn, job["job_id"], source_key,
            requests=int(getattr(fetcher, "requests_count", 0) or 0),
            state="done" if not stopped else "stopped")
        conn.commit()

    if stopped:
        return jobs.get_job(conn, job_ref)
    jobs.append_log(
        conn, job["job_id"],
        f"listing crawl finished in {(time.monotonic() - started) / 60:.1f} min, "
        f"{getattr(fetcher, 'requests_count', 0):,} request(s). This is the LISTING "
        "phase; the profile pages are a separate collector",
        source_key=source_key)
    jobs._update(conn, job["job_id"], progress_done=cells)
    jobs._finish(conn, job["job_id"], JobStatus.COMPLETED, None)
    return jobs.get_job(conn, job_ref)
