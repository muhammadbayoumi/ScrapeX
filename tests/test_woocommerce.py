"""T2: woocommerce-storeapi connector — minor units, per-variation prices, mapping.

The variation payload shape (type/variation/prices/attributes:[]) mirrors a LIVE
capture from samehgabriel.com on 2026-07-22 — where the parent listed 450.00
while its variation actually sells at 2,776.66. A fabricated shape here would
prove nothing (the GPP lesson).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.woocommerce import WooCommerceConnector
from scrapex.ingest import ingest_payloads
from scrapex.normalize import option_fingerprint
from scrapex.rowspec import PRODUCT_PRICES, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"
FIXTURE = json.loads((FX / "woocommerce_products.json").read_text(encoding="utf-8"))
VARIATION = json.loads((FX / "woocommerce_variation_10491.json").read_text(encoding="utf-8"))


class _StubResponse:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _StubFetcher:
    def __init__(self): self.requests_count = 0
    def get(self, url, params=None, **kwargs):
        self.requests_count += 1
        if url.endswith("/products/10491"):
            return _StubResponse(VARIATION)
        page = (params or {}).get("page", 1)
        return _StubResponse(FIXTURE if page == 1 else [])
    def close(self): pass


class _VariationDownFetcher(_StubFetcher):
    def get(self, url, params=None, **kwargs):
        if url.endswith("/products/10491"):
            self.requests_count += 1
            raise RuntimeError("504 gateway timeout")
        return super().get(url, params=params, **kwargs)


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SAMEHGABRIEL", source_name="سامح جبرائيل", base_url="https://samehgabriel.com",
        family="woocommerce-storeapi", currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def test_woo_converts_minor_units_and_maps():
    table = next(iter(WooCommerceConnector(_StubFetcher()).fetch(make_entry())))
    assert len(table.rows) == 2          # 1 variation (replacing its parent) + 1 simple
    view = RowView(PRODUCT_PRICES, table.header)

    wire = view.as_dict(table.rows[0])
    assert wire["external_product_id"] == "10150"
    assert wire["effective_price"] == "2776.66"  # "277666" minor_unit 2 -> 2776.66
    assert wire["regular_price"] == "2985.66"     # on sale
    assert wire["sale_price"] == "2776.66"
    assert wire["currency"] == "EGP" and wire["vat_included"] == "1"
    assert wire["availability"] == "in_stock"

    breaker = view.as_dict(table.rows[1])
    assert breaker["effective_price"] == "125.50" and breaker["sale_price"] == ""
    assert breaker["availability"] == "out_of_stock"


def test_a_variable_products_variations_replace_its_range_low_end():
    """The parent's 450.00 is only the range's low end; the variation's own
    2,776.66 is the price someone actually pays. Emitting both would state the
    same offer twice at two different numbers."""
    fetcher = _StubFetcher()
    table = next(iter(WooCommerceConnector(fetcher).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    rows = [view.as_dict(r) for r in table.rows]
    assert not any(r["effective_price"] == "450.00" for r in rows), \
        "the range's low end leaked through as if it were a price"

    variation = rows[0]
    assert variation["external_variant_id"] == "10491"       # its own identity
    assert variation["external_sku"] == "12cc89c502df-2"      # its own sku
    assert variation["option_label"] == "Color: أرضي"        # the site's words
    assert variation["option_fingerprint"] == option_fingerprint({"Color": "أرضي"})
    # brand/basis attributes arrive empty on variations (verified live) — the
    # parent is the carrier, so nothing is lost by reading them from it.
    assert fetcher.requests_count == 2   # the list page + ONE variation call


def test_a_dead_variation_keeps_the_parent_price_and_says_so():
    """One variation endpoint down must not erase the product from the table —
    but the fallback is the range's low end, and that must be said, not
    slipped in as if it were the real price."""
    table = next(iter(WooCommerceConnector(_VariationDownFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    rows = [view.as_dict(r) for r in table.rows]
    assert len(rows) == 2
    fallback = rows[0]
    assert fallback["effective_price"] == "450.00"           # the low end, kept
    assert fallback["external_variant_id"] == "10150"        # product-level identity
    assert any("low end" in w for w in table.warnings)
    assert any("504" in w for w in table.warnings)


def test_woo_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(WooCommerceConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
    finally:
        conn.close()
    assert result.observations == 2 and not result.errors
    assert result.products == 2 and result.variants == 2


def test_a_variation_answering_price_zero_is_not_a_price():
    """WooCommerce represents an unpriced variation two ways — null AND "0".
    A 0.00 row would replace the real range-low fallback, poison Min, and
    silently skip the say-it-out-loud path (adversarial review, reproduced
    by execution)."""
    class _ZeroPriceFetcher(_StubFetcher):
        def get(self, url, params=None, **kwargs):
            if url.endswith("/products/10491"):
                self.requests_count += 1
                zero = json.loads(json.dumps(VARIATION))
                zero["prices"].update(price="0", regular_price="0", sale_price="")
                return _StubResponse(zero)
            return super().get(url, params=params, **kwargs)

    table = next(iter(WooCommerceConnector(_ZeroPriceFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    rows = [view.as_dict(r) for r in table.rows]

    assert not any(r["effective_price"] == "0.00" for r in rows), \
        "a zero entered the table as if it were a price"
    fallback = rows[0]
    assert fallback["effective_price"] == "450.00"      # the range low, said out loud
    assert fallback["external_variant_id"] == "10150"
    assert any("low end" in w for w in table.warnings)
