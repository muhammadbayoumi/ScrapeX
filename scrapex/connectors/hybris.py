"""hybris-occ family connector (ENGINEERING.md A3: proven family).

SAP Commerce (Hybris) exposes the OCC v2 REST API. Its data host DIFFERS from the
storefront base_url (masdar: api.masdaronline.com vs www.masdaronline.com), so this
is the first connector to read SourceEntry.api (the OCC host + baseSite id). Product
search is paginated 0-indexed; one product -> one PRODUCT_PRICES row (v1 is
product-level; baseProduct->variant expansion via the product-detail call is a later
enhancement).

VAT (masdar) — CORRECTED 2026-07-20 by reading the live API. This file used to
claim the search price was VAT-exclusive and that priceWithTax needed a separate
detail call. Both are false: a FULL search response carries price, priceWithTax
and priceWithoutTax together, and price.value equals priceWithTax.value on every
live product (206.99999999999997 inclusive against 180.00 exclusive — exactly
15%). The manifest said excl, so every MASDAR row would have been published with
its VAT flag inverted. The basis is now read FROM THE PAYLOAD rather than taken
on the manifest's word, because the payload cannot be wrong about itself.
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


def _vat_basis(product: dict, default: str) -> str:
    """'1' when the price we take includes tax, '0' when it does not.

    Decided from the payload wherever the API states both figures, and only
    falling back to the manifest's claim when it does not. The manifest declared
    masdar exclusive while its API returns price == priceWithTax on every
    product — a flag inverted on ~1,354 products, and nothing in the pipeline
    could have noticed, because a VAT flag is carried, never checked.
    """
    value = (product.get("price") or {}).get("value")
    with_tax = (product.get("priceWithTax") or {}).get("value")
    without_tax = (product.get("priceWithoutTax") or {}).get("value")
    try:
        if value is not None and with_tax is not None and float(value) == float(with_tax):
            return "1"
        if value is not None and without_tax is not None and float(value) == float(without_tax):
            return "0"
    except (TypeError, ValueError):
        pass
    return default


def _money(value) -> str:
    """A price as the site means it, not as binary floating point renders it.

    OCC serves 206.99999999999997 for a 207.00 price. Passing that straight
    through publishes a number no human sees on the site, and it defeats the
    price-key's scale-invariance, which folds 0.620 and 0.62 but not this.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    # Minimal representation: 206.99999999999997 -> "207", 25.5 -> "25.5",
    # 320.2865 -> "320.29". Trailing zeros are not added, because the shape of
    # the string is not ours to invent — only the binary artefact is ours to remove.
    return f"{round(number, 2):.2f}".rstrip("0").rstrip(".")


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
        # The payload knows whether its own price includes tax; the manifest only
        # claims to. Where the API states both, believe the API — the manifest
        # said 'excl' for a price that equals priceWithTax exactly.
        vat_flag = _vat_basis(product, default=vat)
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
            vat_included=vat_flag,
            regular_price=_money(value),
            sale_price="",
            effective_price=_money(value),
            availability=_availability(stock),
            stock_quantity=level if level is not None else "",
        )
