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
import time
from contextlib import contextmanager
from pathlib import Path

from .database_ids import GENERAL_APPLICATION_ID

# db/ lives next to the package; schema.sql is the single DDL truth (Q1).
DB_DIR = Path(__file__).resolve().parent.parent / "db"
SCHEMA_FILE = DB_DIR / "schema.sql"
MIGRATIONS_DIR = DB_DIR / "migrations"

DEFAULT_DB_PATH = Path(
    os.environ.get("SCRAPEX_DB_PATH", str(Path.home() / ".scrapex" / "harvest.db"))
)

_MIGRATION_NAME = re.compile(r"^(\d{4})_.+\.sql$")


class DbLockedError(RuntimeError):
    """Another scrapex command holds the write lock (A10)."""


class WrongDatabaseKindError(RuntimeError):
    """The legacy MarketLens facade was pointed at the General database."""


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the legacy/MarketLens price database with the mandated pragmas.

    This compatibility facade remains for price-domain modules while they move
    behind repositories. It explicitly refuses the General database.
    """
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    if int(conn.execute("PRAGMA application_id").fetchone()[0]) == GENERAL_APPLICATION_ID:
        conn.close()
        raise WrongDatabaseKindError(
            f"{path} is the General database; choose the MarketLens database and retry"
        )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


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


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply every migration above the current user_version. Returns applied numbers."""
    applied: list[int] = []
    current = schema_version(conn)
    for number, file in _migration_files():
        if number <= current:
            continue
        sql = file.read_text(encoding="utf-8")
        with conn:  # one transaction per migration — partial application impossible
            conn.executescript(sql)
            # schema.sql sets its own user_version; later migrations must too.
            if schema_version(conn) != number:
                conn.execute(f"PRAGMA user_version = {number}")
        applied.append(number)
    # Stamp the contract version (two-engine guardrail) once the meta table exists.
    from .contract import stamp_contract
    with conn:
        stamp_contract(conn)
    return applied


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


def _reclaim_if_stale(lock_path: Path) -> bool:
    """Remove a lock whose owning process is gone. Returns True if reclaimed.

    Without this a hard-killed runtime bricks every future crawl until someone
    deletes a file by hand — a permanent outage caused by a crash we already
    recovered from everywhere else.
    """
    try:
        owner = int(lock_path.read_text(encoding="ascii").strip() or 0)
    except (OSError, ValueError):
        return False                           # unreadable: leave it alone
    if _pid_is_alive(owner):
        return False
    try:
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return True                            # someone else reclaimed it first
    except OSError:
        return False


@contextmanager
def write_lock(db_path: Path | str = DEFAULT_DB_PATH, timeout_s: float = 10.0):
    """CLI-level lock file: two `scrapex` write commands never interleave (A10).

    O_CREAT|O_EXCL is atomic on Windows and POSIX. A lock left behind by a
    CRASHED process is reclaimed automatically once its pid is confirmed gone;
    only a genuinely live holder makes us wait.
    """
    lock_path = Path(str(db_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if _reclaim_if_stale(lock_path):
                continue                       # dead owner: retry immediately
            if time.monotonic() >= deadline:
                owner = lock_path.read_text(encoding="ascii", errors="replace").strip()
                raise DbLockedError(
                    f"another scrapex process (pid {owner}) is writing to the database; "
                    "wait for its crawl to finish and retry"
                ) from None
            time.sleep(0.2)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:  # already cleaned up — not an error path worth failing
            pass
