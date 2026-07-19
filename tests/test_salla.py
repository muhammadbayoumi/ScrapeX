"""T2: salla-html connector — sitemap enumeration + JSON-LD parse + price gotcha."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.salla import SallaConnector, offer_price, parse_product_jsonld, sitemap_locs
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"


def _read(name): return (FX / name).read_text(encoding="utf-8")


# ---- pure parsers (no network) ----------------------------------------------

def test_sitemap_locs():
    locs = sitemap_locs(_read("salla_subsitemap.xml"))
    assert "https://alsweed.sa/ar/water-pump/p1506395107" in locs and len(locs) == 3


def test_parse_jsonld_simple_and_graph():
    simple = parse_product_jsonld(_read("salla_product_simple.html"))
    assert simple["sku"] == "1506395107" and simple["name"] == "طلمبة مياه جراندفوس"
    variant = parse_product_jsonld(_read("salla_product_variant.html"))  # inside @graph
    assert variant["sku"] == "1256812562"


def test_offer_price_falls_back_to_lowprice():
    assert offer_price({"price": "450", "priceCurrency": "SAR"})[:2] == ("450", "SAR")
    # the variant gotcha: price 0 -> AggregateOffer lowPrice
    assert offer_price({"price": 0, "lowPrice": "120", "priceCurrency": "SAR"})[0] == "120"
    assert offer_price({"price": 0})[0] == ""  # no fallback -> skipped upstream


# ---- full fetch (stubbed) ----------------------------------------------------

class _Resp:
    def __init__(self, text): self.text = text


class _StubFetcher:
    ROUTES = {
        "/ar/sitemap.xml": "salla_sitemap.xml",
        "/ar/sitemap-products.xml": "salla_subsitemap.xml",
        "/p1506395107": "salla_product_simple.html",
        "/p1256812562": "salla_product_variant.html",
    }

    def __init__(self): self.requests_count = 0

    def get(self, url, **kwargs):
        self.requests_count += 1
        for needle, fixture in self.ROUTES.items():
            if url.endswith(needle):
                return _Resp(_read(fixture))
        raise RuntimeError("404 " + url)

    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ALSWEED", source_name="السويد", base_url="https://alsweed.sa",
        family="salla-html", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_salla_crawls_sitemap_and_maps_products():
    table = next(iter(SallaConnector(_StubFetcher()).fetch(make_entry())))
    assert len(table.rows) == 2  # the /privacy-policy URL was filtered out (no /p{id})
    view = RowView(PRODUCT_PRICES, table.header)

    pump = view.as_dict(table.rows[0])
    assert pump["external_product_id"] == "1506395107"
    assert pump["effective_price"] == "450" and pump["currency"] == "SAR"
    assert pump["product_name"] == "طلمبة مياه جراندفوس"
    assert pump["availability"] == "in_stock"

    plywood = view.as_dict(table.rows[1])
    assert plywood["effective_price"] == "120"  # AggregateOffer lowPrice fallback


def test_salla_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(SallaConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 2 and not result.errors
