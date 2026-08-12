"""The shared publish path: same data to any sink, proven through a fake."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.ingest import ingest_payloads
from scrapex.publish import publish_source
from scrapex.reports import EXPORT_HEADER
from tests.test_ingest import make_entry, make_payload, one_row


class _RecordingSink:
    def __init__(self):
        self.calls = []
    def ensure_workbook(self, folder, workbook):
        self.calls.append(("ensure", folder, workbook))
        return "HANDLE"
    def write_tab(self, handle, tab, header, rows):
        self.calls.append(("write", handle, tab, header, rows))
    def location(self, handle):
        return f"loc:{handle}"


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    ingest_payloads(c, make_entry(), [make_payload([one_row(product_name="LED 400W")])])
    yield c
    c.close()


def test_publish_source_drives_the_sink(conn):
    sink = _RecordingSink()
    n, location = publish_source(conn, "ELSEWEDYSHOP", sink, "ScrapeX", "ScrapeX Data")
    assert n == 1 and location == "loc:HANDLE"
    assert sink.calls[0] == ("ensure", "ScrapeX", "ScrapeX Data")
    _, handle, tab, header, rows = sink.calls[1]
    assert handle == "HANDLE" and tab == "ELSEWEDYSHOP" and header == EXPORT_HEADER
    assert rows[0][header.index("product_name")] == "LED 400W"


