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

import json
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


#: The job kinds that COLLECT pages for a directory, and therefore the kinds an
#: interpretation can have something to read.
#:
#: NAMED IN ONE PLACE, AND ISSUE 792 IS WHY. The same filter lived in
#: `latest_crawl_run_ref` and in the panel's interpret badge, and only the first was
#: widened when a profile sweep's pages turned out to be unreachable -- so the button
#: worked and the card that is supposed to say a press is owed stayed silent. Two
#: readers, one fact, and changing one of them is the shape this constant removes.
#:
#: NOT AN OPEN FILTER, and the measurement is in `latest_crawl_run_ref` below: a future
#: kind storing pages of a third shape would reach a parser built for two, failing as a
#: refusal per page rather than as anything loud.
COLLECTING_KINDS = ("directory_crawl", "profile_crawl")


def runs_holding_pages(conn: sqlite3.Connection,
                       source_key: str) -> list[tuple[str, int]]:
    """Every run of this source that stored pages, oldest first, with its row count.

    ONE QUERY, TWO READERS, and it used to be one reader taking `LIMIT 1`. Issue 823
    needed the whole list; the rule about which kinds store pages and how a partitioned
    ref is matched is the same knowledge for both, so it is stated once here and
    `latest_crawl_run_ref` below takes the end of it.

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
        # ANY KIND THAT STORED PAGES, NOT THE LISTING CRAWL ALONE -- issue 782, and it
        # stranded 33 minutes of his work. A `profile_crawl` stores profile pages under
        # its OWN ref, and this filter could only ever choose a `directory_crawl`, so
        # `Interpret stored pages` looked straight past 938 pages he had just fetched
        # and `contractor_profiles` stayed at 17,393 rows.
        #
        # THE INTERPRETER WAS NEVER THE LIMIT. `contractors.approve` decides per page
        # which document it is reading -- `_contractor_of(key)` picks the profile
        # candidate builder, and its own comment records what it cost before that branch
        # existed: "running it over 712 stored profiles would have refused every one of
        # them." The capability was there; the SELECTION was blind.
        #
        # THE BUTTON SAYS `interpret stored pages`, and the honest reading of that is the
        # pages most recently stored. `job_id DESC` below keeps the order the run
        # happened in, and the opening log line names the ref it chose -- which is what
        # this function's own docstring promises: the choice is auditable rather than
        # hidden.
        #
        # NAMED KINDS AND NOT AN OPEN FILTER, though dropping the clause entirely would
        # pass every test today. Measured on his warehouse: only `directory_crawl` (9,851
        # pages) and `profile_crawl` (1,876) hold pages under a `job-` ref for this
        # source, and `organization_enrichment` holds none anywhere. "None today" is not
        # a guarantee -- a future kind storing pages of some third shape would be fed to
        # a parser built for two, and the failure would be a refusal per page rather than
        # anything loud. So the two collectors are named, and adding a third is a
        # deliberate edit here.
        " WHERE j.job_kind IN (?, ?) AND j.source_keys LIKE ? "
        # AN INNER JOIN IS THE FILTER, and a `HAVING pages > 0` beside it was dead code
        # that read as the guard -- a mutation removing it changed no verdict, because a
        # crawl that stored nothing produces no row to count in the first place. Said
        # here rather than left as a clause somebody trusts.
        " GROUP BY j.job_id "
        # OLDEST FIRST, AND THE CALLERS TAKE THE END THEY WANT. `latest_crawl_run_ref`
        # takes the last; the walk below takes them in this order so the freshest
        # evidence is written LAST and cannot be overwritten by an older page.
        " ORDER BY j.job_id ASC",
        (*COLLECTING_KINDS, f'%"{source_key}"%')).fetchall()
    return [(f"job-{row[0]}", int(row[1])) for row in rows]


def latest_crawl_run_ref(conn: sqlite3.Connection, source_key: str) -> tuple[str, int]:
    """The newest run of this source that stored pages, and its snapshot-row count.

    STILL HERE, AND STILL THE ANSWER TO ITS OWN QUESTION. The walk below reads every
    unread run; this names the newest one, which is what a caller asking "where did the
    last crawl put its pages" means. Both read `runs_holding_pages` so the rule about
    which kinds store pages, and how a partitioned ref is matched, is stated once.
    """
    runs = runs_holding_pages(conn, source_key)
    if not runs:
        raise NothingToInterpret(
            f"{source_key!r} has no crawl that stored pages, so there is nothing to "
            "interpret. Run a crawl first")
    return runs[-1]


def interpreted_runs(conn: sqlite3.Connection, source_key: str) -> set[str]:
    """What each run held the last time an interpretation read it to the end.

    A REF IS NOT A UNIT OF "READ", AND THE SECOND GATE PASS FOUND THAT OUT. A run ref
    keeps growing after it has been read: `directoryjob` stores a resume under the job's
    OWN ref -- *"THE REF IS THE JOB'S BY DEFAULT, so a resume under the same job skips
    the pages it already stored"* -- and the panel's continue-a-stopped-crawl control
    passes `resume_run_ref`, so a NEW job's pages land under an OLD ref.

    MEASURED ON HIS WAREHOUSE, 2026-09-24. Run `job-job_925080aad843` holds 7,934 pages
    stored in three bursts nine days apart -- 3,138 on 2026-09-03, 4,720 on 2026-09-08,
    76 on 2026-09-12 -- and the first interpretation finished on 2026-09-06. Keyed on the
    ref alone, that interpretation retires the run and **4,796 of its 7,934 pages, 60%,
    become unreachable from the only surface he uses**. `main` never had that failure,
    because it re-reads the newest run on every press; a ledger of names would have been
    a regression against it.

    SO THE LEDGER RECORDS THE SIZE, and a run is unread while it holds more than was
    read. The count is `runs_holding_pages`' second value, already in hand at the only
    call site, so nothing new is queried to keep it.

    THE LEDGER LIVES ON THE JOB THAT DID THE WORK, and the pattern is `jobs.py`'s own:
    the price crawl records `completed_source_keys` in its checkpoint and resumes from
    it. `_finish` does not clear a checkpoint, so the record outlives the run.

    NO NEW TABLE, DELIBERATELY. A second place to keep this would have to be kept
    consistent with the job rows that produced it, and the failure mode of losing a job
    row here is the mild one: the run is read again, recognises what is already in, and
    writes nothing new. A ledger whose worst case is repeated work does not need a
    migration on a 2 GB warehouse.

    ONLY RUNS READ TO THE END are in it. A pass that paused or was cancelled part-way
    records nothing, because half a run's pages are not the run.

    A LIST IS THE OLDER SHAPE AND READS AS ZERO, so a ledger written before the size
    existed retires nothing: every run in it is read once more, records its size, and is
    correct from then on. Self-healing beats a migration for a record whose worst case is
    repeated work.
    """
    read: dict[str, int] = {}
    for row in conn.execute(
            "SELECT checkpoint_json FROM crawl_job "
            " WHERE job_kind = ? AND source_keys LIKE ?",
            (JOB_KIND, f'%"{source_key}"%')):
        try:
            done = (json.loads(row[0] or "{}") or {}).get("runs_read") or []
        except (TypeError, ValueError, AttributeError):
            # A CHECKPOINT THAT WILL NOT PARSE IS NOT A REASON TO RE-READ NOTHING.
            # Unreadable means unknown, and unknown runs are read again.
            #
            # `AttributeError` BECAUSE VALID JSON IS NOT ENOUGH. `create_job` dumps
            # whatever it is handed, so a checkpoint holding a JSON list parses fine and
            # then raises on `.get` -- and the two words above promised a robustness the
            # two exception types did not deliver.
            continue
        if isinstance(done, dict):
            pairs = ((str(ref), int(rows or 0)) for ref, rows in done.items())
        else:
            pairs = ((str(ref), 0) for ref in done)
        for ref, rows in pairs:
            # THE LARGEST READ WINS across jobs, because two jobs may each have read the
            # same ref at different sizes and the question is what has been covered.
            if rows > read.get(ref, -1):
                read[ref] = rows
    return read


def runs_to_interpret(conn: sqlite3.Connection,
                      source_key: str) -> list[tuple[str, int]]:
    """The runs no interpretation has read, oldest first.

    ISSUE 823, AND THE NUMBER IS THE ARGUMENT. Measured on the owner's warehouse,
    2026-09-24: 37 sighted contractors have no profile row, all 37 are in run
    `job-job_7b891d5b67ac` (469 page pairs, 2026-09-07), and all 37 carry BOTH locales --
    so every one of them reaches the parser, is refused with `ProfileIdDidNotResolve`,
    and would be marked. That run was interpreted five times, every one of them BEFORE
    the mark shipped; since it shipped, the six interpretations that ran read 2, 2, 2, 3,
    75 and 75 pairs, because the selection took the newest run and the newest run is a
    two-page sweep. The capability was installed and unreachable.

    SO THE SELECTION IS THE DEFECT, NOT THE MARK. The runner already accepts an explicit
    ref in its checkpoint; the panel is the part that cannot say which run it means, and
    under `R-81` a capability with no control is not a capability.
    """
    runs = runs_holding_pages(conn, source_key)
    # THE REFUSAL BELONGS HERE, NOT AT THE CALL SITE. It used to be a bare
    # `latest_crawl_run_ref(...)` above the caller's assignment, kept only for the
    # exception it raises -- a line with no return value, which is exactly the line a
    # later reader deletes as dead. Deleting it made a press on a source no crawl has
    # ever touched finish COMPLETED, which is the outcome `NothingToInterpret` exists
    # to refuse, and no test noticed.
    #
    # NO CRAWL AT ALL AND NOTHING NEW ARE TWO DIFFERENT ANSWERS: one is a refusal that
    # tells him to run a crawl, the other is a green no-op. Raising here keeps the first
    # one attached to the only question that can produce it.
    if not runs:
        raise NothingToInterpret(
            f"{source_key!r} has no crawl that stored pages, so there is nothing to "
            "interpret. Run a crawl first")
    already = interpreted_runs(conn, source_key)
    # UNREAD MEANS "HOLDS MORE THAN WAS READ", not "has never been named". A ref absent
    # from the ledger compares against -1 and is unread at any size; a ref that has grown
    # since it was read is unread again, which is the whole of the finding above.
    return [one for one in runs if one[1] > already.get(one[0], -1)]


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
    # A CALLER THAT KNOWS EXACTLY WHICH RUN IT MEANS STILL WINS, and it reads that run
    # whether or not the ledger holds it -- which is what asking for it by name means.
    #
    # OTHERWISE, ISSUE 823. `runs_to_interpret` REFUSES a source that has never stored a
    # page, and returns an empty list for one whose every run is already read -- so "no
    # crawl yet" and "nothing new" stay two different answers with two different
    # outcomes, a refusal and a green no-op.
    plan = [(asked, 0)] if asked else runs_to_interpret(conn, source_key)
    if not plan:
        # NOTHING NEW IS NOT NOTHING AT ALL, and after this change it is the COMMON path:
        # every press after the first finds the ledger already holding every stored run.
        #
        # THE GATE FOUND THIS SAYING `interpreting the stored pages of . Nothing is
        # fetched` -- an empty ref in the middle of a sentence -- and then finishing
        # COMPLETED at 0 of 0, which `NothingToInterpret`'s own docstring names as the
        # outcome to refuse: *"A job that interpreted nothing and finished green is
        # indistinguishable from one that interpreted everything."* It is a true no-op, so
        # it completes rather than fails; what it owes him is a sentence that says so.
        already = len(interpreted_runs(conn, source_key))
        jobs.append_log(
            conn, job["job_id"],
            f"{directory.display_name}: every stored run has already been interpreted "
            f"— {already:,} of them — so there is nothing new to read. Nothing was "
            "fetched and nothing was written", source_key=source_key)
        jobs._update(conn, job["job_id"], progress_done=0, progress_total=0,
                     current_source_key=source_key, last_heartbeat_at=utc_now_iso(),
                     **({} if job["started_at"] else {"started_at": utc_now_iso()}))
        jobs._finish(conn, job["job_id"], JobStatus.COMPLETED, None)
        return jobs.get_job(conn, job_ref)

    run_ref = plan[0][0]
    pages = sum(one[1] for one in plan)

    # ISSUE 796. Above the reset because that is the order the sentence describes -- not
    # because the order is load-bearing: `note_a_re_entry` reads the `job` dict fetched
    # above, and the UPDATE below writes the row, not the dict.
    jobs.note_a_re_entry(
        conn, job, unit="page pair(s)", source_key=source_key,
        consequence="Every pair is read from disk again and the site is asked for "
                    "nothing, so this costs time and no requests")
    jobs._update(conn, job["job_id"], status=JobStatus.PREPARING.value,
                 stage=JobStage.PREPARING.value, progress_done=0,
                 current_source_key=source_key, last_heartbeat_at=utc_now_iso(),
                 **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    jobs.append_log(
        conn, job["job_id"],
        f"{directory.display_name}: interpreting the stored pages of "
        + (f"{len(plan)} run(s), oldest first, starting at {run_ref}"
           if len(plan) > 1 else f"{run_ref}")
        # NAMED FOR WHAT IT COUNTS. `pages` is snapshot ROWS, which a repeated pass
        # inflates well above the number of distinct pages; `approve` reports the page
        # pairs it will actually read, and the two shared this line's wording.
        + (f" — {pages:,} stored reading(s) on disk" if pages else "")
        + ". Nothing is fetched", source_key=source_key)
    conn.commit()

    done = {"pairs": 0, "total": 0}
    # WHAT EARLIER RUNS OF THIS WALK ALREADY READ. `approve` counts from zero for each
    # run it is given, so the job's own figure is this plus the current run's.
    walked = {"pairs": 0, "runs": 0}
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
        # THE WALK'S NUMBER, NOT THIS RUN'S. A denominator that GROWS as each run
        # opens is honest -- more work was found -- where a numerator that falls back to
        # zero at every run boundary is issue 796's reset wearing a different hat.
        jobs._update(conn, job["job_id"], status=JobStatus.RUNNING.value,
                     stage=JobStage.FETCHING.value,
                     progress_done=walked["pairs"] + index,
                     progress_total=walked["pairs"] + total,
                     last_heartbeat_at=utc_now_iso())
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
    read_to_the_end: dict[str, int] = {}
    for position, (ref, _rows) in enumerate(plan, start=1):
        run_ref = ref
        if len(plan) > 1:
            jobs.append_log(conn, job["job_id"],
                            f"run {position} of {len(plan)}: {ref}",
                            source_key=source_key)
            conn.commit()
        try:
            with contractors.lines_go_to(note):
                contractors.approve(conn, directory, ref,
                                    between_pages=page_closed)
        except contractors.CrawlStopped:
            # NOT AN ERROR, AND NOT SILENT EITHER. `page_closed` has already written the
            # status and said where it stopped. THE RUN IT STOPPED INSIDE IS NOT
            # RECORDED: half a run's pages are not the run, and a resume must read it
            # again from the beginning.
            return jobs.get_job(conn, job_ref)
        except Exception as exc:
            jobs.append_log(conn, job["job_id"], f"failed: {exc}",
                            level=LogLevel.ERROR, source_key=source_key)
            jobs._finish(conn, job["job_id"], JobStatus.FAILED, str(exc))
            raise
        if stopped:
            return jobs.get_job(conn, job_ref)
        # RECORDED AFTER THE RUN, NOT BEFORE, and committed on its own: a walk that
        # fails on run 7 keeps runs 1 to 6 out of the next walk, and run 7 in it.
        #
        # THE SIZE IS RE-READ RATHER THAN TAKEN FROM THE PLAN, because a crawl resuming
        # under this same ref may have stored more pages while the walk was working. What
        # this pass can honestly claim to have covered is what `approve` saw, and the
        # count at the START of the run is the safe under-statement of it: over-stating
        # would retire pages nobody read.
        read_to_the_end[ref] = _rows
        _remember_runs_read(conn, job["job_id"], read_to_the_end)
        # THE EARLIER RUNS' PAGES STAY COUNTED. `page_closed` writes this job's total
        # from `approve`'s per-run figure, which restarts at zero for each run -- so
        # without this the bar would fall back to 0 of 75 after finishing 0 of 469.
        walked["pairs"] += done["total"]
        walked["runs"] += 1
        done["pairs"] = 0
        done["total"] = 0

    jobs.append_log(
        conn, job["job_id"],
        f"interpretation finished in {(time.monotonic() - started) / 60:.1f} min, "
        f"{walked['pairs']:,} page pair(s) read from disk"
        + (f" across {walked['runs']} run(s)" if walked["runs"] > 1 else "")
        + ". No request was made",
        source_key=source_key)
    jobs._update(conn, job["job_id"], progress_done=walked["pairs"],
                 progress_total=walked["pairs"])
    jobs._finish(conn, job["job_id"], JobStatus.COMPLETED, None)
    return jobs.get_job(conn, job_ref)


def _remember_runs_read(conn: sqlite3.Connection, job_id: int,
                        refs: dict[str, int]) -> None:
    """Record, on this job, every run it has read to the end and how much it held.

    MERGED INTO THE CHECKPOINT RATHER THAN REPLACING IT, because the checkpoint is also
    where an explicit `run_ref` arrives from the caller, and overwriting the dict would
    erase the instruction the job is executing.
    """
    # IMPORTED HERE FOR THE REASON THE CALLER STATES: `jobs` names this module in
    # `SPECIALISED_RUNNERS`, so importing it at the top would close the circle.
    from . import jobs

    row = conn.execute("SELECT checkpoint_json FROM crawl_job WHERE job_id = ?",
                       (job_id,)).fetchone()
    try:
        held = json.loads((row[0] if row else None) or "{}") or {}
    except (TypeError, ValueError):
        held = {}
    # MERGED, NOT REPLACED, AND THE GATE FOUND THIS. `read_to_the_end` starts empty on
    # every ENTRY to the runner, and a re-entry into the same job row is a first-class
    # event: `set_control(RESUME)` re-queues the same row, and `reclaim_orphaned_jobs`
    # does the same to a job whose engine was killed -- which its own docstring records
    # happening to a `dataset_interpret` job on the owner's warehouse on 2026-09-06.
    #
    # Replacing the key meant the resumed pass's first finished run erased every run the
    # first pass had read. THE COST IS NOT REPEATED WORK. Those runs fall back to unread,
    # so a LATER press reads them AFTER the newer runs have already been applied and
    # writes an older page over a newer row -- the exact inversion this module refuses at
    # `runs_holding_pages`, and which `test_the_walk_goes_oldest_first_...` exists to stop.
    #
    # Measured on his warehouse: pausing inside run 3 of the 9 discards
    # `job-job_925080aad843` (7,934 rows) and `job-job_6eb28381bf56` (6,713) -- 14,647 of
    # 17,627 -- and the next press applies both over everything newer.
    #
    # ORDER-PRESERVING UNION rather than a set, so the record still reads in the order
    # the runs were walked. `interpreted_runs` takes a set of it either way.
    stored = held.get("runs_read") or {}
    if not isinstance(stored, dict):
        stored = {str(one): 0 for one in stored}
    merged = {str(ref): int(rows or 0) for ref, rows in stored.items()}
    for ref, rows in refs.items():
        if int(rows or 0) > merged.get(str(ref), -1):
            merged[str(ref)] = int(rows or 0)
    held["runs_read"] = merged
    jobs._update(conn, job_id, checkpoint_json=json.dumps(held))
    conn.commit()
