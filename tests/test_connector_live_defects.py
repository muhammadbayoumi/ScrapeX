"""Three silent data defects, found by fetching live sites rather than trusting tests.

An audit fetched every connector's real endpoint on 2026-07-20 and compared it to
the committed fixture. ALL EIGHT fixtures turned out to be hand-authored rather
than captured, and three connectors were quietly producing wrong data while their
tests were green — because a fabricated fixture can only ever contain the cases
its author already thought of.

Each test here reproduces the exact live condition that the fabricated fixture
could not contain.
"""
from __future__ import annotations

from scrapex.connectors.hybris import _money, _vat_basis
from scrapex.connectors.salla import one_url_per_product
from scrapex.connectors.shopify import was_price


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
