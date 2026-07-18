"""Capture service: run a source's connector and ingest in one step (DRY).

Shared by the CLI (funnel/local-inbox path stays separate) and the local web
API that the Chrome extension calls. The extension NEVER re-implements parsing:
it triggers this, which reuses the Python connectors + the one ingest pipeline.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .config import SourceEntry
from .connectors.factory import build_connector
from .ingest import IngestResult, ingest_payloads


@dataclass
class CaptureResult:
    ingest: IngestResult
    requests_count: int
    tables: int


def capture_source(conn: sqlite3.Connection, entry: SourceEntry) -> CaptureResult:
    """Fetch a source via its connector and ingest straight into harvest.db.

    The caller holds the DB write lock (A10) and commits. Connector/network
    errors propagate; per-row data errors are isolated inside ingest (Q3)."""
    connector, fetcher = build_connector(entry)
    try:
        tables = list(connector.fetch(entry))
        requests_count = fetcher.requests_count
    finally:
        fetcher.close()
    payloads = [t.to_payload() for t in tables]
    result = ingest_payloads(conn, entry, payloads)
    return CaptureResult(ingest=result, requests_count=requests_count, tables=len(tables))
