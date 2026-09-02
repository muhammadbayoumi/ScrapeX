"""harvest.db access layer (ENGINEERING.md A10, S6).

Single-writer topology (A10): this module is only ever used on the owner's
machine. CI legs never import it — they end at the funnel.

- WAL journal + busy_timeout on every connection.
- A CLI-level lock file so two `scrapex` commands cannot interleave writes.
- Numbered migrations via PRAGMA user_version (S6): db/schema.sql is migration
  0001; future changes are db/migrations/0002_*.sql etc., applied in order.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

# ONE MIGRATION STREAM, AND THIS POINTS AT IT.
#
# `db/migrations/` and `db/schema.sql` were deleted on 2026-08-29 on his ruling: «انا اريد
# كود نظيف لا معكرونة اسبجتى تعيق التطوير بسبب المجهود المضاعف فى تطوير اشياء لا نحتاج
# اليها». They were the pre-`M5` stream and had not moved since **2026-08-04**, four days
# before `db/engine/` was created — frozen, but still live enough that a schema change had
# to be written TWICE. It was written twice exactly once, on the day it was deleted.
#
# What made the deletion safe rather than brave: `db/engine/schema.sql` was DERIVED from
# both streams at the collapse, and `tests/test_one_schema_carries_both_streams.py` holds
# it against a frozen record of all 134 objects they produced. The proof that nothing is
# lost was already in the repository, written the day the streams were merged.
DB_DIR = Path(__file__).resolve().parent.parent / "db" / "engine"
SCHEMA_FILE = DB_DIR / "schema.sql"
MIGRATIONS_DIR = DB_DIR / "migrations"

# WHY SILENCE IS NOT A PATH (2026-07-30)
#
# This used to fall back to ~/.scrapex/harvest.db, which is NOT the warehouse —
# the real one is the engine database under ~/.scrapex/engine/, and harvest.db
# has been empty since 21 July. So a caller that forgot its path opened a
# blank database, found no tables, and in the worst case would have WRITTEN a
# whole crawl into a file nothing else in the product reads. It happened: one
# settings write went there today before being caught.
#
# The env var stays, because naming a path is a deliberate act. Omitting one is
# not, and now says so. Every legitimate caller already passes a path or is a
# method on a database object that carries its own; nothing was relying on the
# guess (verified across scrapex/, tests/ and tools/).
_ENV_DB_PATH = os.environ.get("SCRAPEX_DB_PATH")
DEFAULT_DB_PATH = Path(_ENV_DB_PATH) if _ENV_DB_PATH else None


class NoDatabasePathError(RuntimeError):
    """connect() was called with no path and SCRAPEX_DB_PATH is unset.

    Deliberately louder than a default: the default was a DIFFERENT database
    from the one the product uses, so guessing wrote to the wrong file quietly.
    """

_MIGRATION_NAME = re.compile(r"^(\d{4})_.+\.sql$")


class DbLockedError(RuntimeError):
    """Another scrapex command holds the write lock (A10)."""


def connect(db_path: Path | str | None = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the engine database with the mandated pragmas.

    A compatibility facade for price-domain modules while they move behind
    repositories.

    IT USED TO REFUSE THE GENERIC DATABASE by application id, because opening
    one as the other wrote price rows into a file with no price tables. M5 left
    one database, so there is nothing to be confused with and the check is gone
    with the file it was protecting against. What replaced it is stricter and
    sits one layer up: EngineDatabase.connect() verifies the identity, the
    migration ledger and the payload contract before handing back a connection.
    """
    if db_path is None:
        raise NoDatabasePathError(
            "db.connect() needs a database path: pass one, or set SCRAPEX_DB_PATH. "
            "There is no default, because the old default (~/.scrapex/harvest.db) "
            "was not the warehouse (~/.scrapex/engine/scrapex-engine.db) and a "
            "forgotten path silently opened the wrong, empty file.")
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Does this database have that column yet?

    THE WINDOW THIS EXISTS FOR, written down so it can be closed rather than
    inherited: new code reaches the owner's machine the moment a file is saved,
    but a migration only lands when it is applied. On 2026-07-29 the engine
    restarted itself into code that wrote currency_rate.source_kind while the
    live database was still one migration behind, and the rate refresh threw
    `no such column` on every pass — silently, in a background worker, so the
    Data page went on ranking currencies at a stale rate with nothing saying
    why. That is the failure mode this closes.

    A writer that ASKS instead of assuming keeps working across that window in
    both directions. Delete the callers' branches once every install is past
    the migration that adds the column; keep this helper, it is cheap and it is
    the honest way to ask.
    """
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})"))


def _migration_files() -> list[tuple[int, Path]]:
    """Ordered migrations: schema.sql is 0001; db/migrations/NNNN_*.sql follow."""
    migrations: list[tuple[int, Path]] = [(1, SCHEMA_FILE)]
    if MIGRATIONS_DIR.is_dir():
        for file in sorted(MIGRATIONS_DIR.iterdir()):
            match = _MIGRATION_NAME.match(file.name)
            if not match:
                raise ValueError(
                    f"migration file {file.name!r} does not match NNNN_name.sql (S6)"
                )
            number = int(match.group(1))
            if number == 1:
                raise ValueError("0001 is reserved for db/schema.sql")
            migrations.append((number, file))
    numbers = [n for n, _ in migrations]
    if numbers != sorted(set(numbers)):
        raise ValueError(f"migration numbers must be unique and ordered, got {numbers}")
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"migration numbers must be gapless from 1, got {numbers}")
    return migrations


def latest_schema_version() -> int:
    """The newest warehouse schema this engine understands.

    Storage restore uses this as a downgrade guard: a database produced by a
    newer ScrapeX may be perfectly healthy SQLite, but this engine must not make
    it live and then guess at a schema it does not understand.
    """
    return _migration_files()[-1][0]


def pending_migrations(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Migrations that exist on disk and have NOT been applied to this database.

    WHY THIS IS A PRODUCT FEATURE AND NOT A DIAGNOSTIC (2026-07-30)
    --------------------------------------------------------------
    CI was green and the Data page was broken at the same time, and both were
    correct. CI builds a database from schema.sql plus EVERY migration, so code
    that reads a new column passes there by construction. The owner's machine
    had the code and not the migration, so the same query answered

        sqlite3.OperationalError: no such column: so.weight

    Nothing said "the database is one migration behind"; the product simply
    broke and the raw SQLite text was the only clue. The gap was never in the
    code — it was that `main` can move ahead of a database and nothing notices
    until a page fails.

    Same definition of "not applied" that migrate() uses, so the two can never
    disagree: a number above the recorded user_version.
    """
    # WHICH MIGRATIONS BELONG TO THIS DATABASE, and this took two wrong
    # answers to get right — both of which cried wolf, which is worse than
    # silence.
    #
    # First attempt compared filename numbers against user_version: the ledger
    # numbers a migration by its POSITION in this database's stream (0057 is
    # recorded as 55), so it announced two applied migrations as pending.
    #
    # Second attempt compared filenames against the ledger and announced 0013,
    # 0014 and 0017 as pending, because ONE DIRECTORY HELD TWO STREAMS and those
    # three belonged to General. The answer was a hand-listed tuple of "my"
    # numbers, `_MARKETLENS_LEGACY_NUMBERS`, and everything not in it was hidden.
    #
    # THAT PREMISE EXPIRED AND THE FILTER OUTLIVED IT. `db/` holds only `engine/`
    # now; `db/general/` and `scrapex/databases/split.py` are both gone. There is
    # one stream, so there is nothing to filter against — but the tuple never
    # learned 0013 and 0014 had become engine migrations, so this function could
    # not report them AT ALL. Measured 2026-08-30 on a database missing 0013,
    # 0014 and 0016: it answered `[16]`. A database that never received
    # `0014_one_source_registry` — the merge of `site_profile` into
    # `source_site` — was told nothing was pending, which is the exact silence
    # the docstring above says this function exists to break.
    #
    # THE LEDGER IS THE WHOLE ANSWER NOW. A migration is pending when this
    # database has no row for it, and `schema.sql` is recorded like any other, so
    # the baseline still excludes itself without being named.
    try:
        applied = {row[0] for row in conn.execute(
            "SELECT migration_name FROM database_migration")}
    except sqlite3.DatabaseError:
        # Older than the ledger: user_version is all there is, and on such a
        # database no renumbering has happened yet, so it is still true.
        current = schema_version(conn)
        return [(number, file.name) for number, file in _migration_files()
                if number > current]
    return [(number, file.name) for number, file in _migration_files()
            if file.name not in applied]


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply every migration above the current user_version. Returns applied numbers.

    IT DELEGATES, AND THE REASON IS NOT TIDINESS. This runner and
    `EngineDatabase._migrate` were the same recipe with one difference that matters: the
    engine's writes the `database_migration` ledger and this one never did. A database
    advanced here would carry `user_version = 14` and an empty ledger, and
    `_verify_checksums` would then refuse to open it with "migration ledger is
    incomplete" — a database the product had itself created and could not read.

    So there is one runner as well as one stream. What stays in this module is what is
    genuinely its own: `connect`, `write_lock` and the stale-lock reclamation that eight
    modules use and nothing else provides.
    """
    from .databases.domain import EngineDatabase

    row = next(r for r in conn.execute("PRAGMA database_list") if r[1] == "main")
    return EngineDatabase(Path(row[2]))._migrate(conn)


def _pid_is_alive(pid: int) -> bool:
    """Is this process still running? Biased toward "yes" when unsure — we must
    never steal a lock that is genuinely held."""
    if pid <= 0:
        return False
    if os.name == "nt":
        # NOT os.kill(pid, 0): on Windows that calls TerminateProcess and would
        # KILL the very process we are asking about.
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False                       # no such process
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True                        # couldn't tell -> assume alive
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                            # exists, just not ours
    return True


def _process_started_at(pid: int) -> str:
    """A stamp identifying THIS run of a pid, or "" when unknowable.

    Liveness alone cannot own a lock: Windows recycles pids aggressively, so a
    crashed holder's number is soon a live unrelated process — and the lock is
    then never reclaimed, bricking every crawl until someone deletes a file by
    hand. The creation time makes the identity unambiguous.
    """
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            created = wintypes.FILETIME()
            rest = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
            if kernel32.GetProcessTimes(handle, ctypes.byref(created),
                                        ctypes.byref(rest[0]), ctypes.byref(rest[1]),
                                        ctypes.byref(rest[2])):
                return f"{created.dwHighDateTime}{created.dwLowDateTime}"
            return ""
        finally:
            kernel32.CloseHandle(handle)
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as handle:
            return handle.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""


def _lock_owner(text: str) -> tuple[int, str]:
    """(pid, start stamp) from a lock file. Old single-pid files still parse.

    A pid that is not a number returns 0 — and the caller treats 0 as
    "unreadable, leave it alone" rather than as a dead owner: guessing at a
    file we cannot read is how a live holder gets robbed."""
    pid_text, _, stamp = text.strip().partition(":")
    try:
        return int(pid_text or 0), stamp
    except ValueError:
        return 0, ""


def _reclaim_if_stale(lock_path: Path) -> bool:
    """Remove a lock whose owning process is gone. Returns True if reclaimed.

    Without this a hard-killed runtime bricks every future crawl until someone
    deletes a file by hand — a permanent outage caused by a crash we already
    recovered from everywhere else.
    """
    try:
        owner, stamp = _lock_owner(lock_path.read_text(encoding="ascii"))
    except OSError:
        return False                           # unreadable: leave it alone
    if owner <= 0:
        return False                           # unreadable: leave it alone
    if _pid_is_alive(owner):
        # Alive is not enough: the pid may have been RECYCLED since the lock
        # was written. A stamp that disagrees means the holder is long gone.
        current = _process_started_at(owner)
        if not stamp or not current or stamp == current:
            return False
    try:
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return True                            # someone else reclaimed it first
    except OSError:
        return False


# One gate per database file, for the writers INSIDE this process.
#
# THE FILE LOCK CANNOT SERIALISE US FROM OURSELVES. It is keyed by pid, and
# _reclaim_if_stale deliberately refuses to steal a lock whose owner is alive —
# so when a second THREAD of this same runtime arrives, it finds a live owner
# that is us, waits out the whole timeout, and is then told "another scrapex
# process (pid 43572) is writing to the database", naming its own pid.
#
# Measured 2026-07-30, two threads of one process on one database: the second
# raised DbLockedError after its full budget. That is not serialisation, it is
# refusal — and it is reachable today, because crawl_parallel_sources > 1 runs
# per-host lanes as threads of this process (jobs.py _drive_lanes) and every
# lane ingests under this lock. Two lanes whose ingests overlap by more than
# the timeout lose a source outright, with a message that blames a process
# that does not exist.
#
# A real lock in front of the file lock fixes it: threads of this runtime QUEUE
# here, and whichever one holds this gate is the only one that ever races the
# file against other processes. The caller's timeout still bounds the wait, so
# an HTTP route that must answer keeps answering (409) rather than hanging.
_GATES: dict[str, threading.Lock] = {}
_GATES_GUARD = threading.Lock()


def _process_gate(lock_path: Path) -> threading.Lock:
    """The in-process gate for a lock file, created once per path.

    Keyed on the LOCK FILE, normalised the way the filesystem compares it, so
    two spellings of one database cannot end up with two gates and fall back to
    racing the file.
    """
    key = os.path.normcase(os.path.abspath(str(lock_path)))
    with _GATES_GUARD:
        gate = _GATES.get(key)
        if gate is None:
            gate = _GATES[key] = threading.Lock()
    return gate


@contextmanager
def write_lock(db_path: Path | str = DEFAULT_DB_PATH, timeout_s: float = 10.0):
    """CLI-level lock file: two `scrapex` write commands never interleave (A10).

    O_CREAT|O_EXCL is atomic on Windows and POSIX. A lock left behind by a
    CRASHED process is reclaimed automatically once its pid is confirmed gone;
    only a genuinely live holder makes us wait.

    Threads of THIS process queue on an in-process gate first (see _GATES): the
    file lock can only tell processes apart, and asking it to tell our own
    threads apart made it refuse them instead.
    """
    lock_path = Path(str(db_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    gate = _process_gate(lock_path)
    if not gate.acquire(timeout=max(0.0, timeout_s)):
        raise DbLockedError(
            "another crawl in this runtime is writing to the database; it has "
            f"held the write lock for more than {timeout_s:g}s. Wait for it to "
            "finish and retry — nothing was written."
        )
    try:
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if _reclaim_if_stale(lock_path):
                    continue                       # dead owner: retry immediately
                if time.monotonic() >= deadline:
                    owner, _ = _lock_owner(
                        lock_path.read_text(encoding="ascii", errors="replace"))
                    raise DbLockedError(
                        f"another scrapex process (pid {owner}) is writing to the database; "
                        "wait for its crawl to finish and retry"
                    ) from None
                time.sleep(0.2)
        try:
            os.write(fd, f"{os.getpid()}:{_process_started_at(os.getpid())}".encode("ascii"))
            os.close(fd)
            yield
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:  # already cleaned up — not an error path worth failing
                pass
    finally:
        gate.release()
