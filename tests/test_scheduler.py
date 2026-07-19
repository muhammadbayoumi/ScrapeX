"""Spec 26: schedule maths + the two policies that make missed slots honest."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from scrapex import db as dbmod
from scrapex.jobs import create_job, get_job, list_jobs
from scrapex.scheduler import (
    compute_next_run, due_schedules, fire_due, get_schedule, list_schedules, upsert_schedule,
)
from scrapex.vocab import MissedRunPolicy, OverlapPolicy, ScheduleFrequency


def utc(y, m, d, hh=0, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=dt_timezone.utc)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


# ---- next-run maths ----------------------------------------------------------

def test_daily_next_run_is_strictly_in_the_future():
    now = utc(2026, 7, 20, 8, 0)
    assert compute_next_run("daily", "09:00", "UTC", None, now) == utc(2026, 7, 20, 9, 0)
    # already past today -> tomorrow
    assert compute_next_run("daily", "07:00", "UTC", None, now) == utc(2026, 7, 21, 7, 0)


def test_exactly_on_the_slot_moves_to_the_next_one():
    now = utc(2026, 7, 20, 9, 0)
    assert compute_next_run("daily", "09:00", "UTC", None, now) == utc(2026, 7, 21, 9, 0)


def test_timezone_is_honoured():
    """09:00 Asia/Riyadh is 06:00 UTC — the owner's clock, not the server's."""
    now = utc(2026, 7, 20, 0, 0)
    assert compute_next_run("daily", "09:00", "Asia/Riyadh", None, now) == utc(2026, 7, 20, 6, 0)


def test_unknown_timezone_falls_back_instead_of_breaking():
    now = utc(2026, 7, 20, 0, 0)
    assert compute_next_run("daily", "09:00", "Mars/Olympus", None, now) == utc(2026, 7, 20, 9, 0)


def test_weekly_lands_on_the_requested_weekday():
    now = utc(2026, 7, 20, 10, 0)          # a Monday
    # weekday 2 = Wednesday
    assert compute_next_run("weekly", "09:00", "UTC", 2, now) == utc(2026, 7, 22, 9, 0)
    # same weekday but the time already passed -> next week
    assert compute_next_run("weekly", "09:00", "UTC", 0, now) == utc(2026, 7, 27, 9, 0)


def test_manual_never_schedules():
    assert compute_next_run("manual", "09:00", "UTC", None, utc(2026, 7, 20)) is None


def test_malformed_time_falls_back_to_nine():
    assert compute_next_run("daily", "not-a-time", "UTC", None, utc(2026, 7, 20, 0, 0)) \
        == utc(2026, 7, 20, 9, 0)


# ---- persistence -------------------------------------------------------------

def test_upsert_arms_the_next_run_and_replaces_cleanly(conn):
    s = upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00",
                        now=utc(2026, 7, 20, 8, 0))
    assert s["next_run_at"] == "2026-07-20T09:00:00Z" and s["enabled"] == 1

    upsert_schedule(conn, "SHOP", frequency="weekly", run_at="06:00", weekday=4,
                    now=utc(2026, 7, 20, 8, 0))
    assert len(list_schedules(conn)) == 1          # one schedule per source
    assert get_schedule(conn, "SHOP")["frequency"] == "weekly"


def test_disabled_schedule_is_not_armed_and_not_due(conn):
    upsert_schedule(conn, "SHOP", frequency="daily", enabled=False, now=utc(2026, 7, 20, 8, 0))
    assert get_schedule(conn, "SHOP")["next_run_at"] is None
    assert due_schedules(conn, utc(2026, 7, 30)) == []


def test_manual_schedule_is_never_due(conn):
    upsert_schedule(conn, "SHOP", frequency="manual", now=utc(2026, 7, 20, 8, 0))
    assert due_schedules(conn, utc(2027, 1, 1)) == []


# ---- firing ------------------------------------------------------------------

def test_due_schedule_queues_a_job_and_rearms(conn):
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00", now=utc(2026, 7, 20, 8, 0))
    refs = fire_due(conn, utc(2026, 7, 20, 9, 0))
    assert len(refs) == 1
    job = get_job(conn, refs[0])
    assert job["source_keys"] == ["SHOP"] and job["status"] == "queued"
    # re-armed for tomorrow, and it does not fire twice for the same slot
    assert get_schedule(conn, "SHOP")["next_run_at"] == "2026-07-21T09:00:00Z"
    assert fire_due(conn, utc(2026, 7, 20, 9, 30)) == []


def test_a_week_offline_fires_once_not_seven_times(conn):
    """The honest bit: we cannot wake a sleeping machine, so catch-up must not
    stampede when it finally comes back."""
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00", now=utc(2026, 7, 20, 8, 0))
    refs = fire_due(conn, utc(2026, 7, 27, 14, 0))     # a week later
    assert len(refs) == 1
    assert get_schedule(conn, "SHOP")["next_run_at"] == "2026-07-28T09:00:00Z"


def test_missed_policy_skip_does_not_run_but_still_rearms(conn):
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00",
                    missed_run_policy=MissedRunPolicy.SKIP.value, now=utc(2026, 7, 20, 8, 0))
    assert fire_due(conn, utc(2026, 7, 27, 14, 0)) == []
    assert get_schedule(conn, "SHOP")["next_run_at"] == "2026-07-28T09:00:00Z"
    assert get_schedule(conn, "SHOP")["last_run_at"] is None    # it genuinely did not run


def test_on_time_slot_runs_even_under_skip_policy(conn):
    """`skip` is about MISSED slots, not punctual ones."""
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00",
                    missed_run_policy=MissedRunPolicy.SKIP.value, now=utc(2026, 7, 20, 8, 0))
    assert len(fire_due(conn, utc(2026, 7, 20, 9, 0))) == 1


def test_overlap_skip_drops_the_occurrence_when_still_running(conn):
    create_job(conn, ["SHOP"])                       # an active job for this source
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00",
                    overlap_policy=OverlapPolicy.SKIP.value, now=utc(2026, 7, 20, 8, 0))
    assert fire_due(conn, utc(2026, 7, 20, 9, 0)) == []
    assert get_schedule(conn, "SHOP")["next_run_at"] == "2026-07-21T09:00:00Z"


def test_overlap_queue_lines_up_behind_the_running_one(conn):
    create_job(conn, ["SHOP"])
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00",
                    overlap_policy=OverlapPolicy.QUEUE.value, now=utc(2026, 7, 20, 8, 0))
    assert len(fire_due(conn, utc(2026, 7, 20, 9, 0))) == 1
    assert len(list_jobs(conn, active_only=True)) == 2


def test_schedule_carries_its_run_mode_into_the_job(conn):
    upsert_schedule(conn, "SHOP", frequency="daily", run_at="09:00",
                    run_mode="initial_crawl", now=utc(2026, 7, 20, 8, 0))
    ref = fire_due(conn, utc(2026, 7, 20, 9, 0))[0]
    assert get_job(conn, ref)["run_mode"] == "initial_crawl"


def test_out_of_range_time_falls_back_instead_of_raising():
    assert compute_next_run("daily", "99:99", "UTC", None, utc(2026, 7, 20, 0, 0)) \
        == utc(2026, 7, 20, 9, 0)


def test_dst_fall_back_does_not_fire_the_same_slot_twice():
    """Europe/London leaves BST on 2026-10-25; 01:30 happens twice that morning."""
    from datetime import datetime, timezone as tz
    from zoneinfo import ZoneInfo
    london = ZoneInfo("Europe/London")
    # `after` sits inside the repeated hour, in its SECOND occurrence (fold=1).
    after = datetime(2026, 10, 25, 1, 45, tzinfo=london, fold=1).astimezone(tz.utc)
    nxt = compute_next_run("daily", "01:30", "Europe/London", None, after)
    assert nxt > after                      # strictly forward, never the repeat
    assert nxt.astimezone(london).date().day == 26
