"""Full-rebuild archiving (spec section 13).

"Rebuild" can never mean deletion here: price_observation is append-only and the
schema triggers enforce it. So a rebuild ARCHIVES instead — it marks the source's
current catalogue as vanished and then crawls fresh, so everything still on the
site is re-activated (a 'returned' event) and everything genuinely gone stays
visibly gone. Nothing is destroyed, and the file backup is the rollback path.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .payload import utc_now_iso


def backup_database(db_path: Path | str, tag: str = "rebuild") -> Path:
    """Consistent point-in-time copy of harvest.db, using SQLite's online backup
    (never a raw file copy — WAL means a copy mid-write can be torn)."""
    src = Path(db_path)
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    dst = src.with_name(f"{src.stem}.{tag}-{stamp}.backup{src.suffix or '.db'}")
    source = sqlite3.connect(str(src))
    try:
        target = sqlite3.connect(str(dst))
        try:
            with target:
                source.backup(target)
        finally:
            target.close()
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
