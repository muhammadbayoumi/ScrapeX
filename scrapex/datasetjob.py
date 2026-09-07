"""One interpretation pass over stored evidence, driven as a job so the panel can start it.

WHAT WAS ACTUALLY WRONG, MEASURED ON HIS WAREHOUSE. His muqawil listing crawl finished
2026-09-06T05:01:44Z with 56 of 56 cells and zero errors, having stored 6,713 pages. Zero
of them had been interpreted; the newest `generic_ingestion` row was five days OLDER than
the crawl, and the dataset still held the 17,304 rows it held before the crawl started.
The step that turns evidence into rows is `contractors.approve`, and it could be reached
from `scrapex contractors --approve` and from nowhere else: no API route, no job kind, no
control in the panel. `R-81` says the panel is his only interface, so a crawl of 6,713
pages produced a harvest only a terminal could convert.

WHY A JOB KIND RATHER THAN A STAGE OF THE CRAWL. Folding interpretation into the crawl was
the cheaper answer and it is the wrong one: interpretation fails on its own terms -- a
parser that cannot read a page, a schema that moved -- and a failure reported as the
crawl's would send the next session looking at the network. It is also a thing worth doing
WITHOUT a crawl: the evidence for a run that finished days ago is still on disk, and
re-reading it costs no request. Two jobs, two verdicts.

WHAT IT DOES NOT DUPLICATE. Not one line of interpreting lives here. `contractors.approve`
is the same function `--approve` calls, and this module is the three things a job adds to
it: its report reaches the job log instead of a console, progress is counted in page
PAIRS, and the owner's pause or cancel is applied between two of them.

A PAGE BOUNDARY IS SAFE, AND A CELL BOUNDARY WAS NOT. The crawl stops between cells
because a cell's completeness proof spans many pages, so a cell cut in half has fetched
pages and proved nothing. Interpretation has no such span: each page pair is written on its
own, so stopping between two leaves every earlier one interpreted and nothing half-written.

AND IT TAKES NO POLITENESS RESERVATION, which is the one place it deliberately differs
from `directoryjob`. `_CrawlAdmission` exists to stop two jobs asking one site for pages at
once; this job asks nobody for anything. Holding a host lane here would block a real crawl
of that site for the length of an interpretation that could not have collided with it.
"""
from __future__ import annotations

import sqlite3
import time

from . import contractors, directories
from .features import FeatureKey, is_enabled
from .payload import utc_now_iso
from .vocab import JobControl, JobStage, JobStatus, LogLevel

#: The kind this module runs. Named once; `jobs.SPECIALISED_RUNNERS` reads it so the
#: string cannot be spelled two ways in two files, and `db/engine/schema.sql`'s CHECK
#: carries the same word -- widened by migration 0018.
JOB_KIND = "dataset_interpret"

#: Page pairs between progress writes. Interpretation is fast per page and a write per
#: page would be thousands of transactions on his 6,713; a write every fifty keeps the
#: card within a second or two of the truth for a run of any length.
#:
#: AT MODULE SCOPE SO A TEST CAN VARY IT. The heartbeat guard one module over was written
#: against a local and the monkeypatch did nothing -- five of six beats were silently
#: throttled and the guard passed.
BEAT_EVERY_PAIRS = 50


class NothingToInterpret(LookupError):
    """This source has no stored evidence that a crawl left behind.

    REFUSED RATHER THAN REPORTED AS SUCCESS. A job that interpreted nothing and finished
    green is indistinguishable from one that interpreted everything, and the owner would
    read the second where the first happened.
    """


def latest_crawl_run_ref(conn: sqlite3.Connection, source_key: str) -> tuple[str, int]:
    """The run ref of this source's most recent crawl, and how many READINGS it stored.

    CHOSEN HERE AND SAID OUT LOUD, rather than asked of the caller. The panel would
    otherwise have to know how a run ref is built, which is `directoryjob`'s private
    business -- and the day that changes, the panel would be starting jobs against a ref
    nothing stored under. The runner logs which run it chose and how many pages it holds,
    so the choice is auditable rather than hidden.

    NEWEST BY JOB, NOT BY PAGE. Ordering by `captured_at` would pick a run that stored one
    late page over a run that stored six thousand, because a resumed crawl writes under
    the ref of the job that started it. The job order is the run order.

    THE SECOND VALUE IS SNAPSHOT ROWS, NOT PAGES, AND THE CALLER MUST SAY SO. Measured on
    the owner's warehouse for run `job-job_6eb28381bf56`: 6,713 snapshot rows, 1,818
    distinct URLs, 909 page pairs after collapsing the en/ar halves -- because the
    listing reorders and the sweep reads it once per pass, storing the same URLs again
    each time (1,818 / 1,546 / 1,260 / 1,138 / 761 / 190 across six passes).

    SO THIS NUMBER AND `approve`'S ARE BOTH TRUE AND MEASURE DIFFERENT THINGS. They were
    printed six seconds apart under the same words -- "page(s) on disk" -- and read as
    5,804 pages lost between one line and the next. Nothing was lost; the label was.
    """
    rows = conn.execute(
        "SELECT j.job_ref, count(s.page_snapshot_id) AS pages "
        "  FROM crawl_job AS j "
        "  JOIN generic_page_snapshot AS s "
        "    ON s.crawl_run_ref = 'job-' || j.job_ref "
        "    OR s.crawl_run_ref LIKE 'job-' || j.job_ref || '-%' "
        " WHERE j.job_kind = ? AND j.source_keys LIKE ? "
        # AN INNER JOIN IS THE FILTER, and a `HAVING pages > 0` beside it was dead code
        # that read as the guard -- a mutation removing it changed no verdict, because a
        # crawl that stored nothing produces no row to count in the first place. Said
        # here rather than left as a clause somebody trusts.
        " GROUP BY j.job_id "
        " ORDER BY j.job_id DESC LIMIT 1",
        ("directory_crawl", f'%"{source_key}"%')).fetchone()
    if rows is None:
        raise NothingToInterpret(
            f"{source_key!r} has no crawl that stored pages, so there is nothing to "
            "interpret. Run a crawl first")
    return f"job-{rows[0]}", int(rows[1])


def run_dataset_interpret_job_once(conn: sqlite3.Connection, job_ref: str,
                                   admission=None) -> dict:
    """Interpret one source's stored evidence to completion, or to a control boundary.

    Synchronous and connection-injected, exactly like `jobs.run_job_once` and
    `directoryjob.run_directory_crawl_job_once`, so the thread loop in `JobRunner` is the
    only thing that needs a thread.

    `admission` IS ACCEPTED AND DELIBERATELY UNUSED. The dispatch table hands every
    specialised runner the same three arguments, and taking it while ignoring it is
    honest about a contract; refusing it would make this kind the one entry the table
    needs a condition for. The module docstring says why holding a lane here would be
    wrong rather than merely unnecessary.
    """
    from . import jobs

    job = jobs.get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind") != JOB_KIND:
        raise ValueError(
            f"job {job_ref!r} is a {job.get('job_kind')!r}, not a {JOB_KIND!r}")
    if job["status"] in {status.value for status in jobs.TERMINAL_JOB_STATUSES}:
        # ALREADY DECIDED. A cancelled or finished job that ran again would rewrite rows
        # the owner has already stopped, which is the one thing a re-pick must never do.
        return job

    keys = list(job["source_keys"])
    if len(keys) != 1:
        # ONE SOURCE PER JOB, AND THE REASON IS THE PROGRESS FIGURE, the same reason the
        # crawl gives: page pairs are the denominator and two sources have different
        # ones, so a bar that mixes them cannot say what is left of either.
        raise ValueError(
            f"a {JOB_KIND!r} job interprets exactly one source and {job_ref!r} names "
            f"{len(keys)}: {keys}")
    source_key = keys[0]
    if source_key not in directories.BUILDERS:
        raise NothingToInterpret(
            f"{source_key!r} is not a directory this build can interpret. Known: "
            f"{sorted(directories.BUILDERS)}")

    if not is_enabled(FeatureKey.GENERIC_EXTRACTION):
        # THE SAME GATE THE COMMAND LINE STANDS BEHIND, and it refuses rather than
        # skipping for the reason `contractors.validate` gives in terms: a run that
        # quietly did nothing looks like a crawl with nothing to interpret, and those
        # are opposite facts.
        raise NothingToInterpret(
            "generic extraction is disabled in this build (scrapex/features.py), so "
            "interpreting would write rows the feature manifest says are not available. "
            "Nothing was read or written")

    directory = directories.get(source_key)
    # THE REF THE CRAWL STORED UNDER, resolved from the job history rather than rebuilt
    # from a convention. An explicit ref in the checkpoint wins, so a caller that knows
    # exactly which run it means can say so.
    asked = (job.get("checkpoint") or {}).get("run_ref")
    if asked:
        run_ref, pages = asked, 0
    else:
        run_ref, pages = latest_crawl_run_ref(conn, source_key)

    jobs._update(conn, job["job_id"], status=JobStatus.PREPARING.value,
                 stage=JobStage.PREPARING.value, progress_done=0,
                 current_source_key=source_key, last_heartbeat_at=utc_now_iso(),
                 **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    jobs.append_log(
        conn, job["job_id"],
        f"{directory.display_name}: interpreting the stored pages of {run_ref}"
        # NAMED FOR WHAT IT COUNTS. `pages` is snapshot ROWS, which a repeated pass
        # inflates well above the number of distinct pages; `approve` reports the page
        # pairs it will actually read, and the two shared this line's wording.
        + (f" — {pages:,} stored reading(s) on disk" if pages else "")
        + ". Nothing is fetched", source_key=source_key)
    conn.commit()

    done = {"pairs": 0, "total": 0}
    stopped: list[str] = []

    def note(line: str) -> None:
        """One line of the interpreter's own report, into the job log.

        THROUGH `contractors.say`'S SINK rather than by re-implementing its report. The
        interpreter already says what it made, recovered, reparsed and refused; a job that
        summarised it again would be a second account of one pass, free to disagree.
        """
        jobs.append_log(conn, job["job_id"], line, source_key=source_key)
        conn.commit()

    def page_closed(index: int, total: int) -> bool:
        """Called before each page pair. `True` asks the interpreter to stop here.

        ON THE JOB'S OWN THREAD, unlike the crawl's equivalent: `approve` has no worker
        pool, so there is no second thread and no second connection. If it ever grows one,
        this needs `directoryjob.for_writing`'s treatment and the guard there says why.
        """
        done["total"] = total
        done["pairs"] = index
        # THE FIRST CALL ALWAYS WRITES, so `progress_total` reaches the card before the
        # work rather than after it. An interpretation of 6,713 pages that showed 0/0
        # until it finished would read as a job that never started.
        if index and index % globals()["BEAT_EVERY_PAIRS"]:
            return False
        jobs._update(conn, job["job_id"], status=JobStatus.RUNNING.value,
                     stage=JobStage.FETCHING.value, progress_done=index,
                     progress_total=total, last_heartbeat_at=utc_now_iso())
        conn.commit()
        current = jobs.get_job(conn, job_ref)
        control = jobs._control_of(conn, job["job_id"])
        if control == JobControl.PAUSE.value:
            jobs._update(conn, job["job_id"], status=JobStatus.PAUSED.value,
                         control=JobControl.NONE.value, stage=None,
                         last_heartbeat_at=utc_now_iso())
            jobs.append_log(
                conn, job["job_id"],
                f"paused between pages, {index:,} of {total:,} interpreted. Resuming "
                f"re-reads {run_ref} and recognises what is already in",
                source_key=source_key)
            conn.commit()
            stopped.append(JobStatus.PAUSED.value)
            return True
        if control == JobControl.CANCEL.value:
            jobs._finish(conn, job["job_id"], JobStatus.CANCELLED, None)
            stopped.append(JobStatus.CANCELLED.value)
            return True
        # `current` IS READ AND USED, not read and discarded: a job the worker has been
        # told to drop its database for is a job whose next page must not open.
        return bool(current is None)

    started = time.monotonic()
    try:
        with contractors.lines_go_to(note):
            contractors.approve(conn, directory, run_ref,
                                between_pages=page_closed)
    except contractors.CrawlStopped:
        # NOT AN ERROR, AND NOT SILENT EITHER. `page_closed` has already written the
        # status and said where it stopped.
        return jobs.get_job(conn, job_ref)
    except Exception as exc:
        jobs.append_log(conn, job["job_id"], f"failed: {exc}",
                        level=LogLevel.ERROR, source_key=source_key)
        jobs._finish(conn, job["job_id"], JobStatus.FAILED, str(exc))
        raise

    if stopped:
        return jobs.get_job(conn, job_ref)
    jobs.append_log(
        conn, job["job_id"],
        f"interpretation finished in {(time.monotonic() - started) / 60:.1f} min, "
        f"{done['total']:,} page pair(s) read from disk. No request was made",
        source_key=source_key)
    jobs._update(conn, job["job_id"], progress_done=done["total"],
                 progress_total=done["total"])
    jobs._finish(conn, job["job_id"], JobStatus.COMPLETED, None)
    return jobs.get_job(conn, job_ref)
