"""The tender crawl job: a tender source's collector, run as a job (milestone 51, part 3b-2a).

His word of 2026-10-24 (#1733): the job comes first, on its own, with no route and no
control; part 3b-2b adds `POST /api/jobs`'s tender path, the source rows and the confirmed
control (#1701) in one change. The collector is `scrapex/sites/worldbank_collect.py`
(#1765); this module decides WHAT a run reads and keeps the record of what it read.

WHAT A RUN READS, the design #1701 confirmed:
  * every area the source does not hold whole yet, largest first, with the count taken at
    the start of this run (12, 13a);
  * then, when every area is held and the run is an update, the notices changed since the
    starting point below (13b).
A first crawl that stops is finished by an update, which reads the unread areas first.

THE RECORD IS EACH JOB'S OWN (his ruling of 2026-10-24, #1733). A job writes into its
`checkpoint_json` the count it took and when, the areas it read whole, the areas it left
unread and why, the point inside an area it stopped at, and its pass over changes. The
source's state is read from its jobs (`source_state`); no code deletes a `crawl_job` row,
so the record is the one source of truth and nothing else can drift from it.

WHERE A PASS OVER CHANGES STARTS (his ruling of 2026-10-24, #1701): the first pass after a
first crawl starts from when that crawl took its count, and each later pass from the
newest change held when the last COMPLETE pass ended -- each less one day (`MARGIN`).

ONE WRITER AT A TIME (`CLAUDE.md`; his ruling of 2026-10-31, #1775): a page is written inside
the warehouse's write lock, and read outside it. Another app holding it pauses the job
instead of failing it, because the record already holds its place; a Resume reads the undone
page again. Whichever of the job's writes meets it, and whatever it was doing then.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, fields
from datetime import timedelta

from . import capture, catalog, directoryjob, source_settings, tenders
from . import db as dbmod
from .catalog_models import SiteCreate
from .connectors.base import CrawlBlocked, CrawlInterrupted, source_fetcher
from .normalize import parse_instant
from .payload import utc_now_iso
from .sites import worldbank_collect as wc
from .vocab import JobControl, JobStatus, LogLevel, RunMode

JOB_KIND = "tender_crawl"

#: His ruling of 2026-10-24 (#1701): a pass over changes starts one day before its point,
#: against a gap between this machine's clock and the Bank's stamps, and a stamp seen after
#: it was written. Measured that day: about 570 changes a day, so about one request a pass.
MARGIN = timedelta(days=1)

#: What a run counts, in the words part 3b-2b's control shows (#1701, rows 19-20).
COUNTERS = tuple(field.name for field in fields(wc.Tally))

#: The modes a tender crawl runs. A full rebuild is not one (#1701 Q3): the history keeps
#: every notice it read, and an update reads what changed. History backfill is a price mode.
RUNS = (RunMode.INITIAL_CRAWL.value, RunMode.UPDATE.value)

#: How long one write of this job waits for another app, against `db.connect`'s 5 s. Waiting costs
#: only a slower answer on a warehouse nothing else can write to either, where a refusal costs a
#: pause he must resume by hand; #1399's job 184 measured a hold past 5 s on his machine.
WRITE_WAIT_MS = 60_000


@dataclass(frozen=True)
class SourceState:
    """What a tender source's crawls have done, read from their own records."""

    #: The newest count any job took: `counted_at`, `total`, `requests` and `areas`.
    count: dict | None
    #: Every area some job read whole.
    areas_read: frozenset[str]
    #: When the first count was taken: where the first pass over changes starts.
    first_counted_at: str | None
    #: The newest change held when the last complete pass over changes ended.
    held_whole_at: str | None

    def since(self) -> str | None:
        """Where the next pass over changes starts, less `MARGIN`; None before any count."""
        point = self.held_whole_at or self.first_counted_at
        if point is None:
            return None
        return (parse_instant(point) - MARGIN).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(job_ref: str, raw: str | None) -> dict:
    """One job's record, its shape asserted: it is read back to decide what to crawl."""
    record = json.loads(raw) if raw else {}
    if not isinstance(record, dict):
        raise ValueError(f"{job_ref}: its checkpoint is a {type(record).__name__}, "
                         "not an object")
    if not isinstance(record.get("areas_read", []), list):
        raise ValueError(f"{job_ref}: areas_read is not a list")
    count = record.get("count")
    if count is not None and not (isinstance(count, dict)
                                  and isinstance(count.get("counted_at"), str)
                                  and isinstance(count.get("areas"), list)):
        raise ValueError(f"{job_ref}: its count has no counted_at or areas")
    return record


def source_state(conn: sqlite3.Connection, source_key: str) -> SourceState:
    """The source's state, from every tender crawl of it, oldest first."""
    rows = conn.execute(
        "SELECT job_ref, checkpoint_json FROM crawl_job WHERE job_kind = ? AND EXISTS "
        "(SELECT 1 FROM json_each(crawl_job.source_keys) WHERE value = ?) ORDER BY job_id",
        (JOB_KIND, source_key)).fetchall()
    count = first = held = None
    read: set[str] = set()
    for job_ref, raw in rows:
        record = _record(job_ref, raw)
        read.update(record.get("areas_read", []))
        if record.get("count"):
            count = record["count"]
            first = first or record.get("first_counted_at") or count["counted_at"]
        changes = record.get("changes") or {}
        if changes.get("complete"):
            held = changes.get("held_whole_at") or held
    return SourceState(count=count, areas_read=frozenset(read), first_counted_at=first,
                       held_whole_at=held)


def _site_id(conn: sqlite3.Connection, source: tenders.TenderSource) -> int:
    """The source's `source_site` row, registered here when it is absent.

    ONLY WHEN ABSENT, for `contractors._run_for`'s reason: `register_site` refuses a key
    that exists under another `base_url`, and a crawl declares a site it does not know --
    it does not re-assert the identity of one somebody already registered.
    """
    row = conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                       (source.key,)).fetchone()
    if row is None:
        catalog.register_site(conn, SiteCreate(site_key=source.key,
                                               display_name=source.display_name,
                                               base_url=source.base_url))
        row = conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                           (source.key,)).fetchone()
    return int(row[0])


def _reasons(missed: dict) -> str:
    """Each unread area's reason, which already names the area (`read_area`)."""
    return " ".join(f"{reason}." for reason in missed.values())


def _resuming(record: dict) -> str:
    """What a Resume does from this record: an area goes on from its place, a pass over changes
    has no place to go on from, and `since` stands until one ends. With no count yet, what comes
    next is the count's to say: on a source held whole it is no page at all."""
    if record.get("phase") == "changes":
        return ("Resuming reads the pass over changes again from its start, and what it "
                "kept is not kept twice")
    if record.get("phase") is None:
        return "Resuming counts again, then reads what is left"
    return ("Resuming goes on from the next unread page, and the areas read whole are not "
            "read again")


def _refusals(refused: int) -> str:
    """What a job refused and what a later run does about it, on every ending that settles it: his
    choice of 2026-11-01 says it plainly, and leaves the way back to #1925. REFUSALS AND NOT
    NOTICES: a Resume reads a page again and refuses its notice again, and counting distinct ones
    would mean keeping every id in the record."""
    if not refused:
        return ""
    return (f"{wc._counted(refused, 'refusal')}, and a later run reads a refused notice again only "
            "if a pass over changes reaches it or its area is still unread. "
            f"{'It is' if refused == 1 else 'Each is'} named in the log by its id.")


def _named(exc: Exception) -> str:
    """An error by its type too, for an `httpx` error's message can be empty."""
    first_line = next(iter(str(exc).splitlines()), "")
    return f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__


def run_tender_crawl_job_once(conn: sqlite3.Connection, job_ref: str,
                              admission=None) -> dict:
    """Run one tender crawl to completion, or to a control boundary.

    Synchronous and connection-injected, like every runner in `jobs.SPECIALISED_RUNNERS`.
    `admission` is the cross-job politeness gate, held around the fetching only, for
    `profilejob`'s stated reason.
    """
    from . import jobs

    job = jobs.get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind") != JOB_KIND:
        raise ValueError(f"job {job_ref!r} is a {job.get('job_kind')!r}, not a {JOB_KIND!r}")
    if job["status"] in {status.value for status in jobs.TERMINAL_JOB_STATUSES}:
        return job
    keys = list(job["source_keys"])
    if len(keys) != 1:
        # ONE SOURCE PER JOB, because the areas are the denominator and two sources have
        # different areas.
        raise ValueError(f"a {JOB_KIND!r} job crawls exactly one source and {job_ref!r} "
                         f"names {len(keys)}: {keys}")
    source_key = keys[0]
    source = tenders.get(source_key)
    if job["run_mode"] not in RUNS:
        raise ValueError(f"a {JOB_KIND!r} job runs {list(RUNS)}, not {job['run_mode']!r}: "
                         "the history keeps every notice it read, and an update reads "
                         "what changed (#1701 Q3)")

    conn.execute(f"PRAGMA busy_timeout = {WRITE_WAIT_MS}")
    fetcher = source_fetcher(source_settings.effective(conn, source_key, source),
                             capture.crawl_settings(conn))
    ending: list[str] = []
    try:
        return _crawl(conn, job, job_ref, source, fetcher, admission, ending)
    except Exception as exc:
        # ANOTHER APP HOLDS THE WAREHOUSE (`CLAUDE.md`: wait for it, never route around it). The
        # page was undone and the record holds its place, so a Resume loses nothing, whichever
        # write met it: an entry write, a page's, or the one settling how the run ended.
        if not dbmod.another_app_holds_it(exc):
            raise
        said = f"another app holds the warehouse ({exc})"
        # THE ENDING IT CUT OFF IS NAMED, or that error is recorded nowhere until a Resume meets it.
        if ending:
            said += f", as this run stopped on {ending[0]}"
    # THIS WAITS AS LONG AS IT TAKES: nothing else can say what became of the job, and given up,
    # the row would stay `running` with no worker.
    while True:
        # A FAILED WRITE LEAVES ITS `BEGIN` OPEN, and a write inside it is an upgrade SQLite
        # refuses at once, with no wait, and for good once another app has written.
        conn.rollback()
        # What a Resume does is the committed record's, for that is the one it reads.
        record = _record(job_ref, (jobs.get_job(conn, job_ref) or job).get("checkpoint_json"))
        try:
            directoryjob.log_politeness(conn, job["job_id"], source_key, fetcher)
            directoryjob.pause_because(conn, job, job_ref, source_key, said, _resuming(record))
            return jobs.get_job(conn, job_ref) or job
        except sqlite3.OperationalError as exc:
            if not dbmod.another_app_holds_it(exc):
                raise
            print(f"{job_ref}: waiting to settle this job: {said}", file=sys.stderr)


def _crawl(conn: sqlite3.Connection, job: dict, job_ref: str, source: tenders.TenderSource,
           fetcher, admission, ending: list[str]) -> dict:
    """The run, each of its endings settling the row. A write that meets another app leaves from
    wherever it was, for `run_tender_crawl_job_once` to pause, and `ending` tells it what stopped
    the run if that write was the one settling it."""
    from . import jobs

    source_key = source.key
    job_id = job["job_id"]
    record = _record(job_ref, job.get("checkpoint_json"))
    record.setdefault("areas_read", [])
    record.setdefault("unread", {})
    # THE JOB'S, NOT THIS PASS'S: a resume carries on what the passes before it counted, and
    # the job's outcome rests on all of it.
    tally = wc.Tally(**{name: int((job["counters"] or {}).get(name, 0)) for name in COUNTERS})
    site_id = _site_id(conn, source)
    state = source_state(conn, source_key)
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    plan = None

    def say(level: str, message: str) -> None:
        """The collector's words, into the job log, committed by the `keep` that follows.

        NO COMMIT HERE. Every refused notice is named, his ruling of 2026-10-31 (#1779), and
        a commit each measured 400-589 ms and 9.36 MB of WAL a 1,000 lines, against 13-15 ms
        and 0.2 MB for one. Nothing is left open across a request."""
        jobs.append_log(conn, job_id, message, level=level, source_key=source_key)

    def keep(**progress) -> None:
        """This job's record, counters and progress, written together and committed."""
        jobs._update(conn, job_id, checkpoint_json=json.dumps(record, ensure_ascii=False),
                     last_heartbeat_at=utc_now_iso(), **progress)
        jobs._merge_counters_column(conn, job_id,
                                    {name: getattr(tally, name) for name in COUNTERS})
        conn.commit()

    def stop_if_asked() -> None:
        """At a page boundary, after the page is committed: the owner's Pause or Cancel.

        HERE AND NOT IN THE FETCHER'S `on_request`, which runs after a response arrives,
        so a stop raised there throws away the page just paid for.
        """
        if not jobs.still_wanted(conn, job_ref):
            raise CrawlInterrupted(JobControl.CANCEL.value)
        control = jobs._control_of(conn, job_id)
        if control in {JobControl.PAUSE.value, JobControl.CANCEL.value}:
            raise CrawlInterrupted(control)

    @contextmanager
    def page_write():
        """Around one page's write: the warehouse's one writer, and inside it the seal, the
        only point where that answer cannot go stale (`capture._refuse_if_superseded`)."""
        with dbmod.write_lock(db_file):
            capture._refuse_if_superseded(conn)
            yield

    def what_comes_next() -> str:
        """The part of the job a stop leaves next, so what it says is what a Resume does: the
        areas, until an update holds every area its count named."""
        whole = {name for name, _ in record["count"]["areas"]} <= (
            state.areas_read | set(record["areas_read"]))
        return "changes" if whole and job["run_mode"] == RunMode.UPDATE.value else "areas"

    if record.get("phase") == "changes":
        jobs.note_a_re_entry(conn, job, unit="page(s)", source_key=source_key,
                             opening="reading the changes again from their start",
                             consequence="What it kept is not kept twice")
    elif record.get("phase") is None:
        jobs.note_a_re_entry(conn, job, unit="area(s)", source_key=source_key,
                             opening="counting again, then reading what is left",
                             consequence="The areas already read whole are not read again")
    else:
        jobs.note_a_re_entry(conn, job, unit="area(s)", source_key=source_key,
                             opening="going on from the next unread page",
                             consequence="The areas it read whole are not read again")
    jobs._update(conn, job_id, status=JobStatus.PREPARING.value, stage="counting notices",
                 current_source_key=source_key, last_heartbeat_at=utc_now_iso(),
                 **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    conn.commit()

    host = jobs.host_of_url(source.base_url, source_key)
    admit = admission.lane(host) if admission is not None else nullcontext()

    # HOW THE RUN TREATED THE SITE is said by every ending below, in the write that settles it, so
    # the summary is the last line (#1701, row 21). AND IT COMES FIRST FOR THE ROW'S SAKE: that write
    # opens the transaction, so the ending's re-read of the row holds SQLite's lock, the panel's
    # press waits, and its compare-and-swap misses. A leg with no request has no such line (#1927).
    try:
        with admit:
            if not jobs.still_wanted(conn, job_ref):
                say(LogLevel.INFO, "stopped while waiting for the site's turn, so nothing more "
                                   "was read")
                conn.commit()
                return jobs.get_job(conn, job_ref) or job
            plan = wc.count_areas(fetcher)
            tally.requests += 1
            # THE FIRST COUNT'S TIME IS KEPT ONCE. A resumed job counts again, and the
            # first pass over changes must still start from when the crawl began.
            record.setdefault("first_counted_at", utc_now_iso())
            record["count"] = {"counted_at": utc_now_iso(), "total": plan.total,
                               "requests": plan.requests, "unlisted": plan.unlisted,
                               "areas": [[area.name, area.count] for area in plan.areas]}
            record["phase"] = what_comes_next()
            held = state.areas_read | set(record["areas_read"])
            resume = record.get("area") or {}
            # THE AREA A STOP CAME INSIDE IS READ FIRST. An area left unread earlier comes
            # back on a resume, and read before it, it would end the resume point.
            to_read = sorted((area for area in plan.areas if area.name not in held),
                             key=lambda area: area.name != resume.get("name"))
            resumed = to_read[0] if to_read and to_read[0].name == resume.get("name") else None
            first_page = 0
            if resumed is not None and resume["count"] == resumed.count:
                first_page = resume["next_page"]
            left = wc.requests_for(to_read) - first_page
            if not held:
                say(LogLevel.INFO, wc.count_line(plan))
            elif to_read:
                # THE COUNT INCLUDED, as `count_line`'s figure is (`Plan.requests`): the
                # line and the cost question part 3b-2b asks give one number (#1701, 13a).
                say(LogLevel.INFO, f"{wc._counted(len(to_read), 'area')} not read yet: "
                                   f"{wc._counted(left, 'request')}")
            elif job["run_mode"] == RunMode.INITIAL_CRAWL.value:
                say(LogLevel.INFO, "every area is already read, so an initial crawl has "
                                   "nothing to read")
            if plan.unlisted:
                # HIS RULING OF 2026-10-25 (#1647): named, and the crawl starts.
                one = plan.unlisted == 1
                say(LogLevel.WARNING,
                    f"{wc._counted(plan.unlisted, 'notice')} the Bank lists in no area: an "
                    f"area pass cannot read {'it' if one else 'them'}, and the pass over "
                    f"changes reads {'it' if one else 'each one'} when it changes")
            if resumed is not None and resume["count"] != resumed.count:
                # ONLY THE RECORD CAN SEE THIS MOVE: `read_area`'s guard compares with the
                # count just taken. A notice gone from a page read before the stop slides one
                # in from the next page read, and that one would be in neither.
                say(LogLevel.INFO, f"{resumed.name}: the Bank now counts "
                                   f"{wc._counted(resumed.count, 'notice')}, not the "
                                   f"{resume['count']:,} it counted before this job stopped; "
                                   "reading it again from its first page")
            # THE JOB'S FIGURES, NOT THIS PASS'S; the count is in both `tally` and `left`.
            jobs.record_source_fetch(conn, job_id, source_key,
                                     expected=tally.requests - 1 + left,
                                     basis="declared", requests=tally.requests)
            keep(progress_done=len(record["areas_read"]),
                 progress_total=len(record["areas_read"]) + len(to_read))
            # A STOP ASKED DURING THE COUNT IS HONOURED BEFORE `running` IS CLAIMED: that
            # write would erase the transitional state the panel is showing him.
            stop_if_asked()
            jobs._update(conn, job_id, status=JobStatus.RUNNING.value)
            conn.commit()

            counted = {area.name: area.count for area in to_read}

            def page_kept(name: str, page: int) -> None:
                record["area"] = {"name": name, "next_page": page + 1, "count": counted[name]}
                jobs.record_source_fetch(conn, job_id, source_key, requests=tally.requests)
                keep()
                stop_if_asked()

            for area in to_read:
                jobs._update(conn, job_id, stage=f"reading {area.name}")
                conn.commit()
                read = wc.read_area(conn, fetcher, source_site_id=site_id, area=area,
                                    tally=tally, log=say, lock=page_write,
                                    first_page=first_page if area is resumed else 0,
                                    crawl_job_id=job_id, on_page=page_kept)
                record.pop("area", None)
                if read.complete:
                    record["areas_read"].append(area.name)
                    record["unread"].pop(area.name, None)
                else:
                    record["unread"][area.name] = read.reason
                record["phase"] = what_comes_next()
                keep(progress_done=len(record["areas_read"]))
                # A FAILED PAGE IS A BOUNDARY TOO: `page_kept` never ran for it, and on a Bank
                # failing every page nothing else would ever answer his Pause or Cancel.
                stop_if_asked()

            if record["phase"] == "changes":
                since = SourceState(
                    count=record["count"], areas_read=frozenset(),
                    first_counted_at=state.first_counted_at or record["first_counted_at"],
                    held_whole_at=state.held_whole_at).since()
                say(LogLevel.INFO, f"every area read; reading the notices changed since "
                                   f"{since}")

                def changes_page_kept(page: int, notices: int) -> None:
                    say(LogLevel.INFO, f"changes, page {page + 1}: "
                                       f"{wc._counted(notices, 'notice')}")
                    jobs.record_source_fetch(conn, job_id, source_key,
                                             requests=tally.requests)
                    keep(progress_done=page + 1, progress_total=0)
                    stop_if_asked()

                jobs._update(conn, job_id, stage="reading changes")
                keep(progress_done=0, progress_total=0)
                outcome = wc.read_changes(conn, fetcher, source_site_id=site_id,
                                          since=since, tally=tally, log=say, lock=page_write,
                                          crawl_job_id=job_id, on_page=changes_page_kept)
                record["changes"] = {
                    "since": since, "complete": outcome.complete,
                    "pages": outcome.pages_read, "reason": outcome.reason,
                    # THE NEXT PASS'S POINT, kept only when this one is whole: one cut
                    # short leaves the notices behind it older than this (#1765).
                    "held_whole_at": (wc.newest_held(conn, site_id)
                                      if outcome.complete else None)}
                keep()
    except CrawlInterrupted as stop:
        directoryjob.log_politeness(conn, job_id, source_key, fetcher)
        if not jobs.still_wanted(conn, job_ref):
            # THE ROW OUTRANKS THE INSTRUCTION, as at every other stop: a job something else
            # already settled is not settled again, and the panel's Cancel settles a `pausing`
            # job at once, while this one still holds its page.
            say(LogLevel.INFO, "stopped between pages: this job is already settled, so "
                               "nothing more is read")
        elif stop.control == JobControl.PAUSE.value:
            jobs._update(conn, job_id, status=JobStatus.PAUSED.value,
                         control=JobControl.NONE.value, stage=None,
                         last_heartbeat_at=utc_now_iso())
            say(LogLevel.INFO, f"paused between pages. {_resuming(record)}")
        else:
            refused = _refusals(tally.errors)
            say(LogLevel.INFO, "cancelled between pages. What was kept stays kept, and an update "
                               f"reads the rest{f'. {refused}' if refused else ''}")
            jobs._finish(conn, job_id, JobStatus.CANCELLED, refused or None)
        conn.commit()
        return jobs.get_job(conn, job_ref) or job
    except CrawlBlocked as blocked:
        ending.append(_named(blocked))
        directoryjob.log_politeness(conn, job_id, source_key, fetcher)
        directoryjob.pause_for_the_site(conn, job, job_ref, source_key, blocked,
                                        _resuming(record))
        return jobs.get_job(conn, job_ref) or job
    except Exception as exc:
        # Any other `OperationalError` is a fault of the warehouse, and fails below.
        if dbmod.another_app_holds_it(exc):
            raise
        named = _named(exc)
        ending.append(named)
        directoryjob.log_politeness(conn, job_id, source_key, fetcher)
        # THE CONSEQUENCE LEADS, so the two-line clamp on Jobs keeps it (#1701, row 24).
        if plan is None:
            # A RESUMED JOB HOLDS WHAT ITS EARLIER LEGS KEPT, and only it has made a request.
            lead = ("The count failed; an update reads the rest." if tally.requests
                    else "The count failed, so this run read nothing.")
        elif record.get("phase") == "changes":
            lead = "The pass over changes failed, and the next update reads it again."
        else:
            held = state.areas_read | set(record["areas_read"])
            lead = (f"{sum(area.name in held for area in plan.areas)} of {len(plan.areas)} "
                    "areas read; an update reads the rest.")
        refused = _refusals(tally.errors)
        summary = f"{lead} {named}{f'. {refused}' if refused else ''}"
        if jobs.still_wanted(conn, job_ref):
            jobs._finish(conn, job_id, JobStatus.FAILED, summary)
            say(LogLevel.ERROR, summary)
        else:
            say(LogLevel.ERROR, f"{summary}{directoryjob.ALREADY_SETTLED}")
        conn.commit()
        raise

    directoryjob.log_politeness(conn, job_id, source_key, fetcher)
    # WHAT IS LEFT, THE CONSEQUENCE FIRST, so the two-line clamp on Jobs keeps it (#1701,
    # row 23): areas an update reads first, then a pass cut short, then what this run refused,
    # each already named in the log by its id (#1779: never a stop). An area with a refusal is held
    # whole like any other.
    said = []
    if record["unread"]:
        missed = record["unread"]
        said.append(f"{wc._counted(len(missed), 'area')} not read; an update reads "
                    f"{'it' if len(missed) == 1 else 'them'} first. {_reasons(missed)}")
    if record.get("changes") and not record["changes"]["complete"]:
        said.append(f"the pass over changes stopped: {record['changes']['reason']}. The next "
                    f"update reads again from {record['changes']['since']}.")
    refused = _refusals(tally.errors)
    if refused:
        said.append(refused)
    summary = " ".join(said)
    if not jobs.still_wanted(conn, job_ref):
        say(LogLevel.WARNING if said else LogLevel.INFO,
            f"{summary or 'every page it read is kept'}{directoryjob.ALREADY_SETTLED}")
    elif said:
        jobs._finish(conn, job_id, JobStatus.COMPLETED_WITH_ERRORS, summary)
        say(LogLevel.WARNING, summary)
    else:
        jobs._finish(conn, job_id, JobStatus.COMPLETED, None)
    conn.commit()
    return jobs.get_job(conn, job_ref)
