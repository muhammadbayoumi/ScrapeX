"""T2: salla-html connector — sitemap enumeration + JSON-LD parse + price gotcha."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.salla import SallaConnector, offer_price, parse_product_jsonld, sitemap_locs
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowBuilder, RowView
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


def test_a_priceless_variant_product_is_skipped_OUT_LOUD():
    """Verified live on alsweed 2026-07-23: a variant-priced page publishes
    price:0 with no lowPrice, no meta amount, no inline figure — nothing to
    read. Skipping is right; skipping SILENTLY was the GPP lesson again."""
    class _WithPriceless(_StubFetcher):
        ROUTES = {**_StubFetcher.ROUTES,
                  "/p1506395199": "salla_product_priceless.html"}
        SITEMAP_EXTRA = "https://alsweed.sa/ar/tank/p1506395199"

        def get(self, url, **kwargs):
            if url.endswith("/ar/sitemap-products.xml"):
                self.requests_count += 1
                base = _read("salla_subsitemap.xml")
                return _Resp(base.replace(
                    "</urlset>",
                    f"<url><loc>{self.SITEMAP_EXTRA}</loc></url></urlset>"))
            return super().get(url, **kwargs)

    table = next(iter(SallaConnector(_WithPriceless()).fetch(make_entry())))

    assert len(table.rows) == 2, "the priceless product must be skipped, not guessed"
    assert any("no usable price" in w for w in table.warnings),         "a skipped product left no trace in the run's warnings"
    assert any("1 product(s)" in w for w in table.warnings)


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


def test_an_enrichment_extract_no_longer_dies_on_a_missing_import():
    """The enrichment branch referenced ENRICHMENT without it ever being
    imported, so the FIRST salla source to contract enrichment would have
    crawled the whole catalogue and then died on NameError with nothing
    written. Driven by the 2026-07-20 live captures."""
    class _LiveStub:
        ROUTES = {
            "/ar/sitemap.xml": "live/salla_alsweed_sitemap_index.xml",
            "/ar/sitemap-1.xml": "live/salla_alsweed_sitemap_products_TRIMMED.xml",
            "/p1506395107": "live/salla_alsweed_product_price0_p1506395107.html",
            "/p698258674": "live/salla_alsweed_product_priced_p698258674.html",
        }

        def __init__(self): self.requests_count = 0

        def get(self, url, **kwargs):
            self.requests_count += 1
            for needle, fixture in self.ROUTES.items():
                if url.endswith(needle):
                    return _Resp(_read(fixture))
            return _Resp("<html></html>")   # a page outside the trimmed capture

        def close(self): pass

    entry = make_entry().model_copy(update={"extract": [
        ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
        ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS),
    ]})

    tables = list(SallaConnector(_LiveStub()).fetch(entry))

    assert [str(t.kind) for t in tables] == ["product_prices", "enrichment"]
    codes = {row[tables[1].header.index("attribute_code")] for row in tables[1].rows}
    assert "description" in codes and "sku" in codes


def test_a_sold_out_product_is_recorded_as_sold_out_not_unknown():
    """Live capture, alsweed 2026-07-23: p1754450923 states
    availability https://schema.org/OutOfStock and still carries a price.

    The row said `unknown` — the connector only ever asked whether the string
    contained "InStock" — so a shop's plain "we have run out" was stored as
    "the shop said nothing about stock".
    """
    node = json.loads((FX / "live" /
                       "salla_alsweed_product_node_outofstock_2026-07-23.json")
                      .read_text(encoding="utf-8"))
    builder = RowBuilder(PRODUCT_PRICES)

    row = SallaConnector._row(
        builder, node,
        "https://alsweed.sa/ar/لي-سخان-اسباني-مجدول/p1754450923",
        make_entry(), "1")

    fields = RowView(PRODUCT_PRICES, builder.header).as_dict(row)
    assert fields["availability"] == "out_of_stock"
    assert fields["effective_price"] == "6" and fields["currency"] == "SAR"
    assert fields["external_product_id"] == "1754450923"
