"""When the backup goes to Drive, decided entirely by the owner.

Decision 12 said the frequency is a setting. The owner then asked for the whole
thing to be his: «اعمل اعدادات بحيث يمكن للمتسخدم التحكم الكامل فى ذلك الامر».

So this holds no policy of its own. It answers one question — "should a backup
run right now?" — from the settings and the clock, and every branch of the
answer names WHICH setting decided it, because a backup that did not happen is
indistinguishable from one that failed unless something says which.

THE NUMBERS THE CHOICES ARE ABOUT, measured on the owner's warehouse:

    the bundle          209 MB
    what is uploaded     33 MB   compressed in one second

Thirty-three megabytes is small enough that "after every change" is affordable
and large enough that "every hour regardless" is not. Both are offered; neither
is imposed.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from . import settings

#: How the owner wants it decided. Every value is a whole answer to "when",
#: not a modifier on another one.
WHEN_OFF = "off"
WHEN_AFTER_CHANGE = "after_change"
WHEN_DAILY = "daily"
WHEN_MANUAL = "manual"

WHEN_VALUES = (WHEN_AFTER_CHANGE, WHEN_DAILY, WHEN_MANUAL, WHEN_OFF)


@dataclass
class Decision:
    """Whether to back up now, and which setting said so.

    `because` is not decoration. A backup that did not happen looks exactly like
    one that failed, and the Profile page has to be able to say "you asked for
    manual only" rather than leaving the owner to wonder.
    """
    run: bool
    because: str
    setting: str = ""

    @property
    def blocked(self) -> bool:
        return not self.run


def _int(conn: sqlite3.Connection, key: str, fallback: int) -> int:
    try:
        return int((settings.get(conn, key) or "").strip())
    except (ValueError, TypeError):
        # A number the owner typed wrongly must not stop backups altogether.
        # The default is used and the setting keeps whatever he typed, so the
        # page can still show it back to him.
        return fallback


def _stamp(moment: datetime) -> str:
    return moment.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_stamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def should_back_up(conn: sqlite3.Connection, *, changed: bool = False,
                   manual: bool = False,
                   now: datetime | None = None) -> Decision:
    """The one question, answered from the owner's settings and nothing else.

    `manual` is his own press and outranks everything except OFF: a person who
    just pressed Back up now is not asking to be told about a schedule.
    """
    moment = (now or datetime.now(UTC)).replace(microsecond=0)
    when = (settings.get(conn, "backup_when") or WHEN_AFTER_CHANGE).strip()

    if when == WHEN_OFF:
        # Even a press is refused here, and deliberately: "off" that still
        # uploads when a button is pressed is not off.
        return Decision(False, "backups to Drive are switched off", "backup_when")

    if manual:
        return Decision(True, "you asked for it now", "backup_when")

    if when == WHEN_MANUAL:
        return Decision(False, "you asked for backups only when you press the button",
                        "backup_when")

    last = _read_stamp(settings.get(conn, "backup_last_uploaded_at") or "")

    if when == WHEN_DAILY:
        if last is None:
            return Decision(True, "nothing has been backed up from this device yet",
                            "backup_when")
        due = last + timedelta(hours=_int(conn, "backup_every_hours", 24))
        if moment < due:
            left = int((due - moment).total_seconds() // 60)
            return Decision(False, f"the next backup is due in {left} minutes",
                            "backup_every_hours")
        return Decision(True, "the interval you set has passed", "backup_every_hours")

    # WHEN_AFTER_CHANGE, which is the default.
    if not changed:
        return Decision(False, "nothing changed in this crawl", "backup_when")

    # THE CEILING, and the reason it exists. Twenty small crawls in a day is
    # twenty uploads of thirty-three megabytes, and the owner asked for
    # control rather than for a product that decides for him — so the ceiling
    # is his number too, and zero means "no ceiling".
    ceiling = _int(conn, "backup_min_gap_minutes", 0)
    if ceiling and last is not None and moment < last + timedelta(minutes=ceiling):
        left = int((last + timedelta(minutes=ceiling) - moment).total_seconds() // 60)
        return Decision(False,
                        f"something changed, and the shortest gap you set has "
                        f"{left} minutes left",
                        "backup_min_gap_minutes")
    return Decision(True, "this crawl changed something", "backup_when")


def record_upload(conn: sqlite3.Connection, now: datetime | None = None) -> str:
    """Remember when the last backup reached Drive.

    Written only after the upload SUCCEEDS. Stamping the attempt would make a
    failed upload postpone the next one, which is the opposite of what anyone
    would want from a backup.
    """
    stamp = _stamp(now or datetime.now(UTC))
    settings.save(conn, {"backup_last_uploaded_at": stamp})
    return stamp
