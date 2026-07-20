"""Typed SQLite boundaries for General and MarketLens.

Each type owns a migration stream, application id, lock, health check, backup,
and restore path. Callers cannot accidentally pass one domain to the other.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from .. import db as legacy_db
from ..database_ids import (
    GENERAL_APPLICATION_ID,
    GENERAL_DATABASE_KIND,
    MARKETLENS_APPLICATION_ID,
    MARKETLENS_DATABASE_KIND,
)

ROOT_DB_DIR = Path(__file__).resolve().parents[2] / "db"
GENERAL_SCHEMA = ROOT_DB_DIR / "general" / "schema.sql"
GENERAL_MIGRATIONS = ROOT_DB_DIR / "general" / "migrations"
MARKETLENS_IDENTITY = (
    ROOT_DB_DIR / "marketlens" / "migrations" / "0013_marketlens_database_identity.sql"
)

T = TypeVar("T")


class DatabaseUnavailableError(RuntimeError):
    """A requested operational database is missing or unreadable."""


class DatabaseKindError(RuntimeError):
    """A typed boundary was given the other domain's database."""


class DatabaseMigrationError(RuntimeError):
    """A migration stream is incomplete, newer, or has been edited in place."""


@dataclass(frozen=True)
class Migration:
    number: int
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class DatabaseHealth:
    kind: str
    path: str
    ok: bool
    status: str
    action: str
    schema_version: int | None
    application_id: int | None

    def public(self) -> dict[str, Any]:
        return asdict(self)


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _sqlite_connect(path: Path, *, create: bool) -> sqlite3.Connection:
    if not create and not path.is_file():
        raise DatabaseUnavailableError(
            f"database not found at {path}; reconnect its storage and try again"
        )
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _folder_migrations(folder: Path, start: int = 2) -> list[Migration]:
    if not folder.is_dir():
        return []
    result: list[Migration] = []
    for path in sorted(folder.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        number = int(path.name[:4])
        if number < start:
            continue
        result.append(Migration(number, path))
    return result


def _general_plan() -> tuple[Migration, ...]:
    return tuple([Migration(1, GENERAL_SCHEMA), *_folder_migrations(GENERAL_MIGRATIONS)])


# Legacy migrations belonging to the PRICE domain, in the order MarketLens
# applies them. Legacy 13 and 14 are deliberately absent — they created the
# generic catalogue and generic extraction storage, which are General's alone.
#
# Listed rather than ranged: the unified chain and this one have diverged, so a
# new price migration lands at the END of the legacy chain but in the middle of
# this plan. A range would silently swallow whatever General adds next.
_MARKETLENS_LEGACY_NUMBERS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15)


def _marketlens_plan() -> tuple[Migration, ...]:
    legacy = {number: path
              for number, path in legacy_db._migration_files()  # noqa: SLF001
              if number in _MARKETLENS_LEGACY_NUMBERS}
    missing = sorted(set(_MARKETLENS_LEGACY_NUMBERS) - set(legacy))
    if missing:
        raise MigrationStreamError(
            f"MarketLens expects legacy price migrations {missing}, which are not in "
            "db/migrations. A price migration was renamed or removed.")

    # This stream's version numbers are its own; they are NOT the legacy file
    # numbers, and the gap left by 13/14 is closed here rather than carried.
    plan = [Migration(1, legacy_db.SCHEMA_FILE)]
    for position, number in enumerate(sorted(n for n in legacy if n <= 12), start=2):
        plan.append(Migration(position, legacy[number]))
    plan.append(Migration(13, MARKETLENS_IDENTITY))
    plan.append(Migration(14, legacy[15]))
    return tuple(plan)


class DomainDatabase(Generic[T]):
    """Base implementation; concrete domain types are the public capability."""

    kind: str
    application_id: int

    def __init__(self, path: Path | str, migrations: tuple[Migration, ...]):
        self.path = Path(path)
        self._migrations = migrations
        numbers = [item.number for item in migrations]
        if numbers != list(range(1, len(numbers) + 1)):
            raise DatabaseMigrationError(
                f"{self.kind} migrations must be gapless from 1, got {numbers}"
            )

    @property
    def latest_schema_version(self) -> int:
        return self._migrations[-1].number

    def initialize(self) -> list[int]:
        """Create or advance this database, then verify its physical identity."""
        with legacy_db.write_lock(self.path):
            existed = self.path.exists() and self.path.stat().st_size > 0
            conn = _sqlite_connect(self.path, create=True)
            try:
                if existed:
                    self._assert_not_other_kind(conn)
                applied = self._migrate(conn)
                self._verify(conn)
                return applied
            except Exception:
                conn.close()
                if not existed:
                    self._remove_new_database_files()
                raise
            finally:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    def connect(self) -> sqlite3.Connection:
        conn = _sqlite_connect(self.path, create=False)
        try:
            self._verify(conn)
        except Exception:
            conn.close()
            raise
        return conn

    def write(self, action: Callable[[sqlite3.Connection], T]) -> T:
        with legacy_db.write_lock(self.path):
            conn = self.connect()
            try:
                result = action(conn)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def health(self) -> DatabaseHealth:
        if not self.path.is_file():
            return DatabaseHealth(
                self.kind, str(self.path), False, "Missing",
                "Reconnect the storage containing this database, then retry.",
                None, None,
            )
        try:
            conn = self.connect()
            try:
                quick = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
                fk_problem = conn.execute(
                    "SELECT 1 FROM pragma_foreign_key_check LIMIT 1"
                ).fetchone()
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
            finally:
                conn.close()
            if quick != "ok" or fk_problem is not None:
                return DatabaseHealth(
                    self.kind, str(self.path), False, "Failed",
                    "Restore this database from a verified backup, then retry.",
                    version, app_id,
                )
            return DatabaseHealth(
                self.kind, str(self.path), True, "Healthy",
                "No action is required.", version, app_id,
            )
        except (sqlite3.DatabaseError, DatabaseUnavailableError,
                DatabaseKindError, DatabaseMigrationError) as exc:
            return DatabaseHealth(
                self.kind, str(self.path), False, "Failed",
                f"Choose the correct {self.kind} database or restore a verified backup, "
                f"then retry. ({exc})",
                None, None,
            )

    def backup(self, folder: Path | str | None = None) -> Path:
        target_folder = Path(folder) if folder else self.path.parent / "backups"
        target_folder.mkdir(parents=True, exist_ok=True)
        target = target_folder / f"{self.path.stem}.{self.kind}-{_utc_stamp()}.db"
        incoming = target.with_suffix(".db.incoming")
        with legacy_db.write_lock(self.path):
            source = self.connect()
            destination = _sqlite_connect(incoming, create=True)
            try:
                source.backup(destination)
                destination.close()
                destination = None
                copied = self.__class__(incoming).connect()
                copied.close()
                os.replace(incoming, target)
            finally:
                source.close()
                if destination is not None:
                    destination.close()
                incoming.unlink(missing_ok=True)
        return target

    def restore(self, backup_path: Path | str) -> Path:
        backup = Path(backup_path)
        check = self.__class__(backup).connect()
        check.close()
        incoming = self.path.with_suffix(self.path.suffix + ".restore-incoming")
        displaced = self.path.with_name(
            f"{self.path.stem}.replaced-{_utc_stamp()}{self.path.suffix}"
        )
        with legacy_db.write_lock(self.path):
            try:
                source = self.__class__(backup).connect()
                try:
                    destination = _sqlite_connect(incoming, create=True)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                finally:
                    source.close()
                verified = self.__class__(incoming).connect()
                verified.close()
                try:
                    os.replace(self.path, displaced)
                    os.replace(incoming, self.path)
                except Exception:
                    if displaced.exists() and not self.path.exists():
                        os.replace(displaced, self.path)
                    raise
            finally:
                for suffix in ("", "-wal", "-shm"):
                    Path(str(incoming) + suffix).unlink(missing_ok=True)
        return displaced

    def _migrate(self, conn: sqlite3.Connection) -> list[int]:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current > self.latest_schema_version:
            raise DatabaseMigrationError(
                f"{self.kind} database schema v{current} is newer than this engine's "
                f"v{self.latest_schema_version}; upgrade ScrapeX and retry"
            )
        applied: list[int] = []
        for migration in self._migrations:
            if migration.number <= current:
                continue
            sql = migration.path.read_text(encoding="utf-8")
            try:
                conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            stamped = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if stamped != migration.number:
                # A file shared with the unified chain carries THAT chain's
                # number, and cannot also carry this stream's — the two diverged
                # the moment General and MarketLens stopped applying the same
                # list. The stream owns its version, so the runner stamps it.
                # A file that set nothing at all is still a mistake: it means the
                # author forgot, and every later run would replay it.
                if stamped == 0:
                    raise DatabaseMigrationError(
                        f"{self.kind} migration {migration.name} set no schema "
                        "version at all; add a PRAGMA user_version and retry")
                conn.execute(f"PRAGMA user_version = {migration.number}")
                conn.commit()
            current = migration.number
            applied.append(current)
        self._stamp_and_verify_checksums(conn)
        return applied

    def _stamp_and_verify_checksums(self, conn: sqlite3.Connection) -> None:
        for migration in self._migrations:
            stored = conn.execute(
                "SELECT sha256 FROM database_migration WHERE migration_number = ? LIMIT 1",
                (migration.number,),
            ).fetchone()
            if stored is not None and stored[0] != migration.sha256:
                raise DatabaseMigrationError(
                    f"{self.kind} migration {migration.name} checksum changed; restore "
                    "the original migration file and retry"
                )
            if stored is None:
                conn.execute(
                    "INSERT INTO database_migration "
                    "(migration_number, migration_name, sha256) VALUES (?,?,?)",
                    (migration.number, migration.name, migration.sha256),
                )
        conn.commit()

    def _assert_not_other_kind(self, conn: sqlite3.Connection) -> None:
        app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if app_id == 0 and version > 0:
            raise DatabaseKindError(
                f"{self.path} is an unmarked legacy database; run "
                "'scrapex split-databases' and retry"
            )
        if app_id not in (0, self.application_id):
            raise DatabaseKindError(
                f"expected a {self.kind} database at {self.path}, but its application id "
                f"is {app_id}; select the correct database and retry"
            )

    def _verify_checksums(self, conn: sqlite3.Connection) -> None:
        for migration in self._migrations:
            stored = conn.execute(
                "SELECT sha256 FROM database_migration WHERE migration_number = ? LIMIT 1",
                (migration.number,),
            ).fetchone()
            if stored is None:
                raise DatabaseMigrationError(
                    f"{self.kind} migration ledger is incomplete at {migration.name}; "
                    "run database initialization and retry"
                )
            if stored[0] != migration.sha256:
                raise DatabaseMigrationError(
                    f"{self.kind} migration {migration.name} checksum changed; restore "
                    "the original migration file and retry"
                )

    def _verify(self, conn: sqlite3.Connection) -> None:
        app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
        if app_id != self.application_id:
            raise DatabaseKindError(
                f"expected a {self.kind} database at {self.path}, but its application id "
                f"is {app_id}; select the correct database and retry"
            )
        try:
            row = conn.execute(
                "SELECT value FROM scrapex_meta WHERE key = 'database_kind' LIMIT 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise DatabaseKindError(
                f"{self.path} has no ScrapeX database marker; select the correct "
                f"{self.kind} database and retry"
            ) from exc
        if row is None or row[0] != self.kind:
            actual = row[0] if row else "unmarked"
            raise DatabaseKindError(
                f"expected database kind {self.kind!r}, found {actual!r}; select the "
                "correct database and retry"
            )
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current != self.latest_schema_version:
            raise DatabaseMigrationError(
                f"{self.kind} database is at schema v{current}, expected "
                f"v{self.latest_schema_version}; run database initialization and retry"
            )
        self._verify_checksums(conn)

    def _remove_new_database_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)


class GeneralDatabase(DomainDatabase[T]):
    kind = GENERAL_DATABASE_KIND
    application_id = GENERAL_APPLICATION_ID

    def __init__(self, path: Path | str):
        super().__init__(path, _general_plan())


class MarketLensDatabase(DomainDatabase[T]):
    kind = MARKETLENS_DATABASE_KIND
    application_id = MARKETLENS_APPLICATION_ID

    def __init__(self, path: Path | str):
        super().__init__(path, _marketlens_plan())

    def _migrate(self, conn: sqlite3.Connection) -> list[int]:
        applied = super()._migrate(conn)
        from ..contract import stamp_contract

        with conn:
            stamp_contract(conn)
        return applied

    def _verify(self, conn: sqlite3.Connection) -> None:
        super()._verify(conn)
        from ..contract import CONTRACT_VERSION, stored_contract_version

        stored = stored_contract_version(conn)
        if stored != CONTRACT_VERSION:
            raise DatabaseMigrationError(
                f"MarketLens contract marker is {stored!r}, expected "
                f"{CONTRACT_VERSION}; run database initialization or restore a "
                "compatible backup and retry"
            )
