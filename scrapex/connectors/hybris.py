"""hybris-occ family connector (ENGINEERING.md A3: proven family).

SAP Commerce (Hybris) exposes the OCC v2 REST API. Its data host DIFFERS from the
storefront base_url (masdar: api.masdaronline.com vs www.masdaronline.com), so this
is the first connector to read SourceEntry.api (the OCC host + baseSite id). Product
search is paginated 0-indexed; one product -> one PRODUCT_PRICES row (v1 is
product-level; baseProduct->variant expansion via the product-detail call is a later
enhancement). VAT trap (masdar): the search price is VAT-exclusive on this platform,
recorded via vat_mode=excl; the tax-inclusive priceWithTax needs the detail call.
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable

PAGE_SIZE = 100

# OCC stockLevelStatus -> our vocabulary. lowStock is still purchasable (in_stock).
_STOCK = {
    "inStock": Availability.IN_STOCK.value,
    "lowStock": Availability.IN_STOCK.value,
    "outOfStock": Availability.OUT_OF_STOCK.value,
}


def _availability(stock: dict) -> str:
    return _STOCK.get(stock.get("stockLevelStatus"), Availability.UNKNOWN.value)


def _endpoint(source: SourceEntry) -> str:
    api = source.api
    if api is None or not api.base_url or not api.base_site:
        raise ValueError(
            f"{source.source_key}: hybris-occ needs api.base_url + api.base_site "
            "(the OCC host and baseSite id) in the manifest"
        )
    return f"{api.base_url.rstrip('/')}/rest/v2/{api.base_site}/products/search"


class HybrisOccConnector:
    connector_id = "hybris-occ"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        endpoint = _endpoint(source)
        display_base = source.base_url.rstrip("/")
        vat = "1" if source.vat_mode.value == "incl" else "0"
        currency = source.currency or "UNKNOWN"
        rows: list[list[str]] = []

        page = 0
        while True:
            body = self._fetcher.get(endpoint, params={
                "fields": "FULL", "pageSize": PAGE_SIZE,
                "currentPage": page, "query": ":relevance",
            }).json() or {}
            products = body.get("products") or []
            for product in products:
                row = self._row(builder, product, display_base, currency, vat, source.default_region)
                if row is not None:
                    rows.append(row)
            total_pages = (body.get("pagination") or {}).get("totalPages")
            page += 1
            if not products:
                break
            if total_pages is not None:
                if page >= int(total_pages):
                    break
            elif len(products) < PAGE_SIZE:  # safety net if pagination block is absent
                break

        yield ScrapedTable(
            source_key=source.source_key, kind=PRODUCT_PRICES.kind,
            source_url=endpoint, header=builder.header, rows=rows,
        )

    @staticmethod
    def _row(builder: RowBuilder, product: dict, display_base: str, currency: str, vat: str, region: str):
        price = product.get("price") or {}
        value = price.get("value")
        code = str(product.get("code") or "")
        if value in (None, "") or not code:
            return None  # login-gated / unpriced product — skip, don't emit empty required
        url = product.get("url") or ""
        if url and not url.startswith("http"):
            url = f"{display_base}/{url.lstrip('/')}"
        stock = product.get("stock") or {}
        level = stock.get("stockLevel")
        return builder.row(
            external_product_id=code,
            external_variant_id=code,  # v1 product-level; baseProduct->variants later
            external_sku=code,
            product_name=product.get("name") or "",
            brand_raw=product.get("manufacturer") or "",
            product_url=url,
            region=region,
            currency=price.get("currencyIso") or currency,
            vat_included=vat,
            regular_price=value,
            sale_price="",
            effective_price=value,
            availability=_availability(stock),
            stock_quantity=level if level is not None else "",
        )
