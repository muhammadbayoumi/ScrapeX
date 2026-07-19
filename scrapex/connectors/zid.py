"""zid-html family connector (ENGINEERING.md A3: proven family).

Zid stores (advancedcastle) are server-rendered with schema.org Product JSON-LD,
enumerated from the sitemap — the SAME shape as Salla, so both share
connectors/jsonld.py. Two Zid-specifics: the store 403s non-browser clients, so
the source carries a Chrome `user_agent` the fetcher honors; and product ids are
slugs/UUIDs in /products/ URLs (no numeric /p{id}). v1 takes the product-level
JSON-LD price; per-variant prices live in the page HTML (a later enhancement).
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable
from .jsonld import brand_name, offer_price, parse_product_jsonld, sitemap_locs

_PRODUCT_PATH = "/products/"


def _product_id(url: str, node: dict) -> str:
    """Zid ids are the JSON-LD sku/productID when present, else the URL slug."""
    sku = str(node.get("sku") or node.get("productID") or "").strip()
    return sku or url.rstrip("/").rsplit("/", 1)[-1]


class ZidConnector:
    connector_id = "zid-html"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        vat = "1" if source.vat_mode.value == "incl" else "0"
        rows: list[list[str]] = []

        for url in self._product_urls(f"{base}/sitemap.xml"):
            try:
                html = self._fetcher.get(url).text
            except Exception:  # noqa: BLE001 — one dead page never kills the crawl (Q3)
                continue
            node = parse_product_jsonld(html)
            if not node:
                continue
            row = self._row(builder, node, url, source, vat)
            if row is not None:
                rows.append(row)

        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base, builder.header, rows)

    def _product_urls(self, sitemap_url: str) -> list[str]:
        try:
            locs = sitemap_locs(self._fetcher.get(sitemap_url).text)
        except Exception:  # noqa: BLE001
            return []
        products = [u for u in locs if _PRODUCT_PATH in u]
        for sub in (u for u in locs if u.endswith(".xml")):
            try:
                products += [u for u in sitemap_locs(self._fetcher.get(sub).text) if _PRODUCT_PATH in u]
            except Exception:  # noqa: BLE001
                continue
        return list(dict.fromkeys(products))  # dedupe, preserve order

    @staticmethod
    def _row(builder: RowBuilder, node: dict, url: str, source: SourceEntry, vat: str):
        price, currency, availability = offer_price(node.get("offers"))
        if not price:
            return None  # variant-priced with no usable price — needs HTML/session capture (later)
        pid = _product_id(url, node)
        in_stock = "InStock" in availability
        return builder.row(
            external_product_id=pid, external_variant_id=pid,
            external_sku=str(node.get("sku") or ""), product_name=str(node.get("name") or ""),
            brand_raw=brand_name(node), product_url=url,
            region=source.default_region, currency=currency or source.currency or "UNKNOWN", vat_included=vat,
            regular_price=price, sale_price="", effective_price=price,
            availability=Availability.IN_STOCK.value if in_stock else Availability.UNKNOWN.value,
        )
