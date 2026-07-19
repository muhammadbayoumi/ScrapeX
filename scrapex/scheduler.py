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
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .jobs import create_job, list_jobs
from .vocab import (
    BLOCKING_JOB_STATUSES, MissedRunPolicy, OverlapPolicy, RunMode, ScheduleFrequency,
)

ISO = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(dt_timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, ISO).replace(tzinfo=dt_timezone.utc)


def _format_iso(value: datetime) -> str:
    return value.astimezone(dt_timezone.utc).strftime(ISO)


def _zone(name: str):
    """Resolve an IANA zone, falling back to fixed UTC.

    The fallback is stdlib UTC, NOT ZoneInfo("UTC"): Windows ships no system tz
    database, so on a machine without `tzdata` even "UTC" raises — a fallback
    that can itself fail is no fallback at all.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return dt_timezone.utc


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
        return candidate.astimezone(dt_timezone.utc)

    if frequency == ScheduleFrequency.WEEKLY.value:
        target = 0 if weekday is None else int(weekday) % 7
        days_ahead = (target - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= local:
            candidate += timedelta(days=7)
        return candidate.astimezone(dt_timezone.utc)

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


def _source_is_busy(conn: sqlite3.Connection, source_key: str) -> bool:
    """Busy = occupying the worker or waiting for it.

    Deliberately NOT "any non-terminal job": `paused` and `requires_review` wait
    on the OWNER and never advance on their own, so counting them as busy would
    silently stop that source's schedule from ever firing again.
    """
    return any(source_key in job["source_keys"] and job["status"] in BLOCKING_JOB_STATUSES
               for job in list_jobs(conn, limit=200, active_only=True))


def fire_due(conn: sqlite3.Connection, now: datetime | None = None) -> list[str]:
    """Queue a job for every due schedule. Returns the job_refs created.

    Applies both policies at the moment of firing: a slot missed while the
    machine was off obeys missed_run_policy, and a source whose previous run is
    still going obeys overlap_policy.
    """
    now = now or utcnow()
    created: list[str] = []
    for schedule in due_schedules(conn, now):
        due_at = _parse_iso(schedule["next_run_at"])
        overdue = due_at is not None and (now - due_at) > timedelta(minutes=1)

        if overdue and schedule["missed_run_policy"] == MissedRunPolicy.SKIP.value:
            _rearm(conn, schedule, now, fired=False)
            continue
        if (schedule["overlap_policy"] == OverlapPolicy.SKIP.value
                and _source_is_busy(conn, schedule["source_key"])):
            _rearm(conn, schedule, now, fired=False)
            continue

        # Re-arm BEFORE queueing: create_job commits on its own, so if anything
        # fails between the two the worst outcome is a lost run rather than a
        # duplicated crawl that re-arms on the next tick and fires again.
        _rearm(conn, schedule, now, fired=True)
        conn.commit()
        created.append(create_job(conn, [schedule["source_key"]], schedule["run_mode"]))
    conn.commit()
    return created
