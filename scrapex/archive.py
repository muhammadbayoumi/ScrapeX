"""Full-rebuild archiving (spec section 13).

"Rebuild" can never mean deletion here: price_observation is append-only and the
schema triggers enforce it. So a rebuild ARCHIVES instead — it marks the source's
current catalogue as vanished and then crawls fresh, so everything still on the
site is re-activated (a 'returned' event) and everything genuinely gone stays
visibly gone. Nothing is destroyed, and the file backup is the rollback path.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .payload import utc_now_iso


def backup_database(db_path: Path | str, tag: str = "rebuild") -> Path:
    """Consistent point-in-time copy of harvest.db, using SQLite's online backup
    (never a raw file copy — WAL means a copy mid-write can be torn)."""
    src = Path(db_path)
    # A BACKUP OF NOTHING IS NOT A BACKUP. sqlite3.connect CREATES the file it
    # is handed, so backing up a path that does not exist produced an empty
    # database and reported success. Every caller here uses the result to decide
    # it is safe to proceed — the engine's own upgrade will not migrate without
    # one — and a guard that cannot fail is not a guard. Found by a test that
    # expected the missing-file case to refuse and watched it migrate.
    if not src.is_file():
        raise FileNotFoundError(f"there is no database at {src} to back up")
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    dst = src.with_name(f"{src.stem}.{tag}-{stamp}.backup{src.suffix or '.db'}")
    # A TORN COPY MUST NEVER CARRY THE FINAL NAME, and this became load-bearing the
    # day the retention policy gained a caller on the upgrade path (`OP-136`).
    # `source.backup(target)` fills the destination page by page, so a process killed
    # mid-copy — or a disk that fills — left a PARTIAL database named exactly like a
    # good one, with the newest stamp of its lineage. `storage.prunable_backups` keeps
    # the newest N per lineage, so that file could be kept while a complete older copy
    # was deleted: the one state where a backup is needed is the one where it had been
    # replaced by a fragment of itself.
    #
    # The partial name is invisible to the policy on purpose: `storage.list_backups`
    # accepts only `.db`, and `.part` is neither offered for restore nor pruned. So an
    # interrupted copy leaves litter that cannot be mistaken for a backup, which is the
    # right way round. `bundle.py` writes through a partial name for the same reason.
    partial = dst.with_name(dst.name + ".part")
    partial.unlink(missing_ok=True)
    source = sqlite3.connect(str(src))
    try:
        target = sqlite3.connect(str(partial))
        try:
            with target:
                source.backup(target)
        finally:
            target.close()
        # OPENABLE BEFORE IT IS ALLOWED TO HAVE THE REAL NAME. Cheap on purpose --
        # reading `sqlite_master` proves the header and the schema arrived, and
        # `quick_check` is O(file size) on a warehouse that measured 0.879 s at
        # 1,067 MB. The expensive check belongs to Storage, which offers it.
        check = sqlite3.connect(str(partial))
        try:
            check.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        finally:
            check.close()
        os.replace(partial, dst)
    except BaseException:
        # Including KeyboardInterrupt: a Ctrl-C during a backup is exactly the
        # interruption this exists for, and it is not an `Exception`.
        partial.unlink(missing_ok=True)
        raise
    finally:
        source.close()
    return dst


def archive_source(conn: sqlite3.Connection, source_key: str) -> int:
    """Mark this source's active products vanished ahead of a rebuild.

    Returns how many were archived. Observations, matches and curation decisions
    are all left untouched — the rebuild re-activates whatever it finds again.
    """
    cur = conn.execute(
        "UPDATE source_product SET status = 'vanished' WHERE status = 'active' AND source_id = ("
        "  SELECT source_id FROM source_site WHERE source_key = ?)",
        (source_key,),
    )
    return cur.rowcount
