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

from .config import SourceEntry
from .connectors.factory import build_connector
from .ingest import IngestResult, ingest_payloads


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
    connector, fetcher = build_connector(entry)
    try:
        tables = list(connector.fetch(entry))       # network only — no DB involved
        requests_count = fetcher.requests_count
    finally:
        fetcher.close()
    payloads = [t.to_payload() for t in tables]
    with (lock() if lock is not None else nullcontext()):
        result = ingest_payloads(conn, entry, payloads, job_id=job_id)
    return CaptureResult(ingest=result, requests_count=requests_count,
                         tables=len(tables), rows=sum(len(t.rows) for t in tables))
