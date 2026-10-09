"""Local-runtime scheduling (spec section 26).

WHAT THIS CAN AND CANNOT DO — stated plainly because the spec demands it:
a schedule only fires while the local runtime is running. Nothing here (and no
browser alarm) can wake a sleeping or powered-off machine. A slot that passes
while we are off is therefore a normal state, handled explicitly by
`missed_run_policy` rather than pretended away.

`now` is injected everywhere so the time maths is deterministic under test.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import jobs, source_settings
from .datasetjob import COLLECTING_KINDS
from .jobs import create_job, list_jobs
from .vocab import (
    BLOCKING_JOB_STATUSES,
    JobStatus,
    LogLevel,
    MissedRunPolicy,
    OverlapPolicy,
    RunMode,
    ScheduleFrequency,
)

#: The reason a skip row carries when another app held the warehouse's write lock at
#: the slot (his ruling D5 on #1596). The worker decides the skip at the slot and
#: writes this row once the lock is free, because writing it is itself a write.
LOCK_HELD_REASON = "skipped: another app is writing to the warehouse"

ISO = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, ISO).replace(tzinfo=UTC)


def _format_iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime(ISO)


def zone_exists(name: str) -> bool:
    """Can this IANA name actually resolve HERE? The web layer refuses a save
    it cannot honour: _zone's silent UTC fallback is right for FIRING (a crash
    at 09:00 helps nobody) and wrong for SAVING (a typo'd zone would silently
    mean UTC and the owner's 09:00 would fire at a different hour, unexplained
    forever)."""
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def _zone(name: str):
    """Resolve an IANA zone, falling back to fixed UTC.

    The fallback is stdlib UTC, NOT ZoneInfo("UTC"): Windows ships no system tz
    database, so on a machine without `tzdata` even "UTC" raises — a fallback
    that can itself fail is no fallback at all.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return UTC


def compute_next_run(frequency: str, run_at: str, tz_name: str, weekday: int | None,
                     after: datetime) -> datetime | None:
    """The next firing STRICTLY after `after`, in UTC. None for manual.

    Computed in the owner's timezone so 09:00 stays 09:00 across DST, then
    converted to UTC for storage.
    """
    if frequency == ScheduleFrequency.MANUAL.value:
        return None
    try:
        hour, minute = (int(part) for part in run_at.split(":", 1))
    except (ValueError, AttributeError):
        hour, minute = 9, 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        hour, minute = 9, 0          # out-of-range must fall back, never raise
    zone = _zone(tz_name)
    local = after.astimezone(zone)
    # fold=0 pins the FIRST occurrence of an ambiguous wall time. Without it a
    # re-arm landing inside a DST fall-back hour inherits `after`'s fold and can
    # select the repeated occurrence, firing the same daily slot twice.
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)

    if frequency == ScheduleFrequency.DAILY.value:
        if candidate <= local:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC)

    if frequency == ScheduleFrequency.WEEKLY.value:
        target = 0 if weekday is None else int(weekday) % 7
        days_ahead = (target - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= local:
            candidate += timedelta(days=7)
        return candidate.astimezone(UTC)

    return None


def upsert_schedule(conn: sqlite3.Connection, source_key: str, *, frequency: str = "manual",
                    run_at: str = "09:00", tz_name: str = "UTC", weekday: int | None = None,
                    run_mode: str = RunMode.UPDATE.value,
                    missed_run_policy: str = MissedRunPolicy.RUN_WHEN_AVAILABLE.value,
                    overlap_policy: str = OverlapPolicy.QUEUE.value,
                    enabled: bool = True, now: datetime | None = None) -> dict:
    """Create or replace this source's schedule and arm its next firing."""
    now = now or utcnow()
    next_run = compute_next_run(frequency, run_at, tz_name, weekday, now) if enabled else None
    conn.execute(
        "INSERT INTO schedule (source_key, frequency, run_at, timezone, weekday, run_mode, "
        " missed_run_policy, overlap_policy, enabled, next_run_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(source_key) DO UPDATE SET frequency=excluded.frequency, "
        " run_at=excluded.run_at, timezone=excluded.timezone, weekday=excluded.weekday, "
        " run_mode=excluded.run_mode, missed_run_policy=excluded.missed_run_policy, "
        " overlap_policy=excluded.overlap_policy, enabled=excluded.enabled, "
        " next_run_at=excluded.next_run_at",
        (source_key, frequency, run_at, tz_name, weekday, run_mode, missed_run_policy,
         overlap_policy, 1 if enabled else 0,
         _format_iso(next_run) if next_run else None),
    )
    return get_schedule(conn, source_key)


def get_schedule(conn: sqlite3.Connection, source_key: str) -> dict | None:
    row = conn.execute("SELECT * FROM schedule WHERE source_key = ?", (source_key,)).fetchone()
    return dict(row) if row is not None else None


def list_schedules(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM schedule ORDER BY source_key")]


def due_schedules(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    """Enabled schedules whose slot has arrived (or passed while we were off)."""
    now = now or utcnow()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM schedule WHERE enabled = 1 AND next_run_at IS NOT NULL "
        "AND next_run_at <= ? ORDER BY next_run_at", (_format_iso(now),))]


def _rearm(conn: sqlite3.Connection, schedule: dict, now: datetime, fired: bool) -> None:
    """Advance to the next slot AFTER NOW.

    Deliberately measured from `now`, not from the slot we missed: a runtime that
    was off for a week must fire at most once on catch-up, never seven times.
    """
    next_run = compute_next_run(schedule["frequency"], schedule["run_at"],
                                schedule["timezone"], schedule["weekday"], now)
    conn.execute(
        "UPDATE schedule SET next_run_at = ?, last_run_at = COALESCE(?, last_run_at) "
        "WHERE schedule_id = ?",
        (_format_iso(next_run) if next_run else None,
         _format_iso(now) if fired else None, schedule["schedule_id"]),
    )


def _blocking_job(conn: sqlite3.Connection, source_key: str) -> dict | None:
    """The job this source is busy with, or None.

    Busy = occupying the worker or waiting for it (`BLOCKING_JOB_STATUSES`), and, for a
    directory's collecting kinds only, PAUSED as well -- his ruling D3 on #1596: a
    paused directory crawl is a run waiting for him, and a scheduled one starting
    beside it would collect the same site twice. A paused PRICE job still does not
    count: `paused` and `requires_review` wait on the OWNER and never advance on their
    own, so counting them would silently stop that source's schedule for good.
    """
    for job in list_jobs(conn, limit=200, active_only=True):
        if source_key not in job["source_keys"]:
            continue
        if job["status"] in BLOCKING_JOB_STATUSES:
            return job
        if job["status"] == JobStatus.PAUSED.value and job["job_kind"] in COLLECTING_KINDS:
            return job
    return None


def _record_skip(conn: sqlite3.Connection, schedule: dict, reason: str) -> None:
    """A firing that did not run, written as a finished SKIPPED job he can read.

    The FAILED precedent in `fire_due` below, with the skip's status: created
    uncommitted so the worker never sees it queued, closed by `jobs._finish`, which
    commits it together with the caller's re-arm. The kind and mode are the ones the
    firing would have had.
    """
    ref = create_job(conn, [schedule["source_key"]], schedule["run_mode"], commit=False)
    job_id = jobs.get_job(conn, ref)["job_id"]
    jobs.append_log(conn, job_id, reason, level=LogLevel.INFO,
                    source_key=schedule["source_key"])
    jobs._finish(conn, job_id, JobStatus.SKIPPED, reason)


def fire_due(conn: sqlite3.Connection, now: datetime | None = None,
             manifest=None, held_out: Mapping[int, str] | None = None) -> list[str]:
    """Queue a job for every due schedule. Returns the job_refs queued.

    A slot missed while the machine was off obeys missed_run_policy. A source whose
    previous run is still going is SKIPPED, whatever `overlap_policy` says: the slot
    re-arms and a finished SKIPPED job names the run that blocked it (his rulings on
    #1596; the column stays, and nothing reads it any more).

    `held_out` maps schedule_id to the `next_run_at` that came due while another app
    held the write lock. Such a slot, still unchanged, is skipped the same way, with
    `LOCK_HELD_REASON`. Skip rows are not in the returned list: nothing was queued.

    With a manifest given, `active` finally MEANS something: a schedule for an
    inactive source re-arms without firing. The flag was documentation until
    now — the owner flipped it and nothing changed, which is the emptiest kind
    of switch. Manual runs from the panel are untouched: active gates the
    AUTOMATION, not the owner's hand.
    """
    now = now or utcnow()
    created: list[str] = []
    for schedule in due_schedules(conn, now):
        if manifest is not None:
            try:
                entry = manifest.get(schedule["source_key"])
            except LookupError:
                # REMOVED FROM THE MANIFEST, or known to no registry at all (#1609):
                # the engine passes a `SourceResolver`, whose `UnknownSource` is a
                # `LookupError` and not a `KeyError`. Caught as `KeyError` it escaped
                # this loop on every tick, and the worker skipped `_dispatch` with it --
                # no job started, his manual ones included.
                entry = None
            # HIS `active` FOR THIS SOURCE, over the manifest's (#1584): a source he
            # switched on in the panel fires, one he switched off does not, whatever
            # `sources.yaml` ships. A source the manifest does not name still never
            # fires here -- a directory's schedule is not this function's yet.
            if entry is None:
                _rearm(conn, schedule, now, fired=False)
                continue
            try:
                active = source_settings.effective(conn, entry.source_key, entry).active
            except source_settings.SourceSettingError as exc:
                # ONE SOURCE'S BROKEN RULES MUST NOT STOP EVERY OTHER. This raised out of
                # `fire_due`, and the worker loop calls it before `_dispatch`, so a
                # single bad entry stopped every job -- manual ones included -- on every
                # tick (#1589 review). `SourceEntry` now refuses such an entry when the
                # manifest loads; this is the second layer, for whatever reaches here
                # anyway. The slot is spent, and the refusal is a FAILED job naming the
                # source and the reason, where he reads every other run's outcome.
                #
                # A job and not a log line: the Run page is where he reads why a source
                # did not run, and a job is the record it lists. Closed FAILED by
                # `jobs._finish` -- the one place every runner stamps the end, status
                # and summary -- so nothing dispatches it. `_finish` commits.
                _rearm(conn, schedule, now, fired=False)
                ref = create_job(conn, [schedule["source_key"]], schedule["run_mode"],
                                 commit=False)
                job_id = jobs.get_job(conn, ref)["job_id"]
                reason = f"the scheduled run did not start: {exc}"
                jobs.append_log(conn, job_id, reason, level=LogLevel.ERROR,
                                source_key=schedule["source_key"])
                jobs._finish(conn, job_id, JobStatus.FAILED, reason)
                continue
            if not active:
                _rearm(conn, schedule, now, fired=False)
                continue
        # BEFORE the missed-run policy: a slot the lock held out was not missed by a
        # machine that was off, and a long hold must still leave its row.
        if (held_out is not None
                and held_out.get(schedule["schedule_id"]) == schedule["next_run_at"]):
            _rearm(conn, schedule, now, fired=False)
            _record_skip(conn, schedule, LOCK_HELD_REASON)
            continue
        due_at = _parse_iso(schedule["next_run_at"])
        overdue = due_at is not None and (now - due_at) > timedelta(minutes=1)

        if overdue and schedule["missed_run_policy"] == MissedRunPolicy.SKIP.value:
            _rearm(conn, schedule, now, fired=False)
            continue
        blocker = _blocking_job(conn, schedule["source_key"])
        if blocker is not None:
            _rearm(conn, schedule, now, fired=False)
            waiting = ("a paused run is waiting for you"
                       if blocker["status"] == JobStatus.PAUSED.value
                       else "a run is in progress")
            _record_skip(conn, schedule, f"skipped: {waiting} ({blocker['job_ref']})")
            continue

        # Re-arm BEFORE queueing: create_job commits on its own, so if anything
        # fails between the two the worst outcome is a lost run rather than a
        # duplicated crawl that re-arms on the next tick and fires again.
        _rearm(conn, schedule, now, fired=True)
        conn.commit()
        created.append(create_job(conn, [schedule["source_key"]], schedule["run_mode"]))
    conn.commit()
    return created
