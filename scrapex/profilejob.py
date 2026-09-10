"""One profile-page sweep, driven as a job so the panel can start it.

WHAT WAS ACTUALLY WRONG, MEASURED ON HIS WAREHOUSE 2026-09-06. `contractors.details` --
the step that fetches the profile page of every contractor a listing named -- could be
reached from `scrapex contractors --details` and from nowhere else: no API route, no job
kind, no control in the panel. `R-81` says the panel is his only interface, so the profile
half of muqawil did not exist for the one person the tool is for. His words: «لا استطيع
عبر الواجهة ... عمل crawl ل profiles او حتى استكمال profiles الناقصة».

THIS IS THE SAME HOLE `datasetjob` CLOSED FOR `approve`, one phase earlier in the
pipeline: crawl the listing, fetch the profiles it named, interpret what was stored. Two
of the three had a door before this one.

THE DEFAULT FRONTIER IS WHAT IS MISSING, AND THAT IS HIS RULING RATHER THAN A CONVENIENCE.
The whole frontier is about 35,700 pages -- roughly 87 hours at the measured 9.03 s a page
-- and a control whose only question takes 87 hours is one he cannot safely press. The
missing set on his warehouse is 469 contractors, 938 pages, about 2.4 hours. `--details`
already accepts named ids and they REPLACE the frontier rather than filter it, so the
door asks the narrow question by construction and the wide one on request.

WHY A JOB KIND RATHER THAN A STAGE OF THE LISTING CRAWL. `contractors.details`'s own
docstring settles it: the listing crawl is PROVABLE -- it partitions, witnesses and counts
-- while a profile sweep "has no such theorem to offer: the frontier is a list, and reading
a list proves nothing". Folding them would also put a many-hour walk behind the command
somebody runs to check coverage. Two jobs, two verdicts.

WHAT IT DOES NOT DUPLICATE. Not one line of fetching lives here. `contractors.details` is
the same function `--details` calls, and this module is the three things a job adds: the
sweep's report reaches the job log instead of a console, progress is counted in PAGES, and
the owner's pause or cancel is applied between two of them.

A PAGE BOUNDARY IS SAFE, unlike the listing crawl's cell. A cell's completeness proof spans
many pages, so a cell cut in half has fetched pages and proved nothing; a profile page is
stored whole and the next is independent of it. `already_stored` is scoped to the run ref,
so resuming under the same job skips every page already down.

AND IT HOLDS THE POLITENESS RESERVATION, which is where it differs from `datasetjob` and
agrees with `directoryjob`. This job asks muqawil for pages, so two of them -- or one of
these and a listing crawl -- would double the request rate on that host. `OP-128`.

IT RUNS SEQUENTIALLY, AND THAT IS A CHOICE WITH A REASON RATHER THAN AN OVERSIGHT.
`details` takes `workers` and `connect`, and using them here needs two things this door
does not have: `directoryjob.for_writing`'s connection-by-thread rule, because a pause
WRITES and the pool calls back from worker threads, and `partitioncrawl`'s `stopping`
event, because `ThreadPoolExecutor.__exit__` runs every queued task after a stop is
decided. `details` refuses `between_pages` above one worker for exactly that reason. So
the pool is a separate change with its own measurement, and this one is a door.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import nullcontext

from . import contractors, directories, sightings
from .payload import utc_now_iso
from .sites.muqawil import MuqawilPageSource
from .vocab import JobControl, JobStage, JobStatus, LogLevel

#: The kind this module runs. Named once; `jobs.SPECIALISED_RUNNERS` reads it so the
#: string cannot be spelled two ways in two files, and `db/engine/schema.sql`'s CHECK
#: carries the same word -- widened by migration 0019.
JOB_KIND = "profile_crawl"

#: Pages between progress writes. A profile page costs about nine seconds, so this is a
#: small write about every forty-five seconds -- comfortably inside
#: `jobs.JOB_HEARTBEAT_MAX_AGE_S` (fifteen minutes), and not a write per request.
#:
#: AT MODULE SCOPE SO A TEST CAN VARY IT. The heartbeat guard in `directoryjob` was
#: written against a local and the monkeypatch did nothing -- five of six beats were
#: silently throttled and the guard passed.
BEAT_EVERY_PAGES = 5


class NothingToFetch(LookupError):
    """Every contractor this build knows about already has a profile page stored.

    A REFUSAL RATHER THAN AN EMPTY SUCCESS, for the reason `contractors.validate` gives in
    terms: a run that quietly did nothing looks exactly like a run that had nothing to do,
    and those are opposite facts. The panel offers this control whenever a directory has
    rows, so "nothing missing" is an ordinary answer and it has to be a legible one.
    """


class NotADirectory(LookupError):
    """The key names no directory this build can crawl."""


def missing_profile_ids(conn: sqlite3.Connection,
                        directory: directories.Directory) -> tuple[str, ...]:
    """Every contractor id this warehouse knows of that has no profile row.

    OFF THE SIGHTING LEDGER, NOT OFF THE LISTING ROWS, and the difference is 45
    contractors on his warehouse: 469 sighted ids have no profile against 424 that also
    have a listing row of their own. `dataset_sighting` holds every id the site has ever
    shown us -- that is what it is for -- and a profile URL is built from the id alone, so
    a contractor sighted in a listing we did not keep is still fetchable. `detail_frontier`
    reads the same ledger for the same reason, and measured 40x faster than deriving it
    from the stored pages.

    JOINED ON `contractor_id` OUT OF `data_json`, WHICH IS THE ONLY KEY THAT MEANS
    ANYTHING HERE. My first count of this joined `generic_record.record_key` across the two
    datasets and got 424 by luck: those keys are digests of the PARSED ROW, and the two
    datasets hash different things -- `source_locator` is `div.section-card::row(N)` for a
    listing card and `div.info-box::row(1)` for a profile. A `record_key` join returns a
    plausible number that describes nothing, which is why a guard asserts this one.

    THE PROFILE DATASET IS ASKED OF THE DIRECTORY rather than named here.
    `directory.profiles.dataset_key` is where that fact lives, and a literal
    `'contractor_profiles'` in this file would be a second place for it to be wrong the
    day a second directory grows profiles.
    """
    rows = conn.execute(
        "SELECT external_id FROM dataset_sighting WHERE dataset_key = ? "
        "EXCEPT "
        "SELECT json_extract(r.data_json, '$.' || ?) FROM generic_record AS r "
        "  JOIN dataset_definition AS d "
        "    ON d.dataset_definition_id = r.dataset_definition_id "
        " WHERE d.dataset_key = ? AND r.status = 'active'",
        (directory.dataset_key, directory.identity_field,
         directory.profiles.dataset_key)).fetchall()
    # AND AN ID THE SITE WILL NOT SERVE IS NOT A GAP WE CAN CLOSE -- issue 794. 37 of his
    # 469 answered `/contractors/<id>/143` with the contractors listing at HTTP 200, so
    # they can never become rows: every pass refused the same 37 and wrote nothing, the
    # card went on calling them work waiting, and the fetch control would have bought
    # their 74 pages again on every press.
    #
    # SUBTRACTED HERE AND NOWHERE ELSE, which is what keeps `still_to_fetch` and the
    # route honest without a second filter to forget: this is the DEFAULT frontier both
    # of them start from. A caller naming ids explicitly still reaches them, because
    # `OP-64`'s remediation is re-fetching a contractor whose rows came from the wrong
    # document -- and a marked id is precisely one of those.
    unresolved = sightings.profile_unresolved_ids(conn, directory.dataset_key)
    # ORDERED, so two runs of the same warehouse build the same frontier and a report of
    # one can be diffed against the other. `EXCEPT` does not promise an order.
    return tuple(sorted(str(row[0]) for row in rows
                        if row[0] is not None and str(row[0]) not in unresolved))


def still_to_fetch(conn: sqlite3.Connection, directory: directories.Directory,
                   ids: tuple[str, ...]) -> tuple[str, ...]:
    """Of these contractors, the ones whose profile pages are not already on disk.

    THE FETCH GAP AND THE INTERPRETATION GAP ARE DIFFERENT QUESTIONS, AND I GAVE THEM ONE
    ANSWER. `missing_profile_ids` asks "who has no profile ROW", which is the right
    frontier for interpreting and the wrong one for fetching: storing a page changes no
    row, so the answer does not move when the sweep succeeds. He pressed the control and
    it re-derived the same 469 contractors -- and `details`' own resume could not help,
    because `already_stored` is scoped to the RUN REF and a new job has a new one.

    MEASURED 2026-09-07: two sweeps fetched 938 pages EACH, 1,876 requests for what 938
    would have bought. Left alone the button re-buys the same pages on every press until
    an interpretation happens, which is a crawl that hammers a site -- a defect by this
    repository's own rule, not an inconvenience.

    THE URL SHAPE STAYS IN ITS ONE PLACE. `MuqawilPageSource.profile_urls` says why:
    "Two copies of the pattern is two places to forget `SELF_BUILD_SEGMENT`, which is the
    segment that makes the self-build price section render at all." So this generates each
    contractor's URLs through that builder and tests them against ONE read of the stored
    set, rather than parsing an id back out of a URL.

    ALL LOCALES OR NONE. A contractor with an English page and no Arabic one is not
    fetched: `approve` pairs the halves and a lonely half is counted as lonely. Asking
    for `all` means a half-finished contractor is re-fetched, which is what a resume is
    for.

    AND A CALLER NAMING IDS EXPLICITLY IS NOT FILTERED BY THIS -- the runner applies it
    to the DEFAULT frontier only. `OP-64`'s remediation is re-fetching a contractor whose
    rows came from the wrong document, and that needs the page again even though it is on
    disk.
    """
    if not ids:
        return ()
    source = MuqawilPageSource(last_page=1)
    stored = {row[0] for row in conn.execute(
        "SELECT DISTINCT source_url FROM generic_page_snapshot "
        " WHERE instr(source_url, ?) > 0", ("/contractors/",))}
    return tuple(
        one for one in ids
        if not all(url in stored
                   for url in source.profile_urls(directory.base_url, one)))


def run_profile_crawl_job_once(conn: sqlite3.Connection, job_ref: str,
                               admission=None) -> dict:
    """Fetch the profile pages this job asks for, to completion or a control boundary.

    Synchronous and connection-injected, exactly like `jobs.run_job_once`, so the thread
    loop in `JobRunner` is the only thing that needs a thread.

    THREE FRONTIERS, AND THE CHECKPOINT CHOOSES. Nothing in the checkpoint means the
    MISSING set, which is what the panel's control asks for; `{"ids": [...]}` names
    contractors exactly, which is the `OP-64` remediation for rows written from the wrong
    document; `{"whole_frontier": true}` asks the registered scope's full frontier, which
    is the many-hour question and has to be asked for in words.

    `admission` IS THE CROSS-JOB POLITENESS GATE AND IT IS HELD AROUND THE FETCHING. This
    job asks muqawil for pages, so two of them -- or this and a listing crawl -- would run
    with their own fetcher at `DEFAULT_PACE_S` each and double the rate on that host.
    Held here rather than at the dispatch, for `directoryjob`'s stated reason: only this
    function knows when the first request goes out and when the last one returns.
    """
    from . import jobs

    job = jobs.get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind") != JOB_KIND:
        raise ValueError(
            f"job {job_ref!r} is a {job.get('job_kind')!r}, not a {JOB_KIND!r}")
    if job["status"] in {status.value for status in jobs.TERMINAL_JOB_STATUSES}:
        # ALREADY DECIDED. A cancelled or finished job that ran again would fetch from a
        # site the owner has already stopped, which is the one thing a re-pick must never
        # do.
        return job

    keys = list(job["source_keys"])
    if len(keys) != 1:
        # ONE DIRECTORY PER JOB, AND THE REASON IS THE PROGRESS FIGURE, the same reason
        # the listing crawl gives: pages are the denominator, two directories have
        # different frontiers, and a bar that mixes them cannot say what is left of
        # either.
        raise ValueError(
            f"a {JOB_KIND!r} job sweeps exactly one directory and {job_ref!r} names "
            f"{len(keys)}: {keys}")
    source_key = keys[0]
    if source_key not in directories.BUILDERS:
        raise NotADirectory(
            f"{source_key!r} is not a directory this build can crawl. Known: "
            f"{sorted(directories.BUILDERS)}")

    directory = directories.get(source_key)
    checkpoint = job.get("checkpoint") or {}
    whole = bool(checkpoint.get("whole_frontier"))
    named = tuple(str(one) for one in (checkpoint.get("ids") or ()))
    ceiling = int(checkpoint.get("ceiling") or 0)

    if whole:
        ids: tuple[str, ...] = ()
        wanted = 0
        opening = ("the registered scope's whole profile frontier — every contractor, "
                   "not only the missing ones")
    elif named:
        ids, wanted = named, len(named)
        opening = f"{len(named):,} named contractor(s)"
    else:
        # TWO GAPS, AND THE FETCH ASKS THE SECOND. `missing_profile_ids` answers "who has
        # no profile ROW", which is the interpretation gap; `still_to_fetch` removes the
        # ones whose pages are already on disk. Storing a page changes no row, so without
        # the second call this frontier does not move when the sweep succeeds and the
        # control re-buys the same pages on every press -- measured 2026-09-07 at 1,876
        # requests for what 938 would have bought.
        rowless = missing_profile_ids(conn, directory)
        ids = still_to_fetch(conn, directory, rowless)
        wanted = len(ids)
        if not ids:
            # AN HONEST REFUSAL. `details` with an empty `ids` tuple falls through to the
            # SCOPE's frontier -- the 87-hour question -- so returning early here is not
            # tidiness: passing `()` on would start the wrong sweep, which is the exact
            # four-round hole `--ids` records in `contractors.run`.
            #
            # AND THE TWO REASONS FOR NOTHING TO DO ARE DIFFERENT ANSWERS. Nobody
            # missing at all is one; everybody missing a ROW already having their PAGES
            # is the other, and it means the next step is an interpretation rather than a
            # fetch. Telling him "nothing to fetch" without saying which would send him
            # looking for the wrong button.
            raise NothingToFetch(
                (f"all {len(rowless):,} contractor(s) without a profile row already have "
                 "their profile pages stored, so there is nothing left to FETCH — what "
                 "is owed is an interpretation of those pages, not a request to the "
                 "site. Nothing was requested"
                 ) if rowless else
                (f"every contractor {directory.display_name} has shown us already has a "
                 "profile row, so there is nothing missing. Nothing was requested"))
        opening = (f"{len(ids):,} contractor(s) with no profile page stored — "
                   f"{len(ids) * 2:,} page(s) across both locales")
        if len(rowless) != len(ids):
            opening += (f" ({len(rowless) - len(ids):,} more have no row but their pages "
                        "are already on disk, so they are not fetched again)")

    # THE REF IS THE JOB'S, so a resume under the same job skips the pages it already
    # stored: `already_stored` is scoped to the ref, and the job ref is the only label
    # that is stable across a pause and a re-pick.
    run_ref = f"job-{job_ref}"

    # ISSUE 796, and the same silence sat in all three runners. Above the reset for
    # readability, not for correctness: the count comes from the `job` dict, and the
    # UPDATE below writes the row.
    jobs.note_a_re_entry(
        conn, job, unit="page(s)", source_key=source_key,
        consequence=f"The pages already stored under {run_ref} are skipped rather "
                    "than bought again")
    jobs._update(conn, job["job_id"], status=JobStatus.PREPARING.value,
                 stage=JobStage.PREPARING.value, progress_done=0,
                 progress_total=wanted * 2, current_source_key=source_key,
                 last_heartbeat_at=utc_now_iso(),
                 **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    jobs.append_log(
        conn, job["job_id"],
        f"{directory.display_name}: fetching {opening}, as {run_ref}",
        source_key=source_key)
    if ceiling:
        jobs.append_log(conn, job["job_id"],
                        f"  stopping at {ceiling:,} page(s), so this run is PARTIAL by "
                        "design and running it again continues from here",
                        source_key=source_key)
    conn.commit()

    done = {"pages": 0, "total": 0}
    stopped: list[str] = []

    def note(line: str) -> None:
        """One line of the sweep's own report, into the job log.

        THROUGH `contractors.say`'S SINK rather than by re-implementing the report. The
        sweep already says what it stored, failed and resumed; a job that summarised it
        again would be a second account of one pass, free to disagree with the first.
        """
        jobs.append_log(conn, job["job_id"], line, source_key=source_key)
        conn.commit()

    def page_closed(index: int, total: int) -> bool:
        """Called before each page. `True` asks the sweep to stop here.

        ON THE JOB'S OWN THREAD, and `details` enforces that: it refuses this hook above
        one worker, because a pool would call it from worker threads where this
        connection cannot be used and where a stop is honoured late or not at all.
        """
        done["total"] = total
        done["pages"] = index
        # THE FIRST CALL ALWAYS WRITES, so `progress_total` reaches the card before the
        # work rather than after it. A sweep of 938 pages showing 0/0 until it finished
        # would read as a job that never started -- and the total is corrected here
        # because `details` decides it, after the resume and the ceiling are applied.
        if index and index % globals()["BEAT_EVERY_PAGES"]:
            return False
        # READ BEFORE WRITING, AND THE ORDER IS THE FIX. Issue 791: he pressed Cancel on
        # a running sweep at 13:55:57 and it fetched all 938 pages anyway, with the word
        # "cancel" nowhere in its log. The beat wrote `status = running` FIRST and
        # unconditionally -- over the `cancelling` that `set_control` had just parked
        # there to mean "the worker will settle this at its next safe boundary". Its own
        # docstring calls that compare-and-swap load-bearing so a late click cannot
        # resurrect a settled job; the beat resurrected it from the other side.
        current = jobs.get_job(conn, job_ref)
        control = jobs._control_of(conn, job["job_id"])
        # AND THE ROW OUTRANKS THE INSTRUCTION, because the instruction can be gone. At
        # 13:58 that job carried `finished_at` AND `status = running` AND
        # `control = none` -- finished and running at once, with nothing left to find.
        # `_finish` clears `control`, so a stop that has already been recorded leaves no
        # pending intent, and a guard reading only `control` sails past it. This is the
        # half that stops the run whichever of issue 791's readings was the true one.
        if not jobs.still_wanted(conn, job_ref):
            jobs.append_log(
                conn, job["job_id"],
                f"stopped after {index:,} of {total:,} page(s): this job is already "
                "settled, so nothing more is fetched",
                source_key=source_key)
            conn.commit()
            stopped.append(JobStatus.CANCELLED.value)
            return True
        # THE COUNT IS AN OBSERVATION AND THE STATUS IS A CLAIM, so a pending stop
        # withholds the claim and nothing else. Withholding the whole write was a
        # regression of this branch, and a worse one here than in `directoryjob`:
        # `index` AND `total` sat inside it, so a sweep paused before its first page
        # closed settled at `0/0` -- a card that cannot say whether the job ever had a
        # frontier, on a run that had 938 pages in it.
        beat = {"progress_done": index, "progress_total": total,
                "last_heartbeat_at": utc_now_iso()}
        if control not in {JobControl.PAUSE.value, JobControl.CANCEL.value}:
            # NOT WHEN A STOP IS PENDING. Falling through to the branches below settles
            # it; writing `running` first would erase the transitional state the panel
            # is showing him.
            beat["status"] = JobStatus.RUNNING.value
            beat["stage"] = JobStage.FETCHING.value
        jobs._update(conn, job["job_id"], **beat)
        conn.commit()
        if control == JobControl.PAUSE.value:
            jobs._update(conn, job["job_id"], status=JobStatus.PAUSED.value,
                         control=JobControl.NONE.value, stage=None,
                         last_heartbeat_at=utc_now_iso())
            jobs.append_log(
                conn, job["job_id"],
                f"paused between pages, {index:,} of {total:,} fetched. Resuming "
                f"re-reads {run_ref} and skips what is already stored",
                source_key=source_key)
            conn.commit()
            stopped.append(JobStatus.PAUSED.value)
            return True
        if control == JobControl.CANCEL.value:
            jobs.append_log(
                conn, job["job_id"],
                f"cancelled between pages. The {index:,} page(s) already stored under "
                f"{run_ref} are kept and a later run continues from them",
                source_key=source_key)
            jobs._finish(conn, job["job_id"], JobStatus.CANCELLED, None)
            # COMMITTED, LIKE ITS PAUSE SIBLING. This branch was the only one of the two
            # without it, so its log line and its `_finish` rode on whatever committed
            # next -- and issue 791's log has no cancel line in it at all.
            conn.commit()
            stopped.append(JobStatus.CANCELLED.value)
            return True
        # `current` IS READ AND USED, not read and discarded: a job the worker has been
        # told to drop its database for is a job whose next page must not open.
        return bool(current is None)

    started = time.monotonic()
    fetcher, fetch = contractors.make_fetch(contractors.DEFAULT_PACE_S)
    # ONE DEFINITION OF A HOST, taken from `jobs` rather than written again here, for the
    # reason `directoryjob` states: a source filed under one host name for grouping and
    # another for reservation is two jobs crawling a site together. The fallback is the
    # source key, so two unresolvable sources can never share a reservation.
    host = jobs.host_of_url(directory.base_url, source_key)
    # THE LANE WRAPS THE FETCHING AND NOTHING ELSE, so the frontier query above and the
    # closing report below do not hold a host against another job while asking the site
    # for nothing.
    admit = admission.lane(host) if admission is not None else nullcontext()
    try:
        with admit:
            # RE-READ AFTER THE LANE, BECAUSE THE WAIT MADE THE ENTRY CHECK STALE. The
            # terminal check at the top of this function ran before `admit`, and a lane
            # wait lasts exactly as long as the job holding the lane. Measured
            # 2026-09-07: a sweep entered at 10:33:44, waited 33 minutes, was cancelled
            # at 11:02:54 -- and fetched 938 pages at 11:06 because nothing looked
            # again. `between_pages` could not save it either: `_finish` clears
            # `control`, so by then there was no instruction left to find.
            if not jobs.still_wanted(conn, job_ref):
                jobs.append_log(
                    conn, job["job_id"],
                    "stopped while waiting for the site's turn, so nothing was "
                    "fetched — the decision to stop was made after this run began "
                    "waiting",
                    source_key=source_key)
                conn.commit()
                return jobs.get_job(conn, job_ref) or job
            with contractors.lines_go_to(note):
                contractors.details(conn, directory, fetch, fetcher, run_ref,
                                    ceiling=ceiling, ids=ids,
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
        f"profile sweep finished in {(time.monotonic() - started) / 60:.1f} min, "
        f"{done['total']:,} page(s) asked of the site. Interpreting them into rows is a "
        "separate step",
        source_key=source_key)
    jobs._update(conn, job["job_id"], progress_done=done["total"],
                 progress_total=done["total"])
    jobs._finish(conn, job["job_id"], JobStatus.COMPLETED, None)
    return jobs.get_job(conn, job_ref)
