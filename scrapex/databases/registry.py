"""Persistent registry for the two operational database capabilities."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .domain import GeneralDatabase, MarketLensDatabase

DATABASE_ROOT = Path(
    os.environ.get("SCRAPEX_DATA_ROOT", str(Path.home() / ".scrapex"))
)
REGISTRY_FILE = Path(
    os.environ.get("SCRAPEX_DATABASE_REGISTRY", str(DATABASE_ROOT / "databases.json"))
)
DEFAULT_GENERAL_PATH = DATABASE_ROOT / "general" / "general.db"
DEFAULT_MARKETLENS_PATH = DATABASE_ROOT / "marketlens" / "marketlens.db"
DEFAULT_LEGACY_PATH = DATABASE_ROOT / "harvest.db"


class LegacyDatabaseRequiresSplit(RuntimeError):
    """A unified warehouse exists and must be explicitly split by the owner."""


@dataclass(frozen=True)
class DatabaseRegistry:
    general: GeneralDatabase
    marketlens: MarketLensDatabase
    legacy_path: Path | None = None
    pointer_file: Path = REGISTRY_FILE

    def __post_init__(self) -> None:
        paths = {
            self.general.path.resolve(),
            self.marketlens.path.resolve(),
            self.pointer_file.resolve(),
        }
        if len(paths) != 3:
            raise ValueError(
                "General, MarketLens, and the registry must use three different paths"
            )

    @classmethod
    def defaults(cls, *, pointer_file: Path | str = REGISTRY_FILE) -> "DatabaseRegistry":
        pointer = Path(pointer_file)
        if pointer.is_file():
            return cls.read(pointer)
        if DEFAULT_LEGACY_PATH.is_file():
            raise LegacyDatabaseRequiresSplit(
                f"the unified database still exists at {DEFAULT_LEGACY_PATH}; run "
                "'scrapex split-databases' and retry, or use --db for a temporary "
                "legacy session"
            )
        return cls(
            GeneralDatabase(DEFAULT_GENERAL_PATH),
            MarketLensDatabase(DEFAULT_MARKETLENS_PATH),
            pointer_file=pointer,
        )

    @classmethod
    def read(cls, pointer_file: Path | str = REGISTRY_FILE) -> "DatabaseRegistry":
        pointer = Path(pointer_file)
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LegacyDatabaseRequiresSplit(
                f"database registry {pointer} is unreadable; restore it from backup "
                "or run database recovery and retry"
            ) from exc
        mode = data.get("mode")
        if mode == "legacy":
            legacy = Path(str(data.get("legacy_path") or ""))
            raise LegacyDatabaseRequiresSplit(
                f"rollback mode is active at {legacy}; use --db {legacy} for the "
                "legacy session, then run 'scrapex split-databases' to switch forward"
            )
        if mode != "split":
            raise LegacyDatabaseRequiresSplit(
                f"database registry {pointer} has an unknown mode; restore it from "
                "backup and retry"
            )
        general_raw = str(data.get("general_path") or "").strip()
        marketlens_raw = str(data.get("marketlens_path") or "").strip()
        if not general_raw or not marketlens_raw:
            raise LegacyDatabaseRequiresSplit(
                f"database registry {pointer} is incomplete; restore it and retry"
            )
        general_path = Path(general_raw)
        marketlens_path = Path(marketlens_raw)
        legacy_raw = str(data.get("legacy_path") or "").strip()
        return cls(
            GeneralDatabase(general_path),
            MarketLensDatabase(marketlens_path),
            Path(legacy_raw) if legacy_raw else None,
            pointer,
        )

    def initialize(self) -> dict[str, list[int]]:
        result = {
            "general": self.general.initialize(),
            "marketlens": self.marketlens.initialize(),
        }
        self.write()
        return result

    def ensure_ready(self) -> dict:
        """Create whichever database is not there yet, then report both.

        This exists so that starting the engine is the only thing the owner has
        to do. A database that does not exist holds nothing to lose, so creating
        it needs no permission and no warning.

        An EXISTING database is never migrated here. Advancing the schema of a
        file that already holds the owner's data is their decision (spec 40), so
        a database that is behind is reported with the command that upgrades it
        rather than upgraded behind their back. The caller decides what to do
        with a report that is not ok; this method never refuses on its own.
        """
        created: list[str] = []
        for database in (self.general, self.marketlens):
            if not database.path.is_file():
                database.initialize()
                created.append(database.kind)
        states = self.health()
        ok = all(item["ok"] for item in states.values())
        # The pointer names the pair that is actually usable. Writing it while a
        # database is unusable would record a broken pair as the live one.
        if created and ok:
            self.write()
        return {"ok": ok, "created": created, "databases": states}

    def verify(self) -> None:
        for database in (self.general, self.marketlens):
            health = database.health()
            if not health.ok:
                raise RuntimeError(
                    f"{health.kind} database is {health.status.lower()}: "
                    f"{health.action}"
                )

    def write(self) -> None:
        self.verify()
        self.pointer_file.parent.mkdir(parents=True, exist_ok=True)
        incoming = self.pointer_file.with_suffix(self.pointer_file.suffix + ".incoming")
        payload = {
            "format_version": 1,
            "mode": "split",
            "general_path": str(self.general.path),
            "marketlens_path": str(self.marketlens.path),
            "legacy_path": str(self.legacy_path) if self.legacy_path else None,
        }
        incoming.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(incoming, self.pointer_file)

    def backup_bundle(self, folder: Path | str) -> dict[str, str]:
        destination = Path(folder)
        general_backup = self.general.backup(destination / "general")
        marketlens_backup = self.marketlens.backup(destination / "marketlens")
        return {
            "general": str(general_backup),
            "marketlens": str(marketlens_backup),
        }

    def health(self) -> dict[str, dict]:
        return {
            "general": self.general.health().public(),
            "marketlens": self.marketlens.health().public(),
        }
