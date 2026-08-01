"""Reclaiming space without ever deleting an observation (spec section 18).

price_observation is append-only and stays that way. So a compaction does not
remove rows: it BUILDS A NEW DATABASE containing the rows the policy keeps,
verifies it, and switches the location pointer to it. The previous file is
renamed to `harvest.sealed-<stamp>.db` and left on disk — ScrapeX never unlinks
it. Every observation that ever existed is still in that file.

Three consequences the interface must state, and does:

- **A run frees nothing by itself.** It temporarily needs room for a second copy,
  and space is only returned when the owner removes the sealed archive
  themselves, in their own file manager.
- **The preview IS the compaction**, run into a throwaway file. The size it
  reports is the real size of a real database, not a model, because a modelled
  estimate is a second implementation and would drift from the first.
- **The switch commits on the pointer write.** The live file is never renamed
  before a verified successor exists, so there is no instant where the recorded
  location has no database at it.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import db as dbmod
from . import retention, settings, storage
from .database_ids import MARKETLENS_APPLICATION_ID

# Tables NOT copied verbatim. Everything else is discovered from the schema
# rather than listed here: a hand-written copy list silently drops whatever a
# future migration adds, and "silently drops a table" is the one outcome this
# module exists to make impossible.
_NOT_COPIED = {
    "price_observation",   # the whole point: carried forward selectively
    "retention_run",       # lineage is per file; the successor gets its own row
}


def _tables_to_copy(src: sqlite3.Connection, dst: sqlite3.Connection) -> list[str]:
    """Every table both databases have, minus the two handled specially.

    Foreign keys are off during the copy, so insertion order does not matter and
    no dependency ordering has to be maintained by hand.
    """
    return sorted((_existing_tables(src) & _existing_tables(dst)) - _NOT_COPIED)


class CompactionAborted(RuntimeError):
    """A successor was refused. The live database was only ever read."""


@dataclass
class CompactionResult:
    ok: bool
    observations_before: int = 0
    observations_after: int = 0
    protected_count: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    built_path: str = ""
    sealed_path: str = ""
    detail: str = ""
    problems: list[str] = field(default_factory=list)
    stale_pins: int = 0            # marks that name an observation not held here

    @property
    def observations_left_behind(self) -> int:
        return max(0, self.observations_before - self.observations_after)

    @property
    def bytes_the_archive_would_free(self) -> int:
        """Named for what it is: the sealed file's size, freed only if the owner
        deletes it. Calling this "recovered space" would be a lie — a run
        recovers nothing on its own."""
        return self.bytes_before

    def as_state(self) -> dict:
        return {"ok": self.ok, "rows": self.observations_after,
                "location": self.sealed_path or self.built_path,
                "detail": self.detail, "at": settings.utc_now()}


# ---- building ----------------------------------------------------------------

def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    """Tables this product owns.

    `sqlite_%` is excluded because SQLite creates its own: PRAGMA optimize (which
    Repair runs) creates `sqlite_stat1`. Counting that as a table meant one press
    of Repair made the source and a fresh successor differ forever, and every
    later compaction and preview was refused for a table nobody wrote.
    """
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%'")}


def _typed_class_for(path: Path):
    """The typed database boundary that owns this file, or None for a legacy one.

    Asked of `PRAGMA application_id`, which SQLite keeps in the file header and
    no query can copy — deliberately NOT of `scrapex_meta.database_kind`. That
    row is an ordinary row in an ordinary table, so `_copy_table` carries it into
    the successor verbatim: a successor built the wrong way still says
    'marketlens' about itself. Asked that way, a wrong successor vouches for
    itself and the check is worthless. The application id is the one answer it
    cannot forge, and it is exactly the one `MarketLensDatabase._verify` reads.

    Only MarketLens is recognised because only MarketLens has price observations;
    a General database has no `price_observation` to compact, and `dbmod.connect`
    refuses it outright before ever reaching here. Anything else is a legacy
    unmarked warehouse, which has no typed door and keeps the legacy build.
    """
    from .databases.domain import MarketLensDatabase   # local: databases/ imports down to here

    # `sqlite3.connect` CREATES what it cannot find, and this is asked about the
    # source — the file `build_successor` promises to read and never write. A
    # missing warehouse must stay missing and fail at the caller's open, not be
    # quietly conjured here as an empty database with no application id.
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(path))
    except sqlite3.DatabaseError:
        return None
    try:
        app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()
    return MarketLensDatabase if app_id == MARKETLENS_APPLICATION_ID else None


def _prepare_successor(source: Path, target: Path) -> None:
    """Create the successor's schema the way the SOURCE'S OWN KIND creates it.

    This is the defect in #53. Compaction used to build every successor with
    `dbmod.migrate` — the legacy, untyped stream — whatever the source was. That
    stream is not the MarketLens one: it replays all 57 legacy files, including
    the three (0013, 0014, 0017) that belong to General alone, and it never
    applies MarketLens's own identity migration. Measured against the owner's
    warehouse the two disagree on everything that identifies a database:

        source (MarketLensDatabase)   40 tables  v55  app id 1398295884  ledger 55
        successor (dbmod.migrate)     50 tables  v57  app id 0           no ledger

    So the product could not open its own output. Building it through the same
    typed boundary the source came from is the fix, and it is a fix rather than a
    patch: nothing is stamped onto the successor afterwards to make it acceptable.
    It is the right kind because it was BUILT as that kind, and if it cannot be,
    the build fails here — before anything has been promoted or retired.
    """
    typed = _typed_class_for(source)
    if typed is None:
        # A legacy unmarked warehouse: the untyped stream IS its own stream.
        conn = dbmod.connect(target)
        try:
            dbmod.migrate(conn)
            conn.commit()
        finally:
            conn.close()
        return
    typed(target).initialize()


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> int:
    columns = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
    if not columns:
        return 0
    names = ", ".join(f'"{c}"' for c in columns)
    marks = ", ".join("?" for _ in columns)
    rows = src.execute(f"SELECT {names} FROM {table}").fetchall()
    if rows:
        dst.executemany(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({marks})",
                        [tuple(r) for r in rows])
    return len(rows)


def build_successor(db_path: Path | str, out_path: Path | str, *,
                    policies: dict[str, retention.Policy],
                    cutoffs: dict[str, str], progress=None) -> CompactionResult:
    """Create a fresh database at out_path holding the retained rows.

    Reads db_path and nothing else; never writes to it. A failure here costs one
    temporary file and leaves the warehouse untouched.
    """
    source_path, target_path = Path(db_path), Path(out_path)
    # Siblings too, not just the file: a `-wal` left by an earlier database of
    # this name describes different content, and the schema about to be created
    # here would inherit it. Same reason `_discard` exists.
    _discard(target_path)

    def step(name: str, done: int = 0, total: int = 0) -> None:
        if progress is not None:
            progress({"step": name, "done": done, "total": total})

    step("preparing")
    _prepare_successor(source_path, target_path)

    src = dbmod.connect(source_path)
    dst = dbmod.connect(target_path)
    try:
        before = src.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
        protected = retention.protected_keys(src)

        step("copying catalogue")
        dst.execute("PRAGMA foreign_keys = OFF")   # parents and children arrive in bulk
        for table in _tables_to_copy(src, dst):
            _copy_table(src, dst, table)
        dst.commit()

        step("copying observations")
        sql, params = retention.carry_forward_ids_sql(policies, cutoffs)
        keep_ids = [r[0] for r in src.execute(sql, params)]
        copied = _copy_observations(src, dst, keep_ids)
        dst.execute("PRAGMA foreign_keys = ON")
        dst.commit()

        step("compacting")
        dst.execute("VACUUM")
        dst.commit()
    finally:
        src.close()
        dst.close()

    return CompactionResult(
        ok=True, observations_before=before, observations_after=copied,
        protected_count=len(protected),
        bytes_before=storage._size(source_path), bytes_after=storage._size(target_path),
        built_path=str(target_path),
        detail=f"Built a successor holding {copied:,} of {before:,} observations.")


def _copy_observations(src: sqlite3.Connection, dst: sqlite3.Connection,
                       keep_ids: list[int]) -> int:
    """Copy the kept observations in bounded batches.

    Batched because a single IN (...) of a million ids exceeds SQLite's variable
    limit, and because a compaction must not need the whole stream in memory.
    """
    if not keep_ids:
        return 0
    columns = [r[1] for r in src.execute("PRAGMA table_info(price_observation)")]
    names = ", ".join(f'"{c}"' for c in columns)
    marks = ", ".join("?" for _ in columns)
    copied = 0
    batch = 500
    for start in range(0, len(keep_ids), batch):
        chunk = keep_ids[start:start + batch]
        holes = ", ".join("?" for _ in chunk)
        rows = src.execute(
            f"SELECT {names} FROM price_observation WHERE price_observation_id IN ({holes})",
            chunk).fetchall()
        dst.executemany(
            f"INSERT INTO price_observation ({names}) VALUES ({marks})",
            [tuple(r) for r in rows])
        copied += len(rows)
    return copied


# ---- verifying ---------------------------------------------------------------

def _refused_by_the_product(source: Path, successor: Path) -> list[str]:
    """The successor must open through the door the application itself uses.

    Asked by OPENING it — `MarketLensDatabase(successor).connect()`, the same
    call the engine makes at startup — and not by re-listing what that call
    checks. A re-listed check is a second implementation of the gate, and it
    drifts from the first one silently: #53 walked past a verifier that compares
    schema version, trigger presence, every table's row count and the protected
    set, all of them real checks, not one of them "and can it be opened".

    It is the SOURCE that decides which door to try, never the successor. A
    successor built the wrong way still carries a copied
    `scrapex_meta.database_kind` of 'marketlens' (see `_typed_class_for`), so
    letting the successor nominate its own door lets it pass by answering for
    itself.

    Every failure is a refusal. The successor is not repaired to make it
    acceptable — a compaction that stamped its own output into shape would be
    hiding exactly the divergence this exists to report.
    """
    typed = _typed_class_for(source)
    if typed is None:
        return []          # a legacy unmarked warehouse has no typed door to try
    try:
        typed(successor).connect().close()
    except Exception as exc:            # noqa: BLE001 — any refusal is a problem
        return [f"the successor is not a {typed.kind} database this product can "
                f"open ({type(exc).__name__}: {exc})"]
    return []


def verify_successor(src_path: Path | str, dst_path: Path | str) -> list[str]:
    """Every reason the successor is unacceptable. An empty list is the gate.

    The protected set is re-derived from the SOURCE by the independent Python
    implementation — deliberately not the view the selection used — so the two
    definitions have to agree before anything is promoted.

    Called before the pointer moves and before the predecessor is sealed, so
    everything it refuses is still free to refuse: the successor is a temporary
    file under a name nothing resolves to, and discarding it costs the owner one
    build and no data.
    """
    problems: list[str] = _refused_by_the_product(Path(src_path), Path(dst_path))
    src = dbmod.connect(Path(src_path))
    dst = dbmod.connect(Path(dst_path))
    try:
        must_keep = retention.protected_keys_independently(src)
        landed = {(r[0], r[1], r[2]) for r in dst.execute(
            "SELECT offer_id, business_date, record_hash FROM price_observation")}
        missing = must_keep - landed
        if missing:
            problems.append(
                f"{len(missing)} protected observation(s) did not survive, "
                f"for example offer {next(iter(missing))[0]}")

        for check in ("integrity_check", "foreign_key_check"):
            findings = [r for r in dst.execute(f"PRAGMA {check}")]
            if check == "integrity_check":
                findings = [f for f in findings if f[0] != "ok"]
            if findings:
                problems.append(f"the successor fails PRAGMA {check}")

        if dbmod.schema_version(dst) != dbmod.schema_version(src):
            problems.append("the successor is on a different schema version")

        triggers = {r[0] for r in dst.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        for required in ("trg_price_obs_no_update", "trg_price_obs_no_delete"):
            if required not in triggers:
                problems.append(f"the successor is missing {required} — it would not "
                                "be append-only")

        # EVERY table except the observation stream must arrive whole. Checking
        # them all — rather than a chosen few — is what makes a table added by a
        # future migration impossible to drop unnoticed.
        for table in _tables_to_copy(src, dst):
            a = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            b = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if a != b:
                problems.append(f"{table} has {b} rows in the successor but {a} in the "
                                "original — every table except the observations "
                                "must be carried whole")

        dropped = _existing_tables(src) - _existing_tables(dst)
        if dropped:
            problems.append(f"the successor has no {', '.join(sorted(dropped))} table")
    finally:
        src.close()
        dst.close()
    return problems


# ---- previewing --------------------------------------------------------------

def preview(conn: sqlite3.Connection, db_path: Path | str, *, today: str,
            progress=None) -> CompactionResult:
    """Do the whole thing into a throwaway file, then delete it.

    The result is measured, not modelled: `bytes_after` is the real size of a
    real database containing exactly the rows a run would keep.
    """
    source = Path(db_path)
    policies = retention.effective_policies(conn)
    cutoffs = retention.cutoff_dates(conn, today)
    needed = int(storage._size(source) * storage.FREE_SPACE_MARGIN)
    if storage.free_space(source.parent) < needed:
        raise CompactionAborted(
            f"A preview builds a full trial copy, so it needs about {needed:,} bytes "
            f"free in {source.parent}. Free some space, or move the database first.")

    # A fixed trial name let two previews collide, each deleting the other's
    # file mid-build. A timestamp plus the process id is still not enough: the
    # stamp is second-resolution and the pid is identical for two previews in
    # the same process. A random suffix is the only part that cannot repeat.
    trial = source.with_name(
        f"{source.stem}.preview-{settings.file_stamp()}-{uuid.uuid4().hex[:8]}"
        f"{source.suffix or '.db'}")
    try:
        result = build_successor(source, trial, policies=policies, cutoffs=cutoffs,
                                 progress=progress)
        result.problems = verify_successor(source, trial)
        result.stale_pins = len(retention.stale_pins(conn))
        result.ok = not result.problems
        result.detail = _preview_sentence(result)
    finally:
        try:
            _discard(trial)
        except OSError:
            # A trial file we could not remove is untidy, not a failed preview.
            # Raising here would discard a measurement that was already correct.
            pass
    result.built_path = ""              # it is gone; do not offer a path to nothing
    return result


def _stale_pin_note(result: CompactionResult) -> str:
    """Never silent about a mark that points at nothing."""
    if not result.stale_pins:
        return ""
    return (f" {result.stale_pins} pinned observation(s) are no longer in this "
            "database, so those marks protect nothing. They are left exactly as "
            "they are — review them under Data and history.")


def _preview_sentence(result: CompactionResult) -> str:
    if result.problems:
        return ("This policy would not produce an acceptable database: "
                + "; ".join(result.problems))
    if result.observations_left_behind == 0:
        return ("Nothing would be left behind — every observation is either recent "
                "enough to keep or protected. There is no space to reclaim."
                + _stale_pin_note(result))
    return (f"{result.observations_left_behind:,} of {result.observations_before:,} "
            f"observations would stay in the sealed archive rather than move forward. "
            f"The new database measures {result.bytes_after:,} bytes against "
            f"{result.bytes_before:,} today. Nothing is freed until you delete the "
            "sealed archive yourself." + _stale_pin_note(result))


# ---- committing --------------------------------------------------------------

def compact_warehouse(conn: sqlite3.Connection, db_path: Path | str, *, today: str,
                      expected_digest: str, progress=None) -> CompactionResult:
    """Build, verify, and switch the pointer to the successor.

    The caller must hold the write lock for the whole call: a crawl that commits
    between the build and the switch would land in the file about to be sealed
    and be unreachable from the live one.
    """
    source = Path(db_path)
    policies = retention.effective_policies(conn)
    digest = retention.policy_digest(retention.get_policies(conn))
    if digest != expected_digest:
        raise CompactionAborted(
            "The retention policy changed since the preview you approved. Run the "
            "preview again so the numbers you confirm are the numbers you get.")

    needed = int(storage._size(source) * storage.FREE_SPACE_MARGIN)
    if storage.free_space(source.parent) < needed:
        raise CompactionAborted(
            f"A compaction builds a full second copy before switching, so it needs "
            f"about {needed:,} bytes free in {source.parent}. Free some space first — "
            "nothing has been changed.")

    cutoffs = retention.cutoff_dates(conn, today)
    stamp = settings.file_stamp()
    # Built under a name the fallback can never resolve to and the pointer never
    # names, then renamed once verified. A half-built file left by a crash is
    # therefore always distinguishable from a promoted successor.
    building = source.with_name(f"{source.stem}.building-{stamp}{source.suffix or '.db'}")
    built = source.with_name(f"{source.stem}.compact-{stamp}{source.suffix or '.db'}")

    try:
        result = build_successor(source, building, policies=policies, cutoffs=cutoffs,
                                 progress=progress)
        result.stale_pins = len(retention.stale_pins(conn))
        result.problems = verify_successor(source, building)
    except Exception:
        _discard(building)
        raise
    if result.problems:
        _discard(building)
        raise CompactionAborted(
            "The rebuilt database did not pass verification, so nothing was "
            "switched and your warehouse is untouched: " + "; ".join(result.problems))
    os.replace(building, built)
    result.built_path = str(built)

    storage.commit_live_database(built, previous=source)   # ---- the commit point ----

    # Sealing marks the predecessor from the INSIDE and then tries to rename it.
    # The mark is the load-bearing half: on Windows the caller's open handle
    # blocks the rename, which used to leave the superseded database sitting at
    # the default path — ready to be opened as live the moment the pointer was
    # lost, hiding everything gathered since.
    result.sealed_path, sealed_ok = storage._retire(source, "sealed", built)
    result.ok = True
    result.detail = (
        f"Now using a database with {result.observations_after:,} observations. "
        f"The previous file — all {result.observations_before:,} of them — is sealed "
        f"at {result.sealed_path}. ScrapeX will never delete it; removing it "
        f"yourself returns about {result.bytes_the_archive_would_free:,} bytes.")
    if not sealed_ok:
        # Never claim a mark that did not land: without it, a lost pointer could
        # open this archive as the live warehouse.
        result.detail += (" ScrapeX could not mark it as superseded, so do not "
                          "point ScrapeX back at it by hand.")
    result.detail += _stale_pin_note(result)
    if Path(result.sealed_path) == source:
        result.detail += (" It kept its original name because another program still "
                          "has it open, but it is marked inside as superseded, so it "
                          "can never be opened as the live warehouse by accident.")

    _record_run_in_successor(built, result)
    return result


def _discard(path: Path) -> None:
    """Remove a file this module built, and its write-ahead siblings.

    Leaving the -wal behind would let a later database of the same name inherit
    a journal that describes different content.
    """
    path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _record_run_in_successor(new_live: Path, result: CompactionResult) -> None:
    """Write the audit row into the database that is now live.

    Recording it in the source before the run would leave a row frozen at
    'running' inside the file being sealed, and the live warehouse would report
    a retention run that never finished — a false statement from the very
    audit trail meant to guarantee honesty.
    """
    conn = dbmod.connect(new_live)
    try:
        conn.execute(
            "INSERT INTO retention_run (mode, status, observations_before, "
            "observations_after, protected_count, bytes_before, bytes_after, "
            "sealed_path, detail) VALUES ('compact','succeeded',?,?,?,?,?,?,?)",
            (result.observations_before, result.observations_after,
             result.protected_count, result.bytes_before, result.bytes_after,
             result.sealed_path, result.detail))
        settings.set_state(conn, "retention_last", result.as_state())
        conn.commit()
    finally:
        conn.close()


def undo_compaction(sealed_path: Path | str) -> settings.RunResult:
    """Point back at a sealed archive.

    Possible precisely because nothing was deleted. The consequence is stated
    rather than buried: anything crawled since the compaction lives in the newer
    file and will not be in this one.
    """
    sealed = Path(sealed_path)
    if not sealed.exists():
        raise CompactionAborted(f"There is no sealed archive at {sealed}.")
    verdict = storage.health(sealed)
    if not verdict["ok"]:
        raise CompactionAborted(
            f"That archive does not pass a health check ({verdict['status']}), so "
            "ScrapeX will not switch to it.")
    # The registry follows only what it was already pointing at, so the file
    # being superseded has to be named: undoing a compaction moves the live
    # warehouse BACK, and until now it moved only half of the record.
    storage.commit_live_database(sealed, previous=storage.read_pointer())
    storage.unseal(sealed)              # it is the live warehouse again
    return settings.RunResult(
        ok=True, location=str(sealed),
        detail=(f"Now using {sealed.name} again. Anything crawled since the "
                "compaction is in the newer file and is not in this one."))
