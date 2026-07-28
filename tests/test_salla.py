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


def price_rows(connector, entry):
    """Every price row across every yielded table, with the shared header.

    salla yields ONE TABLE PER PRODUCT since the resume work: a crawl that
    accumulated everything and yielded once at the end had written nothing to
    the journal when interrupted at hour five. These tests care about the rows,
    not the granularity, so they read them the way capture does.
    """
    header, rows, warnings, tokens = None, [], [], []
    for table in connector.fetch(entry):
        if table.kind is not PRODUCT_PRICES.kind:
            continue
        header = header or table.header
        rows.extend(table.rows)
        warnings.extend(table.warnings)
        if table.page_token:
            tokens.append(table.page_token)
    return header, rows, warnings, tokens


def test_salla_crawls_sitemap_and_maps_products():
    header, rows, _warnings, tokens = price_rows(SallaConnector(_StubFetcher()),
                                                make_entry())
    assert len(rows) == 2  # the /privacy-policy URL was filtered out (no /p{id})
    # One token per product, and they differ — that IS the resume checkpoint.
    assert len(tokens) == 2 and len(set(tokens)) == 2
    view = RowView(PRODUCT_PRICES, header)

    pump = view.as_dict(rows[0])
    assert pump["external_product_id"] == "1506395107"
    assert pump["price"] == "450" and pump["currency"] == "SAR"
    assert pump["product_name_ar"] == "طلمبة مياه جراندفوس"
    # The owner's rule, pinned: a source that publishes only Arabic fills
    # only the marked column and leaves the unmarked one EMPTY. Carrying
    # the Arabic name in product_name would rename everything and fix
    # nothing — the heading would still assert a language it does not hold.
    assert pump["product_name"] == ""
    assert pump["availability"] == "in_stock"

    plywood = view.as_dict(rows[1])
    assert plywood["price"] == "120"  # AggregateOffer lowPrice fallback


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

    _header, rows, warnings, _tokens = price_rows(SallaConnector(_WithPriceless()),
                                                 make_entry())

    assert len(rows) == 2, "the priceless product must be skipped, not guessed"
    assert any("no usable price" in w for w in warnings),         "a skipped product left no trace in the run's warnings"
    assert any("1 product(s)" in w for w in warnings)


def test_salla_end_to_end_into_warehouse():
    entry = make_entry()
    # EVERY table, not the first: one product per table since the resume work.
    tables = list(SallaConnector(_StubFetcher()).fetch(entry))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [t.to_payload() for t in tables])
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

    # Interleaved per PRODUCT now, not two tables at the end: each product's
    # price and its details carry the SAME token, so a resume can never land a
    # price without the details that came off the same page.
    kinds = [str(t.kind) for t in tables]
    assert "product_prices" in kinds and "enrichment" in kinds
    enrichment = [t for t in tables if str(t.kind) == "enrichment"]
    codes = {row[t.header.index("attribute_code")]
             for t in enrichment for row in t.rows}
    assert "description" in codes and "sku" in codes
    # Every details table carries a checkpoint of its own. It is the SAME token
    # as that product's price row where the product has a price at all — a
    # priceless product still publishes details, and yields them alone.
    assert all(t.page_token for t in enrichment),         "details with no checkpoint cannot survive a resume"


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

    # The row builder is shared with zid now (it was the same code twice, with
    # one line different), so it is asserted where it lives — with salla's own
    # id rule handed to it, which is that one line.
    from scrapex.connectors.jsonld import product_row
    from scrapex.connectors.salla import _salla_id

    url = "https://alsweed.sa/ar/لي-سخان-اسباني-مجدول/p1754450923"
    row = product_row(builder, node, url, make_entry(), "1", _salla_id(url, node))

    fields = RowView(PRODUCT_PRICES, builder.header).as_dict(row)
    assert fields["availability"] == "out_of_stock"
    assert fields["price"] == "6" and fields["currency"] == "SAR"
    assert fields["external_product_id"] == "1754450923"


# ---- resume: the whole point of the tokens ----------------------------------

def test_a_resumed_crawl_does_not_refetch_what_it_already_journaled():
    """#70. This shop answers about one page every ten seconds, so a resume that
    refetched would cost the hours it exists to save.

    The skip happens BEFORE the request — that is the difference between real
    resume and magento's half-done version, where the check sits below the call
    and saves only parsing.
    """
    connector = SallaConnector(_StubFetcher())
    entry = make_entry()

    first = list(connector.fetch(entry))
    cold_requests = connector._fetcher.requests_count
    tokens = {t.page_token for t in first if t.page_token}
    assert tokens, "a crawl with no checkpoints cannot be resumed"

    resumed = SallaConnector(_StubFetcher())
    resumed.skip_tokens = tokens          # what capture hands back on resume
    tables = list(resumed.fetch(entry))

    assert [t for t in tables if t.page_token] == [], \
        "every product was already journaled, so none should be re-emitted"
    assert resumed._fetcher.requests_count < cold_requests, \
        "a resumed crawl must issue FEWER requests, not merely skip parsing"
    assert any("already journaled" in w for t in tables for w in t.warnings), \
        "the run must say what it skipped rather than look like it found nothing"


def test_a_partial_resume_fetches_only_what_is_missing():
    """The realistic case: one product landed before the pause, the rest did not."""
    cold = SallaConnector(_StubFetcher())
    entry = make_entry()
    first = [t for t in cold.fetch(entry) if t.page_token]
    assert len(first) >= 2

    resumed = SallaConnector(_StubFetcher())
    resumed.skip_tokens = {first[0].page_token}       # only the first survived
    tables = [t for t in resumed.fetch(entry) if t.page_token]

    remaining = {t.page_token for t in tables}
    assert first[0].page_token not in remaining, "the journaled product was refetched"
    assert {t.page_token for t in first[1:]} <= remaining, \
        "a product that was NOT journaled must still be fetched"


def test_a_token_survives_being_written_into_a_filename():
    """The trap this nearly walked into: write_payload SANITISES a token into
    the stem and list_tokens reads the sanitised form back, so a connector
    holding a raw URL compares against something it can never match — the
    resume would silently refetch everything and look simply broken.
    """
    from scrapex.localinbox import safe_token, token_survives_a_filename

    connector = SallaConnector(_StubFetcher())
    for table in connector.fetch(make_entry()):
        if table.page_token:
            assert token_survives_a_filename(table.page_token), table.page_token

    # And the trap itself, so the reason is not lost: a raw URL does NOT.
    assert not token_survives_a_filename("https://alsweed.sa/ar/x/p1")
    assert token_survives_a_filename(safe_token("https://alsweed.sa/ar/x/p1"))
