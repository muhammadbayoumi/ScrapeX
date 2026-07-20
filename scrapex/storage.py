"""Where the warehouse lives, and how it is kept healthy (spec section 17).

Two ideas carry this module.

**The pointer is the commit point.** The database's location is recorded in one
small JSON file. Moving the warehouse never renames the live file first: the copy
is made and verified while the original stays live, and the move commits by
atomically rewriting the pointer. Before that write the old path is authoritative;
after it the new one is. There is no instant where neither is.

**A missing database is an error, not an invitation.** `db.connect` creates what
it does not find, which is right for a first run and catastrophic for a fifth
year: a pointer aimed at an unplugged drive would silently mint an empty
warehouse and the next crawl would fork into it. `resolve_db_path` therefore
refuses when a *recorded* location has gone missing, and says which path and why.

Nothing here deletes a database. Backups, the moved-aside original and sealed
archives are all left on disk for the owner to remove themselves.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import db as dbmod
from . import settings
from .archive import backup_database
from .settings import RunResult

# The pointer lives next to the default database, never inside it: it must be
# readable when the database itself is unreachable.
POINTER_FILE = Path(
    os.environ.get("SCRAPEX_LOCATION_FILE", str(Path.home() / ".scrapex" / "location.json"))
)

# A move needs room for the copy plus headroom for the WAL and normal growth.
FREE_SPACE_MARGIN = 1.2

# Windows drive types (winbase.h). Used only to warn, never to refuse.
_DRIVE_REMOVABLE, _DRIVE_REMOTE = 2, 4

# A readable SQLite file is not necessarily a ScrapeX warehouse. These objects
# are the smallest durable identity shared by the original schema and every
# migration since: accepting a foreign SQLite file during restore would move the
# real warehouse aside and put unrelated data in its place.
_WAREHOUSE_TABLES = frozenset({
    "source_site", "source_product", "source_variant", "source_offer",
    "price_observation", "crawl_run", "raw_snapshot",
})
_WAREHOUSE_TRIGGERS = frozenset({
    "trg_price_obs_no_update", "trg_price_obs_no_delete",
})


class StorageUnavailableError(RuntimeError):
    """The recorded database location cannot be reached right now.

    Deliberately distinct from "no database yet": the caller must not treat this
    as a first run and create a new one.
    """


class StorageRefused(RuntimeError):
    """A pre-flight check refused the operation. Carries the owner-facing reason."""


# ---- where the database is ---------------------------------------------------

def read_pointer() -> Path | None:
    try:
        data = json.loads(POINTER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    recorded = str(data.get("db_path") or "").strip()
    return Path(recorded) if recorded else None


def write_pointer(db_path: Path | str) -> None:
    """Point at a database. Written atomically — a torn pointer is a lost warehouse."""
    POINTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = POINTER_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"db_path": str(Path(db_path)), "at": settings.utc_now()},
                              indent=2), encoding="utf-8")
    os.replace(tmp, POINTER_FILE)


def clear_pointer() -> None:
    POINTER_FILE.unlink(missing_ok=True)


def current_location() -> Path:
    """The database path in force: pointer, then SCRAPEX_DB_PATH, then default."""
    return read_pointer() or dbmod.DEFAULT_DB_PATH


# ---- sealing: a superseded database says so from the inside ------------------

SEALED_KEY = "sealed_at"
SEALED_REASON_KEY = "sealed_reason"


def mark_sealed(db_path: Path | str, reason: str, successor: Path | str = "") -> bool:
    """Record inside a database that it has been superseded.

    Renaming the predecessor is not enough, and on Windows usually does not even
    happen: an open handle blocks the rename, so a compacted-away database keeps
    the name `harvest.db` — which is the DEFAULT path. Lose the pointer and the
    fallback would then open the pre-compaction archive as live, and the next
    crawl would append into it. The mark travels inside the file, so the guard
    works no matter what the file ends up being called.
    """
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return False
    try:
        with conn:
            conn.execute(
                "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (SEALED_KEY, settings.utc_now()))
            conn.execute(
                "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (SEALED_REASON_KEY, f"{reason} -> {successor}" if successor else reason))
        return True
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


def unseal(db_path: Path | str) -> None:
    """Make a sealed database live again (the undo path)."""
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return
    try:
        with conn:
            conn.execute("DELETE FROM scrapex_meta WHERE key IN (?,?)",
                         (SEALED_KEY, SEALED_REASON_KEY))
    except sqlite3.DatabaseError:
        pass
    finally:
        conn.close()


def sealed_at(db_path: Path | str) -> str:
    if not Path(db_path).exists():
        return ""
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return ""
    try:
        row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                           (SEALED_KEY,)).fetchone()
        return row[0] if row else ""
    except sqlite3.DatabaseError:
        return ""
    finally:
        conn.close()


def resolve_db_path() -> Path:
    """The path to open, refusing to invent or resurrect the wrong warehouse.

    Two distinct hazards, two guards:
    - A RECORDED location that vanished is an error, not a first run.
    - The fallback path may hold a database that a move or compaction superseded.
      Opening it silently would hide every observation gathered since, and the
      next crawl would fork into the archive.

    A default path that simply does not exist yet is a normal first run.
    """
    pointed = read_pointer()
    if pointed is not None:
        if pointed.exists():
            return pointed
        raise StorageUnavailableError(
            f"The database recorded at {pointed} is not there. If it is on a drive "
            "that is unplugged, reconnect it; ScrapeX will not start an empty "
            "warehouse in its place."
        )
    fallback = dbmod.DEFAULT_DB_PATH
    when = sealed_at(fallback)
    if when:
        raise StorageUnavailableError(
            f"The database at {fallback} was superseded on {when} and is kept only "
            "as an archive. ScrapeX will not open it as the live warehouse, because "
            "everything gathered since would be invisible and the next crawl would "
            "write into the archive. Point ScrapeX at the current database, or "
            "restore this one deliberately from Settings - Storage."
        )
    if not fallback.exists():
        # Nothing at the default path, but a sealed sibling means this machine
        # HAS a warehouse — it moved. Starting an empty one here would leave the
        # real history sitting somewhere the owner is never told about.
        moved_to = _successor_recorded_nearby(fallback)
        if moved_to:
            raise StorageUnavailableError(
                f"There is no database at {fallback}, but this machine's warehouse "
                f"was moved to {moved_to}. ScrapeX will not start an empty one in "
                "its place. Reconnect that location, or point ScrapeX at it."
            )
    return fallback


def _successor_recorded_nearby(fallback: Path) -> str:
    """Where a retired sibling says the warehouse went, if one is there."""
    folder = fallback.parent
    if not folder.is_dir():
        return ""
    for candidate in sorted(folder.glob(f"{base_stem(fallback)}.*-*{fallback.suffix}"),
                            reverse=True):
        if not sealed_at(candidate):
            continue
        try:
            conn = sqlite3.connect(str(candidate))
        except sqlite3.DatabaseError:
            continue
        try:
            row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                               (SEALED_REASON_KEY,)).fetchone()
        except sqlite3.DatabaseError:
            row = None
        finally:
            conn.close()
        if row and " -> " in row[0]:
            return row[0].split(" -> ", 1)[1]
    return ""


# ---- measuring and checking --------------------------------------------------

def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def measure(db_path: Path | str) -> dict:
    """Sizes that add up to what the warehouse really occupies."""
    path = Path(db_path)
    wal, shm = path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")
    backups = list_backups(path)
    return {
        "db_bytes": _size(path),
        "wal_bytes": _size(wal),
        "shm_bytes": _size(shm),
        "backup_bytes": sum(b["bytes"] for b in backups),
        "backup_count": len(backups),
        "free_bytes": free_space(path.parent),
        "total_bytes": _size(path) + _size(wal) + _size(shm),
    }


def free_space(folder: Path | str) -> int:
    try:
        return shutil.disk_usage(str(folder)).free
    except OSError:
        return 0


def _same_volume(left: Path | str, right: Path | str) -> bool:
    """Do these two folders share a disk?

    The anchor ('C:\\', '/') is the honest answer on Windows. On POSIX every
    path shares '/', so st_dev decides — a mounted external disk has its own.
    """
    left_path, right_path = Path(left), Path(right)
    if os.name == "nt":
        return left_path.anchor.upper() == right_path.anchor.upper()
    try:
        return left_path.stat().st_dev == right_path.stat().st_dev
    except OSError:
        return left_path.anchor == right_path.anchor


def drive_kind(folder: Path | str) -> str:
    """'removable', 'network', 'fixed' or 'unknown'.

    Used to WARN, never to refuse: an external drive is a legitimate place to
    keep a warehouse, as long as the owner is told what happens if it vanishes.
    """
    if os.name != "nt":
        return "unknown"
    try:
        import ctypes

        root = str(Path(folder).resolve().anchor)
        kind = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
    except Exception:                      # a warning is never worth a crash
        return "unknown"
    return {_DRIVE_REMOVABLE: "removable", _DRIVE_REMOTE: "network"}.get(kind, "fixed")


def _warehouse_identity(conn: sqlite3.Connection) -> tuple[str, str] | None:
    """Return ``(status, reason)`` when this is not a compatible warehouse.

    Integrity and identity are deliberately separate checks. ``quick_check``
    answers whether SQLite can read the file; this answers whether ScrapeX may
    safely interpret and restore it.
    """
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version <= 0:
        return (
            "not_scrapex",
            "The file is SQLite, but it is not a ScrapeX warehouse; it has no "
            "ScrapeX schema version.",
        )
    latest = dbmod.latest_schema_version()
    if version > latest:
        return (
            "incompatible",
            f"The file uses ScrapeX schema v{version}, but this engine only "
            f"understands through v{latest}. Update ScrapeX before restoring it.",
        )

    objects = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','trigger')"
        )
    }
    missing_tables = sorted(name for name in _WAREHOUSE_TABLES
                            if objects.get(name) != "table")
    missing_triggers = sorted(name for name in _WAREHOUSE_TRIGGERS
                              if objects.get(name) != "trigger")
    if missing_tables or missing_triggers:
        missing = missing_tables + missing_triggers
        return (
            "not_scrapex",
            "The file is SQLite, but it is not a ScrapeX warehouse; required "
            f"objects are missing: {', '.join(missing)}.",
        )

    # Migration 0002 introduced the contract marker. A v1 warehouse is a valid
    # legacy ScrapeX database and can be migrated after restore; v2+ without the
    # marker is either foreign or incomplete and must be refused.
    if version >= 2:
        if objects.get("scrapex_meta") != "table":
            return "not_scrapex", "The ScrapeX contract marker table is missing."
        row = conn.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'contract_version'"
        ).fetchone()
        if row is None:
            return "not_scrapex", "The ScrapeX contract version marker is missing."
        from .contract import CONTRACT_VERSION
        try:
            stored_contract = int(row[0])
        except (TypeError, ValueError):
            return "not_scrapex", "The ScrapeX contract version marker is invalid."
        if stored_contract != CONTRACT_VERSION:
            return (
                "incompatible",
                f"The warehouse uses contract v{stored_contract}, but this engine "
                f"uses v{CONTRACT_VERSION}. Use a compatible engine or migrate it.",
            )
    return None


def health(db_path: Path | str) -> dict:
    """SQLite's own verdict, reported as a word plus the raw findings.

    `quick_check` rather than `integrity_check`: it catches the corruption that
    matters at a fraction of the cost, which means the Storage page can run it
    on every visit instead of hiding it behind a button nobody presses.
    """
    path = Path(db_path)
    if not path.exists():
        return {"status": "missing", "ok": False,
                "detail": "There is no database at this location yet.",
                "problems": [], "foreign_key_problems": 0}
    if _size(path) == 0:
        # SQLite opens a zero-byte file as a valid EMPTY database and every
        # check passes, so "healthy" was technically true and completely
        # misleading. It is reported as not_scrapex rather than as its own
        # status, because the remedy is the same one: this is not a warehouse.
        return {"status": "not_scrapex", "ok": False,
                "detail": "The file is empty and is not a ScrapeX warehouse.",
                "problems": ["empty file"], "foreign_key_problems": 0,
                "reclaimable_bytes": 0}
    conn = sqlite3.connect(str(path))
    try:
        problems = [r[0] for r in conn.execute("PRAGMA quick_check")]
        problems = [p for p in problems if p != "ok"]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        identity_problem = _warehouse_identity(conn)
    except sqlite3.DatabaseError as exc:
        return {"status": "unreadable", "ok": False,
                "detail": f"SQLite could not read this file: {exc}",
                "problems": [str(exc)], "foreign_key_problems": 0}
    finally:
        conn.close()

    reclaimable = freelist * page_size
    if problems or fk:
        return {"status": "damaged", "ok": False, "problems": problems,
                "foreign_key_problems": len(fk),
                "detail": "SQLite reported problems. Back up first, then run Repair."}
    if identity_problem is not None:
        status, detail = identity_problem
        return {"status": status, "ok": False, "problems": [detail],
                "foreign_key_problems": 0, "reclaimable_bytes": reclaimable,
                "detail": detail}
    return {
        "status": "healthy", "ok": True, "problems": [], "foreign_key_problems": 0,
        "reclaimable_bytes": reclaimable,
        "detail": ("No problems found." + (
            f" Compacting would return about {reclaimable:,} bytes of free pages."
            if reclaimable else "")),
    }


# ---- backups -----------------------------------------------------------------

def backup_folder(conn: sqlite3.Connection, db_path: Path | str) -> Path:
    saved = settings.get(conn, "backup_folder")
    return Path(saved).expanduser() if saved else Path(db_path).parent


# Suffixes this product appends when it supersedes a database. Stripping them
# recovers the ORIGINAL warehouse name, which is what backups are named after.
# Tolerant of both stamp forms: files written before file_stamp() existed carry
# dashes, and they must keep resolving to the same warehouse name.
_LINEAGE_SUFFIX = re.compile(
    r"\.(compact|building|preview|sealed|moved|replaced)-[\d-]{8,10}T[\d:]{6,8}Z(-\d+)?$")


def base_stem(db_path: Path | str) -> str:
    """The warehouse's original name, whatever the live file is called now.

    After a compaction the live file is `harvest.compact-<stamp>.db`. Globbing on
    THAT stem found nothing, so every backup the owner had silently vanished from
    the Storage page and from Restore — at exactly the moment they most needed
    one.
    """
    # Repeated, not single: a second compaction produces
    # harvest.compact-A.compact-B, and stripping one suffix would still miss
    # every backup taken before the first one.
    stem, previous = Path(db_path).stem, None
    while stem != previous:
        stem, previous = _LINEAGE_SUFFIX.sub("", stem), stem
    return stem


def list_backups(db_path: Path | str, folder: Path | None = None) -> list[dict]:
    """Backups produced by this product, newest first."""
    path = Path(db_path)
    where = Path(folder) if folder else path.parent
    if not where.is_dir():
        return []
    found = [{"path": str(p), "name": p.name, "bytes": _size(p),
              "modified_at": _mtime_iso(p)}
             for p in where.glob(f"{base_stem(path)}.*backup*")]
    return sorted(found, key=lambda b: b["modified_at"], reverse=True)


def _mtime_iso(path: Path) -> str:
    from datetime import datetime, timezone

    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return ""
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_now(conn: sqlite3.Connection, db_path: Path | str, tag: str = "manual") -> RunResult:
    """A consistent copy, taken through SQLite's online backup API."""
    path = Path(db_path)
    if not path.exists():
        raise StorageRefused("There is no database to back up yet.")
    destination = backup_folder(conn, path)
    destination.mkdir(parents=True, exist_ok=True)
    if free_space(destination) < _size(path) * FREE_SPACE_MARGIN:
        raise StorageRefused(
            f"Not enough free space in {destination} for a backup of "
            f"{_size(path):,} bytes. Free some space or choose another folder.")

    made = backup_database(path, tag=tag)
    if destination != path.parent:
        moved = destination / made.name
        os.replace(made, moved)
        made = moved
    result = RunResult(ok=True, rows=0, location=str(made),
                       detail=f"Backed up {_size(made):,} bytes to {made}.")
    if _same_volume(destination, path.parent):
        # Saying "backed up" while both copies share one failing disk is the
        # kind of half-truth that is only discovered when it is too late.
        result.detail += (" This backup is on the same disk as the database, so it "
                          "does not survive that drive failing. Set a backup folder "
                          "on another disk to protect against that.")
    settings.set_state(conn, "storage_last", result.as_state())
    return result


def restore(db_path: Path | str, backup_path: Path | str) -> RunResult:
    """Make a backup live again WITHOUT overwriting the current database.

    The current file is moved aside under a name that says what it is; only then
    does the backup take its place. Nothing is destroyed, so a restore chosen by
    mistake is undone by moving one file back.
    """
    path, source = Path(db_path), Path(backup_path)
    if not source.exists():
        raise StorageRefused(f"That backup is no longer at {source}.")
    try:
        if source.resolve() == path.resolve():
            raise StorageRefused("The selected backup is already the live database.")
    except OSError:
        pass
    # health() now answers BOTH questions — can SQLite read this file, and may
    # ScrapeX interpret it — so one refusal covers a corrupt backup, a foreign
    # database, and one written by a newer engine.
    verdict = health(source)
    if not verdict["ok"]:
        raise StorageRefused(
            f"That backup does not pass a health check ({verdict['status']}): "
            f"{verdict['detail']} ScrapeX will not put it in place.")
    if free_space(path.parent) < _size(source) * FREE_SPACE_MARGIN:
        raise StorageRefused(f"Not enough free space in {path.parent} to restore.")

    # Copy and validate while the current warehouse remains authoritative. Only
    # a fully copied, re-checked file is allowed to reach the switch below.
    incoming = path.with_name(path.name + ".restore-incoming")
    incoming.unlink(missing_ok=True)
    try:
        shutil.copy2(source, incoming)
    except OSError:
        incoming.unlink(missing_ok=True)
        raise
    copied_verdict = health(incoming)
    if not copied_verdict["ok"] or not _same_contents(source, incoming):
        incoming.unlink(missing_ok=True)
        raise StorageRefused(
            "The copied backup did not pass verification, so the live database "
            "was not changed. Try an older backup or another storage device."
        )

    displaced = ""
    try:
        if path.exists():
            displaced = str(path.with_name(
                f"{path.stem}.replaced-{settings.file_stamp()}{path.suffix}"))
            # On Windows this fails outright if ANY connection still holds the
            # live database — the job worker keeps one open for its whole life.
            # Unguarded, it escaped as a bare 500 and stranded a full-size copy
            # of the warehouse at .restore-incoming that nothing ever counted.
            os.replace(path, displaced)
        os.replace(incoming, path)
    except OSError as exc:
        if displaced and not path.exists():   # put the original back
            os.replace(displaced, path)
        incoming.unlink(missing_ok=True)
        raise StorageRefused(
            f"The database could not be replaced ({exc}). Another part of ScrapeX "
            "still has it open — stop any running crawl and try again. Nothing "
            "was changed.") from exc
    # The WAL of the replaced database describes a file that is no longer there.
    for suffix in ("-wal", "-shm"):
        try:
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        except OSError:
            # Cosmetic, and AFTER the commit point: the restore succeeded and
            # must not be reported as a failure because a stale journal lingered.
            pass
    detail = f"Restored from {source.name}."
    if displaced:
        detail += (f" The database that was here is still on disk as "
                   f"{Path(displaced).name} — delete it yourself once you have "
                   "confirmed the restore.")
    return RunResult(ok=True, location=str(path), detail=detail)


# ---- maintenance -------------------------------------------------------------

def repair(db_path: Path | str) -> RunResult:
    """Rebuild indexes and refresh planner statistics.

    Repair here never rewrites rows. If SQLite reports structural damage the
    honest answer is a restore from backup, and this says so rather than
    pretending an index rebuild fixed a corrupt page.
    """
    path = Path(db_path)
    verdict = health(path)
    if verdict["status"] in {"missing", "unreadable", "not_scrapex", "incompatible"}:
        raise StorageRefused(
            f"Refusing to repair {path.name}: {verdict['detail']}"
        )
    conn = dbmod.connect(path)
    try:
        conn.execute("REINDEX")
        conn.execute("PRAGMA optimize")
        conn.commit()
    finally:
        conn.close()
    if verdict["ok"]:
        return RunResult(ok=True, location=str(path),
                         detail="Indexes rebuilt and statistics refreshed. "
                                "The database was already healthy.")
    return RunResult(
        ok=False, location=str(path),
        detail="Indexes were rebuilt, but SQLite still reports damage: "
               f"{'; '.join(verdict['problems'][:3])}. Restore from a backup — "
               "an index rebuild cannot recover damaged pages.")


def compact(conn: sqlite3.Connection, db_path: Path | str) -> RunResult:
    """VACUUM: reclaim free pages in place.

    Safe and non-destructive — SQLite rewrites the file with the same rows. It
    needs room for a second copy while it runs, so the space is checked first.
    """
    path = Path(db_path)
    # Measure AFTER a checkpoint. This product runs in WAL mode, where recent
    # writes sit in the -wal file: reading the main file first reports a size
    # that has not caught up yet, so a real reduction could be reported as
    # growth — or a no-op as a saving.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = _size(path)
    if free_space(path.parent) < before * FREE_SPACE_MARGIN:
        raise StorageRefused(
            f"Compacting rewrites the database, so it needs about {before:,} bytes "
            f"free in {path.parent} while it runs. Free some space first.")
    conn.execute("VACUUM")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = _size(path)
    result = RunResult(
        ok=True, location=str(path),
        detail=(f"Compacted: {before:,} -> {after:,} bytes "
                f"({max(0, before - after):,} returned to the disk)."
                if after < before else
                f"Compacted. The file was already tightly packed ({after:,} bytes)."))
    settings.set_state(conn, "storage_last", result.as_state())
    return result


def export_database(conn: sqlite3.Connection, db_path: Path | str,
                    dest_dir: Path | str) -> RunResult:
    """A consistent copy in a folder of the owner's choosing."""
    path, destination = Path(db_path), Path(dest_dir).expanduser()
    if not path.exists():
        raise StorageRefused("There is no database to export yet.")
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageRefused(f"ScrapeX cannot create {destination}: {exc}")
    if free_space(destination) < _size(path) * FREE_SPACE_MARGIN:
        raise StorageRefused(f"Not enough free space in {destination}.")

    made = backup_database(path, tag="export")
    target = destination / made.name
    os.replace(made, target)
    return RunResult(ok=True, location=str(target),
                     detail=f"Exported {_size(target):,} bytes to {target}.")


# ---- moving the warehouse ----------------------------------------------------

@dataclass
class MoveCheck:
    ok: bool
    reason: str = ""
    warning: str = ""
    resumable: bool = False          # a verified copy from an interrupted move


def _is_stranded_copy(source: Path, candidate: Path) -> bool:
    """Is this the copy an interrupted move already made, rather than someone
    else's database? Judged on content, never on the filename.

    `health` covers warehouse identity as well as readability, so a foreign
    database sitting at the destination can never be mistaken for our own.
    """
    return health(candidate)["ok"] and _same_contents(source, candidate)


def check_move(db_path: Path | str, new_dir: Path | str) -> MoveCheck:
    """Everything that can refuse a move, decided before anything is written."""
    path, target = Path(db_path), Path(new_dir).expanduser()
    destination = target / path.name

    if target == path.parent:
        return MoveCheck(False, "The database is already in that folder.")
    try:
        if path.parent.resolve() in target.resolve().parents or \
           target.resolve() in path.parent.resolve().parents:
            return MoveCheck(False, "Choose a folder that is not inside the current "
                                    "database folder, and does not contain it.")
    except OSError:
        pass

    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".scrapex-write-probe"
        probe.write_bytes(b"scrapex")
        if probe.read_bytes() != b"scrapex":
            raise OSError("readback mismatch")
        probe.unlink()
    except OSError as exc:
        return MoveCheck(False, f"ScrapeX cannot write to {target} ({exc}). Choose a "
                                "folder you own, or fix its permissions.")

    if destination.exists():
        # A previous move that died between the file landing and the pointer
        # write leaves a complete, verified copy here. Refusing outright would
        # permanently block the retry and leave the owner staring at a folder
        # they were told not to touch — so offer to finish instead.
        if _is_stranded_copy(path, destination):
            return MoveCheck(True, resumable=True,
                             warning="A complete copy from an interrupted move is "
                                     f"already at {destination}. Moving again will "
                                     "finish that switch rather than copy it twice.")
        return MoveCheck(False, f"A database already exists at {destination}. ScrapeX "
                                "will not overwrite it. Move or rename it first, or "
                                "pick another folder.")

    needed = int(_size(path) * FREE_SPACE_MARGIN)
    available = free_space(target)
    if available < needed:
        return MoveCheck(False, f"{target} has {available:,} bytes free but the move "
                                f"needs about {needed:,}.")

    verdict = health(path)
    if not verdict["ok"] and verdict["status"] != "missing":
        return MoveCheck(False, "The database does not pass a health check "
                                f"({verdict['status']}). Run Repair or restore a "
                                "backup before moving it.")

    kind = drive_kind(target)
    warning = ""
    if kind in {"removable", "network"}:
        warning = (f"{target} looks like a {kind} drive. If it is disconnected while "
                   "ScrapeX is running, the database becomes unreadable and a crawl "
                   "in progress will fail.")
    return MoveCheck(True, warning=warning)


def migrate_location(db_path: Path | str, new_dir: Path | str, *,
                     progress=None) -> RunResult:
    """Move the warehouse, committing on the pointer write and never before.

    Ordering: copy, verify, commit, tidy. Steps before the commit are undone by
    deleting a file this function created; the commit is a single atomic write;
    the step after it is cosmetic. The original is renamed aside, never deleted.
    """
    path, target = Path(db_path), Path(new_dir).expanduser()
    check = check_move(path, target)
    if not check.ok:
        raise StorageRefused(check.reason)
    destination = target / path.name
    incoming = target / (path.name + ".incoming")

    def step(name: str, done: int = 0, total: int = 0) -> None:
        if progress is not None:
            progress({"step": name, "done": done, "total": total})

    if check.resumable:
        # The copy already exists and already matched. Finishing is just the
        # commit, and repeating the copy would only risk a fresh failure.
        step("switching")
        write_pointer(destination)
        _retire(path, "moved", destination)
        return RunResult(ok=True, location=str(destination),
                         detail=f"Finished an interrupted move to {destination}. The "
                                "copy that was already there is now the live database.")

    step("backing up")
    rollback_copy = backup_database(path, tag="move")

    step("copying")
    incoming.unlink(missing_ok=True)
    source_conn = sqlite3.connect(str(path))
    try:
        target_conn = sqlite3.connect(str(incoming))
        try:
            def on_progress(status, remaining, total):
                step("copying", done=total - remaining, total=total)

            with target_conn:
                source_conn.backup(target_conn, pages=2048, progress=on_progress)
        finally:
            target_conn.close()
    except Exception:
        incoming.unlink(missing_ok=True)   # ours, never live, safe to remove
        raise
    finally:
        source_conn.close()

    step("verifying")
    verdict = health(incoming)
    if not verdict["ok"] or not _same_contents(path, incoming):
        incoming.unlink(missing_ok=True)
        raise StorageRefused(
            "The copy did not match the original, so nothing was moved. The "
            f"database is still at {path}. A rollback copy is at {rollback_copy}.")

    os.replace(incoming, destination)      # atomic within the volume
    step("switching")
    write_pointer(destination)             # ---- the commit point ----

    step("tidying")
    left_behind = _retire(path, "moved", destination)
    return RunResult(
        ok=True, location=str(destination),
        detail=(f"Moved to {destination}. The old database is still on disk as "
                f"{Path(left_behind).name} and is marked inside as superseded, so "
                "it can never be opened as the live warehouse by accident. Delete "
                "it yourself once you have confirmed everything works."))


def _retire(path: Path, reason: str, successor: Path) -> str:
    """Mark a superseded database, then TRY to rename it. Returns where it is.

    The mark is what matters and always happens; the rename is cosmetic and
    fails routinely on Windows, where the caller's own open handle blocks it.
    Relying on the rename alone left a superseded database sitting at the
    default path, ready to be opened as live if the pointer were ever lost.
    """
    mark_sealed(path, reason, successor)
    retired = path.with_name(
        f"{path.stem}.{reason}-{settings.file_stamp()}{path.suffix}")
    try:
        os.replace(path, retired)
        for suffix in ("-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        return str(retired)
    except OSError:
        return str(path)


def _same_contents(src: Path, dst: Path) -> bool:
    """Every user table and row count agrees, including future generic data.

    A fixed table allowlist silently stopped protecting data as soon as a new
    migration added a first-class dataset. Schema names come from SQLite itself;
    values remain parameterized and identifiers are quoted before use.
    """
    try:
        a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    except sqlite3.DatabaseError:
        return False
    try:
        table_sql = (
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables_a = [row[0] for row in a.execute(table_sql)]
        tables_b = [row[0] for row in b.execute(table_sql)]
        if tables_a != tables_b:
            return False
        for table in tables_a:
            quoted = table.replace('"', '""')
            count_sql = f'SELECT COUNT(*) FROM "{quoted}"'
            if a.execute(count_sql).fetchone()[0] != b.execute(count_sql).fetchone()[0]:
                return False
        return a.execute("PRAGMA user_version").fetchone()[0] == \
            b.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.DatabaseError:
        return False
    finally:
        a.close()
        b.close()


# ---- the status the interface renders ----------------------------------------

def storage_status(conn: sqlite3.Connection, db_path: Path | str) -> dict:
    path = Path(db_path)
    sizes = measure(path)
    verdict = health(path)
    return {
        "key": "local_storage",
        "label": "Local storage",
        "ready": verdict["ok"],
        "blocker": "" if verdict["ok"] else verdict["detail"],
        "path": str(path),
        "folder": str(path.parent),
        "pointer": str(read_pointer()) if read_pointer() else "",
        "drive_kind": drive_kind(path.parent),
        "sizes": sizes,
        "health": verdict,
        "backups": list_backups(path, backup_folder(conn, path)),
        "backup_folder": str(backup_folder(conn, path)),
        "last": settings.get_state(conn, "storage_last"),
        "migration": settings.get_state(conn, "storage_migration"),
    }
