"""shopify-json family connector (ENGINEERING.md A3: proven family).

Every Shopify storefront exposes /products.json — paginated, structured
products + variants + prices. One variant -> one product_prices row, built
against the canonical RowSpec (never hardcoded column order, Q2).
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_fingerprint
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable

PAGE_SIZE = 250  # Shopify hard max per page


class ShopifyConnector:
    connector_id = "shopify-json"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        rows: list[list[str]] = []
        base = source.base_url.rstrip("/")
        vat_flag = "1" if source.vat_mode.value == "incl" else "0"
        currency = source.currency or "UNKNOWN"

        page = 1
        while True:
            url = f"{base}/products.json?limit={PAGE_SIZE}&page={page}"
            products = self._fetcher.get(url).json().get("products", [])
            if not products:  # explicit stop: empty page ends pagination (Q4)
                break
            for product in products:
                rows.extend(self._product_rows(builder, product, base, currency, vat_flag, source.default_region))
            if len(products) < PAGE_SIZE:
                break
            page += 1

        yield ScrapedTable(
            source_key=source.source_key,
            kind=PRODUCT_PRICES.kind,
            source_url=f"{base}/products.json",
            header=builder.header,
            rows=rows,
        )

    @staticmethod
    def _product_rows(builder, product, base, currency, vat_flag, region) -> list[list[str]]:
        option_names = [opt.get("name", f"option{i}") for i, opt in enumerate(product.get("options", []), start=1)]
        handle = product.get("handle", "")
        rows = []
        for variant in product.get("variants", []):
            options = {}
            for i, name in enumerate(option_names, start=1):
                value = variant.get(f"option{i}")
                if value and value != "Default Title":
                    options[name] = value
            price = variant.get("price")
            compare_at = was_price(variant.get("compare_at_price"), price)
            rows.append(builder.row(
                external_product_id=product.get("id"),
                external_variant_id=variant.get("id"),
                external_sku=variant.get("sku") or "",
                product_name=product.get("title") or "",
                brand_raw=product.get("vendor") or "",
                option_label=variant.get("title") if options else "",
                option_fingerprint=option_fingerprint(options) if options else "",
                product_url=f"{base}/products/{handle}" if handle else "",
                region=region,
                currency=currency,
                vat_included=vat_flag,
                regular_price=compare_at or price,
                sale_price=price if compare_at else "",
                effective_price=price,
                availability=_availability(variant),
                stock_quantity="",
            ))
        return rows


def was_price(compare_at, price) -> str:
    """The genuine "was" price, or "" when the variant is not on sale.

    Shopify writes compare_at_price as a STRING, and a shop that has cleared a
    sale often leaves "0.00" behind rather than null. "0.00" is a non-empty
    string, so the previous `compare_at or price` selected it and the sale
    branch fired: 44 of 1034 live ELSEWEDYSHOP variants were being published as
    "on sale, was 0.00" — a price movement from zero that never happened.

    A "was" price is only real when it is strictly ABOVE what is being charged;
    equal or lower is not a discount, it is noise or a stale field.
    """
    try:
        was = float(str(compare_at).strip())
        now = float(str(price).strip())
    except (TypeError, ValueError):
        return ""
    return str(compare_at) if was > now else ""


def _availability(variant: dict) -> str:
    available = variant.get("available")
    if available is True:
        return Availability.IN_STOCK.value
    if available is False:
        return Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value
