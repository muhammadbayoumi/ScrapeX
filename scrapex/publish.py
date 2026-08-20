"""One publish path, two sinks (ENGINEERING.md P1 DRY, A3 minimal abstraction).

`publish_source` gets the source's flat table ONCE via reports.export_source_table
and hands it to a sink — Google Sheets or a local .xlsx workbook. Both sinks
therefore emit the SAME columns in the SAME order, arranged the SAME way (a
workbook with one tab per source). The only difference is where it lands.
"""
from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

from .fields import ORIGINAL_SCHEMA, apply_schema
from .payload import utc_now_iso
from .reports import export_details_table, export_history_table, export_source_table, source_summary


class SheetSink(Protocol):
    """A destination that holds a 'workbook' of per-source tabs."""

    def ensure_workbook(self, folder: str, workbook: str):
        """Ensure the folder + workbook exist; return an opaque handle."""

    def write_tab(self, handle, tab: str, header: list[str], rows: list[list]) -> None:
        """Create/replace one tab with header + rows."""

    def location(self, handle) -> str:
        """Human-facing URL or path for the workbook."""

    # A sink MAY also offer `batch(handle)` — a context manager around the whole
    # run of write_tab calls (see _sink_batch). It is deliberately not declared
    # here: a sink for which a tab is one cheap call needs no such thing, and
    # requiring it would make every existing sink stop satisfying this protocol.


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
    with _sink_batch(sink, handle):
        for name, header, rows in tabs:
            sink.write_tab(handle, name, header, rows)
    return len(tabs[0][2]), sink.location(handle)


def _sink_batch(sink: SheetSink, handle) -> AbstractContextManager[None]:
    """Let a sink treat one source's tabs as a single operation, if it can.

    A tab is one cheap remote call, but a whole-file rewrite on disk: LocalSink
    used to re-read and re-save the entire .xlsx per tab, which is four passes
    over the workbook for the four tables an export is made of. Asking for the
    batch here — the one place that knows a run of write_tab calls belongs
    together — is what lets it read and write the file once.

    Optional on purpose: a sink without `batch` (the fakes the tests publish
    into) keeps the plain one-call-per-tab path, unchanged.
    """
    batch = getattr(sink, "batch", None)
    return batch(handle) if batch is not None else nullcontext()


def dataset_workbook_tables(payload: dict,
                            tab: str | None = None
                            ) -> list[tuple[str, list[str], list[list]]]:
    """One generic dataset as workbook tabs. A pure function over the payload.

    ONE TAB, and the reason is what a dataset IS. The price export carries four
    because a price has a history, a detail block and a provenance sheet; a
    contractor directory has one flat table and inventing three empty tabs
    beside it would be the "empty tables written as a header nobody can use"
    that workbook_tables already refuses.

    The header is the DISPLAY labels, in the schema's own field order, and the
    cells are read through the same key order — so a column cannot land under
    another column's name if the payload's key order ever changes.
    """
    keys = [column["key"] for column in payload["columns"]]
    header = [column["label"] or column["key"] for column in payload["columns"]]
    rows = [[row.get(key, "") for key in keys] for row in payload["rows"]]
    return [(tab or payload["source_key"], header, rows)]


def workbook_tables(conn: sqlite3.Connection, source_key: str,
                    schema: str = ORIGINAL_SCHEMA,
                    tab: str | None = None,
                    general: sqlite3.Connection | None = None,
                    ) -> list[tuple[str, list[str], list[list]]]:
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
    # A GENERIC DATASET IS A TABLE LIKE ANY OTHER TABLE, and the catalogue is
    # asked FIRST -- the same order and the same reason as /api/table and
    # /source/{key}: a dataset key is lower-case with underscores and a source
    # key is upper-case, so the two sets cannot collide, and asking the smaller
    # table first costs nothing when it misses.
    #
    # THE BRANCH IS HERE RATHER THAN IN THE ROUTE, deliberately. This function
    # is documented as the one place that decides what a complete export
    # CONTAINS, and it has THREE consumers -- the .xlsx download, the Apps
    # Script funnel (outputs.py) and the Google/local sink (publish_source).
    # Fixing only the route would have left `export contractors` from the CLI
    # and the Drive push still answering "nothing to publish", which is the
    # defect this is, one layer down.
    #
    # `general` is separate because a two-database installation keeps the
    # catalogue in the general database; it falls back to `conn`, which is the
    # single-database case and the one the owner runs.
    from .extract.service import dataset_table_payload

    dataset = dataset_table_payload(general if general is not None else conn,
                                    source_key)
    if dataset is not None:
        return dataset_workbook_tables(dataset, tab=tab)

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
        # Row VALUES, so no rename reaches them: the workbook would go on
        # explaining itself in the retired vocabulary. Edited by hand.
        ["source_name", (site[1] if site else "") or ""],
        ["source_name_ar", (site[0] if site else "") or ""],
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
        ["tax", "each row states tax_included, and the evidence columns beside it "
                "say how well that is known and where the source says so"],
        ["details", "one row per fact the source stated about a product: "
                    "descriptions, specifications, images and datasheets"],
        ["history", "every price observation behind the current figure, oldest first"],
    ]
    return ["fact", "value"], facts


# GoogleSink was here until 2026-08-11 — a thin adapter over gdrive.DriveManager,
# and the last thing in this file that knew Google existed. The owner ruled that
# the engine fetches and saves locally while the extension owns every Google
# operation, so writing a tab into a spreadsheet is extension/sheets.js now.
#
# EVERYTHING ELSE IN THIS FILE STAYS, and the distinction is worth stating
# because most of it reads like Google code and none of it is: SheetSink is the
# protocol localsheets.LocalSink implements, publish_source and workbook_tables
# serve the Excel export and the Apps Script funnel, and _sink_batch is what
# stops a four-tab export rewriting the whole workbook four times (ت5, fixed in
# 0a2209c). Deleting any of them alongside GoogleSink would have taken a working
# local feature with it.
