"""Carry a two-database installation into the single file that replaced it.

THE DEFECT THIS EXISTS FOR, found on the owner's own machine on 2026-08-11.
`~/.scrapex/databases.json` still said `"mode": "split"`, so every engine command
refused to start with:

    ... points at the two-database layout that ScrapeX used before it kept
    everything in one file. Nothing has been changed and nothing has been lost:
    the old files are still where they were. Run 'scrapex init-db' to create the
    single database, then 'scrapex database-status'.

Both sentences are true and together they are a trap. `init-db` creates a NEW
database and applies migrations to it; it does not read `marketlens.db` and never
has. Following that instruction on this installation would have produced an empty
warehouse beside 110 MB of prices that nothing would ever open again.

Nobody noticed because the engine had simply stopped starting, and a side panel
whose engine never answers looks like a side panel problem. It cost most of a day
before anyone read the pointer file.

WHAT THIS DOES, and the order matters. It copies every row of every shared table
from the old files into the new one, verifies the counts match, and only then
rewrites the pointer. If anything disagrees the pointer is left alone, so a
failed carry-over leaves an installation that still refuses to start rather than
one that starts on top of half its data.

The old files are never deleted or altered. They are opened read-only.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .domain import EngineDatabase
from .registry import DEFAULT_ENGINE_PATH, REGISTRY_FILE, DatabasePointerError


@dataclass(frozen=True)
class CarryOverPlan:
    """What was found, before anything is written."""

    marketlens: Path | None
    general: Path | None
    destination: Path
    pointer: Path

    @property
    def sources(self) -> list[Path]:
        return [path for path in (self.marketlens, self.general) if path is not None]


def read_split_pointer(pointer_file: Path | str = REGISTRY_FILE) -> CarryOverPlan:
    """Read a `split` pointer, or say why this installation is not one.

    Refusing early and by name matters more than usual here: the command that
    follows writes a database, and "there was nothing to carry" and "the carry
    silently found no rows" must never look the same to a caller.
    """
    pointer = Path(pointer_file)
    if not pointer.is_file():
        raise DatabasePointerError(
            f"there is no {pointer}, so there is no two-database installation "
            "to carry over. Run 'scrapex init-db' to create the single database.")
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabasePointerError(
            f"{pointer} could not be read, so what it points at is unknown. "
            "Restore it from a backup rather than guessing.") from exc

    mode = data.get("mode")
    if mode == "single":
        raise DatabasePointerError(
            f"{pointer} already points at a single database "
            f"({data.get('engine_path')}). There is nothing to carry over.")
    if mode not in ("split", "legacy"):
        raise DatabasePointerError(
            f"{pointer} does not describe a two-database installation "
            f"(mode={mode!r}), so this command cannot tell what to carry.")

    def named(key: str) -> Path | None:
        raw = str(data.get(key) or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_file():
            raise DatabasePointerError(
                f"{pointer} names {path} as its {key}, and that file is not "
                "there. Restore it before carrying anything over: a carry-over "
                "that skipped it would look like a success.")
        return path

    return CarryOverPlan(
        marketlens=named("marketlens_path"),
        general=named("general_path"),
        destination=DEFAULT_ENGINE_PATH,
        pointer=pointer,
    )


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")
    }


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def carry_over(
    plan: CarryOverPlan,
    *,
    migrations: tuple = (),
    dry_run: bool = False,
) -> dict:
    """Copy every shared table across, count both sides, then move the pointer.

    THE POINTER MOVES LAST, and only if every table agrees. A carry-over that
    wrote the pointer first and then failed would leave an installation that
    starts and serves an incomplete warehouse -- which is worse than one that
    refuses to start, because nothing would say so.
    """
    # `initialize`, not `connect`: the destination does not exist yet on the
    # installation this command is for. The registry's own initialize() would
    # also WRITE the pointer, and the pointer must not move until every row is
    # accounted for — so the database is created directly and the pointer is
    # left to the end of this function.
    plan.destination.parent.mkdir(parents=True, exist_ok=True)
    EngineDatabase(plan.destination).initialize()

    report: dict = {"destination": str(plan.destination), "tables": {}, "skipped": []}

    target = sqlite3.connect(plan.destination)
    try:
        target_tables = _tables(target)
        for source_path in plan.sources:
            source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
            try:
                for table in sorted(_tables(source) & target_tables):
                    rows = _row_count(source, table)
                    if rows == 0:
                        continue
                    columns = [r[1] for r in source.execute(f'PRAGMA table_info("{table}")')]
                    target_columns = [
                        r[1] for r in target.execute(f'PRAGMA table_info("{table}")')]
                    shared = [c for c in columns if c in target_columns]
                    if not shared:
                        # A table whose columns no longer overlap is not a table
                        # this version knows how to carry. Named, never skipped
                        # in silence -- an unreported skip is how a migration
                        # loses a year of prices and reports success.
                        report["skipped"].append(
                            {"table": table, "rows": rows,
                             "why": "no column in common with the new schema"})
                        continue
                    quoted = ", ".join(f'"{c}"' for c in shared)
                    payload = source.execute(
                        f'SELECT {quoted} FROM "{table}"').fetchall()
                    if not dry_run:
                        target.executemany(
                            f'INSERT OR IGNORE INTO "{table}" ({quoted}) '
                            f'VALUES ({", ".join("?" * len(shared))})', payload)
                    entry = report["tables"].setdefault(
                        table, {"read": 0, "written": 0, "source": []})
                    entry["read"] += rows
                    entry["source"].append(source_path.name)
                for table in sorted(_tables(source) - target_tables):
                    report["skipped"].append(
                        {"table": table, "rows": _row_count(source, table),
                         "why": "the new schema has no such table"})
            finally:
                source.close()

        if not dry_run:
            target.commit()
        for table in report["tables"]:
            report["tables"][table]["written"] = _row_count(target, table)
    finally:
        target.close()

    short = [
        {"table": name, **counts}
        for name, counts in report["tables"].items()
        if counts["written"] < counts["read"]
    ]
    report["short"] = short
    report["ok"] = not short and not dry_run

    if short:
        # INSERT OR IGNORE drops a row whose key already exists, which is right
        # when a carry-over is re-run and wrong if it hides a real loss. Either
        # way the pointer does not move: a human decides.
        return report

    if not dry_run:
        plan.pointer.write_text(
            json.dumps({"format_version": 2, "mode": "single",
                        "engine_path": str(plan.destination)}, indent=2),
            encoding="utf-8")
        report["pointer_moved_to"] = str(plan.destination)
    return report
