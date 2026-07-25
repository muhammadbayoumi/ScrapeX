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
from .payload import utc_now_iso
from .reports import (export_details_table, export_history_table,
                      export_source_table, source_summary)


class SheetSink(Protocol):
    """A destination that holds a 'workbook' of per-source tabs."""

    def ensure_workbook(self, folder: str, workbook: str):
        """Ensure the folder + workbook exist; return an opaque handle."""

    def write_tab(self, handle, tab: str, header: list[str], rows: list[list]) -> None:
        """Create/replace one tab with header + rows."""

    def location(self, handle) -> str:
        """Human-facing URL or path for the workbook."""


def publish_source(conn: sqlite3.Connection, source_key: str, sink: SheetSink,
                   folder: str, workbook: str, schema: str = ORIGINAL_SCHEMA,
                   tab: str | None = None) -> tuple[int, str]:
    """Publish one source's current-price table to a sink. Returns (rows, location).

    `schema` picks the Original Schema (every column, raw names — the default, so
    a downstream consumer is never surprised by cosmetic choices) or the owner's
    Current View (spec 22).

    `tab` defaults to the source key. Passing a dated one is how the snapshot
    update behaviour keeps each export beside the last instead of replacing it
    (spec 19) — the sink itself needs no knowledge of that choice.
    """
    tabs = workbook_tables(conn, source_key, schema=schema, tab=tab)
    handle = sink.ensure_workbook(folder, workbook)
    for name, header, rows in tabs:
        sink.write_tab(handle, name, header, rows)
    return len(tabs[0][2]), sink.location(handle)


def workbook_tables(conn: sqlite3.Connection, source_key: str,
                    schema: str = ORIGINAL_SCHEMA,
                    tab: str | None = None) -> list[tuple[str, list[str], list[list]]]:
    """EVERY tab one source's export is made of: [(tab, header, rows), ...].

    The one place that decides what a complete export CONTAINS, so a workbook
    downloaded from the Data page, one written to disk by the CLI and one
    pushed to Google can never be three different answers to the same question
    (P1 DRY). The owner's report was that the export carried the price table
    and nothing else — the details and the history were already published to
    Google and were reachable nowhere else.

    Order is deliberate: prices first because that is what the export is for,
    then the details, then the history, then the sheet that says where all of
    it came from. Empty tables are skipped rather than written as a header
    nobody can use — except the price table, whose absence is an error, not an
    empty tab.
    """
    header, rows = export_source_table(conn, source_key)
    if not rows:
        raise ValueError(f"nothing to publish for {source_key} — crawl + ingest it first")
    header, rows = apply_schema(conn, source_key, header, rows, schema)
    name = tab or source_key
    tabs = [(name, header, rows)]
    for suffix, table in (("details", export_details_table(conn, source_key)),
                          ("history", export_history_table(conn, source_key))):
        extra_header, extra_rows = table
        if extra_rows:
            tabs.append((f"{name} — {suffix}", extra_header, extra_rows))
    tabs.append((f"{name} — about", *_about(conn, source_key, tabs)))
    return tabs


def _about(conn: sqlite3.Connection, source_key: str,
           tabs: list[tuple[str, list[str], list[list]]]) -> tuple[list[str], list[list]]:
    """A tab that says what the other tabs ARE and where the numbers came from.

    A spreadsheet outlives the screen it was exported from and gets mailed to
    people who never saw it. Without this, "1124.87" is a number with no source,
    no date, no currency policy and no statement about tax — and the first
    question anyone asks of a price list is which of those it is.
    """
    summary = source_summary(conn, source_key)
    site = conn.execute(
        "SELECT source_name_ar, source_name, base_url FROM source_site WHERE source_key = ?",
        (source_key,)).fetchone()
    facts: list[list] = [
        ["source_key", source_key],
        ["source_name", (site[0] if site else "") or ""],
        ["source_name_en", (site[1] if site else "") or ""],
        ["site", (site[2] if site else "") or ""],
        ["exported_at", utc_now_iso()],
    ]
    if summary is not None:
        facts += [
            ["products", summary.products],
            ["variants", summary.variants],
            ["observations", summary.observations],
            ["last_run_status", summary.last_status or ""],
            ["last_run_at", summary.last_run or ""],
        ]
    facts += [[f"rows in “{name}”", len(rows)] for name, _header, rows in tabs]
    # What the reader is holding, in the reader's terms.
    facts += [
        ["prices", "as the source published them — nothing is computed or converted"],
        ["tax", "each row states vat_included, and the evidence columns beside it "
                "say how well that is known and where the source says so"],
        ["details", "one row per fact the source stated about a product: "
                    "descriptions, specifications, images and datasheets"],
        ["history", "every price observation behind the current figure, oldest first"],
    ]
    return ["fact", "value"], facts


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
