"""Collapse the engine migration chain into a new baseline, and PROVE the result.

    python -m tools.squash_engine_baseline --check     # verify, change nothing
    python -m tools.squash_engine_baseline --write     # regenerate the baseline

WHY A TOOL AND NOT A ONE-OFF SCRIPT. `R-84` makes squashing a repeated operation
with a boundary: before publication the chain may be collapsed whenever it has
grown long, and after publication never. A script that ran once and was deleted is
what `tools/derive_engine_schema.py` was -- it is named in `db/engine/schema.sql`'s
own header as the thing that generated it, and it has not existed in the tree since
migration 0002. The header cited a file nobody could run.

WHAT IT EMITS, and each part is here because leaving it out is silent:

  DDL            every table, view, index and trigger the chain produces, read from
                 `sqlite_master` of a database the chain actually built. Not from the
                 migration text: a column added by ALTER and a column declared inline
                 are the same schema and different SQL, and only the built database
                 knows which one won.
  SEED ROWS      the rows the chain leaves in an EMPTY database. A schema-only dump
                 loses them and nothing fails until something reads them -- measured
                 here: `0015` seeds the shipped retention default, and a baseline
                 without it produces an engine with no retention policy at all.
  THE VERSION    `PRAGMA user_version` = the chain's head, NOT 1. A baseline numbered
                 1 makes `_migrate` replay the whole schema over every database at a
                 higher version, and `db/engine/schema.sql` has 51 `CREATE TABLE` and
                 no `IF NOT EXISTS`.

WHAT IT DELIBERATELY DOES NOT EMIT: the `database_migration` ledger, which the runner
writes, and `scrapex_meta.contract_version`, which `EngineDatabase._migrate` stamps.
Emitting either would put a row in the file that the code writes again on every
initialize.

THE PROOF IS THE POINT. `--check` builds one database through the whole chain and
another from the generated baseline alone, then compares tables, columns with their
types and NOT NULL and DEFAULT, indexes with their columns, triggers, views, and every
seeded row. It exits non-zero on any difference. `--write` runs the same comparison
after writing and refuses to leave a baseline it could not verify.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scrapex import db as dbmod  # noqa: E402
from scrapex import version  # noqa: E402
from scrapex.databases.domain import EngineDatabase, Migration  # noqa: E402

BASELINE = ROOT / "db" / "engine" / "schema.sql"
MIGRATIONS = ROOT / "db" / "engine" / "migrations"
RECORD = ROOT / "db" / "engine" / "squashed-from.json"

#: Written by the runner, never by the file.
CODE_WRITTEN_TABLES = frozenset({"database_migration"})
CODE_WRITTEN_META = frozenset({"contract_version"})


def _fingerprint(conn: sqlite3.Connection) -> dict:
    """The schema as STRUCTURE, not as text.

    Deliberately not a diff of `sqlite_master.sql`: a column added by ALTER reads
    differently from the same column declared inline, and that difference is a
    formatting artefact rather than drift. This is the same shape
    `tests/test_migration_drift.py` compares, for the same reason.
    """
    out: dict = {"tables": {}, "indexes": {}, "triggers": [], "views": []}
    for kind, name in conn.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"):
        if kind == "table":
            out["tables"][name] = [
                [r[1], (r[2] or "").upper(), r[3], r[4], r[5]]
                for r in conn.execute(f'PRAGMA table_info("{name}")')]
            out["tables"][name].sort()
        elif kind == "index":
            out["indexes"][name] = sorted(
                [r[0], r[2] or "<expr>"]
                for r in conn.execute(f'PRAGMA index_info("{name}")'))
        elif kind == "trigger":
            out["triggers"].append(name)
        elif kind == "view":
            out["views"].append(name)
    out["triggers"].sort()
    out["views"].sort()
    return out


def _seed_rows(conn: sqlite3.Connection) -> dict:
    """Every row an EMPTY database ends up holding, minus what the runner writes.

    `applied_at`-style stamps would make this differ run to run, so the ledger is
    excluded wholesale rather than filtered column by column.
    """
    out: dict = {}
    for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if name in CODE_WRITTEN_TABLES:
            continue
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')]
        rows = []
        for row in conn.execute(f'SELECT * FROM "{name}"'):
            record = dict(zip(cols, row, strict=True))
            if name == "scrapex_meta" and record.get("key") in CODE_WRITTEN_META:
                continue
            # A timestamp defaulted at insert time is not part of the schema's
            # identity; it differs between two correct runs.
            record.pop("updated_at", None)
            rows.append(record)
        if rows:
            out[name] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    return out


def _build_from_chain(folder: Path) -> Path:
    """A database the SHIPPED chain built, through the real runner."""
    db = EngineDatabase(folder / "chain.db")
    db.initialize()
    return db.path


def _build_from_text(folder: Path, sql: str) -> Path:
    """A database the candidate baseline alone builds, through the real runner.

    Runs through `EngineDatabase` rather than `executescript` so the ledger and the
    contract marker are stamped exactly as they are in production -- the comparison
    is worth nothing if one side skips the code that writes rows.
    """
    scratch = folder / "candidate"
    scratch.mkdir()
    (scratch / "schema.sql").write_text(sql, encoding="utf-8")
    (scratch / "migrations").mkdir()
    db = EngineDatabase(folder / "fresh.db")
    original = (dbmod.SCHEMA_FILE, dbmod.MIGRATIONS_DIR)
    dbmod.SCHEMA_FILE = scratch / "schema.sql"
    dbmod.MIGRATIONS_DIR = scratch / "migrations"
    try:
        db._migrations = tuple(
            type(db._migrations[0])(number, path)
            for number, path in dbmod._migration_files())
        db.initialize()
    finally:
        dbmod.SCHEMA_FILE, dbmod.MIGRATIONS_DIR = original
    return db.path


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def generate() -> tuple[str, dict]:
    """The new baseline's text, and the record of what the chain produced."""
    head = dbmod.latest_schema_version()
    # NAME AND DIGEST, and the digest is what makes reconciliation provable rather
    # than merely convenient. A database that went through the chain holds these
    # exact digests in its `database_migration` ledger, so the runner can accept the
    # NEW baseline's digest for that database and refuse it for any other. Recorded
    # while the chain still exists, because after the squash there is nothing left to
    # compute them from.
    absorbed = [(number, path.name, Migration(number, path).sha256)
                for number, path in dbmod._migration_files()]
    with tempfile.TemporaryDirectory() as folder:
        built = _build_from_chain(Path(folder))
        conn = sqlite3.connect(str(built))
        try:
            objects = {kind: [] for kind in ("table", "view", "index", "trigger")}
            for kind, name, sql in conn.execute(
                    "SELECT type, name, sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY rowid"):
                if sql:                       # implicit indexes carry no SQL
                    objects[kind].append((name, sql))
            record = {"head": head, "absorbed": absorbed,
                      "fingerprint": _fingerprint(conn), "seed": _seed_rows(conn)}
            seed = _seed_rows(conn)
        finally:
            conn.close()

    lines = [
        "-- ScrapeX-Engine, one database, one schema.",
        "--",
        "-- GENERATED by tools/squash_engine_baseline.py from the migration chain it",
        f"-- replaces: {len(absorbed) - 1} numbered migrations collapsed into this file at",
        f"-- schema version {head}. Do not hand-edit --",
        "-- tests/test_the_squashed_baseline_carries_the_chain.py holds it against a",
        "-- frozen record of everything that chain produced.",
        "--",
        f"-- {len(objects['table'])} tables, {len(objects['index'])} indexes, "
        f"{len(objects['trigger'])} triggers, {len(objects['view'])} views.",
        "--",
        "-- R-84: the base may be collapsed BEFORE publication and never after it.",
        "-- Once a release marker exists, every migration is kept forever, because it",
        "-- is not determined which version any user stopped at.",
        "",
        "-- WHAT A FILE IS, before anything reads a table out of it. The application",
        "-- id lives in the SQLite header, so a backup restored into the wrong place is",
        "-- refused rather than half-used. Written from scrapex/database_ids.py, so the",
        "-- two cannot drift apart.",
        "PRAGMA foreign_keys = ON;",
        "PRAGMA application_id = 1398293838;  -- 0x5358454E",
        "",
    ]
    for kind, title in (("table", "tables"), ("view", "views"),
                        ("index", "indexes"), ("trigger", "triggers")):
        lines.append(f"-- ---- {title} " + "-" * (72 - len(title)))
        lines.append("")
        for _name, sql in objects[kind]:
            lines.append(sql.strip().rstrip(";") + ";")
            lines.append("")

    lines.append("-- ---- identity and shipped defaults " + "-" * 41)
    lines.append("")
    for table, rows in sorted(seed.items()):
        cols = list(rows[0])
        lines.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES")
        values = [f"    ({', '.join(_sql_literal(r[c]) for c in cols)})" for r in rows]
        lines.append(",\n".join(values) + ";")
        lines.append("")

    lines.append("-- THE VERSION THIS FILE ALREADY IS, not 1. A baseline numbered below a")
    lines.append("-- live database's version makes the runner replay this whole schema over")
    lines.append("-- it, and there is no IF NOT EXISTS anywhere in here.")
    lines.append(f"PRAGMA user_version = {head};")
    return "\n".join(lines) + "\n", record


def verify(sql: str) -> list[str]:
    """Every difference between a chain build and a baseline-only build."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as folder:
        chain = _build_from_chain(Path(folder))
        fresh = _build_from_text(Path(folder), sql)
        a, b = sqlite3.connect(str(chain)), sqlite3.connect(str(fresh))
        try:
            want, got = _fingerprint(a), _fingerprint(b)
            for part in ("tables", "indexes"):
                only_chain = sorted(set(want[part]) - set(got[part]))
                only_fresh = sorted(set(got[part]) - set(want[part]))
                if only_chain:
                    problems.append(f"{part} the chain has and the baseline does not: {only_chain}")
                if only_fresh:
                    problems.append(f"{part} the baseline has and the chain does not: {only_fresh}")
                for name in sorted(set(want[part]) & set(got[part])):
                    if want[part][name] != got[part][name]:
                        problems.append(
                            f"{part[:-1]} {name!r} differs:\n"
                            f"    chain   : {want[part][name]}\n"
                            f"    baseline: {got[part][name]}")
            for part in ("triggers", "views"):
                if want[part] != got[part]:
                    problems.append(
                        f"{part} differ: only in the chain "
                        f"{sorted(set(want[part]) - set(got[part]))}, only in the "
                        f"baseline {sorted(set(got[part]) - set(want[part]))}")
            seed_want, seed_got = _seed_rows(a), _seed_rows(b)
            if seed_want != seed_got:
                for table in sorted(set(seed_want) | set(seed_got)):
                    if seed_want.get(table) != seed_got.get(table):
                        problems.append(
                            f"seed rows of {table!r} differ:\n"
                            f"    chain   : {seed_want.get(table)}\n"
                            f"    baseline: {seed_got.get(table)}")
            for label, conn in (("chain", a), ("baseline", b)):
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                if version != dbmod.latest_schema_version():
                    problems.append(
                        f"the {label} build is at user_version {version}, expected "
                        f"{dbmod.latest_schema_version()}")
        finally:
            a.close()
            b.close()
    return problems


def _check_against_ref(ref: str) -> int:
    """A collapsed baseline against the chain still present on `ref`.

    This is what "verified" can mean after the files are gone and before the squash
    merges. If the chain on that ref has moved -- a migration added, or one edited --
    the baseline is a claim about a chain that no longer exists, and
    **every merge that adds a migration invalidates a generated baseline**.
    """
    if not RECORD.is_file():
        print(f"{RECORD.name} is missing, so there is nothing to check this baseline "
              "against, and it cannot be regenerated from a tree with no chain in it.")
        return 1
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    absorbed = {name: sha for _number, name, sha in record["absorbed"]}
    folder_names = set(absorbed) - {"schema.sql"}
    print(f"the chain is collapsed; checking the record against {ref}")

    listed = subprocess.run(
        ["git", "ls-tree", "--name-only", f"{ref}:db/engine/migrations"],
        cwd=str(ROOT), capture_output=True)
    on_ref = set(listed.stdout.decode("utf-8", errors="replace").split())
    problems: list[str] = []
    for name in sorted(on_ref - folder_names):
        problems.append(f"{name} is on {ref} and this baseline did not absorb it")
    for name in sorted(folder_names - on_ref):
        problems.append(f"{name} was absorbed and is not on {ref}")

    newline = chr(13) + chr(10)
    for name, recorded in sorted(absorbed.items()):
        path = ("db/engine/schema.sql" if name == "schema.sql"
                else f"db/engine/migrations/{name}")
        shown = subprocess.run(["git", "show", f"{ref}:{path}"],
                               cwd=str(ROOT), capture_output=True)
        if shown.returncode != 0:
            problems.append(f"{path} is not on {ref} at all")
            continue
        # The same normalisation `Migration.sha256` uses: the repository stores LF and
        # a Windows checkout reads CRLF, so raw bytes would differ by platform.
        raw = shown.stdout.replace(newline.encode(), b"\n").replace(b"\r", b"\n")
        if hashlib.sha256(raw).hexdigest() != recorded:
            problems.append(
                f"{name} differs: the record says {recorded[:12]} and {ref} has "
                f"{hashlib.sha256(raw).hexdigest()[:12]}")

    for problem in problems:
        print(f"  {problem}")
    print(f"absorbed migrations checked: {len(absorbed)}  differences: {len(problems)}")
    if problems:
        print("REGENERATE: this baseline is a claim about a chain that has moved.")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="regenerate db/engine/schema.sql and the frozen record")
    parser.add_argument("--check", action="store_true",
                        help="verify the CURRENT baseline against the chain, or, once "
                             "collapsed, against the chain still on --against")
    parser.add_argument("--against", default="origin/main",
                        help="the ref whose chain a collapsed baseline is checked "
                             "against (default: origin/main)")
    args = parser.parse_args()
    if not (args.write or args.check):
        parser.error("choose --write or --check")

    if args.check:
        # ALREADY COLLAPSED? Then there is no chain here to build a database from and
        # `verify()` cannot run: the plan builder rejects a migration numbered at or
        # below the baseline, which is `OP-122`'s rule doing its job. Run in that
        # state it answered with a ValueError about migration 0002 -- true, and no
        # use to the person asking.
        #
        # What CAN be checked, and is the only thing worth checking in the window
        # between a squash and its merge, is that the record still describes the chain
        # on the ref this will merge into. The record names every absorbed migration
        # WITH ITS DIGEST, so each one is comparable even though the files are gone.
        if not any(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            return _check_against_ref(args.against)
        problems = verify(BASELINE.read_text(encoding="utf-8"))
        for problem in problems:
            print(problem)
        print(f"{len(problems)} difference(s) between the chain and the baseline")
        return 1 if problems else 0

    if version.PUBLISHED_TO_OTHERS:
        print("REFUSING TO SQUASH: scrapex/version.py says PUBLISHED_TO_OTHERS is")
        print("True, and R-84 keeps every migration from publication onwards --")
        print("nobody can say which version a user stopped at, so a migration this")
        print("tree deletes is an upgrade path somebody still needs.")
        print()
        print("If that flag is wrong, correcting it is the change to make first, on")
        print("its own, with the reason recorded. Not as a side effect of a squash.")
        return 1

    sql, record = generate()
    problems = verify(sql)
    if problems:
        print("REFUSING TO WRITE — the generated baseline does not match the chain:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    BASELINE.write_text(sql, encoding="utf-8", newline="\n")
    RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")
    print(f"wrote {BASELINE.relative_to(ROOT)} at schema version {record['head']}")
    print(f"wrote {RECORD.relative_to(ROOT)} — {len(record['absorbed'])} absorbed, "
          f"{len(record['fingerprint']['tables'])} tables, "
          f"{sum(len(v) for v in record['seed'].values())} seed rows")
    print("verified: a database built from this file alone is identical to one built "
          "through the whole chain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
