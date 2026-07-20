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
from dataclasses import dataclass, field
from pathlib import Path

from . import db as dbmod
from . import retention, settings, storage

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
    target_path.unlink(missing_ok=True)

    def step(name: str, done: int = 0, total: int = 0) -> None:
        if progress is not None:
            progress({"step": name, "done": done, "total": total})

    src = dbmod.connect(source_path)
    dst = dbmod.connect(target_path)
    try:
        step("preparing")
        dbmod.migrate(dst)
        dst.commit()

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

def verify_successor(src_path: Path | str, dst_path: Path | str) -> list[str]:
    """Every reason the successor is unacceptable. An empty list is the gate.

    The protected set is re-derived from the SOURCE by the independent Python
    implementation — deliberately not the view the selection used — so the two
    definitions have to agree before anything is promoted.
    """
    problems: list[str] = []
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
    # file mid-build. The stamp plus the process id makes the name unique.
    trial = source.with_name(
        f"{source.stem}.preview-{settings.utc_now().replace(':', '')}-{os.getpid()}"
        f"{source.suffix or '.db'}")
    try:
        result = build_successor(source, trial, policies=policies, cutoffs=cutoffs,
                                 progress=progress)
        result.problems = verify_successor(source, trial)
        result.stale_pins = len(retention.stale_pins(conn))
        result.ok = not result.problems
        result.detail = _preview_sentence(result)
    finally:
        _discard(trial)
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
    stamp = settings.utc_now().replace(":", "").replace("-", "")
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

    storage.write_pointer(built)                 # ---- the commit point ----

    # Sealing marks the predecessor from the INSIDE and then tries to rename it.
    # The mark is the load-bearing half: on Windows the caller's open handle
    # blocks the rename, which used to leave the superseded database sitting at
    # the default path — ready to be opened as live the moment the pointer was
    # lost, hiding everything gathered since.
    result.sealed_path = storage._retire(source, "sealed", built)
    result.ok = True
    result.detail = (
        f"Now using a database with {result.observations_after:,} observations. "
        f"The previous file — all {result.observations_before:,} of them — is sealed "
        f"at {result.sealed_path}. ScrapeX will never delete it; removing it "
        f"yourself returns about {result.bytes_the_archive_would_free:,} bytes.")
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
    storage.write_pointer(sealed)
    storage.unseal(sealed)              # it is the live warehouse again
    return settings.RunResult(
        ok=True, location=str(sealed),
        detail=(f"Now using {sealed.name} again. Anything crawled since the "
                "compaction is in the newer file and is not in this one."))
