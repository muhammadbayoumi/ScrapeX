"""custom-json-api family connector (ENGINEERING.md A3: proven family).

sikaegshop is a custom Next.js shop exposing an open, unauthenticated
GET /api/products that returns the full catalog in one response (~87 products,
Arabic + English names). One product -> one PRODUCT_PRICES row.

PRICE SEMANTICS — owner verifies ONCE before activating (source stays inactive):
`price` is the list price; `specail_price` (the store's own spelling) is the
discounted price when it is a positive number below `price`; `flash_sale` is
treated as a boolean flag, NOT a price. If verification shows flash_sale carries
its own price number, that is the single line to adjust — `_prices()`.
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable


def _num(value) -> float | None:
    """A positive number, or None (0 / null / non-numeric all mean 'no price')."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _fmt(n: float | None) -> str:
    if n is None:
        return ""
    return str(int(n)) if float(n).is_integer() else str(n)


def _prices(product: dict) -> tuple[str, str, str]:
    """(regular, sale, effective) as strings — see PRICE SEMANTICS in the docstring."""
    regular = _num(product.get("price"))
    special = _num(product.get("specail_price"))
    if regular is None:               # a special alone can still be the effective price
        regular = special
    on_sale = special is not None and (regular is None or special < regular)
    effective = special if on_sale else regular
    if effective is None:
        return "", "", ""
    sale = effective if (regular is not None and effective < regular) else None
    return _fmt(regular), _fmt(sale), _fmt(effective)


def _availability(product: dict) -> str:
    flag = product.get("in_stock")
    if isinstance(flag, bool):
        return Availability.IN_STOCK.value if flag else Availability.OUT_OF_STOCK.value
    qty = product.get("stock", product.get("quantity"))
    if isinstance(qty, (int, float)):
        return Availability.IN_STOCK.value if qty > 0 else Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value


class CustomJsonConnector:
    connector_id = "custom-json-api"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/api/products"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        currency = source.currency or "UNKNOWN"

        data = self._fetcher.get(endpoint).json()
        products = data.get("products") if isinstance(data, dict) else data  # dict{products} or bare list
        rows: list[list[str]] = []
        for product in (products or []):
            row = self._row(builder, product, base, currency, vat, source.default_region)
            if row is not None:
                rows.append(row)

        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, endpoint, builder.header, rows)

    @staticmethod
    def _row(builder: RowBuilder, product: dict, base: str, currency: str, vat: str, region: str):
        regular, sale, effective = _prices(product)
        pid = str(product.get("id") or product.get("sku") or "")
        if not effective or not pid:
            return None  # unpriced or unidentifiable — skip, don't emit empty required
        slug = product.get("slug") or ""
        url = product.get("url") or (f"{base}/product/{slug}" if slug else "")
        if url and not url.startswith("http"):
            url = f"{base}/{url.lstrip('/')}"
        name = product.get("name_ar") or product.get("name") or product.get("name_en") or ""
        return builder.row(
            external_product_id=pid, external_variant_id=pid,
            external_sku=str(product.get("sku") or ""), product_name=str(name),
            brand_raw=str(product.get("brand") or ""), product_url=url,
            region=region, currency=currency, vat_included=vat,
            regular_price=regular, sale_price=sale, effective_price=effective,
            availability=_availability(product),
        )
