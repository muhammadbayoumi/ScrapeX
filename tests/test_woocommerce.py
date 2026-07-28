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
    assert wire["price"] == "2776.66"  # "277666" minor_unit 2 -> 2776.66
    assert wire["price_before"] == "2985.66"     # on sale
    assert wire["price_sale"] == "2776.66"
    assert wire["currency"] == "EGP" and wire["tax_included"] == "1"
    assert wire["availability"] == "in_stock"

    breaker = view.as_dict(table.rows[1])
    assert breaker["price"] == "125.50" and breaker["price_sale"] == ""
    assert breaker["availability"] == "out_of_stock"


def test_a_variable_products_variations_replace_its_range_low_end():
    """The parent's 450.00 is only the range's low end; the variation's own
    2,776.66 is the price someone actually pays. Emitting both would state the
    same offer twice at two different numbers."""
    fetcher = _StubFetcher()
    table = next(iter(WooCommerceConnector(fetcher).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)

    rows = [view.as_dict(r) for r in table.rows]
    assert not any(r["price"] == "450.00" for r in rows), \
        "the range's low end leaked through as if it were a price"

    variation = rows[0]
    assert variation["external_variant_id"] == "10491"       # its own identity
    assert variation["external_sku"] == "12cc89c502df-2"      # its own sku
    assert variation["variant_ar"] == "Color: أرضي"        # the site's words
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
    assert fallback["price"] == "450.00"           # the low end, kept
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
                zero["prices"].update(price="0", price_before="0", price_sale="")
                return _StubResponse(zero)
            return super().get(url, params=params, **kwargs)

    table = next(iter(WooCommerceConnector(_ZeroPriceFetcher()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    rows = [view.as_dict(r) for r in table.rows]

    assert not any(r["price"] == "0.00" for r in rows), \
        "a zero entered the table as if it were a price"
    fallback = rows[0]
    assert fallback["price"] == "450.00"      # the range low, said out loud
    assert fallback["external_variant_id"] == "10150"
    assert any("low end" in w for w in table.warnings)


# ---------------------------------------------------------------------------
# B1 (2026-07-25): the shape census of samehgabriel's live catalogue is
# 18 products, ALL `type: variable` — no simple, no grouped, no external. Every
# one publishes 6 variations and the connector prices each individually, so
# today's rows are right. What the study also found is that this shop really
# does publish `prices.price_range` (product 9803: min 208978, max 209072), and
# the connector was reading straight past it — so the moment a shape arrives
# that has a range and NO variations to price individually (a grouped or
# external product), the range's low end would be filed as if it were a price.
# ---------------------------------------------------------------------------

LIVE = json.loads((FX / "live" / "samehgabriel_wc_store_products_2026-07-20.json")
                  .read_text(encoding="utf-8"))


def test_the_live_catalogue_is_all_variable_and_the_shop_does_publish_ranges():
    """The premise the two fixes below rest on, asserted against the capture."""
    assert {p.get("type") for p in LIVE} == {"variable"}
    ranged = [p for p in LIVE if (p.get("prices") or {}).get("price_range")]
    assert [p["id"] for p in ranged] == [9803]
    assert ranged[0]["prices"]["price_range"] == {"min_amount": "208978",
                                                  "max_amount": "209072"}


def _grouped_entry(**over):
    """A woo `grouped` product: a range, and no variations to resolve it."""
    product = {
        "id": 7777, "name": "طقم توصيلات", "type": "grouped", "sku": "KIT-7777",
        "permalink": "https://samehgabriel.com/product/kit/",
        "prices": {"price": "208978", "price_before": "208978",
                   "price_sale": "", "currency_code": "EGP",
                   "currency_minor_unit": 2,
                   "price_range": {"min_amount": "208978",
                                   "max_amount": "209072"}},
        "is_in_stock": True, "variations": [], "attributes": [],
        "categories": [], "tags": [], "brands": [],
    }
    product.update(over)
    return product


def test_a_grouped_product_priced_as_a_range_is_skipped_out_loud():
    """`prices.price` on a range-priced product is the LOW END, not a price.

    Writing 2,089.78 for something the shop quotes at 2,089.78–2,090.72 states
    a figure it does not quote. There is no variation to ask instead, so the
    honest answer is to say nothing and say why.
    """
    class _Grouped(_StubFetcher):
        def get(self, url, params=None, **kwargs):
            self.requests_count += 1
            page = (params or {}).get("page", 1)
            return _StubResponse([_grouped_entry()] if page == 1 else [])

    table = next(iter(WooCommerceConnector(_Grouped()).fetch(make_entry())))
    assert table.rows == []
    warning = next(w for w in table.warnings if "RANGE" in w)
    assert "grouped" in warning
    assert "2089.78..2090.72" in warning, "the warning states the span it refused"


def test_a_grouped_product_with_ONE_price_is_still_recorded():
    """A range is the reason to refuse — not the type. A grouped or external
    product the shop quotes at a single figure is a perfectly good row."""
    class _Single(_StubFetcher):
        def get(self, url, params=None, **kwargs):
            self.requests_count += 1
            page = (params or {}).get("page", 1)
            one = _grouped_entry()
            one["prices"].pop("price_range")
            return _StubResponse([one] if page == 1 else [])

    table = next(iter(WooCommerceConnector(_Single()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    assert len(table.rows) == 1
    assert view.as_dict(table.rows[0])["price"] == "2089.78"
    assert not any("RANGE" in w for w in table.warnings)


def test_a_range_priced_product_whose_variations_all_die_is_skipped_not_guessed():
    """The fallback path, held to the same rule. Keeping the parent figure is
    right when the shop states one price; when it states a SPAN, keeping the
    low end is the guess the house rule forbids."""
    ranged = json.loads(json.dumps(FIXTURE))
    ranged[0]["prices"]["price_range"] = {"min_amount": "45000",
                                          "max_amount": "277666"}

    class _AllVariationsDown(_StubFetcher):
        def get(self, url, params=None, **kwargs):
            if "/products/10491" in url:
                self.requests_count += 1
                raise RuntimeError("504 gateway timeout")
            self.requests_count += 1
            page = (params or {}).get("page", 1)
            return _StubResponse(ranged if page == 1 else [])

    table = next(iter(WooCommerceConnector(_AllVariationsDown()).fetch(make_entry())))
    view = RowView(PRODUCT_PRICES, table.header)
    rows = [view.as_dict(r) for r in table.rows]
    assert not any(r["price"] == "450.00" for r in rows), \
        "the range's low end was kept as if the shop quoted it"
    assert [r["external_product_id"] for r in rows] == ["10200"]   # the simple one
    assert any("RANGE" in w and "450.00..2776.66" in w for w in table.warnings)
    assert any("504" in w for w in table.warnings), "the dead variation still reported"


def test_every_live_variation_price_survives_the_new_guard():
    """The regression this change must not cause: the 18 live products are all
    variable and all priced per variation, so the guard must touch none of
    them. Variations are served from the capture's own parent prices."""
    variations = {}
    for product in LIVE:
        for index, ref in enumerate(product.get("variations") or []):
            variations[str(ref["id"])] = {
                "id": ref["id"], "sku": f"{product.get('sku') or ''}-{index}",
                "name": product["name"], "variation": f"Color: {index}",
                "prices": dict(product["prices"], price_range=None),
                "is_in_stock": True, "attributes": [],
            }

    class _Live(_StubFetcher):
        def get(self, url, params=None, **kwargs):
            self.requests_count += 1
            tail = url.rsplit("/", 1)[-1]
            if tail in variations:
                return _StubResponse(variations[tail])
            page = (params or {}).get("page", 1)
            return _StubResponse(LIVE if page == 1 else [])

    table = next(iter(WooCommerceConnector(_Live()).fetch(make_entry())))
    assert len(table.rows) == sum(len(p.get("variations") or []) for p in LIVE)
    assert not any("RANGE" in w for w in table.warnings)
