"""Task #38 said "images captured by every connector". Four sources stored none.

The four were NOT one bug wearing four hats — each is checked here against what
its own site actually publishes (`fixtures/live/images_2026-07-30.CAPTURE.md`):

  MADAR         the site publishes a placeholder for 184 products, and the
                connector was right to refuse it. What it got wrong was filing
                the main picture TWICE, as `image` and again as `image_1`.
  ALSWEED       the connector reads the JSON-LD image; the MANIFEST never
                declared enrichment, so those rows were never built.
  ELSEWEDYSHOP  the pictures are in the payload the price came from and the
                connector read straight past them.
  MASDAR        same, plus relative URLs and one picture published three times
                over, once per rendering size.
"""
from __future__ import annotations

import json
from pathlib import Path

from scrapex.config import MANIFEST_FILE, ExtractSpec, SourceEntry, load_manifest
from scrapex.connectors.hybris import HybrisOccConnector
from scrapex.connectors.hybris import enrichment_rows as hybris_images
from scrapex.connectors.jsonld import parse_product_jsonld
# Shared by salla AND zid since 00c81a2 — the third argument is the product id,
# not the page URL, because the id is the one thing the two families disagree
# about. Imported from its real home so a future move is a visible test change.
from scrapex.connectors.jsonld import enrichment_rows as jsonld_images
from scrapex.connectors.magento import _enrichment_rows as magento_rows
from scrapex.connectors.salla import _salla_id
from scrapex.connectors.shopify import ShopifyConnector
from scrapex.connectors.shopify import enrichment_rows as shopify_images
from scrapex.rowspec import ENRICHMENT, RowBuilder, RowView
from scrapex.vocab import DetailGroup, ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"
LIVE = FX / "live"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def shaped(rows) -> list[dict]:
    view = RowView(ENRICHMENT, RowBuilder(ENRICHMENT).header)
    return [view.as_dict(r) for r in rows]


def pictures(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["attribute_code"].startswith("image")]


# --------------------------------------------------------------------------
# MADAR — the placeholder is honest; the duplicate was not
# --------------------------------------------------------------------------
MADAR_MAIN = "https://www.madar.com/media/catalog/product/cache/x/g/main.jpg"
MADAR_SECOND = "https://www.madar.com/media/catalog/product/cache/x/g/second.jpg"
MADAR_PLACEHOLDER = ("https://www.madar.com/media/catalog/product/placeholder"
                     "/default/placeholder_4.png")


def madar_pictures(product: dict) -> list[dict]:
    """The image rows madar's enrichment builder makes for one product."""
    return pictures(shaped(magento_rows(RowBuilder(ENRICHMENT), product, {})))


def test_madar_files_the_main_picture_once_not_under_two_codes():
    """`image` repeats media_gallery[0] on 575 of 577 live products.

    Filing both put ONE picture in the warehouse twice, for 576 products.
    """
    rows = madar_pictures({
        "uid": "p1",
        "image": {"url": MADAR_MAIN, "label": "main"},
        "media_gallery": [{"url": MADAR_MAIN, "label": "main", "position": 1},
                          {"url": MADAR_SECOND, "label": "second", "position": 2}],
    })

    assert [r["attribute_code"] for r in rows] == ["image", "image_1"]
    assert [r["value_url"] for r in rows] == [MADAR_MAIN, MADAR_SECOND]
    assert len({r["value_url"] for r in rows}) == len(rows), "one URL, one code"


def test_madar_numbers_the_pictures_it_keeps_not_the_ones_it_skipped():
    """A placeholder main + a real gallery used to start at `image_1`.

    The position came from enumerate() BEFORE the skip, so that product
    published no `image` at all — 577 products carry image_1 in the warehouse
    against 576 carrying image.
    """
    rows = madar_pictures({
        "uid": "p2",
        "image": {"url": MADAR_PLACEHOLDER, "label": "placeholder"},
        "media_gallery": [{"url": MADAR_MAIN, "position": 1},
                          {"url": MADAR_SECOND, "position": 2}],
    })

    assert [r["attribute_code"] for r in rows] == ["image", "image_1"]
    assert rows[0]["value_url"] == MADAR_MAIN


def test_madar_still_refuses_the_placeholder_because_the_site_means_no_image():
    """184 live products publish ONLY this URL. A grey box is not a picture."""
    rows = madar_pictures({"uid": "p3",
                           "image": {"url": MADAR_PLACEHOLDER},
                           "media_gallery": []})

    assert rows == [], "the site says 'no image'; the column stays honestly empty"


# --------------------------------------------------------------------------
# ALSWEED — the connector could read it all along; the manifest never asked
# --------------------------------------------------------------------------
def test_alsweed_declares_enrichment_so_the_image_rows_get_built():
    """salla.py only calls enrichment_rows when the SOURCE declares the kind,
    and ingest refuses an enrichment payload from a source that does not."""
    entry = load_manifest(MANIFEST_FILE).get("ALSWEED")

    assert any(spec.kind == ExtractKind.ENRICHMENT for spec in entry.extract), \
        "1,203 products landed with no picture because nothing asked for one"


# Families whose connector BUILDS image rows today. A source on one of these
# that does not declare enrichment silently publishes no pictures — the
# connector never builds the rows, and ingest.py:789 would refuse them anyway.
#
# This list is the durable half of the ELBUROJ lesson. ALSWEED was fixed as a
# ONE-SOURCE manifest line, and ELBUROJ — the same family, same connector, same
# JSON-LD image — was left behind and completed its first crawl publishing
# 1,200 products with no pictures. A per-source assertion could not catch that;
# a per-FAMILY one does. Add a family here the moment its connector learns to
# capture images, and this test will name every source still missing the line.
IMAGE_CAPABLE_FAMILIES = {
    "magento-graphql",        # magento.py
    "salla-html",             # salla.py
    "shopify-json",           # shopify.py
    "hybris-occ",             # hybris.py
    "custom-json-api",        # custom_json.py
    "woocommerce-storeapi",   # woocommerce.py
    # zid.py gained its image path in 00c81a2 (ADVANCEDCASTLE, 0/168 -> 168/168),
    # which also moved salla's reader into jsonld.py for the two SSR families to
    # share. Added here on merging that work, because a family whose connector
    # can capture images and is NOT listed is a family this guard silently stops
    # watching — the exact failure mode that let ELBUROJ through.
    "zid-html",               # zid.py, via jsonld.py
}


def test_every_source_whose_connector_can_capture_images_asks_for_them():
    """The test that would have caught ELBUROJ before it crawled for an hour."""
    missing = [
        entry.source_key
        for entry in load_manifest(MANIFEST_FILE).sources
        if entry.family.value in IMAGE_CAPABLE_FAMILIES
        and not any(spec.kind == ExtractKind.ENRICHMENT for spec in entry.extract)
    ]

    assert missing == [], (
        "these sources run a connector that CAN capture images but never ask "
        f"for enrichment, so they store none: {missing}")


def test_both_salla_sources_declare_it_not_just_the_one_we_noticed():
    """ELBUROJ is the same family, connector and page shape as ALSWEED."""
    salla = [e for e in load_manifest(MANIFEST_FILE).sources
             if e.family.value == "salla-html"]
    assert {e.source_key for e in salla} >= {"ALSWEED", "ELBUROJ"}

    for entry in salla:
        assert any(spec.kind == ExtractKind.ENRICHMENT for spec in entry.extract), \
            f"{entry.source_key} publishes images and never asks for them"


def test_elburoj_page_publishes_an_image_the_connector_already_reads():
    """Proven from the captured page — no request was made to elburoj, which
    was mid-crawl. The connector code needs no change; the manifest did."""
    url = "https://elburoj.com/ar/x/p543555922"
    html = (LIVE / "salla_elburoj_product_priced_p543555922.html").read_text(
        encoding="utf-8")
    node = parse_product_jsonld(html)

    rows = pictures(shaped(jsonld_images(
        RowBuilder(ENRICHMENT), node, _salla_id(url, node))))

    assert [r["attribute_code"] for r in rows] == ["image"]
    assert rows[0]["value_url"].startswith("https://cdn.salla.sa/")
    assert rows[0]["attribute_group"] == DetailGroup.MEDIA.value
    assert rows[0]["external_product_id"] == "543555922"


def test_alsweed_page_json_ld_yields_the_picture_the_site_publishes():
    """15/15 sampled live products publish exactly one image. Same shape here.

    Read from the captured PAGE through the shared parser, so this exercises
    the path the crawl actually takes rather than a hand-picked node.
    """
    url = "https://alsweed.sa/ar/x/p698258674"
    html = (LIVE / "salla_alsweed_product_priced_p698258674.html").read_text(
        encoding="utf-8")
    node = parse_product_jsonld(html)

    rows = pictures(shaped(jsonld_images(
        RowBuilder(ENRICHMENT), node, _salla_id(url, node))))

    assert [r["attribute_code"] for r in rows] == ["image"]
    assert rows[0]["value_url"] == node["image"]
    assert rows[0]["value_url"].startswith("https://cdn.salla.sa/")
    assert rows[0]["attribute_group"] == DetailGroup.MEDIA.value
    # The id is salla's numeric /p{id}, not the URL — the argument that
    # changed when this reader moved into jsonld.py for zid to share.
    assert rows[0]["external_product_id"] == "698258674"


# --------------------------------------------------------------------------
# ELSEWEDYSHOP — the pictures rode the price payload and were read past
# --------------------------------------------------------------------------
SHOPIFY_FIXTURE = LIVE / "elsewedyshop_products_images_2026-07-30.json"


def test_elsewedyshop_keeps_every_picture_in_the_shops_own_order():
    """932/932 live products publish one; this one publishes seven."""
    products = _json(SHOPIFY_FIXTURE)["products"]
    gallery = max(products, key=lambda p: len(p["images"]))
    assert len(gallery["images"]) > 1, "fixture must exercise the ordering"

    rows = pictures(shaped(shopify_images(RowBuilder(ENRICHMENT), gallery)))

    assert [r["attribute_code"] for r in rows] == \
        ["image"] + [f"image_{n}" for n in range(1, len(gallery["images"]))]
    assert [r["value_url"] for r in rows] == [i["src"] for i in gallery["images"]]
    assert all(r["external_product_id"] == str(gallery["id"]) for r in rows)
    assert all(r["attribute_group"] == DetailGroup.MEDIA.value for r in rows)


def test_elsewedyshop_labels_the_picture_without_touching_its_url():
    """Shopify states no alt (1,442 of 1,442 null), so the filename stands in —
    and the `?v=` cache-buster is dropped from the LABEL only."""
    product = _json(SHOPIFY_FIXTURE)["products"][0]
    rows = pictures(shaped(shopify_images(RowBuilder(ENRICHMENT), product)))

    assert "?" not in rows[0]["raw_value"]
    assert rows[0]["value_url"] == product["images"][0]["src"], "URL verbatim"


def test_elsewedyshop_connector_emits_the_enrichment_table():
    """The rows are worth nothing if fetch() never yields them."""
    payload = _json(SHOPIFY_FIXTURE)

    class _Resp:
        def __init__(self, body): self._body = body
        def json(self): return self._body

    class _Fetcher:
        def get(self, url, **kwargs):
            return _Resp(payload if "page=1" in url and "/en/" not in url
                         else {"products": []})

    entry = SourceEntry.model_validate(dict(
        source_key="ELSEWEDYSHOP", source_name="Elsewedy",
        base_url="https://elsewedyshop.com", family="shopify-json",
        currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT,
                             scope=ExtractScope.CENSUS)]))

    tables = list(ShopifyConnector(_Fetcher()).fetch(entry))
    enrichment = [t for t in tables if t.kind == ExtractKind.ENRICHMENT]

    assert len(enrichment) == 1, "the source declares enrichment and gets none"
    published = sum(len(p["images"]) for p in payload["products"])
    assert len(enrichment[0].rows) == published


def test_elsewedyshop_stays_silent_when_the_manifest_does_not_ask():
    """A source that declares only prices must not be sent enrichment —
    ingest refuses the payload outright."""
    payload = _json(SHOPIFY_FIXTURE)

    class _Resp:
        def __init__(self, body): self._body = body
        def json(self): return self._body

    class _Fetcher:
        def get(self, url, **kwargs):
            return _Resp(payload if "page=1" in url and "/en/" not in url
                         else {"products": []})

    entry = SourceEntry.model_validate(dict(
        source_key="ELSEWEDYSHOP", source_name="Elsewedy",
        base_url="https://elsewedyshop.com", family="shopify-json",
        currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS)]))

    tables = list(ShopifyConnector(_Fetcher()).fetch(entry))

    assert not [t for t in tables if t.kind == ExtractKind.ENRICHMENT]


# --------------------------------------------------------------------------
# MASDAR — relative URLs, and one picture published three times over
# --------------------------------------------------------------------------
MASDAR_FIXTURE = LIVE / "masdar_hybris_occ_images_2026-07-30.json"
API_HOST = "https://api.masdaronline.com"


def masdar_products() -> list[dict]:
    return _json(MASDAR_FIXTURE)["products"]


def test_masdar_stores_one_row_per_picture_not_one_per_rendering_size():
    """Every imaged product publishes ONE picture as thumbnail+product+zoom.

    Three rows would assert three pictures — a claim the site never made.
    """
    product = next(p for p in masdar_products() if p.get("images"))
    assert len(product["images"]) == 3, "fixture must carry all three renderings"

    rows = pictures(shaped(hybris_images(
        RowBuilder(ENRICHMENT), product, API_HOST)))

    assert [r["attribute_code"] for r in rows] == ["image"]


def test_masdar_keeps_the_largest_rendering_the_site_offers():
    """Chosen by the site's own `format` name, not by a size parsed out of a URL."""
    product = next(p for p in masdar_products() if p.get("images"))
    zoom = next(i for i in product["images"] if i["format"] == "zoom")

    rows = pictures(shaped(hybris_images(
        RowBuilder(ENRICHMENT), product, API_HOST)))

    assert rows[0]["value_url"] == API_HOST + zoom["url"]


def test_masdar_resolves_relative_urls_against_the_host_that_serves_them():
    """HEAD 2026-07-30: api host -> 200 image/jpeg, storefront -> 404."""
    product = next(p for p in masdar_products() if p.get("images"))

    rows = pictures(shaped(hybris_images(
        RowBuilder(ENRICHMENT), product, API_HOST)))

    assert rows[0]["value_url"].startswith(f"{API_HOST}/medias/")
    assert "www.masdaronline.com" not in rows[0]["value_url"]
    # Everything after the host is the site's, passed through untouched.
    assert rows[0]["value_url"].endswith(
        next(i["url"] for i in product["images"] if i["format"] == "zoom"))


def test_masdar_product_that_publishes_no_image_stays_honestly_blank():
    """80 of 640 priced products publish `images: []`. No placeholder invented."""
    bare = next(p for p in masdar_products() if not p.get("images"))
    assert (bare.get("price") or {}).get("value") not in (None, ""), \
        "the imageless product must still be a priced one"

    rows = hybris_images(RowBuilder(ENRICHMENT), bare, API_HOST)

    assert rows == []


def test_masdar_connector_emits_enrichment_beside_the_prices_on_one_token():
    """A resume must not land a page's prices without its pictures."""
    payload = _json(MASDAR_FIXTURE)

    class _Resp:
        def __init__(self, body): self._body = body
        def json(self): return self._body

    class _Fetcher:
        def get(self, url, params=None, **kwargs):
            if url.endswith("/languages"):
                return _Resp({"languages": [{"isocode": "ar", "active": True}]})
            page = int((params or {}).get("currentPage", 0))
            return _Resp(payload if page == 0 else {"products": []})

    entry = SourceEntry.model_validate(dict(
        source_key="MASDAR", source_name="مصدر",
        base_url="https://www.masdaronline.com", family="hybris-occ",
        currency="SAR", default_region="SA", vat_mode="incl",
        api={"base_url": API_HOST, "base_site": "masdar"},
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT,
                             scope=ExtractScope.CENSUS)]))

    tables = list(HybrisOccConnector(_Fetcher()).fetch(entry))
    prices = [t for t in tables if t.kind == ExtractKind.PRODUCT_PRICES and t.rows]
    enrichment = [t for t in tables if t.kind == ExtractKind.ENRICHMENT]

    assert len(enrichment) == 1
    assert enrichment[0].page_token == prices[0].page_token
    imaged = [p for p in payload["products"] if p.get("images")]
    assert len(enrichment[0].rows) == len(imaged)


def test_masdar_declares_enrichment_in_the_manifest():
    entry = load_manifest(MANIFEST_FILE).get("MASDAR")

    assert any(spec.kind == ExtractKind.ENRICHMENT for spec in entry.extract)


def test_elsewedyshop_declares_enrichment_in_the_manifest():
    entry = load_manifest(MANIFEST_FILE).get("ELSEWEDYSHOP")

    assert any(spec.kind == ExtractKind.ENRICHMENT for spec in entry.extract)
