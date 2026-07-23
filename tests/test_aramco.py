"""aramco-fuel-page — the official Saudi monthly prices, live-shaped.

The fixture is a window CUT FROM THE LIVE PAGE on 2026-07-23 (React build,
styles and all): a fabricated fixture would prove nothing (the GPP lesson).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.aramco import (
    AramcoFuelConnector, page_lines, parse_month, parse_pairs,
)
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import COMMODITY_PRICE, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"
HTML = (FX / "aramco_retail_fuels.html").read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text): self.text = text


class _StubFetcher:
    def __init__(self): self.requests_count = 0
    def get(self, url, **kwargs):
        self.requests_count += 1
        assert url.endswith("/ar/what-we-do/energy-products/retail-fuels")
        return _Resp(HTML)
    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ARAMCO_FUEL_SA", source_name="أرامكو السعودية",
        base_url="https://www.aramco.com", family="aramco-fuel-page",
        cadence="monthly", authority="official", currency="SAR",
        default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                             scope=ExtractScope.LATEST_ONLY,
                             materials=["GASOLINE_91", "GASOLINE_95",
                                        "GASOLINE_98", "DIESEL", "KEROSENE"],
                             regions=["SA"])],
    ))


# ---- pure parsers ------------------------------------------------------------

def test_the_heading_month_parses_to_the_sources_own_date():
    lines = page_lines(HTML)
    heading = next(l for l in lines if "أسعار المنتجات لشهر" in l)
    assert parse_month(heading) == "2026-07-01"


def test_an_unreadable_month_is_loud_never_todays_date():
    with pytest.raises(ValueError, match="readable month"):
        parse_month("أسعار المنتجات لشهر ~~~ ؟؟")


def test_pairs_read_in_page_order_and_a_thin_page_is_loud():
    lines = page_lines(HTML)
    start = next(i for i, l in enumerate(lines) if "أسعار المنتجات لشهر" in l)
    pairs = parse_pairs(lines, start)
    assert ("2.18", "بنزين 91") in pairs and ("1.79", "ديزل") in pairs
    with pytest.raises(ValueError, match="layout has changed"):
        parse_pairs(["heading", "1.0", "بنزين 91", "prose"], 0)


# ---- the full fetch ----------------------------------------------------------

def test_aramco_emits_the_five_official_rows():
    table = next(iter(AramcoFuelConnector(_StubFetcher()).fetch(make_entry())))
    view = RowView(COMMODITY_PRICE, table.header)
    rows = {view.as_dict(r)["material_key"]: view.as_dict(r) for r in table.rows}

    assert set(rows) == {"GASOLINE_91", "GASOLINE_95", "GASOLINE_98",
                         "DIESEL", "KEROSENE"}
    g91 = rows["GASOLINE_91"]
    assert g91["effective_price"] == "2.18"
    assert g91["currency"] == "SAR" and g91["unit"] == "liter"
    assert g91["region"] == "SA" and g91["vat_included"] == "1"
    # The heading month is the SOURCE's dating, never our crawl date.
    assert g91["source_date"] == "2026-07-01"
    assert g91["price_basis"] == "original"
    assert rows["KEROSENE"]["effective_price"] == "1.75"


def test_an_unmapped_label_is_dropped_out_loud():
    blank = HTML.replace("بنزين 98", "وقود مستقبلي غامض")
    class _Odd(_StubFetcher):
        def get(self, url, **kwargs):
            self.requests_count += 1
            return _Resp(blank)

    table = next(iter(AramcoFuelConnector(_Odd()).fetch(make_entry())))

    view = RowView(COMMODITY_PRICE, table.header)
    assert len(table.rows) == 4
    assert any("وقود مستقبلي غامض" in w for w in table.warnings), \
        "an unknown fuel label vanished without a word"


def test_a_redesigned_page_fails_loud_not_empty():
    class _Redesigned(_StubFetcher):
        def get(self, url, **kwargs):
            self.requests_count += 1
            return _Resp("<html><body><h1>Welcome</h1></body></html>")

    with pytest.raises(ValueError, match="layout change"):
        next(iter(AramcoFuelConnector(_Redesigned()).fetch(make_entry())))


def test_aramco_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(AramcoFuelConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
        offers = conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0]
    finally:
        conn.close()
    assert result.observations == 5 and not result.errors
    assert offers == 5
