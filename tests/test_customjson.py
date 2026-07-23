"""T2: custom-json-api connector — against the REAL sikaegshop API shape.

Every fixture here is captured from https://www.sikaegshop.com/api/products on
2026-07-20 (products trimmed to 3 per page; envelope, field names, values and
pagination byte-faithful). The previous fixture was hand-authored from memory
and wrong in every structural detail, which let this connector be green in CI
and return nothing at all in reality.

The tests are therefore written against what the API actually sends, not against
what the connector expected it to send.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.custom_json import CustomJsonConnector, _availability, _prices
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowBuilder, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"
PAGE1 = json.loads((FX / "sikaegshop_page1.json").read_text(encoding="utf-8"))
PAGE2 = json.loads((FX / "sikaegshop_page2.json").read_text(encoding="utf-8"))


class _Resp:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves the two captured pages and records what was asked for."""

    def __init__(self, payloads=None, total_pages: int | None = None):
        self.requests_count = 0
        self.urls: list[str] = []
        self._payloads = payloads
        self._total_pages = total_pages

    def get(self, url, **kwargs):
        self.requests_count += 1
        self.urls.append(url)
        if self._payloads is not None:
            return _Resp(self._payloads)
        page = PAGE2 if "page=2" in url else PAGE1
        if self._total_pages is not None:
            page = {**page, "pagination": {**page["pagination"],
                                           "totalPages": self._total_pages}}
        return _Resp(page)

    def close(self): pass


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SIKAEGSHOP", source_name="سيكا مصر شوب", base_url="https://www.sikaegshop.com",
        family="custom-json-api", currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def fetch_rows(fetcher):
    table = next(iter(CustomJsonConnector(fetcher).fetch(make_entry())))
    return table, RowView(PRODUCT_PRICES, table.header)


# ---- price semantics, verified against all 87 live products ------------------

def test_specail_price_is_a_TRADE_TIER_price_the_public_is_never_charged():
    """SETTLED 2026-07-23 from the storefront's own bundle + a live browser.

    The shop's rule (905ebab0162dcb89.js, identical in the grid and home cards)
    charges `specail_price` only when `2 === Number(user.customerTypeId)`.
    Proven on product 235 (price 1252.5, specail_price 939.38): anonymous and
    customerTypeId 1 both render 1252.50 with no badge; only customerTypeId 2
    renders 939.38 with the "سعر خاص" badge and 1252.50 struck through.

    ScrapeX crawls anonymously, so this branch is unreachable BY CONSTRUCTION —
    not "until a date". Honouring specail_price invented a discount the public
    is never offered, and because the field never changes no re-crawl, rebuild
    or wipe could clear it (the owner's exact report)."""
    assert _prices({"price": 325, "specail_price": 206.25}) == ("325", "", "325")
    # the real product-235 numbers, not a stand-in
    assert _prices({"price": 1252.5, "specail_price": 939.38}) == ("1252.5", "", "1252.5")


def test_a_LIVE_flash_sale_IS_the_price_because_it_binds_every_visitor():
    """Branch (1) of the same rule: a positive flash_sale_price is returned
    before the customer type is even consulted, so it is what ANY visitor pays.
    Null on all 87 products today; this pins the shape for the day it runs."""
    assert _prices({"price": 325, "specail_price": 206.25,
                    "flash_sale_price": 150}) == ("325", "150", "150")


def test_a_flash_sale_beats_a_trade_price_even_when_the_trade_price_is_lower():
    """Order matters and is not ours to choose: the bundle returns the flash
    price FIRST, without comparing it to specail_price. A dormant trade price
    below a live flash price must not leak into what we report."""
    assert _prices({"price": 1000, "specail_price": 600,
                    "flash_sale_price": 800}) == ("1000", "800", "800")


def test_a_flash_price_at_or_above_list_is_charged_but_is_not_called_a_discount():
    """The shop honours any positive flash_sale_price — it never checks that the
    flash price is lower. We charge what it charges, but `sale_price` stays
    empty so a mispriced flash cannot be reported as a discount it is not."""
    assert _prices({"price": 100, "flash_sale_price": 120}) == ("100", "", "120")
    assert _prices({"price": 100, "flash_sale_price": 100}) == ("100", "", "100")


def test_the_trade_price_is_kept_as_enrichment_named_for_what_it_is():
    """Nothing is lost by refusing to charge it: specail_price still travels,
    labelled as the customer-type-2 price rather than as a discount."""
    from scrapex.connectors.custom_json import enrichment_rows
    from scrapex.rowspec import ENRICHMENT

    builder = RowBuilder(ENRICHMENT)
    view = RowView(ENRICHMENT, builder.header)
    rows = [view.as_dict(r) for r in enrichment_rows(
        builder, {"product_id": 235, "price": 1252.5, "specail_price": 939.38},
        "https://www.sikaegshop.com")]

    trade = [r for r in rows if r["attribute_code"] == "trade_tier_price"]
    assert len(trade) == 1
    assert trade[0]["raw_value"] == "939.38"
    assert "customer type 2" in trade[0]["attribute_label"]
    # and it is never mistaken for a price row
    assert not any(r["attribute_code"] in ("sale_price", "effective_price") for r in rows)


def test_a_product_without_a_trade_price_emits_no_trade_row():
    """9 of the 87 live products carry no specail_price at all — they must not
    acquire an empty one."""
    from scrapex.connectors.custom_json import enrichment_rows
    from scrapex.rowspec import ENRICHMENT

    builder = RowBuilder(ENRICHMENT)
    view = RowView(ENRICHMENT, builder.header)
    rows = [view.as_dict(r) for r in enrichment_rows(
        builder, {"product_id": 285, "price": 1600, "specail_price": None},
        "https://www.sikaegshop.com")]

    assert not any(r["attribute_code"] == "trade_tier_price" for r in rows)


def test_zero_or_null_discount_means_no_sale():
    assert _prices({"price": 120, "specail_price": 0}) == ("120", "", "120")
    assert _prices({"price": 120, "specail_price": None, "sale_price": None}) == ("120", "", "120")
    assert _prices({"price": 120, "flash_sale_price": 0}) == ("120", "", "120")


def test_unpriced_is_empty():
    assert _prices({"price": 0, "specail_price": 0}) == ("", "", "")


def test_stock_quantity_decides_availability_not_the_listing_flag():
    """is_active means "listed", not "in stock". A live product with zero stock
    is out of stock — calling it in_stock promises what cannot be bought."""
    assert _availability({"stock_quantity": 83, "is_active": True}) == "in_stock"
    assert _availability({"stock_quantity": 0, "is_active": True}) == "out_of_stock"
    assert _availability({"is_active": False}) == "out_of_stock"
    assert _availability({}) == "unknown"


# ---- the real envelope -------------------------------------------------------

def test_the_real_response_envelope_is_read():
    """The live API answers {success, data[], pagination{}}. Reading `products`
    found None, looped zero times, and reported a clean zero-row success."""
    table, view = fetch_rows(_StubFetcher(total_pages=1))

    assert table.rows, "the real envelope produced no rows"
    first = view.as_dict(table.rows[0])
    assert first["external_product_id"] == "256"
    assert first["product_name"] == "سيكا فيوم 5 كيلو"      # Arabic name preferred
    assert first["regular_price"] == "325"
    # No live flash sale -> the shop charges its listing price, and so do we.
    assert first["sale_price"] == ""
    assert first["effective_price"] == "325"
    assert first["currency"] == "EGP" and first["vat_included"] == "1"
    assert first["availability"] == "in_stock"
    # /products/{id} verified live; /product/{id} returns 404.
    assert first["product_url"] == "https://www.sikaegshop.com/products/256"


def test_an_unreadable_response_fails_loudly_instead_of_returning_zero_rows():
    """This is the whole defect. A shape the connector cannot read has to be an
    error the owner sees, not a crawl that prints 0 rows and exits 0."""
    with pytest.raises(ValueError, match="no product list"):
        next(iter(CustomJsonConnector(
            _StubFetcher(payloads={"unexpected": "shape"})).fetch(make_entry())))


def test_a_bare_list_response_is_still_accepted():
    """A sibling shop in this family may answer with a plain array."""
    table, _ = fetch_rows(_StubFetcher(payloads=PAGE1["data"]))
    assert len(table.rows) == 3


# ---- pagination --------------------------------------------------------------

def test_every_page_is_read_not_just_the_first():
    """The catalogue is 87 products over 8 pages of 12. Reading one page would
    have captured 12 of them and called it the whole catalogue."""
    fetcher = _StubFetcher(total_pages=2)

    table, view = fetch_rows(fetcher)

    assert fetcher.requests_count == 2
    assert any("page=2" in u for u in fetcher.urls)
    ids = {view.get(r, "external_product_id") for r in table.rows}
    assert ids == {"256", "223", "257", "252", "253", "248"}


def test_a_product_repeated_across_a_page_edge_is_counted_once():
    """The catalogue can shift between page requests, so the same product can
    arrive twice. Two rows for one product would read as two offers."""
    fetcher = _StubFetcher(total_pages=3)   # page 3 serves page 1 again

    table, view = fetch_rows(fetcher)

    ids = [view.get(r, "external_product_id") for r in table.rows]
    assert len(ids) == len(set(ids)), f"duplicated across pages: {ids}"


def test_pagination_is_capped_against_a_runaway():
    from scrapex.connectors.custom_json import _MAX_PAGES

    fetcher = _StubFetcher(total_pages=10_000)
    fetch_rows(fetcher)

    assert fetcher.requests_count == _MAX_PAGES


# ---- end to end --------------------------------------------------------------

def test_customjson_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(CustomJsonConnector(_StubFetcher(total_pages=2)).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 6 and not result.errors


def test_both_languages_and_the_classification_ride_every_row():
    """The API states two names and a bilingual category per product and the
    connector dropped ALL of it — sika crawled with no categories and no
    English names (owner-reported). The live arname arrives with stray
    whitespace; it must not survive into the path."""
    table, view = fetch_rows(_StubFetcher())
    first = view.as_dict(table.rows[0])

    assert first["product_name"] == "سيكا فيوم 5 كيلو"
    assert first["product_name_en"] == "Sika Fume® 5 KG"
    assert first["lang"] == "ar"
    assert first["category_path"] == "إضافات الخرسانه"      # tab stripped
    assert first["category_external_id"] == "20"


def test_the_classification_lands_in_BOTH_languages(conn=None):
    """The owner's standing rule: a site publishing both languages is captured
    in both. sika states category_arname AND category_enname per product."""
    table, view = fetch_rows(_StubFetcher())
    first = view.as_dict(table.rows[0])

    assert first["category_path"] == "إضافات الخرسانه"
    assert first["category_path_en"] == "Concrete additives"
