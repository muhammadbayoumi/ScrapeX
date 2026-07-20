"""Reversible migration from the unified warehouse to two domain databases."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .. import db as legacy_db
from .. import storage
from .domain import GeneralDatabase, MarketLensDatabase
from .registry import DatabaseRegistry, REGISTRY_FILE

BATCH_SIZE = 500
GENERIC_TABLES = (
    "site_profile",
    "dataset_definition",
    "field_definition",
    "dataset_relationship",
    "relationship_field_pair",
    "generic_page_snapshot",
    "dataset_schema_version",
    "schema_version_field",
    "generic_record",
    "generic_record_revision",
    "generic_ingestion",
)
GENERIC_COPY_COLUMNS = {
    "dataset_definition": (
        "dataset_definition_id", "site_profile_id", "dataset_key", "original_name",
        "display_name", "dataset_kind", "discovery_method", "locator_json",
        "first_seen_at", "last_seen_at", "valid_to",
    ),
    "field_definition": (
        "field_definition_id", "dataset_definition_id", "field_key", "original_name",
        "display_name", "data_type", "is_nullable", "identity_role", "display_order",
        "first_seen_at", "last_seen_at", "valid_to",
    ),
    "dataset_relationship": (
        "dataset_relationship_id", "site_profile_id", "relationship_key",
        "parent_dataset_id", "child_dataset_id", "cardinality", "review_status",
        "confidence", "evidence_json", "created_at", "updated_at", "valid_to",
    ),
    "relationship_field_pair": (
        "relationship_field_pair_id", "dataset_relationship_id", "parent_field_id",
        "child_field_id", "pair_order",
    ),
    "generic_page_snapshot": (
        "page_snapshot_id", "source_url", "content_type", "html_content",
        "content_hash", "captured_at",
    ),
    "dataset_schema_version": (
        "schema_version_id", "dataset_definition_id", "version_number",
        "schema_hash", "status", "approved_at", "valid_to",
    ),
    "schema_version_field": (
        "schema_version_id", "field_definition_id", "field_order",
    ),
    "generic_record": (
        "generic_record_id", "dataset_definition_id", "record_key",
        "schema_version_id", "data_json", "source_snapshot_id", "source_locator",
        "content_hash", "first_seen_at", "last_seen_at", "status",
    ),
    "generic_record_revision": (
        "record_revision_id", "generic_record_id", "schema_version_id",
        "source_snapshot_id", "data_json", "content_hash", "observed_at",
    ),
    "generic_ingestion": (
        "generic_ingestion_id", "dataset_definition_id", "schema_version_id",
        "source_snapshot_id", "source_locator", "record_count", "status",
        "ingested_at",
    ),
}


class DatabaseSplitError(RuntimeError):
    """The split was refused or failed before the runtime pointer switched."""


@dataclass(frozen=True)
class SplitResult:
    legacy_path: str
    legacy_backup: str
    general_path: str
    marketlens_path: str
    registry_path: str
    generic_rows: int
    marketlens_tables_verified: int
    status: str
    recovery: str

    def public(self) -> dict[str, Any]:
        return asdict(self)


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _quote(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise DatabaseSplitError(f"unsafe SQLite identifier {identifier!r}")
    return f'"{identifier}"'


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {_quote(table)} LIMIT 1"
    ).fetchone()[0])


def _iter_rows(
    conn: sqlite3.Connection, table: str, columns: Iterable[str]
) -> Iterable[sqlite3.Row]:
    names = tuple(columns)
    selected = ", ".join(_quote(name) for name in names)
    cursor: int | None = None
    while True:
        if cursor is None:
            rows = conn.execute(
                f"SELECT rowid AS _copy_rowid, {selected} FROM {_quote(table)} "
                "ORDER BY rowid LIMIT ?",
                (BATCH_SIZE,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT rowid AS _copy_rowid, {selected} FROM {_quote(table)} "
                "WHERE rowid > ? ORDER BY rowid LIMIT ?",
                (cursor, BATCH_SIZE),
            ).fetchall()
        if not rows:
            return
        for row in rows:
            yield row
        cursor = int(rows[-1]["_copy_rowid"])


def _remove_sqlite_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def _table_hash(conn: sqlite3.Connection, table: str) -> str:
    columns = [
        row[0] for row in conn.execute(
            "SELECT name FROM pragma_table_info(?) ORDER BY cid LIMIT 200", (table,)
        ).fetchall()
    ]
    digest = hashlib.sha256()
    for row in _iter_rows(conn, table, columns):
        payload = [row[name] for name in columns]
        digest.update(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                       default=str).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _legacy_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 200"
        ).fetchall()
    ]


def _backup_legacy(source: sqlite3.Connection, legacy_path: Path) -> Path:
    folder = legacy_path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{legacy_path.stem}.pre-split-{_stamp()}.db"
    destination = sqlite3.connect(str(target))
    try:
        source.backup(destination)
    finally:
        destination.close()
    check = sqlite3.connect(str(target))
    try:
        if check.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
            raise DatabaseSplitError(
                "the pre-split backup failed verification; free disk space and retry"
            )
    finally:
        check.close()
    return target


def _build_marketlens(
    legacy: sqlite3.Connection, legacy_tables: list[str], incoming_path: Path
) -> int:
    target = sqlite3.connect(str(incoming_path))
    target.row_factory = sqlite3.Row
    try:
        legacy.backup(target)
        target.execute("PRAGMA foreign_keys = OFF")
        with target:
            for table in reversed(GENERIC_TABLES):
                target.execute(f"DROP TABLE IF EXISTS {_quote(table)}")
            target.executescript(
                MarketLensDatabase(incoming_path)._migrations[-1].path.read_text(  # noqa: SLF001
                    encoding="utf-8"
                )
            )
        marketlens = MarketLensDatabase(incoming_path)
        marketlens._stamp_and_verify_checksums(target)  # noqa: SLF001
        target.execute("PRAGMA foreign_keys = ON")
        if target.execute(
            "SELECT 1 FROM pragma_foreign_key_check LIMIT 1"
        ).fetchone() is not None:
            raise DatabaseSplitError(
                "the MarketLens copy has a foreign-key error; keep using the legacy "
                "database and retry after repairing it"
            )
        verified = 0
        for table in legacy_tables:
            if table in GENERIC_TABLES or table in {"database_migration", "scrapex_meta"}:
                continue
            if not _table_exists(target, table):
                raise DatabaseSplitError(f"MarketLens copy is missing table {table}")
            if _count(legacy, table) != _count(target, table):
                raise DatabaseSplitError(f"MarketLens row count changed for {table}")
            if _table_hash(legacy, table) != _table_hash(target, table):
                raise DatabaseSplitError(f"MarketLens row checksum changed for {table}")
            verified += 1
    finally:
        target.close()
    check = MarketLensDatabase(incoming_path).connect()
    check.close()
    return verified


def _insert_rows(
    source: sqlite3.Connection,
    destination: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> int:
    placeholders = ",".join("?" for _ in columns)
    names = ",".join(_quote(name) for name in columns)
    written = 0
    for row in _iter_rows(source, table, columns):
        destination.execute(
            f"INSERT INTO {_quote(table)} ({names}) VALUES ({placeholders})",
            tuple(row[name] for name in columns),
        )
        written += 1
    return written


def _copy_general(legacy: sqlite3.Connection, incoming_path: Path) -> int:
    general = GeneralDatabase(incoming_path)
    general.initialize()
    if not _table_exists(legacy, "site_profile"):
        return 0
    destination = general.connect()
    written = 0
    try:
        with destination:
            site_columns = (
                "site_profile_id", "site_key", "display_name", "base_url",
                "price_source_id", "lifecycle", "created_at", "updated_at", "valid_to",
            )
            for row in _iter_rows(legacy, "site_profile", site_columns):
                source_key = None
                if row["price_source_id"] is not None:
                    linked = legacy.execute(
                        "SELECT source_key FROM source_site WHERE source_id = ? LIMIT 1",
                        (row["price_source_id"],),
                    ).fetchone()
                    source_key = linked[0] if linked else None
                destination.execute(
                    "INSERT INTO site_profile "
                    "(site_profile_id, site_key, display_name, base_url, "
                    "marketlens_source_key, lifecycle, created_at, updated_at, valid_to) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        row["site_profile_id"], row["site_key"], row["display_name"],
                        row["base_url"], source_key, row["lifecycle"], row["created_at"],
                        row["updated_at"], row["valid_to"],
                    ),
                )
                written += 1
            for table in GENERIC_TABLES[1:]:
                written += _insert_rows(
                    legacy, destination, table, GENERIC_COPY_COLUMNS[table]
                )
        for table in GENERIC_TABLES:
            if _count(legacy, table) != _count(destination, table):
                raise DatabaseSplitError(f"General row count changed for {table}")
        if destination.execute(
            "SELECT 1 FROM pragma_foreign_key_check LIMIT 1"
        ).fetchone() is not None:
            raise DatabaseSplitError(
                "the General copy has a foreign-key error; keep using the legacy "
                "database and retry after repairing it"
            )
    finally:
        destination.close()
    return written


def split_legacy_database(
    legacy_path: Path | str,
    *,
    general_path: Path | str,
    marketlens_path: Path | str,
    pointer_file: Path | str = REGISTRY_FILE,
) -> SplitResult:
    """Copy, verify, switch, and seal without deleting or rewriting the legacy file."""
    legacy_path = Path(legacy_path).resolve()
    general_path = Path(general_path).resolve()
    marketlens_path = Path(marketlens_path).resolve()
    pointer_file = Path(pointer_file).resolve()
    if not legacy_path.is_file():
        raise DatabaseSplitError(
            f"legacy database not found at {legacy_path}; reconnect its storage and retry"
        )
    if len({legacy_path, general_path, marketlens_path, pointer_file}) != 4:
        raise DatabaseSplitError(
            "legacy, General, MarketLens, and registry paths must be different files"
        )
    for target in (general_path, marketlens_path):
        if target.exists():
            raise DatabaseSplitError(
                f"target {target} already exists; choose an empty target or restore the "
                "existing domain database intentionally"
            )
        target.parent.mkdir(parents=True, exist_ok=True)

    general_incoming = general_path.with_suffix(general_path.suffix + ".split-incoming")
    marketlens_incoming = marketlens_path.with_suffix(
        marketlens_path.suffix + ".split-incoming"
    )
    for incoming in (general_incoming, marketlens_incoming):
        if incoming.exists():
            raise DatabaseSplitError(
                f"recovery file {incoming} already exists; inspect it, move it aside, "
                "and retry the split"
            )

    with legacy_db.write_lock(legacy_path):
        legacy = legacy_db.connect(legacy_path)
        try:
            if legacy_db.schema_version(legacy) != legacy_db.latest_schema_version():
                raise DatabaseSplitError(
                    "the legacy database is not at the latest schema; run "
                    "'scrapex init-db --db <path>' and retry"
                )
            if legacy.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise DatabaseSplitError(
                    "the legacy database failed its integrity check; restore or repair "
                    "it before retrying"
                )
            tables = _legacy_tables(legacy)
            legacy_backup = _backup_legacy(legacy, legacy_path)
            verified = _build_marketlens(legacy, tables, marketlens_incoming)
            generic_rows = _copy_general(legacy, general_incoming)
        except Exception:
            for incoming in (general_incoming, marketlens_incoming):
                _remove_sqlite_files(incoming)
            raise
        finally:
            legacy.close()

    registry = DatabaseRegistry(
        GeneralDatabase(general_path), MarketLensDatabase(marketlens_path),
        legacy_path, pointer_file,
    )
    promoted: list[tuple[Path, Path]] = []
    try:
        os.replace(general_incoming, general_path)
        promoted.append((general_path, general_incoming))
        os.replace(marketlens_incoming, marketlens_path)
        promoted.append((marketlens_path, marketlens_incoming))
        registry.verify()
        if not storage.mark_sealed(
            legacy_path, "split into isolated General and MarketLens databases",
            f"{general_path}; {marketlens_path}",
        ):
            raise DatabaseSplitError(
                "the new databases passed verification but the legacy database could "
                "not be sealed; restore write access to it and retry"
            )
        registry.write()
        try:
            os.chmod(legacy_path, stat.S_IREAD)
        except OSError:
            pass
    except Exception:
        try:
            os.chmod(legacy_path, stat.S_IREAD | stat.S_IWRITE)
            storage.unseal(legacy_path)
        except OSError:
            pass
        for live, incoming in reversed(promoted):
            if live.exists() and not incoming.exists():
                os.replace(live, incoming)
        raise

    return SplitResult(
        str(legacy_path), str(legacy_backup), str(general_path), str(marketlens_path),
        str(pointer_file), generic_rows, verified, "Succeeded",
        "To recover, run 'scrapex rollback-databases'; the legacy file and backup "
        "remain on disk.",
    )


def rollback_to_legacy(pointer_file: Path | str = REGISTRY_FILE) -> Path:
    """Switch the runtime pointer back; split files remain untouched for recovery."""
    pointer = Path(pointer_file)
    registry = DatabaseRegistry.read(pointer)
    if registry.legacy_path is None or not registry.legacy_path.is_file():
        raise DatabaseSplitError(
            "the recorded legacy database is unavailable; reconnect its storage and retry"
        )
    legacy = registry.legacy_path
    try:
        os.chmod(legacy, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    storage.unseal(legacy)
    if storage.sealed_at(legacy):
        raise DatabaseSplitError(
            "the legacy database could not be unsealed; restore write access and retry"
        )
    incoming = pointer.with_suffix(pointer.suffix + ".incoming")
    try:
        incoming.write_text(
            json.dumps({
                "format_version": 1,
                "mode": "legacy",
                "legacy_path": str(legacy),
                "general_path": str(registry.general.path),
                "marketlens_path": str(registry.marketlens.path),
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(incoming, pointer)
    except Exception:
        incoming.unlink(missing_ok=True)
        storage.mark_sealed(
            legacy, "rollback pointer update failed; split databases remain active",
            registry.marketlens.path,
        )
        raise
    return legacy
