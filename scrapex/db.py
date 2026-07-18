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


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open harvest.db with the mandated pragmas. Creates parent dirs."""
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
    return applied


@contextmanager
def write_lock(db_path: Path | str = DEFAULT_DB_PATH, timeout_s: float = 10.0):
    """CLI-level lock file: two `scrapex` write commands never interleave (A10).

    O_CREAT|O_EXCL is atomic on Windows and POSIX. Stale locks (crashed process)
    are the owner's call to delete — the error message says exactly which file.
    """
    lock_path = Path(str(db_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise DbLockedError(
                    f"another scrapex command holds {lock_path}; "
                    "if no scrapex process is running, delete the file and retry"
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
