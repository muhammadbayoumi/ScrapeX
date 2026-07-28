"""T2: custom-json-api connector — against the REAL sikaegshop API shape.

Every fixture here is captured from https://www.sikaegshop.com/api/products on
2026-07-20 (products trimmed to 3 per page; envelope, field names, values and
pagination byte-faithful). The previous fixture was hand-authored from memory
and wrong in every structural detail, which let this connector be green in CI
and return nothing at all in reality.

`sikaegshop_detail_252.json` is the DETAIL response for the same product 252
that page 2 lists, captured live 2026-07-25 from /api/products/252 and faithful
except for one edit: `product_related_..._idToproducts` is emptied. It arrives
holding two complete product objects — prices, attachments and all — and this
connector deliberately does not capture them, so the fixture keeps the key and
drops ninety lines of a record no assertion reads.

The tests are therefore written against what the API actually sends, not against
what the connector expected it to send.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import CrawlBlocked, CrawlInterrupted
from scrapex.connectors.custom_json import CustomJsonConnector, _availability, _prices
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"
PAGE1 = json.loads((FX / "sikaegshop_page1.json").read_text(encoding="utf-8"))
PAGE2 = json.loads((FX / "sikaegshop_page2.json").read_text(encoding="utf-8"))
DETAIL_252 = json.loads((FX / "sikaegshop_detail_252.json").read_text(encoding="utf-8"))

# ".../api/products/252" — a DETAIL url. ".../api/products" and
# ".../api/products?page=2" are the list, and must not be confused for one.
_DETAIL_URL = re.compile(r"/api/products/(\d+)$")


class _Resp:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    """Serves the two captured pages and records what was asked for.

    `details` maps product id -> detail payload; `fails` maps product id -> the
    exception its detail request raises, so the error paths (T3) are driven by
    the same stub as the happy one.
    """

    def __init__(self, payloads=None, total_pages: int | None = None,
                 details: dict | None = None, fails: dict | None = None):
        self.requests_count = 0
        self.urls: list[str] = []
        self.detail_urls: list[str] = []
        self._payloads = payloads
        self._total_pages = total_pages
        self._details = details or {}
        self._fails = fails or {}

    def get(self, url, **kwargs):
        self.requests_count += 1
        self.urls.append(url)
        found = _DETAIL_URL.search(url)
        if found:
            pid = found.group(1)
            self.detail_urls.append(url)
            if pid in self._fails:
                raise self._fails[pid]
            return _Resp(self._details.get(pid, {}))
        if self._payloads is not None:
            return _Resp(self._payloads)
        page = PAGE2 if "page=2" in url else PAGE1
        if self._total_pages is not None:
            page = {**page, "pagination": {**page["pagination"],
                                           "totalPages": self._total_pages}}
        return _Resp(page)

    def close(self): pass


def make_entry(enrichment: bool = False) -> SourceEntry:
    extract = [ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)]
    if enrichment:
        extract.append(ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS))
    return SourceEntry.model_validate(dict(
        source_key="SIKAEGSHOP", source_name="سيكا مصر شوب", base_url="https://www.sikaegshop.com",
        family="custom-json-api", currency="EGP", default_region="EG", vat_mode="incl",
        extract=extract,
    ))


def fetch_rows(fetcher):
    table = next(iter(CustomJsonConnector(fetcher).fetch(make_entry())))
    return table, RowView(PRODUCT_PRICES, table.header)


def list_page(*products, total_pages: int = 1) -> dict:
    """A list response carrying exactly the given captured product entries."""
    return {"success": True, "data": list(products),
            "pagination": {"page": 1, "limit": 12, "total": len(products),
                           "totalPages": total_pages}}


def crawl(fetcher, entry) -> list:
    return list(CustomJsonConnector(fetcher).fetch(entry))


def details_of(tables) -> list[dict]:
    """Every enrichment row across the yielded tables, read by column name."""
    out = []
    for table in tables:
        if table.kind is not ENRICHMENT.kind:
            continue
        view = RowView(ENRICHMENT, table.header)
        out.extend(view.as_dict(row) for row in table.rows)
    return out


PRODUCT_252 = next(p for p in PAGE2["data"] if p["product_id"] == 252)
PRODUCT_253 = next(p for p in PAGE2["data"] if p["product_id"] == 253)


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
    flash price is lower. We charge what it charges, but `price_sale` stays
    empty so a mispriced flash cannot be reported as a discount it is not."""
    assert _prices({"price": 100, "flash_sale_price": 120}) == ("100", "", "120")
    assert _prices({"price": 100, "flash_sale_price": 100}) == ("100", "", "100")


def test_the_trade_price_rides_the_price_row_and_is_never_charged():
    """Nothing is lost by refusing to charge it: specail_price still travels —
    as a PRICE, in its own column, since the owner ruled «عمود سعر فى الجدول لا
    تفصيلة» (0052). It was an enrichment row until then, which put a number in
    the attributes bag that no other shop's bag would ever match.

    What must not change is that it is never mistaken for what the public pays.
    """
    fetcher = _StubFetcher(payloads=list_page(
        {**PRODUCT_252, "price": 1252.5, "specail_price": 939.38}))
    table, view = fetch_rows(fetcher)
    wire = view.as_dict(table.rows[0])

    assert wire["price_trade"] == "939.38"
    # the public price is untouched by it
    assert wire["price"] == "1252.5"
    assert wire["price_sale"] == ""


def test_a_product_without_a_trade_price_states_nothing_rather_than_zero():
    """9 of the 87 live products carry no specail_price at all. Absent is not
    zero, and a 0.00 trade price would read as a giveaway."""
    fetcher = _StubFetcher(payloads=list_page(
        {**PRODUCT_252, "price": 1252.5, "specail_price": None}))
    table, view = fetch_rows(fetcher)

    assert view.as_dict(table.rows[0])["price_trade"] == ""


def test_zero_or_null_discount_means_no_sale():
    assert _prices({"price": 120, "specail_price": 0}) == ("120", "", "120")
    assert _prices({"price": 120, "specail_price": None, "price_sale": None}) == ("120", "", "120")
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
    assert first["product_name_ar"] == "سيكا فيوم 5 كيلو"      # Arabic name preferred
    assert first["price_before"] == "325"
    # No live flash sale -> the shop charges its listing price, and so do we.
    assert first["price_sale"] == ""
    assert first["price"] == "325"
    assert first["currency"] == "EGP" and first["tax_included"] == "1"
    assert first["availability"] == "in_stock"
    # /products/{id} verified live; /product/{id} returns 404.
    assert first["product_link"] == "https://www.sikaegshop.com/products/256"


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

    assert first["product_name_ar"] == "سيكا فيوم 5 كيلو"
    assert first["product_name"] == "Sika Fume® 5 KG"
    assert first["lang"] == "ar"
    assert first["category_path_ar"] == "إضافات الخرسانه"      # tab stripped
    assert first["category_external_id"] == "20"


def test_the_classification_lands_in_BOTH_languages(conn=None):
    """The owner's standing rule: a site publishing both languages is captured
    in both. sika states category_arname AND category_enname per product."""
    table, view = fetch_rows(_StubFetcher())
    first = view.as_dict(table.rows[0])

    assert first["category_path_ar"] == "إضافات الخرسانه"
    assert first["category_path"] == "Concrete additives"


def test_this_shop_publishes_exactly_ONE_product_shape():
    """B1 (2026-07-25): sikaegshop has no second shape, and this pins it.

    All 87 live products were read, plus `/api/products/{id}` for a detail
    check, and the API carries NO field describing a variant, option, bundle or
    group — no `type`, `product_type`, `variants`, `variations`, `options`,
    `bundle`, `child_products`, `has_variants`. One product is one offer at one
    `price`, so nothing here can be a range collapsed into a single figure.

    CORRECTED 2026-07-25: this docstring used to also claim "the detail endpoint
    returns nothing the list did not", which was never checked and is false —
    the detail states the specifications, the full description, ten more
    attachments and the sku (see the detail-pass tests below). The claim that
    survives the re-check is the narrow one above, about product SHAPE.
    `product_attribute_assignments` is a detail-only bag of published facts, not
    a variant axis: it carries no price and no stock of its own.

    If the shop ever grows one of these, this test fails the moment the fixture
    is re-captured, instead of the connector quietly recording the first price
    it finds in a new structure.
    """
    shape_bearing = {
        "type", "product_type", "variants", "variations", "options",
        "attributes", "bundle", "bundle_products", "child_products",
        "has_variants", "is_bundle", "grouped", "grouped_products",
        "price_range", "price_min", "price_max",
    }
    for product in PAGE1["data"]:
        found = shape_bearing & set(product)
        assert not found, (
            f"product {product.get('product_id')} now carries {sorted(found)} — "
            "this shop has grown a second product shape and the connector's "
            "one-product-one-price rule has to be re-derived, not assumed")


# ---- the detail pass: the record the LIST endpoint does not publish ----------
#
# The owner's report, 2026-07-25: the product page prints a Specifications card,
# two PDF datasheets, a three-part description and nine photographs; the details
# panel showed a trade price, a weight and two short descriptions. Nothing was
# being dropped — the connector only ever read /api/products, which publishes
# none of that. These tests pin the second endpoint.

def test_the_detail_pass_runs_ONLY_when_the_manifest_declares_enrichment():
    """87 products is 87 extra requests. A source asking for prices alone must
    not pay for them — and must not be slowed by a pass it never asked for."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, PRODUCT_253),
                           details={"252": DETAIL_252})

    tables = crawl(fetcher, make_entry())            # prices only

    assert fetcher.detail_urls == []
    assert fetcher.requests_count == 1               # the one list page, nothing else
    assert [t.kind for t in tables] == [PRODUCT_PRICES.kind]


def test_the_detail_is_asked_once_per_product_at_the_verified_url():
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, PRODUCT_253),
                           details={"252": DETAIL_252, "253": DETAIL_252})

    crawl(fetcher, make_entry(enrichment=True))

    assert fetcher.detail_urls == [
        "https://www.sikaegshop.com/api/products/252",
        "https://www.sikaegshop.com/api/products/253",
    ]


def test_a_product_we_refused_to_price_is_never_asked_for_its_detail():
    """Details hang on a product the warehouse knows, and it learns a product
    from its PRICE row. Fetching details for one we refused to price would buy
    a request and get out-of-scope rejects for it at ingest — the rule the woo
    connector already follows."""
    unpriced = {**PRODUCT_253, "price": 0, "specail_price": 0,
                "flash_sale_price": None}
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, unpriced),
                           details={"252": DETAIL_252})

    tables = crawl(fetcher, make_entry(enrichment=True))

    assert fetcher.detail_urls == ["https://www.sikaegshop.com/api/products/252"]
    assert all(r["external_product_id"] == "252" for r in details_of(tables))


def test_a_product_repeated_across_a_page_edge_is_asked_for_ONCE():
    """The catalogue can shift between page requests. The price loop already
    drops the repeat; paying a second request for the same record and filing
    its details twice would be the same defect one layer down."""
    page = list_page(PRODUCT_252, PRODUCT_252)
    fetcher = _StubFetcher(payloads=page, details={"252": DETAIL_252})

    tables = crawl(fetcher, make_entry(enrichment=True))

    assert fetcher.detail_urls == ["https://www.sikaegshop.com/api/products/252"]
    # 31 since 0052 took the trade tier out to a price column of its own.
    assert len(details_of(tables)) == 31


def test_the_technical_specifications_arrive_in_BOTH_languages():
    """The standing bilingual rule. The shop states every attribute twice —
    name_ar/name_en and value_ar/value_en — and keeping only one would drop a
    translation the site publishes, which is a defect, not a simplification.

    The codes are paired `attr_1` / `attr_1_en` because that is the convention
    the panel reads to print one bilingual line per fact.
    """
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = details_of(crawl(fetcher, make_entry(enrichment=True)))
    # The SHOP's own assigned attributes, which all carry an attr_ code.
    # The group no longer isolates them: since the vocabulary closed to
    # five, sku/weight/stock file under Specifications too.
    specs = {r["attribute_code"]: r for r in rows
             if r["attribute_code"].startswith("attr_")}

    # the five attributes the shop assigns to product 252, each in both
    # languages. The codes are the shop's own attribute_ids (1, 2, 4, 5, 6),
    # never positions: a positional code would rename every fact the day the
    # shop reorders one product's list.
    assert set(specs) == {"attr_1", "attr_1_ar", "attr_2", "attr_2_ar",
                          "attr_4", "attr_4_ar", "attr_5", "attr_5_ar",
                          "attr_6", "attr_6_ar"}
    # The code and the `lang` beside it say the SAME thing (0039). Read them
    # together: the unmarked code carries English and declares lang="en".
    assert specs["attr_2_ar"]["attribute_label"] == "اللون"
    assert specs["attr_2_ar"]["raw_value"] == "ابيض"
    assert specs["attr_2_ar"]["lang"] == "ar"
    assert specs["attr_2"]["attribute_label"] == "color"
    assert specs["attr_2"]["raw_value"] == "white"
    assert specs["attr_2"]["lang"] == "en"


def test_the_shops_own_trailing_whitespace_never_reaches_a_value_or_a_label():
    """Live data, not a hypothetical: this shop stores "1 Meter ", "Product
    Attributes " and "Suitable for Application " with the space in them."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = {r["attribute_code"]: r
            for r in details_of(crawl(fetcher, make_entry(enrichment=True)))}

    assert rows["attr_1"]["raw_value"] == "1 Meter"
    assert rows["attr_1"]["attribute_label"] == "consumption Rate Approx."
    assert rows["attr_4"]["attribute_label"] == "Product Attributes"
    assert rows["attr_4"]["raw_value"] == "Polyethylene Foam"
    assert rows["attr_5"]["raw_value"] == "Joint Sealant"


def test_EVERY_image_reaches_the_gallery_not_only_the_primary_one():
    """The list publishes one attachment per product; the detail publishes
    eleven for this one. The panel's gallery showed a single picture where the
    site shows nine."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = details_of(crawl(fetcher, make_entry(enrichment=True)))
    media = [r for r in rows if r["attribute_group"] == "Media"]

    assert len(media) == 9
    # keyed on the shop's own attachment_id, so nine pictures stay nine
    assert {r["attribute_code"] for r in media} == {
        f"image_{n}" for n in range(3105, 3114)}
    assert all(r["value_url"].startswith("https://www.sikaegshop.com/uploads/")
               for r in media)
    # and the list entry alone would have produced exactly one of them
    only_list = details_of(crawl(
        _StubFetcher(payloads=list_page(PRODUCT_252), details={"252": {}}),
        make_entry(enrichment=True)))
    assert len([r for r in only_list if r["attribute_group"] == "Media"]) == 1


def test_a_datasheet_lands_in_Attachments_with_its_real_size_and_absolute_url():
    """The site itself prints "0 Bytes" beside every download — its own bug.
    The API states the true size, and what the API states is what we record."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = details_of(crawl(fetcher, make_entry(enrichment=True)))
    files = [r for r in rows if r["attribute_group"] == "Attachments"]

    assert len(files) == 2                          # English TDS + Arabic TDS
    assert {r["attribute_code"] for r in files} == {"attachment_3114",
                                                    "attachment_3115"}
    english = next(r for r in files if "English" in r["raw_value"])
    assert english["raw_value"] == "Sika Backing Rod® English TDS.pdf"
    assert english["numeric_value"] == "265089"     # not "0 Bytes"
    assert english["unit_raw"] == "bytes"
    assert english["value_url"] == (
        "https://www.sikaegshop.com/uploads/productattachments/"
        "product_temp_1767561409824_4a2fo0kml4y.pdf")
    arabic = next(r for r in files if "Arabic" in r["raw_value"])
    assert arabic["numeric_value"] == "882092"
    # a PDF is not a picture: it must never be handed to the gallery
    assert not any(r["attribute_group"] == "Media" and ".pdf" in r["raw_value"]
                   for r in rows)


def test_two_attachments_the_shop_names_the_same_stay_two_records():
    """Found by running the connector against all 87 live products, 2026-07-25:
    13 of them file TWO `video/url` attachments both called "Video" (different
    YouTube links). Ingest keys an attribute on (product, attribute_code,
    raw_value), so a shared "attachment" code made the second UPSERT over the
    first — one of the two videos gone, and nothing anywhere saying so.

    The shop's own attachment_id is the identity, so the two stay two. The
    exact shape below is product 293's, copied from the live response.
    """
    videos = {**DETAIL_252, "product_attachments": [
        {"attachment_id": 3634, "file_name": "Video", "file_type": "video/url",
         "file_url": "https://www.youtube.com/watch?v=R6Gol26m3oQ",
         "file_size": None, "is_primary": False, "sort_order": 2},
        {"attachment_id": 3635, "file_name": "Video", "file_type": "video/url",
         "file_url": "https://www.youtube.com/watch?v=5LTKZZkKlXs",
         "file_size": None, "is_primary": False, "sort_order": 3},
    ]}
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252), details={"252": videos})

    rows = details_of(crawl(fetcher, make_entry(enrichment=True)))
    files = [r for r in rows if r["attribute_group"] == "Attachments"]

    assert len(files) == 2
    assert {r["attribute_code"] for r in files} == {"attachment_3634",
                                                    "attachment_3635"}
    assert {r["value_url"] for r in files} == {
        "https://www.youtube.com/watch?v=R6Gol26m3oQ",
        "https://www.youtube.com/watch?v=5LTKZZkKlXs"}
    # an off-site absolute url is left alone, never prefixed with the shop
    assert not any(r["value_url"].startswith("https://www.sikaegshop.com/https")
                   for r in files)
    # no size is stated, so no size is invented — and no "bytes" without a number
    assert {r["numeric_value"] for r in files} == {""}
    assert {r["unit_raw"] for r in files} == {""}
    # a video is not a picture: the gallery renders <img>, so it must not go there
    assert not any(r["attribute_group"] == "Media" for r in rows)


def test_the_full_description_arrives_in_both_languages():
    """DESCRIPTION / USES / CHARACTERISTICS — the body of the product page.
    Detail-only; the list carries the one-line short description alone."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = {r["attribute_code"]: r
            for r in details_of(crawl(fetcher, make_entry(enrichment=True)))}

    assert rows["full_description"]["lang"] == "en"
    assert rows["full_description"]["attribute_group"] == "Description"
    assert "CHARACTERISTICS / ADVANTAGES" in rows["full_description"]["raw_value"]
    assert "USES:" in rows["full_description"]["raw_value"]
    assert "الإستعمالات:" in rows["full_description_ar"]["raw_value"]
    assert rows["full_description_ar"]["lang"] == "ar"
    # and the SHORT description still stands beside it, not replaced by it
    assert rows["description"]["raw_value"] == "Backing rod for joint sealing"


def test_the_stock_levels_are_emitted_only_where_the_shop_populates_them():
    """min_stock_level is 10 here (and never 0 or null across the 87 live
    products); max_stock_level is 0, which is the field left unset — 85 of 87
    live products carry that 0. "Maximum stock: 0" would state a limit the shop
    does not impose."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = {r["attribute_code"]: r
            for r in details_of(crawl(fetcher, make_entry(enrichment=True)))}

    assert rows["min_stock_level"]["raw_value"] == "10"
    assert "max_stock_level" not in rows


# ---- the sku, and what the price table owes the detail pass ------------------

def test_the_REAL_sku_reaches_the_price_row_because_only_the_detail_states_it():
    """The owner ruled sika "registers no SKU, take the product id" — true of
    the LIST endpoint, which has no such field on any of the 87 live products,
    and false of the DETAIL, which states one on all 87. Where the shop
    publishes a real sku, that is what we record."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    tables = crawl(fetcher, make_entry(enrichment=True))
    prices = next(t for t in tables if t.kind is PRODUCT_PRICES.kind)
    row = RowView(PRODUCT_PRICES, prices.header).as_dict(prices.rows[0])

    assert row["external_sku"] == "SK1049"       # not the id — the shop's own
    assert row["external_product_id"] == "252"


def test_a_product_the_shop_gives_no_sku_falls_back_to_its_product_id():
    """The owner's approved exception, applied exactly where it applies. Zero of
    the 87 live products need it today; it exists so the column is never blank
    and so the day one arrives is not the day the connector starts guessing."""
    nameless = {k: v for k, v in DETAIL_252.items() if k != "sku"}
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": nameless})

    tables = crawl(fetcher, make_entry(enrichment=True))
    prices = next(t for t in tables if t.kind is PRODUCT_PRICES.kind)
    row = RowView(PRODUCT_PRICES, prices.header).as_dict(prices.rows[0])

    assert row["external_sku"] == "252"
    # and the enrichment bag does NOT invent a "SKU: 252" fact the shop never
    # published — the fallback is an identifier for our table, not a claim
    assert not any(r["attribute_code"] == "sku" for r in details_of(tables))


def test_the_price_table_is_whole_without_the_detail_pass_sku_is_the_fallback():
    """The prices must never depend on an enrichment declaration. A source that
    asks for prices alone gets every priced row; what it forgoes is the shop's
    real sku, and the product id stands in for it (owner's exception)."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252))

    tables = crawl(fetcher, make_entry())
    prices = tables[0]
    row = RowView(PRODUCT_PRICES, prices.header).as_dict(prices.rows[0])

    assert row["external_sku"] == "252"
    assert row["price"] == "10" and row["availability"] == "in_stock"


def test_a_sibling_shop_that_DOES_publish_a_sku_on_its_list_is_believed():
    """This is a FAMILY connector. A sibling whose list carries a sku must not
    be handed the fallback just because sikaegshop's list does not."""
    sibling = {**PRODUCT_252, "sku": "SIB-99"}
    fetcher = _StubFetcher(payloads=list_page(sibling))

    table = crawl(fetcher, make_entry())[0]
    row = RowView(PRODUCT_PRICES, table.header).as_dict(table.rows[0])

    assert row["external_sku"] == "SIB-99"


# ---- the selling unit --------------------------------------------------------

def test_the_selling_unit_is_recorded_only_when_the_name_and_the_weight_AGREE():
    """The owner's rule, shared with madar (normalize.selling_unit_from): the
    site must STATE what one price buys. sika states it in the English name and
    again in `weight`, and the two are compared before anything is written."""
    table, view = fetch_rows(_StubFetcher(total_pages=1))
    by_id = {view.get(r, "external_product_id"): view.as_dict(r) for r in table.rows}

    # "Sika Fume® 5 KG" + weight 5 -> the shop said it twice
    assert (by_id["256"]["unit"], by_id["256"]["basis_quantity"]) == ("kg", "5")
    assert (by_id["257"]["unit"], by_id["257"]["basis_quantity"]) == ("kg", "25")


def test_a_name_that_states_no_kg_quantity_gets_no_invented_unit():
    """"Sika Backing ® Rod 1 CM" weighs 1 kg, but 1 CM is a diameter, not what
    the price buys. A weight alone is the piece's mass and states nothing."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252))
    table = crawl(fetcher, make_entry())[0]
    row = RowView(PRODUCT_PRICES, table.header).as_dict(table.rows[0])

    assert row["unit"] == "" and row["basis_quantity"] == ""


def test_a_name_that_CONTRADICTS_the_weight_states_nothing():
    """Not hypothetical: live product 218 is "Sika Latex®- 20 kg" with weight 5,
    and 4 of the 87 products disagree with themselves this way (2026-07-25).
    Trusting either side alone would publish a basis the shop never stated."""
    contradicting = {**PRODUCT_252, "product_enname": "Sika Latex®- 20 kg",
                     "weight": 5}
    fetcher = _StubFetcher(payloads=list_page(contradicting))

    table = crawl(fetcher, make_entry())[0]
    row = RowView(PRODUCT_PRICES, table.header).as_dict(table.rows[0])

    assert row["unit"] == "" and row["basis_quantity"] == ""


# ---- error paths (T3): one product's detail is never the whole crawl ---------

def test_one_failing_detail_does_not_kill_the_crawl_and_IS_reported():
    """Q3: carrying on is right; carrying on quietly is not. The product keeps
    everything the LIST stated, and the warning names what it lost."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, PRODUCT_253),
                           details={"252": DETAIL_252},
                           fails={"253": RuntimeError("HTTP 503")})

    tables = crawl(fetcher, make_entry(enrichment=True))
    prices = next(t for t in tables if t.kind is PRODUCT_PRICES.kind)
    rows = details_of(tables)

    assert len(prices.rows) == 2                      # both products still priced
    assert any(r["external_product_id"] == "252" and
               r["attribute_group"] == "Specifications" for r in rows)
    # 253's LIST facts survive — its short description and its one image
    kept = {r["attribute_code"] for r in rows if r["external_product_id"] == "253"}
    assert "description" in kept
    assert any(code.startswith("image_") for code in kept)
    assert "full_description" not in kept             # honestly absent, not faked

    assert len(prices.warnings) == 1
    warning = prices.warnings[0]
    assert "253" in warning and "HTTP 503" in warning
    assert "sku" in warning and "full description" in warning


def test_an_unreadable_detail_response_is_reported_not_read_as_no_details():
    """A 200 whose body is not a product is a shape change, and shape changes
    fail loud in this repo (Q4) — never as a product that simply has no details."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": {"unexpected": "shape"}})

    tables = crawl(fetcher, make_entry(enrichment=True))
    prices = next(t for t in tables if t.kind is PRODUCT_PRICES.kind)

    assert len(prices.warnings) == 1
    assert "no product object" in prices.warnings[0]
    assert "unexpected" in prices.warnings[0]         # the shape it did send


def test_a_detail_wrapped_in_the_shops_own_success_data_envelope_is_read():
    """The LIST endpoint answers {success, data...}; a sibling shop in this
    family may wrap the detail the same way. Recognised, not guessed at."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": {"success": True, "data": DETAIL_252}})

    rows = details_of(crawl(fetcher, make_entry(enrichment=True)))

    assert any(r["attribute_code"] == "attr_2" for r in rows)


def test_the_owners_stop_button_is_never_swallowed_by_the_per_product_guard():
    """CrawlInterrupted rides CrawlBlocked exactly so a broad per-item except
    cannot eat it. If this ever passes silently, the Pause button is decorative
    and the crawl runs on for the rest of the catalogue."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, PRODUCT_253),
                           details={"252": DETAIL_252},
                           fails={"253": CrawlInterrupted("pause")})

    with pytest.raises(CrawlBlocked):
        crawl(fetcher, make_entry(enrichment=True))


def test_a_stop_mid_detail_still_hands_over_the_prices_already_read():
    """capture.py journals a table the moment it is yielded. Yielding the price
    table before the interrupt propagates is the difference between a pause at
    product 40 keeping 87 products and losing them."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, PRODUCT_253),
                           details={"252": DETAIL_252},
                           fails={"253": CrawlInterrupted("pause")})
    kept = []

    with pytest.raises(CrawlInterrupted):
        for table in CustomJsonConnector(fetcher).fetch(make_entry(enrichment=True)):
            kept.append(table)

    assert [t.kind for t in kept] == [PRODUCT_PRICES.kind]
    assert len(kept[0].rows) == 2


def test_every_detail_row_survives_the_warehouse_none_overwrites_another():
    """Ingest keys an attribute on (product, attribute_code, raw_value), so a
    connector that repeats a code loses rows at the INSERT and nowhere else —
    silently, and only in the database. Counting them back out is the only
    place that can be caught (T5: the real schema, not a mock)."""
    entry = make_entry(enrichment=True)
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252, PRODUCT_253),
                           details={"252": DETAIL_252})
    tables = crawl(fetcher, entry)
    produced = sum(len(t.rows) for t in tables if t.kind is ENRICHMENT.kind)

    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [t.to_payload() for t in tables])
        stored = conn.execute(
            "SELECT COUNT(*) FROM source_product_attribute").fetchone()[0]
    finally:
        conn.close()

    assert not result.errors and not result.rejected_out_of_scope
    # 252 in full (31); 253's detail answered {} so it falls back to its list
    # entry — 2 descriptions, 2 keyword lines, weight, stock and the one
    # primary image the list publishes. Both lost their trade-tier row in 0052,
    # which moved that number to a price column of its own.
    assert produced == 31 + 7
    assert stored == produced        # nothing collapsed on the way in


def test_the_enrichment_table_carries_the_whole_record_for_one_product():
    """The owner's report, answered field by field: what product 252 produces."""
    fetcher = _StubFetcher(payloads=list_page(PRODUCT_252),
                           details={"252": DETAIL_252})

    rows = details_of(crawl(fetcher, make_entry(enrichment=True)))
    groups: dict[str, int] = {}
    for r in rows:
        groups[r["attribute_group"]] = groups.get(r["attribute_group"], 0) + 1

    # A CLOSED vocabulary for every source (owner ruling 2026-07-26, widened to
    # seven on 2026-07-28). This shop used to file into "Specs" AND
    # "Specifications" — two headings for one question, on one site. Read from
    # the enum rather than retyped: this line went stale the first time the
    # vocabulary grew, which is the exact failure it exists to catch.
    from scrapex.vocab import DetailGroup

    assert set(groups) <= {g.value for g in DetailGroup}
    assert groups == {
        "Description": 4,        # short ar/en + full ar/en
        "Specifications": 11,    # weight + 5 attrs x2
        # This store's handling of the product, not the product itself (0046).
        # The trade tier left for a price column of its own in 0052.
        "Store": 3,              # sku, stock_quantity, min_stock_level
        "Site metadata": 2,      # keywords ar/en — sika's search terms for ITS site
        "Media": 9,              # every photograph
        "Attachments": 2,        # both datasheets
    }
    assert all(r["external_product_id"] == "252" for r in rows)
