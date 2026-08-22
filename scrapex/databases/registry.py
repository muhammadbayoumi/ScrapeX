"""Where the engine's one database is, and whether it is fit to open.

M5 collapsed two databases into one. What is left of this module is small on
purpose: a registry whose job was coordinating a PAIR — two files that had to be
initialised together, backed up together, and never half-promoted — has almost
nothing left to coordinate.

IT IS NOT DELETED, and that is deliberate rather than lazy. The pointer file is
still the answer to "which file is the live one", which matters the moment a
database lives anywhere but the default path: a second disk, a restored copy, a
machine where `SCRAPEX_DATA_ROOT` was set once and forgotten. Removing it would
replace one readable file with a rule spread across every caller.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .domain import EngineDatabase

DATABASE_ROOT = Path(
    os.environ.get("SCRAPEX_DATA_ROOT", str(Path.home() / ".scrapex"))
)
REGISTRY_FILE = Path(
    os.environ.get("SCRAPEX_DATABASE_REGISTRY", str(DATABASE_ROOT / "databases.json"))
)

#: One file, named after the engine that owns it. `scrapex-engine.exe` beside
#: `scrapex-engine.db` — the owner's instruction, and it means a support
#: conversation never has to establish which file is meant.
DEFAULT_ENGINE_PATH = DATABASE_ROOT / "engine" / "scrapex-engine.db"

#: What this version writes. A pointer from before the collapse says "split" and
#: names two files that no longer make a pair.
POINTER_FORMAT = 2


class DatabasePointerError(RuntimeError):
    """The pointer file does not describe a database this version can open."""


@dataclass(frozen=True)
class DatabaseRegistry:
    engine: EngineDatabase
    pointer_file: Path = REGISTRY_FILE

    def __post_init__(self) -> None:
        if self.engine.path.resolve() == self.pointer_file.resolve():
            raise ValueError(
                "the database and the registry cannot be the same file")

    @classmethod
    def defaults(cls, *, pointer_file: Path | str = REGISTRY_FILE) -> DatabaseRegistry:
        pointer = Path(pointer_file)
        if pointer.is_file():
            return cls.read(pointer)
        return cls(EngineDatabase(DEFAULT_ENGINE_PATH), pointer_file=pointer)

    @classmethod
    def read(cls, pointer_file: Path | str = REGISTRY_FILE) -> DatabaseRegistry:
        pointer = Path(pointer_file)
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatabasePointerError(
                f"the database pointer {pointer} could not be read; delete it and "
                "run 'scrapex init-db', or restore it from a backup"
            ) from exc

        mode = data.get("mode")
        if mode in ("split", "legacy"):
            # A POINTER FROM BEFORE THE COLLAPSE, and the message has to say so
            # in those words. Everything about it looks valid — it parses, it
            # names real files, those files exist — so the failure without this
            # branch is a KeyError on `engine_path`, which sends someone
            # debugging this module instead of running one command.
            raise DatabasePointerError(
                f"{pointer} points at the two-database layout that ScrapeX used "
                "before it kept everything in one file. Nothing has been changed "
                "and nothing has been lost: the old files are still where they "
                "were. Run 'scrapex carry-over' to copy them into the single "
                "database, then 'scrapex database-status'. "
                "NOT 'init-db': that is what this message used to say and it "
                "was a trap, because init-db creates a NEW database and applies "
                "migrations to it and never reads the old files. On an "
                "installation with data in them it produces an empty warehouse "
                "beside a full one that nothing will open again.")
        if mode != "single":
            raise DatabasePointerError(
                f"{pointer} does not say which database is live (mode={mode!r}); "
                "delete it and run 'scrapex init-db'")

        raw = str(data.get("engine_path") or "").strip()
        if not raw:
            raise DatabasePointerError(
                f"{pointer} names no database; delete it and run 'scrapex init-db'")
        return cls(EngineDatabase(Path(raw)), pointer)

    def initialize(self) -> dict[str, list[int]]:
        result = {self.engine.kind: self.engine.initialize()}
        self.write()
        return result

    def ensure_ready(self) -> dict:
        """Create the database if it is not there, then report it.

        This exists so that starting the engine is the only thing the owner has
        to do. A database that does not exist holds nothing to lose, so creating
        it needs no permission and no warning.

        AN EXISTING DATABASE IS NEVER MIGRATED HERE. Advancing the schema of a
        file that already holds the owner's data is their decision (spec 40), so
        a database that is behind is reported with the command that upgrades it
        rather than upgraded behind their back. The caller decides what to do
        with a report that is not ok; this method never refuses on its own.

        AND SINCE 2026-08-05 ONE CALLER DECIDES TO UPGRADE. `scrapex ui` — the
        single path every launch takes, terminal or panel button or autostart —
        backs the file up and migrates it when its ONLY fault is being behind
        (cli._upgrade_what_is_only_behind). The owner asked for that after
        migration 0061 merged, was never applied here, and the engine refused to
        start with the exact command to fix it in a log he had no reason to
        read: the rule protected his data and cost him the product.

        This sentence stays true of THIS method, and the protections spec 40
        existed for are kept in the caller — a backup first without exception,
        forward only, never over damage, and said out loud. Nothing else in the
        codebase may migrate an existing file.
        """
        created: list[str] = []
        if not self.engine.path.is_file():
            self.engine.initialize()
            created.append(self.engine.kind)
        states = self.health()
        ok = all(item["ok"] for item in states.values())
        # The pointer names the database that is actually usable. Writing it
        # while the database is unusable would record a broken file as the live
        # one, and the next run would trust it.
        if created and ok:
            self.write()
        return {"ok": ok, "created": created, "databases": states}

    def verify(self) -> None:
        health = self.engine.health()
        if not health.ok:
            raise RuntimeError(
                f"{health.kind} database is {health.status.lower()}: {health.action}")

    def write(self) -> None:
        self.verify()
        self.pointer_file.parent.mkdir(parents=True, exist_ok=True)
        incoming = self.pointer_file.with_suffix(self.pointer_file.suffix + ".incoming")
        payload = {
            "format_version": POINTER_FORMAT,
            "mode": "single",
            "engine_path": str(self.engine.path),
        }
        incoming.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # Written whole and then moved into place: a pointer half-written by a
        # process that died is a pointer nothing can read, and it names the only
        # file that holds anything.
        os.replace(incoming, self.pointer_file)

    def backup_bundle(self, folder: Path | str) -> dict[str, str]:
        return {self.engine.kind: str(self.engine.backup(Path(folder) / self.engine.kind))}

    def health(self, *, integrity: bool = True) -> dict[str, dict]:
        """`integrity=False` for a timed poll: see `EngineDatabase.health`."""
        return {self.engine.kind: self.engine.health(integrity=integrity).public()}
