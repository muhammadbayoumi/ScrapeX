"""The Python/SQLite reference numbers, and the SQL trace the browser replays.

Two jobs, one file, because they must not drift apart:

1. **Measure** what the shipping engine costs on the real warehouse — the Data
   page's `table_payload` (which is `_LATEST_PER_OFFER` plus its rate and
   history subqueries) and an ingest of one real crawl's journal.
2. **Record** the exact statements those two operations issue, with their
   parameters, into `.work/trace-*.json`. `run.py` hands *those strings* to the
   browser. Nobody hand-copies a query into the JS harness, so the comparison
   cannot quietly become "a query that looks like the Data page's".

A number with no baseline decides nothing, so every figure here is emitted with
the hardware, the row counts and the statement it came from.

Run:  python baseline.py            (needs .work/snapshot.db from prepare.py)
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sqlite3
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / ".work"
SNAPSHOT = WORK / "snapshot.db"
REPO = HERE.parent.parent

# This spike lives in a worktree while an editable install points `scrapex` at
# the MAIN checkout. Without this pin the baseline would silently measure the
# other tree's reports.py, and the trace it hands the browser would be that
# tree's SQL.
sys.path.insert(0, str(REPO))

from scrapex import config as configmod  # noqa: E402
from scrapex import db as dbmod  # noqa: E402
from scrapex import ingest as ingestmod  # noqa: E402
from scrapex import reports  # noqa: E402
from scrapex.payload import FunnelPayload  # noqa: E402

for _mod in (reports, ingestmod, dbmod):
    assert Path(_mod.__file__).resolve().is_relative_to(REPO), (
        f"{_mod.__name__} loaded from {_mod.__file__}, not the worktree at {REPO}"
    )


class Recorder(sqlite3.Connection):
    """A connection that keeps every statement it was asked to run.

    Subclasses `Connection` rather than wrapping it so that `isinstance` checks
    and `sqlite3.Row` behaviour downstream are unchanged; only `execute` is
    intercepted, which is the single call path `reports.py` and `ingest.py` use.
    """

    def _init_recording(self) -> None:
        self.trace: list[dict] = []
        self.recording = True

    def execute(self, sql, parameters=(), /):  # type: ignore[override]
        t0 = time.perf_counter()
        cur = super().execute(sql, parameters)
        dt = time.perf_counter() - t0
        if getattr(self, "recording", False):
            self.trace.append({
                "sql": sql,
                "params": [_jsonable(p) for p in (parameters or ())],
                # prepare+first-step only; fetch cost is attributed to the caller
                "python_ms": round(dt * 1000, 4),
            })
        return cur


def _jsonable(value):
    if isinstance(value, (str, int, float)) or value is None:
        return value
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return str(value)


def _open(path: Path) -> Recorder:
    conn = sqlite3.connect(str(path), factory=Recorder)
    conn._init_recording()
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.trace.clear()
    return conn


def _hardware() -> dict:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
    }


# ---- 1. the Data page ------------------------------------------------------

def measure_queries(repeats: int) -> dict:
    facts = json.loads((WORK / "snapshot-facts.json").read_text(encoding="utf-8"))
    per_source = facts["observations_per_source"]
    # The two that matter: the biggest source in the warehouse, and the biggest
    # shop. A spike that only measured a small source would prove nothing.
    targets = [k for k in ("GPP_ENERGY", "MADAR") if k in per_source]

    out: dict = {"hardware": _hardware(), "sources": {}}
    trace: dict[str, list[dict]] = {}

    for source_key in targets:
        # COLD: a connection that has never touched a page of this database.
        conn = _open(SNAPSHOT)
        t0 = time.perf_counter()
        payload = reports.table_payload(conn, source_key)
        cold_ms = (time.perf_counter() - t0) * 1000
        trace[source_key] = list(conn.trace)
        conn.recording = False

        warm: list[float] = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            reports.table_payload(conn, source_key)
            warm.append((time.perf_counter() - t0) * 1000)

        # The two statements on their own, so the browser can be compared
        # statement-for-statement and not only end to end.
        stmts = []
        for entry in trace[source_key]:
            if "price_observation" not in entry["sql"]:
                continue
            params = tuple(entry["params"])
            runs = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                conn.execute(entry["sql"], params).fetchall()
                runs.append((time.perf_counter() - t0) * 1000)
            stmts.append({
                "sql": entry["sql"],
                "params": entry["params"],
                "label": "count" if entry["sql"].lstrip().upper().startswith("SELECT COUNT") else "rows",
                "min_ms": round(min(runs), 2),
                "median_ms": round(statistics.median(runs), 2),
                "max_ms": round(max(runs), 2),
            })

        out["sources"][source_key] = {
            "observations": per_source[source_key],
            "rows_returned": len(payload.get("rows", [])),
            "statements_issued": len(trace[source_key]),
            "table_payload_cold_ms": round(cold_ms, 2),
            "table_payload_warm_min_ms": round(min(warm), 2),
            "table_payload_warm_median_ms": round(statistics.median(warm), 2),
            "table_payload_warm_max_ms": round(max(warm), 2),
            "statements": stmts,
        }
        conn.close()
        print(f"  {source_key:14s} {per_source[source_key]:>6,} obs  "
              f"cold {cold_ms:8.1f} ms  warm median {statistics.median(warm):8.1f} ms  "
              f"({len(payload.get('rows', []))} rows, {len(trace[source_key])} statements)")

    (WORK / "trace-queries.json").write_text(
        json.dumps({"repeats": repeats, "traces": trace}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ---- 2. one crawl's ingest -------------------------------------------------

JOURNAL = Path.home() / ".scrapex" / "journal-dropped-v5-ELBUROJ"


def _load_crawl_payload() -> tuple[FunnelPayload, dict]:
    """One real crawl's journal, coalesced into one payload.

    Read from `journal-dropped-v5-ELBUROJ` — the pages a version gate rejected
    this morning — and NOT from `~/.scrapex/job-journal/`, which the running
    ELBUROJ crawl owns. Read-only either way; the copy is made in memory.

    The only field rewritten is `payload_version` (5 -> 6). That single number
    is what the gate rejected; every row below it is exactly the bytes the
    connector produced. Recorded here rather than hidden because it is the
    subject of question 4.
    """
    files = sorted(JOURNAL.glob("*.json"))
    if not files:
        raise SystemExit(f"no journal pages under {JOURNAL}")
    first = json.loads(files[0].read_text(encoding="utf-8"))
    rows: list[list] = []
    raw_bytes = 0
    for path in files:
        raw_bytes += path.stat().st_size
        page = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(page["rows"])
    doc = dict(first)
    doc["payload_version"] = 6
    doc["rows"] = rows
    doc["chunk"] = None
    meta = {
        "journal_dir": str(JOURNAL),
        "pages": len(files),
        "journal_bytes": raw_bytes,
        "rows": len(rows),
        "source_key": doc["source_key"],
        "rewritten_fields": {"payload_version": "5 -> 6"},
    }
    return FunnelPayload.model_validate(doc), meta


def measure_ingest() -> dict:
    payload, meta = _load_crawl_payload()

    # A copy of the copy: the ingest WRITES, and the query baseline above must
    # keep measuring the untouched snapshot.
    target = WORK / "ingest-target.db"
    for stale in (target, Path(str(target) + "-wal"), Path(str(target) + "-shm")):
        if stale.exists():
            stale.unlink()
    shutil.copy2(SNAPSHOT, target)

    # The source's real manifest entry: tax evidence, region and currency all
    # come from it, and ingest writes differently without them.
    manifest = configmod.load_manifest(REPO / "sources.yaml")
    entry = next(e for e in manifest.sources if e.source_key == meta["source_key"])

    conn = _open(target)
    before = conn.execute("SELECT count(*) FROM price_observation").fetchone()[0]
    conn.trace.clear()
    t0 = time.perf_counter()
    result = ingestmod.ingest_payloads(conn, entry, [payload])
    conn.commit()
    total_ms = (time.perf_counter() - t0) * 1000
    after = conn.execute("SELECT count(*) FROM price_observation").fetchone()[0]
    trace = [e for e in conn.trace if e["sql"] != "SELECT count(*) FROM price_observation"]
    conn.close()

    writes = sum(1 for e in trace if e["sql"].lstrip()[:6].upper() in ("INSERT", "UPDATE", "DELETE"))
    out = {
        "hardware": _hardware(),
        "crawl": meta,
        "observations_before": before,
        "observations_after": after,
        "observations_appended": after - before,
        "ingest_result": str(result)[:400],
        "wall_ms": round(total_ms, 1),
        "statements_issued": len(trace),
        "write_statements": writes,
        "ms_per_row": round(total_ms / max(1, meta["rows"]), 3),
    }
    (WORK / "trace-ingest.json").write_text(
        json.dumps({"statements": trace}, ensure_ascii=False), encoding="utf-8")
    print(f"  ingest         {meta['rows']:>6,} rows from {meta['pages']} journal pages  "
          f"{total_ms:8.1f} ms  ({len(trace):,} statements, {writes:,} writes)")
    return out


# ---- 3. the resume journal, on the filesystem ------------------------------

def measure_journal(pages: int) -> dict:
    """What the journal costs on disk today, so the OPFS figure has a reference.

    The shipping engine writes one JSON file per fetched page
    (`scrapex/localinbox.py:37` `write_payload`) and reads the resume skip set
    back by scanning filenames (`list_tokens`). Both halves are timed here.
    """
    target = WORK / "journal-baseline"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    # Same page size as the OPFS side of the experiment: the real journal's
    # mean page, 930,534 bytes over 871 files.
    envelope = len(json.dumps({"payload_version": 6, "filler": ""}))
    body = json.dumps({"payload_version": 6, "filler": "x" * (1069 - envelope)})

    t0 = time.perf_counter()
    for i in range(pages):
        (target / f"t-{i:020d}__page.json").write_text(body, encoding="utf-8")
    write_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    listed = {p.name.split("__", 1)[0] for p in target.iterdir()}
    list_s = time.perf_counter() - t1

    size = sum(p.stat().st_size for p in target.iterdir())
    shutil.rmtree(target, ignore_errors=True)
    out = {
        "pages": pages,
        "bytes_per_page": len(body.encode("utf-8")),
        "total_bytes": size,
        "write_ms": round(write_s * 1000, 1),
        "write_ms_per_page": round(write_s * 1000 / pages, 3),
        "list_ms": round(list_s * 1000, 1),
        "listed": len(listed),
    }
    print(f"  journal        {pages:>6,} pages  {out['write_ms']:8.1f} ms "
          f"({out['write_ms_per_page']:.3f} ms/page), list {out['list_ms']:.1f} ms")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--journal-pages", type=int, default=3570)
    args = ap.parse_args()

    if not SNAPSHOT.exists():
        print("run prepare.py first", file=sys.stderr)
        return 2

    print(f"baseline on {SNAPSHOT.stat().st_size/1024/1024:.1f} MiB snapshot, "
          f"sqlite {sqlite3.sqlite_version}, {platform.platform()}")
    result = {"queries": measure_queries(args.repeats)}
    if not args.skip_ingest:
        result["ingest"] = measure_ingest()
    result["journal"] = measure_journal(args.journal_pages)

    (WORK / "baseline.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {WORK / 'baseline.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
