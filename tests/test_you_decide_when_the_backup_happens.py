"""The owner decides when a backup runs, and the product never overrules him.

He asked for exactly this: «اعمل اعدادات بحيث يمكن للمتسخدم التحكم الكامل فى
ذلك الامر» — settings that give him full control, rather than a rule the product
picks and he lives with.

So this module holds no policy. It answers one question — should a backup run
right now? — from the settings and the clock, and every answer NAMES THE SETTING
that decided it. That is not decoration: a backup that did not happen looks
exactly like one that failed, and the Profile page has to be able to say "you
asked for manual only" instead of leaving him to guess.

THE NUMBERS THE CHOICES ARE ABOUT, measured on his own warehouse: the bundle is
209 MB and 33 MB compressed, in one second. Small enough that "after every
change" is affordable, large enough that "every hour regardless" is not.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scrapex import backupschedule as sched
from scrapex import db as dbmod
from scrapex import settings


def at(hours: float = 0) -> datetime:
    """A stated clock. A test that takes the real one fails for six hours a
    year, which this repository has already paid for once."""
    return (datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc)
            + timedelta(hours=hours))


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "s.db")
    dbmod.migrate(connection)
    return connection


def set_to(conn, **values):
    settings.save(conn, {k: str(v) for k, v in values.items()})


# ---- the default, and why it is the default ---------------------------------

def test_by_default_a_crawl_that_changed_something_is_backed_up(conn):
    decision = sched.should_back_up(conn, changed=True, now=at())

    assert decision.run
    assert decision.because == "this crawl changed something"


def test_by_default_a_crawl_that_changed_nothing_is_not(conn):
    """Thirty-three megabytes of identical data is the upload Decision 12 calls
    "not free"."""
    decision = sched.should_back_up(conn, changed=False, now=at())

    assert decision.blocked
    assert decision.because == "nothing changed in this crawl"
    assert decision.setting == "backup_when"


# ---- every answer names the setting that gave it ----------------------------

@pytest.mark.parametrize("when,changed,expect_setting", [
    ("off", True, "backup_when"),
    ("manual", True, "backup_when"),
    ("after_change", False, "backup_when"),
])
def test_a_refusal_always_names_the_setting_behind_it(conn, when, changed,
                                                      expect_setting):
    """A backup that did not happen is indistinguishable from one that failed
    unless something says which. Every branch is asserted, not a sample."""
    set_to(conn, backup_when=when)

    decision = sched.should_back_up(conn, changed=changed, now=at())

    assert decision.blocked
    assert decision.setting == expect_setting
    assert decision.because, "a refusal with no reason is a silent one"


# ---- off means off ----------------------------------------------------------

def test_off_refuses_even_a_press(conn):
    """"Off" that still uploads when a button is pressed is not off. This is
    the one place a deliberate press does not win."""
    set_to(conn, backup_when="off")

    assert sched.should_back_up(conn, changed=True, now=at()).blocked
    assert sched.should_back_up(conn, manual=True, now=at()).blocked


def test_a_press_outranks_every_schedule_except_off(conn):
    """Someone who just pressed "Back up now" is not asking to be told about a
    schedule."""
    for when in ("after_change", "daily", "manual"):
        set_to(conn, backup_when=when,
               backup_last_uploaded_at="2026-08-06T08:59:00Z")

        decision = sched.should_back_up(conn, manual=True, now=at())

        assert decision.run, f"a press was refused under {when}"
        assert decision.because == "you asked for it now"


# ---- the interval -----------------------------------------------------------

def test_a_daily_schedule_runs_once_and_then_waits(conn):
    set_to(conn, backup_when="daily", backup_every_hours=24)

    first = sched.should_back_up(conn, now=at())
    assert first.run
    assert "nothing has been backed up" in first.because

    sched.record_upload(conn, now=at())

    assert sched.should_back_up(conn, now=at(23)).blocked
    assert sched.should_back_up(conn, now=at(24)).run


def test_the_interval_is_the_owners_number_and_not_a_day(conn):
    """"Daily" is the label; the hours are his. Six-hourly is a setting change,
    not a code change."""
    set_to(conn, backup_when="daily", backup_every_hours=6)
    sched.record_upload(conn, now=at())

    assert sched.should_back_up(conn, now=at(5)).blocked
    assert sched.should_back_up(conn, now=at(6)).run


def test_a_waiting_schedule_says_how_long_is_left(conn):
    """"Not yet" with no idea how long is the same dead end as "locked" with no
    idea by whom."""
    set_to(conn, backup_when="daily", backup_every_hours=24)
    sched.record_upload(conn, now=at())

    decision = sched.should_back_up(conn, now=at(20))

    assert decision.blocked
    assert "240 minutes" in decision.because


# ---- the ceiling, which is his number too -----------------------------------

def test_no_ceiling_by_default_so_every_change_is_kept(conn):
    """Zero means no ceiling, and zero is the default: the product does not
    start by throttling him."""
    sched.record_upload(conn, now=at())

    assert sched.should_back_up(conn, changed=True, now=at(0.01)).run


def test_a_ceiling_he_sets_holds_back_the_twentieth_small_crawl(conn):
    """Twenty small crawls in a day is twenty uploads of thirty-three
    megabytes. He can decide that is fine, or decide it is not."""
    set_to(conn, backup_min_gap_minutes=60)
    sched.record_upload(conn, now=at())

    held = sched.should_back_up(conn, changed=True, now=at(0.5))
    assert held.blocked
    assert held.setting == "backup_min_gap_minutes"
    assert "30 minutes left" in held.because

    assert sched.should_back_up(conn, changed=True, now=at(1)).run


# ---- what a wrong number must not do ----------------------------------------

def test_a_number_typed_wrongly_does_not_stop_backups_altogether(conn):
    """The default is used and the setting KEEPS what he typed, so the page can
    still show it back to him. Silently rewriting it would hide the mistake and
    leave him wondering why the field will not stay as he set it."""
    set_to(conn, backup_when="daily", backup_every_hours="every day please")
    sched.record_upload(conn, now=at())

    assert sched.should_back_up(conn, now=at(23)).blocked
    assert sched.should_back_up(conn, now=at(24)).run
    assert settings.get(conn, "backup_every_hours") == "every day please"


def test_an_unknown_value_falls_back_to_the_default_rather_than_refusing(conn):
    """A setting corrupted by hand, or written by a newer build, must not leave
    the owner with no backups and no explanation."""
    settings.save(conn, {"backup_when": "whenever-i-feel-like-it"})

    decision = sched.should_back_up(conn, changed=True, now=at())

    assert decision.run, "an unrecognised setting stopped every backup"


# ---- the stamp --------------------------------------------------------------

def test_only_a_successful_upload_moves_the_clock(conn):
    """Stamping the ATTEMPT would let a failed upload postpone the next one,
    which is the opposite of what anyone wants from a backup. record_upload is
    called by the caller after Drive answers, and never before."""
    set_to(conn, backup_when="daily", backup_every_hours=24)

    # A failed upload records nothing, so the next check still says "due".
    assert sched.should_back_up(conn, now=at()).run
    assert sched.should_back_up(conn, now=at(1)).run

    sched.record_upload(conn, now=at(1))
    assert sched.should_back_up(conn, now=at(2)).blocked


def test_every_choice_the_panel_can_offer_is_a_choice_this_understands(conn):
    """The list the interface shows and the list this reads are the same list.
    A fifth option in a dropdown that falls through to the default here is a
    setting that silently does something else."""
    for when in sched.WHEN_VALUES:
        set_to(conn, backup_when=when)
        decision = sched.should_back_up(conn, changed=True, manual=False, now=at())
        assert decision.setting, f"{when} produced an answer that names no setting"
