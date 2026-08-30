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

    #: The priced warehouse of a two-database installation. The FIELD is named
    #: for what it holds; the on-disk KEY that fills it still carries the old
    #: product's name and cannot be renamed -- see `read_split_pointer`. They are
    #: joined by exactly one call, so a find-and-replace over this file would
    #: rename both and break every installation that has not been carried over.
    priced: Path | None
    general: Path | None
    destination: Path
    pointer: Path

    @property
    def sources(self) -> list[Path]:
        return [path for path in (self.priced, self.general) if path is not None]


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
        # `"marketlens_path"` IS NOT A LEFTOVER NAME AND MUST NOT BE RENAMED.
        # It is a key inside `~/.scrapex/databases.json`, written there by a
        # SHIPPED version of ScrapeX before the two databases became one. That
        # file is on the owner's disk and cannot be rewritten from here; this is
        # the only reader left.
        #
        # AND THE FAILURE IS SILENT, which is why it is called out. `named()`
        # returns None for a key it cannot find, an absent path is not an error
        # (see `sources` above, which simply drops it), `carry_over` then reports
        # `ok` because a database it never opened contributes no rows to compare,
        # and the pointer is rewritten to `mode: single`. The installation comes
        # up healthy with its entire price history orphaned -- the exact trap the
        # header of this module exists to describe, re-created by a rename.
        #
        # Measured 2026-08-30: this machine still holds 115.8 MB at
        # `~/.scrapex/marketlens/marketlens.db`. Its own pointer already reads
        # `mode: single`, so it is past the gate; the owner works from two
        # machines and the other one's pointer has not been read.
        priced=named("marketlens_path"),
        general=named("general_path"),
        destination=DEFAULT_ENGINE_PATH,
        pointer=pointer,
    )


#: Tables the DESTINATION owns, with the reason each is here.
#:
#: Measured on the owner's real databases on 2026-08-11: every table of DATA
#: carried across exactly -- 88,286 price observations, 122,509 change events,
#: 37,452 product attributes, not one row short. These two came up short and
#: stopped the whole carry-over:
#:
#:     database_migration   62 -> 56
#:     scrapex_meta         26 -> 21
#:
#: Neither is data. `EngineDatabase.initialize()` writes its own schema version
#: and its own migration record when it creates the database, so some of the old
#: rows are duplicates and INSERT OR IGNORE drops them -- correctly. A new schema
#: must not inherit its predecessor's ledger; that is what makes it a new schema.
#:
#: They are still COPIED and still REPORTED. What changes is only that a
#: shortfall in one of them does not block the pointer, because a shortfall there
#: is expected rather than a loss. Written as a named set with this note rather
#: than as two names quietly dropped from a comparison: a guard that is narrowed
#: without saying why is a guard nobody can audit later.
LEDGER_TABLES = {
    "database_migration": "the destination writes its own migration record",
    "scrapex_meta": "the destination writes its own schema version",
}


@dataclass(frozen=True)
class Backfill:
    """A column the NEW schema requires that an OLD one never had.

    THE DEFECT THIS EXISTS FOR, found by running the carry-over for real on the
    owner's own installation on 2026-08-20:

        error: a selling unit must carry its provenance and its witness

    Migration 0058 added `source_offer.unit_basis_provenance` and
    `unit_basis_witness` plus two triggers that REFUSE a row carrying a
    `selling_unit_id` without both. 261 of this installation's 3,739 offers carry
    one, and the old schema has no such columns at all — so every carry-over of a
    pre-0058 installation aborted on the first of them, and the documented upgrade
    path was closed for exactly the installations it was written for.

    WHY A DECLARED TABLE AND NOT A POST-COPY UPDATE. The trigger fires on INSERT.
    A backfill that ran afterwards would never run, because the insert raises
    first. The value has to arrive WITH the row.

    WHY THIS IS NOT INVENTING EVIDENCE, which is the only thing that would make it
    unacceptable. 0058 met these same rows in the in-place upgrade path and already
    answered: `legacy_unwitnessed`, with a witness that says in words that nobody
    can say where the value came from. Under the resolution metric it counts as
    unresolved, which is the truth about it. This reuses that answer rather than
    minting a second one — and
    `tests/test_a_carry_over_upgrades_rather_than_starting_over.py` fails if the
    two ever drift apart.

    WHY IT IS CONDITIONAL. 0058's own `UPDATE` is `WHERE selling_unit_id IS NOT
    NULL`. An offer with no unit has nothing to say the provenance OF, and filling
    it would claim a fact about 3,478 rows that the migration deliberately leaves
    alone.
    """

    #: The table this applies to.
    table: str
    #: The column whose non-NULL value makes the fill apply, row by row.
    when: str
    #: `column -> value`, applied only where `when` is not NULL.
    values: dict[str, str]


#: What migration 0058 assigns to rows that predate it, reused verbatim.
LEGACY_UNWITNESSED = "legacy_unwitnessed"
LEGACY_WITNESS = (
    "pre-0058: written by normalize.selling_unit_from or a connector constant; "
    "the field it was read from was not recorded")

#: Every column the engine schema requires that a split-era schema lacked. Empty
#: until one is needed, and it needed one the first time it met real data.
BACKFILLS: tuple[Backfill, ...] = (
    Backfill(table="source_offer", when="selling_unit_id",
             values={"unit_basis_provenance": LEGACY_UNWITNESSED,
                     "unit_basis_witness": LEGACY_WITNESS}),
)


def _backfill_for(table: str, source_columns: list[str],
                  target_columns: list[str]) -> tuple[Backfill, list[str]] | None:
    """The backfill this table needs, and which of its columns are actually missing.

    ONLY COLUMNS THE SOURCE LACKS AND THE TARGET HAS. A source that already carries
    the column carries its VALUES too, and overwriting them with a legacy marker
    would replace real provenance with "nobody knows" — the exact inversion of what
    this is for.
    """
    for backfill in BACKFILLS:
        if backfill.table != table or backfill.when not in source_columns:
            continue
        missing = [name for name in backfill.values
                   if name in target_columns and name not in source_columns]
        if missing:
            return backfill, missing
    return None


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
        # WHAT THE DESTINATION ALREADY HOLDS. `initialize()` writes its own rows
        # -- schema version, migration ledger -- and counting those as carried
        # would make a short carry look complete. Comparing "rows read" against
        # "rows now in the table" was the first version of this check and it was
        # simply the wrong comparison; the baseline is what makes it right.
        baseline = {table: _row_count(target, table) for table in target_tables}
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

                    # A COLUMN THE NEW SCHEMA REQUIRES AND THE OLD ONE NEVER HAD.
                    # It has to arrive WITH the row: the trigger that demands it
                    # fires on INSERT, so a backfill afterwards never runs. See
                    # `Backfill` for why this reuses 0058's own value rather than
                    # minting a second one.
                    fill = _backfill_for(table, columns, target_columns)
                    if fill is not None:
                        backfill, missing = fill
                        gate = shared.index(backfill.when)
                        columns_out = shared + missing
                        payload = [
                            (*row, *(backfill.values[name] if row[gate] is not None
                                     else None for name in missing))
                            for row in payload]
                        quoted = ", ".join(f'"{c}"' for c in columns_out)
                        entry_columns = len(columns_out)
                        report.setdefault("backfilled", []).append(
                            {"table": table, "columns": missing,
                             "rows": sum(1 for row in payload if row[gate] is not None),
                             "why": "the new schema requires it and the old one had "
                                    "no such column; value from migration 0058"})
                    else:
                        entry_columns = len(shared)

                    # DISTINCT, because the two old files can legitimately hold
                    # the same row -- both carried `scrapex_meta`, for instance.
                    # `INSERT OR IGNORE` drops the second copy, and counting it
                    # as missing would fail every real carry-over.
                    distinct = len({tuple(row) for row in payload})
                    if not dry_run:
                        target.executemany(
                            f'INSERT OR IGNORE INTO "{table}" ({quoted}) '
                            f'VALUES ({", ".join("?" * entry_columns)})', payload)
                    entry = report["tables"].setdefault(
                        table, {"read": 0, "distinct": 0, "written": 0, "source": []})
                    entry["read"] += rows
                    entry["distinct"] += distinct
                    entry["source"].append(source_path.name)
                for table in sorted(_tables(source) - target_tables):
                    report["skipped"].append(
                        {"table": table, "rows": _row_count(source, table),
                         "why": "the new schema has no such table"})
            finally:
                source.close()

        if not dry_run:
            target.commit()
        for table, counts in report["tables"].items():
            counts["written"] = _row_count(target, table) - baseline.get(table, 0)
    finally:
        target.close()

    short = [
        {"table": name, **counts}
        for name, counts in report["tables"].items()
        if counts["written"] < counts["distinct"] and name not in LEDGER_TABLES
    ]
    report["ledgers"] = [
        {"table": name, "why": LEDGER_TABLES[name], **counts}
        for name, counts in report["tables"].items()
        if name in LEDGER_TABLES and counts["written"] < counts["distinct"]
    ]
    report["short"] = short
    report["ok"] = not short and not dry_run

    if short:
        # Fewer rows arrived than the sources hold DISTINCTLY, so something was
        # genuinely dropped rather than deduplicated. The pointer does not move
        # and a human decides.
        #
        # WHAT THIS STILL CANNOT SEE: a row that arrived with a different value
        # under the same key. The counts would agree and the content would not.
        # Proving that needs a per-row comparison this command does not do, and
        # saying so here is better than implying a guarantee it has not earned.
        return report

    if not dry_run:
        plan.pointer.write_text(
            json.dumps({"format_version": 2, "mode": "single",
                        "engine_path": str(plan.destination)}, indent=2),
            encoding="utf-8")
        report["pointer_moved_to"] = str(plan.destination)
    return report
