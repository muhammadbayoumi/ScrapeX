"""Capture service: run a source's connector and ingest in one step (DRY).

Shared by the CLI (funnel/local-inbox path stays separate) and the local web
API that the Chrome extension calls. The extension NEVER re-implements parsing:
it triggers this, which reuses the Python connectors + the one ingest pipeline.
"""
from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Callable

from . import settings
from .config import SourceEntry
from .connectors.factory import build_connector
from .ingest import IngestResult, ingest_payloads


class WarehouseSupersededError(RuntimeError):
    """The database this crawl opened stopped being the live one mid-flight."""


def _refuse_if_superseded(conn: sqlite3.Connection) -> None:
    """Abort rather than ingest into a database that was sealed while we crawled.

    The write lock serialises a commit DURING a compaction, but not one made
    immediately AFTER it by a crawl that began before it: `connector.fetch` runs
    for minutes holding no lock, and the connection it returns to is a handle on
    a file that may since have been sealed and replaced. Those observations
    would land in the archive and be invisible to the live warehouse forever.

    Checked HERE, inside the lock and immediately before the insert, because
    that is the only point where the answer cannot go stale again.
    """
    from . import storage

    row = conn.execute("PRAGMA database_list").fetchone()
    path = row[2] if row is not None else ""
    if not path:
        return                              # in-memory database: nothing to seal
    when = storage.sealed_at(path)
    if when:
        raise WarehouseSupersededError(
            f"The warehouse was replaced at {when} while this crawl was running, "
            f"so its rows were not written: they would have gone into the sealed "
            f"archive at {path} rather than the live database. Run the crawl again."
        )


def crawl_settings(conn: sqlite3.Connection) -> dict:
    """The owner's politeness choices (spec 33), read once per capture.

    Read here rather than inside the fetcher so the connector layer keeps no
    dependency on the database, and so a bad saved value degrades to the shipped
    default instead of failing a crawl.
    """
    def number(key: str, fallback: float) -> float:
        try:
            return float(settings.get(conn, key))
        except (ValueError, TypeError):
            return fallback

    return {
        "min_interval_s": number("crawl_min_interval_s", 1.0),
        "timeout_s": number("crawl_timeout_s", 30.0),
        "user_agent": settings.get(conn, "crawl_user_agent"),
    }


@dataclass
class CaptureResult:
    ingest: IngestResult
    requests_count: int
    tables: int
    rows: int = 0          # raw rows the connector produced — the F6 canary input


def capture_source(conn: sqlite3.Connection, entry: SourceEntry,
                   job_id: int | None = None,
                   lock: Callable[[], AbstractContextManager] | None = None) -> CaptureResult:
    """Fetch a source via its connector and ingest straight into harvest.db.

    `lock` (when given) wraps ONLY the ingest write. Holding the process-wide DB
    lock across `connector.fetch` would keep it for the whole network crawl —
    minutes of politeness delays — during which every unrelated UI write (renaming
    a column, saving a view) is refused. The fetch touches no database at all, so
    it has no business holding a database lock.

    Connector/network errors propagate; per-row data errors are isolated (Q3)."""
    connector, fetcher = build_connector(entry, crawl_settings(conn))
    try:
        tables = list(connector.fetch(entry))       # network only — no DB involved
        requests_count = fetcher.requests_count
    finally:
        fetcher.close()
    payloads = [t.to_payload() for t in tables]
    with (lock() if lock is not None else nullcontext()):
        _refuse_if_superseded(conn)
        result = ingest_payloads(conn, entry, payloads, job_id=job_id)
    return CaptureResult(ingest=result, requests_count=requests_count,
                         tables=len(tables), rows=sum(len(t.rows) for t in tables))
