"""DriveManager logic via mocked Google service clients (no network/creds).

The googleapiclient fluent chain (drive.files().list().execute()) is naturally
mockable with MagicMock — we assert the requests ScrapeX builds and the
idempotent create-if-absent behaviour.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from scrapex import db as dbmod
from scrapex.gdrive import FOLDER_MIME, SHEET_MIME, MAX_EXPORT_ROWS, DriveManager
from scrapex.ingest import ingest_payloads
from scrapex.reports import EXPORT_HEADER, export_source_table
from tests.test_ingest import make_entry, make_payload, one_row


def _drive_returning(files):
    drive = MagicMock()
    drive.files.return_value.list.return_value.execute.return_value = {"files": files}
    drive.files.return_value.create.return_value.execute.return_value = {"id": "NEW_ID"}
    return drive


def test_ensure_folder_creates_when_absent():
    drive = _drive_returning([])
    dm = DriveManager(drive, MagicMock())
    assert dm.ensure_folder("ScrapeX") == "NEW_ID"
    body = drive.files.return_value.create.call_args.kwargs["body"]
    assert body["mimeType"] == FOLDER_MIME and body["name"] == "ScrapeX"


def test_ensure_folder_reuses_when_present():
    drive = _drive_returning([{"id": "EXISTING", "name": "ScrapeX"}])
    dm = DriveManager(drive, MagicMock())
    assert dm.ensure_folder("ScrapeX") == "EXISTING"
    drive.files.return_value.create.assert_not_called()  # idempotent


def test_ensure_spreadsheet_creates_in_folder():
    drive = _drive_returning([])
    dm = DriveManager(drive, MagicMock())
    sid = dm.ensure_spreadsheet("ScrapeX Data", "FOLDER1")
    assert sid == "NEW_ID"
    body = drive.files.return_value.create.call_args.kwargs["body"]
    assert body["mimeType"] == SHEET_MIME and body["parents"] == ["FOLDER1"]


def test_find_query_escapes_apostrophes():
    drive = _drive_returning([])
    DriveManager(drive, MagicMock()).ensure_folder("O'Neill's")
    q = drive.files.return_value.list.call_args.kwargs["q"]
    assert "O\\'Neill\\'s" in q  # no query injection / breakage


def test_write_tab_adds_missing_tab_then_writes():
    sheets = MagicMock()
    sheets.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": "Sheet1"}}]}
    dm = DriveManager(MagicMock(), sheets)
    dm.write_tab("SID", "ELSEWEDYSHOP", ["a", "b"], [["1", "2"]])
    # tab was missing -> addSheet requested
    batch = sheets.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    assert batch["requests"][0]["addSheet"]["properties"]["title"] == "ELSEWEDYSHOP"
    # cleared then wrote header + rows
    sheets.spreadsheets.return_value.values.return_value.clear.assert_called_once()
    update_body = sheets.spreadsheets.return_value.values.return_value.update.call_args.kwargs["body"]
    assert update_body["values"] == [["a", "b"], ["1", "2"]]


def test_write_tab_skips_addsheet_when_present():
    sheets = MagicMock()
    sheets.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": "ELSEWEDYSHOP"}}]}
    DriveManager(MagicMock(), sheets).write_tab("SID", "ELSEWEDYSHOP", ["a"], [["1"]])
    sheets.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_write_tab_rejects_oversized():
    dm = DriveManager(MagicMock(), MagicMock())
    with pytest.raises(ValueError, match="MAX_EXPORT_ROWS"):
        dm.write_tab("SID", "T", ["a"], [["x"]] * (MAX_EXPORT_ROWS + 1))


def test_urls():
    assert DriveManager.spreadsheet_url("ABC").endswith("/ABC/edit")
    assert "ABC" in DriveManager.folder_url("ABC")


# ---- export query (DRY with browse) -----------------------------------------

def test_export_source_table_shape():
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        ingest_payloads(conn, make_entry(), [make_payload([
            one_row(product_name="LED 400W", effective_price="1,200.00", regular_price="1,450.00", sale_price="1,200.00"),
        ])])
        header, rows = export_source_table(conn, "ELSEWEDYSHOP")
    finally:
        conn.close()
    assert header == EXPORT_HEADER
    assert len(rows) == 1
    row = dict(zip(header, rows[0]))
    assert row["product_name"] == "LED 400W"
    assert row["effective_price"] == 1200.0        # numeric, not a string
    assert row["vat_included"] == "yes"
    # The 2026-07-22 widening: identity completed and the discount made visible.
    assert row["brand"] == "Elsewedy"
    assert row["discount"] == "-250.00 (-17.2%)"
    assert row["category"] == "" and row["official_source"] == ""
