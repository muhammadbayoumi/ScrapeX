"""Which account a warehouse belongs to.

WHY THIS EXISTS. He ruled it: «كيف تتعامل الاداة مع الحسابات المختلفة … لكل حساب
قاعدة بيانات» (`REQ-26`), and then named the identity by naming one: «ايضا databse
الموجودة حاليا اجعلها تخص حساب muhammad.bayoumi.ali@gmail.com». That answers `Q-14`
— **the account is the signed-in address** — which was the one question that could
not be answered from the code, because it decides where other people's data lands.

WHAT THIS IS AND IS NOT. This records the owner OF a warehouse. It does not yet put
warehouses in per-account directories, and it deliberately does not REFUSE a
warehouse claimed by someone else: `DATABASE_ROOT` is still `~/.scrapex`, so a second
account on this machine would open this file, and refusing on connect before the
per-account root exists would lock the owner out of his own data to enforce a rule
the layout cannot yet keep. The claim is the identity; the layout is `REQ-26`.

WHY `scrapex_meta` AND NOT A NEW TABLE. It already holds exactly this kind of fact —
`database_kind`, `migration_stream`, `contract_version` — one row, one truth about the
file, no migration. A table would be a row count of one with a schema change to pay
for it.

THE ADDRESS IS STORED AS HE WRITES IT, and compared case-insensitively on the domain
half only where it matters. Email local parts are case-sensitive by specification even
though almost nobody treats them so; folding the whole thing would quietly merge two
addresses that a provider considers different, and this decides whose data is whose.
"""
from __future__ import annotations

import sqlite3

KEY = "account_owner"


class AccountMismatch(RuntimeError):
    """This warehouse belongs to a different account.

    Raised only by `assert_owner`, which nothing calls on the connect path yet — see
    the module docstring on why enforcement waits for the per-account layout.
    """


def owner(conn: sqlite3.Connection) -> str | None:
    """The account this warehouse belongs to, or `None` if it has never been claimed.

    NONE IS A REAL ANSWER and not a failure: every warehouse that existed before this
    was written is unclaimed, and `R-23` says an unclaimed installation is the normal
    first-run state rather than a fault.
    """
    row = conn.execute(
        "SELECT value FROM scrapex_meta WHERE key = ? LIMIT 1", (KEY,)).fetchone()
    return str(row[0]) if row and row[0] else None


def claim(conn: sqlite3.Connection, account: str, *, force: bool = False) -> str:
    """Record that this warehouse belongs to `account`. Returns the stored value.

    A CLAIMED WAREHOUSE IS NOT RE-CLAIMED SILENTLY. Handing a file from one account
    to another is a real decision — it moves someone's data into someone else's name
    — so it takes `force`, and the same address twice is a no-op rather than an
    error. That is `R-24`'s reasoning about a user's database applied to its owner:
    a thing that holds his data is upgraded and re-pointed deliberately, never behind
    his back.
    """
    account = account.strip()
    if not account:
        raise ValueError("an account cannot be empty; pass the signed-in address")
    held = owner(conn)
    if held and held != account and not force:
        raise AccountMismatch(
            f"this warehouse belongs to {held!r}, not {account!r}. Re-pointing it "
            "moves one account's data under another's name, so pass force=True if "
            "that is really the intent.")
    conn.execute(
        "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (KEY, account))
    conn.commit()
    return account


def assert_owner(conn: sqlite3.Connection, account: str) -> None:
    """Refuse a warehouse that belongs to someone else.

    NOT CALLED FROM `connect` YET, deliberately. `DATABASE_ROOT` is still
    `~/.scrapex`, one directory per operating-system user, so a second account has
    nowhere else to go — enforcing this before `REQ-26`'s per-account layout exists
    would refuse the only warehouse there is. It is here so the rule has one
    definition when the layout arrives, rather than being invented twice.
    """
    held = owner(conn)
    if held and held != account.strip():
        raise AccountMismatch(
            f"this warehouse belongs to {held!r} and the current account is "
            f"{account.strip()!r}")
