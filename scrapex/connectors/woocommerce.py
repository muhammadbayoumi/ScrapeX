"""woocommerce-storeapi family connector (ENGINEERING.md A3: proven family).

WooCommerce's Store API (`/wp-json/wc/store/products`) is open JSON, paginated.
Gotcha (handled here): prices are integer strings in MINOR units with a
`currency_minor_unit` (e.g. "1050" + 2 → 10.50). v1 emits one row per product
(product-level price); per-variation prices need extra calls — a later enhancement.
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable

PER_PAGE = 100


def _money(prices: dict, key: str) -> str:
    raw = prices.get(key)
    if raw in (None, ""):
        return ""
    minor = int(prices.get("currency_minor_unit", 2))
    return f"{int(raw) / (10 ** minor):.{minor}f}"


class WooCommerceConnector:
    connector_id = "woocommerce-storeapi"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/wp-json/wc/store/products"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        rows: list[list[str]] = []

        page = 1
        while True:
            products = self._fetcher.get(endpoint, params={"per_page": PER_PAGE, "page": page}).json()
            if not isinstance(products, list) or not products:
                break
            for p in products:
                row = self._row(builder, p, source, vat)
                if row is not None:
                    rows.append(row)
            if len(products) < PER_PAGE:
                break
            page += 1

        yield ScrapedTable(
            source_key=source.source_key, kind=PRODUCT_PRICES.kind,
            source_url=endpoint, header=builder.header, rows=rows,
        )

    @staticmethod
    def _row(builder: RowBuilder, product: dict, source: SourceEntry, vat: str):
        prices = product.get("prices") or {}
        effective = _money(prices, "price")
        if not effective:
            return None  # no price — skip
        regular = _money(prices, "regular_price") or effective
        sale = _money(prices, "sale_price")
        pid = str(product.get("id", ""))
        return builder.row(
            external_product_id=pid,
            external_variant_id=pid,  # v1: product-level; per-variation prices later
            external_sku=product.get("sku") or "",
            product_name=product.get("name") or "",
            product_url=product.get("permalink") or "",
            region=source.default_region,
            currency=prices.get("currency_code") or source.currency or "UNKNOWN",
            vat_included=vat,
            regular_price=regular,
            sale_price=sale if (sale and sale != regular) else "",
            effective_price=effective,
            availability=Availability.IN_STOCK.value if product.get("is_in_stock") else Availability.OUT_OF_STOCK.value,
        )
