"""Snapshot the live warehouse into `.work/snapshot.db`, and record its shape.

Spike 2's first requirement is that the experiment runs against THE warehouse,
not a toy. This makes the only copy the rest of the spike is allowed to touch.

Two rules this file exists to enforce:

* The live database is opened **read-only** (`?mode=ro`) and never written. The
  engine may be mid-crawl while this runs; a spike that could corrupt the
  owner's price history would cost more than the question is worth.
* The copy is made with `sqlite3.Connection.backup()`, not `shutil.copy`. A
  file copy of a WAL database is a torn read — it takes the main file without
  the ~15 MB of committed frames sitting in `-wal`, and the result is a
  *smaller, older* database that would flatter every number downstream.
  `backup()` reads through the WAL and produces a page-for-page snapshot.

Run:  python prepare.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / ".work"
SNAPSHOT = WORK / "snapshot.db"
# The same warehouse with WAL turned off. Not a convenience: no OPFS VFS
# implements SQLite's shared-memory hook (`xShmMap`), so a WAL-mode file cannot
# be opened in a browser at all. The browser has to be handed this one, and the
# difference between the two files is a finding, not a detail.
SNAPSHOT_NOWAL = WORK / "snapshot-nowal.db"

LIVE = Path(
    os.environ.get("SCRAPEX_SPIKE_LIVE_DB", str(Path.home() / ".scrapex" / "marketlens" / "marketlens.db"))
)


def _ro_uri(path: Path) -> str:
    return "file:" + str(path).replace("\\", "/") + "?mode=ro"


def main() -> int:
    if not LIVE.exists():
        print(f"live warehouse not found: {LIVE}", file=sys.stderr)
        return 2

    WORK.mkdir(parents=True, exist_ok=True)
    for stale in (SNAPSHOT, Path(str(SNAPSHOT) + "-wal"), Path(str(SNAPSHOT) + "-shm")):
        if stale.exists():
            stale.unlink()

    live_sizes = {
        "main_bytes": LIVE.stat().st_size,
        "wal_bytes": Path(str(LIVE) + "-wal").stat().st_size if Path(str(LIVE) + "-wal").exists() else 0,
        "shm_bytes": Path(str(LIVE) + "-shm").stat().st_size if Path(str(LIVE) + "-shm").exists() else 0,
    }

    src = sqlite3.connect(_ro_uri(LIVE), uri=True, timeout=30)
    dst = sqlite3.connect(str(SNAPSHOT))
    t0 = time.perf_counter()
    src.backup(dst)
    copy_s = time.perf_counter() - t0
    dst.commit()

    cur = dst.cursor()
    page_size = cur.execute("PRAGMA page_size").fetchone()[0]
    page_count = cur.execute("PRAGMA page_count").fetchone()[0]
    facts = {
        "live_path": str(LIVE),
        "live_sizes": live_sizes,
        "snapshot_path": str(SNAPSHOT),
        "snapshot_bytes": SNAPSHOT.stat().st_size,
        "copy_seconds": round(copy_s, 3),
        "page_size": page_size,
        "page_count": page_count,
        "user_version": cur.execute("PRAGMA user_version").fetchone()[0],
        "integrity_check": cur.execute("PRAGMA integrity_check").fetchone()[0],
        "sqlite_version": sqlite3.sqlite_version,
        "tables": {},
        "counts": {
            "views": cur.execute("SELECT count(*) FROM sqlite_master WHERE type='view'").fetchone()[0],
            "triggers": cur.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],
            "indexes": cur.execute("SELECT count(*) FROM sqlite_master WHERE type='index'").fetchone()[0],
        },
    }
    for (name,) in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall():
        facts["tables"][name] = cur.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]

    facts["observations_per_source"] = dict(
        cur.execute(
            "SELECT ss.source_key, count(*) FROM price_observation po "
            "JOIN source_offer so ON so.offer_id = po.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    )

    dst.close()
    src.close()

    # ---- the browser's copy: same bytes, WAL off -------------------------
    for stale in (SNAPSHOT_NOWAL, Path(str(SNAPSHOT_NOWAL) + "-wal"), Path(str(SNAPSHOT_NOWAL) + "-shm")):
        if stale.exists():
            stale.unlink()
    shutil.copy2(SNAPSHOT, SNAPSHOT_NOWAL)
    nowal = sqlite3.connect(str(SNAPSHOT_NOWAL))
    t0 = time.perf_counter()
    mode = nowal.execute("PRAGMA journal_mode = delete").fetchone()[0]
    nowal.commit()
    nowal.close()
    convert_s = time.perf_counter() - t0
    header = SNAPSHOT_NOWAL.read_bytes()[18:20]
    facts["nowal"] = {
        "path": str(SNAPSHOT_NOWAL),
        "bytes": SNAPSHOT_NOWAL.stat().st_size,
        "journal_mode": mode,
        "header_18_19": list(header),
        "convert_seconds": round(convert_s, 3),
        "why": "no OPFS VFS implements xShmMap, so a WAL-mode file cannot be opened in a browser",
    }

    (WORK / "snapshot-facts.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")

    mib = facts["snapshot_bytes"] / 1024 / 1024
    print(f"live      {LIVE}")
    print(f"          main {live_sizes['main_bytes']:,} B  wal {live_sizes['wal_bytes']:,} B")
    print(f"snapshot  {SNAPSHOT}")
    print(f"          {facts['snapshot_bytes']:,} B ({mib:.1f} MiB) in {copy_s:.2f}s")
    print(f"          user_version={facts['user_version']} integrity={facts['integrity_check']}")
    print(f"          price_observation={facts['tables'].get('price_observation'):,}")
    print(f"          {len(facts['tables'])} tables, {facts['counts']['indexes']} indexes, "
          f"{facts['counts']['triggers']} triggers, {facts['counts']['views']} views")
    print(f"nowal     {SNAPSHOT_NOWAL.name}: journal_mode={facts['nowal']['journal_mode']}, "
          f"header[18:20]={facts['nowal']['header_18_19']} (WAL is 2,2), "
          f"{facts['nowal']['convert_seconds']:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
