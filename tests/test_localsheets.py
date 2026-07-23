"""Local .xlsx export — same data + arrangement as the Google sink, on disk."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("openpyxl")
from openpyxl import load_workbook  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.localsheets import LocalSink, _safe_title  # noqa: E402
from scrapex.publish import publish_source  # noqa: E402
from scrapex.reports import EXPORT_HEADER  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    ingest_payloads(c, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1", product_name="LED 400W",
                effective_price="1,200.00"),
        one_row(external_product_id="2", external_variant_id="v2", product_name="Copper Wire",
                effective_price="50.00", availability="out_of_stock"),
    ])])
    yield c
    c.close()


def test_export_creates_workbook_with_source_tab(tmp_path: Path, conn):
    n, location = publish_source(conn, "ELSEWEDYSHOP", LocalSink(), str(tmp_path), "ScrapeX Data")
    assert n == 2
    path = Path(location)
    assert path.exists() and path.name == "ScrapeX Data.xlsx"

    wb = load_workbook(path)
    assert "ELSEWEDYSHOP" in wb.sheetnames
    assert "Sheet" not in wb.sheetnames  # default empty sheet removed
    ws = wb["ELSEWEDYSHOP"]
    assert [c.value for c in ws[1]] == EXPORT_HEADER          # same header as Google
    names = {ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)}
    assert names == {"LED 400W", "Copper Wire"}
    # numeric price stays numeric (not a string) — same as the Google sink
    price_col = EXPORT_HEADER.index("effective_price") + 1
    assert ws.cell(row=2, column=price_col).value in (1200.0, 50.0)


def test_export_is_idempotent_replace(tmp_path: Path, conn):
    LocalSink().ensure_workbook  # noqa: B018 - smoke
    publish_source(conn, "ELSEWEDYSHOP", LocalSink(), str(tmp_path), "ScrapeX Data")
    publish_source(conn, "ELSEWEDYSHOP", LocalSink(), str(tmp_path), "ScrapeX Data")
    wb = load_workbook(tmp_path / "ScrapeX Data.xlsx")
    assert wb.sheetnames.count("ELSEWEDYSHOP") == 1  # replaced, not duplicated


def test_second_source_adds_a_tab(tmp_path: Path, conn):
    sink = LocalSink()
    publish_source(conn, "ELSEWEDYSHOP", sink, str(tmp_path), "ScrapeX Data")
    # a second (empty->skip): simulate another source by writing directly
    sink.write_tab(tmp_path / "ScrapeX Data.xlsx", "MASDAR", EXPORT_HEADER, [["x"] * len(EXPORT_HEADER)])
    wb = load_workbook(tmp_path / "ScrapeX Data.xlsx")
    # One workbook, a tab per source — plus the source's own history tab.
    # (Its details tab is skipped: this fixture publishes no attributes, and
    # a header with no rows is furniture, not data.)
    assert set(wb.sheetnames) == {"ELSEWEDYSHOP", "ELSEWEDYSHOP — history", "MASDAR"}


def test_safe_title_truncates_and_sanitizes():
    assert _safe_title("A" * 40) == "A" * 31
    assert "/" not in _safe_title("A/B:C")


def test_publish_empty_source_raises(tmp_path: Path):
    c = dbmod.connect(":memory:")
    try:
        dbmod.migrate(c)
        with pytest.raises(ValueError, match="nothing to publish"):
            publish_source(c, "ELSEWEDYSHOP", LocalSink(), str(tmp_path), "ScrapeX Data")
    finally:
        c.close()
