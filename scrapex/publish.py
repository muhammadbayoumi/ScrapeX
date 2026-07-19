"""One publish path, two sinks (ENGINEERING.md P1 DRY, A3 minimal abstraction).

`publish_source` gets the source's flat table ONCE via reports.export_source_table
and hands it to a sink — Google Sheets or a local .xlsx workbook. Both sinks
therefore emit the SAME columns in the SAME order, arranged the SAME way (a
workbook with one tab per source). The only difference is where it lands.
"""
from __future__ import annotations

import sqlite3
from typing import Protocol

from .fields import ORIGINAL_SCHEMA, apply_schema
from .reports import export_source_table


class SheetSink(Protocol):
    """A destination that holds a 'workbook' of per-source tabs."""

    def ensure_workbook(self, folder: str, workbook: str):
        """Ensure the folder + workbook exist; return an opaque handle."""

    def write_tab(self, handle, tab: str, header: list[str], rows: list[list]) -> None:
        """Create/replace one tab with header + rows."""

    def location(self, handle) -> str:
        """Human-facing URL or path for the workbook."""


def publish_source(conn: sqlite3.Connection, source_key: str, sink: SheetSink,
                   folder: str, workbook: str, schema: str = ORIGINAL_SCHEMA) -> tuple[int, str]:
    """Publish one source's current-price table to a sink. Returns (rows, location).

    `schema` picks the Original Schema (every column, raw names — the default, so
    a downstream consumer is never surprised by cosmetic choices) or the owner's
    Current View (spec 22).
    """
    header, rows = export_source_table(conn, source_key)
    if not rows:
        raise ValueError(f"nothing to publish for {source_key} — crawl + ingest it first")
    header, rows = apply_schema(conn, source_key, header, rows, schema)
    handle = sink.ensure_workbook(folder, workbook)
    sink.write_tab(handle, source_key, header, rows)
    return len(rows), sink.location(handle)


class GoogleSink:
    """SheetSink backed by a gdrive.DriveManager (Sign in with Google)."""

    def __init__(self, manager) -> None:
        self._m = manager

    def ensure_workbook(self, folder: str, workbook: str) -> str:
        folder_id = self._m.ensure_folder(folder)
        return self._m.ensure_spreadsheet(workbook, folder_id)

    def write_tab(self, spreadsheet_id: str, tab: str, header, rows) -> None:
        self._m.write_tab(spreadsheet_id, tab, header, rows)

    def location(self, spreadsheet_id: str) -> str:
        return self._m.spreadsheet_url(spreadsheet_id)
