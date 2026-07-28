"""Silent data defects, found by fetching live sites rather than trusting tests.

An audit fetched every connector's real endpoint on 2026-07-20 and compared it to
the committed fixture. ALL EIGHT fixtures turned out to be hand-authored rather
than captured, and three connectors were quietly producing wrong data while their
tests were green — because a fabricated fixture can only ever contain the cases
its author already thought of.

A second audit on 2026-07-23 ran each dormant source's own connector against its
live site and found three more, all of the same kind: something the page states
plainly, read and then dropped. Those live captures sit in fixtures/live/.

Each test here reproduces the exact live condition that the fabricated fixture
could not contain.
"""
from __future__ import annotations

import json
from pathlib import Path

from scrapex.connectors.hybris import _money, _storefront_url, _vat_basis
from scrapex.connectors.jsonld import availability_status, category_path
from scrapex.connectors.salla import one_url_per_product
from scrapex.connectors.shopify import was_price

LIVE = Path(__file__).parent / "fixtures" / "live"


def _node(name): return json.loads((LIVE / name).read_text(encoding="utf-8"))


# ---- Shopify: "0.00" is a truthy string --------------------------------------

def test_a_cleared_sale_price_is_not_a_discount_from_zero():
    """44 of 1034 live ELSEWEDYSHOP variants carry compare_at_price "0.00" — a
    shop clears a sale and leaves the field behind rather than nulling it.

    "0.00" is a non-empty string, so `compare_at or price` selected it and the
    sale branch fired. Every crawl published 44 rows reading "on sale, was 0.00":
    a price movement from zero that never happened.
    """
    assert was_price("0.00", "925.00") == ""


def test_a_real_was_price_still_marks_a_sale():
    assert was_price("1450.00", "1200.00") == "1450.00"


def test_a_was_price_at_or_below_the_price_is_not_a_sale():
    """Equal is not a discount, and lower is a stale field, not a markdown."""
    assert was_price("1200.00", "1200.00") == ""
    assert was_price("900.00", "1200.00") == ""


def test_an_absent_or_unparseable_was_price_is_simply_absent():
    assert was_price(None, "1200.00") == ""
    assert was_price("", "1200.00") == ""
    assert was_price("on request", "1200.00") == ""


# ---- Salla: the same product listed once per locale --------------------------

def test_one_product_listed_in_two_languages_is_crawled_once():
    """A Salla sitemap index lists every product once per locale. Deduplicating
    by URL string collapses nothing: alsweed published 2466 URLs for 1233
    products, so every crawl fetched each page twice and emitted two rows with
    the SAME external_product_id."""
    urls = ["https://alsweed.sa/ar/cement/p1506395107",
            "https://alsweed.sa/en/cement/p1506395107",
            "https://alsweed.sa/ar/steel/p698258674"]

    kept = one_url_per_product(urls)

    assert len(kept) == 2
    assert kept == ["https://alsweed.sa/ar/cement/p1506395107",
                    "https://alsweed.sa/ar/steel/p698258674"], \
        "first occurrence must win, so the locale crawled stays predictable"


def test_the_duplication_could_not_have_been_caught_by_the_volume_canary():
    """Worth stating in a test: duplication INFLATES the row count, and
    min_expected_rows only watches for rows going missing. Nothing downstream
    would have reported this."""
    # Real Salla ids are long; the matcher requires 5+ digits on purpose.
    urls = [f"https://alsweed.sa/{loc}/x/p{1500000 + n}"
            for n in range(50) for loc in ("ar", "en")]

    assert len(urls) == 100
    assert len(one_url_per_product(urls)) == 50


def test_a_url_with_no_product_id_is_kept_rather_than_dropped():
    """Unrecognised is not the same as duplicate. Silently dropping it would
    lose a product to a regex that did not match."""
    urls = ["https://alsweed.sa/ar/odd-shape", "https://alsweed.sa/ar/other-shape"]
    assert len(one_url_per_product(urls)) == 2


# ---- Hybris: the VAT flag was inverted ---------------------------------------

def test_the_vat_basis_is_read_from_the_payload_not_the_manifest():
    """masdar's manifest declared vat_mode: excl. Its API returns price ==
    priceWithTax on every product (206.99999999999997 incl vs 180.00 excl,
    exactly 15%), so ~1,354 products were going to be published with an inverted
    VAT flag. Nothing could have caught it: a VAT flag is carried, never checked."""
    product = {"price": {"value": 206.99999999999997},
               "priceWithTax": {"value": 206.99999999999997},
               "priceWithoutTax": {"value": 180.0}}

    assert _vat_basis(product, default="0") == "1", \
        "the payload says the price includes tax and was overruled by the manifest"


def test_a_tax_exclusive_payload_is_reported_as_exclusive():
    product = {"price": {"value": 180.0},
               "priceWithTax": {"value": 207.0},
               "priceWithoutTax": {"value": 180.0}}
    assert _vat_basis(product, default="1") == "0"


def test_the_manifest_still_decides_when_the_api_states_nothing():
    """Falling back is correct — but only where there is genuinely nothing to
    read, never in preference to what the payload says."""
    assert _vat_basis({"price": {"value": 100.0}}, default="1") == "1"
    assert _vat_basis({}, default="0") == "0"


def test_a_binary_float_artefact_is_not_published_as_a_price():
    """OCC serves 206.99999999999997 for a 207.00 price. Publishing that shows a
    number no human sees on the site, and it defeats the price key's
    scale-invariance, which folds 0.620 and 0.62 but not this."""
    assert _money(206.99999999999997) == "207"
    assert _money(57.49999999999999) == "57.5"


def test_rounding_stops_at_two_decimals_and_invents_no_zeros():
    assert _money(320.2865) == "320.29"
    assert _money(25.5) == "25.5", "the shape of the string is not ours to invent"
    assert _money(None) == ""


# ---- SSR families: "out of stock" was being reported as "we don't know" ------

def test_a_product_the_shop_says_it_has_run_out_of_is_not_unknown():
    """Live, alsweed 2026-07-23: p1754450923 publishes
    availability https://schema.org/OutOfStock.

    Both SSR connectors read `"InStock" in availability` and sent everything
    else to `unknown`, so a shop's clear "we don't have this" was stored as
    "the shop said nothing". The vocabulary has always had out_of_stock; no
    connector was writing it.
    """
    node = _node("salla_alsweed_product_node_outofstock_2026-07-23.json")

    assert node["offers"]["availability"] == "https://schema.org/OutOfStock"
    assert availability_status(node["offers"]["availability"]) == "out_of_stock"


def test_in_stock_and_silence_still_mean_what_they_meant():
    assert availability_status("https://schema.org/InStock") == "in_stock"
    assert availability_status("") == "unknown"
    assert availability_status("https://schema.org/PreOrder") == "unknown", \
        "an availability we do not recognise stays unknown rather than guessed"


# ---- Zid: the filing the page states, read and thrown away -------------------

def test_the_category_the_product_page_states_is_kept():
    """Live, advancedcastle 2026-07-23: the JSON-LD the price is read from also
    carries `category`, already in the "A > B" shape category_path uses. The
    connector parsed the node, took the price, and dropped the filing."""
    node = _node("zid_advancedcastle_product_node_category_2026-07-23.json")

    assert node["category"] == "قفل عجلات > مخفض"
    assert category_path(node) == "قفل عجلات > مخفض"


def test_a_category_shape_we_do_not_recognise_yields_nothing_invented():
    assert category_path({}) == ""
    assert category_path({"category": {"@type": "Thing", "name": "Cables"}}) == "Cables"
    assert category_path({"category": ["Cables > LV", "Other"]}) == "Cables > LV"
    assert category_path({"category": 17}) == ""


# ---- Hybris: every product_link was a 404 -------------------------------------

def test_the_masdar_product_url_carries_the_storefront_prefix():
    """Live 2026-07-23: the OCC payload states only
    /electrical-…/p/1000035833, and www.masdaronline.com serves that path as
    404. The storefront files products under /{lang}/{currency}/{sales-unit}/
    — checked against masdaronline's own Product sitemap for all 639 priced
    products, 0 mismatches."""
    product = _node("masdar_hybris_occ_search_ar_2026-07-23.json")["products"][0]

    assert _storefront_url(product, "https://www.masdaronline.com", "ar", "SAR") == (
        "https://www.masdaronline.com/ar/sar/pce/electrical-supplies-and-equipment"
        "/switches-and-sockets/sockets/alfanar-new-alf-switch-1gang-20a-double-pole"
        "-7-7cm-with-neon-ab104/p/1000035833")


def test_a_product_stating_no_sales_unit_keeps_the_plain_join():
    """No unit, no invented prefix — a wrong guess is worse than the old link."""
    assert _storefront_url({"url": "/asmnt/p/1000123"},
                           "https://www.masdaronline.com", "ar", "SAR") == \
        "https://www.masdaronline.com/asmnt/p/1000123"
    assert _storefront_url({}, "https://www.masdaronline.com", "ar", "SAR") == ""
    assert _storefront_url({"url": "https://elsewhere/x"},
                           "https://www.masdaronline.com", "ar", "SAR") == \
        "https://elsewhere/x"
