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
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import timedelta

from . import capture, catalog, directoryjob, source_settings, tenders
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
COUNTERS = ("requests", "notices", "releases_new", "releases_unchanged", "errors")

#: The modes a tender crawl runs. A full rebuild is not one (#1701 Q3): the history keeps
#: every notice it read, and an update reads what changed. History backfill is a price mode.
RUNS = (RunMode.INITIAL_CRAWL.value, RunMode.UPDATE.value)


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

    job_id = job["job_id"]
    record = _record(job_ref, job.get("checkpoint_json"))
    record.setdefault("areas_read", [])
    record.setdefault("unread", {})
    tally = wc.Tally(**{name: int((job["counters"] or {}).get(name, 0)) for name in COUNTERS})
    errors_before = tally.errors
    site_id = _site_id(conn, source)
    state = source_state(conn, source_key)

    def say(level: str, message: str) -> None:
        """The collector's words, into the job log. The collector calls it outside every
        page's transaction (#1765), so committing here commits nothing half-kept."""
        jobs.append_log(conn, job_id, message, level=level, source_key=source_key)
        conn.commit()

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

    jobs.note_a_re_entry(conn, job, unit="area(s)", source_key=source_key,
                         consequence="The areas it read whole are not read again")
    jobs._update(conn, job_id, status=JobStatus.PREPARING.value, stage="counting notices",
                 current_source_key=source_key, last_heartbeat_at=utc_now_iso(),
                 **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    conn.commit()

    fetcher = source_fetcher(source_settings.effective(conn, source_key, source),
                             capture.crawl_settings(conn))
    host = jobs.host_of_url(source.base_url, source_key)
    admit = admission.lane(host) if admission is not None else nullcontext()
    try:
        with admit:
            if not jobs.still_wanted(conn, job_ref):
                say(LogLevel.INFO, "stopped while waiting for the site's turn, so nothing "
                                   "was read")
                return jobs.get_job(conn, job_ref) or job
            plan = wc.count_areas(fetcher)
            tally.requests += 1
            # THE FIRST COUNT'S TIME IS KEPT ONCE. A resumed job counts again, and the
            # first pass over changes must still start from when the crawl began.
            record.setdefault("first_counted_at", utc_now_iso())
            record["count"] = {"counted_at": utc_now_iso(), "total": plan.total,
                               "requests": plan.requests,
                               "areas": [[area.name, area.count] for area in plan.areas]}
            held = state.areas_read | set(record["areas_read"])
            to_read = [area for area in plan.areas if area.name not in held]
            asked = sum(area.pages for area in to_read)
            if not held:
                say(LogLevel.INFO, wc.count_line(plan))
            elif to_read:
                # THE COUNT INCLUDED, as `count_line`'s figure is (`Plan.requests`): the
                # line and the cost question part 3b-2b asks give one number (#1701, 13a).
                say(LogLevel.INFO, f"{wc._counted(len(to_read), 'area')} not read yet: "
                                   f"{1 + asked:,} requests")
            jobs.record_source_fetch(conn, job_id, source_key, expected=1 + asked,
                                     basis="declared", requests=tally.requests)
            keep(progress_done=0, progress_total=len(to_read))
            # A STOP ASKED DURING THE COUNT IS HONOURED BEFORE `running` IS CLAIMED: that
            # write would erase the transitional state the panel is showing him.
            stop_if_asked()
            jobs._update(conn, job_id, status=JobStatus.RUNNING.value)
            conn.commit()

            done = 0
            for area in to_read:
                resume = record.get("area") or {}
                first_page = int(resume.get("next_page", 0)) if resume.get("name") == area.name else 0

                def page_kept(name: str, page: int) -> None:
                    record["area"] = {"name": name, "next_page": page + 1}
                    jobs.record_source_fetch(conn, job_id, source_key,
                                             requests=tally.requests)
                    keep()
                    stop_if_asked()

                jobs._update(conn, job_id, stage=f"reading {area.name}")
                conn.commit()
                read = wc.read_area(conn, fetcher, source_site_id=site_id, area=area,
                                    tally=tally, log=say, first_page=first_page,
                                    crawl_job_id=job_id, on_page=page_kept)
                record.pop("area", None)
                if read.complete:
                    record["areas_read"].append(area.name)
                    record["unread"].pop(area.name, None)
                    done += 1
                else:
                    record["unread"][area.name] = read.reason
                keep(progress_done=done)

            whole = {area.name for area in plan.areas} <= (
                state.areas_read | set(record["areas_read"]))
            if whole and job["run_mode"] == RunMode.UPDATE.value:
                since = SourceState(
                    count=record["count"], areas_read=frozenset(),
                    first_counted_at=state.first_counted_at or record["first_counted_at"],
                    held_whole_at=state.held_whole_at).since()
                say(LogLevel.INFO, f"every area read; reading the notices changed since "
                                   f"{since}")

                def changes_page_kept(page: int, notices: int) -> None:
                    say(LogLevel.INFO, f"changes: {notices:,} notices in 1 request")
                    jobs.record_source_fetch(conn, job_id, source_key,
                                             requests=tally.requests)
                    keep(progress_done=page + 1, progress_total=0)
                    stop_if_asked()

                jobs._update(conn, job_id, stage="reading changes", progress_done=0,
                             progress_total=0)
                conn.commit()
                outcome = wc.read_changes(conn, fetcher, source_site_id=site_id,
                                          since=since, tally=tally, log=say,
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
        if stop.control == JobControl.PAUSE.value:
            jobs._update(conn, job_id, status=JobStatus.PAUSED.value,
                         control=JobControl.NONE.value, stage=None,
                         last_heartbeat_at=utc_now_iso())
            say(LogLevel.INFO, "paused between pages. Resuming goes on from the next "
                               "unread page, and the areas read whole are not read again")
        elif not jobs.still_wanted(conn, job_ref):
            # THE ROW OUTRANKS THE INSTRUCTION, as at every other stop: a job something
            # else already settled is not settled again.
            say(LogLevel.INFO, "stopped between pages: this job is already settled, so "
                               "nothing more is read")
        else:
            say(LogLevel.INFO, "cancelled between pages. What was kept stays kept, and an "
                               "update reads the rest")
            jobs._finish(conn, job_id, JobStatus.CANCELLED, None)
            conn.commit()
        return jobs.get_job(conn, job_ref) or job
    except CrawlBlocked as blocked:
        directoryjob.pause_for_the_site(
            conn, job, job_ref, source_key, blocked,
            "Resuming goes on from the next unread page")
        return jobs.get_job(conn, job_ref) or job
    except Exception as exc:
        say(LogLevel.ERROR, f"failed: {exc}")
        jobs._finish(conn, job_id, JobStatus.FAILED, str(exc))
        conn.commit()
        raise
    finally:
        directoryjob.log_politeness(conn, job_id, source_key, fetcher)
        conn.commit()

    # WHAT IS LEFT, THE CONSEQUENCE FIRST, so the two-line clamp on Jobs keeps it (#1701,
    # row 23): areas an update reads first, then a pass cut short, then the notices this
    # run refused, each already named in the log by its id (#1779: never a stop).
    said = []
    if record["unread"]:
        missed = record["unread"]
        said.append(f"{len(missed)} area{'' if len(missed) == 1 else 's'} not read; an "
                    f"update reads {'it' if len(missed) == 1 else 'them'} first. "
                    f"{_reasons(missed)}")
    if record.get("changes") and not record["changes"]["complete"]:
        said.append(f"the pass over changes stopped: {record['changes']['reason']}. The next "
                    f"update reads again from {record['changes']['since']}")
    refused = tally.errors - errors_before
    if refused:
        said.append(f"{wc._counted(refused, 'notice')} not kept; "
                    f"{'it is' if refused == 1 else 'each is'} named in the log by its id.")
    if said:
        summary = " ".join(said)
        say(LogLevel.WARNING, summary)
        jobs._finish(conn, job_id, JobStatus.COMPLETED_WITH_ERRORS, summary)
    else:
        jobs._finish(conn, job_id, JobStatus.COMPLETED, None)
    conn.commit()
    return jobs.get_job(conn, job_ref)
