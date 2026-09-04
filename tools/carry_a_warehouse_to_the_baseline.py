"""Walk a warehouse BELOW the squashed baseline up to it, with the chain from history.

WHY THIS EXISTS. `R-84` collapsed sixteen migrations into `db/engine/schema.sql` at
schema v17, and `EngineDatabase._migrate` refuses anything between 1 and 16: there is no
upgrade path, so the refusal is correct and total (`OP-135`). The refusal's own advice is
*"bring it to v17 with the last release that still carried those migrations"* — and
`OP-134` measured that **no release ever carried the chain past v10**, so that advice
names an artefact that does not exist. This is the thing that does.

He hit it twice in one day, which is why it is worth a tool rather than a session's
one-off: the home machine's warehouse at v10 (renamed aside on his instruction), and then
*«كان ظاهر على جهاز آخر ومنذ تحديثات اليوم اختفى»* — the work machine, measured at
`user_version = 16` by `R-84` itself, where 17,304 contractors and 17,385 profiles stop
being reachable the moment 0.4.8 opens it.

WHAT MAKES IT SAFE, and each of these is a step below rather than a claim:

  - **The chain is PROVED, not trusted.** `db/engine/squashed-from.json` records every
    absorbed migration with its digest. Each file is recovered from git history and
    hashed against that record — the same normalisation `Migration.sha256` uses, so a
    CRLF checkout cannot fail it. Measured on this repository: 17 of 17 verified.
  - **The engine's own runner applies it.** This does not re-implement the migration
    loop: it points `db.SCHEMA_FILE`/`MIGRATIONS_DIR` at the recovered chain and calls
    `EngineDatabase.initialize()`, so the transaction discipline, the suspended foreign
    keys, the `foreign_key_check` compensator and the ledger stamping are the shipped
    ones. A rescue that hand-rolled SQL would be a second migration runner, which is
    exactly what `R-72` deleted.
  - **It rehearses by default.** Nothing touches the named file until `--apply`, and the
    rehearsal is a real run against a real copy, not a simulation.
  - **It backs up before it writes**, names the copy, and refuses if the copy fails.
  - **It ends by asking the SHIPPED build**, not itself: after the walk it restores the
    real plan and calls `initialize()` again so the squashed baseline reconciles the
    ledger, then requires `health().ok`. That reconciliation is not new machinery — it is
    what `test_a_database_that_went_through_the_chain_opens` covers.

IT IS AN OPERATOR TOOL AND NOT A FEATURE, which is why it is in `tools/`. He does not use
a terminal (`R-81`), so this is run FOR him, from a checkout; the panel-side answer to the
same fault is `OP-144`'s missing control and `OP-133`'s ruling. Recording that here rather
than letting the tool read as the product's answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scrapex import db as dbmod  # noqa: E402
from scrapex.archive import backup_database  # noqa: E402
from scrapex.database_ids import ENGINE_APPLICATION_ID  # noqa: E402
from scrapex.databases.domain import EngineDatabase  # noqa: E402

RECORD = ROOT / "db" / "engine" / "squashed-from.json"

#: The commit the squash replaced. Its tree still holds every absorbed file, and the
#: digests below are what make naming it safe rather than a matter of memory — a
#: different commit with the same files verifies identically, and one with edited files
#: fails loudly.
PRE_SQUASH = "9cbc6f0"


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          check=True).stdout


def _normalised(raw: bytes) -> str:
    """`Migration.sha256`'s rule: the SQL, not the platform's newlines."""
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def recover_chain(folder: Path, ref: str = PRE_SQUASH) -> tuple[Path, Path]:
    """Write the absorbed chain into `folder`, verifying every file's digest.

    Returns `(baseline, migrations_dir)` in the shape `db.SCHEMA_FILE` and
    `db.MIGRATIONS_DIR` expect.
    """
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    migrations = folder / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)
    baseline = folder / "schema.sql"

    for number, name, digest in record["absorbed"]:
        where = ("db/engine/schema.sql" if name == "schema.sql"
                 else f"db/engine/migrations/{name}")
        try:
            raw = _git("show", f"{ref}:{where}")
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                f"v{number} ({name}) is not in {ref}: {exc}. The record says the "
                "squash absorbed it, so either the ref is wrong or history was "
                "rewritten -- and neither is something this tool may guess past.")
        got = _normalised(raw)
        if got != digest:
            raise SystemExit(
                f"v{number} ({name}) does not match the record.\n"
                f"  squashed-from.json {digest}\n  {ref} {got}\n"
                "This file is not the one that was absorbed. Refusing: applying it "
                "would put a schema in the warehouse that no baseline describes.")
        target = baseline if name == "schema.sql" else migrations / name
        target.write_bytes(raw)
    return baseline, migrations


def _identity(path: Path) -> tuple[int, int, str]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
        quick = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
    finally:
        conn.close()
    return version, app_id, quick


def carry(path: Path, ref: str = PRE_SQUASH) -> int:
    """Walk `path` to the baseline in place. Returns the version it reached."""
    baseline_version = dbmod.declared_schema_version(dbmod.SCHEMA_FILE)
    version, app_id, quick = _identity(path)

    if quick != "ok":
        raise SystemExit(
            f"{path.name} fails `quick_check`: {quick}. Migrating a damaged file is "
            "how a small corruption becomes an unrecoverable one -- restore a backup "
            "first.")
    if app_id != ENGINE_APPLICATION_ID:
        raise SystemExit(
            f"{path.name} carries application_id {app_id}, not the engine's "
            f"{ENGINE_APPLICATION_ID}. This is not a ScrapeX engine warehouse.")
    if version <= 0:
        raise SystemExit(f"{path.name} has no ScrapeX schema version to walk from.")
    if version >= baseline_version:
        print(f"{path.name} is at v{version} and the baseline is v{baseline_version} "
              "-- nothing to carry, this tool is for a warehouse BELOW it.")
        return version

    print(f"{path.name}: v{version} -> v{baseline_version}")
    made = backup_database(path, tag="pre-carry")
    print(f"  backed up to {made.name} ({made.stat().st_size:,} bytes)")

    with tempfile.TemporaryDirectory(prefix="scrapex-absorbed-chain-") as folder:
        chain_baseline, chain_migrations = recover_chain(Path(folder), ref=ref)
        print(f"  recovered the absorbed chain from {ref}, every digest verified")

        real = (dbmod.SCHEMA_FILE, dbmod.MIGRATIONS_DIR)
        try:
            dbmod.SCHEMA_FILE, dbmod.MIGRATIONS_DIR = chain_baseline, chain_migrations
            walking = EngineDatabase(path)
            applied = walking.initialize()
        finally:
            dbmod.SCHEMA_FILE, dbmod.MIGRATIONS_DIR = real
    print(f"  applied {applied}")

    # THE SHIPPED BUILD HAS THE LAST WORD, not this tool. `initialize()` on the real
    # plan is what rewrites the ledger to the squashed baseline's own digest -- accepted
    # on read, upgraded on stamp -- and `health()` is the answer the panel would get.
    settled = EngineDatabase(path)
    reconciled = settled.initialize()
    report = settled.health()
    if not report.ok:
        raise SystemExit(
            f"carried to v{version} but the shipped build still refuses it: "
            f"{report.status} -- {report.action}")
    print(f"  the shipped baseline reconciled it ({reconciled or 'ledger only'})")
    print(f"  health: {report.status} at v{report.schema_version}")
    return report.schema_version or baseline_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="carry_a_warehouse_to_the_baseline",
        description="Walk a warehouse below R-84's squashed baseline up to it.")
    parser.add_argument("database", help="the warehouse to carry")
    parser.add_argument("--apply", action="store_true",
                        help="write to the named file; without this it rehearses on a "
                             "copy and the original is never opened for writing")
    parser.add_argument("--ref", default=PRE_SQUASH,
                        help=f"the commit to recover the chain from (default {PRE_SQUASH})")
    args = parser.parse_args(argv)

    path = Path(args.database).expanduser()
    if not path.is_file():
        raise SystemExit(f"there is no database at {path}")

    if args.apply:
        print("APPLYING to the named file.")
        carry(path, ref=args.ref)
        print("\nDone. Start the engine; it opens this warehouse now.")
        return 0

    # A REHEARSAL IS A REAL RUN ON A REAL COPY, which is the only kind worth having: a
    # simulation would prove the tool's reasoning rather than the migrations' effect on
    # HIS rows. `R-24` -- the data survives the schema -- is not satisfied by a dry run
    # that never executes the SQL.
    with tempfile.TemporaryDirectory(prefix="scrapex-carry-rehearsal-") as folder:
        copy = Path(folder) / path.name
        print(f"rehearsing on a copy of {path} ({path.stat().st_size:,} bytes)")
        shutil.copy2(path, copy)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.is_file():
                shutil.copy2(sidecar, f"{copy}{suffix}")
        reached = carry(copy, ref=args.ref)
        print(f"\nREHEARSAL ONLY -- {path.name} was not written to. It reached "
              f"v{reached} on the copy.")
        print("Run again with --apply to do it for real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
